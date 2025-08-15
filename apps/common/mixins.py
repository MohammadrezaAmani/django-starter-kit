import logging
from typing import Any, Dict, Optional

from django.core.cache import cache
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework.request import Request
from rest_framework.response import Response

from .utils import get_client_ip, get_user_agent

logger = logging.getLogger(__name__)


class CacheableViewSetMixin:
    """
    Mixin to add caching capabilities to ViewSets
    """

    cache_timeout = 300  # 5 minutes default
    cache_per_user = False
    cache_key_prefix = None

    def get_cache_key(self, request: Request, *args, **kwargs) -> str:
        """Generate cache key for the request"""
        base_key = self.cache_key_prefix or f"{self.__class__.__name__}"

        # Include view action
        action = getattr(self, "action", "unknown")
        key_parts = [base_key, action]

        # Include object pk if available
        if "pk" in kwargs:
            key_parts.append(str(kwargs["pk"]))

        # Include user ID if per-user caching
        if self.cache_per_user and request.user.is_authenticated:
            key_parts.append(f"user_{request.user.id}")

        # Include query params for list views
        if action == "list" and request.query_params:
            sorted_params = sorted(request.query_params.items())
            params_str = "&".join([f"{k}={v}" for k, v in sorted_params])
            key_parts.append(params_str)

        return ":".join(key_parts)

    def get_cached_response(
        self, request: Request, *args, **kwargs
    ) -> Optional[Response]:
        """Get cached response if available"""
        if not self.should_cache(request):
            return None

        cache_key = self.get_cache_key(request, *args, **kwargs)
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug(f"Cache hit for key: {cache_key}")
            return Response(cached_data)

        return None

    def set_cached_response(
        self, request: Request, response: Response, *args, **kwargs
    ) -> None:
        """Cache the response"""
        if not self.should_cache(request) or not response.status_code == 200:
            return

        cache_key = self.get_cache_key(request, *args, **kwargs)
        cache.set(cache_key, response.data, self.cache_timeout)
        logger.debug(f"Cached response for key: {cache_key}")

    def should_cache(self, request: Request) -> bool:
        """Determine if the request should be cached"""
        # Don't cache non-GET requests
        if request.method != "GET":
            return False

        # Don't cache if user is staff (for real-time admin data)
        if request.user.is_authenticated and request.user.is_staff:
            return False

        return True

    def invalidate_cache_pattern(self, pattern: str) -> None:
        """Invalidate cache keys matching pattern"""
        try:
            # This would require a more sophisticated cache backend
            # For now, we'll just log the pattern
            logger.info(f"Cache invalidation requested for pattern: {pattern}")
        except Exception as e:
            logger.error(f"Cache invalidation failed: {e}")


class SecurityMixin:
    """
    Mixin to add security features to views
    """

    def get_request_metadata(self, request: Request) -> Dict[str, Any]:
        """Extract request metadata for security logging"""
        return {
            "ip_address": get_client_ip(request),
            "user_agent": get_user_agent(request),
            "timestamp": timezone.now().isoformat(),
            "method": request.method,
            "path": request.path,
            "user_id": request.user.id if request.user.is_authenticated else None,
            "user_username": request.user.username
            if request.user.is_authenticated
            else None,
        }

    def log_security_event(
        self, request: Request, event_type: str, **extra_data
    ) -> None:
        """Log security-related events"""
        metadata = self.get_request_metadata(request)
        metadata.update(extra_data)

        logger.warning(f"Security Event [{event_type}]: {metadata}")

    def check_rate_limit(
        self, request: Request, key: str, limit: int, window: int
    ) -> bool:
        """Simple rate limiting check"""
        cache_key = f"rate_limit:{key}"
        current_count = cache.get(cache_key, 0)

        if current_count >= limit:
            self.log_security_event(
                request,
                "RATE_LIMIT_EXCEEDED",
                limit=limit,
                window=window,
                current_count=current_count,
            )
            return False

        # Increment counter
        cache.set(cache_key, current_count + 1, window)
        return True


class AuditMixin:
    """
    Mixin to add audit trail functionality
    """

    def create_audit_log(
        self,
        request: Request,
        action: str,
        resource_type: str,
        resource_id: Optional[str] = None,
        **extra_data,
    ) -> None:
        """Create audit log entry"""
        try:
            from apps.audit_log.models import AuditLog

            AuditLog.objects.create(
                user=request.user if request.user.is_authenticated else None,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                metadata=extra_data,
                success=True,
            )
        except Exception as e:
            logger.error(f"Failed to create audit log: {e}")

    def perform_create(self, serializer):
        """Override to add audit logging for create operations"""
        instance = serializer.save()

        if hasattr(self.request, "user"):
            self.create_audit_log(
                self.request,
                "CREATE",
                instance.__class__.__name__,
                str(instance.pk) if hasattr(instance, "pk") else None,
                data=serializer.validated_data,
            )

        return instance

    def perform_update(self, serializer):
        """Override to add audit logging for update operations"""
        instance = serializer.save()

        if hasattr(self.request, "user"):
            self.create_audit_log(
                self.request,
                "UPDATE",
                instance.__class__.__name__,
                str(instance.pk) if hasattr(instance, "pk") else None,
                data=serializer.validated_data,
            )

        return instance

    def perform_destroy(self, instance):
        """Override to add audit logging for delete operations"""
        resource_id = str(instance.pk) if hasattr(instance, "pk") else None
        resource_type = instance.__class__.__name__

        instance.delete()

        if hasattr(self.request, "user"):
            self.create_audit_log(self.request, "DELETE", resource_type, resource_id)


class PermissionMixin:
    """
    Mixin to add advanced permission checking
    """

    def check_object_permission(
        self, request: Request, obj: Any, permission_type: str = "read"
    ) -> bool:
        """Check if user has permission for specific object"""
        try:
            # Check if object has custom permission method
            if hasattr(obj, f"user_can_{permission_type}"):
                permission_method = getattr(obj, f"user_can_{permission_type}")
                return permission_method(request.user)

            # Default permission logic
            if permission_type == "read":
                return True  # Default to allowing read

            # For write operations, check ownership
            if hasattr(obj, "user") and obj.user == request.user:
                return True

            # Check if user is staff/admin
            if request.user.is_staff or request.user.is_superuser:
                return True

            return False

        except Exception as e:
            logger.error(f"Permission check failed: {e}")
            return False

    def get_filtered_queryset(self, queryset: QuerySet, request: Request) -> QuerySet:
        """Filter queryset based on user permissions"""
        if not request.user.is_authenticated:
            # For anonymous users, only return public objects
            if hasattr(queryset.model, "is_public"):
                return queryset.filter(is_public=True)
            return queryset.none()

        # For authenticated users, apply privacy filters
        if request.user.is_staff or request.user.is_superuser:
            return queryset  # Staff can see everything

        # Regular users see their own objects and public ones
        if hasattr(queryset.model, "user"):
            return queryset.filter(Q(user=request.user) | Q(is_public=True))

        return queryset


class PaginationMixin:
    """
    Mixin to add advanced pagination features
    """

    def get_paginated_data(
        self, queryset: QuerySet, request: Request
    ) -> Dict[str, Any]:
        """Get paginated data with additional metadata"""
        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
            paginated_response = self.get_paginated_response(serializer.data)

            # Add additional metadata
            paginator = self.paginator
            if hasattr(paginator, "page"):
                current_page = paginator.page
                paginated_response.data.update(
                    {
                        "page_info": {
                            "current_page": current_page.number,
                            "total_pages": current_page.paginator.num_pages,
                            "page_size": current_page.paginator.per_page,
                            "total_count": current_page.paginator.count,
                            "has_next": current_page.has_next(),
                            "has_previous": current_page.has_previous(),
                        }
                    }
                )

            return paginated_response.data

        # If no pagination, return regular serialized data
        serializer = self.get_serializer(queryset, many=True)
        return {"results": serializer.data, "count": len(serializer.data)}


class SearchMixin:
    """
    Mixin to add advanced search capabilities
    """

    def get_search_queryset(self, queryset: QuerySet, search_term: str) -> QuerySet:
        """Apply search filtering to queryset"""
        if not search_term:
            return queryset

        search_fields = getattr(self, "search_fields", [])
        if not search_fields:
            return queryset

        search_terms = search_term.split()
        search_conditions = Q()

        for term in search_terms:
            term_conditions = Q()
            for field in search_fields:
                lookup = f"{field}__icontains"
                term_conditions |= Q(**{lookup: term})
            search_conditions &= term_conditions

        return queryset.filter(search_conditions).distinct()

    def get_highlighted_results(self, queryset: QuerySet, search_term: str) -> QuerySet:
        """Add search term highlighting (would need full-text search setup)"""
        # This would typically integrate with Elasticsearch or similar
        # For now, just return the queryset
        return queryset


class ValidationMixin:
    """
    Mixin to add advanced validation features
    """

    def validate_file_upload(
        self, file_obj: Any, allowed_types: list = None, max_size: int = None
    ) -> Dict[str, Any]:
        """Validate uploaded files"""
        errors = {}

        if not file_obj:
            errors["file"] = "No file provided"
            return errors

        # Check file size
        if max_size and file_obj.size > max_size:
            errors["file"] = (
                f"File size exceeds maximum allowed size of {max_size} bytes"
            )

        # Check file type
        if allowed_types:
            file_extension = file_obj.name.split(".")[-1].lower()
            if file_extension not in allowed_types:
                errors["file"] = (
                    f"File type not allowed. Allowed types: {', '.join(allowed_types)}"
                )

        return errors

    def validate_business_rules(
        self, data: Dict[str, Any], instance: Any = None
    ) -> Dict[str, Any]:
        """Validate business rules specific to the model"""
        errors = {}

        # Override in specific view classes to add custom validation
        return errors


class OptimizationMixin:
    """
    Mixin to add query optimization features
    """

    def get_optimized_queryset(self, queryset: QuerySet) -> QuerySet:
        """Apply query optimizations"""
        # Add select_related for foreign keys
        select_related_fields = getattr(self, "select_related_fields", [])
        if select_related_fields:
            queryset = queryset.select_related(*select_related_fields)

        # Add prefetch_related for many-to-many and reverse foreign keys
        prefetch_related_fields = getattr(self, "prefetch_related_fields", [])
        if prefetch_related_fields:
            queryset = queryset.prefetch_related(*prefetch_related_fields)

        # Add only() for field limiting
        only_fields = getattr(self, "only_fields", [])
        if only_fields:
            queryset = queryset.only(*only_fields)

        return queryset

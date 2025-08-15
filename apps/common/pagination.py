from typing import Any, Optional

from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom pagination class with enhanced features:
    - Configurable page size
    - Detailed pagination metadata
    - Performance optimizations
    - Custom response format
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
    page_query_param = "page"

    def __init__(self):
        super().__init__()
        self.total_count = 0
        self.filtered_count = 0

    def paginate_queryset(
        self, queryset: QuerySet, request, view=None
    ) -> Optional[list]:
        """
        Paginate a queryset and return a page of results.
        """
        # Store original count before filtering
        self.total_count = (
            queryset.count() if hasattr(queryset, "count") else len(queryset)
        )

        page_size = self.get_page_size(request)
        if not page_size:
            return None

        paginator = self.django_paginator_class(queryset, page_size)
        page_number = self.get_page_number(request, paginator)

        try:
            self.page = paginator.page(page_number)
        except Exception:
            # Handle invalid page numbers gracefully
            self.page = paginator.page(1)

        # Store filtered count
        self.filtered_count = paginator.count

        if paginator.num_pages > 1 and self.template is not None:
            # The browsable API should display pagination controls.
            self.display_page_controls = True

        return list(self.page)

    def get_paginated_response(self, data: list) -> Response:
        """
        Return a paginated style Response object for the given output data.
        """
        return Response(
            {
                "pagination": {
                    "count": self.page.paginator.count,
                    "total_pages": self.page.paginator.num_pages,
                    "current_page": self.page.number,
                    "page_size": self.page.paginator.per_page,
                    "has_next": self.page.has_next(),
                    "has_previous": self.page.has_previous(),
                    "next_page": self.page.next_page_number()
                    if self.page.has_next()
                    else None,
                    "previous_page": self.page.previous_page_number()
                    if self.page.has_previous()
                    else None,
                    "start_index": self.page.start_index(),
                    "end_index": self.page.end_index(),
                },
                "links": {
                    "next": self.get_next_link(),
                    "previous": self.get_previous_link(),
                    "first": self.get_first_link(),
                    "last": self.get_last_link(),
                },
                "results": data,
            }
        )

    def get_first_link(self) -> Optional[str]:
        """Get the first page link"""
        if not self.page.has_previous():
            return None

        url = self.request.build_absolute_uri()
        return self.replace_query_param(url, self.page_query_param, 1)

    def get_last_link(self) -> Optional[str]:
        """Get the last page link"""
        if not self.page.has_next():
            return None

        url = self.request.build_absolute_uri()
        return self.replace_query_param(
            url, self.page_query_param, self.page.paginator.num_pages
        )

    def get_page_size(self, request) -> int:
        """
        Get the page size for the request with validation
        """
        if self.page_size_query_param:
            try:
                page_size = int(request.query_params[self.page_size_query_param])
                if page_size > 0:
                    return min(page_size, self.max_page_size)
            except (KeyError, ValueError):
                pass

        return self.page_size

    def get_page_number(self, request, paginator) -> int:
        """
        Get the page number for the request with validation
        """
        page_number = request.query_params.get(self.page_query_param, 1)
        if page_number in self.last_page_strings:
            page_number = paginator.num_pages

        try:
            page_number = int(page_number)
            if page_number < 1:
                page_number = 1
            elif page_number > paginator.num_pages and paginator.num_pages > 0:
                page_number = paginator.num_pages
        except ValueError:
            page_number = 1

        return page_number


class CursorPagination(PageNumberPagination):
    """
    Cursor-based pagination for large datasets with better performance
    """

    cursor_query_param = "cursor"
    cursor_query_description = "The pagination cursor value."
    page_size = 20
    ordering = "-created_at"  # Default ordering

    def paginate_queryset(
        self, queryset: QuerySet, request, view=None
    ) -> Optional[list]:
        """
        Paginate using cursor-based approach
        """
        self.ordering = self.get_ordering(request, queryset, view)

        if not self.ordering:
            # Fallback to regular pagination if no ordering
            return super().paginate_queryset(queryset, request, view)

        cursor = self.decode_cursor(request)
        if cursor is None:
            # First page
            queryset = queryset.order_by(*self.ordering)
            page = queryset[
                : self.page_size + 1
            ]  # Get one extra to check if there's a next page
        else:
            # Subsequent pages
            field = self.ordering[0].lstrip("-")
            reverse = self.ordering[0].startswith("-")

            if reverse:
                queryset = queryset.filter(**{f"{field}__lt": cursor}).order_by(
                    *self.ordering
                )
            else:
                queryset = queryset.filter(**{f"{field}__gt": cursor}).order_by(
                    *self.ordering
                )

            page = queryset[: self.page_size + 1]

        page = list(page)
        self.has_next = len(page) > self.page_size
        if self.has_next:
            page = page[:-1]  # Remove the extra item

        self.page = page
        return page

    def get_paginated_response(self, data: list) -> Response:
        """
        Return cursor-based pagination response
        """
        next_cursor = None
        if self.has_next and self.page:
            next_cursor = self.encode_cursor(self.page[-1])

        return Response(
            {
                "pagination": {
                    "has_next": self.has_next,
                    "next_cursor": next_cursor,
                    "page_size": len(data),
                },
                "results": data,
            }
        )

    def decode_cursor(self, request) -> Optional[Any]:
        """
        Decode cursor from request
        """
        cursor = request.query_params.get(self.cursor_query_param)
        if not cursor:
            return None

        try:
            # Simple base64 decoding - in production, use more secure encoding
            import base64
            import json

            decoded = base64.b64decode(cursor).decode("utf-8")
            return json.loads(decoded)
        except Exception:
            return None

    def encode_cursor(self, obj) -> str:
        """
        Encode cursor for object
        """
        try:
            import base64
            import json

            if hasattr(obj, self.ordering[0].lstrip("-")):
                field_name = self.ordering[0].lstrip("-")
                value = getattr(obj, field_name)

                # Handle datetime serialization
                if hasattr(value, "isoformat"):
                    value = value.isoformat()

                cursor_data = json.dumps(value, default=str)
                return base64.b64encode(cursor_data.encode("utf-8")).decode("utf-8")
        except Exception:
            pass

        return ""

    def get_ordering(self, request, queryset, view) -> list:
        """
        Get ordering for the queryset
        """
        ordering = getattr(view, "ordering", self.ordering)
        if isinstance(ordering, str):
            ordering = [ordering]
        return ordering or ["-id"]  # Fallback to id ordering


class OptimizedPagination(CustomPageNumberPagination):
    """
    Optimized pagination for large datasets using database-level optimization
    """

    def paginate_queryset(
        self, queryset: QuerySet, request, view=None
    ) -> Optional[list]:
        """
        Optimized pagination with count optimization
        """
        page_size = self.get_page_size(request)
        if not page_size:
            return None

        # For large datasets, estimate count instead of exact count
        estimated_count = self.get_estimated_count(queryset)

        if estimated_count > 10000:  # For very large datasets
            # Use LIMIT/OFFSET without exact count
            page_number = self.get_page_number(request, None)
            offset = (page_number - 1) * page_size

            # Get page_size + 1 to check if there are more results
            page_results = list(queryset[offset : offset + page_size + 1])

            has_next = len(page_results) > page_size
            if has_next:
                page_results = page_results[:-1]

            # Create a mock page object
            self.page = type(
                "MockPage",
                (),
                {
                    "object_list": page_results,
                    "number": page_number,
                    "has_next": lambda: has_next,
                    "has_previous": lambda: page_number > 1,
                    "next_page_number": lambda: page_number + 1 if has_next else None,
                    "previous_page_number": lambda: page_number - 1
                    if page_number > 1
                    else None,
                    "start_index": lambda: offset + 1 if page_results else 0,
                    "end_index": lambda: offset + len(page_results),
                    "paginator": type(
                        "MockPaginator",
                        (),
                        {
                            "count": estimated_count,
                            "num_pages": -1,  # Unknown
                            "per_page": page_size,
                        },
                    )(),
                },
            )()

            return page_results
        else:
            # Use regular pagination for smaller datasets
            return super().paginate_queryset(queryset, request, view)

    def get_estimated_count(self, queryset: QuerySet) -> int:
        """
        Get estimated count for large querysets
        """
        try:
            # Try to get an estimate from database statistics
            # This is database-specific and would need to be implemented per backend
            return queryset.count()
        except Exception:
            return 0

    def get_paginated_response(self, data: list) -> Response:
        """
        Return optimized pagination response
        """
        if (
            hasattr(self.page.paginator, "num_pages")
            and self.page.paginator.num_pages == -1
        ):
            # For estimated count responses
            return Response(
                {
                    "pagination": {
                        "count": f"~{self.page.paginator.count}",  # Approximate count
                        "total_pages": "unknown",
                        "current_page": self.page.number,
                        "page_size": self.page.paginator.per_page,
                        "has_next": self.page.has_next(),
                        "has_previous": self.page.has_previous(),
                        "next_page": self.page.next_page_number()
                        if self.page.has_next()
                        else None,
                        "previous_page": self.page.previous_page_number()
                        if self.page.has_previous()
                        else None,
                        "start_index": self.page.start_index(),
                        "end_index": self.page.end_index(),
                        "estimated": True,
                    },
                    "links": {
                        "next": self.get_next_link(),
                        "previous": self.get_previous_link(),
                    },
                    "results": data,
                }
            )
        else:
            # Regular pagination response
            return super().get_paginated_response(data)


class InfinitePagination(PageNumberPagination):
    """
    Infinite scroll pagination for mobile apps and modern web interfaces
    """

    page_size = 20
    page_size_query_param = "limit"
    offset_query_param = "offset"

    def paginate_queryset(
        self, queryset: QuerySet, request, view=None
    ) -> Optional[list]:
        """
        Paginate using offset-based approach for infinite scroll
        """
        limit = self.get_page_size(request)
        offset = self.get_offset(request)

        if limit is None:
            return None

        # Get limit + 1 to check if there are more results
        results = list(queryset[offset : offset + limit + 1])

        self.has_next = len(results) > limit
        if self.has_next:
            results = results[:-1]

        self.offset = offset
        self.limit = limit
        self.results = results

        return results

    def get_offset(self, request) -> int:
        """
        Get offset from request parameters
        """
        try:
            return max(0, int(request.query_params.get(self.offset_query_param, 0)))
        except ValueError:
            return 0

    def get_paginated_response(self, data: list) -> Response:
        """
        Return infinite scroll pagination response
        """
        next_offset = None
        if self.has_next:
            next_offset = self.offset + self.limit

        return Response(
            {
                "pagination": {
                    "has_next": self.has_next,
                    "next_offset": next_offset,
                    "current_offset": self.offset,
                    "limit": self.limit,
                    "returned_count": len(data),
                },
                "results": data,
            }
        )

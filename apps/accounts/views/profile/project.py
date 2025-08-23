import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

from ...models import ActivityLog, Project, ProjectImage, Task
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import ProjectImageSerializer, ProjectSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class ProjectViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user projects and portfolio items.
    """

    serializer_class = ProjectSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["category", "status", "is_current"]
    search_fields = ["title", "description", "technologies", "role"]
    ordering_fields = ["start_date", "end_date", "title", "category"]
    ordering = ["-start_date"]

    def get_queryset(self):
        """Filter projects based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's projects")
                    return Project.objects.filter(user=user).prefetch_related("images")
                except User.DoesNotExist:
                    return Project.objects.none()
            else:
                return Project.objects.filter(user=self.request.user).prefetch_related(
                    "images"
                )

        return Project.objects.filter(user=self.request.user).prefetch_related("images")

    def get_permissions(self):
        if self.action in ["list", "retrieve", "by_category", "by_status", "featured"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["upload_images", "delete_image"]:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create project for the current user."""
        project = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
            description=f"Added project: {project.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update project and log activity."""
        project = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
            description=f"Updated project: {project.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete project and log activity."""
        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
            description=f"Deleted project: {instance.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user projects with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing projects: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get projects"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        request=ProjectSerializer,
        responses={201: ProjectSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new project entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current projects cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating project: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        request=ProjectSerializer,
        responses={200: ProjectSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a project entry."""
        try:
            # Validate that if is_current is True, no end_date should be provided
            if request.data.get("is_current") and request.data.get("end_date"):
                return Response(
                    {"error": "Current projects cannot have an end date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating project: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a project entry."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting project: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def current(self, request):
        """Get current/ongoing projects."""
        try:
            current_projects = self.get_queryset().filter(is_current=True)
            serializer = self.get_serializer(current_projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting current projects: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get current projects"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_category(self, request):
        """Get projects by category."""
        try:
            category = request.query_params.get("category")
            if not category:
                return Response(
                    {"error": "Category parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            projects = self.get_queryset().filter(category=category)
            serializer = self.get_serializer(projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting projects by category: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get projects by category"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_status(self, request):
        """Get projects by status."""
        try:
            project_status = request.query_params.get("status")
            if not project_status:
                return Response(
                    {"error": "Status parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            projects = self.get_queryset().filter(status=project_status)
            serializer = self.get_serializer(projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting projects by status: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get projects by status"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def featured(self, request):
        """Get featured projects (most recent and significant)."""
        try:
            featured_projects = (
                self.get_queryset()
                .filter(status=Project.ProjectStatus.COMPLETED)
                .order_by("-start_date")[:6]
            )
            serializer = self.get_serializer(featured_projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting featured projects: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get featured projects"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: {"technologies": "list"}},
    )
    @action(detail=False, methods=["get"])
    def technologies(self, request):
        """Get all technologies used across projects."""
        try:
            projects = self.get_queryset()
            all_technologies = set()

            for project in projects:
                if project.technologies:
                    all_technologies.update(project.technologies)

            return Response({"technologies": sorted(list(all_technologies))})
        except Exception as e:
            logger.error(f"Error getting project technologies: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get project technologies"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        request=ProjectImageSerializer,
        responses={201: ProjectImageSerializer(many=True)},
    )
    @action(detail=True, methods=["post"], parser_classes=[MultiPartParser, FormParser])
    def upload_images(self, request, pk=None):
        """Upload additional images for a project."""
        try:
            project = self.get_object()

            if "images" not in request.FILES:
                return Response(
                    {"error": "No images provided"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            images = request.FILES.getlist("images")
            created_images = []

            with transaction.atomic():
                for idx, image in enumerate(images):
                    project_image = ProjectImage.objects.create(
                        project=project,
                        image=image,
                        caption=request.data.get(f"caption_{idx}", ""),
                        order=idx,
                    )
                    created_images.append(project_image)

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
                description=f"Uploaded {len(images)} images to project: {project.title}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            serializer = ProjectImageSerializer(created_images, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error uploading project images: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to upload project images"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={204: None},
    )
    @action(
        detail=True, methods=["delete"], url_path="delete-image/(?P<image_id>[^/.]+)"
    )
    def delete_image(self, request, pk=None, image_id=None):
        """Delete a project image."""
        try:
            project = self.get_object()

            project_image = ProjectImage.objects.filter(
                id=image_id, project=project
            ).first()

            if not project_image:
                return Response(
                    {"error": "Project image not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            project_image.delete()

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
                description=f"Deleted image from project: {project.title}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            logger.error(f"Error deleting project image: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete project image"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: {"tasks": "list"}},
    )
    @action(detail=True, methods=["get"])
    def tasks(self, request, pk=None):
        """Get tasks associated with a project."""
        try:
            project = self.get_object()

            # Import here to avoid circular imports
            from ...serializers import TaskSerializer

            tasks = (
                Task.objects.filter(project=project)
                .select_related("assignee", "created_by")
                .order_by("-created_at")
            )

            page = self.paginate_queryset(tasks)
            if page is not None:
                serializer = TaskSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = TaskSerializer(tasks, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting project tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get project tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_technology(self, request):
        """Get projects that use specific technology."""
        try:
            technology = request.query_params.get("technology")
            if not technology:
                return Response(
                    {"error": "Technology parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            projects = self.get_queryset().filter(technologies__contains=[technology])
            serializer = self.get_serializer(projects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(
                f"Error getting projects by technology: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get projects by technology"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: ProjectSerializer},
    )
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Duplicate a project."""
        try:
            original_project = self.get_object()

            # Create a copy of the project
            new_project = Project.objects.create(
                user=self.request.user,
                title=f"{original_project.title} (Copy)",
                description=original_project.description,
                start_date=original_project.start_date,
                end_date=original_project.end_date,
                is_current=False,  # Copies are not current by default
                url=original_project.url,
                github_url=original_project.github_url,
                technologies=(
                    original_project.technologies.copy()
                    if original_project.technologies
                    else []
                ),
                role=original_project.role,
                team_size=original_project.team_size,
                category=original_project.category,
                status=Project.ProjectStatus.IN_PROGRESS,  # Default status for copies
            )

            # Copy project images
            for image in original_project.images.all():
                ProjectImage.objects.create(
                    project=new_project,
                    image=image.image,
                    caption=image.caption,
                    order=image.order,
                )

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROJECT_UPDATE,
                description=f"Duplicated project: {original_project.title}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(new_project)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error duplicating project: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to duplicate project"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Projects"],
        responses={200: {"statistics": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """Get project statistics for the user."""
        try:
            queryset = self.get_queryset()

            stats = {
                "total_projects": queryset.count(),
                "completed_projects": queryset.filter(
                    status=Project.ProjectStatus.COMPLETED
                ).count(),
                "in_progress_projects": queryset.filter(
                    status=Project.ProjectStatus.IN_PROGRESS
                ).count(),
                "on_hold_projects": queryset.filter(
                    status=Project.ProjectStatus.ON_HOLD
                ).count(),
                "cancelled_projects": queryset.filter(
                    status=Project.ProjectStatus.CANCELLED
                ).count(),
                "projects_by_category": {},
                "technologies_used": set(),
                "average_team_size": 0,
            }

            # Calculate category breakdown
            for category, _ in Project.ProjectCategory.choices:
                count = queryset.filter(category=category).count()
                if count > 0:
                    stats["projects_by_category"][category] = count

            # Get all technologies used
            for project in queryset:
                if project.technologies:
                    stats["technologies_used"].update(project.technologies)

            stats["technologies_used"] = sorted(list(stats["technologies_used"]))

            # Calculate average team size
            team_sizes = [p.team_size for p in queryset if p.team_size]
            if team_sizes:
                stats["average_team_size"] = sum(team_sizes) / len(team_sizes)

            return Response({"statistics": stats})

        except Exception as e:
            logger.error(f"Error getting project statistics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get project statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

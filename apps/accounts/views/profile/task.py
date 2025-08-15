import logging

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ...models import ActivityLog, Notification, Task, TaskComment
from ...permissions import IsTaskAssigneeOrCreator
from ...serializers import TaskCommentSerializer, TaskSerializer
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

logger = logging.getLogger(__name__)
User = get_user_model()


class TaskViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing tasks and task assignments.
    """

    serializer_class = TaskSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "priority", "assignee", "created_by", "project"]
    search_fields = ["title", "description", "tags"]
    ordering_fields = ["due_date", "created_at", "priority", "status"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter tasks based on user permissions and roles."""
        user = self.request.user

        # Admins can see all tasks
        if user.is_staff:
            return Task.objects.select_related(
                "assignee", "created_by", "project"
            ).prefetch_related("comments__user", "watchers")

        # Users can see tasks they're assigned to, created, or watching
        return (
            Task.objects.filter(
                Q(assignee=user) | Q(created_by=user) | Q(watchers=user)
            )
            .select_related("assignee", "created_by", "project")
            .prefetch_related("comments__user", "watchers")
            .distinct()
        )

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "my_tasks",
            "assigned_to_me",
            "created_by_me",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update", "destroy"]:
            permission_classes = [permissions.IsAuthenticated, IsTaskAssigneeOrCreator]
        elif self.action in [
            "assign",
            "complete",
            "reopen",
            "add_watcher",
            "remove_watcher",
        ]:
            permission_classes = [permissions.IsAuthenticated, IsTaskAssigneeOrCreator]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create task and send notifications."""
        # Set default assignee to current user if not specified
        assignee = serializer.validated_data.get("assignee", self.request.user)

        task = serializer.save(created_by=self.request.user, assignee=assignee)

        # Create notification if assignee is different from creator
        if task.assignee != self.request.user:
            Notification.objects.create(
                recipient=task.assignee,
                sender=self.request.user,
                notification_type=Notification.NotificationType.TASK_ASSIGNED,
                title=f"New task assigned: {task.title}",
                message=f"{self.request.user.get_full_name()} assigned you a new task: {task.title}",
                data={"task_id": str(task.id)},
            )

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Created task: {task.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update task and log changes."""
        old_task = self.get_object()
        old_status = old_task.status
        old_assignee = old_task.assignee

        task = serializer.save()

        # Check for status changes
        if old_status != task.status:
            if task.status == Task.TaskStatus.COMPLETED:
                task.completed_at = timezone.now()
                task.save(update_fields=["completed_at"])

                # Notify task creator if different from assignee
                if task.created_by != task.assignee:
                    Notification.objects.create(
                        recipient=task.created_by,
                        sender=self.request.user,
                        notification_type=Notification.NotificationType.TASK_COMPLETED,
                        title=f"Task completed: {task.title}",
                        message=f"Task '{task.title}' has been completed.",
                        data={"task_id": str(task.id)},
                    )

        # Check for assignee changes
        if old_assignee != task.assignee:
            Notification.objects.create(
                recipient=task.assignee,
                sender=self.request.user,
                notification_type=Notification.NotificationType.TASK_ASSIGNED,
                title=f"Task reassigned: {task.title}",
                message=f"You have been assigned to task: {task.title}",
                data={"task_id": str(task.id)},
            )

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description=f"Updated task: {task.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List tasks with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def my_tasks(self, request):
        """Get all tasks related to the current user."""
        try:
            tasks = self.get_queryset()

            page = self.paginate_queryset(tasks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(tasks, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting user tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get user tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def assigned_to_me(self, request):
        """Get tasks assigned to the current user."""
        try:
            tasks = self.get_queryset().filter(assignee=request.user)

            page = self.paginate_queryset(tasks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(tasks, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting assigned tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get assigned tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def created_by_me(self, request):
        """Get tasks created by the current user."""
        try:
            tasks = self.get_queryset().filter(created_by=request.user)

            page = self.paginate_queryset(tasks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(tasks, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting created tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get created tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to assign task to"
            ),
        ],
        responses={200: TaskSerializer},
    )
    @action(detail=True, methods=["post"])
    def assign(self, request, pk=None):
        """Assign task to a user."""
        try:
            task = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                new_assignee = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            old_assignee = task.assignee
            task.assignee = new_assignee
            task.save()

            # Create notification for new assignee
            if new_assignee != request.user:
                Notification.objects.create(
                    recipient=new_assignee,
                    sender=request.user,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,
                    title=f"Task assigned: {task.title}",
                    message=f"You have been assigned to task: {task.title}",
                    data={"task_id": str(task.id)},
                )

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Reassigned task '{task.title}' from {old_assignee.username} to {new_assignee.username}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(task)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error assigning task: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to assign task"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer},
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Mark task as completed."""
        try:
            task = self.get_object()

            if task.status == Task.TaskStatus.COMPLETED:
                return Response(
                    {"error": "Task is already completed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            task.status = Task.TaskStatus.COMPLETED
            task.completed_at = timezone.now()
            task.save()

            # Notify task creator if different from assignee
            if task.created_by != task.assignee:
                Notification.objects.create(
                    recipient=task.created_by,
                    sender=request.user,
                    notification_type=Notification.NotificationType.TASK_COMPLETED,
                    title=f"Task completed: {task.title}",
                    message=f"Task '{task.title}' has been completed by {request.user.get_full_name()}.",
                    data={"task_id": str(task.id)},
                )

            # Notify watchers
            for watcher in task.watchers.exclude(
                id__in=[request.user.id, task.created_by.id]
            ):
                Notification.objects.create(
                    recipient=watcher,
                    sender=request.user,
                    notification_type=Notification.NotificationType.TASK_COMPLETED,
                    title=f"Task completed: {task.title}",
                    message=f"Task '{task.title}' has been completed.",
                    data={"task_id": str(task.id)},
                )

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Completed task: {task.title}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(task)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error completing task: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to complete task"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer},
    )
    @action(detail=True, methods=["post"])
    def reopen(self, request, pk=None):
        """Reopen a completed task."""
        try:
            task = self.get_object()

            if task.status != Task.TaskStatus.COMPLETED:
                return Response(
                    {"error": "Only completed tasks can be reopened"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            task.status = Task.TaskStatus.IN_PROGRESS
            task.completed_at = None
            task.save()

            # Log activity
            ActivityLog.objects.create(
                user=self.request.user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Reopened task: {task.title}",
                ip_address=self.request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(task)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error reopening task: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to reopen task"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        request=TaskCommentSerializer,
        responses={201: TaskCommentSerializer},
    )
    @action(detail=True, methods=["post"])
    def add_comment(self, request, pk=None):
        """Add a comment to a task."""
        try:
            task = self.get_object()

            serializer = TaskCommentSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            comment = TaskComment.objects.create(
                task=task,
                user=request.user,
                content=serializer.validated_data["content"],
            )

            # Notify task participants
            participants = set([task.assignee, task.created_by])
            participants.update(task.watchers.all())
            participants.discard(request.user)  # Don't notify the commenter

            for participant in participants:
                Notification.objects.create(
                    recipient=participant,
                    sender=request.user,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,  # Reusing this type
                    title=f"New comment on task: {task.title}",
                    message=f"{request.user.get_full_name()} commented on task '{task.title}'.",
                    data={"task_id": str(task.id), "comment_id": str(comment.id)},
                )

            return Response(
                TaskCommentSerializer(comment).data,
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            logger.error(f"Error adding task comment: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to add comment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to add as watcher"
            ),
        ],
        responses={200: TaskSerializer},
    )
    @action(detail=True, methods=["post"])
    def add_watcher(self, request, pk=None):
        """Add a watcher to a task."""
        try:
            task = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                watcher = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            task.watchers.add(watcher)

            # Notify the new watcher
            if watcher != request.user:
                Notification.objects.create(
                    recipient=watcher,
                    sender=request.user,
                    notification_type=Notification.NotificationType.TASK_ASSIGNED,
                    title=f"Added as watcher to task: {task.title}",
                    message=f"You have been added as a watcher to task: {task.title}",
                    data={"task_id": str(task.id)},
                )

            serializer = self.get_serializer(task)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error adding task watcher: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to add watcher"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        parameters=[
            OpenApiParameter(
                "user_id", OpenApiTypes.INT, description="User ID to remove as watcher"
            ),
        ],
        responses={200: TaskSerializer},
    )
    @action(detail=True, methods=["delete"])
    def remove_watcher(self, request, pk=None):
        """Remove a watcher from a task."""
        try:
            task = self.get_object()
            user_id = request.data.get("user_id")

            if not user_id:
                return Response(
                    {"error": "user_id is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                watcher = User.objects.get(id=user_id)
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            task.watchers.remove(watcher)

            serializer = self.get_serializer(task)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error removing task watcher: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to remove watcher"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: {"statistics": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def statistics(self, request):
        """Get task statistics for the current user."""
        try:
            queryset = self.get_queryset()

            stats = {
                "total_tasks": queryset.count(),
                "assigned_to_me": queryset.filter(assignee=request.user).count(),
                "created_by_me": queryset.filter(created_by=request.user).count(),
                "completed_tasks": queryset.filter(
                    status=Task.TaskStatus.COMPLETED
                ).count(),
                "in_progress_tasks": queryset.filter(
                    status=Task.TaskStatus.IN_PROGRESS
                ).count(),
                "todo_tasks": queryset.filter(status=Task.TaskStatus.TODO).count(),
                "overdue_tasks": queryset.filter(
                    due_date__lt=timezone.now(),
                    status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
                ).count(),
                "tasks_by_priority": {},
                "completion_rate": 0,
            }

            # Calculate priority breakdown
            for priority, _ in Task.TaskPriority.choices:
                count = queryset.filter(priority=priority).count()
                if count > 0:
                    stats["tasks_by_priority"][priority] = count

            # Calculate completion rate
            total = stats["total_tasks"]
            if total > 0:
                completed = stats["completed_tasks"]
                stats["completion_rate"] = round((completed / total) * 100, 2)

            return Response({"statistics": stats})

        except Exception as e:
            logger.error(f"Error getting task statistics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get task statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def overdue(self, request):
        """Get overdue tasks."""
        try:
            overdue_tasks = self.get_queryset().filter(
                due_date__lt=timezone.now(),
                status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
            )

            page = self.paginate_queryset(overdue_tasks)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(overdue_tasks, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting overdue tasks: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get overdue tasks"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def due_today(self, request):
        """Get tasks due today."""
        try:
            today = timezone.now().date()
            due_today_tasks = self.get_queryset().filter(
                due_date__date=today,
                status__in=[Task.TaskStatus.TODO, Task.TaskStatus.IN_PROGRESS],
            )

            serializer = self.get_serializer(due_today_tasks, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting tasks due today: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get tasks due today"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Tasks"],
        responses={200: TaskCommentSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def comments(self, request, pk=None):
        """Get comments for a task."""
        try:
            task = self.get_object()
            comments = task.comments.select_related("user").order_by("created_at")

            page = self.paginate_queryset(comments)
            if page is not None:
                serializer = TaskCommentSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = TaskCommentSerializer(comments, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting task comments: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get task comments"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

import logging

from django.contrib.auth import get_user_model
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from ..permissions import IsAdminUser, IsAdminUserOrReadOnly, IsOwnerOrAdmin
from ..serializers import RegisterSerializer, UserSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

    def get_paginated_response(self, data):
        return Response(
            {
                "count": self.page.paginator.count,
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
            }
        )


class UserThrottle(UserRateThrottle):
    rate = "100/hour"


class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("username")
    serializer_class = UserSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active", "is_staff", "is_verified"]
    search_fields = ["username", "email"]
    ordering_fields = ["username", "email", "date_joined", "last_activity"]
    ordering = ["username"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated, IsAdminUserOrReadOnly]
        elif self.action in [
            "create",
            "update",
            "partial_update",
            "destroy",
            "bulk_delete",
        ]:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        elif self.action == "upload_profile_picture":
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        else:
            permission_classes = [permissions.IsAuthenticated, IsAdminUser]
        return [permission() for permission in permission_classes]

    def get_serializer_class(self):  # type: ignore
        if self.action == "create":
            return RegisterSerializer
        return UserSerializer

    @extend_schema(
        tags=["User Management"],
        responses={
            200: UserSerializer(many=True),
            401: OpenApiResponse(
                description="Unauthorized",
                examples=[
                    OpenApiExample(
                        "Unauthorized",
                        value={
                            "detail": "Authentication credentials were not provided"
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Forbidden",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "detail": "You do not have permission to perform this action"
                        },
                    )
                ],
            ),
        },
        parameters=[
            OpenApiParameter(
                name="is_active",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by active status",
            ),
            OpenApiParameter(
                name="is_staff",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by staff status",
            ),
            OpenApiParameter(
                name="is_verified",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Filter by email verification status",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Search by username or email",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Order by username, email, date_joined, or last_activity",
            ),
        ],
        description="Retrieves a paginated list of users with filtering, searching, and ordering. Accessible to admins and staff (read-only).",
        examples=[
            OpenApiExample(
                "List users response",
                value={
                    "count": 2,
                    "next": None,
                    "previous": None,
                    "results": [
                        {
                            "id": 1,
                            "username": "admin",
                            "email": "admin@example.com",
                            "first_name": "Admin",
                            "last_name": "User",
                            "last_login": "2025-05-16T12:00:00Z",
                            "date_joined": "2025-05-16T12:00:00Z",
                            "is_verified": True,
                            "last_activity": "2025-05-16T12:00:00Z",
                        },
                        {
                            "id": 2,
                            "username": "user",
                            "email": "user@example.com",
                            "first_name": "Regular",
                            "last_name": "User",
                            "last_login": None,
                            "date_joined": "2025-05-16T12:00:00Z",
                            "is_verified": False,
                            "last_activity": None,
                        },
                    ],
                },
                response_only=True,
            )
        ],
    )
    def list(self, request, *args, **kwargs):
        try:
            queryset = self.filter_queryset(self.get_queryset())
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer = self.get_serializer(queryset, many=True)
            logger.info(f"User list accessed by {request.user.username}")
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error listing users: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        responses={
            200: UserSerializer,
            404: OpenApiResponse(
                description="Not found",
                examples=[
                    OpenApiExample(
                        "Not found",
                        value={"detail": "Not found"},
                    )
                ],
            ),
        },
        description="Retrieves details of a specific user. Accessible to admins, staff, or the user themselves.",
    )
    def retrieve(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            serializer = self.get_serializer(instance)
            logger.info(
                f"User {instance.username} details accessed by {request.user.username}"
            )
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error retrieving user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request=RegisterSerializer,
        responses={
            201: UserSerializer,
            400: OpenApiResponse(
                description="Invalid input",
                examples=[
                    OpenApiExample(
                        "Invalid input",
                        value={"error": "Email already exists"},
                    )
                ],
            ),
        },
        description="Creates a new user. Accessible to admins or during registration.",
    )
    def create(self, request, *args, **kwargs):
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            headers = self.get_success_headers(serializer.data)
            logger.info(
                f"User created by {request.user.username}: {serializer.data['username']}"
            )
            return Response(
                serializer.data, status=status.HTTP_201_CREATED, headers=headers
            )
        except ValidationError as e:
            logger.warning(f"Validation error during user creation: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error creating user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        responses={
            200: UserSerializer,
            400: OpenApiResponse(
                description="Invalid input",
                examples=[
                    OpenApiExample(
                        "Invalid input",
                        value={"error": "Invalid data"},
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Forbidden",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "detail": "You do not have permission to perform this action"
                        },
                    )
                ],
            ),
        },
        description="Updates a user's information. Accessible to admins or the user themselves.",
    )
    def update(self, request, *args, **kwargs):
        try:
            partial = kwargs.pop("partial", False)
            instance = self.get_object()
            serializer = self.get_serializer(
                instance, data=request.data, partial=partial
            )
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            logger.info(f"User {instance.username} updated by {request.user.username}")
            return Response(serializer.data)
        except ValidationError as e:
            logger.warning(f"Validation error during user update: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error updating user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        responses={
            204: OpenApiResponse(
                description="User deleted successfully",
            ),
            403: OpenApiResponse(
                description="Forbidden",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "detail": "You do not have permission to perform this action"
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                description="Not found",
                examples=[
                    OpenApiExample(
                        "Not found",
                        value={"detail": "Not found"},
                    )
                ],
            ),
        },
        description="Deletes a user. Accessible to admins or the user themselves.",
    )
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            logger.info(f"User {instance.username} deleted by {request.user.username}")
            self.perform_destroy(instance)
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error deleting user: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request={
            "multipart/form-data": {
                "type": "object",
                "properties": {
                    "profile_picture": {"type": "string", "format": "binary"},
                },
            }
        },
        responses={
            200: UserSerializer,
            400: OpenApiResponse(
                description="Invalid input",
                examples=[
                    OpenApiExample(
                        "Invalid input",
                        value={"error": "No file was submitted"},
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Forbidden",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "detail": "You do not have permission to perform this action"
                        },
                    )
                ],
            ),
        },
        description="Uploads or updates a user's profile picture. Accessible to admins or the user themselves.",
    )
    @action(detail=True, methods=["post"], url_path="upload-profile-picture")
    def upload_profile_picture(self, request, pk=None):
        try:
            user = self.get_object()
            if "profile_picture" not in request.FILES:
                return Response(
                    {"error": "No file was submitted"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user.profile_picture = request.FILES["profile_picture"]
            user.save()
            serializer = self.get_serializer(user)
            logger.info(
                f"Profile picture updated for user {user.username} by {request.user.username}"
            )
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ValidationError as e:
            logger.warning(f"Validation error during profile picture upload: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Error uploading profile picture: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["User Management"],
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "user_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of user IDs to delete",
                    }
                },
                "required": ["user_ids"],
            }
        },
        responses={
            204: OpenApiResponse(
                description="Users deleted successfully",
            ),
            400: OpenApiResponse(
                description="Invalid input",
                examples=[
                    OpenApiExample(
                        "Invalid input",
                        value={"error": "user_ids is required"},
                    )
                ],
            ),
            403: OpenApiResponse(
                description="Forbidden",
                examples=[
                    OpenApiExample(
                        "Forbidden",
                        value={
                            "detail": "You do not have permission to perform this action"
                        },
                    )
                ],
            ),
        },
        description="Bulk deletes users by IDs. Accessible to admins only.",
        examples=[
            OpenApiExample(
                "Bulk delete request", value={"user_ids": [2, 3, 4]}, request_only=True
            )
        ],
    )
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    def bulk_delete(self, request):
        try:
            if not request.user.is_staff:
                return Response(
                    {"detail": "You do not have permission to perform this action"},
                    status=status.HTTP_403_FORBIDDEN,
                )

            user_ids = request.data.get("user_ids", [])
            if not user_ids:
                return Response(
                    {"error": "user_ids is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Prevent deleting superusers or the requesting user
            users_to_delete = User.objects.filter(
                id__in=user_ids, is_superuser=False
            ).exclude(id=request.user.id)

            count = users_to_delete.count()
            if count == 0:
                return Response(
                    {"error": "No valid users to delete"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            users_to_delete.delete()
            logger.info(f"Bulk deleted {count} users by {request.user.username}")
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            logger.error(f"Error during bulk delete: {str(e)}", exc_info=True)
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

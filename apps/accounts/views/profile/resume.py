import logging

from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from ...models import ActivityLog, Resume
from ...permissions import IsOwnerOrAdmin, can_view_user_profile
from ...serializers import ResumeSerializer
from ..user import StandardResultsSetPagination, UserThrottle

logger = logging.getLogger(__name__)
User = get_user_model()


class ResumeViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user resumes with PDF generation and templates.
    """

    serializer_class = ResumeSerializer
    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserThrottle]
    parser_classes = [MultiPartParser, FormParser]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "template", "is_default"]
    search_fields = ["title", "description"]
    ordering_fields = ["created_at", "updated_at", "title"]
    ordering = ["-updated_at"]

    def get_queryset(self):
        """Filter resumes based on user and permissions."""
        if self.action == "list":
            # Get user from query params or current user
            user_id = self.request.query_params.get("user_id")
            if user_id:
                try:
                    user = User.objects.get(id=user_id)
                    if not can_view_user_profile(self.request.user, user):
                        raise PermissionDenied("Cannot view this user's resumes")
                    # Only show published resumes for other users
                    return Resume.objects.filter(
                        user=user, status=Resume.ResumeStatus.PUBLISHED
                    )
                except User.DoesNotExist:
                    return Resume.objects.none()
            else:
                return Resume.objects.filter(user=self.request.user)

        return Resume.objects.filter(user=self.request.user)

    def get_permissions(self):
        if self.action in [
            "list",
            "retrieve",
            "download",
            "templates",
            "generate_pdf",
        ]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create resume for the current user."""
        # If this is the first resume, make it default
        if not Resume.objects.filter(user=self.request.user).exists():
            serializer.validated_data["is_default"] = True

        resume = serializer.save(user=self.request.user)

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RESUME_CREATED,
            description=f"Created resume: {resume.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_update(self, serializer):
        """Update resume and log activity."""
        resume = serializer.save()

        # Log activity
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RESUME_UPDATED,
            description=f"Updated resume: {resume.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

    def perform_destroy(self, instance):
        """Delete resume and log activity."""
        # If deleting default resume, set another as default
        if instance.is_default:
            other_resume = (
                Resume.objects.filter(user=self.request.user)
                .exclude(id=instance.id)
                .first()
            )
            if other_resume:
                other_resume.is_default = True
                other_resume.save()

        # Log activity before deletion
        ActivityLog.objects.create(
            user=self.request.user,
            activity_type=ActivityLog.ActivityType.RESUME_DELETED,
            description=f"Deleted resume: {instance.title}",
            ip_address=self.request.META.get("REMOTE_ADDR"),
        )

        instance.delete()

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List user resumes with filtering and search."""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing resumes: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get resumes"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        request=ResumeSerializer,
        responses={201: ResumeSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new resume."""
        try:
            # Check resume limit (max 5 resumes per user)
            resume_count = Resume.objects.filter(user=request.user).count()
            if resume_count >= 5:
                return Response(
                    {"error": "Maximum 5 resumes allowed per user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        request=ResumeSerializer,
        responses={200: ResumeSerializer},
    )
    def update(self, request, *args, **kwargs):
        """Update a resume."""
        try:
            return super().update(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error updating resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={204: None},
    )
    def destroy(self, request, *args, **kwargs):
        """Delete a resume."""
        try:
            return super().destroy(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error deleting resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to delete resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def set_default(self, request, pk=None):
        """Set resume as default."""
        try:
            resume = self.get_object()

            # Remove default from all other resumes
            Resume.objects.filter(user=request.user).update(is_default=False)

            # Set this resume as default
            resume.is_default = True
            resume.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_UPDATED,
                description=f"Set resume as default: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error setting default resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to set default resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def publish(self, request, pk=None):
        """Publish a resume."""
        try:
            resume = self.get_object()

            if resume.status == Resume.ResumeStatus.PUBLISHED:
                return Response(
                    {"error": "Resume is already published"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            resume.status = Resume.ResumeStatus.PUBLISHED
            resume.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_PUBLISHED,
                description=f"Published resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error publishing resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to publish resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def unpublish(self, request, pk=None):
        """Unpublish a resume."""
        try:
            resume = self.get_object()

            if resume.status != Resume.ResumeStatus.PUBLISHED:
                return Response(
                    {"error": "Resume is not published"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            resume.status = Resume.ResumeStatus.DRAFT
            resume.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_UPDATED,
                description=f"Unpublished resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error unpublishing resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to unpublish resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: "application/pdf"},
    )
    @action(detail=True, methods=["get"])
    def download(self, request, pk=None):
        """Download resume as PDF."""
        try:
            resume = self.get_object()

            # Check if user can access this resume
            if resume.user != request.user:
                if not can_view_user_profile(request.user, resume.user):
                    raise PermissionDenied("Cannot access this resume")
                if resume.status != Resume.ResumeStatus.PUBLISHED:
                    raise PermissionDenied("Resume is not published")

            # Generate PDF content (placeholder - implement with reportlab or weasyprint)
            pdf_content = self._generate_pdf(resume)

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_DOWNLOADED,
                description=f"Downloaded resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="{resume.title}.pdf"'
            )
            return response
        except Exception as e:
            logger.error(f"Error downloading resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to download resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: "application/pdf"},
    )
    @action(detail=True, methods=["post"])
    def generate_pdf(self, request, pk=None):
        """Generate and return resume PDF."""
        try:
            resume = self.get_object()
            template = request.data.get("template", resume.template)

            # Generate PDF with specified template
            pdf_content = self._generate_pdf(resume, template)

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_GENERATED,
                description=f"Generated PDF for resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            response = HttpResponse(pdf_content, content_type="application/pdf")
            response["Content-Disposition"] = f'inline; filename="{resume.title}.pdf"'
            return response
        except Exception as e:
            logger.error(f"Error generating resume PDF: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to generate resume PDF"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def duplicate(self, request, pk=None):
        """Duplicate a resume."""
        try:
            original_resume = self.get_object()

            # Check resume limit
            resume_count = Resume.objects.filter(user=request.user).count()
            if resume_count >= 5:
                return Response(
                    {"error": "Maximum 5 resumes allowed per user"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create duplicate
            duplicate = Resume.objects.create(
                user=request.user,
                title=f"{original_resume.title} (Copy)",
                description=original_resume.description,
                template=original_resume.template,
                content=original_resume.content,
                status=Resume.ResumeStatus.DRAFT,
                is_default=False,
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_CREATED,
                description=f"Duplicated resume: {duplicate.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(duplicate)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error duplicating resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to duplicate resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: {"templates": "list"}},
    )
    @action(detail=False, methods=["get"])
    def templates(self, request):
        """Get available resume templates."""
        try:
            templates = [
                {
                    "value": "modern",
                    "label": "Modern",
                    "description": "Clean and contemporary design",
                },
                {
                    "value": "classic",
                    "label": "Classic",
                    "description": "Traditional professional layout",
                },
                {
                    "value": "creative",
                    "label": "Creative",
                    "description": "Stylish design for creative professionals",
                },
                {
                    "value": "minimal",
                    "label": "Minimal",
                    "description": "Simple and elegant layout",
                },
                {
                    "value": "executive",
                    "label": "Executive",
                    "description": "Professional design for senior roles",
                },
                {
                    "value": "academic",
                    "label": "Academic",
                    "description": "Formal layout for academic positions",
                },
            ]
            return Response({"templates": templates})
        except Exception as e:
            logger.error(f"Error getting resume templates: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get resume templates"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=False, methods=["get"])
    def default(self, request):
        """Get user's default resume."""
        try:
            default_resume = (
                self.get_queryset().filter(is_default=True).first()
                or self.get_queryset().first()
            )

            if not default_resume:
                return Response(
                    {"error": "No resume found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            serializer = self.get_serializer(default_resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting default resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get default resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def published(self, request):
        """Get published resumes."""
        try:
            user_id = request.query_params.get("user_id", request.user.id)
            try:
                user = User.objects.get(id=user_id)
                if user != request.user and not can_view_user_profile(
                    request.user, user
                ):
                    raise PermissionDenied("Cannot view this user's resumes")
            except User.DoesNotExist:
                return Response(
                    {"error": "User not found"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            published_resumes = Resume.objects.filter(
                user=user, status=Resume.ResumeStatus.PUBLISHED
            )
            serializer = self.get_serializer(published_resumes, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting published resumes: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get published resumes"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def drafts(self, request):
        """Get draft resumes."""
        try:
            draft_resumes = self.get_queryset().filter(status=Resume.ResumeStatus.DRAFT)
            serializer = self.get_serializer(draft_resumes, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting draft resumes: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get draft resumes"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=False, methods=["post"])
    def auto_generate(self, request):
        """Auto-generate resume from profile data."""
        try:
            from ...models import Education, Experience, Project, Skill

            # Get user's profile data
            user = request.user
            experiences = Experience.objects.filter(user=user).order_by("-start_date")
            education = Education.objects.filter(user=user).order_by("-start_date")
            skills = Skill.objects.filter(user=user).order_by("-level")
            projects = Project.objects.filter(user=user).order_by("-start_date")

            # Generate resume content
            content = {
                "experiences": [
                    {
                        "title": exp.title,
                        "company": exp.company,
                        "start_date": (
                            exp.start_date.isoformat() if exp.start_date else None
                        ),
                        "end_date": exp.end_date.isoformat() if exp.end_date else None,
                        "is_current": exp.is_current,
                        "description": exp.description,
                    }
                    for exp in experiences
                ],
                "education": [
                    {
                        "degree": edu.degree,
                        "institution": edu.institution,
                        "start_date": (
                            edu.start_date.isoformat() if edu.start_date else None
                        ),
                        "end_date": edu.end_date.isoformat() if edu.end_date else None,
                        "description": edu.description,
                    }
                    for edu in education
                ],
                "skills": [
                    {
                        "name": skill.name,
                        "level": skill.level,
                        "category": skill.category,
                    }
                    for skill in skills
                ],
                "projects": [
                    {
                        "title": proj.title,
                        "description": proj.description,
                        "start_date": (
                            proj.start_date.isoformat() if proj.start_date else None
                        ),
                        "end_date": (
                            proj.end_date.isoformat() if proj.end_date else None
                        ),
                        "technologies": proj.technologies,
                    }
                    for proj in projects
                ],
            }

            # Create auto-generated resume
            resume = Resume.objects.create(
                user=user,
                title="Auto-Generated Resume",
                description="Resume automatically generated from profile data",
                template="modern",
                content=content,
                status=Resume.ResumeStatus.DRAFT,
                is_default=False,
            )

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_CREATED,
                description=f"Auto-generated resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            logger.error(f"Error auto-generating resume: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to auto-generate resume"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: {"stats": "dict"}},
    )
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Get resume statistics."""
        try:
            queryset = self.get_queryset()
            total_resumes = queryset.count()
            published_count = queryset.filter(
                status=Resume.ResumeStatus.PUBLISHED
            ).count()
            draft_count = queryset.filter(status=Resume.ResumeStatus.DRAFT).count()

            # Get template usage
            template_stats = {}
            templates = [
                "modern",
                "classic",
                "creative",
                "minimal",
                "executive",
                "academic",
            ]
            for template in templates:
                count = queryset.filter(template=template).count()
                template_stats[template] = count

            stats = {
                "total_resumes": total_resumes,
                "published_count": published_count,
                "draft_count": draft_count,
                "template_usage": template_stats,
            }

            return Response({"stats": stats})
        except Exception as e:
            logger.error(f"Error getting resume stats: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get resume statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _generate_pdf(self, resume, template=None):
        """
        Generate PDF content for resume.
        This is a placeholder implementation - integrate with a PDF library like reportlab or weasyprint.
        """
        template = template or resume.template

        # Placeholder PDF content
        pdf_content = (
            b"%PDF-1.4\n1 0 obj\n<<\n/Type /Catalog\n/Pages 2 0 R\n>>\nendobj\n"
        )
        pdf_content += (
            f"Resume: {resume.title}\nUser: {resume.user.get_full_name()}\n".encode()
        )
        pdf_content += b"%%EOF"

        return pdf_content

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def update_content(self, request, pk=None):
        """Update resume content."""
        try:
            resume = self.get_object()
            content = request.data.get("content")

            if not content:
                return Response(
                    {"error": "Content is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            resume.content = content
            resume.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_UPDATED,
                description=f"Updated content for resume: {resume.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error updating resume content: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to update resume content"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Resume"],
        responses={200: ResumeSerializer},
    )
    @action(detail=True, methods=["post"])
    def change_template(self, request, pk=None):
        """Change resume template."""
        try:
            resume = self.get_object()
            template = request.data.get("template")

            if not template:
                return Response(
                    {"error": "Template is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            valid_templates = [
                "modern",
                "classic",
                "creative",
                "minimal",
                "executive",
                "academic",
            ]
            if template not in valid_templates:
                return Response(
                    {
                        "error": f"Invalid template. Choose from: {', '.join(valid_templates)}"
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            resume.template = template
            resume.save()

            # Log activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.RESUME_UPDATED,
                description=f"Changed template for resume: {resume.title} to {template}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = self.get_serializer(resume)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error changing resume template: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to change resume template"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

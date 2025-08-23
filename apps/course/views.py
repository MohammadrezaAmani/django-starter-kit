import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Avg, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from apps.accounts.models import ActivityLog
from apps.accounts.permissions import IsOwnerOrAdmin
from apps.accounts.views.user import UserRateThrottle
from apps.events.views import StandardResultsSetPagination

from .filters import (
    CourseFilter,
    DiscussionFilter,
    FeedbackFilter,
    LessonFilter,
    ProgressFilter,
    QuestionFilter,
    VocabularyFilter,
)
from .models import (
    Assessment,
    Course,
    DiscussionThread,
    Feedback,
    Language,
    Lesson,
    Module,
    Question,
    SpacedRepetition,
    Step,
    UserAchievement,
    UserAnalytics,
    UserAssessmentAttempt,
    UserProgress,
    UserResponse,
    Vocabulary,
)
from .serializers import (
    AssessmentDetailSerializer,
    AssessmentListSerializer,
    AssessmentResultSerializer,
    CourseCreateUpdateSerializer,
    CourseDetailSerializer,
    CourseEnrollmentSerializer,
    CourseListSerializer,
    CourseProgressSerializer,
    CourseStatisticsSerializer,
    DashboardSerializer,
    DialectSerializer,
    DiscussionPostSerializer,
    DiscussionThreadSerializer,
    FeedbackSerializer,
    LanguageSerializer,
    LessonDetailSerializer,
    LessonListSerializer,
    ModuleSerializer,
    QuestionSerializer,
    StepSerializer,
    UserAssessmentAttemptSerializer,
    UserProgressSerializer,
    UserResponseSerializer,
    VocabularySerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class BaseViewSet(viewsets.ModelViewSet):
    """Base ViewSet with common functionality"""

    pagination_class = StandardResultsSetPagination
    throttle_classes = [UserRateThrottle]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    def get_queryset(self):
        """Base queryset with active objects only"""
        return self.queryset.filter(is_active=True)

    def perform_create(self, serializer):
        """Set created_by field"""
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        """Set updated_by field"""
        serializer.save(updated_by=self.request.user)

    def handle_exception(self, exc):
        """Enhanced error handling with logging"""
        logger.error(f"Error in {self.__class__.__name__}: {str(exc)}", exc_info=True)
        return super().handle_exception(exc)


class LanguageViewSet(BaseViewSet):
    """ViewSet for managing languages"""

    queryset = Language.objects.all()
    serializer_class = LanguageSerializer
    search_fields = ["name", "native_name", "code"]
    ordering_fields = ["name", "code", "difficulty_rating", "speakers_count"]
    ordering = ["name"]

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Languages"],
        responses={200: LanguageSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List all available languages"""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing languages: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get languages"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: DialectSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def dialects(self, request, pk=None):
        """Get dialects for a specific language"""
        try:
            language = self.get_object()
            dialects = language.dialects.filter(is_active=True)
            serializer = DialectSerializer(dialects, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting dialects: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get dialects"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Languages"],
        responses={200: CourseListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def courses(self, request, pk=None):
        """Get courses available in a specific language"""
        try:
            language = self.get_object()
            courses = Course.objects.filter(
                target_language=language, is_published=True, is_active=True
            ).select_related("instructor", "target_language")

            # Apply filtering
            level = request.query_params.get("level")
            category = request.query_params.get("category")

            if level:
                courses = courses.filter(level=level)
            if category:
                courses = courses.filter(category=category)

            page = self.paginate_queryset(courses)
            if page is not None:
                serializer = CourseListSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = CourseListSerializer(courses, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting language courses: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get courses"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class CourseViewSet(BaseViewSet):
    """ViewSet for managing courses"""

    queryset = Course.objects.all()
    filterset_class = CourseFilter
    search_fields = ["title", "description", "skills_focused"]
    ordering_fields = [
        "title",
        "created_at",
        "enrollment_count",
        "average_rating",
        "level",
    ]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return CourseListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return CourseCreateUpdateSerializer
        return CourseDetailSerializer

    def get_queryset(self):
        """Filter courses based on user permissions"""
        queryset = super().get_queryset()

        if self.action == "list":
            # Public list shows only published courses
            if not self.request.user.is_staff:
                queryset = queryset.filter(is_published=True)

        return queryset.select_related(
            "target_language", "target_dialect", "base_language", "instructor"
        ).prefetch_related("co_instructors", "prerequisites")

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Courses"],
        responses={200: CourseListSerializer(many=True)},
    )
    def list(self, request, *args, **kwargs):
        """List courses with advanced filtering"""
        try:
            return super().list(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error listing courses: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get courses"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Courses"],
        request=CourseCreateUpdateSerializer,
        responses={201: CourseDetailSerializer},
    )
    def create(self, request, *args, **kwargs):
        """Create a new course"""
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            logger.error(f"Error creating course: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to create course"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Courses"],
        request=CourseEnrollmentSerializer,
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(detail=True, methods=["post"])
    def enroll(self, request, pk=None):
        """Enroll user in a course"""
        try:
            course = self.get_object()
            user = request.user

            # Check if already enrolled
            if UserProgress.objects.filter(user=user, course=course).exists():
                return Response(
                    {"error": "Already enrolled in this course"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check prerequisites
            if course.prerequisites.exists():
                completed_prerequisites = UserProgress.objects.filter(
                    user=user, course__in=course.prerequisites.all(), is_completed=True
                ).count()

                if completed_prerequisites < course.prerequisites.count():
                    return Response(
                        {"error": "Prerequisites not completed"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            with transaction.atomic():
                # Create progress entry
                UserProgress.objects.create(
                    user=user, course=course, first_accessed=timezone.now()
                )

                # Update course enrollment count
                course.enrollment_count = F("enrollment_count") + 1
                course.save(update_fields=["enrollment_count"])

                # Log activity
                ActivityLog.objects.create(
                    user=user,
                    activity_type=ActivityLog.ActivityType.COURSE_ENROLLMENT,
                    description=f"Enrolled in course: {course.title}",
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

            return Response({"message": "Successfully enrolled in course"})

        except Exception as e:
            logger.error(f"Error enrolling in course: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to enroll in course"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Courses"],
        responses={200: CourseProgressSerializer},
    )
    @action(detail=True, methods=["get"])
    def progress(self, request, pk=None):
        """Get user's progress in a course"""
        try:
            course = self.get_object()
            user = request.user

            progress = get_object_or_404(UserProgress, user=user, course=course)

            # Calculate detailed progress
            total_lessons = Lesson.objects.filter(
                module__course=course, is_active=True
            ).count()

            completed_lessons = UserProgress.objects.filter(
                user=user, lesson__module__course=course, is_completed=True
            ).count()

            # Find current lesson
            current_lesson = None
            next_incomplete = (
                UserProgress.objects.filter(
                    user=user, lesson__module__course=course, is_completed=False
                )
                .select_related("lesson")
                .first()
            )

            if next_incomplete:
                current_lesson = next_incomplete.lesson

            progress_data = {
                "course": course,
                "completion_percentage": progress.completion_percentage,
                "current_lesson": current_lesson,
                "total_lessons": total_lessons,
                "completed_lessons": completed_lessons,
                "total_xp_earned": progress.xp_earned,
                "current_streak": progress.current_streak,
                "last_accessed": progress.last_accessed,
            }

            serializer = CourseProgressSerializer(progress_data)
            return Response(serializer.data)

        except UserProgress.DoesNotExist:
            return Response(
                {"error": "Not enrolled in this course"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error getting course progress: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get course progress"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Courses"],
        responses={200: ModuleSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def modules(self, request, pk=None):
        """Get modules for a course"""
        try:
            course = self.get_object()
            modules = course.modules.filter(is_active=True).order_by("order")
            serializer = ModuleSerializer(modules, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting course modules: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get course modules"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Courses"],
        responses={200: CourseStatisticsSerializer},
    )
    @action(detail=True, methods=["get"])
    def statistics(self, request, pk=None):
        """Get course statistics (instructor/admin only)"""
        try:
            course = self.get_object()

            # Check permissions
            if not (
                request.user == course.instructor
                or request.user in course.co_instructors.all()
                or request.user.is_staff
            ):
                raise PermissionDenied("Not authorized to view course statistics")

            stats = {
                "total_enrollments": course.enrollment_count,
                "active_learners": UserProgress.objects.filter(
                    course=course,
                    last_accessed__gte=timezone.now() - timezone.timedelta(days=30),
                ).count(),
                "completion_rate": course.completion_rate,
                "average_rating": course.average_rating,
                "average_completion_time": UserProgress.objects.filter(
                    course=course, is_completed=True
                ).aggregate(avg_time=Avg("total_time_spent_seconds"))["avg_time"]
                or 0,
                "difficulty_distribution": {},
                "engagement_metrics": {},
                "feedback_summary": {},
                "learning_outcomes": {},
            }

            serializer = CourseStatisticsSerializer(stats)
            return Response(serializer.data)

        except PermissionDenied:
            raise
        except Exception as e:
            logger.error(f"Error getting course statistics: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get course statistics"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ModuleViewSet(BaseViewSet):
    """ViewSet for managing course modules"""

    queryset = Module.objects.all()
    serializer_class = ModuleSerializer
    search_fields = ["title", "description"]
    ordering_fields = ["title", "order", "created_at"]
    ordering = ["order"]

    def get_queryset(self):
        """Filter modules based on course access"""
        queryset = super().get_queryset().select_related("course")

        # Filter by course if provided
        course_id = self.request.query_params.get("course")
        if course_id:
            queryset = queryset.filter(course_id=course_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Modules"],
        responses={200: LessonListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def lessons(self, request, pk=None):
        """Get lessons for a module"""
        try:
            module = self.get_object()
            lessons = module.lessons.filter(is_active=True).order_by("order")
            serializer = LessonListSerializer(lessons, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting module lessons: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get module lessons"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class LessonViewSet(BaseViewSet):
    """ViewSet for managing lessons"""

    queryset = Lesson.objects.all()
    filterset_class = LessonFilter
    search_fields = ["title", "description", "content_type"]
    ordering_fields = ["title", "order", "difficulty", "created_at"]
    ordering = ["order"]

    def get_serializer_class(self):
        if self.action == "list":
            return LessonListSerializer
        return LessonDetailSerializer

    def get_queryset(self):
        """Filter lessons based on access permissions"""
        queryset = super().get_queryset().select_related("module__course")

        # Filter by module/course if provided
        module_id = self.request.query_params.get("module")
        course_id = self.request.query_params.get("course")

        if module_id:
            queryset = queryset.filter(module_id=module_id)
        elif course_id:
            queryset = queryset.filter(module__course_id=course_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve", "start", "complete"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Lessons"],
        responses={200: StepSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def steps(self, request, pk=None):
        """Get steps for a lesson"""
        try:
            lesson = self.get_object()
            steps = lesson.steps.filter(is_active=True).order_by("order")
            serializer = StepSerializer(steps, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting lesson steps: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get lesson steps"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Lessons"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start a lesson (create/update progress)"""
        try:
            lesson = self.get_object()
            user = request.user

            # Check if user is enrolled in course
            if not UserProgress.objects.filter(
                user=user, course=lesson.module.course
            ).exists():
                return Response(
                    {"error": "Not enrolled in course"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create or update lesson progress
            progress, created = UserProgress.objects.get_or_create(
                user=user,
                lesson=lesson,
                defaults={
                    "course": lesson.module.course,
                    "module": lesson.module,
                    "first_accessed": timezone.now(),
                },
            )

            if not created:
                progress.last_accessed = timezone.now()
                progress.save(update_fields=["last_accessed"])

            # Log activity
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.LESSON_START,
                description=f"Started lesson: {lesson.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            return Response({"message": "Lesson started successfully"})

        except Exception as e:
            logger.error(f"Error starting lesson: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to start lesson"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Lessons"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        """Mark lesson as completed"""
        try:
            lesson = self.get_object()
            user = request.user

            # Get or create lesson progress
            progress = get_object_or_404(UserProgress, user=user, lesson=lesson)

            if not progress.is_completed:
                with transaction.atomic():
                    progress.is_completed = True
                    progress.completion_percentage = 100
                    progress.completed_at = timezone.now()
                    progress.xp_earned += lesson.completion_xp_reward
                    progress.save()

                    # Update course progress
                    course_progress = UserProgress.objects.get(
                        user=user, course=lesson.module.course
                    )

                    # Recalculate course completion percentage
                    total_lessons = Lesson.objects.filter(
                        module__course=lesson.module.course, is_active=True
                    ).count()

                    completed_lessons = UserProgress.objects.filter(
                        user=user,
                        lesson__module__course=lesson.module.course,
                        is_completed=True,
                    ).count()

                    course_progress.completion_percentage = min(
                        100, int((completed_lessons / total_lessons) * 100)
                    )
                    course_progress.xp_earned += lesson.completion_xp_reward
                    course_progress.save()

                    # Check for course completion
                    if course_progress.completion_percentage == 100:
                        course_progress.is_completed = True
                        course_progress.completed_at = timezone.now()
                        course_progress.save()

                        # Update course completion count
                        lesson.module.course.completion_count = (
                            F("completion_count") + 1
                        )
                        lesson.module.course.save(update_fields=["completion_count"])

                    # Log activity
                    ActivityLog.objects.create(
                        user=user,
                        activity_type=ActivityLog.ActivityType.LESSON_COMPLETION,
                        description=f"Completed lesson: {lesson.title}",
                        ip_address=request.META.get("REMOTE_ADDR"),
                    )

            return Response({"message": "Lesson completed successfully"})

        except UserProgress.DoesNotExist:
            return Response(
                {"error": "Lesson not started"}, status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error completing lesson: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to complete lesson"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StepViewSet(BaseViewSet):
    """ViewSet for managing lesson steps"""

    queryset = Step.objects.all()
    serializer_class = StepSerializer
    search_fields = ["title", "learning_objective", "content_type"]
    ordering_fields = ["order", "created_at"]
    ordering = ["order"]

    def get_queryset(self):
        """Filter steps based on lesson access"""
        queryset = super().get_queryset().select_related("lesson__module__course")

        # Filter by lesson if provided
        lesson_id = self.request.query_params.get("lesson")
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Steps"],
        responses={200: QuestionSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def questions(self, request, pk=None):
        """Get questions for a step"""
        try:
            step = self.get_object()
            questions = step.questions.filter(is_active=True)
            serializer = QuestionSerializer(questions, many=True)
            return Response(serializer.data)
        except Exception as e:
            logger.error(f"Error getting step questions: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get step questions"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VocabularyViewSet(BaseViewSet):
    """ViewSet for managing vocabulary"""

    queryset = Vocabulary.objects.all()
    serializer_class = VocabularySerializer
    filterset_class = VocabularyFilter
    search_fields = ["word", "translation", "definition", "example_sentence"]
    ordering_fields = ["word", "frequency_rating", "difficulty_level", "created_at"]
    ordering = ["word"]

    def get_queryset(self):
        """Filter vocabulary based on language and user progress"""
        queryset = super().get_queryset().select_related("language")

        # Filter by language if provided
        language_id = self.request.query_params.get("language")
        if language_id:
            queryset = queryset.filter(language_id=language_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Vocabulary"],
        responses={200: VocabularySerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def by_frequency(self, request):
        """Get vocabulary sorted by frequency"""
        try:
            language_id = request.query_params.get("language")
            if not language_id:
                return Response(
                    {"error": "Language parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            vocabulary = (
                self.get_queryset()
                .filter(language_id=language_id)
                .order_by("-frequency_rating", "word")
            )

            page = self.paginate_queryset(vocabulary)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = self.get_serializer(vocabulary, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(
                f"Error getting vocabulary by frequency: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get vocabulary"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Vocabulary"],
        responses={200: VocabularySerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def for_review(self, request):
        """Get vocabulary items due for spaced repetition review"""
        try:
            user = request.user
            language_id = request.query_params.get("language")

            # Get vocabulary items due for review
            due_items = SpacedRepetition.objects.filter(
                user=user, is_due=True, content_type__model="vocabulary"
            )

            if language_id:
                due_items = due_items.filter(vocabulary__language_id=language_id)

            vocabulary_ids = due_items.values_list("object_id", flat=True)
            vocabulary = self.get_queryset().filter(id__in=vocabulary_ids)

            serializer = self.get_serializer(vocabulary, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(
                f"Error getting vocabulary for review: {str(e)}", exc_info=True
            )
            return Response(
                {"error": "Failed to get vocabulary for review"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QuestionViewSet(BaseViewSet):
    """ViewSet for managing questions"""

    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    filterset_class = QuestionFilter
    search_fields = ["text", "instruction", "question_type"]
    ordering_fields = ["difficulty", "created_at", "success_rate"]
    ordering = ["created_at"]

    def get_queryset(self):
        """Filter questions based on access permissions"""
        queryset = super().get_queryset().select_related("step__lesson__module__course")

        # Filter by step/lesson if provided
        step_id = self.request.query_params.get("step")
        lesson_id = self.request.query_params.get("lesson")

        if step_id:
            queryset = queryset.filter(step_id=step_id)
        elif lesson_id:
            queryset = queryset.filter(step__lesson_id=lesson_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve", "answer"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Questions"],
        request=UserResponseSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "correct": {"type": "boolean"},
                    "feedback": {"type": "string"},
                },
            }
        },
    )
    @action(detail=True, methods=["post"])
    def answer(self, request, pk=None):
        """Submit answer to a question"""
        try:
            question = self.get_object()
            user = request.user

            # Get response data
            response_data = request.data.get("response_data", {})
            time_taken = request.data.get("time_taken_seconds", 0)
            confidence_level = request.data.get("confidence_level", 0)

            # Check if user can answer this question (enrolled in course)
            if question.step:
                course = question.step.lesson.module.course
                if not UserProgress.objects.filter(user=user, course=course).exists():
                    return Response(
                        {"error": "Not enrolled in course"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Calculate attempt number
            attempt_number = (
                UserResponse.objects.filter(user=user, question=question).count() + 1
            )

            # Create user response
            user_response = UserResponse.objects.create(
                user=user,
                question=question,
                response_data=response_data,
                time_taken_seconds=time_taken,
                attempt_number=attempt_number,
                confidence_level=confidence_level,
            )

            # Auto-grade if enabled
            if question.auto_grading_enabled:
                is_correct = self._evaluate_response(question, response_data)
                user_response.is_correct = is_correct
                user_response.score = question.points if is_correct else 0
                user_response.max_score = question.points

                # Generate feedback
                if is_correct:
                    user_response.feedback = (
                        question.step.feedback_correct if question.step else "Correct!"
                    )
                else:
                    user_response.feedback = (
                        question.step.feedback_incorrect
                        if question.step
                        else "Incorrect. Try again!"
                    )

                user_response.save()

            return Response(
                {
                    "correct": user_response.is_correct,
                    "feedback": user_response.feedback,
                    "score": user_response.score,
                    "max_score": user_response.max_score,
                }
            )

        except Exception as e:
            logger.error(f"Error submitting answer: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to submit answer"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _evaluate_response(self, question, response_data):
        """Evaluate user response based on question type"""
        if question.question_type == "multiple_choice":
            return response_data.get("selected_option") in question.correct_answers
        elif question.question_type == "multi_select":
            selected = set(response_data.get("selected_options", []))
            correct = set(question.correct_answers)
            return selected == correct
        elif question.question_type in ["fill_blank", "short_answer"]:
            user_answer = response_data.get("answer", "").lower().strip()
            return any(
                user_answer == correct.lower().strip()
                for correct in question.correct_answers
            )
        elif question.question_type == "true_false":
            return response_data.get("answer") in question.correct_answers
        else:
            # For complex question types, require manual grading
            return False


class UserProgressViewSet(BaseViewSet):
    """ViewSet for managing user progress"""

    queryset = UserProgress.objects.all()
    serializer_class = UserProgressSerializer
    filterset_class = ProgressFilter
    search_fields = ["notes"]
    ordering_fields = [
        "completion_percentage",
        "last_accessed",
        "xp_earned",
        "created_at",
    ]
    ordering = ["-last_accessed"]

    def get_queryset(self):
        """Filter progress based on user permissions"""
        queryset = (
            super()
            .get_queryset()
            .select_related("user", "course", "module", "lesson", "step")
        )

        # Users can only see their own progress unless admin/instructor
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        # Filter by course/module/lesson if provided
        course_id = self.request.query_params.get("course")
        module_id = self.request.query_params.get("module")
        lesson_id = self.request.query_params.get("lesson")

        if course_id:
            queryset = queryset.filter(course_id=course_id)
        if module_id:
            queryset = queryset.filter(module_id=module_id)
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Progress"],
        responses={200: UserProgressSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    def dashboard(self, request):
        """Get user's learning dashboard data"""
        try:
            user = request.user

            # Get recent progress
            recent_progress = self.get_queryset().filter(
                user=user,
                last_accessed__gte=timezone.now() - timezone.timedelta(days=7),
            )[:10]

            # Get learning path recommendations
            next_lesson = (
                self.get_queryset()
                .filter(user=user, lesson__isnull=False, is_completed=False)
                .select_related("lesson")
                .first()
            )

            # Get review items
            review_items_count = SpacedRepetition.objects.filter(
                user=user, is_due=True
            ).count()

            # Get recent achievements
            achievements_this_week = UserAchievement.objects.filter(
                user=user, unlocked_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).select_related("achievement")

            # Calculate daily goal progress
            today_analytics = UserAnalytics.objects.filter(
                user=user, date=timezone.now().date()
            ).first()

            daily_goal_progress = {
                "minutes_studied": (
                    today_analytics.total_time_spent_minutes if today_analytics else 0
                ),
                "daily_goal": (
                    user.course_settings.daily_goal_minutes
                    if hasattr(user, "course_settings")
                    else 15
                ),
                "percentage": 0,
            }

            if daily_goal_progress["daily_goal"] > 0:
                daily_goal_progress["percentage"] = min(
                    100,
                    (
                        daily_goal_progress["minutes_studied"]
                        / daily_goal_progress["daily_goal"]
                    )
                    * 100,
                )

            dashboard_data = {
                "user_stats": {
                    "total_xp": self.get_queryset().aggregate(Sum("xp_earned"))[
                        "xp_earned__sum"
                    ]
                    or 0,
                    "courses_enrolled": self.get_queryset()
                    .filter(course__isnull=False)
                    .values("course")
                    .distinct()
                    .count(),
                    "lessons_completed": self.get_queryset()
                    .filter(lesson__isnull=False, is_completed=True)
                    .count(),
                    "current_streak": self.get_queryset()
                    .filter(course__isnull=False)
                    .aggregate(avg_streak=Avg("current_streak"))["avg_streak"]
                    or 0,
                },
                "recent_activity": [
                    {
                        "type": "progress",
                        "description": f"Studied {p.lesson.title if p.lesson else p.course.title}",
                        "timestamp": p.last_accessed,
                        "xp_earned": p.xp_earned,
                    }
                    for p in recent_progress
                ],
                "progress_summary": {
                    "active_courses": recent_progress.filter(course__isnull=False)
                    .values("course")
                    .distinct()
                    .count(),
                    "completion_rate": recent_progress.filter(is_completed=True).count()
                    / max(recent_progress.count(), 1)
                    * 100,
                },
                "upcoming_lessons": (
                    [next_lesson.lesson] if next_lesson and next_lesson.lesson else []
                ),
                "review_items_count": review_items_count,
                "achievements_this_week": achievements_this_week,
                "daily_goal_progress": daily_goal_progress,
                "recommendations": [],  # Would be populated by recommendation engine
            }

            serializer = DashboardSerializer(dashboard_data)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting dashboard: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get dashboard"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AssessmentViewSet(BaseViewSet):
    """ViewSet for managing assessments"""

    queryset = Assessment.objects.all()
    search_fields = ["title", "description", "assessment_type"]
    ordering_fields = ["title", "assessment_type", "created_at", "passing_score"]
    ordering = ["-created_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return AssessmentListSerializer
        return AssessmentDetailSerializer

    def get_queryset(self):
        """Filter assessments based on access permissions"""
        queryset = (
            super()
            .get_queryset()
            .select_related("course", "module", "lesson")
            .prefetch_related("questions")
        )

        # Filter by course/module/lesson if provided
        course_id = self.request.query_params.get("course")
        module_id = self.request.query_params.get("module")
        lesson_id = self.request.query_params.get("lesson")

        if course_id:
            queryset = queryset.filter(course_id=course_id)
        if module_id:
            queryset = queryset.filter(module_id=module_id)
        if lesson_id:
            queryset = queryset.filter(lesson_id=lesson_id)

        # Filter by availability
        now = timezone.now()
        if not self.request.user.is_staff:
            queryset = queryset.filter(
                Q(available_from__isnull=True) | Q(available_from__lte=now),
                Q(available_until__isnull=True) | Q(available_until__gte=now),
            )

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve", "start", "submit"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=["Assessments"],
        responses={201: UserAssessmentAttemptSerializer},
    )
    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        """Start an assessment attempt"""
        try:
            assessment = self.get_object()
            user = request.user

            # Check if user is enrolled in course
            if (
                assessment.course
                and not UserProgress.objects.filter(
                    user=user, course=assessment.course
                ).exists()
            ):
                return Response(
                    {"error": "Not enrolled in course"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Check attempt limits
            existing_attempts = UserAssessmentAttempt.objects.filter(
                user=user, assessment=assessment
            ).count()

            if existing_attempts >= assessment.attempts_allowed:
                return Response(
                    {"error": "Maximum attempts exceeded"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Create new attempt
            attempt = UserAssessmentAttempt.objects.create(
                user=user,
                assessment=assessment,
                attempt_number=existing_attempts + 1,
                max_score=assessment.total_points,
            )

            # Log activity
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.ASSESSMENT_START,
                description=f"Started assessment: {assessment.title}",
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            serializer = UserAssessmentAttemptSerializer(attempt)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error starting assessment: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to start assessment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        tags=["Assessments"],
        responses={200: AssessmentResultSerializer},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, pk=None):
        """Submit an assessment attempt"""
        try:
            assessment = self.get_object()
            user = request.user
            attempt_id = request.data.get("attempt_id")

            if not attempt_id:
                return Response(
                    {"error": "Attempt ID is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the attempt
            attempt = get_object_or_404(
                UserAssessmentAttempt,
                id=attempt_id,
                user=user,
                assessment=assessment,
                status="in_progress",
            )

            with transaction.atomic():
                # Mark as submitted
                attempt.submitted_at = timezone.now()
                attempt.status = "submitted"

                # Calculate score and grade
                attempt.calculate_score()

                # Mark as completed
                attempt.completed_at = timezone.now()
                attempt.status = "completed"
                attempt.completion_time_seconds = int(
                    (attempt.completed_at - attempt.started_at).total_seconds()
                )
                attempt.save()

                # Award XP if passed
                if attempt.passed:
                    UserProgress.objects.filter(
                        user=user, course=assessment.course
                    ).update(xp_earned=F("xp_earned") + assessment.xp_reward)

                # Log activity
                ActivityLog.objects.create(
                    user=user,
                    activity_type=ActivityLog.ActivityType.ASSESSMENT_COMPLETION,
                    description=f"Completed assessment: {assessment.title} (Score: {attempt.percentage_score}%)",
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

            # Prepare result data
            result_data = {
                "attempt": attempt,
                "detailed_results": self._calculate_detailed_results(attempt),
                "performance_analysis": self._analyze_performance(attempt),
                "improvement_suggestions": self._get_improvement_suggestions(attempt),
                "next_steps": self._get_next_steps(attempt),
            }

            serializer = AssessmentResultSerializer(result_data)
            return Response(serializer.data)

        except UserAssessmentAttempt.DoesNotExist:
            return Response(
                {"error": "Assessment attempt not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            logger.error(f"Error submitting assessment: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to submit assessment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _calculate_detailed_results(self, attempt):
        """Calculate detailed results breakdown"""
        responses = attempt.responses.all()
        return {
            "total_questions": responses.count(),
            "correct_answers": responses.filter(is_correct=True).count(),
            "partially_correct": responses.filter(is_partially_correct=True).count(),
            "incorrect_answers": responses.filter(is_correct=False).count(),
            "average_time_per_question": responses.aggregate(Avg("time_taken_seconds"))[
                "time_taken_seconds__avg"
            ]
            or 0,
            "question_breakdown": [
                {
                    "question_id": str(r.question.id),
                    "question_text": r.question.text[:100],
                    "correct": r.is_correct,
                    "score": r.score,
                    "time_taken": r.time_taken_seconds,
                }
                for r in responses
            ],
        }

    def _analyze_performance(self, attempt):
        """Analyze performance and identify patterns"""
        responses = attempt.responses.select_related("question").all()

        # Group by question type
        type_performance = {}
        for response in responses:
            q_type = response.question.question_type
            if q_type not in type_performance:
                type_performance[q_type] = {"correct": 0, "total": 0}
            type_performance[q_type]["total"] += 1
            if response.is_correct:
                type_performance[q_type]["correct"] += 1

        # Calculate accuracy by type
        for q_type in type_performance:
            type_performance[q_type]["accuracy"] = (
                type_performance[q_type]["correct"]
                / type_performance[q_type]["total"]
                * 100
            )

        return {
            "overall_accuracy": attempt.percentage_score,
            "time_efficiency": self._calculate_time_efficiency(attempt),
            "question_type_performance": type_performance,
            "difficulty_analysis": self._analyze_difficulty_performance(responses),
            "strengths": self._identify_strengths(type_performance),
            "weaknesses": self._identify_weaknesses(type_performance),
        }

    def _calculate_time_efficiency(self, attempt):
        """Calculate time efficiency metrics"""
        responses = attempt.responses.all()
        if not responses:
            return 0

        total_time = (
            responses.aggregate(Sum("time_taken_seconds"))["time_taken_seconds__sum"]
            or 0
        )
        recommended_time = (
            responses.aggregate(Sum("question__recommended_time_seconds"))[
                "question__recommended_time_seconds__sum"
            ]
            or total_time
        )

        return (
            min(100, (recommended_time / total_time * 100)) if total_time > 0 else 100
        )

    def _analyze_difficulty_performance(self, responses):
        """Analyze performance by question difficulty"""
        difficulty_stats = {}
        for response in responses:
            difficulty = response.question.difficulty
            if difficulty not in difficulty_stats:
                difficulty_stats[difficulty] = {"correct": 0, "total": 0}
            difficulty_stats[difficulty]["total"] += 1
            if response.is_correct:
                difficulty_stats[difficulty]["correct"] += 1

        for difficulty in difficulty_stats:
            difficulty_stats[difficulty]["accuracy"] = (
                difficulty_stats[difficulty]["correct"]
                / difficulty_stats[difficulty]["total"]
                * 100
            )

        return difficulty_stats

    def _identify_strengths(self, type_performance):
        """Identify question types where user performed well"""
        return [
            q_type
            for q_type, stats in type_performance.items()
            if stats["accuracy"] >= 80
        ]

    def _identify_weaknesses(self, type_performance):
        """Identify question types where user needs improvement"""
        return [
            q_type
            for q_type, stats in type_performance.items()
            if stats["accuracy"] < 60
        ]

    def _get_improvement_suggestions(self, attempt):
        """Generate improvement suggestions based on performance"""
        suggestions = []

        if attempt.percentage_score < 70:
            suggestions.append(
                "Review the course material before retaking the assessment"
            )

        if attempt.completion_time_seconds > attempt.assessment.time_limit_minutes * 60:
            suggestions.append(
                "Practice time management - focus on answering questions more quickly"
            )

        # Add more sophisticated suggestions based on performance analysis
        return suggestions

    def _get_next_steps(self, attempt):
        """Suggest next steps based on assessment results"""
        next_steps = []

        if attempt.passed:
            next_steps.append(
                "Congratulations! You may proceed to the next lesson/module"
            )
            if attempt.assessment.certificate_required:
                next_steps.append("You are eligible for course certificate")
        else:
            next_steps.append(
                "Review the areas where you scored low and retake the assessment"
            )
            next_steps.append(
                "Consider reviewing related lessons and practice materials"
            )

        return next_steps


class FeedbackViewSet(BaseViewSet):
    """ViewSet for managing feedback"""

    queryset = Feedback.objects.all()
    serializer_class = FeedbackSerializer
    filterset_class = FeedbackFilter
    search_fields = ["comment", "suggestions", "feedback_type"]
    ordering_fields = ["rating", "created_at", "status", "helpful_votes"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Filter feedback based on user permissions"""
        queryset = super().get_queryset().select_related("user", "resolved_by")

        # Non-staff users can only see their own feedback
        if not self.request.user.is_staff:
            queryset = queryset.filter(user=self.request.user)

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve", "create"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update", "resolve"]:
            permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create feedback with user context"""
        serializer.save(
            user=self.request.user,
            created_by=self.request.user,
            user_progress_context=self._get_user_context(),
        )

    def _get_user_context(self):
        """Get user's current learning context"""
        user = self.request.user
        latest_progress = (
            UserProgress.objects.filter(user=user)
            .select_related("course", "lesson")
            .first()
        )

        if latest_progress:
            return {
                "current_course": (
                    latest_progress.course.title if latest_progress.course else None
                ),
                "current_lesson": (
                    latest_progress.lesson.title if latest_progress.lesson else None
                ),
                "completion_percentage": latest_progress.completion_percentage,
                "total_xp": UserProgress.objects.filter(user=user).aggregate(
                    Sum("xp_earned")
                )["xp_earned__sum"]
                or 0,
            }
        return {}

    @extend_schema(
        tags=["Feedback"],
        responses={
            200: {"type": "object", "properties": {"message": {"type": "string"}}}
        },
    )
    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        """Resolve feedback (admin only)"""
        try:
            feedback = self.get_object()
            resolution_notes = request.data.get("resolution_notes", "")

            feedback.status = "resolved"
            feedback.resolved_by = request.user
            feedback.resolved_at = timezone.now()
            feedback.resolution_notes = resolution_notes
            feedback.save()

            return Response({"message": "Feedback resolved successfully"})

        except Exception as e:
            logger.error(f"Error resolving feedback: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to resolve feedback"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DiscussionViewSet(BaseViewSet):
    """ViewSet for managing discussion threads"""

    queryset = DiscussionThread.objects.all()
    serializer_class = DiscussionThreadSerializer
    filterset_class = DiscussionFilter
    search_fields = ["title", "description"]
    ordering_fields = ["title", "created_at", "last_post_at", "posts_count"]
    ordering = ["-is_pinned", "-last_post_at"]

    def get_queryset(self):
        """Filter discussions based on visibility and permissions"""
        queryset = (
            super()
            .get_queryset()
            .select_related("creator", "last_post_by")
            .prefetch_related("moderators")
        )

        # Filter by visibility
        if not self.request.user.is_staff:
            queryset = queryset.filter(visibility="public")

        # Filter by associated object if provided
        content_type = self.request.query_params.get("content_type")
        object_id = self.request.query_params.get("object_id")

        if content_type and object_id:
            queryset = queryset.filter(
                content_type__model=content_type, object_id=object_id
            )

        return queryset

    def get_permissions(self):
        if self.action in ["list", "retrieve"]:
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["create"]:
            permission_classes = [permissions.IsAuthenticated]
        else:
            permission_classes = [permissions.IsAuthenticated, IsOwnerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_create(self, serializer):
        """Create discussion thread"""
        serializer.save(creator=self.request.user, created_by=self.request.user)

    @extend_schema(
        tags=["Discussions"],
        responses={200: DiscussionPostSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def posts(self, request, pk=None):
        """Get posts for a discussion thread"""
        try:
            thread = self.get_object()
            posts = (
                thread.posts.filter(is_active=True)
                .select_related("author")
                .prefetch_related("replies")
                .order_by("created_at")
            )

            page = self.paginate_queryset(posts)
            if page is not None:
                serializer = DiscussionPostSerializer(page, many=True)
                return self.get_paginated_response(serializer.data)

            serializer = DiscussionPostSerializer(posts, many=True)
            return Response(serializer.data)

        except Exception as e:
            logger.error(f"Error getting discussion posts: {str(e)}", exc_info=True)
            return Response(
                {"error": "Failed to get discussion posts"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# Additional ViewSets would continue here following the same patterns...
# Including: UserSettingsViewSet, AnalyticsViewSet, LeaderboardViewSet, etc.

from datetime import timedelta

import django_filters
from django.db.models import Count, Q
from django.utils import timezone

from .models import (
    Assessment,
    Course,
    DiscussionThread,
    Feedback,
    Lesson,
    Question,
    UserAnalytics,
    UserProgress,
    Vocabulary,
)


class CourseFilter(django_filters.FilterSet):
    """Advanced filtering for courses"""

    # Basic filters
    title = django_filters.CharFilter(lookup_expr="icontains")
    level = django_filters.MultipleChoiceFilter(choices=Course.LEVEL_CHOICES)
    category = django_filters.MultipleChoiceFilter(choices=Course.CATEGORY_CHOICES)
    target_language = django_filters.ModelMultipleChoiceFilter(
        field_name="target_language__code", to_field_name="code", queryset=None
    )

    # Price and access filters
    is_free = django_filters.BooleanFilter()
    is_certified = django_filters.BooleanFilter()
    is_featured = django_filters.BooleanFilter()

    # Rating and popularity filters
    min_rating = django_filters.NumberFilter(
        field_name="average_rating", lookup_expr="gte"
    )
    max_rating = django_filters.NumberFilter(
        field_name="average_rating", lookup_expr="lte"
    )
    min_enrollments = django_filters.NumberFilter(
        field_name="enrollment_count", lookup_expr="gte"
    )

    # Duration filters
    max_duration_hours = django_filters.NumberFilter(
        field_name="estimated_duration_hours", lookup_expr="lte"
    )
    min_duration_hours = django_filters.NumberFilter(
        field_name="estimated_duration_hours", lookup_expr="gte"
    )

    # Difficulty filters
    max_difficulty = django_filters.NumberFilter(
        field_name="difficulty_score", lookup_expr="lte"
    )
    min_difficulty = django_filters.NumberFilter(
        field_name="difficulty_score", lookup_expr="gte"
    )

    # Skills filter
    skills_focused = django_filters.CharFilter(method="filter_by_skills")

    # Instructor filter
    instructor = django_filters.CharFilter(
        field_name="instructor__username", lookup_expr="iexact"
    )

    # Date filters
    published_after = django_filters.DateTimeFilter(
        field_name="published_at", lookup_expr="gte"
    )
    published_before = django_filters.DateTimeFilter(
        field_name="published_at", lookup_expr="lte"
    )
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )

    # Advanced filters
    has_prerequisites = django_filters.BooleanFilter(method="filter_has_prerequisites")
    completion_rate_min = django_filters.NumberFilter(
        method="filter_completion_rate_min"
    )

    class Meta:
        model = Course
        fields = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically set language queryset
        from .models import Language

        self.filters["target_language"].queryset = Language.objects.filter(
            is_active=True
        )

    def filter_by_skills(self, queryset, name, value):
        """Filter by skills focused"""
        skills = [skill.strip() for skill in value.split(",") if skill.strip()]
        for skill in skills:
            queryset = queryset.filter(skills_focused__icontains=skill)
        return queryset

    def filter_has_prerequisites(self, queryset, name, value):
        """Filter courses that have or don't have prerequisites"""
        if value:
            return queryset.filter(prerequisites__isnull=False).distinct()
        else:
            return queryset.filter(prerequisites__isnull=True)

    def filter_completion_rate_min(self, queryset, name, value):
        """Filter by minimum completion rate"""
        return queryset.annotate(
            calculated_completion_rate=Count(
                "user_progress", filter=Q(user_progress__is_completed=True)
            )
            * 100.0
            / Count("user_progress")
        ).filter(calculated_completion_rate__gte=value)


class LessonFilter(django_filters.FilterSet):
    """Filtering for lessons"""

    title = django_filters.CharFilter(lookup_expr="icontains")
    content_type = django_filters.MultipleChoiceFilter(
        choices=Lesson.CONTENT_TYPE_CHOICES
    )
    difficulty = django_filters.RangeFilter()
    min_difficulty = django_filters.NumberFilter(
        field_name="difficulty", lookup_expr="gte"
    )
    max_difficulty = django_filters.NumberFilter(
        field_name="difficulty", lookup_expr="lte"
    )

    # Duration filters
    max_time = django_filters.NumberFilter(
        field_name="estimated_time_minutes", lookup_expr="lte"
    )
    min_time = django_filters.NumberFilter(
        field_name="estimated_time_minutes", lookup_expr="gte"
    )

    # XP filters
    min_xp_reward = django_filters.NumberFilter(
        field_name="completion_xp_reward", lookup_expr="gte"
    )
    min_xp_required = django_filters.NumberFilter(
        field_name="unlock_xp_required", lookup_expr="gte"
    )

    # Course and module filters
    course = django_filters.UUIDFilter(field_name="module__course__id")
    module = django_filters.UUIDFilter(field_name="module__id")

    # AI features
    has_adaptive_content = django_filters.BooleanFilter(field_name="adaptive_content")
    has_ai_difficulty = django_filters.BooleanFilter(
        field_name="ai_difficulty_adjustment"
    )

    class Meta:
        model = Lesson
        fields = []


class VocabularyFilter(django_filters.FilterSet):
    """Filtering for vocabulary"""

    word = django_filters.CharFilter(lookup_expr="icontains")
    language = django_filters.UUIDFilter(field_name="language__id")
    language_code = django_filters.CharFilter(field_name="language__code")
    part_of_speech = django_filters.MultipleChoiceFilter(
        choices=Vocabulary.PART_OF_SPEECH_CHOICES
    )

    # Difficulty and frequency
    difficulty_level = django_filters.RangeFilter()
    min_difficulty = django_filters.NumberFilter(
        field_name="difficulty_level", lookup_expr="gte"
    )
    max_difficulty = django_filters.NumberFilter(
        field_name="difficulty_level", lookup_expr="lte"
    )
    frequency_rating = django_filters.RangeFilter()
    min_frequency = django_filters.NumberFilter(
        field_name="frequency_rating", lookup_expr="gte"
    )

    # Content filters
    has_audio = django_filters.BooleanFilter(method="filter_has_audio")
    has_image = django_filters.BooleanFilter(method="filter_has_image")
    has_examples = django_filters.BooleanFilter(method="filter_has_examples")

    # AI features
    ai_generated_examples = django_filters.BooleanFilter()

    # Context categories
    context_category = django_filters.CharFilter(method="filter_context_category")

    # Lesson association
    lesson = django_filters.UUIDFilter(field_name="lessons__id")
    course = django_filters.UUIDFilter(field_name="lessons__module__course__id")

    class Meta:
        model = Vocabulary
        fields = []

    def filter_has_audio(self, queryset, name, value):
        if value:
            return queryset.exclude(audio_url="")
        else:
            return queryset.filter(audio_url="")

    def filter_has_image(self, queryset, name, value):
        if value:
            return queryset.exclude(image_url="")
        else:
            return queryset.filter(image_url="")

    def filter_has_examples(self, queryset, name, value):
        if value:
            return queryset.exclude(example_sentence="")
        else:
            return queryset.filter(example_sentence="")

    def filter_context_category(self, queryset, name, value):
        return queryset.filter(context_categories__icontains=value)


class QuestionFilter(django_filters.FilterSet):
    """Filtering for questions"""

    question_type = django_filters.MultipleChoiceFilter(choices=Question.QUESTION_TYPES)
    difficulty = django_filters.RangeFilter()
    min_difficulty = django_filters.NumberFilter(
        field_name="difficulty", lookup_expr="gte"
    )
    max_difficulty = django_filters.NumberFilter(
        field_name="difficulty", lookup_expr="lte"
    )

    # Points and timing
    min_points = django_filters.NumberFilter(field_name="points", lookup_expr="gte")
    max_points = django_filters.NumberFilter(field_name="points", lookup_expr="lte")
    has_time_limit = django_filters.BooleanFilter(method="filter_has_time_limit")

    # Content features
    has_media = django_filters.BooleanFilter(method="filter_has_media")
    has_image = django_filters.BooleanFilter(method="filter_has_image")
    has_hints = django_filters.BooleanFilter(method="filter_has_hints")

    # AI features
    ai_generated = django_filters.BooleanFilter()
    auto_grading_enabled = django_filters.BooleanFilter()
    ai_evaluation_enabled = django_filters.BooleanFilter(
        field_name="ai_evaluation_criteria", lookup_expr="isnull", exclude=True
    )

    # Performance metrics
    min_success_rate = django_filters.NumberFilter(
        field_name="success_rate", lookup_expr="gte"
    )
    max_success_rate = django_filters.NumberFilter(
        field_name="success_rate", lookup_expr="lte"
    )
    min_attempts = django_filters.NumberFilter(
        field_name="attempt_count", lookup_expr="gte"
    )

    # Skills and focus
    skill_focus = django_filters.CharFilter(method="filter_skill_focus")
    cognitive_load = django_filters.RangeFilter()

    # Related objects
    step = django_filters.UUIDFilter(field_name="step__id")
    lesson = django_filters.UUIDFilter(field_name="step__lesson__id")
    course = django_filters.UUIDFilter(field_name="step__lesson__module__course__id")

    class Meta:
        model = Question
        fields = []

    def filter_has_time_limit(self, queryset, name, value):
        if value:
            return queryset.filter(time_limit_seconds__gt=0)
        else:
            return queryset.filter(time_limit_seconds=0)

    def filter_has_media(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(media_url__isnull=False) | Q(media_file__isnull=False)
            ).exclude(Q(media_url="") & Q(media_file=""))
        else:
            return queryset.filter(
                Q(media_url__isnull=True) | Q(media_url="")
            ) & queryset.filter(Q(media_file__isnull=True) | Q(media_file=""))

    def filter_has_image(self, queryset, name, value):
        if value:
            return queryset.exclude(image__isnull=True).exclude(image="")
        else:
            return queryset.filter(Q(image__isnull=True) | Q(image=""))

    def filter_has_hints(self, queryset, name, value):
        if value:
            return queryset.exclude(hints=[])
        else:
            return queryset.filter(hints=[])

    def filter_skill_focus(self, queryset, name, value):
        skills = [skill.strip() for skill in value.split(",") if skill.strip()]
        for skill in skills:
            queryset = queryset.filter(skill_focus__icontains=skill)
        return queryset


class ProgressFilter(django_filters.FilterSet):
    """Filtering for user progress"""

    user = django_filters.UUIDFilter(field_name="user__id")
    course = django_filters.UUIDFilter(field_name="course__id")
    module = django_filters.UUIDFilter(field_name="module__id")
    lesson = django_filters.UUIDFilter(field_name="lesson__id")

    # Completion filters
    is_completed = django_filters.BooleanFilter()
    min_completion = django_filters.NumberFilter(
        field_name="completion_percentage", lookup_expr="gte"
    )
    max_completion = django_filters.NumberFilter(
        field_name="completion_percentage", lookup_expr="lte"
    )

    # Date filters
    completed_after = django_filters.DateTimeFilter(
        field_name="completed_at", lookup_expr="gte"
    )
    completed_before = django_filters.DateTimeFilter(
        field_name="completed_at", lookup_expr="lte"
    )
    accessed_after = django_filters.DateTimeFilter(
        field_name="last_accessed", lookup_expr="gte"
    )
    accessed_before = django_filters.DateTimeFilter(
        field_name="last_accessed", lookup_expr="lte"
    )

    # Performance filters
    min_xp = django_filters.NumberFilter(field_name="xp_earned", lookup_expr="gte")
    max_xp = django_filters.NumberFilter(field_name="xp_earned", lookup_expr="lte")
    min_average_score = django_filters.NumberFilter(
        field_name="average_score", lookup_expr="gte"
    )
    min_streak = django_filters.NumberFilter(
        field_name="current_streak", lookup_expr="gte"
    )

    # Time spent filters
    min_time_spent = django_filters.NumberFilter(
        field_name="total_time_spent_seconds", lookup_expr="gte"
    )
    max_time_spent = django_filters.NumberFilter(
        field_name="total_time_spent_seconds", lookup_expr="lte"
    )

    # Engagement filters
    min_attempts = django_filters.NumberFilter(
        field_name="attempts_count", lookup_expr="gte"
    )
    bookmarked = django_filters.BooleanFilter()
    has_notes = django_filters.BooleanFilter(method="filter_has_notes")

    # Active learners (accessed recently)
    is_active_learner = django_filters.BooleanFilter(method="filter_active_learner")

    class Meta:
        model = UserProgress
        fields = []

    def filter_has_notes(self, queryset, name, value):
        if value:
            return queryset.exclude(notes="")
        else:
            return queryset.filter(notes="")

    def filter_active_learner(self, queryset, name, value):
        if value:
            cutoff_date = timezone.now() - timedelta(days=7)
            return queryset.filter(last_accessed__gte=cutoff_date)
        else:
            cutoff_date = timezone.now() - timedelta(days=7)
            return queryset.filter(last_accessed__lt=cutoff_date)


class FeedbackFilter(django_filters.FilterSet):
    """Filtering for feedback"""

    feedback_type = django_filters.MultipleChoiceFilter(choices=Feedback.FEEDBACK_TYPES)
    rating = django_filters.RangeFilter()
    min_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="gte")
    max_rating = django_filters.NumberFilter(field_name="rating", lookup_expr="lte")

    # Status filters
    status = django_filters.MultipleChoiceFilter(choices=Feedback.STATUS_CHOICES)
    severity = django_filters.ChoiceFilter(
        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")]
    )

    # User filters
    user = django_filters.UUIDFilter(field_name="user__id")
    resolved_by = django_filters.UUIDFilter(field_name="resolved_by__id")

    # Date filters
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )
    resolved_after = django_filters.DateTimeFilter(
        field_name="resolved_at", lookup_expr="gte"
    )
    resolved_before = django_filters.DateTimeFilter(
        field_name="resolved_at", lookup_expr="lte"
    )

    # Content filters
    has_comment = django_filters.BooleanFilter(method="filter_has_comment")
    has_suggestions = django_filters.BooleanFilter(method="filter_has_suggestions")

    # Community interaction
    is_helpful = django_filters.BooleanFilter()
    min_helpful_votes = django_filters.NumberFilter(
        field_name="helpful_votes", lookup_expr="gte"
    )
    is_moderated = django_filters.BooleanFilter()

    # Categories
    category = django_filters.CharFilter(method="filter_category")

    class Meta:
        model = Feedback
        fields = []

    def filter_has_comment(self, queryset, name, value):
        if value:
            return queryset.exclude(comment="")
        else:
            return queryset.filter(comment="")

    def filter_has_suggestions(self, queryset, name, value):
        if value:
            return queryset.exclude(suggestions="")
        else:
            return queryset.filter(suggestions="")

    def filter_category(self, queryset, name, value):
        return queryset.filter(categories__icontains=value)


class DiscussionFilter(django_filters.FilterSet):
    """Filtering for discussion threads"""

    title = django_filters.CharFilter(lookup_expr="icontains")
    thread_type = django_filters.MultipleChoiceFilter(
        choices=DiscussionThread.THREAD_TYPES
    )
    visibility = django_filters.ChoiceFilter(
        choices=[
            ("public", "Public"),
            ("private", "Private"),
            ("restricted", "Restricted"),
        ]
    )

    # Creator and moderation
    creator = django_filters.UUIDFilter(field_name="creator__id")
    is_pinned = django_filters.BooleanFilter()
    is_locked = django_filters.BooleanFilter()
    is_archived = django_filters.BooleanFilter()
    is_moderated = django_filters.BooleanFilter()

    # Activity filters
    min_posts = django_filters.NumberFilter(field_name="posts_count", lookup_expr="gte")
    max_posts = django_filters.NumberFilter(field_name="posts_count", lookup_expr="lte")
    min_views = django_filters.NumberFilter(field_name="views_count", lookup_expr="gte")
    min_participants = django_filters.NumberFilter(
        field_name="participants_count", lookup_expr="gte"
    )

    # Date filters
    created_after = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="gte"
    )
    created_before = django_filters.DateTimeFilter(
        field_name="created_at", lookup_expr="lte"
    )
    last_post_after = django_filters.DateTimeFilter(
        field_name="last_post_at", lookup_expr="gte"
    )
    last_post_before = django_filters.DateTimeFilter(
        field_name="last_post_at", lookup_expr="lte"
    )

    # Associated object filters
    content_type = django_filters.CharFilter(field_name="content_type__model")
    object_id = django_filters.UUIDFilter()

    # Activity level
    is_active = django_filters.BooleanFilter(method="filter_active_threads")
    has_recent_activity = django_filters.BooleanFilter(method="filter_recent_activity")

    class Meta:
        model = DiscussionThread
        fields = []

    def filter_active_threads(self, queryset, name, value):
        if value:
            return queryset.filter(posts_count__gt=0)
        else:
            return queryset.filter(posts_count=0)

    def filter_recent_activity(self, queryset, name, value):
        cutoff_date = timezone.now() - timedelta(days=7)
        if value:
            return queryset.filter(last_post_at__gte=cutoff_date)
        else:
            return queryset.filter(
                Q(last_post_at__lt=cutoff_date) | Q(last_post_at__isnull=True)
            )


class AnalyticsFilter(django_filters.FilterSet):
    """Filtering for user analytics"""

    user = django_filters.UUIDFilter(field_name="user__id")
    course = django_filters.UUIDFilter(field_name="course__id")
    date = django_filters.DateFilter()
    date_range = django_filters.DateFromToRangeFilter(field_name="date")

    # Time filters
    min_time_spent = django_filters.NumberFilter(
        field_name="total_time_spent_minutes", lookup_expr="gte"
    )
    max_time_spent = django_filters.NumberFilter(
        field_name="total_time_spent_minutes", lookup_expr="lte"
    )

    # Performance filters
    min_xp_gained = django_filters.NumberFilter(
        field_name="xp_gained", lookup_expr="gte"
    )
    min_accuracy = django_filters.NumberFilter(
        field_name="accuracy_percentage", lookup_expr="gte"
    )
    max_accuracy = django_filters.NumberFilter(
        field_name="accuracy_percentage", lookup_expr="lte"
    )

    # Activity filters
    min_lessons_completed = django_filters.NumberFilter(
        field_name="lessons_completed", lookup_expr="gte"
    )
    min_questions_answered = django_filters.NumberFilter(
        field_name="questions_answered", lookup_expr="gte"
    )
    streak_maintained = django_filters.BooleanFilter()

    # Device and context
    device_type = django_filters.CharFilter(field_name="primary_device_type")
    has_social_activity = django_filters.BooleanFilter(
        method="filter_has_social_activity"
    )

    # Engagement metrics
    min_login_count = django_filters.NumberFilter(
        field_name="login_count", lookup_expr="gte"
    )
    min_session_count = django_filters.NumberFilter(
        field_name="session_count", lookup_expr="gte"
    )

    class Meta:
        model = UserAnalytics
        fields = []

    def filter_has_social_activity(self, queryset, name, value):
        if value:
            return queryset.filter(
                Q(discussions_participated__gt=0)
                | Q(feedback_given__gt=0)
                | Q(help_requests__gt=0)
            )
        else:
            return queryset.filter(
                discussions_participated=0, feedback_given=0, help_requests=0
            )


class AssessmentFilter(django_filters.FilterSet):
    """Filtering for assessments"""

    title = django_filters.CharFilter(lookup_expr="icontains")
    assessment_type = django_filters.MultipleChoiceFilter(
        choices=Assessment.ASSESSMENT_TYPES
    )

    # Related objects
    course = django_filters.UUIDFilter(field_name="course__id")
    module = django_filters.UUIDFilter(field_name="module__id")
    lesson = django_filters.UUIDFilter(field_name="lesson__id")

    # Difficulty and scoring
    min_passing_score = django_filters.NumberFilter(
        field_name="passing_score", lookup_expr="gte"
    )
    max_passing_score = django_filters.NumberFilter(
        field_name="passing_score", lookup_expr="lte"
    )
    min_total_points = django_filters.NumberFilter(
        field_name="total_points", lookup_expr="gte"
    )

    # Timing
    has_time_limit = django_filters.BooleanFilter(method="filter_has_time_limit")
    max_time_limit = django_filters.NumberFilter(
        field_name="time_limit_minutes", lookup_expr="lte"
    )

    # Behavior
    is_adaptive = django_filters.BooleanFilter()
    randomize_questions = django_filters.BooleanFilter()
    is_proctored = django_filters.BooleanFilter()

    # Availability
    available_now = django_filters.BooleanFilter(method="filter_available_now")
    available_from = django_filters.DateTimeFilter(
        field_name="available_from", lookup_expr="gte"
    )
    available_until = django_filters.DateTimeFilter(
        field_name="available_until", lookup_expr="lte"
    )

    # Performance metrics
    min_attempts = django_filters.NumberFilter(
        field_name="attempt_count", lookup_expr="gte"
    )
    min_average_score = django_filters.NumberFilter(
        field_name="average_score", lookup_expr="gte"
    )
    min_completion_rate = django_filters.NumberFilter(
        field_name="completion_rate", lookup_expr="gte"
    )

    # Features
    certificate_required = django_filters.BooleanFilter()
    min_xp_reward = django_filters.NumberFilter(
        field_name="xp_reward", lookup_expr="gte"
    )

    class Meta:
        model = Assessment
        fields = []

    def filter_has_time_limit(self, queryset, name, value):
        if value:
            return queryset.filter(time_limit_minutes__gt=0)
        else:
            return queryset.filter(time_limit_minutes=0)

    def filter_available_now(self, queryset, name, value):
        now = timezone.now()
        if value:
            return queryset.filter(
                Q(available_from__isnull=True) | Q(available_from__lte=now),
                Q(available_until__isnull=True) | Q(available_until__gte=now),
            )
        else:
            return queryset.filter(
                Q(available_from__gt=now) | Q(available_until__lt=now)
            )

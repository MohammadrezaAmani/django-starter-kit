from django.contrib import admin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from .models import (
    Achievement,
    Assessment,
    AssessmentQuestion,
    Certificate,
    Course,
    Dialect,
    DiscussionPost,
    DiscussionThread,
    Feedback,
    GrammarRule,
    Language,
    LeaderboardEntry,
    Lesson,
    Module,
    Question,
    Recommendation,
    SpacedRepetition,
    Step,
    Translation,
    UserAchievement,
    UserAnalytics,
    UserAssessmentAttempt,
    UserProgress,
    UserResponse,
    UserSettings,
    Vocabulary,
)


# Inline classes
class DialectInline(admin.TabularInline):
    model = Dialect
    extra = 1
    fields = ("name", "region", "speakers_count", "is_active")


class ModuleInline(admin.StackedInline):
    model = Module
    extra = 0
    fields = ("title", "order", "is_mandatory", "completion_xp_reward", "is_active")
    readonly_fields = ("created_at", "updated_at")
    show_change_link = True


class LessonInline(admin.TabularInline):
    model = Lesson
    extra = 0
    fields = (
        "title",
        "order",
        "content_type",
        "difficulty",
        "completion_xp_reward",
        "is_active",
    )
    readonly_fields = ("created_at",)
    show_change_link = True


class StepInline(admin.StackedInline):
    model = Step
    extra = 0
    fields = (
        "title",
        "order",
        "content_type",
        "step_type",
        "required_for_completion",
        "is_active",
    )
    readonly_fields = ("created_at",)
    show_change_link = True


class QuestionInline(admin.TabularInline):
    model = Question
    extra = 0
    fields = ("text", "question_type", "difficulty", "points", "auto_grading_enabled")
    readonly_fields = ("success_rate", "attempt_count")


class AssessmentQuestionInline(admin.TabularInline):
    model = AssessmentQuestion
    extra = 0
    fields = ("question", "order", "points", "is_mandatory", "weight")


class TranslationInline(GenericTabularInline):
    model = Translation
    extra = 0
    fields = (
        "language",
        "translated_title",
        "translated_text",
        "is_ai_translated",
        "is_reviewed",
    )


class UserResponseInline(admin.TabularInline):
    model = UserResponse
    extra = 0
    fields = ("user", "is_correct", "score", "time_taken_seconds", "attempt_number")
    readonly_fields = ("created_at", "is_correct", "score")


# Main admin classes
@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "code",
        "native_name",
        "flag_emoji",
        "difficulty_rating",
        "speakers_count",
        "course_count_display",
        "is_active",
    )
    list_filter = ("difficulty_rating", "is_rtl", "is_active", "script")
    search_fields = ("name", "code", "native_name")
    ordering = ("name",)
    inlines = [DialectInline, TranslationInline]
    readonly_fields = ("created_at", "updated_at", "learning_resources_count")

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("name", "code", "native_name", "flag_emoji")},
        ),
        (
            _("Language Properties"),
            {"fields": ("is_rtl", "script", "difficulty_rating", "speakers_count")},
        ),
        (
            _("Statistics"),
            {"fields": ("learning_resources_count",), "classes": ("collapse",)},
        ),
        (_("Status"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def course_count_display(self, obj):
        return obj.course_count

    course_count_display.short_description = "Courses"

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("target_courses")


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "target_language",
        "level",
        "category",
        "instructor_display",
        "enrollment_count",
        "average_rating",
        "is_published",
        "is_featured",
    )
    list_filter = (
        "level",
        "category",
        "is_published",
        "is_featured",
        "is_free",
        "is_certified",
        "target_language",
        "created_at",
    )
    search_fields = (
        "title",
        "description",
        "instructor__username",
        "instructor__email",
    )
    ordering = ("-created_at",)
    filter_horizontal = ("prerequisites", "co_instructors")
    inlines = [ModuleInline, TranslationInline]
    readonly_fields = (
        "slug",
        "enrollment_count",
        "completion_count",
        "average_rating",
        "total_ratings",
        "completion_rate",
        "modules_count",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("title", "slug", "description", "short_description")},
        ),
        (
            _("Language & Level"),
            {
                "fields": (
                    "target_language",
                    "target_dialect",
                    "base_language",
                    "level",
                    "category",
                )
            },
        ),
        (
            _("Course Structure"),
            {
                "fields": (
                    "estimated_duration_hours",
                    "prerequisites",
                    "skills_focused",
                    "learning_objectives",
                )
            },
        ),
        (_("Instructors"), {"fields": ("instructor", "co_instructors")}),
        (
            _("Pricing & Certification"),
            {"fields": ("is_free", "course_fee", "is_certified", "certification_fee")},
        ),
        (_("Media"), {"fields": ("thumbnail", "banner_image", "intro_video_url")}),
        (_("Publishing"), {"fields": ("is_published", "is_featured", "published_at")}),
        (
            _("AI & Personalization"),
            {
                "fields": ("difficulty_score", "ai_generated_content_percentage"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": (
                    "enrollment_count",
                    "completion_count",
                    "average_rating",
                    "total_ratings",
                    "completion_rate",
                    "modules_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def instructor_display(self, obj):
        if obj.instructor:
            return format_html(
                '<a href="{}">{}</a>',
                reverse("admin:accounts_user_change", args=[obj.instructor.pk]),
                obj.instructor.get_full_name() or obj.instructor.username,
            )
        return "-"

    instructor_display.short_description = "Instructor"

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("target_language", "instructor")
            .prefetch_related("modules")
        )

    actions = [
        "publish_courses",
        "unpublish_courses",
        "feature_courses",
        "unfeature_courses",
    ]

    def publish_courses(self, request, queryset):
        updated = queryset.update(is_published=True, published_at=timezone.now())
        self.message_user(request, f"{updated} courses were published.")

    publish_courses.short_description = "Publish selected courses"

    def unpublish_courses(self, request, queryset):
        updated = queryset.update(is_published=False)
        self.message_user(request, f"{updated} courses were unpublished.")

    unpublish_courses.short_description = "Unpublish selected courses"


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "course",
        "order",
        "lessons_count_display",
        "is_mandatory",
        "completion_xp_reward",
        "is_active",
    )
    list_filter = ("is_mandatory", "is_active", "course__target_language", "created_at")
    search_fields = ("title", "description", "course__title")
    ordering = ("course", "order")
    inlines = [LessonInline, TranslationInline]
    readonly_fields = ("slug", "lessons_count", "created_at", "updated_at")

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("course", "title", "slug", "order", "description")},
        ),
        (
            _("Learning Objectives"),
            {"fields": ("objectives", "estimated_time_minutes")},
        ),
        (
            _("Requirements & Rewards"),
            {
                "fields": (
                    "prerequisites",
                    "is_mandatory",
                    "unlock_xp_required",
                    "completion_xp_reward",
                )
            },
        ),
        (_("Appearance"), {"fields": ("icon_name",)}),
        (_("Statistics"), {"fields": ("lessons_count",), "classes": ("collapse",)}),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def lessons_count_display(self, obj):
        return obj.lessons_count

    lessons_count_display.short_description = "Lessons"


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "module",
        "order",
        "content_type",
        "difficulty",
        "steps_count_display",
        "completion_xp_reward",
        "is_active",
    )
    list_filter = (
        "content_type",
        "difficulty",
        "ai_difficulty_adjustment",
        "adaptive_content",
        "is_active",
        "created_at",
    )
    search_fields = ("title", "description", "module__title", "module__course__title")
    ordering = ("module", "order")
    inlines = [StepInline, TranslationInline]
    readonly_fields = ("slug", "steps_count", "created_at", "updated_at")
    filter_horizontal = ("prerequisite_lessons",)

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("module", "title", "slug", "order", "content_type")},
        ),
        (
            _("Content"),
            {
                "fields": (
                    "description",
                    "learning_objectives",
                    "estimated_time_minutes",
                )
            },
        ),
        (
            _("Difficulty & Prerequisites"),
            {"fields": ("difficulty", "prerequisite_lessons")},
        ),
        (
            _("Rewards & Requirements"),
            {"fields": ("unlock_xp_required", "completion_xp_reward")},
        ),
        (_("Media"), {"fields": ("thumbnail", "intro_audio_url")}),
        (
            _("AI Features"),
            {
                "fields": ("ai_difficulty_adjustment", "adaptive_content"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Associated Content"),
            {"fields": ("vocabulary", "grammar_rules"), "classes": ("collapse",)},
        ),
        (_("Statistics"), {"fields": ("steps_count",), "classes": ("collapse",)}),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def steps_count_display(self, obj):
        return obj.steps_count

    steps_count_display.short_description = "Steps"


@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "lesson",
        "order",
        "content_type",
        "step_type",
        "is_interactive",
        "required_for_completion",
        "is_active",
    )
    list_filter = (
        "content_type",
        "step_type",
        "is_interactive",
        "required_for_completion",
        "ai_generated",
        "ai_evaluation_enabled",
        "is_active",
    )
    search_fields = ("title", "learning_objective", "lesson__title")
    ordering = ("lesson", "order")
    inlines = [QuestionInline, TranslationInline]
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("lesson", "title", "order", "content_type", "step_type")},
        ),
        (
            _("Content"),
            {
                "fields": (
                    "data",
                    "learning_objective",
                    "media_file",
                    "external_url",
                    "duration_seconds",
                )
            },
        ),
        (_("Interaction"), {"fields": ("is_interactive", "required_for_completion")}),
        (
            _("Feedback"),
            {
                "fields": (
                    "hints",
                    "feedback_correct",
                    "feedback_incorrect",
                    "feedback_partial",
                )
            },
        ),
        (
            _("Completion Requirements"),
            {
                "fields": (
                    "required_completion_percentage",
                    "max_attempts",
                    "time_limit_seconds",
                )
            },
        ),
        (
            _("Adaptive Learning"),
            {
                "fields": ("branching_rules", "difficulty_adjustment_rules"),
                "classes": ("collapse",),
            },
        ),
        (
            _("AI Features"),
            {
                "fields": ("ai_generated", "ai_evaluation_enabled"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Rewards"),
            {
                "fields": ("base_xp_reward", "bonus_xp_conditions"),
                "classes": ("collapse",),
            },
        ),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Vocabulary)
class VocabularyAdmin(admin.ModelAdmin):
    list_display = (
        "word",
        "language",
        "part_of_speech",
        "frequency_rating",
        "difficulty_level",
        "has_audio",
        "is_active",
    )
    list_filter = (
        "language",
        "part_of_speech",
        "difficulty_level",
        "frequency_rating",
        "ai_generated_examples",
        "is_active",
    )
    search_fields = ("word", "translation", "definition", "example_sentence")
    ordering = ("language", "word")
    filter_horizontal = ("lessons", "synonyms", "antonyms", "related_words")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("word", "language", "phonetic_transcription")},
        ),
        (
            _("Translations & Definition"),
            {"fields": ("translation", "translations", "definition")},
        ),
        (_("Grammar"), {"fields": ("part_of_speech",)}),
        (_("Examples"), {"fields": ("example_sentence", "example_sentences")}),
        (_("Media"), {"fields": ("audio_url", "image_url", "pronunciation_tips")}),
        (
            _("Metadata"),
            {
                "fields": (
                    "frequency_rating",
                    "difficulty_level",
                    "usage_notes",
                    "etymology",
                )
            },
        ),
        (
            _("Relationships"),
            {
                "fields": ("lessons", "synonyms", "antonyms", "related_words"),
                "classes": ("collapse",),
            },
        ),
        (
            _("AI Features"),
            {
                "fields": ("ai_generated_examples", "context_categories"),
                "classes": ("collapse",),
            },
        ),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_audio(self, obj):
        return bool(obj.audio_url)

    has_audio.boolean = True
    has_audio.short_description = "Audio"


@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = (
        "text_preview",
        "question_type",
        "difficulty",
        "points",
        "success_rate",
        "attempt_count",
        "auto_grading_enabled",
        "is_active",
    )
    list_filter = (
        "question_type",
        "difficulty",
        "auto_grading_enabled",
        "ai_generated",
        "is_active",
        "created_at",
    )
    search_fields = ("text", "instruction", "explanation")
    ordering = ("-created_at",)
    inlines = [UserResponseInline]
    readonly_fields = (
        "success_rate",
        "attempt_count",
        "average_response_time",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("step", "question_type", "text", "instruction")},
        ),
        (
            _("Options & Answers"),
            {
                "fields": (
                    "options",
                    "correct_answers",
                    "partial_credit_rules",
                    "explanation",
                    "hints",
                )
            },
        ),
        (_("Scoring"), {"fields": ("points", "negative_marking")}),
        (_("Timing"), {"fields": ("time_limit_seconds", "recommended_time_seconds")}),
        (_("Media"), {"fields": ("media_url", "media_file", "image")}),
        (_("Metadata"), {"fields": ("difficulty", "cognitive_load", "skill_focus")}),
        (
            _("AI Features"),
            {
                "fields": (
                    "ai_evaluation_criteria",
                    "ai_generated",
                    "auto_grading_enabled",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            _("Statistics"),
            {
                "fields": ("average_response_time", "success_rate", "attempt_count"),
                "classes": ("collapse",),
            },
        ),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def text_preview(self, obj):
        return obj.text[:50] + "..." if len(obj.text) > 50 else obj.text

    text_preview.short_description = "Question Text"


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "assessment_type",
        "course",
        "total_points",
        "passing_score",
        "attempt_count",
        "average_score",
        "is_active",
    )
    list_filter = (
        "assessment_type",
        "is_adaptive",
        "randomize_questions",
        "is_proctored",
        "certificate_required",
        "is_active",
        "created_at",
    )
    search_fields = ("title", "description", "course__title")
    ordering = ("-created_at",)
    inlines = [AssessmentQuestionInline, TranslationInline]
    readonly_fields = (
        "slug",
        "total_points",
        "attempt_count",
        "average_score",
        "completion_rate",
        "questions_count",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            _("Basic Information"),
            {
                "fields": (
                    "title",
                    "slug",
                    "assessment_type",
                    "description",
                    "instructions",
                )
            },
        ),
        (_("Association"), {"fields": ("lesson", "module", "course")}),
        (
            _("Scoring"),
            {"fields": ("total_points", "passing_score", "grade_boundaries")},
        ),
        (_("Timing"), {"fields": ("time_limit_minutes", "show_timer")}),
        (
            _("Behavior"),
            {
                "fields": (
                    "attempts_allowed",
                    "is_adaptive",
                    "randomize_questions",
                    "randomize_options",
                    "show_answers_after",
                    "show_score_immediately",
                    "allow_review_before_submit",
                    "prevent_backtracking",
                )
            },
        ),
        (
            _("Availability"),
            {"fields": ("available_from", "available_until", "is_proctored")},
        ),
        (_("Rewards"), {"fields": ("xp_reward", "certificate_required")}),
        (
            _("Statistics"),
            {
                "fields": (
                    "attempt_count",
                    "average_score",
                    "completion_rate",
                    "questions_count",
                ),
                "classes": ("collapse",),
            },
        ),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(UserProgress)
class UserProgressAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "content_display",
        "completion_percentage",
        "is_completed",
        "xp_earned",
        "current_streak",
        "last_accessed",
    )
    list_filter = (
        "is_completed",
        "bookmarked",
        "course__target_language",
        "created_at",
    )
    search_fields = ("user__username", "user__email", "course__title", "lesson__title")
    ordering = ("-last_accessed",)
    readonly_fields = ("created_at", "updated_at", "first_accessed", "completed_at")
    date_hierarchy = "last_accessed"

    fieldsets = (
        (
            _("User & Content"),
            {"fields": ("user", "course", "module", "lesson", "step", "assessment")},
        ),
        (
            _("Progress"),
            {
                "fields": (
                    "completion_percentage",
                    "is_completed",
                    "last_accessed",
                    "completed_at",
                    "first_accessed",
                )
            },
        ),
        (
            _("Performance"),
            {
                "fields": (
                    "total_time_spent_seconds",
                    "average_score",
                    "best_score",
                    "attempts_count",
                )
            },
        ),
        (
            _("Gamification"),
            {
                "fields": (
                    "xp_earned",
                    "streak_days",
                    "current_streak",
                    "longest_streak",
                )
            },
        ),
        (
            _("Personalization"),
            {
                "fields": (
                    "difficulty_preference",
                    "learning_style_data",
                    "notes",
                    "bookmarked",
                )
            },
        ),
        (
            _("Analytics"),
            {
                "fields": ("interaction_count", "help_requests_count", "mistakes_made"),
                "classes": ("collapse",),
            },
        ),
        (_("Status"), {"fields": ("is_active",)}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    def content_display(self, obj):
        if obj.course:
            return f"Course: {obj.course.title}"
        elif obj.lesson:
            return f"Lesson: {obj.lesson.title}"
        elif obj.step:
            return f"Step: {obj.step.title}"
        return "Unknown"

    content_display.short_description = "Content"


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "category",
        "rarity",
        "xp_reward",
        "unlock_count",
        "is_secret",
        "is_repeatable",
        "is_active",
    )
    list_filter = (
        "category",
        "rarity",
        "is_secret",
        "is_repeatable",
        "is_active",
        "created_at",
    )
    search_fields = ("name", "description")
    ordering = ("category", "name")
    inlines = [TranslationInline]
    readonly_fields = ("unlock_count", "created_at", "updated_at")
    filter_horizontal = ("prerequisites",)

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("name", "description", "short_description", "category")},
        ),
        (_("Visual"), {"fields": ("icon_name", "icon_url", "badge_color")}),
        (_("Rewards"), {"fields": ("xp_reward", "bonus_rewards")}),
        (_("Criteria"), {"fields": ("criteria", "prerequisites")}),
        (_("Properties"), {"fields": ("rarity", "is_secret", "is_repeatable")}),
        (_("Availability"), {"fields": ("available_from", "available_until")}),
        (_("Statistics"), {"fields": ("unlock_count",), "classes": ("collapse",)}),
        (_("Status & Tags"), {"fields": ("is_active", "tags")}),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "feedback_type",
        "rating",
        "status",
        "severity",
        "helpful_votes",
        "is_moderated",
        "created_at",
    )
    list_filter = (
        "feedback_type",
        "rating",
        "status",
        "severity",
        "is_helpful",
        "is_moderated",
        "created_at",
    )
    search_fields = ("user__username", "comment", "suggestions")
    ordering = ("-created_at",)
    readonly_fields = (
        "helpful_votes",
        "unhelpful_votes",
        "reported_count",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "created_at"

    fieldsets = (
        (_("User & Content"), {"fields": ("user", "content_type", "object_id")}),
        (
            _("Feedback"),
            {"fields": ("feedback_type", "rating", "comment", "suggestions")},
        ),
        (_("Classification"), {"fields": ("categories", "severity")}),
        (
            _("Status"),
            {"fields": ("status", "resolved_by", "resolved_at", "resolution_notes")},
        ),
        (
            _("Community"),
            {
                "fields": (
                    "is_helpful",
                    "helpful_votes",
                    "unhelpful_votes",
                    "reported_count",
                    "is_moderated",
                )
            },
        ),
        (
            _("Context"),
            {
                "fields": ("user_progress_context", "device_info"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Metadata"),
            {
                "fields": ("created_at", "updated_at", "created_by", "updated_by"),
                "classes": ("collapse",),
            },
        ),
    )

    actions = ["mark_as_resolved", "mark_as_helpful", "moderate_feedback"]

    def mark_as_resolved(self, request, queryset):
        updated = queryset.update(
            status="resolved", resolved_by=request.user, resolved_at=timezone.now()
        )
        self.message_user(request, f"{updated} feedback items were marked as resolved.")

    mark_as_resolved.short_description = "Mark selected feedback as resolved"


@admin.register(DiscussionThread)
class DiscussionThreadAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "thread_type",
        "creator",
        "posts_count",
        "views_count",
        "is_pinned",
        "is_locked",
        "last_post_at",
    )
    list_filter = (
        "thread_type",
        "visibility",
        "is_pinned",
        "is_locked",
        "is_archived",
        "is_moderated",
        "created_at",
    )
    search_fields = ("title", "description", "creator__username")
    ordering = ("-is_pinned", "-last_post_at")
    readonly_fields = (
        "slug",
        "posts_count",
        "views_count",
        "participants_count",
        "last_post_at",
        "last_post_by",
        "created_at",
        "updated_at",
    )
    filter_horizontal = ("moderators", "subscribers")
    date_hierarchy = "created_at"

    actions = ["pin_threads", "unpin_threads", "lock_threads", "unlock_threads"]

    def pin_threads(self, request, queryset):
        updated = queryset.update(is_pinned=True)
        self.message_user(request, f"{updated} threads were pinned.")

    pin_threads.short_description = "Pin selected threads"


@admin.register(UserAnalytics)
class UserAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "date",
        "course",
        "total_time_spent_minutes",
        "lessons_completed",
        "accuracy_percentage",
        "xp_gained",
    )
    list_filter = ("date", "course__target_language", "streak_maintained")
    search_fields = ("user__username", "user__email", "course__title")
    ordering = ("-date", "user")
    readonly_fields = ("accuracy_percentage", "completion_rate")
    date_hierarchy = "date"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("user", "course")


# Register remaining models with simple admin
admin.site.register(Dialect)
admin.site.register(GrammarRule)
admin.site.register(UserResponse)
admin.site.register(UserAssessmentAttempt)
admin.site.register(SpacedRepetition)
admin.site.register(UserAchievement)
admin.site.register(Certificate)
admin.site.register(Translation)
admin.site.register(DiscussionPost)
admin.site.register(LeaderboardEntry)
admin.site.register(Recommendation)
admin.site.register(UserSettings)


# Customize admin site
admin.site.site_header = "Language Learning Platform Administration"
admin.site.site_title = "Language Learning Admin"
admin.site.index_title = "Welcome to Language Learning Administration"

import logging

from django.contrib.auth import get_user_model
from rest_framework import serializers
from taggit.serializers import TaggitSerializer, TagListSerializerField

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

logger = logging.getLogger(__name__)
User = get_user_model()


# Base serializers
class BaseModelSerializer(serializers.ModelSerializer):
    """Base serializer with common fields and functionality"""

    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    created_by_name = serializers.CharField(
        source="created_by.get_full_name", read_only=True
    )
    updated_by_name = serializers.CharField(
        source="updated_by.get_full_name", read_only=True
    )

    class Meta:
        abstract = True
        fields = [
            "id",
            "created_at",
            "updated_at",
            "created_by_name",
            "updated_by_name",
            "is_active",
        ]


# Language-related serializers
class LanguageSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Language model"""

    tags = TagListSerializerField(required=False)
    course_count = serializers.ReadOnlyField()

    class Meta:
        model = Language
        fields = BaseModelSerializer.Meta.fields + [
            "name",
            "code",
            "native_name",
            "flag_emoji",
            "is_rtl",
            "script",
            "difficulty_rating",
            "speakers_count",
            "learning_resources_count",
            "tags",
            "course_count",
        ]


class DialectSerializer(BaseModelSerializer):
    """Serializer for Dialect model"""

    language_name = serializers.CharField(source="language.name", read_only=True)

    class Meta:
        model = Dialect
        fields = BaseModelSerializer.Meta.fields + [
            "language",
            "language_name",
            "name",
            "region",
            "description",
            "speakers_count",
        ]


# Course structure serializers
class CourseListSerializer(BaseModelSerializer, TaggitSerializer):
    """Lightweight serializer for course lists"""

    target_language_name = serializers.CharField(
        source="target_language.name", read_only=True
    )
    target_language_code = serializers.CharField(
        source="target_language.code", read_only=True
    )
    instructor_name = serializers.CharField(
        source="instructor.get_full_name", read_only=True
    )
    completion_rate = serializers.ReadOnlyField()
    modules_count = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Course
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "slug",
            "short_description",
            "target_language",
            "target_language_name",
            "target_language_code",
            "level",
            "category",
            "estimated_duration_hours",
            "instructor",
            "instructor_name",
            "is_certified",
            "course_fee",
            "is_free",
            "thumbnail",
            "enrollment_count",
            "average_rating",
            "is_published",
            "is_featured",
            "completion_rate",
            "modules_count",
            "tags",
        ]


class CourseDetailSerializer(BaseModelSerializer, TaggitSerializer):
    """Detailed serializer for individual course"""

    target_language = LanguageSerializer(read_only=True)
    target_dialect = DialectSerializer(read_only=True)
    base_language = LanguageSerializer(read_only=True)
    instructor = serializers.StringRelatedField(read_only=True)
    co_instructors = serializers.StringRelatedField(many=True, read_only=True)
    prerequisites = CourseListSerializer(many=True, read_only=True)
    completion_rate = serializers.ReadOnlyField()
    modules_count = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Course
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "slug",
            "description",
            "short_description",
            "target_language",
            "target_dialect",
            "base_language",
            "level",
            "category",
            "estimated_duration_hours",
            "prerequisites",
            "skills_focused",
            "learning_objectives",
            "instructor",
            "co_instructors",
            "is_certified",
            "certification_fee",
            "course_fee",
            "is_free",
            "thumbnail",
            "banner_image",
            "intro_video_url",
            "enrollment_count",
            "completion_count",
            "average_rating",
            "total_ratings",
            "is_published",
            "is_featured",
            "published_at",
            "difficulty_score",
            "ai_generated_content_percentage",
            "completion_rate",
            "modules_count",
            "tags",
        ]


class CourseCreateUpdateSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for creating/updating courses"""

    tags = TagListSerializerField(required=False)

    class Meta:
        model = Course
        fields = [
            "title",
            "description",
            "short_description",
            "target_language",
            "target_dialect",
            "base_language",
            "level",
            "category",
            "estimated_duration_hours",
            "prerequisites",
            "skills_focused",
            "learning_objectives",
            "co_instructors",
            "is_certified",
            "certification_fee",
            "course_fee",
            "is_free",
            "thumbnail",
            "banner_image",
            "intro_video_url",
            "is_published",
            "is_featured",
            "difficulty_score",
            "ai_generated_content_percentage",
            "tags",
        ]

    def create(self, validated_data):
        request = self.context.get("request")
        if request and request.user:
            validated_data["instructor"] = request.user
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class ModuleSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Module model"""

    course_title = serializers.CharField(source="course.title", read_only=True)
    lessons_count = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Module
        fields = BaseModelSerializer.Meta.fields + [
            "course",
            "course_title",
            "title",
            "slug",
            "order",
            "description",
            "objectives",
            "estimated_time_minutes",
            "prerequisites",
            "is_mandatory",
            "unlock_xp_required",
            "completion_xp_reward",
            "icon_name",
            "lessons_count",
            "tags",
        ]

    def validate(self, data):
        """Validate module data"""
        if data.get("unlock_xp_required", 0) < 0:
            raise serializers.ValidationError("XP requirement cannot be negative")
        return data


class LessonListSerializer(BaseModelSerializer):
    """Lightweight serializer for lesson lists"""

    module_title = serializers.CharField(source="module.title", read_only=True)
    steps_count = serializers.ReadOnlyField()

    class Meta:
        model = Lesson
        fields = BaseModelSerializer.Meta.fields + [
            "module",
            "module_title",
            "title",
            "slug",
            "order",
            "content_type",
            "description",
            "estimated_time_minutes",
            "difficulty",
            "unlock_xp_required",
            "completion_xp_reward",
            "thumbnail",
            "steps_count",
        ]


class LessonDetailSerializer(BaseModelSerializer, TaggitSerializer):
    """Detailed serializer for individual lesson"""

    module = ModuleSerializer(read_only=True)
    prerequisite_lessons = LessonListSerializer(many=True, read_only=True)
    steps_count = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Lesson
        fields = BaseModelSerializer.Meta.fields + [
            "module",
            "title",
            "slug",
            "order",
            "content_type",
            "description",
            "learning_objectives",
            "estimated_time_minutes",
            "difficulty",
            "unlock_xp_required",
            "completion_xp_reward",
            "prerequisite_lessons",
            "thumbnail",
            "intro_audio_url",
            "ai_difficulty_adjustment",
            "adaptive_content",
            "steps_count",
            "tags",
        ]


class StepSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Step model"""

    lesson_title = serializers.CharField(source="lesson.title", read_only=True)
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Step
        fields = BaseModelSerializer.Meta.fields + [
            "lesson",
            "lesson_title",
            "order",
            "content_type",
            "title",
            "data",
            "media_file",
            "external_url",
            "duration_seconds",
            "is_interactive",
            "required_for_completion",
            "step_type",
            "learning_objective",
            "hints",
            "feedback_correct",
            "feedback_incorrect",
            "feedback_partial",
            "required_completion_percentage",
            "max_attempts",
            "time_limit_seconds",
            "branching_rules",
            "difficulty_adjustment_rules",
            "ai_generated",
            "ai_evaluation_enabled",
            "base_xp_reward",
            "bonus_xp_conditions",
            "tags",
        ]

    def validate_data(self, value):
        """Validate step data based on content type"""
        content_type = self.initial_data.get("content_type")
        if content_type == "flashcard" and not value.get("front_text"):
            raise serializers.ValidationError("Flashcard must have front_text")
        return value


# Content serializers
class VocabularySerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Vocabulary model"""

    language_name = serializers.CharField(source="language.name", read_only=True)
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Vocabulary
        fields = BaseModelSerializer.Meta.fields + [
            "word",
            "language",
            "language_name",
            "phonetic_transcription",
            "translation",
            "translations",
            "part_of_speech",
            "definition",
            "example_sentence",
            "example_sentences",
            "audio_url",
            "image_url",
            "pronunciation_tips",
            "frequency_rating",
            "difficulty_level",
            "usage_notes",
            "etymology",
            "lessons",
            "synonyms",
            "antonyms",
            "related_words",
            "ai_generated_examples",
            "context_categories",
            "tags",
        ]


class GrammarRuleSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for GrammarRule model"""

    language_name = serializers.CharField(source="language.name", read_only=True)
    tags = TagListSerializerField(required=False)

    class Meta:
        model = GrammarRule
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "language",
            "language_name",
            "category",
            "explanation",
            "formula_pattern",
            "examples",
            "exceptions",
            "common_mistakes",
            "level",
            "lessons",
            "related_rules",
            "diagram_image",
            "example_audio_url",
            "usage_frequency",
            "practice_exercises_count",
            "tags",
        ]


class QuestionSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Question model"""

    step_title = serializers.CharField(
        source="step.title", read_only=True, allow_null=True
    )
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Question
        fields = BaseModelSerializer.Meta.fields + [
            "step",
            "step_title",
            "question_type",
            "text",
            "instruction",
            "options",
            "correct_answers",
            "partial_credit_rules",
            "explanation",
            "hints",
            "points",
            "negative_marking",
            "time_limit_seconds",
            "recommended_time_seconds",
            "media_url",
            "media_file",
            "image",
            "difficulty",
            "cognitive_load",
            "skill_focus",
            "ai_evaluation_criteria",
            "ai_generated",
            "auto_grading_enabled",
            "average_response_time",
            "success_rate",
            "attempt_count",
            "tags",
        ]

    def validate(self, data):
        """Validate question data"""
        question_type = data.get("question_type")
        if question_type == "multiple_choice" and not data.get("options"):
            raise serializers.ValidationError(
                "Multiple choice questions must have options"
            )
        if question_type in ["fill_blank", "short_answer"] and not data.get(
            "correct_answers"
        ):
            raise serializers.ValidationError("Question must have correct answers")
        return data


class UserResponseSerializer(BaseModelSerializer):
    """Serializer for UserResponse model"""

    question_text = serializers.CharField(source="question.text", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserResponse
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "question",
            "question_text",
            "response_data",
            "is_correct",
            "is_partially_correct",
            "score",
            "max_score",
            "time_taken_seconds",
            "attempt_number",
            "feedback",
            # "ai_feedback",
            "instructor_feedback",
            "confidence_level",
            "perceived_difficulty",
            "hints_used",
            "help_requested",
            "session_id",
        ]
        read_only_fields = [
            "user",
            "is_correct",
            "is_partially_correct",
            "score",
            "feedback",
            # "ai_feedback",
        ]


class AssessmentQuestionSerializer(BaseModelSerializer):
    """Serializer for AssessmentQuestion through model"""

    question_text = serializers.CharField(source="question.text", read_only=True)
    question_type = serializers.CharField(
        source="question.question_type", read_only=True
    )

    class Meta:
        model = AssessmentQuestion
        fields = BaseModelSerializer.Meta.fields + [
            "assessment",
            "question",
            "question_text",
            "question_type",
            "order",
            "points",
            "is_mandatory",
            "weight",
        ]


class AssessmentListSerializer(BaseModelSerializer):
    """Lightweight serializer for assessment lists"""

    course_title = serializers.CharField(
        source="course.title", read_only=True, allow_null=True
    )
    module_title = serializers.CharField(
        source="module.title", read_only=True, allow_null=True
    )
    lesson_title = serializers.CharField(
        source="lesson.title", read_only=True, allow_null=True
    )
    questions_count = serializers.ReadOnlyField()

    class Meta:
        model = Assessment
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "slug",
            "assessment_type",
            "description",
            "lesson",
            "lesson_title",
            "module",
            "module_title",
            "course",
            "course_title",
            "total_points",
            "passing_score",
            "time_limit_minutes",
            "attempts_allowed",
            "is_adaptive",
            "available_from",
            "available_until",
            "attempt_count",
            "average_score",
            "completion_rate",
            "xp_reward",
            "questions_count",
        ]


class AssessmentDetailSerializer(BaseModelSerializer, TaggitSerializer):
    """Detailed serializer for individual assessment"""

    course = CourseListSerializer(read_only=True)
    module = ModuleSerializer(read_only=True)
    lesson = LessonListSerializer(read_only=True)
    questions = AssessmentQuestionSerializer(
        source="assessmentquestion_set", many=True, read_only=True
    )
    questions_count = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = Assessment
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "slug",
            "assessment_type",
            "description",
            "instructions",
            "lesson",
            "module",
            "course",
            "questions",
            "total_points",
            "passing_score",
            "grade_boundaries",
            "time_limit_minutes",
            "show_timer",
            "attempts_allowed",
            "is_adaptive",
            "randomize_questions",
            "randomize_options",
            "show_answers_after",
            "show_score_immediately",
            "allow_review_before_submit",
            "prevent_backtracking",
            "available_from",
            "available_until",
            "is_proctored",
            "attempt_count",
            "average_score",
            "completion_rate",
            "xp_reward",
            "certificate_required",
            "questions_count",
            "tags",
        ]


class UserAssessmentAttemptSerializer(BaseModelSerializer):
    """Serializer for UserAssessmentAttempt model"""

    assessment_title = serializers.CharField(source="assessment.title", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserAssessmentAttempt
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "assessment",
            "assessment_title",
            "attempt_number",
            "started_at",
            "submitted_at",
            "completed_at",
            "score",
            "max_score",
            "percentage_score",
            "grade",
            "passed",
            "completion_time_seconds",
            "time_limit_exceeded",
            "status",
            "responses",
            # "proctoring_data",
            "integrity_flags",
        ]
        read_only_fields = [
            "user",
            "score",
            "max_score",
            "percentage_score",
            "grade",
            "passed",
        ]


# Progress and analytics serializers
class UserProgressSerializer(BaseModelSerializer):
    """Serializer for UserProgress model"""

    course_title = serializers.CharField(
        source="course.title", read_only=True, allow_null=True
    )
    module_title = serializers.CharField(
        source="module.title", read_only=True, allow_null=True
    )
    lesson_title = serializers.CharField(
        source="lesson.title", read_only=True, allow_null=True
    )
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserProgress
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "course",
            "course_title",
            "module",
            "module_title",
            "lesson",
            "lesson_title",
            "step",
            "assessment",
            "completion_percentage",
            "is_completed",
            "last_accessed",
            "completed_at",
            "first_accessed",
            "total_time_spent_seconds",
            "average_score",
            "best_score",
            "attempts_count",
            "xp_earned",
            "streak_days",
            "current_streak",
            "longest_streak",
            "difficulty_preference",
            "learning_style_data",
            "notes",
            "bookmarked",
            "interaction_count",
            "help_requests_count",
            "mistakes_made",
        ]
        read_only_fields = ["user"]


class SpacedRepetitionSerializer(BaseModelSerializer):
    """Serializer for SpacedRepetition model"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = SpacedRepetition
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "content_type",
            "object_id",
            "last_reviewed",
            "next_review",
            "ease_factor",
            "interval_days",
            "repetition_count",
            "consecutive_correct",
            "average_response_time",
            "difficulty_rating",
            "success_rate",
            "is_due",
            "is_learning",
            "is_mature",
            "algorithm",
        ]
        read_only_fields = ["user"]


# Gamification serializers
class AchievementSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for Achievement model"""

    tags = TagListSerializerField(required=False)

    class Meta:
        model = Achievement
        fields = BaseModelSerializer.Meta.fields + [
            "name",
            "description",
            "short_description",
            "category",
            "icon_name",
            "icon_url",
            "badge_color",
            "xp_reward",
            "bonus_rewards",
            "criteria",
            "prerequisites",
            "rarity",
            "is_secret",
            "is_repeatable",
            "unlock_count",
            "available_from",
            "available_until",
            "tags",
        ]


class UserAchievementSerializer(BaseModelSerializer):
    """Serializer for UserAchievement model"""

    achievement = AchievementSerializer(read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = UserAchievement
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "achievement",
            "unlocked_at",
            "progress_data",
            "notification_sent",
        ]
        read_only_fields = ["user"]


class CertificateSerializer(BaseModelSerializer):
    """Serializer for Certificate model"""

    course = CourseListSerializer(read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)

    class Meta:
        model = Certificate
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "course",
            "issued_at",
            "valid_from",
            "expiration_date",
            "verification_code",
            "verification_url",
            "final_score",
            "completion_time_hours",
            "grade",
            "certificate_template",
            "issuer_name",
            "issuer_signature_url",
            "pdf_file",
            "pdf_url",
            "is_revoked",
            "revoked_at",
            "revocation_reason",
        ]
        read_only_fields = ["user", "verification_code"]


class LeaderboardEntrySerializer(BaseModelSerializer):
    """Serializer for LeaderboardEntry model"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    course_title = serializers.CharField(
        source="course.title", read_only=True, allow_null=True
    )

    class Meta:
        model = LeaderboardEntry
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "leaderboard_type",
            "course",
            "course_title",
            "total_xp",
            "current_rank",
            "previous_rank",
            "rank_change",
            "achievements_count",
            "courses_completed",
            "lessons_completed",
            "current_streak",
            "longest_streak",
            "period_start",
            "period_end",
            "last_updated",
            "last_activity",
        ]


# Social and community serializers
class FeedbackSerializer(BaseModelSerializer):
    """Serializer for Feedback model"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    resolved_by_name = serializers.CharField(
        source="resolved_by.get_full_name", read_only=True
    )

    class Meta:
        model = Feedback
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "content_type",
            "object_id",
            "feedback_type",
            "rating",
            "comment",
            "suggestions",
            "categories",
            "severity",
            "status",
            "resolved_by",
            "resolved_by_name",
            "resolved_at",
            "resolution_notes",
            "is_helpful",
            "helpful_votes",
            "unhelpful_votes",
            "reported_count",
            "is_moderated",
            "user_progress_context",
            # "device_info",
        ]
        read_only_fields = ["user"]


class DiscussionPostSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for DiscussionPost model"""

    author_name = serializers.CharField(source="author.get_full_name", read_only=True)
    thread_title = serializers.CharField(source="thread.title", read_only=True)
    depth_level = serializers.ReadOnlyField()
    tags = TagListSerializerField(required=False)

    class Meta:
        model = DiscussionPost
        fields = BaseModelSerializer.Meta.fields + [
            "thread",
            "thread_title",
            "author",
            "author_name",
            "content",
            "parent_post",
            "content_format",
            "attachments",
            "likes",
            "dislikes",
            "replies_count",
            "is_edited",
            "edit_history",
            "original_content",
            "is_flagged",
            "flagged_count",
            "is_approved",
            "moderated_by",
            "is_solution",
            "helpful_votes",
            "depth_level",
            "tags",
        ]
        read_only_fields = ["author", "likes", "dislikes", "replies_count"]


class DiscussionThreadSerializer(BaseModelSerializer, TaggitSerializer):
    """Serializer for DiscussionThread model"""

    creator_name = serializers.CharField(source="creator.get_full_name", read_only=True)
    last_post_by_name = serializers.CharField(
        source="last_post_by.get_full_name", read_only=True
    )
    recent_posts = DiscussionPostSerializer(source="posts", many=True, read_only=True)
    tags = TagListSerializerField(required=False)

    class Meta:
        model = DiscussionThread
        fields = BaseModelSerializer.Meta.fields + [
            "title",
            "slug",
            "thread_type",
            "description",
            "content_type",
            "object_id",
            "creator",
            "creator_name",
            "moderators",
            "subscribers",
            "posts_count",
            "views_count",
            "participants_count",
            "last_post_at",
            "last_post_by",
            "last_post_by_name",
            "is_pinned",
            "is_locked",
            "is_archived",
            "visibility",
            "is_moderated",
            "reported_count",
            "recent_posts",
            "tags",
        ]
        read_only_fields = [
            "creator",
            "posts_count",
            "views_count",
            "participants_count",
        ]


# Personalization serializers
class RecommendationSerializer(BaseModelSerializer):
    """Serializer for Recommendation model"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    is_expired = serializers.ReadOnlyField()

    class Meta:
        model = Recommendation
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "recommended_type",
            "recommended_id",
            "source",
            "score",
            "confidence",
            "relevance_score",
            "reason",
            "explanation_data",
            "factors",
            "generated_at",
            "expires_at",
            "context",
            "is_viewed",
            "viewed_at",
            "is_clicked",
            "clicked_at",
            "is_dismissed",
            "dismissed_at",
            "user_rating",
            "feedback_text",
            "is_expired",
        ]
        read_only_fields = ["user", "generated_at"]


class UserSettingsSerializer(BaseModelSerializer):
    """Serializer for UserSettings model"""

    preferred_base_language = LanguageSerializer(read_only=True)
    ui_language = LanguageSerializer(read_only=True)

    class Meta:
        model = UserSettings
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "preferred_base_language",
            "ui_language",
            "learning_style",
            "difficulty_preference",
            "daily_goal_minutes",
            "weekly_goal_lessons",
            "preferred_study_times",
            "timezone",
            "reminder_enabled",
            "reminder_time",
            "notification_preferences",
            "email_notifications",
            "push_notifications",
            "achievement_notifications",
            "enable_spaced_repetition",
            "enable_adaptive_difficulty",
            "enable_ai_recommendations",
            "enable_gamification",
            "accessibility_preferences",
            "high_contrast_mode",
            "large_text_mode",
            "screen_reader_mode",
            "profile_visibility",
            "show_in_leaderboards",
            "allow_friend_requests",
        ]
        read_only_fields = ["user"]


class UserAnalyticsSerializer(BaseModelSerializer):
    """Serializer for UserAnalytics model"""

    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    course_title = serializers.CharField(
        source="course.title", read_only=True, allow_null=True
    )

    class Meta:
        model = UserAnalytics
        fields = BaseModelSerializer.Meta.fields + [
            "user",
            "user_name",
            "date",
            "course",
            "course_title",
            "total_time_spent_minutes",
            "active_learning_minutes",
            "passive_learning_minutes",
            "lessons_started",
            "lessons_completed",
            "steps_completed",
            "questions_answered",
            "correct_answers",
            "xp_gained",
            "accuracy_percentage",
            "average_response_time",
            "completion_rate",
            "skills_improved",
            "content_types_engaged",
            "vocabulary_learned",
            "grammar_rules_practiced",
            "login_count",
            "session_count",
            "streak_maintained",
            "achievements_unlocked",
            "discussions_participated",
            "feedback_given",
            "help_requests",
            "primary_device_type",
            "study_locations",
        ]
        read_only_fields = ["user"]


# Translation serializers
class TranslationSerializer(BaseModelSerializer):
    """Serializer for Translation model"""

    language = LanguageSerializer(read_only=True)
    translator_name = serializers.CharField(
        source="translator.get_full_name", read_only=True
    )
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", read_only=True
    )

    class Meta:
        model = Translation
        fields = BaseModelSerializer.Meta.fields + [
            "content_type",
            "object_id",
            "language",
            "translated_title",
            "translated_description",
            "translated_text",
            "translated_data",
            "translator",
            "translator_name",
            "is_ai_translated",
            "translation_service",
            "confidence_score",
            "is_reviewed",
            "reviewed_by",
            "reviewed_by_name",
            "reviewed_at",
            "quality_score",
        ]


# Specialized serializers for specific use cases
class CourseEnrollmentSerializer(serializers.Serializer):
    """Serializer for course enrollment"""

    course_id = serializers.UUIDField()
    enrollment_date = serializers.DateTimeField(read_only=True)
    progress_percentage = serializers.FloatField(read_only=True)

    def validate_course_id(self, value):
        """Validate that course exists and is published"""
        try:
            course = Course.objects.get(id=value, is_published=True, is_active=True)
            return value
        except Course.DoesNotExist:
            raise serializers.ValidationError(
                "Course not found or not available for enrollment"
            )


class CourseProgressSerializer(serializers.Serializer):
    """Serializer for course progress summary"""

    course = CourseListSerializer(read_only=True)
    completion_percentage = serializers.FloatField(read_only=True)
    current_lesson = LessonListSerializer(read_only=True)
    total_lessons = serializers.IntegerField(read_only=True)
    completed_lessons = serializers.IntegerField(read_only=True)
    total_xp_earned = serializers.IntegerField(read_only=True)
    current_streak = serializers.IntegerField(read_only=True)
    last_accessed = serializers.DateTimeField(read_only=True)


class LearningPathSerializer(serializers.Serializer):
    """Serializer for personalized learning path"""

    next_lesson = LessonListSerializer(read_only=True)
    recommended_lessons = LessonListSerializer(many=True, read_only=True)
    review_items = serializers.ListField(read_only=True)
    daily_goal_progress = serializers.DictField(read_only=True)
    achievements_to_unlock = AchievementSerializer(many=True, read_only=True)


class AssessmentResultSerializer(serializers.Serializer):
    """Serializer for assessment results"""

    attempt = UserAssessmentAttemptSerializer(read_only=True)
    detailed_results = serializers.DictField(read_only=True)
    performance_analysis = serializers.DictField(read_only=True)
    improvement_suggestions = serializers.ListField(read_only=True)
    next_steps = serializers.ListField(read_only=True)


class SkillAnalysisSerializer(serializers.Serializer):
    """Serializer for skill analysis and proficiency"""

    skill_name = serializers.CharField(read_only=True)
    proficiency_level = serializers.FloatField(read_only=True)
    progress_trend = serializers.CharField(read_only=True)
    strengths = serializers.ListField(read_only=True)
    weaknesses = serializers.ListField(read_only=True)
    recommended_practice = serializers.ListField(read_only=True)


class StudyStreakSerializer(serializers.Serializer):
    """Serializer for study streak information"""

    current_streak = serializers.IntegerField(read_only=True)
    longest_streak = serializers.IntegerField(read_only=True)
    streak_multiplier = serializers.FloatField(read_only=True)
    days_until_next_milestone = serializers.IntegerField(read_only=True)
    streak_rewards = serializers.ListField(read_only=True)


class BulkOperationSerializer(serializers.Serializer):
    """Serializer for bulk operations"""

    object_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100
    )
    action = serializers.CharField(max_length=50)
    parameters = serializers.DictField(required=False, default=dict)

    def validate_action(self, value):
        """Validate action type"""
        allowed_actions = [
            "delete",
            "activate",
            "deactivate",
            "archive",
            "publish",
            "unpublish",
        ]
        if value not in allowed_actions:
            raise serializers.ValidationError(
                f"Action must be one of: {', '.join(allowed_actions)}"
            )
        return value


class SearchResultSerializer(serializers.Serializer):
    """Serializer for search results"""

    result_type = serializers.CharField(read_only=True)
    object_id = serializers.UUIDField(read_only=True)
    title = serializers.CharField(read_only=True)
    description = serializers.CharField(read_only=True)
    relevance_score = serializers.FloatField(read_only=True)
    highlight_text = serializers.CharField(read_only=True)
    url = serializers.CharField(read_only=True)
    metadata = serializers.DictField(read_only=True)


class DashboardSerializer(serializers.Serializer):
    """Serializer for user dashboard data"""

    user_stats = serializers.DictField(read_only=True)
    recent_activity = serializers.ListField(read_only=True)
    progress_summary = serializers.DictField(read_only=True)
    upcoming_lessons = LessonListSerializer(many=True, read_only=True)
    review_items_count = serializers.IntegerField(read_only=True)
    achievements_this_week = UserAchievementSerializer(many=True, read_only=True)
    leaderboard_position = LeaderboardEntrySerializer(read_only=True)
    study_streak = StudyStreakSerializer(read_only=True)
    daily_goal_progress = serializers.DictField(read_only=True)
    recommendations = RecommendationSerializer(many=True, read_only=True)


class CourseStatisticsSerializer(serializers.Serializer):
    """Serializer for course statistics"""

    total_enrollments = serializers.IntegerField(read_only=True)
    active_learners = serializers.IntegerField(read_only=True)
    completion_rate = serializers.FloatField(read_only=True)
    average_rating = serializers.FloatField(read_only=True)
    average_completion_time = serializers.FloatField(read_only=True)
    difficulty_distribution = serializers.DictField(read_only=True)
    engagement_metrics = serializers.DictField(read_only=True)
    feedback_summary = serializers.DictField(read_only=True)
    learning_outcomes = serializers.DictField(read_only=True)


class InstructorAnalyticsSerializer(serializers.Serializer):
    """Serializer for instructor analytics"""

    courses_taught = serializers.IntegerField(read_only=True)
    total_students = serializers.IntegerField(read_only=True)
    average_course_rating = serializers.FloatField(read_only=True)
    student_success_rate = serializers.FloatField(read_only=True)
    engagement_score = serializers.FloatField(read_only=True)
    feedback_score = serializers.FloatField(read_only=True)
    course_performance = serializers.ListField(read_only=True)
    popular_content = serializers.ListField(read_only=True)
    improvement_areas = serializers.ListField(read_only=True)

import uuid

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

# from django.contrib.postgres.fields import ArrayField  # Not compatible with SQLite
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _
from taggit.managers import TaggableManager

# Helper functions for default values
# Using built-in list and dict constructors for JSONField defaults


# Abstract base model for common fields: timestamps, soft delete, UUID, auditing
class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_%(class)s",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="updated_%(class)s",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)  # For optimistic concurrency
    tags = TaggableManager(blank=True)  # Tagging support for searchability

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["created_at", "is_active"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.__class__.__name__} ({self.id})"

    def soft_delete(self):
        """Soft delete the instance"""
        from django.utils import timezone

        self.is_active = False
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_active", "deleted_at"])

    def restore(self):
        """Restore soft deleted instance"""
        self.is_active = True
        self.deleted_at = None
        self.save(update_fields=["is_active", "deleted_at"])


# Language model with more details
class Language(BaseModel):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    code = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        validators=[RegexValidator(r"^[a-zA-Z]{2,3}(-[a-zA-Z]{2,3})?$")],
    )
    native_name = models.CharField(max_length=100, blank=True)
    flag_emoji = models.CharField(max_length=10, blank=True)
    is_rtl = models.BooleanField(default=False)
    script = models.CharField(max_length=50, blank=True)  # e.g., Latin, Cyrillic
    difficulty_rating = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        db_index=True,
    )
    speakers_count = models.BigIntegerField(default=0, blank=True)
    learning_resources_count = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        verbose_name = _("Language")
        verbose_name_plural = _("Languages")
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["code", "difficulty_rating"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"

    @property
    def course_count(self):
        return (
            getattr(self, "target_courses", self.__class__.objects.none())
            .filter(is_published=True, is_active=True)
            .count()
        )


# Dialect model for language variations
class Dialect(BaseModel):
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="dialects"
    )
    name = models.CharField(max_length=100, db_index=True)
    region = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    speakers_count = models.BigIntegerField(default=0, blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("language", "name")]
        verbose_name = _("Dialect")
        verbose_name_plural = _("Dialects")

    def __str__(self):
        return f"{self.name} ({getattr(self.language, 'code', 'N/A')})"


# Course model with advanced features
class Course(BaseModel):
    LEVEL_CHOICES = [
        ("A1", "A1"),
        ("A2", "A2"),
        ("B1", "B1"),
        ("B2", "B2"),
        ("C1", "C1"),
        ("C2", "C2"),
        ("beginner", _("Beginner")),
        ("intermediate", _("Intermediate")),
        ("advanced", _("Advanced")),
        ("expert", _("Expert")),
    ]

    CATEGORY_CHOICES = [
        ("general", _("General Language")),
        ("business", _("Business")),
        ("academic", _("Academic")),
        ("conversational", _("Conversational")),
        ("technical", _("Technical")),
        ("cultural", _("Cultural")),
        ("exam_prep", _("Exam Preparation")),
    ]

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, unique=True, db_index=True, blank=True)
    description = models.TextField(blank=True)
    short_description = models.CharField(max_length=500, blank=True)
    target_language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="target_courses"
    )
    target_dialect = models.ForeignKey(
        Dialect,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="target_courses",
    )
    base_language = models.ForeignKey(
        Language,
        on_delete=models.CASCADE,
        related_name="base_courses",
        null=True,
        blank=True,
    )
    level = models.CharField(
        max_length=20, choices=LEVEL_CHOICES, default="beginner", db_index=True
    )
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default="general", db_index=True
    )
    estimated_duration_hours = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0)]
    )
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="dependent_courses"
    )
    skills_focused = models.JSONField(
        default=list, blank=True
    )  # e.g., ['listening', 'speaking']
    learning_objectives = models.JSONField(default=list, blank=True)
    instructor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses_taught",
    )
    co_instructors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="courses_co_taught"
    )

    # Certification and pricing
    is_certified = models.BooleanField(default=False)
    certification_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, blank=True
    )
    course_fee = models.DecimalField(
        max_digits=10, decimal_places=2, default=0.00, blank=True
    )
    is_free = models.BooleanField(default=True)

    # Media
    thumbnail = models.ImageField(upload_to="course_thumbnails/", blank=True, null=True)
    banner_image = models.ImageField(upload_to="course_banners/", blank=True, null=True)
    intro_video_url = models.URLField(max_length=500, blank=True)

    # Statistics
    enrollment_count = models.PositiveBigIntegerField(default=0, db_index=True)
    completion_count = models.PositiveBigIntegerField(default=0, db_index=True)
    average_rating = models.FloatField(
        default=0.0,
        validators=[MinValueValidator(0.0), MaxValueValidator(5.0)],
        db_index=True,
    )
    total_ratings = models.PositiveIntegerField(default=0)

    # Publishing
    is_published = models.BooleanField(default=False, db_index=True)
    is_featured = models.BooleanField(default=False, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # AI and personalization
    difficulty_score = models.FloatField(
        default=1.0, validators=[MinValueValidator(0.1), MaxValueValidator(10.0)]
    )
    ai_generated_content_percentage = models.PositiveIntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        unique_together = [("title", "target_language", "level")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(
                fields=[
                    "slug",
                    "target_language",
                    "level",
                    "is_published",
                    "is_featured",
                ]
            ),
            models.Index(fields=["average_rating", "enrollment_count", "category"]),
        ]
        verbose_name = _("Course")
        verbose_name_plural = _("Courses")

    def __str__(self):
        return f"{self.title} ({getattr(self.target_language, 'code', 'N/A')} - {self.level})"

    @property
    def completion_rate(self):
        if self.enrollment_count == 0:
            return 0
        return (self.completion_count / self.enrollment_count) * 100

    @property
    def modules_count(self):
        return (
            getattr(self, "modules", self.__class__.objects.none())
            .filter(is_active=True)
            .count()
        )


# Module model (replacing Topic for modularity)
class Module(BaseModel):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="modules")
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=1, db_index=True)
    description = models.TextField(blank=True)
    objectives = models.JSONField(default=list, blank=True)
    estimated_time_minutes = models.PositiveIntegerField(default=0)
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="dependent_modules"
    )
    is_mandatory = models.BooleanField(default=True)
    unlock_xp_required = models.PositiveIntegerField(default=0)
    completion_xp_reward = models.PositiveIntegerField(default=100)
    icon_name = models.CharField(max_length=50, blank=True)
    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        unique_together = [("course", "order"), ("course", "slug")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["course", "order"]),
        ]
        verbose_name = _("Module")
        verbose_name_plural = _("Modules")

    def __str__(self):
        return f"{self.title} (Order: {self.order} in {self.course})"

    @property
    def lessons_count(self):
        return (
            getattr(self, "lessons", self.__class__.objects.none())
            .filter(is_active=True)
            .count()
        )


# Lesson model within modules
class Lesson(BaseModel):
    CONTENT_TYPE_CHOICES = [
        ("grammar", _("Grammar")),
        ("vocabulary", _("Vocabulary")),
        ("conversation", _("Conversation")),
        ("pronunciation", _("Pronunciation")),
        ("listening", _("Listening")),
        ("reading", _("Reading")),
        ("writing", _("Writing")),
        ("culture", _("Culture")),
        ("review", _("Review")),
        ("assessment", _("Assessment")),
    ]

    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name="lessons")
    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=1, db_index=True)
    content_type = models.CharField(
        max_length=50, choices=CONTENT_TYPE_CHOICES, db_index=True
    )
    description = models.TextField(blank=True)
    learning_objectives = models.JSONField(default=list, blank=True)
    estimated_time_minutes = models.PositiveIntegerField(default=0)
    difficulty = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        db_index=True,
    )
    unlock_xp_required = models.PositiveIntegerField(default=0)
    completion_xp_reward = models.PositiveIntegerField(default=50)

    # Prerequisites and dependencies
    prerequisite_lessons = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="unlocked_lessons"
    )

    # Media
    thumbnail = models.ImageField(upload_to="lesson_thumbnails/", blank=True, null=True)
    intro_audio_url = models.URLField(max_length=500, blank=True)

    # AI features
    ai_difficulty_adjustment = models.BooleanField(default=True)
    adaptive_content = models.BooleanField(default=False)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        unique_together = [("module", "order"), ("module", "slug")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["module", "order", "content_type", "difficulty"]),
        ]
        verbose_name = _("Lesson")
        verbose_name_plural = _("Lessons")

    def __str__(self):
        return f"{self.title} (Order: {self.order} in {self.module})"

    @property
    def steps_count(self):
        return self.steps.filter(is_active=True).count()


# Abstract ContentBlock for polymorphic content
class ContentBlock(BaseModel):
    CONTENT_TYPES = [
        ("text", _("Text")),
        ("image", _("Image")),
        ("video", _("Video")),
        ("audio", _("Audio")),
        ("interactive", _("Interactive")),
        ("code", _("Code")),
        ("flashcard", _("Flashcard")),
        ("dialogue", _("Dialogue")),
        ("pronunciation", _("Pronunciation Practice")),
        ("game", _("Game")),
        ("quiz", _("Quiz")),
        ("story", _("Story")),
    ]

    lesson = models.ForeignKey(
        Lesson, on_delete=models.CASCADE, related_name="content_blocks"
    )
    order = models.PositiveIntegerField(default=1, db_index=True)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPES, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    data = models.JSONField(default=dict, blank=True)  # Type-specific data
    media_file = models.FileField(upload_to="content_media/", blank=True, null=True)
    external_url = models.URLField(max_length=500, blank=True)
    duration_seconds = models.PositiveIntegerField(default=0, blank=True)
    is_interactive = models.BooleanField(default=False)
    required_for_completion = models.BooleanField(default=True)
    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        abstract = True
        unique_together = [("lesson", "order")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["lesson", "order", "content_type"]),
        ]


# Step model as concrete ContentBlock
class Step(ContentBlock):
    STEP_TYPES = [
        ("intro", _("Introduction")),
        ("learning", _("Learning")),
        ("practice", _("Practice")),
        ("review", _("Review")),
        ("assessment", _("Assessment")),
        ("bonus", _("Bonus")),
    ]

    step_type = models.CharField(
        max_length=50, choices=STEP_TYPES, default="learning", db_index=True
    )
    learning_objective = models.TextField(blank=True)
    hints = models.JSONField(default=list, blank=True)
    feedback_correct = models.TextField(blank=True)
    feedback_incorrect = models.TextField(blank=True)
    feedback_partial = models.TextField(blank=True)
    required_completion_percentage = models.PositiveIntegerField(
        default=100, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    max_attempts = models.PositiveIntegerField(default=3)
    time_limit_seconds = models.PositiveIntegerField(default=0, blank=True)

    # Adaptive learning
    branching_rules = models.JSONField(
        default=dict, blank=True
    )  # e.g., {'if_score < 50': 'redirect_to_step_id'}
    difficulty_adjustment_rules = models.JSONField(default=dict, blank=True)

    # AI features
    ai_generated = models.BooleanField(default=False)
    ai_evaluation_enabled = models.BooleanField(default=False)

    # XP and rewards
    base_xp_reward = models.PositiveIntegerField(default=10)
    bonus_xp_conditions = models.JSONField(default=dict, blank=True)

    class Meta(ContentBlock.Meta):
        verbose_name = _("Step")
        verbose_name_plural = _("Steps")
        indexes = ContentBlock.Meta.indexes + [
            models.Index(fields=["step_type"]),
        ]

    def __str__(self):
        return f"Step: {self.title or self.content_type} (Order: {self.order})"


# Vocabulary model for word tracking
class Vocabulary(BaseModel):
    PART_OF_SPEECH_CHOICES = [
        ("noun", _("Noun")),
        ("verb", _("Verb")),
        ("adjective", _("Adjective")),
        ("adverb", _("Adverb")),
        ("pronoun", _("Pronoun")),
        ("preposition", _("Preposition")),
        ("conjunction", _("Conjunction")),
        ("interjection", _("Interjection")),
        ("phrase", _("Phrase")),
        ("idiom", _("Idiom")),
    ]

    word = models.CharField(max_length=255, db_index=True)
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="vocabulary"
    )
    phonetic_transcription = models.CharField(max_length=255, blank=True)
    translation = models.CharField(max_length=255, blank=True)
    translations = models.JSONField(
        default=dict, blank=True
    )  # Multiple language translations
    part_of_speech = models.CharField(
        max_length=50, choices=PART_OF_SPEECH_CHOICES, blank=True
    )
    definition = models.TextField(blank=True)
    example_sentence = models.TextField(blank=True)
    example_sentences = models.JSONField(default=list, blank=True)

    # Media
    audio_url = models.URLField(max_length=500, blank=True)
    image_url = models.URLField(max_length=500, blank=True)
    pronunciation_tips = models.TextField(blank=True)

    # Metadata
    frequency_rating = models.IntegerField(default=1, db_index=True)
    difficulty_level = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    usage_notes = models.TextField(blank=True)
    etymology = models.TextField(blank=True)

    # Relations
    lessons = models.ManyToManyField(Lesson, related_name="vocabulary", blank=True)
    synonyms = models.ManyToManyField("self", blank=True, symmetrical=True)
    antonyms = models.ManyToManyField("self", blank=True, symmetrical=True)
    related_words = models.ManyToManyField("self", blank=True)

    # AI features
    ai_generated_examples = models.BooleanField(default=False)
    context_categories = models.JSONField(default=list, blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("word", "language")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["word", "language", "frequency_rating"]),
            models.Index(fields=["part_of_speech", "difficulty_level"]),
        ]
        verbose_name = _("Vocabulary")
        verbose_name_plural = _("Vocabulary")

    def __str__(self):
        return f"{self.word} ({self.language.code})"


# GrammarRule model
class GrammarRule(BaseModel):
    title = models.CharField(max_length=255, db_index=True)
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="grammar_rules"
    )
    category = models.CharField(
        max_length=100, db_index=True
    )  # e.g., "Tenses", "Articles"
    explanation = models.TextField()
    formula_pattern = models.CharField(max_length=500, blank=True)
    examples = models.JSONField(default=list, blank=True)
    exceptions = models.JSONField(default=list, blank=True)
    common_mistakes = models.JSONField(default=list, blank=True)
    level = models.CharField(
        max_length=20, choices=Course.LEVEL_CHOICES, default="beginner", db_index=True
    )

    # Relations
    lessons = models.ManyToManyField(Lesson, related_name="grammar_rules", blank=True)
    related_rules = models.ManyToManyField("self", blank=True)

    # Media
    diagram_image = models.ImageField(
        upload_to="grammar_diagrams/", blank=True, null=True
    )
    example_audio_url = models.URLField(max_length=500, blank=True)

    # Metadata
    usage_frequency = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    practice_exercises_count = models.PositiveIntegerField(default=0)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        unique_together = [("title", "language")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["language", "level", "category"]),
        ]
        verbose_name = _("Grammar Rule")
        verbose_name_plural = _("Grammar Rules")

    def __str__(self):
        return f"{self.title} ({self.language.code})"


# Question model with advanced types
class Question(BaseModel):
    QUESTION_TYPES = [
        ("multiple_choice", _("Multiple Choice")),
        ("multi_select", _("Multi Select")),
        ("fill_blank", _("Fill in the Blank")),
        ("drag_drop", _("Drag and Drop")),
        ("matching", _("Matching")),
        ("true_false", _("True/False")),
        ("short_answer", _("Short Answer")),
        ("essay", _("Essay")),
        ("audio_response", _("Audio Response")),
        ("video_response", _("Video Response")),
        ("speaking_practice", _("Speaking Practice")),
        ("listening_comprehension", _("Listening Comprehension")),
        ("pronunciation_check", _("Pronunciation Check")),
        ("conversation_practice", _("Conversation Practice")),
        ("translation", _("Translation")),
        ("sentence_building", _("Sentence Building")),
    ]

    step = models.ForeignKey(
        Step, on_delete=models.CASCADE, related_name="questions", null=True, blank=True
    )
    question_type = models.CharField(
        max_length=30, choices=QUESTION_TYPES, db_index=True
    )
    text = models.TextField()
    instruction = models.TextField(blank=True)
    options = models.JSONField(default=list, blank=True)
    correct_answers = models.JSONField(
        default=list, blank=True
    )  # Support multiple correct
    partial_credit_rules = models.JSONField(default=dict, blank=True)
    explanation = models.TextField(blank=True)
    hints = models.JSONField(default=list, blank=True)

    # Scoring
    points = models.PositiveIntegerField(default=1)
    negative_marking = models.FloatField(default=0.0)

    # Timing
    time_limit_seconds = models.PositiveIntegerField(default=0, blank=True)
    recommended_time_seconds = models.PositiveIntegerField(default=30)

    # Media
    media_url = models.URLField(max_length=500, blank=True)
    media_file = models.FileField(upload_to="question_media/", blank=True, null=True)
    image = models.ImageField(upload_to="question_images/", blank=True, null=True)

    # Metadata
    difficulty = models.IntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        db_index=True,
    )
    cognitive_load = models.IntegerField(
        default=1, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    skill_focus = models.JSONField(default=list, blank=True)

    # AI features
    ai_evaluation_criteria = models.JSONField(
        default=dict, blank=True
    )  # For open-ended questions
    ai_generated = models.BooleanField(default=False)
    auto_grading_enabled = models.BooleanField(default=True)

    # Analytics
    average_response_time = models.PositiveIntegerField(default=0)  # in seconds
    success_rate = models.FloatField(default=0.0)
    attempt_count = models.PositiveIntegerField(default=0)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["question_type", "difficulty"]),
            models.Index(fields=["step", "question_type"]),
        ]
        verbose_name = _("Question")
        verbose_name_plural = _("Questions")

    def __str__(self):
        return f"Question: {self.text[:50]}... ({self.question_type})"

    def update_analytics(self):
        """Update question analytics based on user responses"""
        responses = self.user_responses.all()
        if responses.exists():
            self.attempt_count = responses.count()
            self.success_rate = (
                responses.filter(is_correct=True).count() / self.attempt_count
            ) * 100
            self.average_response_time = (
                responses.aggregate(avg_time=models.Avg("time_taken_seconds"))[
                    "avg_time"
                ]
                or 0
            )
            self.save(
                update_fields=["attempt_count", "success_rate", "average_response_time"]
            )


# UserResponse model (replacing UserAnswer for flexibility)
class UserResponse(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_responses",
    )
    question = models.ForeignKey(
        Question, on_delete=models.CASCADE, related_name="user_responses"
    )
    response_data = models.JSONField(
        default=dict, blank=True
    )  # Flexible: text, selections, audio_url, etc.
    is_correct = models.BooleanField(default=False, db_index=True)
    is_partially_correct = models.BooleanField(default=False)
    score = models.FloatField(default=0.0, db_index=True)
    max_score = models.FloatField(default=1.0)
    time_taken_seconds = models.PositiveIntegerField(default=0)
    attempt_number = models.PositiveIntegerField(default=1)

    # Feedback
    feedback = models.TextField(blank=True)  # AI-generated feedback
    analytics_data = models.JSONField(default=dict, blank=True)
    instructor_feedback = models.TextField(blank=True)

    # Confidence and difficulty
    confidence_level = models.IntegerField(
        default=0, validators=[MinValueValidator(0), MaxValueValidator(100)], blank=True
    )
    perceived_difficulty = models.IntegerField(
        default=0, validators=[MinValueValidator(1), MaxValueValidator(5)], blank=True
    )

    # Help used
    hints_used = models.JSONField(default=list, blank=True)
    help_requested = models.BooleanField(default=False)

    # Context
    session_id = models.UUIDField(
        null=True, blank=True
    )  # For grouping responses in a session
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "question", "attempt_number")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "question", "is_correct", "score"]),
            models.Index(fields=["session_id", "created_at"]),
        ]
        verbose_name = _("User Response")
        verbose_name_plural = _("User Responses")

    def __str__(self):
        return f"Response by {self.user} to {self.question} (Score: {self.score})"


# Assessment model (base for Quiz, Exam, etc.)
class Assessment(BaseModel):
    ASSESSMENT_TYPES = [
        ("quiz", _("Quiz")),
        ("exam", _("Exam")),
        ("practice", _("Practice")),
        ("placement", _("Placement Test")),
        ("progress", _("Progress Check")),
        ("final", _("Final Assessment")),
        ("diagnostic", _("Diagnostic Test")),
    ]

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True)
    assessment_type = models.CharField(
        max_length=20, choices=ASSESSMENT_TYPES, db_index=True
    )
    description = models.TextField(blank=True)
    instructions = models.TextField(blank=True)

    # Relations
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="assessments",
        null=True,
        blank=True,
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="assessments",
        null=True,
        blank=True,
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="assessments",
        null=True,
        blank=True,
    )
    questions = models.ManyToManyField(
        Question, related_name="assessments", through="AssessmentQuestion"
    )

    # Scoring and passing
    total_points = models.PositiveIntegerField(default=0)
    passing_score = models.PositiveIntegerField(
        default=70, validators=[MinValueValidator(0), MaxValueValidator(100)]
    )
    grade_boundaries = models.JSONField(
        default=dict, blank=True
    )  # {'A': 90, 'B': 80, 'C': 70}

    # Timing
    time_limit_minutes = models.PositiveIntegerField(default=0)
    show_timer = models.BooleanField(default=True)

    # Behavior
    attempts_allowed = models.PositiveIntegerField(default=3)
    is_adaptive = models.BooleanField(default=False)
    randomize_questions = models.BooleanField(default=True)
    randomize_options = models.BooleanField(default=True)
    show_answers_after = models.BooleanField(default=True)
    show_score_immediately = models.BooleanField(default=True)
    allow_review_before_submit = models.BooleanField(default=True)
    prevent_backtracking = models.BooleanField(default=False)

    # Availability
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)
    is_proctored = models.BooleanField(default=False)

    # Statistics
    attempt_count = models.PositiveIntegerField(default=0)
    average_score = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)

    # Rewards
    xp_reward = models.PositiveIntegerField(default=100)
    certificate_required = models.BooleanField(default=False)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        unique_together = [("course", "slug"), ("lesson", "slug"), ("module", "slug")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["assessment_type", "course"]),
            models.Index(fields=["available_from", "available_until"]),
        ]
        verbose_name = _("Assessment")
        verbose_name_plural = _("Assessments")

    def __str__(self):
        return f"{self.assessment_type.capitalize()}: {self.title}"

    @property
    def questions_count(self):
        return self.assessmentquestion_set.filter(question__is_active=True).count()

    def calculate_total_points(self):
        """Calculate total points from all questions"""
        total = sum([aq.points for aq in self.assessmentquestion_set.all()])
        if self.total_points != total:
            self.total_points = total
            self.save(update_fields=["total_points"])
        return total


# AssessmentQuestion through model for additional question metadata in assessments
class AssessmentQuestion(BaseModel):
    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=1)
    points = models.PositiveIntegerField(default=1)
    is_mandatory = models.BooleanField(default=True)
    weight = models.FloatField(default=1.0)  # For weighted scoring

    class Meta(BaseModel.Meta):
        unique_together = [("assessment", "question"), ("assessment", "order")]
        ordering = ["order"]

    def __str__(self):
        return f"{self.question} in {self.assessment}"


# UserAssessmentAttempt model
class UserAssessmentAttempt(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="assessment_attempts",
    )
    assessment = models.ForeignKey(
        Assessment, on_delete=models.CASCADE, related_name="user_attempts"
    )
    attempt_number = models.PositiveIntegerField(default=1)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Scoring
    score = models.FloatField(default=0.0, db_index=True)
    max_score = models.FloatField(default=0.0)
    percentage_score = models.FloatField(default=0.0, db_index=True)
    grade = models.CharField(max_length=5, blank=True)
    passed = models.BooleanField(default=False, db_index=True)

    # Timing
    completion_time_seconds = models.PositiveIntegerField(default=0)
    time_limit_exceeded = models.BooleanField(default=False)

    # Status
    STATUS_CHOICES = [
        ("in_progress", _("In Progress")),
        ("completed", _("Completed")),
        ("submitted", _("Submitted")),
        ("graded", _("Graded")),
        ("abandoned", _("Abandoned")),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="in_progress", db_index=True
    )

    # Relations
    responses = models.ManyToManyField(
        UserResponse, related_name="assessment_attempts", blank=True
    )

    # Proctoring
    preferences = models.JSONField(default=dict, blank=True)
    integrity_flags = models.JSONField(default=list, blank=True)

    # Context
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "assessment", "attempt_number")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "assessment", "passed", "score"]),
            models.Index(fields=["status", "started_at"]),
        ]
        verbose_name = _("User Assessment Attempt")
        verbose_name_plural = _("User Assessment Attempts")

    def __str__(self):
        return f"Attempt {self.attempt_number} by {self.user} on {self.assessment} (Score: {self.score})"

    def calculate_score(self):
        """Calculate and update the attempt score"""
        total_score = 0
        max_possible = 0
        for response in self.responses.all():
            total_score += response.score
            max_possible += response.max_score

        self.score = total_score
        self.max_score = max_possible
        self.percentage_score = (
            (total_score / max_possible * 100) if max_possible > 0 else 0
        )
        self.passed = self.percentage_score >= self.assessment.passing_score

        # Calculate grade based on boundaries
        for grade, threshold in sorted(
            self.assessment.grade_boundaries.items(), key=lambda x: x[1], reverse=True
        ):
            if self.percentage_score >= threshold:
                self.grade = grade
                break

        self.save(
            update_fields=["score", "max_score", "percentage_score", "passed", "grade"]
        )


# Progress model with granular tracking
class UserProgress(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_progress_records",
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="user_progress",
        null=True,
        blank=True,
    )
    module = models.ForeignKey(
        Module,
        on_delete=models.CASCADE,
        related_name="user_progress",
        null=True,
        blank=True,
    )
    lesson = models.ForeignKey(
        Lesson,
        on_delete=models.CASCADE,
        related_name="user_progress",
        null=True,
        blank=True,
    )
    step = models.ForeignKey(
        Step,
        on_delete=models.CASCADE,
        related_name="user_progress",
        null=True,
        blank=True,
    )
    assessment = models.ForeignKey(
        Assessment,
        on_delete=models.CASCADE,
        related_name="user_progress",
        null=True,
        blank=True,
    )

    # Progress tracking
    completion_percentage = models.PositiveIntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        db_index=True,
    )
    is_completed = models.BooleanField(default=False, db_index=True)
    last_accessed = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    first_accessed = models.DateTimeField(null=True, blank=True)

    # Performance metrics
    total_time_spent_seconds = models.PositiveBigIntegerField(default=0)
    average_score = models.FloatField(default=0.0)
    best_score = models.FloatField(default=0.0)
    attempts_count = models.PositiveIntegerField(default=0)

    # Gamification
    xp_earned = models.PositiveBigIntegerField(default=0, db_index=True)
    streak_days = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    # Personalization
    difficulty_preference = models.IntegerField(
        default=0, validators=[MinValueValidator(-2), MaxValueValidator(2)]
    )
    learning_style_data = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)  # User personal notes
    bookmarked = models.BooleanField(default=False)

    # Analytics
    interaction_count = models.PositiveIntegerField(default=0)
    help_requests_count = models.PositiveIntegerField(default=0)
    mistakes_made = models.PositiveIntegerField(default=0)

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(
                fields=["user", "course", "completion_percentage", "xp_earned"]
            ),
            models.Index(fields=["is_completed", "completed_at"]),
            models.Index(fields=["last_accessed", "streak_days"]),
        ]
        verbose_name = _("User Progress")
        verbose_name_plural = _("User Progresses")

    def __str__(self):
        return f"Progress of {self.user} in {self.course or self.module or self.lesson} ({self.completion_percentage}%)"

    def update_streak(self):
        """Update learning streak based on activity"""
        from django.utils import timezone

        today = timezone.now().date()
        yesterday = today - timezone.timedelta(days=1)

        # Check if user was active yesterday
        if self.last_accessed.date() == yesterday:
            self.current_streak += 1
        elif self.last_accessed.date() != today:
            self.current_streak = 1

        if self.current_streak > self.longest_streak:
            self.longest_streak = self.current_streak

        self.save(update_fields=["current_streak", "longest_streak"])


# SpacedRepetition model for review scheduling
class SpacedRepetition(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="spaced_repetitions",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    review_item = GenericForeignKey("content_type", "object_id")

    # Spaced repetition algorithm data
    last_reviewed = models.DateTimeField(null=True, blank=True)
    next_review = models.DateTimeField(null=True, blank=True, db_index=True)
    ease_factor = models.FloatField(default=2.5)
    interval_days = models.PositiveIntegerField(default=1)
    repetition_count = models.PositiveIntegerField(default=0)
    consecutive_correct = models.PositiveIntegerField(default=0)

    # Performance tracking
    average_response_time = models.PositiveIntegerField(default=0)
    difficulty_rating = models.FloatField(default=0.0)
    success_rate = models.FloatField(default=0.0)

    # Status
    is_due = models.BooleanField(default=True, db_index=True)
    is_learning = models.BooleanField(default=True)
    is_mature = models.BooleanField(default=False)  # Card that has been learned well

    # Algorithm type
    ALGORITHM_CHOICES = [
        ("sm2", "SuperMemo 2"),
        ("anki", "Anki Algorithm"),
        ("fsrs", "Free Spaced Repetition Scheduler"),
    ]
    algorithm = models.CharField(
        max_length=10, choices=ALGORITHM_CHOICES, default="sm2"
    )

    class Meta(BaseModel.Meta):
        unique_together = [("user", "content_type", "object_id")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "next_review", "is_due"]),
            models.Index(fields=["is_learning", "is_mature"]),
        ]
        verbose_name = _("Spaced Repetition")
        verbose_name_plural = _("Spaced Repetitions")

    def __str__(self):
        return f"SR for {self.review_item} by {self.user}"

    def update_schedule(self, quality_rating):
        """Update the review schedule based on SM-2 algorithm"""
        from django.utils import timezone

        if quality_rating >= 3:  # Correct response
            if self.repetition_count == 0:
                self.interval_days = 1
            elif self.repetition_count == 1:
                self.interval_days = 6
            else:
                self.interval_days = int(self.interval_days * self.ease_factor)

            self.repetition_count += 1
            self.consecutive_correct += 1
        else:  # Incorrect response
            self.repetition_count = 0
            self.interval_days = 1
            self.consecutive_correct = 0

        # Update ease factor
        self.ease_factor = max(
            1.3,
            self.ease_factor
            + 0.1
            - (5 - quality_rating) * (0.08 + (5 - quality_rating) * 0.02),
        )

        # Set next review date
        self.last_reviewed = timezone.now()
        self.next_review = timezone.now() + timezone.timedelta(days=self.interval_days)
        self.is_due = False
        self.is_mature = self.interval_days >= 21

        self.save()


# Achievement model with criteria
class Achievement(BaseModel):
    RARITY_CHOICES = [
        ("common", _("Common")),
        ("uncommon", _("Uncommon")),
        ("rare", _("Rare")),
        ("epic", _("Epic")),
        ("legendary", _("Legendary")),
    ]

    CATEGORY_CHOICES = [
        ("progress", _("Progress")),
        ("performance", _("Performance")),
        ("social", _("Social")),
        ("streak", _("Streak")),
        ("exploration", _("Exploration")),
        ("mastery", _("Mastery")),
        ("challenge", _("Challenge")),
    ]

    name = models.CharField(max_length=100, unique=True, db_index=True)
    description = models.TextField()
    short_description = models.CharField(max_length=200, blank=True)
    category = models.CharField(
        max_length=50, choices=CATEGORY_CHOICES, default="progress", db_index=True
    )

    # Visual
    icon_name = models.CharField(max_length=50, blank=True)
    icon_url = models.URLField(max_length=500, blank=True)
    badge_color = models.CharField(max_length=7, default="#FFD700")  # Hex color

    # Rewards
    xp_reward = models.PositiveIntegerField(default=100)
    bonus_rewards = models.JSONField(
        default=dict, blank=True
    )  # Additional rewards like course unlocks

    # Criteria and conditions
    criteria = models.JSONField(
        default=dict
    )  # e.g., {'courses_completed': 5, 'min_score': 90}
    prerequisites = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="unlocked_achievements"
    )

    # Metadata
    rarity = models.CharField(
        max_length=20, choices=RARITY_CHOICES, default="common", db_index=True
    )
    is_secret = models.BooleanField(default=False)  # Hidden until unlocked
    is_repeatable = models.BooleanField(default=False)
    unlock_count = models.PositiveIntegerField(default=0)

    # Availability
    available_from = models.DateTimeField(null=True, blank=True)
    available_until = models.DateTimeField(null=True, blank=True)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["category", "rarity"]),
            models.Index(fields=["is_secret", "available_from"]),
        ]
        verbose_name = _("Achievement")
        verbose_name_plural = _("Achievements")

    def __str__(self):
        return self.name

    def check_criteria(self, user):
        """Check if user meets the achievement criteria"""
        # This will be implemented based on specific criteria types
        # For now, return False as a placeholder
        return False


# UserAchievement model
class UserAchievement(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_achievements",
    )
    achievement = models.ForeignKey(
        Achievement, on_delete=models.CASCADE, related_name="unlocked_by"
    )
    unlocked_at = models.DateTimeField(auto_now_add=True)
    progress_data = models.JSONField(
        default=dict, blank=True
    )  # Track progress towards achievement
    notification_sent = models.BooleanField(default=False)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "achievement")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "unlocked_at"]),
            models.Index(fields=["achievement", "unlocked_at"]),
        ]
        verbose_name = _("User Achievement")
        verbose_name_plural = _("User Achievements")

    def __str__(self):
        return f"{self.user} unlocked {self.achievement}"


# Certificate model
class Certificate(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="certificates"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="certificates"
    )
    issued_at = models.DateTimeField(auto_now_add=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    expiration_date = models.DateTimeField(null=True, blank=True)

    # Verification
    verification_code = models.CharField(max_length=50, unique=True, db_index=True)
    verification_url = models.URLField(max_length=500, blank=True)

    # Performance data
    final_score = models.FloatField(db_index=True)
    completion_time_hours = models.PositiveIntegerField(default=0)
    grade = models.CharField(max_length=5, blank=True)

    # Certificate details
    certificate_template = models.CharField(max_length=100, default="standard")
    issuer_name = models.CharField(max_length=200, blank=True)
    issuer_signature_url = models.URLField(max_length=500, blank=True)

    # Files
    pdf_file = models.FileField(upload_to="certificates/", blank=True, null=True)
    pdf_url = models.URLField(max_length=500, blank=True)

    # Status
    is_revoked = models.BooleanField(default=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revocation_reason = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "course")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "course", "issued_at"]),
            models.Index(fields=["verification_code"]),
            models.Index(fields=["is_revoked", "expiration_date"]),
        ]
        verbose_name = _("Certificate")
        verbose_name_plural = _("Certificates")

    def __str__(self):
        return f"Certificate for {self.user} in {self.course}"

    def is_valid(self):
        """Check if certificate is currently valid"""
        from django.utils import timezone

        now = timezone.now()

        if self.is_revoked:
            return False

        if self.expiration_date and now > self.expiration_date:
            return False

        if self.valid_from and now < self.valid_from:
            return False

        return True


# Translation model
class Translation(BaseModel):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    translatable_object = GenericForeignKey("content_type", "object_id")
    language = models.ForeignKey(
        Language, on_delete=models.CASCADE, related_name="translations"
    )

    # Translation fields
    translated_title = models.CharField(max_length=255, blank=True)
    translated_description = models.TextField(blank=True)
    translated_text = models.TextField(blank=True)
    grade_boundaries = models.JSONField(default=dict, blank=True)

    # Translation metadata
    translator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="translations",
    )
    is_ai_translated = models.BooleanField(default=False)
    translation_service = models.CharField(
        max_length=50, blank=True
    )  # e.g., 'google', 'deepl'
    confidence_score = models.FloatField(default=0.0)

    # Quality control
    is_reviewed = models.BooleanField(default=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_translations",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    quality_score = models.FloatField(default=0.0)

    class Meta(BaseModel.Meta):
        unique_together = [("content_type", "object_id", "language")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["content_type", "object_id", "language"]),
            models.Index(fields=["is_ai_translated", "is_reviewed"]),
        ]
        verbose_name = _("Translation")
        verbose_name_plural = _("Translations")

    def __str__(self):
        return f"Translation for {self.translatable_object} in {self.language}"


# Feedback model
class Feedback(BaseModel):
    FEEDBACK_TYPES = [
        ("content", _("Content Feedback")),
        ("bug", _("Bug Report")),
        ("suggestion", _("Suggestion")),
        ("difficulty", _("Difficulty Feedback")),
        ("translation", _("Translation Issue")),
        ("accessibility", _("Accessibility Issue")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_feedback_given",
    )
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    feedback_object = GenericForeignKey("content_type", "object_id")

    # Feedback content
    feedback_type = models.CharField(
        max_length=50, choices=FEEDBACK_TYPES, default="content", db_index=True
    )
    rating = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        null=True,
        blank=True,
        db_index=True,
    )
    comment = models.TextField(blank=True)
    suggestions = models.TextField(blank=True)

    # Categorization
    categories = models.JSONField(default=list, blank=True)
    severity = models.CharField(
        max_length=20,
        choices=[("low", "Low"), ("medium", "Medium"), ("high", "High")],
        default="medium",
    )

    # Status and resolution
    STATUS_CHOICES = [
        ("open", _("Open")),
        ("in_review", _("In Review")),
        ("resolved", _("Resolved")),
        ("closed", _("Closed")),
        ("duplicate", _("Duplicate")),
    ]
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="open", db_index=True
    )
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_feedback",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

    # Community interaction
    is_helpful = models.BooleanField(default=True, db_index=True)
    helpful_votes = models.PositiveIntegerField(default=0)
    unhelpful_votes = models.PositiveIntegerField(default=0)
    reported_count = models.PositiveIntegerField(default=0)
    is_moderated = models.BooleanField(default=False)

    # Context
    user_progress_context = models.JSONField(
        default=dict, blank=True
    )  # User's progress when feedback was given
    metadata = models.JSONField(default=dict, blank=True)

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["content_type", "object_id", "rating"]),
            models.Index(fields=["feedback_type", "status", "severity"]),
            models.Index(fields=["is_helpful", "helpful_votes"]),
        ]
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedbacks")

    def __str__(self):
        return (
            f"Feedback by {self.user} on {self.feedback_object} (Rating: {self.rating})"
        )


# DiscussionThread model for community
class DiscussionThread(BaseModel):
    THREAD_TYPES = [
        ("general", _("General Discussion")),
        ("question", _("Question")),
        ("study_group", _("Study Group")),
        ("announcement", _("Announcement")),
        ("feedback", _("Feedback")),
    ]

    title = models.CharField(max_length=255, db_index=True)
    slug = models.SlugField(max_length=255, blank=True)
    thread_type = models.CharField(
        max_length=50, choices=THREAD_TYPES, default="general", db_index=True
    )
    description = models.TextField(blank=True)

    # Relations
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.UUIDField()
    associated_object = GenericForeignKey("content_type", "object_id")
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="discussion_threads",
    )

    # Thread management
    moderators = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="moderated_threads"
    )
    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="subscribed_threads"
    )

    # Statistics
    posts_count = models.PositiveIntegerField(default=0, db_index=True)
    views_count = models.PositiveIntegerField(default=0)
    participants_count = models.PositiveIntegerField(default=0)
    last_post_at = models.DateTimeField(null=True, blank=True)
    last_post_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="last_posts",
    )

    # Status and visibility
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_locked = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    visibility = models.CharField(
        max_length=20,
        choices=[
            ("public", "Public"),
            ("private", "Private"),
            ("restricted", "Restricted"),
        ],
        default="public",
    )

    # Content moderation
    is_moderated = models.BooleanField(default=False)
    reported_count = models.PositiveIntegerField(default=0)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(
                fields=["content_type", "object_id", "is_pinned", "last_post_at"]
            ),
            models.Index(fields=["thread_type", "visibility"]),
            models.Index(fields=["creator", "created_at"]),
        ]
        verbose_name = _("Discussion Thread")
        verbose_name_plural = _("Discussion Threads")

    def __str__(self):
        return self.title

    def update_stats(self):
        """Update thread statistics"""
        posts = self.posts.filter(is_active=True)
        self.posts_count = posts.count()
        if posts.exists():
            latest_post = posts.latest("created_at")
            self.last_post_at = latest_post.created_at
            self.last_post_by = latest_post.author
            self.participants_count = posts.values("author").distinct().count()
        self.save(
            update_fields=[
                "posts_count",
                "last_post_at",
                "last_post_by",
                "participants_count",
            ]
        )


# DiscussionPost model
class DiscussionPost(BaseModel):
    thread = models.ForeignKey(
        DiscussionThread, on_delete=models.CASCADE, related_name="posts"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="discussion_posts",
    )
    content = models.TextField()
    parent_post = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )

    # Formatting and media
    content_format = models.CharField(
        max_length=20,
        choices=[("markdown", "Markdown"), ("html", "HTML"), ("plain", "Plain Text")],
        default="markdown",
    )
    attachments = models.JSONField(default=list, blank=True)  # File attachments

    # Interaction
    likes = models.PositiveIntegerField(default=0, db_index=True)
    dislikes = models.PositiveIntegerField(default=0)
    replies_count = models.PositiveIntegerField(default=0)

    # Editing and versioning
    is_edited = models.BooleanField(default=False)
    edit_history = models.JSONField(default=list, blank=True)
    original_content = models.TextField(blank=True)

    # Moderation
    is_flagged = models.BooleanField(default=False)
    flagged_count = models.PositiveIntegerField(default=0)
    is_approved = models.BooleanField(default=True)
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="moderated_posts",
    )

    # Helpful/solution marking
    is_solution = models.BooleanField(default=False)
    helpful_votes = models.PositiveIntegerField(default=0)

    translations = GenericRelation("Translation")

    class Meta(BaseModel.Meta):
        ordering = ["created_at"]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["thread", "created_at"]),
            models.Index(fields=["author", "created_at"]),
            models.Index(fields=["is_solution", "helpful_votes"]),
        ]
        verbose_name = _("Discussion Post")
        verbose_name_plural = _("Discussion Posts")

    def __str__(self):
        return f"Post in {self.thread} by {self.author}"

    @property
    def depth_level(self):
        """Calculate nesting depth of the post"""
        depth = 0
        parent = self.parent_post
        while parent:
            depth += 1
            parent = parent.parent_post
        return depth


# Leaderboard model
class LeaderboardEntry(BaseModel):
    LEADERBOARD_TYPES = [
        ("global", _("Global")),
        ("course", _("Course")),
        ("weekly", _("Weekly")),
        ("monthly", _("Monthly")),
        ("friends", _("Friends")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="leaderboard_entries",
    )
    leaderboard_type = models.CharField(
        max_length=20, choices=LEADERBOARD_TYPES, default="global", db_index=True
    )
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="leaderboard",
        null=True,
        blank=True,
    )

    # Metrics
    total_xp = models.PositiveBigIntegerField(default=0, db_index=True)
    current_rank = models.PositiveIntegerField(default=0, db_index=True)
    previous_rank = models.PositiveIntegerField(default=0)
    rank_change = models.IntegerField(default=0)  # Can be negative

    # Additional statistics
    achievements_count = models.PositiveIntegerField(default=0)
    courses_completed = models.PositiveIntegerField(default=0)
    lessons_completed = models.PositiveIntegerField(default=0)
    current_streak = models.PositiveIntegerField(default=0)
    longest_streak = models.PositiveIntegerField(default=0)

    # Time periods for weekly/monthly leaderboards
    period_start = models.DateTimeField(null=True, blank=True)
    period_end = models.DateTimeField(null=True, blank=True)

    # Metadata
    last_updated = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "leaderboard_type", "course", "period_start")]
        ordering = ["-total_xp"]
        indexes = BaseModel.Meta.indexes + [
            models.Index(
                fields=["leaderboard_type", "course", "total_xp", "current_rank"]
            ),
            models.Index(fields=["period_start", "period_end"]),
        ]
        verbose_name = _("Leaderboard Entry")
        verbose_name_plural = _("Leaderboard Entries")

    def __str__(self):
        return f"{self.user} - Rank {self.current_rank} ({self.total_xp} XP)"

    def calculate_rank_change(self):
        """Calculate rank change from previous position"""
        self.rank_change = self.previous_rank - self.current_rank
        self.save(update_fields=["rank_change"])


# Recommendation model for personalized suggestions
class Recommendation(BaseModel):
    RECOMMENDATION_TYPES = [
        ("course", _("Course")),
        ("lesson", _("Lesson")),
        ("vocabulary", _("Vocabulary")),
        ("grammar", _("Grammar")),
        ("practice", _("Practice")),
        ("review", _("Review")),
    ]

    RECOMMENDATION_SOURCES = [
        ("ai", _("AI Algorithm")),
        ("collaborative", _("Collaborative Filtering")),
        ("content_based", _("Content-Based")),
        ("popularity", _("Popularity-Based")),
        ("instructor", _("Instructor Recommended")),
        ("peer", _("Peer Recommended")),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="recommendations",
    )
    recommended_type = models.CharField(
        max_length=50, choices=RECOMMENDATION_TYPES, db_index=True
    )
    recommended_id = models.UUIDField()
    source = models.CharField(
        max_length=50, choices=RECOMMENDATION_SOURCES, default="ai", db_index=True
    )

    # Scoring and ranking
    score = models.FloatField(default=0.0, db_index=True)
    confidence = models.FloatField(default=0.0)
    relevance_score = models.FloatField(default=0.0)

    # Reasoning and explanation
    reason = models.TextField(blank=True)
    explanation_data = models.JSONField(default=dict, blank=True)
    factors = models.JSONField(default=list, blank=True)

    # Timing and context
    generated_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    context = models.JSONField(default=dict, blank=True)  # User context when generated

    # User interaction
    is_viewed = models.BooleanField(default=False)
    viewed_at = models.DateTimeField(null=True, blank=True)
    is_clicked = models.BooleanField(default=False)
    clicked_at = models.DateTimeField(null=True, blank=True)
    is_dismissed = models.BooleanField(default=False)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    # Feedback
    user_rating = models.IntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    feedback_text = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "score", "generated_at"]),
            models.Index(fields=["recommended_type", "source"]),
            models.Index(fields=["expires_at", "is_dismissed"]),
        ]
        verbose_name = _("Recommendation")
        verbose_name_plural = _("Recommendations")

    def __str__(self):
        return f"Recommendation for {self.user} ({self.recommended_type})"

    @property
    def is_expired(self):
        """Check if recommendation has expired"""
        from django.utils import timezone

        return self.expires_at and timezone.now() > self.expires_at


# UserSettings model for personalization
class UserSettings(BaseModel):
    LEARNING_STYLES = [
        ("visual", _("Visual")),
        ("auditory", _("Auditory")),
        ("kinesthetic", _("Kinesthetic")),
        ("reading", _("Reading/Writing")),
        ("mixed", _("Mixed")),
    ]

    DIFFICULTY_PREFERENCES = [
        ("easy", _("Prefer Easier Content")),
        ("balanced", _("Balanced")),
        ("challenging", _("Prefer Challenging Content")),
        ("adaptive", _("Adaptive to Performance")),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_settings",
    )

    # Language preferences
    preferred_base_language = models.ForeignKey(
        Language, on_delete=models.SET_NULL, null=True, related_name="preferred_by"
    )
    ui_language = models.ForeignKey(
        Language, on_delete=models.SET_NULL, null=True, related_name="ui_language_users"
    )

    # Learning preferences
    learning_style = models.CharField(
        max_length=50, choices=LEARNING_STYLES, default="mixed"
    )
    difficulty_preference = models.CharField(
        max_length=50, choices=DIFFICULTY_PREFERENCES, default="balanced"
    )
    daily_goal_minutes = models.PositiveIntegerField(default=15)
    weekly_goal_lessons = models.PositiveIntegerField(default=5)

    # Study schedule
    preferred_study_times = models.JSONField(
        default=list, blank=True
    )  # ['morning', 'evening']
    timezone = models.CharField(max_length=50, default="UTC")
    reminder_enabled = models.BooleanField(default=True)
    reminder_time = models.TimeField(null=True, blank=True)

    # Notification preferences
    notification_preferences = models.JSONField(default=dict, blank=True)
    email_notifications = models.BooleanField(default=True)
    push_notifications = models.BooleanField(default=True)
    achievement_notifications = models.BooleanField(default=True)

    # Learning features
    enable_spaced_repetition = models.BooleanField(default=True)
    enable_adaptive_difficulty = models.BooleanField(default=True)
    enable_ai_recommendations = models.BooleanField(default=True)
    enable_gamification = models.BooleanField(default=True)

    # Accessibility
    accessibility_preferences = models.JSONField(default=dict, blank=True)
    high_contrast_mode = models.BooleanField(default=False)
    large_text_mode = models.BooleanField(default=False)
    screen_reader_mode = models.BooleanField(default=False)

    # Privacy
    profile_visibility = models.CharField(
        max_length=20,
        choices=[("public", "Public"), ("friends", "Friends"), ("private", "Private")],
        default="public",
    )
    show_in_leaderboards = models.BooleanField(default=True)
    allow_friend_requests = models.BooleanField(default=True)

    class Meta(BaseModel.Meta):
        verbose_name = _("User Settings")
        verbose_name_plural = _("User Settings")

    def __str__(self):
        return f"Settings for {self.user}"


# Analytics model for user performance tracking
class UserAnalytics(BaseModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="course_analytics",
    )
    date = models.DateField(db_index=True)
    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="user_analytics",
    )

    # Time tracking
    total_time_spent_minutes = models.PositiveIntegerField(default=0)
    active_learning_minutes = models.PositiveIntegerField(default=0)
    passive_learning_minutes = models.PositiveIntegerField(default=0)

    # Progress metrics
    lessons_started = models.PositiveIntegerField(default=0)
    lessons_completed = models.PositiveIntegerField(default=0)
    steps_completed = models.PositiveIntegerField(default=0)
    questions_answered = models.PositiveIntegerField(default=0)
    correct_answers = models.PositiveIntegerField(default=0)

    # Performance metrics
    xp_gained = models.PositiveIntegerField(default=0)
    accuracy_percentage = models.FloatField(default=0.0)
    average_response_time = models.FloatField(default=0.0)
    completion_rate = models.FloatField(default=0.0)

    # Skills and content
    skills_improved = models.JSONField(default=list, blank=True)
    content_types_engaged = models.JSONField(default=list, blank=True)
    vocabulary_learned = models.PositiveIntegerField(default=0)
    grammar_rules_practiced = models.PositiveIntegerField(default=0)

    # Engagement metrics
    login_count = models.PositiveIntegerField(default=0)
    session_count = models.PositiveIntegerField(default=0)
    streak_maintained = models.BooleanField(default=False)
    achievements_unlocked = models.PositiveIntegerField(default=0)

    # Social interaction
    discussions_participated = models.PositiveIntegerField(default=0)
    feedback_given = models.PositiveIntegerField(default=0)
    help_requests = models.PositiveIntegerField(default=0)

    # Device and context
    primary_device_type = models.CharField(max_length=50, blank=True)
    study_locations = models.JSONField(default=list, blank=True)

    class Meta(BaseModel.Meta):
        unique_together = [("user", "date", "course")]
        indexes = BaseModel.Meta.indexes + [
            models.Index(fields=["user", "date"]),
            models.Index(fields=["date", "course"]),
            models.Index(fields=["accuracy_percentage", "xp_gained"]),
        ]
        verbose_name = _("User Analytics")
        verbose_name_plural = _("User Analytics")

    def __str__(self):
        return f"Analytics for {self.user} on {self.date}"

    def calculate_metrics(self):
        """Calculate derived metrics from raw data"""
        if self.questions_answered > 0:
            self.accuracy_percentage = (
                self.correct_answers / self.questions_answered
            ) * 100

        if self.lessons_started > 0:
            self.completion_rate = (self.lessons_completed / self.lessons_started) * 100

        self.save(update_fields=["accuracy_percentage", "completion_rate"])


# Signal handlers for automated actions
@receiver(pre_save, sender=Course)
def course_pre_save(sender, instance, **kwargs):
    """Generate slug and handle course updates"""
    if not instance.slug:
        instance.slug = slugify(
            f"{instance.title}-{instance.target_language.code}-{instance.level}"
        )

    # Ensure unique slug
    original_slug = instance.slug
    counter = 1
    while Course.objects.filter(slug=instance.slug).exclude(id=instance.id).exists():
        instance.slug = f"{original_slug}-{counter}"
        counter += 1


@receiver(post_save, sender=Course)
def course_post_save(sender, instance, created, **kwargs):
    """Handle course creation and updates"""
    if created:
        # Create initial analytics entry
        from django.utils import timezone

        UserAnalytics.objects.get_or_create(
            user=instance.instructor,
            date=timezone.now().date(),
            course=instance,
        )


@receiver(pre_save, sender=Module)
def module_pre_save(sender, instance, **kwargs):
    """Generate module slug"""
    if not instance.slug:
        instance.slug = slugify(instance.title)


@receiver(pre_save, sender=Lesson)
def lesson_pre_save(sender, instance, **kwargs):
    """Generate lesson slug"""
    if not instance.slug:
        instance.slug = slugify(instance.title)


@receiver(pre_save, sender=Assessment)
def assessment_pre_save(sender, instance, **kwargs):
    """Generate assessment slug"""
    if not instance.slug:
        instance.slug = slugify(instance.title)


@receiver(pre_save, sender=DiscussionThread)
def thread_pre_save(sender, instance, **kwargs):
    """Generate thread slug"""
    if not instance.slug:
        instance.slug = slugify(instance.title)


@receiver(post_save, sender=UserResponse)
def user_response_post_save(sender, instance, created, **kwargs):
    """Update question analytics when response is saved"""
    if created:
        instance.question.update_analytics()


@receiver(post_save, sender=UserAssessmentAttempt)
def assessment_attempt_post_save(sender, instance, created, **kwargs):
    """Update assessment statistics"""
    if instance.status == "completed":
        assessment = instance.assessment
        attempts = assessment.user_attempts.filter(status="completed")

        if attempts.exists():
            assessment.attempt_count = attempts.count()
            assessment.average_score = (
                attempts.aggregate(avg=models.Avg("percentage_score"))["avg"] or 0
            )
            assessment.completion_rate = (
                attempts.filter(passed=True).count() / attempts.count()
            ) * 100
            assessment.save(
                update_fields=["attempt_count", "average_score", "completion_rate"]
            )


@receiver(post_save, sender=UserProgress)
def user_progress_post_save(sender, instance, created, **kwargs):
    """Handle progress updates"""
    if instance.is_completed and not instance.completed_at:
        from django.utils import timezone

        instance.completed_at = timezone.now()
        instance.save(update_fields=["completed_at"])

    # Update streak
    instance.update_streak()


@receiver(post_save, sender=DiscussionPost)
def discussion_post_post_save(sender, instance, created, **kwargs):
    """Update thread statistics when post is created/updated"""
    if created:
        instance.thread.update_stats()


@receiver(post_delete, sender=DiscussionPost)
def discussion_post_post_delete(sender, instance, **kwargs):
    """Update thread statistics when post is deleted"""
    instance.thread.update_stats()


@receiver(post_save, sender=UserAchievement)
def user_achievement_post_save(sender, instance, created, **kwargs):
    """Handle achievement unlocking"""
    if created:
        # Update achievement unlock count
        instance.achievement.unlock_count += 1
        instance.achievement.save(update_fields=["unlock_count"])

        # Award XP to user
        # This would typically be handled by a separate XP system


@receiver(pre_save, sender=Certificate)
def certificate_pre_save(sender, instance, **kwargs):
    """Generate verification code for certificates"""
    if not instance.verification_code:
        instance.verification_code = str(uuid.uuid4()).replace("-", "").upper()[:16]

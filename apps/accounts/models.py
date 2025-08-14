import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _
from guardian.mixins import GuardianUserMixin


class User(GuardianUserMixin, AbstractUser):
    """
    Custom User model with additional fields and Guardian permissions.
    """

    email = models.EmailField(
        _("email address"),
        unique=True,
        error_messages={"unique": _("A user with that email already exists.")},
    )
    phone_number = models.CharField(
        _("phone number"),
        max_length=15,
        blank=True,
        null=True,
        help_text=_(
            "Optional phone number in international format (e.g., +1234567890)."
        ),
    )
    bio = models.TextField(
        _("biography"),
        max_length=500,
        blank=True,
        help_text=_("Short user biography or description."),
    )
    date_of_birth = models.DateField(
        _("date of birth"),
        blank=True,
        null=True,
        help_text=_("Optional date of birth."),
    )
    is_verified = models.BooleanField(
        _("email verified"),
        default=False,
        help_text=_("Indicates if the user's email has been verified."),
    )
    profile_picture = models.ImageField(
        _("profile picture"),
        upload_to="profile_pictures/",
        blank=True,
        null=True,
        help_text=_("Optional profile picture."),
    )
    last_activity = models.DateTimeField(
        _("last activity"),
        blank=True,
        null=True,
        help_text=_("Timestamp of the user's last activity."),
    )

    is_staff = models.BooleanField(
        _("staff status"),
        default=False,
        help_text=_("Designates whether the user can log into the admin site."),
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    # Professional networking fields
    headline = models.CharField(
        _("professional headline"),
        max_length=220,
        blank=True,
        help_text=_("Professional headline or title"),
    )
    current_position = models.CharField(
        _("current position"),
        max_length=100,
        blank=True,
    )
    current_company = models.CharField(
        _("current company"),
        max_length=100,
        blank=True,
    )
    location = models.CharField(
        _("location"),
        max_length=100,
        blank=True,
    )
    timezone = models.CharField(
        _("timezone"),
        max_length=50,
        blank=True,
        default="UTC",
    )

    class UserStatus(models.TextChoices):
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")
        AWAY = "away", _("Away")
        BUSY = "busy", _("Busy")
        DO_NOT_DISTURB = "do-not-disturb", _("Do Not Disturb")
        SUSPENDED = "suspended", _("Suspended")
        PENDING = "pending", _("Pending")
        DELETED = "deleted", _("Deleted")
        ARCHIVED = "archived", _("Archived")

    status = models.CharField(
        max_length=20,
        choices=UserStatus.choices,
        default=UserStatus.ACTIVE,
    )
    is_online = models.BooleanField(default=False)

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["username"]

    def __str__(self):
        return self.username

    def save(self, *args, **kwargs):
        """Ensure email is stored in lowercase."""
        if self.email:
            self.email = self.email.lower()
        super().save(*args, **kwargs)

    def get_full_name(self):
        """Return the first_name plus the last_name, with a space in between."""
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or self.username

    def update_last_activity(self):
        """Update the last_activity timestamp."""
        from django.utils import timezone

        self.last_activity = timezone.now()
        self.save(update_fields=["last_activity"])


class UserProfile(models.Model):
    """Extended user profile with comprehensive professional information."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    display_name = models.CharField(
        _("display name"),
        max_length=100,
        blank=True,
    )
    bio = models.TextField(
        _("bio"),
        max_length=500,
        blank=True,
        help_text=_("Brief description about yourself"),
    )
    location = models.CharField(
        _("location"),
        max_length=100,
        blank=True,
    )
    current_position = models.CharField(
        _("current position"),
        max_length=100,
        blank=True,
    )
    industry = models.CharField(
        _("industry"),
        max_length=100,
        blank=True,
    )
    phone = models.CharField(
        _("phone number"),
        max_length=20,
        blank=True,
    )
    date_of_birth = models.DateField(
        _("date of birth"),
        null=True,
        blank=True,
    )
    profile_picture = models.ImageField(
        _("profile picture"),
        upload_to="profile_pictures/",
        blank=True,
        null=True,
    )
    cover_image = models.ImageField(
        _("cover image"),
        upload_to="cover_images/",
        blank=True,
        null=True,
    )
    website = models.URLField(
        _("website"),
        blank=True,
    )
    interests = models.JSONField(
        _("interests"),
        default=list,
        blank=True,
    )

    # Profile visibility settings
    class ProfileVisibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Private")
        CONNECTIONS_ONLY = "connections-only", _("Connections Only")

    profile_visibility = models.CharField(
        max_length=20,
        choices=ProfileVisibility.choices,
        default=ProfileVisibility.PUBLIC,
    )
    visibility = models.CharField(
        _("visibility"),
        max_length=20,
        choices=ProfileVisibility.choices,
        default=ProfileVisibility.PUBLIC,
        help_text=_("Alias for profile_visibility"),
    )

    # Privacy settings
    show_contact_info = models.BooleanField(default=True)
    show_email = models.BooleanField(
        _("show email"),
        default=True,
        help_text=_("Show email address in profile"),
    )
    show_phone = models.BooleanField(
        _("show phone"),
        default=True,
        help_text=_("Show phone number in profile"),
    )
    show_experience = models.BooleanField(default=True)
    show_education = models.BooleanField(default=True)
    show_skills = models.BooleanField(default=True)
    show_projects = models.BooleanField(default=True)
    show_achievements = models.BooleanField(default=True)
    show_publications = models.BooleanField(default=True)
    show_volunteer = models.BooleanField(default=True)
    allow_endorsements = models.BooleanField(default=True)
    allow_messages = models.BooleanField(default=True)
    allow_connections = models.BooleanField(default=True)
    show_last_seen = models.BooleanField(default=True)
    searchable = models.BooleanField(default=True)

    # Notification preferences
    email_notifications = models.JSONField(
        default=dict, help_text=_("Email notification preferences")
    )
    push_notifications = models.JSONField(
        default=dict, help_text=_("Push notification preferences")
    )

    # Account settings
    theme = models.CharField(
        max_length=10,
        choices=[
            ("light", _("Light")),
            ("dark", _("Dark")),
            ("system", _("System")),
        ],
        default="system",
    )
    language = models.CharField(max_length=10, default="en")
    date_format = models.CharField(
        max_length=15,
        choices=[
            ("MM/DD/YYYY", "MM/DD/YYYY"),
            ("DD/MM/YYYY", "DD/MM/YYYY"),
            ("YYYY-MM-DD", "YYYY-MM-DD"),
        ],
        default="YYYY-MM-DD",
    )
    time_format = models.CharField(
        max_length=3, choices=[("12h", "12h"), ("24h", "24h")], default="24h"
    )
    two_factor_enabled = models.BooleanField(default=False)
    login_alerts = models.BooleanField(default=True)

    # Privacy settings
    data_processing = models.BooleanField(default=True)
    analytics_tracking = models.BooleanField(default=True)
    personalized_ads = models.BooleanField(default=False)
    third_party_sharing = models.BooleanField(default=False)
    location_tracking = models.BooleanField(default=False)
    activity_tracking = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("user profile")
        verbose_name_plural = _("user profiles")

    def __str__(self):
        return f"{self.user.username}'s profile"


class SocialLink(models.Model):
    """Social media and web links for user profiles."""

    class Platform(models.TextChoices):
        LINKEDIN = "linkedin", _("LinkedIn")
        GITHUB = "github", _("GitHub")
        TWITTER = "twitter", _("Twitter")
        INSTAGRAM = "instagram", _("Instagram")
        FACEBOOK = "facebook", _("Facebook")
        YOUTUBE = "youtube", _("YouTube")
        WEBSITE = "website", _("Website")
        CUSTOM = "custom", _("Custom")

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="social_links"
    )
    platform = models.CharField(max_length=20, choices=Platform.choices)
    url = models.URLField()
    title = models.CharField(max_length=100, blank=True)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("social link")
        verbose_name_plural = _("social links")
        unique_together = [["user", "platform", "url"]]

    def __str__(self):
        return f"{self.user.username} - {self.platform}"


class Experience(models.Model):
    """Professional work experience."""

    class ExperienceType(models.TextChoices):
        WORK = "work", _("Work")
        INTERNSHIP = "internship", _("Internship")
        VOLUNTEER = "volunteer", _("Volunteer")
        FREELANCE = "freelance", _("Freelance")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="experiences")
    title = models.CharField(max_length=100)
    company = models.CharField(max_length=100)
    company_url = models.URLField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    achievements = models.JSONField(default=list, blank=True)
    type = models.CharField(
        max_length=20, choices=ExperienceType.choices, default=ExperienceType.WORK
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("experience")
        verbose_name_plural = _("experiences")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.title} at {self.company}"


class Education(models.Model):
    """Educational background."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="educations")
    institution = models.CharField(max_length=200)
    degree = models.CharField(max_length=100)
    field_of_study = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    gpa = models.CharField(max_length=10, blank=True)
    description = models.TextField(blank=True)
    achievements = models.JSONField(default=list, blank=True)
    activities = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("education")
        verbose_name_plural = _("educations")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.degree} at {self.institution}"


class Certification(models.Model):
    """Professional certifications."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=200)
    issuer = models.CharField(max_length=200)
    issue_date = models.DateField()
    expiration_date = models.DateField(blank=True, null=True)
    credential_id = models.CharField(max_length=100, blank=True)
    credential_url = models.URLField(blank=True)
    description = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("certification")
        verbose_name_plural = _("certifications")
        ordering = ["-issue_date"]

    def __str__(self):
        return f"{self.name} - {self.issuer}"


class Project(models.Model):
    """User projects and portfolio items."""

    class ProjectCategory(models.TextChoices):
        PERSONAL = "personal", _("Personal")
        PROFESSIONAL = "professional", _("Professional")
        ACADEMIC = "academic", _("Academic")
        OPEN_SOURCE = "open-source", _("Open Source")

    class ProjectStatus(models.TextChoices):
        COMPLETED = "completed", _("Completed")
        IN_PROGRESS = "in-progress", _("In Progress")
        ON_HOLD = "on-hold", _("On Hold")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="projects")
    title = models.CharField(max_length=200)
    description = models.TextField()
    thumbnail = models.ImageField(
        upload_to="project_thumbnails/", blank=True, null=True
    )
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    technologies = models.JSONField(default=list)
    role = models.CharField(max_length=100, blank=True)
    team_size = models.PositiveIntegerField(blank=True, null=True)
    category = models.CharField(
        max_length=20, choices=ProjectCategory.choices, default=ProjectCategory.PERSONAL
    )
    status = models.CharField(
        max_length=20, choices=ProjectStatus.choices, default=ProjectStatus.COMPLETED
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("project")
        verbose_name_plural = _("projects")
        ordering = ["-start_date"]

    def __str__(self):
        return self.title


class ProjectImage(models.Model):
    """Additional images for projects."""

    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to="project_images/")
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]


class Skill(models.Model):
    """User skills with endorsements."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="skills")
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50)
    level = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text=_("Skill level from 1 (Beginner) to 5 (Expert)"),
    )
    years_of_experience = models.PositiveIntegerField(blank=True, null=True)
    last_used = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("skill")
        verbose_name_plural = _("skills")
        unique_together = [["user", "name"]]

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    @property
    def is_endorsed(self):
        return self.endorsements.exists()

    @property
    def endorsement_count(self):
        return self.endorsements.count()


class SkillEndorsement(models.Model):
    """Skill endorsements from other users."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    skill = models.ForeignKey(
        Skill, on_delete=models.CASCADE, related_name="endorsements"
    )
    endorser = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="skill_endorsements_given"
    )
    message = models.TextField(blank=True, max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("skill endorsement")
        verbose_name_plural = _("skill endorsements")
        unique_together = [["skill", "endorser"]]

    def __str__(self):
        return f"{self.endorser.username} endorsed {self.skill.name}"


class Language(models.Model):
    """User language skills."""

    class Proficiency(models.TextChoices):
        NATIVE = "native", _("Native")
        FLUENT = "fluent", _("Fluent")
        CONVERSATIONAL = "conversational", _("Conversational")
        BASIC = "basic", _("Basic")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="languages")
    name = models.CharField(max_length=50)
    code = models.CharField(max_length=10)  # ISO language code
    proficiency = models.CharField(max_length=15, choices=Proficiency.choices)
    certifications = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("language")
        verbose_name_plural = _("languages")
        unique_together = [["user", "name"]]

    def __str__(self):
        return f"{self.user.username} - {self.name} ({self.proficiency})"


class Achievement(models.Model):
    """User achievements and awards."""

    class AchievementCategory(models.TextChoices):
        AWARD = "award", _("Award")
        RECOGNITION = "recognition", _("Recognition")
        PUBLICATION = "publication", _("Publication")
        PATENT = "patent", _("Patent")
        CERTIFICATION = "certification", _("Certification")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="achievements"
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    issuer = models.CharField(max_length=200, blank=True)
    date = models.DateField()
    category = models.CharField(
        max_length=20,
        choices=AchievementCategory.choices,
        default=AchievementCategory.AWARD,
    )
    url = models.URLField(blank=True)
    image = models.ImageField(upload_to="achievements/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("achievement")
        verbose_name_plural = _("achievements")
        ordering = ["-date"]

    def __str__(self):
        return self.title


class Publication(models.Model):
    """User publications and articles."""

    class PublicationCategory(models.TextChoices):
        ARTICLE = "article", _("Article")
        BOOK = "book", _("Book")
        RESEARCH = "research", _("Research")
        BLOG = "blog", _("Blog")
        WHITEPAPER = "whitepaper", _("Whitepaper")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="publications"
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    publisher = models.CharField(max_length=200)
    publication_date = models.DateField()
    url = models.URLField(blank=True)
    authors = models.JSONField(default=list)
    category = models.CharField(
        max_length=20,
        choices=PublicationCategory.choices,
        default=PublicationCategory.ARTICLE,
    )
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("publication")
        verbose_name_plural = _("publications")
        ordering = ["-publication_date"]

    def __str__(self):
        return self.title


class Volunteer(models.Model):
    """Volunteer work experience."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="volunteer_work"
    )
    organization = models.CharField(max_length=200)
    role = models.CharField(max_length=100)
    cause = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField(blank=True, null=True)
    is_current = models.BooleanField(default=False)
    description = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    hours_contributed = models.PositiveIntegerField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("volunteer work")
        verbose_name_plural = _("volunteer work")
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.role} at {self.organization}"


class Connection(models.Model):
    """Professional connections between users."""

    class ConnectionStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACCEPTED = "accepted", _("Accepted")
        DECLINED = "declined", _("Declined")
        BLOCKED = "blocked", _("Blocked")

    from_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="connections_sent"
    )
    to_user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="connections_received"
    )
    status = models.CharField(
        max_length=10,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.PENDING,
    )
    message = models.TextField(blank=True, max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("connection")
        verbose_name_plural = _("connections")
        unique_together = [["from_user", "to_user"]]

    def clean(self):
        """Validate that users cannot connect to themselves."""
        if self.from_user == self.to_user:
            raise ValidationError(_("Users cannot connect to themselves."))

    def __str__(self):
        return f"{self.from_user.username} -> {self.to_user.username} ({self.status})"


class Follow(models.Model):
    """User following relationships."""

    follower = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="following"
    )
    following = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="followers"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("follow")
        verbose_name_plural = _("follows")
        unique_together = [["follower", "following"]]

    def __str__(self):
        return f"{self.follower.username} follows {self.following.username}"


class ProfileView(models.Model):
    """Track profile views for analytics."""

    viewer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="profile_views_made",
        null=True,
        blank=True,
    )
    profile_owner = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="profile_views_received"
    )
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("profile view")
        verbose_name_plural = _("profile views")

    def __str__(self):
        viewer_name = self.viewer.username if self.viewer else "Anonymous"
        return f"{viewer_name} viewed {self.profile_owner.username}"


class UserFile(models.Model):
    """File attachments for users (resume, portfolio, etc.)."""

    class FileType(models.TextChoices):
        RESUME = "resume", _("Resume")
        PORTFOLIO = "portfolio", _("Portfolio")
        CERTIFICATE = "certificate", _("Certificate")
        DOCUMENT = "document", _("Document")
        OTHER = "other", _("Other")

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="files")
    file = models.FileField(upload_to="user_files/")
    name = models.CharField(max_length=200)
    file_type = models.CharField(
        max_length=20, choices=FileType.choices, default=FileType.OTHER
    )
    description = models.TextField(blank=True)
    is_public = models.BooleanField(default=False)
    size = models.PositiveIntegerField()  # File size in bytes
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("user file")
        verbose_name_plural = _("user files")

    def __str__(self):
        return f"{self.user.username} - {self.name}"

    def save(self, *args, **kwargs):
        if self.file:
            self.size = self.file.size
        super().save(*args, **kwargs)


class ActivityLog(models.Model):
    """Log user activities for analytics and audit."""

    class ActivityType(models.TextChoices):
        PROFILE_UPDATE = "profile_update", _("Profile Update")
        CONNECTION_REQUEST = "connection_request", _("Connection Request")
        CONNECTION_ACCEPT = "connection_accept", _("Connection Accept")
        ENDORSEMENT = "endorsement", _("Endorsement")
        PROJECT_UPDATE = "project_update", _("Project Update")
        SKILL_UPDATE = "skill_update", _("Skill Update")
        LOGIN = "login", _("Login")
        PASSWORD_CHANGE = "password_change", _("Password Change")
        PROFILE_VIEW = "profile_view", _("Profile View")
        RESUME_CREATED = "resume_created", _("Resume Created")
        RESUME_UPDATED = "resume_updated", _("Resume Updated")
        RESUME_DELETED = "resume_deleted", _("Resume Deleted")
        RESUME_PUBLISHED = "resume_published", _("Resume Published")
        RESUME_DOWNLOADED = "resume_downloaded", _("Resume Downloaded")
        RESUME_GENERATED = "resume_generated", _("Resume Generated")
        RECOMMENDATION_GIVEN = "recommendation_given", _("Recommendation Given")
        RECOMMENDATION_RECEIVED = (
            "recommendation_received",
            _("Recommendation Received"),
        )
        RECOMMENDATION_UPDATED = "recommendation_updated", _("Recommendation Updated")
        RECOMMENDATION_DELETED = "recommendation_deleted", _("Recommendation Deleted")
        RECOMMENDATION_APPROVED = (
            "recommendation_approved",
            _("Recommendation Approved"),
        )
        RECOMMENDATION_DECLINED = (
            "recommendation_declined",
            _("Recommendation Declined"),
        )
        RECOMMENDATION_REQUESTED = (
            "recommendation_requested",
            _("Recommendation Requested"),
        )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="activity_logs"
    )
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)
    description = models.CharField(max_length=200)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.TextField(blank=True)
    location = models.CharField(max_length=100, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("activity log")
        verbose_name_plural = _("activity logs")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.username} - {self.activity_type.upper()}"


# Signal to create profile when user is created


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, "profile"):
        instance.profile.save()


class Role(models.Model):
    """User roles for role-based access control."""

    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    is_system_role = models.BooleanField(default=False)
    permissions = models.ManyToManyField(
        "auth.Permission", blank=True, related_name="custom_roles"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("role")
        verbose_name_plural = _("roles")

    def __str__(self):
        return self.name


class UserRole(models.Model):
    """User role assignments with optional expiration."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="user_roles")
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="user_assignments"
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="role_assignments_made",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("user role")
        verbose_name_plural = _("user roles")
        unique_together = [["user", "role"]]

    def __str__(self):
        return f"{self.user.username} - {self.role.name}"


class Department(models.Model):
    """Organizational departments."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="sub_departments",
    )
    head = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="departments_headed",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("department")
        verbose_name_plural = _("departments")

    def __str__(self):
        return self.name


class UserDepartment(models.Model):
    """User department assignments."""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="departments")
    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="members"
    )
    position = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("user department")
        verbose_name_plural = _("user departments")
        unique_together = [["user", "department"]]

    def __str__(self):
        return f"{self.user.username} in {self.department.name}"


class Task(models.Model):
    """Task management system."""

    class TaskStatus(models.TextChoices):
        TODO = "todo", _("To Do")
        IN_PROGRESS = "in_progress", _("In Progress")
        REVIEW = "review", _("Under Review")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")

    class TaskPriority(models.TextChoices):
        LOW = "low", _("Low")
        MEDIUM = "medium", _("Medium")
        HIGH = "high", _("High")
        URGENT = "urgent", _("Urgent")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="assigned_tasks"
    )
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="created_tasks"
    )
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="tasks", null=True, blank=True
    )
    status = models.CharField(
        max_length=20, choices=TaskStatus.choices, default=TaskStatus.TODO
    )
    priority = models.CharField(
        max_length=10, choices=TaskPriority.choices, default=TaskPriority.MEDIUM
    )
    due_date = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    estimated_hours = models.PositiveIntegerField(null=True, blank=True)
    actual_hours = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    watchers = models.ManyToManyField(User, blank=True, related_name="watched_tasks")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("task")
        verbose_name_plural = _("tasks")
        ordering = ["-created_at"]

    def __str__(self):
        return self.title


class TaskComment(models.Model):
    """Comments on tasks."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="comments")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("task comment")
        verbose_name_plural = _("task comments")
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment on {self.task.title} by {self.user.username}"


class Resume(models.Model):
    """User resume/CV management."""

    class ResumeStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        ACTIVE = "active", _("Active")
        ARCHIVED = "archived", _("Archived")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="resumes")
    title = models.CharField(max_length=200)
    template = models.CharField(max_length=50, default="default")
    content = models.JSONField(default=dict)  # Structured resume data
    file = models.FileField(upload_to="resumes/", blank=True, null=True)
    status = models.CharField(
        max_length=10, choices=ResumeStatus.choices, default=ResumeStatus.DRAFT
    )
    is_default = models.BooleanField(default=False)
    download_count = models.PositiveIntegerField(default=0)
    last_downloaded = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("resume")
        verbose_name_plural = _("resumes")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.user.username} - {self.title}"

    def save(self, *args, **kwargs):
        if self.is_default:
            # Ensure only one default resume per user
            Resume.objects.filter(user=self.user, is_default=True).update(
                is_default=False
            )
        super().save(*args, **kwargs)


class Network(models.Model):
    """Professional networks and groups."""

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    industry = models.CharField(max_length=100, blank=True)
    location = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    logo = models.ImageField(upload_to="network_logos/", blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    is_public = models.BooleanField(default=True)
    member_count = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="networks_created"
    )
    admins = models.ManyToManyField(
        User, blank=True, related_name="networks_administered"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("network")
        verbose_name_plural = _("networks")

    def __str__(self):
        return self.name


class NetworkMembership(models.Model):
    """User membership in professional networks."""

    class MembershipStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        ACTIVE = "active", _("Active")
        INACTIVE = "inactive", _("Inactive")
        BANNED = "banned", _("Banned")

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="network_memberships"
    )
    network = models.ForeignKey(
        Network, on_delete=models.CASCADE, related_name="memberships"
    )
    status = models.CharField(
        max_length=10,
        choices=MembershipStatus.choices,
        default=MembershipStatus.PENDING,
    )
    role = models.CharField(max_length=50, default="member")
    joined_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("network membership")
        verbose_name_plural = _("network memberships")
        unique_together = [["user", "network"]]

    def __str__(self):
        return f"{self.user.username} in {self.network.name}"


class Recommendation(models.Model):
    """Professional recommendations between users."""

    class RecommendationType(models.TextChoices):
        COLLEAGUE = "colleague", _("Colleague")
        MANAGER = "manager", _("Manager")
        DIRECT_REPORT = "direct_report", _("Direct Report")
        CLIENT = "client", _("Client")
        MENTOR = "mentor", _("Mentor")
        OTHER = "other", _("Other")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recommender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="recommendations_given"
    )
    recommendee = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="recommendations_received"
    )
    relationship_type = models.CharField(
        max_length=20, choices=RecommendationType.choices
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    skills_highlighted = models.JSONField(default=list, blank=True)
    is_public = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("recommendation")
        verbose_name_plural = _("recommendations")
        unique_together = [["recommender", "recommendee"]]

    def __str__(self):
        return f"Recommendation from {self.recommender.username} to {self.recommendee.username}"


class Message(models.Model):
    """Direct messages between users."""

    class MessageStatus(models.TextChoices):
        SENT = "sent", _("Sent")
        DELIVERED = "delivered", _("Delivered")
        READ = "read", _("Read")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="messages_sent"
    )
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="messages_received"
    )
    subject = models.CharField(max_length=200, blank=True)
    content = models.TextField()
    status = models.CharField(
        max_length=10, choices=MessageStatus.choices, default=MessageStatus.SENT
    )
    attachment = models.FileField(
        upload_to="message_attachments/", blank=True, null=True
    )
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="replies"
    )
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("message")
        verbose_name_plural = _("messages")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Message from {self.sender.username} to {self.recipient.username}"

    def mark_as_read(self):
        """Mark message as read."""
        from django.utils import timezone

        if self.status != self.MessageStatus.READ:
            self.status = self.MessageStatus.READ
            self.read_at = timezone.now()
            self.save(update_fields=["status", "read_at"])


class Notification(models.Model):
    """User notifications system."""

    class NotificationType(models.TextChoices):
        CONNECTION_REQUEST = "connection_request", _("Connection Request")
        CONNECTION_ACCEPTED = "connection_accepted", _("Connection Accepted")
        SKILL_ENDORSEMENT = "skill_endorsement", _("Skill Endorsement")
        PROFILE_VIEW = "profile_view", _("Profile View")
        MESSAGE = "message", _("New Message")
        RECOMMENDATION = "recommendation", _("Recommendation")
        RECOMMENDATION_RECEIVED = (
            "recommendation_received",
            _("Recommendation Received"),
        )
        RECOMMENDATION_APPROVED = (
            "recommendation_approved",
            _("Recommendation Approved"),
        )
        RECOMMENDATION_DECLINED = (
            "recommendation_declined",
            _("Recommendation Declined"),
        )
        RECOMMENDATION_REQUEST = "recommendation_request", _("Recommendation Request")
        TASK_ASSIGNED = "task_assigned", _("Task Assigned")
        TASK_COMPLETED = "task_completed", _("Task Completed")
        PROJECT_INVITATION = "project_invitation", _("Project Invitation")
        NETWORK_INVITATION = "network_invitation", _("Network Invitation")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="account_notifications"
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="account_notifications_sent",
        null=True,
        blank=True,
    )
    notification_type = models.CharField(
        max_length=30, choices=NotificationType.choices
    )
    title = models.CharField(max_length=200)
    message = models.TextField()
    data = models.JSONField(default=dict, blank=True)
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("notification")
        verbose_name_plural = _("notifications")
        ordering = ["-created_at"]

    def __str__(self):
        return f"Notification to {self.recipient.username}: {self.title}"

    def mark_as_read(self):
        """Mark notification as read."""
        from django.utils import timezone

        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


class SavedSearch(models.Model):
    """Saved search queries for users."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="saved_searches"
    )
    name = models.CharField(max_length=100)
    query_params = models.JSONField()
    alert_enabled = models.BooleanField(default=False)
    last_run = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("saved search")
        verbose_name_plural = _("saved searches")

    def __str__(self):
        return f"{self.user.username} - {self.name}"


class ProfileStats(models.Model):
    """Profile statistics and analytics."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="stats")
    profile_views = models.PositiveIntegerField(default=0)
    profile_views_this_week = models.PositiveIntegerField(default=0)
    profile_views_this_month = models.PositiveIntegerField(default=0)
    connections_count = models.PositiveIntegerField(default=0)
    endorsements_count = models.PositiveIntegerField(default=0)
    project_views = models.PositiveIntegerField(default=0)
    search_appearances = models.PositiveIntegerField(default=0)
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("profile stats")
        verbose_name_plural = _("profile stats")

    def __str__(self):
        return f"Stats for {self.user.username}"

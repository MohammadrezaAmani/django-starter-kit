import hashlib
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

# GuardianModelMixin not available in current version, using regular models
from mptt.models import MPTTModel, TreeForeignKey

User = get_user_model()


class EventQuerySet(models.QuerySet):
    """Custom queryset for Event with useful filters and annotations."""

    def published(self):
        return self.filter(status=Event.EventStatus.PUBLISHED)

    def live(self):
        return self.filter(status=Event.EventStatus.LIVE)

    def upcoming(self):
        return self.filter(
            start_datetime__gt=timezone.now(),
            status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.SCHEDULED],
        )

    def past(self):
        return self.filter(end_datetime__lt=timezone.now())

    def public(self):
        return self.filter(visibility=Event.Visibility.PUBLIC)

    def registration_open(self):
        now = timezone.now()
        return self.filter(
            registration_start_date__lte=now,
            registration_end_date__gte=now,
            status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.SCHEDULED],
        )

    def with_capacity(self):
        return self.filter(
            models.Q(max_participants__isnull=True)
            | models.Q(max_participants__gt=models.F("participants_count"))
        )

    def by_organizer(self, user):
        return self.filter(organizer=user)

    def search(self, query):
        return self.filter(
            models.Q(title__icontains=query)
            | models.Q(description__icontains=query)
            | models.Q(tags__name__icontains=query)
        ).distinct()


class Event(models.Model):
    """
    Core event model: Supports multi-event, hybrid/virtual, ticketing, sponsorships, AI recommendations.
    Integrates with Chat for event-specific messaging, Blog for announcements.
    """

    class EventType(models.TextChoices):
        CONFERENCE = "conference", _("Conference")
        WORKSHOP = "workshop", _("Workshop")
        SEMINAR = "seminar", _("Seminar")
        WEBINAR = "webinar", _("Webinar")
        MEETUP = "meetup", _("Meetup")
        FAIR = "fair", _("Fair")
        EXHIBITION = "exhibition", _("Exhibition")
        HYBRID = "hybrid", _("Hybrid")
        VIRTUAL = "virtual", _("Virtual")
        NETWORKING = "networking", _("Networking")

    class EventStatus(models.TextChoices):
        DRAFT = "draft", _("Draft")
        PUBLISHED = "published", _("Published")
        SCHEDULED = "scheduled", _("Scheduled")
        LIVE = "live", _("Live")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")
        POSTPONED = "postponed", _("Postponed")
        ARCHIVED = "archived", _("Archived")

    class Visibility(models.TextChoices):
        PUBLIC = "public", _("Public")
        PRIVATE = "private", _("Private")
        INVITE_ONLY = "invite_only", _("Invite Only")
        MEMBERS_ONLY = "members_only", _("Members Only")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("Event Name"), max_length=300)
    slug = models.SlugField(_("Slug"), unique=True, max_length=300)
    description = models.JSONField(
        _("Description"), default=dict, help_text="Lexical JSON for rich text"
    )
    raw_description = models.TextField(
        _("Raw Description"), blank=True, help_text="Plain text for search"
    )
    excerpt = models.TextField(_("Excerpt"), max_length=500, blank=True)

    # Event classification
    type = models.CharField(
        _("Event Type"),
        max_length=20,
        choices=EventType.choices,
        default=EventType.CONFERENCE,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.DRAFT,
    )
    visibility = models.CharField(
        _("Visibility"),
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PUBLIC,
    )

    # Date and time
    start_date = models.DateTimeField(_("Start Date"))
    end_date = models.DateTimeField(_("End Date"))
    registration_start = models.DateTimeField(
        _("Registration Start"), null=True, blank=True
    )
    registration_end = models.DateTimeField(
        _("Registration End"), null=True, blank=True
    )
    timezone = models.CharField(_("Timezone"), max_length=50, default="UTC")

    # Location
    location = models.CharField(_("Location"), max_length=200, blank=True)
    address = models.TextField(_("Address"), blank=True)
    city = models.CharField(_("City"), max_length=100, blank=True)
    country = models.CharField(_("Country"), max_length=100, blank=True)
    venue_name = models.CharField(_("Venue Name"), max_length=200, blank=True)
    venue_map = models.ImageField(
        _("Venue Map"), upload_to="event_maps/", blank=True, null=True
    )
    virtual_link = models.URLField(_("Virtual Link"), blank=True)

    # Organizers and roles
    organizer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="events_organized",
        verbose_name=_("Organizer"),
    )
    co_organizers = models.ManyToManyField(
        User,
        blank=True,
        related_name="events_coorganized",
        verbose_name=_("Co-organizers"),
    )
    speakers = models.ManyToManyField(
        User, blank=True, related_name="events_spoken", verbose_name=_("Speakers")
    )
    moderators = models.ManyToManyField(
        User, blank=True, related_name="events_moderated", verbose_name=_("Moderators")
    )

    # Media
    logo = models.ImageField(_("Logo"), upload_to="event_logos/", blank=True, null=True)
    banner = models.ImageField(
        _("Banner"), upload_to="event_banners/", blank=True, null=True
    )
    gallery = models.JSONField(
        _("Gallery"), default=list, blank=True, help_text="Array of image URLs"
    )

    # Capacity and registration
    capacity = models.PositiveIntegerField(
        _("Capacity"), default=0, validators=[MinValueValidator(0)]
    )
    max_tickets_per_user = models.PositiveIntegerField(
        _("Max Tickets Per User"), default=1, validators=[MinValueValidator(1)]
    )
    registration_required = models.BooleanField(
        _("Registration Required"), default=True
    )
    approval_required = models.BooleanField(_("Approval Required"), default=False)
    waitlist_enabled = models.BooleanField(_("Waitlist Enabled"), default=True)

    # Pricing and tickets
    is_free = models.BooleanField(_("Is Free"), default=True)
    currency = models.CharField(_("Currency"), max_length=3, default="USD")
    ticket_types = models.JSONField(_("Ticket Types"), default=list, blank=True)
    discount_codes = models.JSONField(_("Discount Codes"), default=list, blank=True)

    # Features and settings
    allow_comments = models.BooleanField(_("Allow Comments"), default=True)
    allow_reviews = models.BooleanField(_("Allow Reviews"), default=True)
    enable_networking = models.BooleanField(_("Enable Networking"), default=True)
    enable_chat = models.BooleanField(_("Enable Chat"), default=True)
    enable_qr_checkin = models.BooleanField(_("Enable QR Check-in"), default=True)
    enable_live_streaming = models.BooleanField(
        _("Enable Live Streaming"), default=False
    )

    # AI and recommendations
    ai_recommendations_enabled = models.BooleanField(
        _("AI Recommendations"), default=False
    )
    ai_metadata = models.JSONField(_("AI Metadata"), default=dict, blank=True)

    # SEO and metadata
    seo_title = models.CharField(_("SEO Title"), max_length=60, blank=True)
    seo_description = models.CharField(_("SEO Description"), max_length=160, blank=True)
    seo_keywords = models.JSONField(_("SEO Keywords"), default=list, blank=True)
    canonical_url = models.URLField(_("Canonical URL"), blank=True)

    # Integration with existing models
    linked_project = models.ForeignKey(
        "accounts.Project",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Linked Project"),
    )
    linked_task = models.ForeignKey(
        "accounts.Task",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Linked Task"),
    )
    linked_network = models.ForeignKey(
        "accounts.Network",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Linked Network"),
    )
    linked_chat = models.ForeignKey(
        "chats.Chat",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Event Chat"),
    )
    linked_blog = models.ForeignKey(
        "blog.BlogPost",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name=_("Announcement Blog"),
    )

    # Customization
    custom_theme = models.JSONField(_("Custom Theme"), default=dict, blank=True)
    custom_fields = models.JSONField(_("Custom Fields"), default=dict, blank=True)
    branding = models.JSONField(_("Branding"), default=dict, blank=True)

    # Analytics and metrics
    view_count = models.PositiveIntegerField(_("View Count"), default=0, editable=False)
    registration_count = models.PositiveIntegerField(
        _("Registration Count"), default=0, editable=False
    )
    attendance_count = models.PositiveIntegerField(
        _("Attendance Count"), default=0, editable=False
    )
    engagement_score = models.FloatField(
        _("Engagement Score"), default=0.0, editable=False
    )

    # Languages and translations
    language = models.CharField(_("Primary Language"), max_length=10, default="en")
    languages = models.JSONField(_("Supported Languages"), default=list, blank=True)
    translations = models.JSONField(_("Translations"), default=dict, blank=True)

    # Security and moderation
    content_hash = models.CharField(
        _("Content Hash"), max_length=64, blank=True, editable=False
    )
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    is_trending = models.BooleanField(_("Is Trending"), default=False)
    is_verified = models.BooleanField(_("Is Verified"), default=False)

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    published_at = models.DateTimeField(_("Published At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Event")
        verbose_name_plural = _("Events")
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["slug", "status"]),
            models.Index(fields=["organizer", "start_date"]),
            models.Index(fields=["status", "visibility"]),
            models.Index(fields=["start_date", "end_date"]),
            models.Index(fields=["city", "country"]),
            models.Index(fields=["type", "status"]),
            models.Index(fields=["-created_at"]),
            models.Index(fields=["is_featured", "is_trending"]),
        ]
        permissions = [
            ("can_moderate_event", "Can moderate events"),
            ("can_feature_event", "Can feature events"),
            ("can_verify_event", "Can verify events"),
        ]

    objects = EventQuerySet.as_manager()

    def __str__(self):
        return self.name

    def clean(self):
        if self.end_date <= self.start_date:
            raise ValidationError(_("End date must be after start date."))
        if self.registration_end and self.registration_end > self.start_date:
            raise ValidationError(_("Registration end must be before event start."))
        if (
            self.registration_start
            and self.registration_end
            and self.registration_start >= self.registration_end
        ):
            raise ValidationError(
                _("Registration start must be before registration end.")
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        if self.status == self.EventStatus.PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        if self.description:
            self.content_hash = hashlib.sha256(
                str(self.description).encode()
            ).hexdigest()
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        return (
            self.status == self.EventStatus.LIVE
            and self.start_date <= timezone.now() <= self.end_date
        )

    @property
    def is_registration_open(self):
        now = timezone.now()
        if self.registration_start and now < self.registration_start:
            return False
        if self.registration_end and now > self.registration_end:
            return False
        return self.registration_required and self.status in [
            self.EventStatus.PUBLISHED,
            self.EventStatus.SCHEDULED,
        ]

    @property
    def spots_remaining(self):
        if self.capacity == 0:
            return float("inf")
        return max(0, self.capacity - self.registration_count)

    def get_absolute_url(self):
        return f"/events/{self.slug}/"


class EventCategoryQuerySet(models.QuerySet):
    """Custom queryset for EventCategory with useful filters."""

    def active(self):
        return self.filter(is_active=True)

    def root_categories(self):
        return self.filter(parent__isnull=True)

    def with_event_count(self):
        return self.annotate(event_count=models.Count("events"))


class EventCategory(MPTTModel):
    """Categories for events with hierarchical structure."""

    name = models.CharField(_("Name"), max_length=100, unique=True)
    slug = models.SlugField(_("Slug"), unique=True)
    description = models.TextField(_("Description"), blank=True)
    icon = models.CharField(
        _("Icon"), max_length=50, blank=True, help_text="FontAwesome icon class"
    )
    color = models.CharField(_("Color"), max_length=7, default="#6366f1")
    parent = TreeForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    is_active = models.BooleanField(_("Is Active"), default=True)
    sort_order = models.PositiveIntegerField(_("Sort Order"), default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class MPTTMeta:
        order_insertion_by = ["sort_order", "name"]

    class Meta:
        verbose_name = _("Event Category")
        verbose_name_plural = _("Event Categories")
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["slug", "is_active"])]

    objects = EventCategoryQuerySet.as_manager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class EventTagQuerySet(models.QuerySet):
    """Custom queryset for EventTag with useful filters."""

    def trending(self):
        return self.filter(is_trending=True)

    def popular(self):
        return self.order_by("-usage_count")

    def with_event_count(self):
        return self.annotate(event_count=models.Count("events"))


class EventTag(models.Model):
    """Tags for events with usage tracking."""

    name = models.CharField(_("Name"), max_length=50, unique=True)
    slug = models.SlugField(_("Slug"), unique=True)
    description = models.TextField(_("Description"), blank=True)
    color = models.CharField(_("Color"), max_length=7, default="#6b7280")
    usage_count = models.PositiveIntegerField(
        _("Usage Count"), default=0, editable=False
    )
    is_trending = models.BooleanField(_("Is Trending"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Event Tag")
        verbose_name_plural = _("Event Tags")
        ordering = ["-usage_count", "name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["-usage_count"]),
        ]

    objects = EventTagQuerySet.as_manager()

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


# Through model for Event-Category relationship
class EventCategoryRelation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    category = models.ForeignKey(EventCategory, on_delete=models.CASCADE)
    is_primary = models.BooleanField(_("Is Primary"), default=False)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        unique_together = [["event", "category"]]
        verbose_name = _("Event Category Relation")
        verbose_name_plural = _("Event Category Relations")

    objects = models.Manager()


# Through model for Event-Tag relationship
class EventTagRelation(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    tag = models.ForeignKey(EventTag, on_delete=models.CASCADE)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        unique_together = [["event", "tag"]]
        verbose_name = _("Event Tag Relation")
        verbose_name_plural = _("Event Tag Relations")

    objects = models.Manager()


class SessionQuerySet(models.QuerySet):
    """Custom queryset for Session with useful filters."""

    def live(self):
        return self.filter(status=Session.SessionStatus.LIVE)

    def scheduled(self):
        return self.filter(status=Session.SessionStatus.SCHEDULED)

    def completed(self):
        return self.filter(status=Session.SessionStatus.COMPLETED)

    def upcoming(self):
        return self.filter(
            start_time__gt=timezone.now(),
            status=Session.SessionStatus.SCHEDULED,
        )

    def by_event(self, event):
        return self.filter(event=event)

    def by_speaker(self, user):
        return self.filter(speakers=user)

    def by_type(self, session_type):
        return self.filter(type=session_type)


class Session(models.Model):
    """Sessions/schedule for events with tracks, locations, and live status."""

    class SessionType(models.TextChoices):
        KEYNOTE = "keynote", _("Keynote")
        PRESENTATION = "presentation", _("Presentation")
        WORKSHOP = "workshop", _("Workshop")
        PANEL = "panel", _("Panel Discussion")
        ROUNDTABLE = "roundtable", _("Roundtable")
        BREAK = "break", _("Break")
        LUNCH = "lunch", _("Lunch")
        NETWORKING = "networking", _("Networking")
        Q_AND_A = "q_and_a", _("Q&A Session")
        DEMO = "demo", _("Demo")

    class SessionStatus(models.TextChoices):
        SCHEDULED = "scheduled", _("Scheduled")
        LIVE = "live", _("Live")
        COMPLETED = "completed", _("Completed")
        CANCELLED = "cancelled", _("Cancelled")
        POSTPONED = "postponed", _("Postponed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="sessions",
        verbose_name=_("Event"),
    )
    title = models.CharField(_("Title"), max_length=300)
    slug = models.SlugField(_("Slug"), max_length=300)
    description = models.JSONField(
        _("Description"), default=dict, help_text="Lexical JSON for rich text"
    )
    raw_description = models.TextField(_("Raw Description"), blank=True)

    # Session details
    type = models.CharField(
        _("Type"),
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.PRESENTATION,
    )
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=SessionStatus.choices,
        default=SessionStatus.SCHEDULED,
    )

    # Schedule
    start_time = models.DateTimeField(_("Start Time"))
    end_time = models.DateTimeField(_("End Time"))
    timezone = models.CharField(_("Timezone"), max_length=50, default="UTC")

    # Location and logistics
    track = models.CharField(
        _("Track"),
        max_length=100,
        blank=True,
        help_text="e.g., 'Business Track', 'Tech Track'",
    )
    room = models.CharField(_("Room"), max_length=100, blank=True)
    location = models.CharField(_("Location"), max_length=100, blank=True)
    virtual_link = models.URLField(_("Virtual Link"), blank=True)

    # People
    speakers = models.ManyToManyField(
        User, blank=True, related_name="sessions_spoken", verbose_name=_("Speakers")
    )
    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sessions_moderated",
        verbose_name=_("Moderator"),
    )

    # Settings
    capacity = models.PositiveIntegerField(
        _("Capacity"), default=0, validators=[MinValueValidator(0)]
    )
    is_paid = models.BooleanField(_("Requires Paid Ticket"), default=False)
    is_recorded = models.BooleanField(_("Is Recorded"), default=False)
    is_live_streamed = models.BooleanField(_("Is Live Streamed"), default=False)
    is_featured = models.BooleanField(_("Is Featured"), default=False)
    requires_registration = models.BooleanField(
        _("Requires Registration"), default=False
    )

    # Content
    materials = models.JSONField(
        _("Materials"),
        default=list,
        blank=True,
        help_text="Links to slides, documents, etc.",
    )
    recording_url = models.URLField(_("Recording URL"), blank=True)

    # Analytics
    attendee_count = models.PositiveIntegerField(
        _("Attendee Count"), default=0, editable=False
    )
    rating_avg = models.FloatField(_("Average Rating"), default=0.0, editable=False)
    rating_count = models.PositiveIntegerField(
        _("Rating Count"), default=0, editable=False
    )

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Session")
        verbose_name_plural = _("Sessions")
        ordering = ["start_time"]
        unique_together = [["event", "slug"]]
        indexes = [
            models.Index(fields=["event", "start_time"]),
            models.Index(fields=["track", "room"]),
            models.Index(fields=["status", "start_time"]),
            models.Index(fields=["type", "start_time"]),
        ]

    objects = SessionQuerySet.as_manager()

    def __str__(self):
        return f"{self.title} - {self.event.name}"

    def clean(self):
        if self.end_time <= self.start_time:
            raise ValidationError(_("End time must be after start time."))
        if (
            self.start_time < self.event.start_date
            or self.end_time > self.event.end_date
        ):
            raise ValidationError(_("Session must be within event dates."))

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.title}-{self.event.slug}")
        super().save(*args, **kwargs)

    @property
    def is_live(self):
        return (
            self.status == self.SessionStatus.LIVE
            and self.start_time <= timezone.now() <= self.end_time
        )

    @property
    def duration_minutes(self):
        return int((self.end_time - self.start_time).total_seconds() / 60)


class ParticipantQuerySet(models.QuerySet):
    """Custom queryset for Participant with useful filters."""

    def confirmed(self):
        return self.filter(registration_status=Participant.RegistrationStatus.CONFIRMED)

    def attended(self):
        return self.filter(registration_status=Participant.RegistrationStatus.ATTENDED)

    def checked_in(self):
        return self.filter(attendance_status=Participant.AttendanceStatus.CHECKED_IN)

    def by_event(self, event):
        return self.filter(event=event)

    def by_role(self, role):
        return self.filter(role=role)

    def speakers(self):
        return self.filter(role=Participant.Role.SPEAKER)

    def organizers(self):
        return self.filter(
            role__in=[Participant.Role.ORGANIZER, Participant.Role.CO_ORGANIZER]
        )


class Participant(models.Model):
    """User participation in events with roles, badges, and registrations."""

    class Role(models.TextChoices):
        ATTENDEE = "attendee", _("Attendee")
        SPEAKER = "speaker", _("Speaker")
        MODERATOR = "moderator", _("Moderator")
        ORGANIZER = "organizer", _("Organizer")
        CO_ORGANIZER = "co_organizer", _("Co-organizer")
        SPONSOR = "sponsor", _("Sponsor")
        EXHIBITOR = "exhibitor", _("Exhibitor")
        VOLUNTEER = "volunteer", _("Volunteer")
        MEDIA = "media", _("Media")
        VIP = "vip", _("VIP")

    class RegistrationStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        CONFIRMED = "confirmed", _("Confirmed")
        CANCELLED = "cancelled", _("Cancelled")
        WAITLIST = "waitlist", _("Waitlist")
        REJECTED = "rejected", _("Rejected")
        NO_SHOW = "no_show", _("No Show")
        ATTENDED = "attended", _("Attended")

    class AttendanceStatus(models.TextChoices):
        NOT_ATTENDED = "not_attended", _("Not Attended")
        CHECKED_IN = "checked_in", _("Checked In")
        ATTENDED = "attended", _("Attended")
        LEFT_EARLY = "left_early", _("Left Early")

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="event_participations",
        verbose_name=_("User"),
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="participants",
        verbose_name=_("Event"),
    )

    # Registration details
    role = models.CharField(
        _("Role"), max_length=20, choices=Role.choices, default=Role.ATTENDEE
    )
    registration_status = models.CharField(
        _("Registration Status"),
        max_length=20,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.PENDING,
    )
    attendance_status = models.CharField(
        _("Attendance Status"),
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.NOT_ATTENDED,
    )

    # Ticket information
    ticket_type = models.CharField(_("Ticket Type"), max_length=50, blank=True)
    ticket_code = models.CharField(
        _("Ticket Code"), max_length=100, blank=True, unique=True
    )
    ticket_price = models.DecimalField(
        _("Ticket Price"), max_digits=10, decimal_places=2, default=0
    )
    payment_status = models.CharField(
        _("Payment Status"), max_length=20, default="pending"
    )

    # Profile and preferences
    bio = models.TextField(_("Bio"), blank=True, max_length=500)
    company = models.CharField(_("Company"), max_length=200, blank=True)
    job_title = models.CharField(_("Job Title"), max_length=200, blank=True)
    website = models.URLField(_("Website"), blank=True)
    social_links = models.JSONField(_("Social Links"), default=dict, blank=True)

    # Privacy settings
    is_public_profile = models.BooleanField(_("Public Profile"), default=False)
    allow_networking = models.BooleanField(_("Allow Networking"), default=True)
    allow_messages = models.BooleanField(_("Allow Messages"), default=True)

    # Gamification
    points = models.PositiveIntegerField(_("Points"), default=0)
    level = models.PositiveIntegerField(_("Level"), default=1)
    badges = models.JSONField(_("Badges"), default=list, blank=True)

    # Preferences
    interests = models.JSONField(_("Interests"), default=list, blank=True)
    dietary_requirements = models.TextField(_("Dietary Requirements"), blank=True)
    accessibility_needs = models.TextField(_("Accessibility Needs"), blank=True)
    session_preferences = models.JSONField(
        _("Session Preferences"), default=list, blank=True
    )

    # Attendance tracking
    check_in_time = models.DateTimeField(_("Check-in Time"), null=True, blank=True)
    check_out_time = models.DateTimeField(_("Check-out Time"), null=True, blank=True)
    sessions_attended = models.ManyToManyField(
        Session,
        blank=True,
        related_name="attendees",
        verbose_name=_("Sessions Attended"),
    )

    # Analytics
    last_activity = models.DateTimeField(_("Last Activity"), null=True, blank=True)
    total_session_time = models.PositiveIntegerField(
        _("Total Session Time"), default=0, help_text="in minutes"
    )
    engagement_score = models.FloatField(_("Engagement Score"), default=0.0)

    # Registration data
    registration_data = models.JSONField(
        _("Registration Data"), default=dict, blank=True
    )
    notes = models.TextField(_("Notes"), blank=True)

    # Timestamps
    registered_at = models.DateTimeField(_("Registered At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Participant")
        verbose_name_plural = _("Participants")
        unique_together = [["user", "event"]]
        indexes = [
            models.Index(fields=["event", "role"]),
            models.Index(fields=["registration_status", "attendance_status"]),
            models.Index(fields=["user", "registered_at"]),
            models.Index(fields=["ticket_code"]),
        ]

    objects = ParticipantQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} - {self.event.name}"

    def save(self, *args, **kwargs):
        if not self.ticket_code:
            self.ticket_code = f"{self.event.slug}-{uuid.uuid4().hex[:8]}"
        super().save(*args, **kwargs)

    def add_points(self, amount, reason=""):
        """Add points and update level if necessary."""
        self.points = F("points") + amount
        self.save(update_fields=["points"])
        self.refresh_from_db()

        # Simple level calculation (can be made more sophisticated)
        new_level = min(10, max(1, self.points // 100 + 1))
        if new_level != self.level:
            self.level = new_level
            self.save(update_fields=["level"])

    def check_in(self):
        """Check in the participant."""
        self.check_in_time = timezone.now()
        self.attendance_status = self.AttendanceStatus.CHECKED_IN
        self.save(update_fields=["check_in_time", "attendance_status"])
        self.add_points(10, "Event check-in")

    def check_out(self):
        """Check out the participant."""
        self.check_out_time = timezone.now()
        if self.attendance_status == self.AttendanceStatus.CHECKED_IN:
            self.attendance_status = self.AttendanceStatus.ATTENDED
        self.save(update_fields=["check_out_time", "attendance_status"])


class ExhibitorQuerySet(models.QuerySet):
    """Custom queryset for Exhibitor with useful filters."""

    def approved(self):
        return self.filter(status=Exhibitor.ExhibitorStatus.APPROVED)

    def pending(self):
        return self.filter(status=Exhibitor.ExhibitorStatus.PENDING)

    def by_event(self, event):
        return self.filter(event=event)

    def by_tier(self, tier):
        return self.filter(sponsorship_tier=tier)

    def sponsors(self):
        return self.exclude(sponsorship_tier=Exhibitor.SponsorshipTier.NONE)


class Exhibitor(models.Model):
    """Exhibitor model for booths, products, and sponsorships."""

    class SponsorshipTier(models.TextChoices):
        TITLE = "title", _("Title Sponsor")
        PLATINUM = "platinum", _("Platinum")
        GOLD = "gold", _("Gold")
        SILVER = "silver", _("Silver")
        BRONZE = "bronze", _("Bronze")
        SUPPORTER = "supporter", _("Supporter")
        NONE = "none", _("None")

    class ExhibitorStatus(models.TextChoices):
        PENDING = "pending", _("Pending")
        APPROVED = "approved", _("Approved")
        REJECTED = "rejected", _("Rejected")
        CANCELLED = "cancelled", _("Cancelled")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="exhibitors",
        verbose_name=_("Event"),
    )

    # Company information
    company_name = models.CharField(_("Company Name"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200)
    description = models.JSONField(
        _("Description"), default=dict, help_text="Lexical JSON for rich text"
    )
    raw_description = models.TextField(_("Raw Description"), blank=True)

    # Media
    logo = models.ImageField(
        _("Logo"), upload_to="exhibitor_logos/", blank=True, null=True
    )
    banner = models.ImageField(
        _("Banner"), upload_to="exhibitor_banners/", blank=True, null=True
    )
    gallery = models.JSONField(_("Gallery"), default=list, blank=True)

    # Booth information
    booth_number = models.CharField(_("Booth Number"), max_length=50, blank=True)
    booth_size = models.CharField(_("Booth Size"), max_length=50, blank=True)
    booth_location = models.CharField(_("Booth Location"), max_length=100, blank=True)
    booth_map_coordinates = models.JSONField(
        _("Booth Map Coordinates"), default=dict, blank=True
    )

    # Contact information
    website = models.URLField(_("Website"), blank=True)
    contact_email = models.EmailField(_("Contact Email"), blank=True)
    contact_phone = models.CharField(_("Contact Phone"), max_length=20, blank=True)
    social_links = models.JSONField(_("Social Links"), default=dict, blank=True)

    # Representatives
    representatives = models.ManyToManyField(
        User,
        blank=True,
        related_name="exhibitor_representations",
        verbose_name=_("Representatives"),
    )
    primary_contact = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="primary_exhibitor_contacts",
        verbose_name=_("Primary Contact"),
    )

    # Sponsorship
    sponsorship_tier = models.CharField(
        _("Sponsorship Tier"),
        max_length=20,
        choices=SponsorshipTier.choices,
        default=SponsorshipTier.NONE,
    )
    sponsorship_amount = models.DecimalField(
        _("Sponsorship Amount"), max_digits=10, decimal_places=2, default=0
    )
    sponsorship_benefits = models.JSONField(
        _("Sponsorship Benefits"), default=list, blank=True
    )

    # Status and approval
    status = models.CharField(
        _("Status"),
        max_length=20,
        choices=ExhibitorStatus.choices,
        default=ExhibitorStatus.PENDING,
    )

    # Analytics
    view_count = models.PositiveIntegerField(_("View Count"), default=0, editable=False)
    connection_count = models.PositiveIntegerField(
        _("Connection Count"), default=0, editable=False
    )
    lead_count = models.PositiveIntegerField(_("Lead Count"), default=0, editable=False)

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)
    approved_at = models.DateTimeField(_("Approved At"), null=True, blank=True)

    class Meta:
        verbose_name = _("Exhibitor")
        verbose_name_plural = _("Exhibitors")
        unique_together = [["event", "slug"], ["event", "company_name"]]
        indexes = [
            models.Index(fields=["event", "company_name"]),
            models.Index(fields=["status", "sponsorship_tier"]),
            models.Index(fields=["booth_number"]),
        ]

    objects = ExhibitorQuerySet.as_manager()

    def __str__(self):
        return f"{self.company_name} - {self.event.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.company_name)
        super().save(*args, **kwargs)


class ProductQuerySet(models.QuerySet):
    """Custom queryset for Product with useful filters."""

    def available(self):
        return self.filter(is_available=True)

    def by_exhibitor(self, exhibitor):
        return self.filter(exhibitor=exhibitor)

    def by_category(self, category):
        return self.filter(category=category)

    def featured(self):
        return self.filter(is_featured=True)

    def in_stock(self):
        return self.filter(stock_quantity__gt=0)


class Product(models.Model):
    """Products showcased by exhibitors."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    exhibitor = models.ForeignKey(
        Exhibitor,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("Exhibitor"),
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="products",
        verbose_name=_("Event"),
    )

    # Product information
    name = models.CharField(_("Product Name"), max_length=200)
    slug = models.SlugField(_("Slug"), max_length=200)
    description = models.JSONField(
        _("Description"), default=dict, help_text="Lexical JSON for rich text"
    )
    raw_description = models.TextField(_("Raw Description"), blank=True)

    # Media
    image = models.ImageField(
        _("Product Image"), upload_to="product_images/", blank=True, null=True
    )
    gallery = models.JSONField(_("Gallery"), default=list, blank=True)

    # Product details
    category = models.CharField(_("Category"), max_length=100, blank=True)
    price = models.DecimalField(
        _("Price"), max_digits=10, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(_("Currency"), max_length=3, default="USD")
    availability = models.CharField(_("Availability"), max_length=100, blank=True)
    features = models.JSONField(_("Features"), default=list, blank=True)
    specifications = models.JSONField(_("Specifications"), default=dict, blank=True)

    # Links and resources
    website = models.URLField(_("Product Website"), blank=True)
    demo_url = models.URLField(_("Demo URL"), blank=True)
    documentation_url = models.URLField(_("Documentation URL"), blank=True)
    brochure = models.FileField(
        _("Brochure"), upload_to="product_brochures/", blank=True, null=True
    )

    # Analytics
    view_count = models.PositiveIntegerField(_("View Count"), default=0, editable=False)
    favorite_count = models.PositiveIntegerField(
        _("Favorite Count"), default=0, editable=False
    )
    inquiry_count = models.PositiveIntegerField(
        _("Inquiry Count"), default=0, editable=False
    )

    # Timestamps
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        verbose_name = _("Product")
        verbose_name_plural = _("Products")
        unique_together = [["exhibitor", "slug"], ["event", "slug"]]
        indexes = [
            models.Index(fields=["event", "category"]),
            models.Index(fields=["exhibitor", "name"]),
            models.Index(fields=["price", "currency"]),
        ]

    objects = ProductQuerySet.as_manager()

    def __str__(self):
        return f"{self.name} - {self.exhibitor.company_name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.name}-{self.exhibitor.slug}")
        super().save(*args, **kwargs)


class EventAnalyticsQuerySet(models.QuerySet):
    """Custom queryset for EventAnalytics with useful filters."""

    def by_event(self, event):
        return self.filter(event=event)

    def with_high_engagement(self, threshold=0.7):
        return self.filter(engagement_rate__gte=threshold)


class EventAnalytics(models.Model):
    """Analytics model for tracking event performance."""

    event = models.OneToOneField(
        Event,
        on_delete=models.CASCADE,
        related_name="analytics",
        verbose_name=_("Event"),
    )

    # Registration metrics
    total_registrations = models.PositiveIntegerField(
        _("Total Registrations"), default=0
    )
    confirmed_registrations = models.PositiveIntegerField(
        _("Confirmed Registrations"), default=0
    )
    cancelled_registrations = models.PositiveIntegerField(
        _("Cancelled Registrations"), default=0
    )
    waitlist_registrations = models.PositiveIntegerField(
        _("Waitlist Registrations"), default=0
    )

    # Attendance metrics
    total_attendance = models.PositiveIntegerField(_("Total Attendance"), default=0)
    attendance_rate = models.FloatField(_("Attendance Rate"), default=0.0)
    no_show_rate = models.FloatField(_("No Show Rate"), default=0.0)
    early_departure_rate = models.FloatField(_("Early Departure Rate"), default=0.0)

    # Engagement metrics
    avg_session_attendance = models.FloatField(
        _("Average Session Attendance"), default=0.0
    )
    session_completion_rate = models.FloatField(
        _("Session Completion Rate"), default=0.0
    )
    networking_connections = models.PositiveIntegerField(
        _("Networking Connections"), default=0
    )
    chat_messages = models.PositiveIntegerField(_("Chat Messages"), default=0)

    # Content metrics
    total_sessions = models.PositiveIntegerField(_("Total Sessions"), default=0)
    avg_session_rating = models.FloatField(_("Average Session Rating"), default=0.0)
    total_exhibitors = models.PositiveIntegerField(_("Total Exhibitors"), default=0)
    total_products = models.PositiveIntegerField(_("Total Products"), default=0)

    # Financial metrics
    total_revenue = models.DecimalField(
        _("Total Revenue"), max_digits=12, decimal_places=2, default=0
    )
    avg_ticket_price = models.DecimalField(
        _("Average Ticket Price"), max_digits=10, decimal_places=2, default=0
    )
    sponsorship_revenue = models.DecimalField(
        _("Sponsorship Revenue"), max_digits=12, decimal_places=2, default=0
    )

    # Geographic metrics
    top_countries = models.JSONField(_("Top Countries"), default=list, blank=True)
    top_cities = models.JSONField(_("Top Cities"), default=list, blank=True)

    # Device and platform metrics
    device_breakdown = models.JSONField(_("Device Breakdown"), default=dict, blank=True)
    browser_breakdown = models.JSONField(
        _("Browser Breakdown"), default=dict, blank=True
    )

    # Time-based metrics
    peak_attendance_time = models.DateTimeField(
        _("Peak Attendance Time"), null=True, blank=True
    )
    avg_session_duration = models.PositiveIntegerField(
        _("Average Session Duration"), default=0, help_text="in minutes"
    )

    # Satisfaction metrics
    overall_satisfaction = models.FloatField(_("Overall Satisfaction"), default=0.0)
    nps_score = models.FloatField(_("NPS Score"), default=0.0)
    recommendation_rate = models.FloatField(_("Recommendation Rate"), default=0.0)

    # Last updated
    last_calculated = models.DateTimeField(_("Last Calculated"), auto_now=True)

    class Meta:
        verbose_name = _("Event Analytics")
        verbose_name_plural = _("Event Analytics")

    objects = EventAnalyticsQuerySet.as_manager()

    def __str__(self):
        return f"Analytics for {self.event.name}"

    def recalculate(self):
        """Recalculate all analytics metrics."""
        # Registration metrics
        participants = self.event.participants.all()
        self.total_registrations = participants.count()
        self.confirmed_registrations = participants.filter(
            registration_status=Participant.RegistrationStatus.CONFIRMED
        ).count()
        self.cancelled_registrations = participants.filter(
            registration_status=Participant.RegistrationStatus.CANCELLED
        ).count()
        self.waitlist_registrations = participants.filter(
            registration_status=Participant.RegistrationStatus.WAITLIST
        ).count()

        # Attendance metrics
        attended = participants.filter(
            attendance_status__in=[
                Participant.AttendanceStatus.CHECKED_IN,
                Participant.AttendanceStatus.ATTENDED,
            ]
        )
        self.total_attendance = attended.count()
        if self.confirmed_registrations > 0:
            self.attendance_rate = (
                self.total_attendance / self.confirmed_registrations
            ) * 100

        # Session metrics
        sessions = self.event.sessions.all()
        self.total_sessions = sessions.count()
        if sessions.exists():
            self.avg_session_rating = (
                sessions.aggregate(avg_rating=models.Avg("rating_avg"))["avg_rating"]
                or 0.0
            )

        # Exhibitor and product metrics
        self.total_exhibitors = self.event.exhibitors.count()
        self.total_products = self.event.products.count()

        self.save()


class EventBadgeQuerySet(models.QuerySet):
    """Custom queryset for EventBadge with useful filters."""

    def active(self):
        return self.filter(is_active=True)

    def by_points_range(self, min_points, max_points):
        return self.filter(
            points_required__gte=min_points, points_required__lte=max_points
        )


class EventBadge(models.Model):
    """Badges for gamification in events."""

    name = models.CharField(_("Badge Name"), max_length=100)
    description = models.TextField(_("Description"), blank=True)
    icon = models.ImageField(
        _("Icon"), upload_to="event_badges/", blank=True, null=True
    )
    color = models.CharField(_("Color"), max_length=7, default="#6366f1")
    points_required = models.PositiveIntegerField(_("Points Required"), default=0)
    criteria = models.JSONField(_("Criteria"), default=dict, blank=True)
    is_active = models.BooleanField(_("Is Active"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Event Badge")
        verbose_name_plural = _("Event Badges")
        ordering = ["points_required", "name"]

    objects = EventBadgeQuerySet.as_manager()

    def __str__(self):
        return self.name


class ParticipantBadgeQuerySet(models.QuerySet):
    """Custom queryset for ParticipantBadge with useful filters."""

    def by_participant(self, participant):
        return self.filter(participant=participant)

    def by_badge(self, badge):
        return self.filter(badge=badge)

    def recent(self):
        return self.order_by("-earned_at")


class ParticipantBadge(models.Model):
    """Badges earned by participants."""

    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="earned_badges",
        verbose_name=_("Participant"),
    )
    badge = models.ForeignKey(
        EventBadge, on_delete=models.CASCADE, verbose_name=_("Badge")
    )
    earned_at = models.DateTimeField(_("Earned At"), auto_now_add=True)
    reason = models.TextField(_("Reason"), blank=True)

    class Meta:
        unique_together = [["participant", "badge"]]
        verbose_name = _("Participant Badge")
        verbose_name_plural = _("Participant Badges")
        ordering = ["-earned_at"]

    objects = ParticipantBadgeQuerySet.as_manager()

    def __str__(self):
        return f"{self.participant.user.get_full_name()} - {self.badge.name}"


class EventAttachmentQuerySet(models.QuerySet):
    """Custom queryset for EventAttachment with useful filters."""

    def by_type(self, attachment_type):
        return self.filter(type=attachment_type)

    def images(self):
        return self.filter(type=EventAttachment.AttachmentType.IMAGE)

    def documents(self):
        return self.filter(type=EventAttachment.AttachmentType.DOCUMENT)

    def by_event(self, event):
        return self.filter(event=event)


class EventAttachment(models.Model):
    """Attachments for events, sessions, exhibitors, and products."""

    class AttachmentType(models.TextChoices):
        IMAGE = "image", _("Image")
        VIDEO = "video", _("Video")
        DOCUMENT = "document", _("Document")
        AUDIO = "audio", _("Audio")
        PRESENTATION = "presentation", _("Presentation")
        BROCHURE = "brochure", _("Brochure")
        LINK = "link", _("Link")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("Title"), max_length=200)
    description = models.TextField(_("Description"), blank=True)
    type = models.CharField(
        _("Type"),
        max_length=20,
        choices=AttachmentType.choices,
        default=AttachmentType.DOCUMENT,
    )
    file = models.FileField(
        _("File"), upload_to="event_attachments/", blank=True, null=True
    )
    url = models.URLField(_("URL"), blank=True)
    thumbnail = models.ImageField(
        _("Thumbnail"), upload_to="attachment_thumbnails/", blank=True, null=True
    )
    file_size = models.PositiveIntegerField(
        _("File Size"), default=0, help_text="in bytes"
    )
    mime_type = models.CharField(_("MIME Type"), max_length=100, blank=True)
    download_count = models.PositiveIntegerField(
        _("Download Count"), default=0, editable=False
    )
    is_public = models.BooleanField(_("Is Public"), default=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_uploaded_attachments",
        verbose_name=_("Uploaded By"),
    )

    # Generic foreign keys to different models
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Event"),
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Session"),
    )
    exhibitor = models.ForeignKey(
        Exhibitor,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Exhibitor"),
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="attachments",
        verbose_name=_("Product"),
    )

    class Meta:
        verbose_name = _("Event Attachment")
        verbose_name_plural = _("Event Attachments")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["type", "created_at"]),
            models.Index(fields=["event", "type"]),
            models.Index(fields=["session", "type"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(event__isnull=False)
                    & models.Q(session__isnull=True)
                    & models.Q(exhibitor__isnull=True)
                    & models.Q(product__isnull=True)
                )
                | (
                    models.Q(event__isnull=True)
                    & models.Q(session__isnull=False)
                    & models.Q(exhibitor__isnull=True)
                    & models.Q(product__isnull=True)
                )
                | (
                    models.Q(event__isnull=True)
                    & models.Q(session__isnull=True)
                    & models.Q(exhibitor__isnull=False)
                    & models.Q(product__isnull=True)
                )
                | (
                    models.Q(event__isnull=True)
                    & models.Q(session__isnull=True)
                    & models.Q(exhibitor__isnull=True)
                    & models.Q(product__isnull=False)
                ),
                name="attachment_single_relation",
            )
        ]

    objects = EventAttachmentQuerySet.as_manager()

    def clean(self):
        """Ensure only one foreign key is set."""
        foreign_keys = [self.event, self.session, self.exhibitor, self.product]
        non_null_keys = [key for key in foreign_keys if key is not None]

        if len(non_null_keys) != 1:
            raise ValidationError(
                "EventAttachment must be related to exactly one of: event, session, exhibitor, or product."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class SessionRatingQuerySet(models.QuerySet):
    """Custom queryset for SessionRating with useful filters."""

    def by_session(self, session):
        return self.filter(session=session)

    def by_participant(self, participant):
        return self.filter(participant=participant)

    def high_ratings(self, threshold=4):
        return self.filter(rating__gte=threshold)


class SessionRating(models.Model):
    """Ratings and reviews for sessions."""

    session = models.ForeignKey(
        Session,
        on_delete=models.CASCADE,
        related_name="ratings",
        verbose_name=_("Session"),
    )
    participant = models.ForeignKey(
        Participant,
        on_delete=models.CASCADE,
        related_name="session_ratings",
        verbose_name=_("Participant"),
    )
    rating = models.PositiveIntegerField(
        _("Rating"), choices=[(i, i) for i in range(1, 6)], default=5
    )
    review = models.TextField(_("Review"), blank=True)
    helpful_count = models.PositiveIntegerField(_("Helpful Count"), default=0)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Updated At"), auto_now=True)

    class Meta:
        unique_together = [["session", "participant"]]
        verbose_name = _("Session Rating")
        verbose_name_plural = _("Session Ratings")
        ordering = ["-created_at"]

    objects = SessionRatingQuerySet.as_manager()

    def __str__(self):
        return f"{self.session.title} - {self.rating}/5"


class EventFavoriteQuerySet(models.QuerySet):
    """Custom queryset for EventFavorite with useful filters."""

    def by_user(self, user):
        return self.filter(user=user)

    def by_event(self, event):
        return self.filter(event=event)

    def recent(self):
        return self.order_by("-created_at")


class EventFavorite(models.Model):
    """User favorites for events, sessions, exhibitors, and products."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="event_favorites",
        verbose_name=_("User"),
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="favorited_by",
        verbose_name=_("Event"),
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        unique_together = [["user", "event"]]
        verbose_name = _("Event Favorite")
        verbose_name_plural = _("Event Favorites")
        ordering = ["-created_at"]

    objects = EventFavoriteQuerySet.as_manager()

    def __str__(self):
        return f"{self.user.get_full_name()} favorites {self.event.name}"


class EventViewQuerySet(models.QuerySet):
    """Custom queryset for EventView with useful filters."""

    def by_event(self, event):
        return self.filter(event=event)

    def by_user(self, user):
        return self.filter(user=user)

    def recent(self):
        return self.order_by("-viewed_at")


class EventView(models.Model):
    """Track views for analytics."""

    event = models.ForeignKey(
        Event, on_delete=models.CASCADE, related_name="views", verbose_name=_("Event")
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="event_views",
        verbose_name=_("User"),
    )
    session_key = models.CharField(_("Session Key"), max_length=40, blank=True)
    ip_address = models.GenericIPAddressField(_("IP Address"), null=True, blank=True)
    user_agent = models.TextField(_("User Agent"), blank=True)
    duration = models.PositiveIntegerField(
        _("Duration"), default=0, help_text="in seconds"
    )
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Event View")
        verbose_name_plural = _("Event Views")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "-created_at"]),
            models.Index(fields=["user", "-created_at"]),
        ]

    objects = EventViewQuerySet.as_manager()

    def __str__(self):
        return f"View of {self.event.name} at {self.created_at}"


class EventModerationLogQuerySet(models.QuerySet):
    """Custom queryset for EventModerationLog with useful filters."""

    def by_event(self, event):
        return self.filter(event=event)

    def by_moderator(self, moderator):
        return self.filter(moderator=moderator)

    def by_action(self, action_type):
        return self.filter(action_type=action_type)

    def recent(self):
        return self.order_by("-created_at")


class EventModerationLog(models.Model):
    """Moderation actions for events."""

    class ActionType(models.TextChoices):
        APPROVE = "approve", _("Approve")
        REJECT = "reject", _("Reject")
        SUSPEND = "suspend", _("Suspend")
        FEATURE = "feature", _("Feature")
        UNFEATURE = "unfeature", _("Remove Feature")
        VERIFY = "verify", _("Verify")
        UNVERIFY = "unverify", _("Remove Verification")
        DELETE = "delete", _("Delete")
        RESTORE = "restore", _("Restore")

    moderator = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="event_moderation_actions",
        verbose_name=_("Moderator"),
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        related_name="moderation_logs",
        verbose_name=_("Event"),
    )
    action = models.CharField(_("Action"), max_length=20, choices=ActionType.choices)
    reason = models.TextField(_("Reason"), blank=True)
    notes = models.TextField(_("Notes"), blank=True)
    created_at = models.DateTimeField(_("Created At"), auto_now_add=True)

    class Meta:
        verbose_name = _("Event Moderation Log")
        verbose_name_plural = _("Event Moderation Logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["event", "action"]),
            models.Index(fields=["moderator", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]

    objects = EventModerationLogQuerySet.as_manager()

    def __str__(self):
        return f"{self.action} on {self.event.name} by {self.moderator}"

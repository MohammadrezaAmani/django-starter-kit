from typing import Dict, List, Optional

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify
from guardian.shortcuts import assign_perm
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError

from .models import (
    Event,
    EventAnalytics,
    EventAttachment,
    EventBadge,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventModerationLog,
    EventTag,
    EventTagRelation,
    EventView,
    Exhibitor,
    Participant,
    ParticipantBadge,
    Product,
    Session,
    SessionRating,
)

User = get_user_model()


class EventCategorySerializer(serializers.ModelSerializer):
    """Serializer for event categories with hierarchical support."""

    children = serializers.SerializerMethodField()
    event_count = serializers.SerializerMethodField()
    parent_name = serializers.CharField(source="parent.name", read_only=True)
    level = serializers.IntegerField(read_only=True)

    class Meta:
        model = EventCategory
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "color",
            "is_active",
            "parent",
            "parent_name",
            "level",
            "children",
            "event_count",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "level", "created_at", "updated_at"]

    def get_children(self, obj):
        """Get immediate children of this category."""
        if hasattr(obj, "prefetched_children"):
            children = obj.prefetched_children
        else:
            children = obj.get_children().filter(is_active=True)

        return EventCategorySerializer(children, many=True, context=self.context).data

    def get_event_count(self, obj):
        """Get count of active events in this category and its descendants."""
        if hasattr(obj, "event_count_cache"):
            return obj.event_count_cache

        # Use prefetch_related in viewset to optimize this
        descendant_ids = obj.get_descendants(include_self=True).values_list(
            "id", flat=True
        )
        return (
            Event.objects.filter(
                eventcategoryrelation__category__in=descendant_ids,
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            )
            .distinct()
            .count()
        )

    def validate_parent(self, value):
        """Ensure no circular references in category hierarchy."""
        if value and self.instance:
            if value == self.instance:
                raise ValidationError("Category cannot be its own parent.")
            if self.instance.get_descendants().filter(id=value.id).exists():
                raise ValidationError("Category cannot be a descendant of itself.")
        return value


class EventTagSerializer(serializers.ModelSerializer):
    """Serializer for event tags."""

    event_count = serializers.SerializerMethodField()
    trending_score = serializers.SerializerMethodField()

    class Meta:
        model = EventTag
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "color",
            "event_count",
            "trending_score",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]

    def get_event_count(self, obj):
        """Get count of active events with this tag."""
        if hasattr(obj, "event_count_cache"):
            return obj.event_count_cache
        return Event.objects.filter(
            eventtagrelation__tag=obj,
            status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
        ).count()

    def get_trending_score(self, obj):
        """Calculate trending score based on recent event activity."""
        if hasattr(obj, "trending_score_cache"):
            return obj.trending_score_cache

        recent_events = Event.objects.filter(
            eventtagrelation__tag=obj,
            created_at__gte=timezone.now() - timezone.timedelta(days=30),
        ).count()
        total_events = Event.objects.filter(eventtagrelation__tag=obj).count()

        if total_events == 0:
            return 0.0
        return round((recent_events / total_events) * 100, 2)


class UserMinimalSerializer(serializers.ModelSerializer):
    """Minimal user serializer for performance optimization."""

    avatar_url = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "full_name", "avatar_url"]

    def get_avatar_url(self, obj) -> Optional[str]:
        """Get user's avatar URL."""
        if obj.profile_picture:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.profile_picture.url)
        return None

    def get_full_name(self, obj) -> str:
        """Get user's full name or username as fallback."""
        return obj.get_full_name() or obj.username


class SessionMinimalSerializer(serializers.ModelSerializer):
    """Minimal session serializer for performance."""

    speaker_names = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    is_live = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            "id",
            "title",
            "type",
            "start_time",
            "end_time",
            "speaker_names",
            "duration_display",
            "is_live",
            "capacity",
        ]

    def get_speaker_names(self, obj) -> List[str]:
        """Get list of speaker names."""
        if hasattr(obj, "prefetched_speakers"):
            return [
                speaker.get_full_name() or speaker.username
                for speaker in obj.prefetched_speakers
            ]
        return [
            p.user.get_full_name() or p.user.username
            for p in obj.participants.filter(role=Participant.Role.SPEAKER)
        ]

    def get_duration_display(self, obj) -> str:
        """Get human-readable duration."""
        duration = obj.duration_minutes()
        if duration < 60:
            return f"{duration}m"
        hours = duration // 60
        minutes = duration % 60
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

    def get_is_live(self, obj) -> bool:
        """Check if session is currently live."""
        return obj.is_live()


class EventAttachmentSerializer(serializers.ModelSerializer):
    """Serializer for event attachments with security validation."""

    file_url = serializers.SerializerMethodField()
    file_size_display = serializers.SerializerMethodField()
    can_download = serializers.SerializerMethodField()

    class Meta:
        model = EventAttachment
        fields = [
            "id",
            "title",
            "description",
            "attachment_type",
            "file",
            "file_url",
            "file_size",
            "file_size_display",
            "is_public",
            "download_count",
            "can_download",
            "created_at",
        ]
        read_only_fields = ["id", "file_size", "download_count", "created_at"]

    def get_file_url(self, obj) -> Optional[str]:
        """Get secure file URL based on permissions."""
        if not obj.file:
            return None

        request = self.context.get("request")

        # Check if user has permission to access file
        if not self.get_can_download(obj):
            return None

        if request:
            return request.build_absolute_uri(obj.file.url)
        return obj.file.url

    def get_file_size_display(self, obj) -> str:
        """Get human-readable file size."""
        if not obj.file_size:
            return "Unknown"

        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def get_can_download(self, obj) -> bool:
        """Check if current user can download this attachment."""
        request = self.context.get("request")
        if not request:
            return obj.is_public

        user = request.user
        if isinstance(user, AnonymousUser):
            return obj.is_public

        # Event organizers can always download
        if user == obj.event.organizer or user in obj.event.collaborators.all():
            return True

        # Public files can be downloaded by registered participants
        if obj.is_public:
            return obj.event.participants.filter(user=user).exists()

        return False

    def validate_file(self, value):
        """Validate uploaded file."""
        if not value:
            return value

        # Check file size (10MB limit)
        if value.size > 10 * 1024 * 1024:
            raise ValidationError("File size cannot exceed 10MB.")

        # Check file type based on attachment type
        allowed_types = {
            EventAttachment.AttachmentType.DOCUMENT: [
                "application/pdf",
                "application/msword",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "text/plain",
            ],
            EventAttachment.AttachmentType.IMAGE: [
                "image/jpeg",
                "image/png",
                "image/gif",
                "image/webp",
            ],
            EventAttachment.AttachmentType.VIDEO: [
                "video/mp4",
                "video/avi",
                "video/mov",
                "video/wmv",
            ],
            EventAttachment.AttachmentType.AUDIO: [
                "audio/mpeg",
                "audio/wav",
                "audio/ogg",
            ],
        }

        attachment_type = None
        if hasattr(self, "initial_data") and self.initial_data:
            attachment_type = self.initial_data.get("type")
        if attachment_type and attachment_type in allowed_types:
            if value.content_type not in allowed_types[attachment_type]:
                raise ValidationError(
                    f"Invalid file type for {attachment_type}. "
                    f"Allowed types: {', '.join(allowed_types[attachment_type])}"
                )

        return value


class ExhibitorMinimalSerializer(serializers.ModelSerializer):
    """Minimal exhibitor serializer for performance."""

    logo_url = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Exhibitor
        fields = [
            "id",
            "company_name",
            "booth_number",
            "sponsorship_tier",
            "logo_url",
            "product_count",
            "is_featured",
        ]

    def get_logo_url(self, obj) -> Optional[str]:
        """Get exhibitor logo URL."""
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def get_product_count(self, obj) -> int:
        """Get count of exhibitor's products."""
        if hasattr(obj, "product_count_cache"):
            return obj.product_count_cache
        return obj.products.count()


class ProductMinimalSerializer(serializers.ModelSerializer):
    """Minimal product serializer for performance."""

    image_url = serializers.SerializerMethodField()
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "price",
            "price_display",
            "currency",
            "image_url",
            "category",
            "availability",
        ]

    def get_image_url(self, obj) -> Optional[str]:
        """Get product image URL."""
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None

    def get_price_display(self, obj) -> str:
        """Get formatted price display."""
        if obj.price is None:
            return "Free"
        return f"{obj.currency} {obj.price:,.2f}"


class EventAnalyticsSerializer(serializers.ModelSerializer):
    """Serializer for event analytics with computed metrics."""

    engagement_rate = serializers.SerializerMethodField()
    popular_sessions = serializers.SerializerMethodField()

    class Meta:
        model = EventAnalytics
        fields = [
            "id",
            "total_registrations",
            "confirmed_registrations",
            "cancelled_registrations",
            "waitlist_registrations",
            "total_attendance",
            "attendance_rate",
            "no_show_rate",
            "early_departure_rate",
            "avg_session_attendance",
            "session_completion_rate",
            "networking_connections",
            "chat_messages",
            "total_sessions",
            "avg_session_rating",
            "total_exhibitors",
            "total_products",
            "total_revenue",
            "avg_ticket_price",
            "sponsorship_revenue",
            "top_countries",
            "top_cities",
            "device_breakdown",
            "browser_breakdown",
            "peak_attendance_time",
            "avg_session_duration",
            "overall_satisfaction",
            "nps_score",
            "recommendation_rate",
            "last_calculated",
            "engagement_rate",
            "popular_sessions",
        ]
        read_only_fields = ["id", "last_calculated"]

    def get_engagement_rate(self, obj):
        """Calculate engagement rate (attendance/registrations)."""
        if obj.total_registrations == 0:
            return 0.0
        return round((obj.total_attendance / obj.total_registrations) * 100, 2)

    def get_popular_sessions(self, obj):
        """Get top 3 popular sessions by attendance."""
        sessions = (
            Session.objects.filter(event=obj.event)
            .annotate(participant_count=models.Count("attendees"))
            .order_by("-participant_count")[:3]
        )
        return SessionMinimalSerializer(sessions, many=True, context=self.context).data


class EventListSerializer(serializers.ModelSerializer):
    """Optimized serializer for event list views."""

    organizer = UserMinimalSerializer(read_only=True)
    categories = EventCategorySerializer(many=True, read_only=True)
    tags = EventTagSerializer(many=True, read_only=True)
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    participant_count = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    registration_status = serializers.SerializerMethodField()
    upcoming_session = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "name",  # Changed from "title" to match model
            "slug",
            "description",
            "type",  # Changed from "event_type" to match model
            "status",
            "start_date",
            "end_date",
            "timezone",
            "logo_url",
            "banner_url",
            "organizer",
            "categories",
            "tags",
            "capacity",  # Changed from "capacity" to match model
            "participant_count",
            "is_free",  # Changed from "registration_fee" to align with model's pricing field
            "currency",
            "is_featured",
            "is_favorited",
            "registration_status",
            "upcoming_session",
            "created_at",
            # "rating_avg" removed as it doesn't exist in the model
        ]

    def get_logo_url(self, obj):
        return obj.logo.url if obj.logo else None

    def get_banner_url(self, obj):
        return obj.banner.url if obj.banner else None

    def get_participant_count(self, obj):
        return obj.registration_count  # Maps to model's registration_count

    def get_is_favorited(self, obj):
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            return EventFavorite.objects.filter(event=obj, user=request.user).exists()
        return False

    def get_registration_status(self, obj):
        return "open" if obj.is_registration_open else "closed"

    def get_upcoming_session(self, obj):
        """Get the next upcoming session for this event."""
        try:
            session = (
                obj.sessions.filter(
                    start_time__gte=timezone.now(),
                    status=Session.SessionStatus.SCHEDULED,
                )
                .order_by("start_time")
                .first()
            )
            return SessionMinimalSerializer(session).data if session else None
        except Exception:
            return None


class EventDetailSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for event detail views."""

    organizer = UserMinimalSerializer(read_only=True)
    co_organizers = UserMinimalSerializer(many=True, read_only=True)
    categories = EventCategorySerializer(many=True, read_only=True)
    tags = EventTagSerializer(many=True, read_only=True)

    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    venue_map_url = serializers.SerializerMethodField()

    participant_count = serializers.SerializerMethodField()
    spots_remaining = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    registration_status = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_moderate = serializers.SerializerMethodField()

    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "raw_description",
            "type",
            "status",
            "visibility",
            "start_date",
            "end_date",
            "timezone",
            "location",
            "venue_name",
            "address",
            "capacity",
            "virtual_link",
            "logo_url",
            "banner_url",
            "venue_map_url",
            "organizer",
            "co_organizers",
            "categories",
            "tags",
            "is_free",
            "currency",
            "registration_start",
            "registration_end",
            "is_featured",
            "is_favorited",
            "registration_status",
            "can_edit",
            "can_moderate",
            "created_at",
            "updated_at",
            "participant_count",
            "spots_remaining",
        ]

    def get_logo_url(self, obj) -> Optional[str]:
        """Get event logo URL."""
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner_url(self, obj) -> Optional[str]:
        """Get event banner URL."""
        if obj.banner:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.banner.url)
        return None

    def get_venue_map_url(self, obj) -> Optional[str]:
        """Get venue map URL."""
        if obj.venue_map:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.venue_map.url)
        return None

    def get_participant_count(self, obj) -> int:
        """Get current participant count."""
        if hasattr(obj, "participant_count_cache"):
            return obj.participant_count_cache
        return obj.registration_count

    def get_spots_remaining(self, obj) -> float:
        """Get remaining spots for registration."""
        return obj.spots_remaining

    def get_is_favorited(self, obj) -> bool:
        """Check if current user has favorited this event."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            return False
        # Check if user has favorited the event
        if hasattr(obj, "is_favorited_cache"):
            return request.user.id in obj.is_favorited_cache
        return EventFavorite.objects.filter(user=request.user, event=obj).exists()

    def get_registration_status(self, obj) -> str:
        """Get registration status for the event."""
        return "open" if obj.is_registration_open else "closed"

    def get_can_edit(self, obj) -> bool:
        """Check if current user can edit this event."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            return False
        user = request.user
        return (
            user == obj.organizer
            or user in obj.co_organizers.all()
            or user.has_perm("change_event", obj)
        )

    def get_can_moderate(self, obj) -> bool:
        """Check if current user can moderate this event."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            return False
        user = request.user
        return (
            user == obj.organizer
            or user.has_perm("can_moderate_event", obj)
            or user.is_staff
        )


class EventCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating events with comprehensive validation."""

    category_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of category IDs",
    )
    tag_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of tag IDs",
    )
    co_organizer_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of co-organizer user IDs",
    )

    class Meta:
        model = Event
        fields = [
            "name",  # Changed from "title"
            "description",
            "raw_description",  # Changed from "full_description"
            "type",  # Changed from "event_type"
            "start_date",
            "end_date",
            "timezone",
            "location",
            "venue_name",
            "address",  # Changed from "venue_address"
            "capacity",  # Changed from "venue_capacity" and "capacity"
            "virtual_link",  # Changed from "virtual_link"
            "logo",
            "banner",  # Changed from "banner_image"
            "venue_map",
            "is_free",  # Changed from "registration_fee"
            "currency",
            "registration_start",  # Changed from "registration_start_date"
            "registration_end",  # Changed from "registration_end_date"
            "visibility",
            "category_ids",
            "tag_ids",
            "co_organizer_ids",
        ]

    def validate(self, attrs):
        """Comprehensive validation for event data."""
        errors = {}

        # Date validations
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")
        registration_start = attrs.get("registration_start")
        registration_end = attrs.get("registration_end")

        if start_date and end_date:
            if start_date >= end_date:
                errors["end_date"] = "End date must be after start date."

        if registration_start and registration_end:
            if registration_start >= registration_end:
                errors["registration_end"] = (
                    "Registration end date must be after registration start date."
                )

        if registration_end and start_date:
            if registration_end > start_date:
                errors["registration_end"] = (
                    "Registration must end before event starts."
                )

        # Event type-specific validations
        event_type = attrs.get("type")
        if event_type == Event.EventType.VIRTUAL and not attrs.get("virtual_link"):
            errors["virtual_link"] = "Virtual link is required for virtual events."

        if event_type in [
            Event.EventType.HYBRID,
            Event.EventType.CONFERENCE,
            Event.EventType.WORKSHOP,
            Event.EventType.SEMINAR,
            Event.EventType.MEETUP,
            Event.EventType.FAIR,
            Event.EventType.EXHIBITION,
        ]:
            if not attrs.get("venue_name") or not attrs.get("address"):
                errors["venue_name"] = (
                    "Venue information is required for in-person or hybrid events."
                )

        # Capacity validation
        capacity = attrs.get("capacity")
        if capacity is not None and capacity < 0:
            errors["capacity"] = "Capacity cannot be negative."

        # Fee validation
        is_free = attrs.get("is_free")
        if is_free is not None and is_free is False and not attrs.get("ticket_types"):
            errors["ticket_types"] = (
                "Ticket types must be specified for non-free events."
            )

        if errors:
            raise ValidationError(errors)

        return attrs

    def validate_category_ids(self, value):
        """Validate category IDs."""
        if not value:
            return value

        valid_categories = EventCategory.objects.filter(id__in=value).values_list(
            "id", flat=True
        )

        invalid_ids = set(value) - set(valid_categories)
        if invalid_ids:
            raise ValidationError(f"Invalid category IDs: {list(invalid_ids)}")

        return value

    def validate_tag_ids(self, value):
        """Validate tag IDs."""
        if not value:
            return value

        valid_tags = EventTag.objects.filter(id__in=value).values_list("id", flat=True)

        invalid_ids = set(value) - set(valid_tags)
        if invalid_ids:
            raise ValidationError(f"Invalid tag IDs: {list(invalid_ids)}")

        return value

    def validate_co_organizer_ids(self, value):
        """Validate co-organizer user IDs."""
        if not value:
            return value

        valid_users = User.objects.filter(id__in=value, is_active=True).values_list(
            "id", flat=True
        )

        invalid_ids = set(value) - set(valid_users)
        if invalid_ids:
            raise ValidationError(f"Invalid co-organizer IDs: {list(invalid_ids)}")

        return value

    @transaction.atomic
    def create(self, validated_data) -> Event:
        """Create event with related objects."""
        category_ids = validated_data.pop("category_ids", [])
        tag_ids = validated_data.pop("tag_ids", [])
        co_organizer_ids = validated_data.pop("co_organizer_ids", [])

        # Set organizer from request user
        request = self.context.get("request")
        if request and request.user.is_authenticated:
            validated_data["organizer"] = request.user
        else:
            raise PermissionDenied("Authentication required to create events.")

        # Set slug if not provided
        if "name" in validated_data and "slug" not in validated_data:
            validated_data["slug"] = slugify(validated_data["name"])

        event = Event.objects.create(**validated_data)

        # Create category relations through the relation model
        if category_ids:
            categories = EventCategory.objects.filter(id__in=category_ids)
            for i, category in enumerate(categories):
                EventCategoryRelation.objects.create(
                    event=event,
                    category=category,
                    is_primary=(i == 0),  # First category is primary
                )

        # Create tag relations through the relation model
        if tag_ids:
            tags = EventTag.objects.filter(id__in=tag_ids)
            for tag in tags:
                EventTagRelation.objects.create(event=event, tag=tag)

        # Set co-organizers
        if co_organizer_ids:
            event.co_organizers.set(User.objects.filter(id__in=co_organizer_ids))

        # Assign permissions to organizer
        assign_perm("change_event", request.user, event)
        assign_perm("delete_event", request.user, event)
        assign_perm("can_moderate_event", request.user, event)

        return event

    @transaction.atomic
    def update(self, instance, validated_data) -> Event:
        """Update event with related objects."""
        category_ids = validated_data.pop("category_ids", None)
        tag_ids = validated_data.pop("tag_ids", None)
        co_organizer_ids = validated_data.pop("co_organizer_ids", None)

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update category relations
        if category_ids is not None:
            # Remove existing relations
            EventCategoryRelation.objects.filter(event=instance).delete()
            # Create new relations
            categories = EventCategory.objects.filter(id__in=category_ids)
            for i, category in enumerate(categories):
                EventCategoryRelation.objects.create(
                    event=instance, category=category, is_primary=(i == 0)
                )

        # Update tag relations
        if tag_ids is not None:
            # Remove existing relations
            EventTagRelation.objects.filter(event=instance).delete()
            # Create new relations
            tags = EventTag.objects.filter(id__in=tag_ids)
            for tag in tags:
                EventTagRelation.objects.create(event=instance, tag=tag)

        # Update co-organizers
        if co_organizer_ids is not None:
            instance.co_organizers.set(User.objects.filter(id__in=co_organizer_ids))

        return instance


class SessionSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for sessions with speaker management."""

    speakers = UserMinimalSerializer(many=True, read_only=True)
    speaker_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False,
        help_text="List of speaker user IDs",
    )
    participant_count = serializers.SerializerMethodField()
    duration_display = serializers.SerializerMethodField()
    is_live = serializers.SerializerMethodField()
    can_attend = serializers.SerializerMethodField()
    user_attendance_status = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            "id",
            "event",
            "title",
            "description",
            "type",
            "status",
            "start_time",
            "end_time",
            "capacity",
            "speakers",
            "speaker_ids",
            "participant_count",
            "duration_display",
            "is_live",
            "can_attend",
            "user_attendance_status",
            "is_featured",
            "rating_avg",
            "location",
            "virtual_link",
            "recording_url",
            "materials",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "rating_avg", "created_at", "updated_at"]

    def get_participant_count(self, obj) -> int:
        """Get current participant count for session."""
        if hasattr(obj, "participant_count_cache"):
            return obj.participant_count_cache
        return obj.participants.filter(
            registration_status=Participant.RegistrationStatus.CONFIRMED
        ).count()

    def get_duration_display(self, obj) -> str:
        """Get human-readable duration."""
        duration = obj.duration_minutes()
        if duration < 60:
            return f"{duration}m"
        hours = duration // 60
        minutes = duration % 60
        return f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"

    def get_is_live(self, obj) -> bool:
        """Check if session is currently live."""
        return obj.is_live()

    def get_can_attend(self, obj) -> bool:
        """Check if user can attend this session."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            return False

        # Check if user is registered for the event
        event_participant = obj.event.participants.filter(
            user=request.user,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        ).first()

        if not event_participant:
            return False

        # Check if session has capacity
        if obj.capacity:
            current_count = self.get_participant_count(obj)
            if current_count >= obj.capacity:
                return False

        return True

    def get_user_attendance_status(self, obj):
        """Get user's attendance status for this session."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            return None

        # Check if user has attended this session
        participant = Participant.objects.filter(
            user=request.user, event=obj.event, sessions_attended=obj
        ).first()

        if participant:
            return participant.attendance_status
        return None

    def validate(self, attrs):
        """Validate session data."""
        errors = {}

        start_time = attrs.get("start_time")
        end_time = attrs.get("end_time")

        if start_time and end_time:
            if start_time >= end_time:
                errors["end_time"] = "End time must be after start time."

        # Validate session is within event timeframe
        event = attrs.get("event")
        if event and start_time:
            if start_time < event.start_date:
                errors["start_time"] = "Session cannot start before event starts."
            if end_time and end_time > event.end_date:
                errors["end_time"] = "Session cannot end after event ends."

        # Validate session type specific requirements
        session_type = attrs.get("type")
        if session_type in [
            Session.SessionType.KEYNOTE,
            Session.SessionType.PRESENTATION,
        ] and not attrs.get("virtual_link"):
            errors["virtual_link"] = "Virtual link is required for online sessions."

        if errors:
            raise ValidationError(errors)

        return attrs

    def validate_speaker_ids(self, value):
        """Validate speaker user IDs."""
        if not value:
            return value

        valid_users = User.objects.filter(id__in=value, is_active=True).values_list(
            "id", flat=True
        )

        invalid_ids = set(value) - set(valid_users)
        if invalid_ids:
            raise ValidationError(f"Invalid user IDs: {list(invalid_ids)}")

        return value

    @transaction.atomic
    def create(self, validated_data) -> Session:
        """Create session with speakers."""
        speaker_ids = validated_data.pop("speaker_ids", [])
        session = Session.objects.create(**validated_data)

        # Create speaker participants
        if speaker_ids:
            speakers = User.objects.filter(id__in=speaker_ids, is_active=True)
            for speaker in speakers:
                Participant.objects.get_or_create(
                    user=speaker,
                    event=session.event,
                    defaults={
                        "role": Participant.Role.SPEAKER,
                        "registration_status": Participant.RegistrationStatus.CONFIRMED,
                    },
                )

        return session

    @transaction.atomic
    def update(self, instance, validated_data) -> Session:
        """Update session with speakers."""
        speaker_ids = validated_data.pop("speaker_ids", None)

        # Update basic fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update speakers if provided
        if speaker_ids is not None:
            # Remove existing speaker participants for this session
            Participant.objects.filter(
                event=instance.event, role=Participant.Role.SPEAKER, sessions=instance
            ).delete()

            # Add new speakers
            speakers = User.objects.filter(id__in=speaker_ids, is_active=True)
            for speaker in speakers:
                participant, created = Participant.objects.get_or_create(
                    user=speaker,
                    event=instance.event,
                    defaults={
                        "role": Participant.Role.SPEAKER,
                        "registration_status": Participant.RegistrationStatus.CONFIRMED,
                    },
                )

        return instance


class ParticipantSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for event participants."""

    user = UserMinimalSerializer(read_only=True)
    event_title = serializers.CharField(source="event.name", read_only=True)
    badges = serializers.SerializerMethodField()
    sessions_count = serializers.SerializerMethodField()
    attendance_rate = serializers.SerializerMethodField()

    class Meta:
        model = Participant
        fields = [
            "id",
            "user",
            "event",
            "event_title",
            "role",
            "registration_status",
            "attendance_status",
            "registration_data",
            "check_in_time",
            "check_out_time",
            "notes",
            "badges",
            "sessions_count",
            "attendance_rate",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "check_in_time",
            "check_out_time",
            "created_at",
            "updated_at",
        ]

    def get_badges(self, obj) -> List[Dict]:
        """Get participant's earned badges."""
        badges = ParticipantBadge.objects.filter(participant=obj).select_related(
            "badge"
        )
        return [
            {
                "badge_id": pb.badge.id,
                "badge_name": pb.badge.name,
                "badge_description": pb.badge.description,
                "badge_icon": pb.badge.icon.url if pb.badge.icon else None,
                "earned_at": pb.earned_at,
                "reason": pb.reason,
            }
            for pb in badges
        ]

    def get_sessions_count(self, obj) -> int:
        """Get count of sessions participant is registered for."""
        return obj.sessions.count()

    def get_attendance_rate(self, obj) -> float:
        """Calculate participant's attendance rate."""
        total_sessions = obj.sessions.count()
        if total_sessions == 0:
            return 0.0

        attended_sessions = obj.sessions.filter(
            # This would need to be tracked via session attendance
            # For now, we'll use a placeholder
        ).count()

        return round((attended_sessions / total_sessions) * 100, 2)


class ExhibitorSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for exhibitors."""

    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()
    products = ProductMinimalSerializer(many=True, read_only=True)
    product_count = serializers.SerializerMethodField()
    primary_contact = UserMinimalSerializer(read_only=True)

    class Meta:
        model = Exhibitor
        fields = [
            "id",
            "event",
            "company_name",
            "slug",
            "description",
            "raw_description",
            "logo",
            "banner",
            "gallery",
            "logo_url",
            "banner_url",
            "booth_number",
            "booth_size",
            "booth_location",
            "booth_map_coordinates",
            "website",
            "contact_email",
            "contact_phone",
            "social_links",
            "primary_contact",
            "representatives",
            "sponsorship_tier",
            "sponsorship_amount",
            "sponsorship_benefits",
            "status",
            "view_count",
            "connection_count",
            "lead_count",
            "products",
            "product_count",
            "created_at",
            "updated_at",
            "approved_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "view_count",
            "connection_count",
            "lead_count",
            "created_at",
            "updated_at",
            "approved_at",
        ]

    def get_logo_url(self, obj) -> Optional[str]:
        """Get exhibitor logo URL."""
        if obj.logo:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner_url(self, obj) -> Optional[str]:
        """Get exhibitor banner URL."""
        if obj.banner:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.banner.url)
        return None

    def get_product_count(self, obj) -> int:
        """Get count of exhibitor's products."""
        if hasattr(obj, "product_count_cache"):
            return obj.product_count_cache
        return obj.products.filter(is_active=True).count()

    def validate_contact_email(self, value):
        """Validate contact email format."""
        if value and "@" not in value:
            raise ValidationError("Enter a valid email address.")
        return value

    def validate_website_url(self, value):
        """Validate website URL format."""
        if value and not (value.startswith("http://") or value.startswith("https://")):
            raise ValidationError("Enter a valid URL starting with http:// or https://")
        return value


class ProductSerializer(serializers.ModelSerializer):
    """Comprehensive serializer for products."""

    exhibitor_name = serializers.CharField(
        source="exhibitor.company_name", read_only=True
    )
    image_url = serializers.SerializerMethodField()
    price_display = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "exhibitor",
            "event",
            "exhibitor_name",
            "name",
            "slug",
            "description",
            "raw_description",
            "image",
            "image_url",
            "gallery",
            "category",
            "price",
            "currency",
            "price_display",
            "availability",
            "features",
            "specifications",
            "website",
            "demo_url",
            "documentation_url",
            "brochure",
            "view_count",
            "favorite_count",
            "inquiry_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "slug",
            "view_count",
            "favorite_count",
            "inquiry_count",
            "created_at",
            "updated_at",
        ]

    def get_image_url(self, obj) -> Optional[str]:
        """Get product image URL."""
        if obj.image:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.image.url)
        return None

    def get_price_display(self, obj) -> str:
        """Get formatted price display."""
        if obj.price is None:
            return "Free"
        return f"{obj.currency} {obj.price:,.2f}"

    def validate_price(self, value):
        """Validate price is not negative."""
        if value is not None and value < 0:
            raise ValidationError("Price cannot be negative.")
        return value

    def validate_stock_quantity(self, value):
        """Validate stock quantity is not negative."""
        if value is not None and value < 0:
            raise ValidationError("Stock quantity cannot be negative.")
        return value


class SessionRatingSerializer(serializers.ModelSerializer):
    """Serializer for session ratings with validation."""

    participant_name = serializers.SerializerMethodField()
    session_title = serializers.CharField(source="session.title", read_only=True)

    class Meta:
        model = SessionRating
        fields = [
            "id",
            "session",
            "session_title",
            "participant",
            "participant_name",
            "rating",
            "review",
            "helpful_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_participant_name(self, obj) -> str:
        """Get participant's display name."""
        return obj.participant.user.get_full_name() or obj.participant.user.username

    def validate_rating(self, value):
        """Validate rating is within valid range."""
        if not (1 <= value <= 5):
            raise ValidationError("Rating must be between 1 and 5.")
        return value

    def validate(self, attrs):
        """Validate user can rate this session."""
        request = self.context.get("request")
        if not request or isinstance(request.user, AnonymousUser):
            raise PermissionDenied("Authentication required to rate sessions.")

        session = attrs.get("session")
        if not session:
            raise ValidationError("Session is required.")

        # Check if user is a participant in the event
        participant = session.event.participants.filter(user=request.user).first()
        if not participant:
            raise ValidationError("You must be a participant to rate sessions.")

        attrs["participant"] = participant

        # Check if user has already rated this session
        if SessionRating.objects.filter(
            session=session, participant__user=request.user
        ).exists():
            raise ValidationError("You have already rated this session.")

        return attrs


class EventBadgeSerializer(serializers.ModelSerializer):
    """Serializer for event badges."""

    icon_url = serializers.SerializerMethodField()

    class Meta:
        model = EventBadge
        fields = [
            "id",
            "name",
            "description",
            "icon",
            "icon_url",
            "color",
            "criteria",
            "points_required",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id"]

    def get_icon_url(self, obj) -> Optional[str]:
        """Get badge icon URL."""
        if obj.icon:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.icon.url)
        return None


class ParticipantBadgeSerializer(serializers.ModelSerializer):
    """Serializer for participant badges."""

    badge = EventBadgeSerializer(read_only=True)
    participant_name = serializers.SerializerMethodField()

    class Meta:
        model = ParticipantBadge
        fields = [
            "id",
            "participant",
            "participant_name",
            "badge",
            "earned_at",
            "reason",
        ]
        read_only_fields = ["id", "earned_at"]

    def get_participant_name(self, obj) -> str:
        """Get participant's display name."""
        return obj.participant.user.get_full_name() or obj.participant.user.username


class EventFavoriteSerializer(serializers.ModelSerializer):
    """Serializer for event favorites."""

    event = EventListSerializer(read_only=True)

    class Meta:
        model = EventFavorite
        fields = ["id", "event", "created_at"]
        read_only_fields = ["id", "created_at"]


class EventViewSerializer(serializers.ModelSerializer):
    """Serializer for event views tracking."""

    class Meta:
        model = EventView
        fields = ["id", "event", "user", "ip_address", "user_agent", "created_at"]
        read_only_fields = ["id", "created_at"]


class EventModerationLogSerializer(serializers.ModelSerializer):
    """Serializer for event moderation logs."""

    moderator = UserMinimalSerializer(read_only=True)
    event_title = serializers.CharField(source="event.title", read_only=True)

    class Meta:
        model = EventModerationLog
        fields = [
            "id",
            "event",
            "event_title",
            "moderator",
            "action_type",
            "reason",
            "details",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]

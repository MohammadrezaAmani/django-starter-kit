import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, F, Prefetch, Q
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.views.decorators.vary import vary_on_headers
from django_filters import rest_framework as django_filters
from django_filters.rest_framework import DjangoFilterBackend
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, extend_schema_view
from guardian.shortcuts import assign_perm, get_objects_for_user
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import (
    Event,
    EventAnalytics,
    EventCategory,
    EventFavorite,
    EventModerationLog,
    EventTag,
    EventView,
    Exhibitor,
    Participant,
    Product,
    Session,
    SessionRating,
)
from .permissions import (
    CanModerateEvent,
    IsEventOrganizerOrCollaborator,
    IsOwnerOrReadOnly,
)
from .serializers import (
    EventAnalyticsSerializer,
    EventCategorySerializer,
    EventCreateUpdateSerializer,
    EventDetailSerializer,
    EventFavoriteSerializer,
    EventListSerializer,
    EventTagSerializer,
    ExhibitorSerializer,
    ParticipantBadgeSerializer,
    ParticipantSerializer,
    ProductSerializer,
    SessionRatingSerializer,
    SessionSerializer,
)

logger = logging.getLogger(__name__)
User = get_user_model()


class StandardResultsSetPagination(PageNumberPagination):
    """Standard pagination for API responses."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class EventThrottle:
    """Custom throttling for event endpoints."""

    scope = "events"

    @staticmethod
    def get_cache_key(request, view):
        if request.user.is_authenticated:
            return f"throttle_{view.__class__.__name__}_{request.user.id}"
        return f"throttle_{view.__class__.__name__}_{request.META.get('REMOTE_ADDR')}"


class EventFilter(django_filters.FilterSet):
    """Advanced filtering for events."""

    title = django_filters.CharFilter(lookup_expr="icontains")
    description = django_filters.CharFilter(lookup_expr="icontains")
    event_type = django_filters.ChoiceFilter(choices=Event.EventType.choices)
    status = django_filters.MultipleChoiceFilter(choices=Event.EventStatus.choices)
    visibility = django_filters.ChoiceFilter(choices=Event.Visibility.choices)

    start_date_after = django_filters.DateTimeFilter(
        field_name="start_date", lookup_expr="gte"
    )
    start_date_before = django_filters.DateTimeFilter(
        field_name="start_date", lookup_expr="lte"
    )
    end_date_after = django_filters.DateTimeFilter(
        field_name="end_date", lookup_expr="gte"
    )
    end_date_before = django_filters.DateTimeFilter(
        field_name="end_date", lookup_expr="lte"
    )

    categories = django_filters.ModelMultipleChoiceFilter(
        field_name="eventcategoryrelation__category",
        queryset=EventCategory.objects.all(),
        to_field_name="id",
    )
    tags = django_filters.ModelMultipleChoiceFilter(
        field_name="eventtagrelation__tag",
        queryset=EventTag.objects.all(),
        to_field_name="id",
    )

    organizer = django_filters.ModelChoiceFilter(queryset=User.objects.all())

    is_free = django_filters.BooleanFilter(method="filter_is_free")
    registration_open = django_filters.BooleanFilter(method="filter_registration_open")
    has_capacity = django_filters.BooleanFilter(method="filter_has_capacity")

    min_price = django_filters.NumberFilter(
        field_name="registration_fee", lookup_expr="gte"
    )
    max_price = django_filters.NumberFilter(
        field_name="registration_fee", lookup_expr="lte"
    )

    location = django_filters.CharFilter(lookup_expr="icontains")
    city = django_filters.CharFilter(field_name="location", lookup_expr="icontains")

    is_featured = django_filters.BooleanFilter()

    class Meta:
        model = Event
        fields = [
            "title",
            "description",
            "event_type",
            "status",
            "visibility",
            "start_date_after",
            "start_date_before",
            "end_date_after",
            "end_date_before",
            "categories",
            "tags",
            "organizer",
            "is_free",
            "registration_open",
            "has_capacity",
            "min_price",
            "max_price",
            "location",
            "city",
            "is_featured",
        ]

    def filter_is_free(self, queryset, name, value):
        """Filter events by free/paid status."""
        if value is True:
            return queryset.filter(
                Q(registration_fee__isnull=True) | Q(registration_fee=0)
            )
        elif value is False:
            return queryset.filter(
                registration_fee__isnull=False, registration_fee__gt=0
            )
        return queryset

    def filter_registration_open(self, queryset, name, value):
        """Filter events by registration status."""
        now = timezone.now()
        if value is True:
            return queryset.filter(
                Q(registration_start_date__isnull=True)
                | Q(registration_start_date__lte=now),
                Q(registration_end_date__isnull=True)
                | Q(registration_end_date__gte=now),
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            )
        elif value is False:
            return queryset.filter(
                Q(registration_end_date__lt=now) | Q(status=Event.EventStatus.CANCELLED)
            )
        return queryset

    def filter_has_capacity(self, queryset, name, value):
        """Filter events by available capacity."""
        if value is True:
            return queryset.annotate(
                participant_count=Count(
                    "participants",
                    filter=Q(
                        participants__registration_status=Participant.RegistrationStatus.CONFIRMED
                    ),
                )
            ).filter(
                Q(max_participants__isnull=True)
                | Q(participant_count__lt=F("max_participants"))
            )
        elif value is False:
            return queryset.annotate(
                participant_count=Count(
                    "participants",
                    filter=Q(
                        participants__registration_status=Participant.RegistrationStatus.CONFIRMED
                    ),
                )
            ).filter(
                max_participants__isnull=False,
                participant_count__gte=F("max_participants"),
            )
        return queryset


@extend_schema_view(
    list=extend_schema(
        summary="List events",
        description="Get a paginated list of events with filtering and search capabilities.",
    ),
    retrieve=extend_schema(
        summary="Get event details",
        description="Get detailed information about a specific event.",
    ),
    create=extend_schema(
        summary="Create event",
        description="Create a new event. Only authenticated users can create events.",
    ),
    update=extend_schema(
        summary="Update event",
        description="Update an existing event. Only organizers and collaborators can update events.",
    ),
    destroy=extend_schema(
        summary="Delete event",
        description="Delete an event. Only organizers can delete events.",
    ),
)
class EventViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing events with comprehensive security and performance optimizations.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = EventFilter
    search_fields = ["title", "description", "location", "venue_name"]
    ordering_fields = [
        "start_date",
        "end_date",
        "created_at",
        "updated_at",
        "registration_fee",
        "average_rating",
    ]
    ordering = ["-created_at"]
    pagination_class = StandardResultsSetPagination

    def get_serializer_class(self):
        """Return appropriate serializer based on action."""
        if self.action == "list":
            return EventListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return EventCreateUpdateSerializer
        return EventDetailSerializer

    def get_queryset(self):
        """
        Get optimized queryset with proper prefetching and permission filtering.
        """
        queryset = (
            Event.objects.select_related("organizer")
            .prefetch_related(
                "eventcategoryrelation__category",
                "eventtagrelation__tag",
                "co_organizers",
                Prefetch(
                    "participants",
                    queryset=Participant.objects.select_related("user").filter(
                        registration_status=Participant.RegistrationStatus.CONFIRMED
                    ),
                ),
                Prefetch(
                    "sessions",
                    queryset=Session.objects.filter(is_featured=True).order_by(
                        "start_time"
                    )[:3],
                ),
            )
            .annotate(
                participant_count=Count(
                    "participants",
                    filter=Q(
                        participants__registration_status=Participant.RegistrationStatus.CONFIRMED
                    ),
                ),
                session_count=Count("sessions"),
                average_rating=Avg("sessions__ratings__rating"),
            )
        )

        user = self.request.user

        # Apply visibility and permission filters
        if user.is_authenticated:
            # Users can see public events, their own events, and events they have permissions for
            try:
                accessible_events = get_objects_for_user(
                    user,
                    "view_event",
                    klass=Event.objects.all(),
                    accept_global_perms=False,
                )
                accessible_event_ids = list(
                    accessible_events.values_list("id", flat=True)
                )
            except Exception:
                accessible_event_ids = []

            queryset = queryset.filter(
                Q(visibility=Event.Visibility.PUBLIC)
                | Q(organizer=user)
                | Q(co_organizers=user)
                | Q(id__in=accessible_event_ids)
            ).distinct()
        else:
            # Anonymous users can only see public published events
            queryset = queryset.filter(
                visibility=Event.Visibility.PUBLIC,
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            )

        # Filter by status for non-staff users
        if not user.is_staff:
            queryset = queryset.filter(
                status__in=[
                    Event.EventStatus.PUBLISHED,
                    Event.EventStatus.LIVE,
                    Event.EventStatus.COMPLETED,
                ]
            )

        return queryset.filter(is_active=True)

    def get_permissions(self):
        """
        Instantiate and return the list of permissions required for this action.
        """
        if self.action == "create":
            permission_classes = [permissions.IsAuthenticated]
        elif self.action in ["update", "partial_update"]:
            permission_classes = [IsEventOrganizerOrCollaborator]
        elif self.action == "destroy":
            permission_classes = [IsOwnerOrReadOnly]
        elif self.action in ["moderate", "analytics"]:
            permission_classes = [CanModerateEvent]
        else:
            permission_classes = [permissions.AllowAny]

        return [permission() for permission in permission_classes]

    @method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST"))
    @transaction.atomic
    def perform_create(self, serializer):
        """Create event with proper permissions and logging."""
        event = serializer.save()

        # Assign permissions to organizer
        assign_perm("view_event", self.request.user, event)
        assign_perm("change_event", self.request.user, event)
        assign_perm("delete_event", self.request.user, event)
        assign_perm("can_moderate_event", self.request.user, event)

        # Create initial analytics
        EventAnalytics.objects.create(event=event)

        # Log activity
        logger.info(f"Event created: {event.name} by {self.request.user.username}")

    @method_decorator(ratelimit(key="user_or_ip", rate="20/m", method="PATCH"))
    def perform_update(self, serializer):
        """Update event with validation and logging."""
        old_status = serializer.instance.status
        event = serializer.save()

        # Log status changes
        if old_status != event.status:
            EventModerationLog.objects.create(
                event=event,
                moderator=self.request.user,
                action=EventModerationLog.ActionType.APPROVE,
                reason=f"Status changed from {old_status} to {event.status}",
            )

        logger.info(f"Event updated: {event.name} by {self.request.user.username}")

    def perform_destroy(self, instance):
        """Soft delete event and log action."""
        instance.is_active = False
        instance.status = Event.EventStatus.CANCELLED
        instance.save()

        # Log deletion
        EventModerationLog.objects.create(
            event=instance,
            moderator=self.request.user,
            action=EventModerationLog.ActionType.DELETE,
            reason="Event deleted by organizer",
        )

        logger.info(f"Event deleted: {instance.title} by {self.request.user.username}")

    @method_decorator(cache_page(60 * 5))  # Cache for 5 minutes
    @method_decorator(vary_on_headers("User-Agent"))
    def retrieve(self, request, *args, **kwargs):
        """Retrieve event with view tracking."""
        instance = self.get_object()

        # Track view asynchronously
        self._track_event_view(instance, request)

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _track_event_view(self, event: Event, request) -> None:
        """Track event view for analytics."""
        try:
            # Only track unique views per user/IP per day
            cache_key = f"event_view_{event.id}_{request.user.id if request.user.is_authenticated else request.META.get('REMOTE_ADDR')}"

            if not cache.get(cache_key):
                EventView.objects.create(
                    event=event,
                    user=request.user if request.user.is_authenticated else None,
                    ip_address=request.META.get("REMOTE_ADDR"),
                    user_agent=request.META.get("HTTP_USER_AGENT", "")[:200],
                )

                # Update analytics
                analytics, created = EventAnalytics.objects.get_or_create(event=event)
                analytics.total_views = F("total_views") + 1
                if not cache.get(f"unique_view_{cache_key}"):
                    analytics.unique_views = F("unique_views") + 1
                    cache.set(
                        f"unique_view_{cache_key}", True, 60 * 60 * 24
                    )  # 24 hours
                analytics.save()

                # Set cache to prevent duplicate tracking
                cache.set(cache_key, True, 60 * 60)  # 1 hour

        except Exception as e:
            logger.error(f"Error tracking event view: {e}")

    @extend_schema(
        summary="Register for event",
        description="Register the authenticated user for an event.",
        request=None,
        responses={201: ParticipantSerializer},
    )
    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    @method_decorator(ratelimit(key="user", rate="5/m", method="POST"))
    @transaction.atomic
    def register(self, request, pk=None):
        """Register user for event with comprehensive validation."""
        event = self.get_object()
        user = request.user

        # Validation checks
        if not event.is_registration_open():
            return Response(
                {"error": "Registration is not open for this event."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if user is already registered
        existing_participant = Participant.objects.filter(
            user=user, event=event
        ).first()

        if existing_participant:
            if (
                existing_participant.registration_status
                == Participant.RegistrationStatus.CONFIRMED
            ):
                return Response(
                    {"error": "You are already registered for this event."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            elif (
                existing_participant.registration_status
                == Participant.RegistrationStatus.CANCELLED
            ):
                # Reactivate cancelled registration
                existing_participant.registration_status = (
                    Participant.RegistrationStatus.CONFIRMED
                )
                existing_participant.save()

                serializer = ParticipantSerializer(
                    existing_participant, context={"request": request}
                )
                return Response(serializer.data, status=status.HTTP_200_OK)

        # Check capacity
        if event.spots_remaining() is not None and event.spots_remaining() <= 0:
            return Response(
                {"error": "This event has reached its maximum capacity."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if event requires approval (implement business logic)
        registration_status = Participant.RegistrationStatus.CONFIRMED

        # Create participant
        participant = Participant.objects.create(
            user=user,
            event=event,
            role=Participant.Role.ATTENDEE,
            registration_status=registration_status,
            registration_data=request.data.get("registration_data", {}),
        )

        # Update analytics
        analytics, created = EventAnalytics.objects.get_or_create(event=event)
        analytics.total_registrations = F("total_registrations") + 1
        analytics.save()

        # Log registration
        logger.info(f"User {user.username} registered for event {event.title}")

        serializer = ParticipantSerializer(participant, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Unregister from event",
        description="Cancel registration for an event.",
        request=None,
        responses={200: {"description": "Successfully unregistered"}},
    )
    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    @method_decorator(ratelimit(key="user", rate="10/m", method="POST"))
    @transaction.atomic
    def unregister(self, request, pk=None):
        """Unregister user from event."""
        event = self.get_object()
        user = request.user

        try:
            participant = Participant.objects.get(
                user=user,
                event=event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )
        except Participant.DoesNotExist:
            return Response(
                {"error": "You are not registered for this event."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check cancellation policy (implement business logic)
        hours_until_event = (event.start_date - timezone.now()).total_seconds() / 3600
        if hours_until_event < 24:  # Less than 24 hours
            return Response(
                {
                    "error": "Cannot cancel registration less than 24 hours before the event."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Cancel registration
        participant.registration_status = Participant.RegistrationStatus.CANCELLED
        participant.save()

        # Log cancellation
        logger.info(f"User {user.username} unregistered from event {event.title}")

        return Response(
            {"message": "Successfully unregistered from the event."},
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Get event sessions",
        description="Get all sessions for an event.",
        responses={200: SessionSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def sessions(self, request, pk=None):
        """Get event sessions with optimized query."""
        event = self.get_object()

        sessions = (
            Session.objects.filter(event=event)
            .select_related("event")
            .prefetch_related("participants__user")
            .annotate(
                participant_count=Count("participants"),
                average_rating=Avg("ratings__rating"),
            )
            .order_by("start_time")
        )

        # Apply filters
        session_type = request.query_params.get("type")
        if session_type:
            sessions = sessions.filter(session_type=session_type)

        status_filter = request.query_params.get("status")
        if status_filter:
            sessions = sessions.filter(status=status_filter)

        page = self.paginate_queryset(sessions)
        if page is not None:
            serializer = SessionSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)

        serializer = SessionSerializer(
            sessions, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Get event participants",
        description="Get all participants for an event. Only accessible to organizers and collaborators.",
        responses={200: ParticipantSerializer(many=True)},
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsEventOrganizerOrCollaborator],
    )
    def participants(self, request, pk=None):
        """Get event participants (organizers only)."""
        event = self.get_object()

        participants = (
            Participant.objects.filter(event=event)
            .select_related("user")
            .prefetch_related("badges__badge")
            .order_by("-created_at")
        )

        # Apply filters
        role_filter = request.query_params.get("role")
        if role_filter:
            participants = participants.filter(role=role_filter)

        status_filter = request.query_params.get("status")
        if status_filter:
            participants = participants.filter(registration_status=status_filter)

        page = self.paginate_queryset(participants)
        if page is not None:
            serializer = ParticipantSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)

        serializer = ParticipantSerializer(
            participants, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Toggle event favorite",
        description="Add or remove event from user's favorites.",
        request=None,
        responses={
            201: {"description": "Added to favorites"},
            204: {"description": "Removed from favorites"},
        },
    )
    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    @method_decorator(ratelimit(key="user", rate="20/m", method="POST"))
    def favorite(self, request, pk=None):
        """Toggle event favorite status."""
        event = self.get_object()
        user = request.user

        favorite, created = EventFavorite.objects.get_or_create(user=user, event=event)

        if not created:
            favorite.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        serializer = EventFavoriteSerializer(favorite, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        summary="Get featured events",
        description="Get a list of featured events.",
        responses={200: EventListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    @method_decorator(cache_page(60 * 15))  # Cache for 15 minutes
    def featured(self, request):
        """Get featured events."""
        events = (
            self.get_queryset()
            .filter(
                is_featured=True,
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            )
            .order_by("-created_at")[:10]
        )

        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Get trending events",
        description="Get trending events based on recent activity.",
        responses={200: EventListSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    @method_decorator(cache_page(60 * 10))  # Cache for 10 minutes
    def trending(self, request):
        """Get trending events based on recent activity."""
        # Calculate trending score based on recent registrations, views, and ratings
        one_week_ago = timezone.now() - timedelta(days=7)

        events = (
            self.get_queryset()
            .filter(
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
                start_date__gte=timezone.now(),
            )
            .annotate(
                recent_registrations=Count(
                    "participants", filter=Q(participants__created_at__gte=one_week_ago)
                ),
                recent_views=Count(
                    "views", filter=Q(views__created_at__gte=one_week_ago)
                ),
                trending_score=F("recent_registrations") * 3 + F("recent_views"),
            )
            .filter(trending_score__gt=0)
            .order_by("-trending_score")[:20]
        )

        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Get user's events",
        description="Get events organized by or participated in by the authenticated user.",
        responses={200: EventListSerializer(many=True)},
    )
    @action(
        detail=False, methods=["get"], permission_classes=[permissions.IsAuthenticated]
    )
    def my_events(self, request):
        """Get user's events (organized or participating)."""
        user = request.user
        event_type = request.query_params.get("type", "all")

        if event_type == "organized":
            events = (
                self.get_queryset()
                .filter(Q(organizer=user) | Q(collaborators=user))
                .distinct()
            )
        elif event_type == "participating":
            events = self.get_queryset().filter(
                participants__user=user,
                participants__registration_status=Participant.RegistrationStatus.CONFIRMED,
            )
        elif event_type == "favorites":
            events = self.get_queryset().filter(favorites__user=user)
        else:
            events = (
                self.get_queryset()
                .filter(
                    Q(organizer=user)
                    | Q(collaborators=user)
                    | Q(
                        participants__user=user,
                        participants__registration_status=Participant.RegistrationStatus.CONFIRMED,
                    )
                    | Q(favorites__user=user)
                )
                .distinct()
            )

        page = self.paginate_queryset(events)
        if page is not None:
            serializer = EventListSerializer(
                page, many=True, context={"request": request}
            )
            return self.get_paginated_response(serializer.data)

        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)

    @extend_schema(
        summary="Get event analytics",
        description="Get detailed analytics for an event. Only accessible to organizers and collaborators.",
        responses={200: EventAnalyticsSerializer},
    )
    @action(
        detail=True,
        methods=["get"],
        permission_classes=[IsEventOrganizerOrCollaborator],
    )
    def analytics(self, request, pk=None):
        """Get event analytics (organizers only)."""
        event = self.get_object()

        analytics, created = EventAnalytics.objects.get_or_create(event=event)

        if created or analytics.should_recalculate():
            analytics.recalculate()

        serializer = EventAnalyticsSerializer(analytics, context={"request": request})
        return Response(serializer.data)


class EventCategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for event categories."""

    queryset = EventCategory.objects.all().order_by("name")
    serializer_class = EventCategorySerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None  # No pagination for categories

    @extend_schema(
        summary="Get events in category",
        description="Get all events in a specific category.",
        responses={200: EventListSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def events(self, request, pk=None):
        """Get events in category."""
        category = self.get_object()

        # Get events in this category and its descendants
        descendant_categories = category.get_descendants(include_self=True)

        events = (
            Event.objects.filter(
                categories__category__in=descendant_categories,
                is_active=True,
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            )
            .select_related("organizer")
            .prefetch_related("categories__category", "tags__tag")
            .distinct()
            .order_by("-created_at")
        )

        # Apply standard event filtering
        event_viewset = EventViewSet()
        event_viewset.request = request
        events = event_viewset.filter_queryset(events)

        page = event_viewset.paginate_queryset(events)
        if page is not None:
            serializer = EventListSerializer(
                page, many=True, context={"request": request}
            )
            return event_viewset.get_paginated_response(serializer.data)

        serializer = EventListSerializer(
            events, many=True, context={"request": request}
        )
        return Response(serializer.data)


class EventTagViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for event tags."""

    queryset = EventTag.objects.all().order_by("name")
    serializer_class = EventTagSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "description"]

    @extend_schema(
        summary="Get trending tags",
        description="Get trending event tags based on recent usage.",
        responses={200: EventTagSerializer(many=True)},
    )
    @action(detail=False, methods=["get"])
    @method_decorator(cache_page(60 * 30))  # Cache for 30 minutes
    def trending(self, request):
        """Get trending tags."""
        one_month_ago = timezone.now() - timedelta(days=30)

        trending_tags = (
            EventTag.objects.filter(
                events__created_at__gte=one_month_ago,
                events__status__in=[
                    Event.EventStatus.PUBLISHED,
                    Event.EventStatus.LIVE,
                ],
            )
            .annotate(usage_count=Count("events"))
            .order_by("-usage_count")[:20]
        )

        serializer = self.get_serializer(trending_tags, many=True)
        return Response(serializer.data)

    @extend_schema(
        summary="Get tag statistics",
        description="Get usage statistics for event tags.",
        responses={200: {"type": "object"}},
    )
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        """Get tag statistics."""
        tag = self.get_object()

        stats = {
            "total_events": tag.events.count(),
            "active_events": tag.events.filter(
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE]
            ).count(),
            "upcoming_events": tag.events.filter(
                start_date__gt=timezone.now(),
                status__in=[Event.EventStatus.PUBLISHED, Event.EventStatus.LIVE],
            ).count(),
            "past_events": tag.events.filter(end_date__lt=timezone.now()).count(),
        }

        return Response(stats)


@extend_schema_view(
    list=extend_schema(
        summary="List sessions",
        description="Get a paginated list of sessions with filtering capabilities.",
    ),
    retrieve=extend_schema(
        summary="Get session details",
        description="Get detailed information about a specific session.",
    ),
    create=extend_schema(
        summary="Create session",
        description="Create a new session. Only event organizers can create sessions.",
    ),
    update=extend_schema(
        summary="Update session",
        description="Update an existing session. Only event organizers can update sessions.",
    ),
    destroy=extend_schema(
        summary="Delete session",
        description="Delete a session. Only event organizers can delete sessions.",
    ),
)
class SessionViewSet(viewsets.ModelViewSet):
    """ViewSet for managing event sessions."""

    serializer_class = SessionSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = [
        "title",
        "description",
        "speaker__first_name",
        "speaker__last_name",
    ]
    ordering_fields = ["start_time", "title", "created_at"]
    ordering = ["start_time"]

    def get_queryset(self):
        """Get sessions with optimized queries."""
        return (
            Session.objects.select_related("event", "speaker")
            .prefetch_related("ratings", "participants")
            .order_by("start_time")
        )

    def perform_create(self, serializer):
        """Create session with proper permissions."""
        event = serializer.validated_data["event"]
        if not self.request.user.has_perm("change_event", event):
            raise PermissionDenied(
                "You don't have permission to add sessions to this event"
            )
        serializer.save()

    @extend_schema(
        summary="Rate session",
        description="Rate a session. Only participants can rate sessions.",
        request=SessionRatingSerializer,
        responses={201: SessionRatingSerializer},
    )
    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def rate(self, request, pk=None):
        """Rate a session."""
        session = self.get_object()

        # Check if user is a participant
        participant = Participant.objects.filter(
            event=session.event, user=request.user
        ).first()

        if not participant:
            raise PermissionDenied("You must be a participant to rate sessions")

        # Create or update rating
        rating, created = SessionRating.objects.get_or_create(
            session=session,
            participant=participant,
            defaults={
                "rating": request.data.get("rating"),
                "comment": request.data.get("comment", ""),
            },
        )

        if not created:
            rating.rating = request.data.get("rating")
            rating.comment = request.data.get("comment", "")
            rating.save()

        serializer = SessionRatingSerializer(rating)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        summary="List participants",
        description="Get a paginated list of event participants.",
    ),
    retrieve=extend_schema(
        summary="Get participant details",
        description="Get detailed information about a specific participant.",
    ),
    create=extend_schema(
        summary="Register participant",
        description="Register for an event.",
    ),
    update=extend_schema(
        summary="Update participation",
        description="Update participant information.",
    ),
    destroy=extend_schema(
        summary="Unregister",
        description="Unregister from an event.",
    ),
)
class ParticipantViewSet(viewsets.ModelViewSet):
    """ViewSet for managing event participants."""

    serializer_class = ParticipantSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["user__username", "user__first_name", "user__last_name"]
    ordering_fields = ["created_at", "check_in_time"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Get participants with optimized queries."""
        return Participant.objects.select_related("user", "event").prefetch_related(
            "earned_badges__badge"
        )

    def perform_create(self, serializer):
        """Register user for event."""
        event = serializer.validated_data["event"]

        # Check if registration is open
        now = timezone.now()
        if event.registration_end_date and event.registration_end_date < now:
            raise ValidationError("Registration has closed for this event")

        # Check capacity
        if event.max_participants:
            current_count = event.participants.filter(
                registration_status=Participant.RegistrationStatus.CONFIRMED
            ).count()
            if current_count >= event.max_participants:
                raise ValidationError("Event is at full capacity")

        serializer.save(user=self.request.user)

    @extend_schema(
        summary="Check in participant",
        description="Check in a participant to the event.",
        responses={200: ParticipantSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsEventOrganizerOrCollaborator],
    )
    def check_in(self, request, pk=None):
        """Check in a participant."""
        participant = self.get_object()
        participant.check_in_time = timezone.now()
        participant.attendance_status = Participant.AttendanceStatus.CHECKED_IN
        participant.save()

        serializer = self.get_serializer(participant)
        return Response(serializer.data)

    @extend_schema(
        summary="Get participant badges",
        description="Get badges earned by the participant.",
        responses={200: ParticipantBadgeSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def badges(self, request, pk=None):
        """Get participant badges."""
        participant = self.get_object()
        badges = participant.earned_badges.select_related("badge")
        serializer = ParticipantBadgeSerializer(badges, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="List exhibitors",
        description="Get a paginated list of event exhibitors.",
    ),
    retrieve=extend_schema(
        summary="Get exhibitor details",
        description="Get detailed information about a specific exhibitor.",
    ),
    create=extend_schema(
        summary="Create exhibitor",
        description="Create a new exhibitor. Only event organizers can create exhibitors.",
    ),
    update=extend_schema(
        summary="Update exhibitor",
        description="Update an existing exhibitor.",
    ),
    destroy=extend_schema(
        summary="Delete exhibitor",
        description="Delete an exhibitor.",
    ),
)
class ExhibitorViewSet(viewsets.ModelViewSet):
    """ViewSet for managing event exhibitors."""

    serializer_class = ExhibitorSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["company_name", "description"]
    ordering_fields = ["company_name", "created_at", "sponsorship_tier"]
    ordering = ["company_name"]

    def get_queryset(self):
        """Get exhibitors with optimized queries."""
        return Exhibitor.objects.select_related(
            "event", "contact_person"
        ).prefetch_related("products")

    def perform_create(self, serializer):
        """Create exhibitor with proper permissions."""
        event = serializer.validated_data["event"]
        if not self.request.user.has_perm("change_event", event):
            raise PermissionDenied(
                "You don't have permission to add exhibitors to this event"
            )
        serializer.save()

    @extend_schema(
        summary="Get exhibitor products",
        description="Get products showcased by the exhibitor.",
        responses={200: ProductSerializer(many=True)},
    )
    @action(detail=True, methods=["get"])
    def products(self, request, pk=None):
        """Get exhibitor products."""
        exhibitor = self.get_object()
        products = exhibitor.products.all()
        serializer = ProductSerializer(products, many=True)
        return Response(serializer.data)


@extend_schema_view(
    list=extend_schema(
        summary="List products",
        description="Get a paginated list of products from exhibitors.",
    ),
    retrieve=extend_schema(
        summary="Get product details",
        description="Get detailed information about a specific product.",
    ),
    create=extend_schema(
        summary="Create product",
        description="Create a new product. Only exhibitors can create products.",
    ),
    update=extend_schema(
        summary="Update product",
        description="Update an existing product.",
    ),
    destroy=extend_schema(
        summary="Delete product",
        description="Delete a product.",
    ),
)
class ProductViewSet(viewsets.ModelViewSet):
    """ViewSet for managing exhibitor products."""

    serializer_class = ProductSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    search_fields = ["name", "description", "exhibitor__company_name"]
    ordering_fields = ["name", "price", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        """Get products with optimized queries."""
        return Product.objects.select_related("exhibitor", "event")

    def perform_create(self, serializer):
        """Create product with proper permissions."""
        exhibitor = serializer.validated_data["exhibitor"]
        if exhibitor.contact_person != self.request.user:
            raise PermissionDenied(
                "You can only add products to your own exhibitor profile"
            )
        serializer.save()

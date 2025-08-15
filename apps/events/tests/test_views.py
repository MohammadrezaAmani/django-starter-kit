"""
Comprehensive view tests for events app.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    Event,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventTag,
    EventTagRelation,
    Participant,
    Session,
)

User = get_user_model()


class BaseViewTestCase(APITestCase):
    """Base test case with common setup for view tests."""

    def setUp(self):
        self.client = APIClient()

        # Create users
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.collaborator = User.objects.create_user(
            username="collaborator",
            email="collaborator@example.com",
            password="testpass123",
        )
        self.participant_user = User.objects.create_user(
            username="participant",
            email="participant@example.com",
            password="testpass123",
        )
        self.random_user = User.objects.create_user(
            username="random", email="random@example.com", password="testpass123"
        )
        self.staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="testpass123",
            is_staff=True,
        )

        # Create categories and tags
        self.category = EventCategory.objects.create(
            name="Technology", description="Technology events"
        )
        self.tag = EventTag.objects.create(
            name="Python", description="Python programming"
        )

        # Create events
        self.public_event = Event.objects.create(
            title="Public Event",
            description="A public event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            max_participants=100,
            registration_fee=Decimal("50.00"),
            currency="USD",
            status=Event.EventStatus.PUBLISHED,
            visibility=Event.Visibility.PUBLIC,
        )

        self.private_event = Event.objects.create(
            title="Private Event",
            description="A private event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=10),
            end_date=timezone.now() + timedelta(days=11),
            status=Event.EventStatus.PUBLISHED,
            visibility=Event.Visibility.PRIVATE,
        )

        # Add relationships
        self.public_event.collaborators.add(self.collaborator)
        EventCategoryRelation.objects.create(
            event=self.public_event, category=self.category
        )
        EventTagRelation.objects.create(event=self.public_event, tag=self.tag)

        # Create sessions
        self.session = Session.objects.create(
            event=self.public_event,
            title="Opening Session",
            description="Welcome session",
            start_time=self.public_event.start_date + timedelta(hours=9),
            end_time=self.public_event.start_date + timedelta(hours=10),
            max_participants=50,
        )

        # Create participant
        self.participant = Participant.objects.create(
            user=self.participant_user,
            event=self.public_event,
            role=Participant.Role.ATTENDEE,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

    def tearDown(self):
        cache.clear()

    def authenticate(self, user=None):
        """Helper method to authenticate requests."""
        if user is None:
            user = self.organizer
        self.client.force_authenticate(user=user)

    def get_event_url(self, event_id, action=None):
        """Helper to generate event URLs."""
        if action:
            return reverse(f"events:event-{action}", kwargs={"pk": event_id})
        return reverse("events:event-detail", kwargs={"pk": event_id})


class EventListViewTest(BaseViewTestCase):
    """Test cases for event list view."""

    def test_event_list_unauthenticated(self):
        """Test event list access without authentication."""
        url = reverse("events:event-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("results", response.data)

        # Should only see public events
        event_titles = [event["title"] for event in response.data["results"]]
        self.assertIn("Public Event", event_titles)
        self.assertNotIn("Private Event", event_titles)

    def test_event_list_authenticated(self):
        """Test event list access with authentication."""
        self.authenticate(self.organizer)

        url = reverse("events:event-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Organizer should see both public and private events
        event_titles = [event["title"] for event in response.data["results"]]
        self.assertIn("Public Event", event_titles)
        self.assertIn("Private Event", event_titles)

    def test_event_list_filtering(self):
        """Test event list filtering functionality."""
        url = reverse("events:event-list")

        # Filter by category
        response = self.client.get(url, {"categories": self.category.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Public Event")

        # Filter by tag
        response = self.client.get(url, {"tags": self.tag.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        # Filter by organizer
        response = self.client.get(url, {"organizer": self.organizer.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_event_list_search(self):
        """Test event list search functionality."""
        url = reverse("events:event-list")

        # Search by title
        response = self.client.get(url, {"search": "Public"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Public Event")

        # Search with no results
        response = self.client.get(url, {"search": "NonExistent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)

    def test_event_list_ordering(self):
        """Test event list ordering."""
        # Create another event
        Event.objects.create(
            title="Earlier Event",
            description="An earlier event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

        url = reverse("events:event-list")

        # Order by start date ascending
        response = self.client.get(url, {"ordering": "start_date"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        events = response.data["results"]
        self.assertGreaterEqual(len(events), 2)

        # Should be ordered by start_date
        dates = [event["start_date"] for event in events]
        self.assertEqual(dates, sorted(dates))

    def test_event_list_pagination(self):
        """Test event list pagination."""
        # Create multiple events
        for i in range(25):
            Event.objects.create(
                title=f"Test Event {i}",
                description=f"Description {i}",
                organizer=self.organizer,
                start_date=timezone.now() + timedelta(days=i + 20),
                end_date=timezone.now() + timedelta(days=i + 21),
                status=Event.EventStatus.PUBLISHED,
            )

        url = reverse("events:event-list")

        # First page
        response = self.client.get(url, {"page": 1, "page_size": 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

        # Second page
        response = self.client.get(url, {"page": 2, "page_size": 10})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)


class EventDetailViewTest(BaseViewTestCase):
    """Test cases for event detail view."""

    def test_event_detail_public_unauthenticated(self):
        """Test public event detail access without authentication."""
        url = self.get_event_url(self.public_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Public Event")
        self.assertIn("organizer", response.data)
        self.assertIn("sessions", response.data)

    def test_event_detail_private_unauthenticated(self):
        """Test private event detail access without authentication."""
        url = self.get_event_url(self.private_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_detail_private_organizer(self):
        """Test private event detail access by organizer."""
        self.authenticate(self.organizer)

        url = self.get_event_url(self.private_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Private Event")

    def test_event_detail_private_unauthorized(self):
        """Test private event detail access by unauthorized user."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.private_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch("backend.apps.events.views.EventViewSet._track_event_view")
    def test_event_detail_view_tracking(self, mock_track):
        """Test that event views are tracked."""
        url = self.get_event_url(self.public_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_track.assert_called_once()

    def test_event_detail_permissions(self):
        """Test event detail permission flags."""
        # Organizer should have edit permissions
        self.authenticate(self.organizer)
        url = self.get_event_url(self.public_event.id)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["can_edit"])
        self.assertTrue(response.data["can_moderate"])

        # Participant should not have edit permissions
        self.authenticate(self.participant_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["can_edit"])
        self.assertFalse(response.data["can_moderate"])


class EventCreateViewTest(BaseViewTestCase):
    """Test cases for event creation."""

    def test_event_creation_unauthenticated(self):
        """Test event creation without authentication."""
        url = reverse("events:event-list")
        data = {
            "title": "New Event",
            "description": "A new event",
            "start_date": timezone.now() + timedelta(days=1),
            "end_date": timezone.now() + timedelta(days=2),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_event_creation_authenticated(self):
        """Test event creation with authentication."""
        self.authenticate(self.organizer)

        url = reverse("events:event-list")
        data = {
            "title": "New Event",
            "description": "A new event",
            "event_type": Event.EventType.IN_PERSON,
            "start_date": (timezone.now() + timedelta(days=10)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=11)).isoformat(),
            "venue_name": "Test Venue",
            "venue_address": "123 Test St",
            "max_participants": 50,
            "registration_fee": "25.00",
            "currency": "USD",
            "category_ids": [self.category.id],
            "tag_ids": [self.tag.id],
            "collaborator_ids": [self.collaborator.id],
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify event was created
        event = Event.objects.get(id=response.data["id"])
        self.assertEqual(event.title, "New Event")
        self.assertEqual(event.organizer, self.organizer)
        self.assertEqual(event.categories.count(), 1)
        self.assertEqual(event.tags.count(), 1)
        self.assertEqual(event.collaborators.count(), 1)

    def test_event_creation_validation_errors(self):
        """Test event creation with validation errors."""
        self.authenticate(self.organizer)

        url = reverse("events:event-list")

        # Invalid dates (end before start)
        data = {
            "title": "Invalid Event",
            "description": "Invalid event",
            "start_date": (timezone.now() + timedelta(days=11)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=10)).isoformat(),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_event_creation_online_validation(self):
        """Test online event creation validation."""
        self.authenticate(self.organizer)

        url = reverse("events:event-list")
        data = {
            "title": "Online Event",
            "description": "An online event",
            "event_type": Event.EventType.ONLINE,
            "start_date": (timezone.now() + timedelta(days=10)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=11)).isoformat(),
            # Missing online_meeting_url
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("online_meeting_url", response.data)


class EventUpdateViewTest(BaseViewTestCase):
    """Test cases for event updates."""

    def test_event_update_organizer(self):
        """Test event update by organizer."""
        self.authenticate(self.organizer)

        url = self.get_event_url(self.public_event.id)
        data = {"title": "Updated Event Title"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.public_event.refresh_from_db()
        self.assertEqual(self.public_event.title, "Updated Event Title")

    def test_event_update_collaborator(self):
        """Test event update by collaborator."""
        self.authenticate(self.collaborator)

        url = self.get_event_url(self.public_event.id)
        data = {"description": "Updated description"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_event_update_unauthorized(self):
        """Test event update by unauthorized user."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id)
        data = {"title": "Hacked Title"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_update_with_relationships(self):
        """Test event update with category and tag changes."""
        new_category = EventCategory.objects.create(
            name="Business", description="Business events"
        )
        new_tag = EventTag.objects.create(name="Django", description="Django framework")

        self.authenticate(self.organizer)

        url = self.get_event_url(self.public_event.id)
        data = {"category_ids": [new_category.id], "tag_ids": [new_tag.id]}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify relationships updated
        self.assertEqual(self.public_event.categories.count(), 1)
        self.assertEqual(self.public_event.categories.first(), new_category)


class EventDeleteViewTest(BaseViewTestCase):
    """Test cases for event deletion."""

    def test_event_deletion_organizer(self):
        """Test event deletion by organizer."""
        self.authenticate(self.organizer)

        url = self.get_event_url(self.public_event.id)
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify event is soft deleted
        self.public_event.refresh_from_db()
        self.assertFalse(self.public_event.is_active)
        self.assertEqual(self.public_event.status, Event.EventStatus.CANCELLED)

    def test_event_deletion_unauthorized(self):
        """Test event deletion by unauthorized user."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id)
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_deletion_collaborator_denied(self):
        """Test event deletion denied for collaborator."""
        self.authenticate(self.collaborator)

        url = self.get_event_url(self.public_event.id)
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class EventRegistrationViewTest(BaseViewTestCase):
    """Test cases for event registration."""

    def test_event_registration_success(self):
        """Test successful event registration."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "register")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify participant was created
        participant = Participant.objects.get(
            user=self.random_user, event=self.public_event
        )
        self.assertEqual(
            participant.registration_status, Participant.RegistrationStatus.CONFIRMED
        )

    def test_event_registration_unauthenticated(self):
        """Test event registration without authentication."""
        url = self.get_event_url(self.public_event.id, "register")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_event_registration_already_registered(self):
        """Test registration when already registered."""
        self.authenticate(self.participant_user)

        url = self.get_event_url(self.public_event.id, "register")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("already registered", response.data["error"].lower())

    def test_event_registration_capacity_full(self):
        """Test registration when event is at capacity."""
        # Set capacity to current participant count
        self.public_event.max_participants = 1
        self.public_event.save()

        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "register")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("capacity", response.data["error"].lower())

    def test_event_registration_closed(self):
        """Test registration when registration is closed."""
        # Set registration end date in the past
        self.public_event.registration_end_date = timezone.now() - timedelta(days=1)
        self.public_event.save()

        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "register")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not open", response.data["error"].lower())

    def test_event_registration_with_data(self):
        """Test event registration with additional data."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "register")
        data = {
            "registration_data": {
                "dietary_requirements": "Vegetarian",
                "t_shirt_size": "L",
            }
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        participant = Participant.objects.get(
            user=self.random_user, event=self.public_event
        )
        self.assertEqual(
            participant.registration_data["dietary_requirements"], "Vegetarian"
        )


class EventUnregistrationViewTest(BaseViewTestCase):
    """Test cases for event unregistration."""

    def test_event_unregistration_success(self):
        """Test successful event unregistration."""
        self.authenticate(self.participant_user)

        url = self.get_event_url(self.public_event.id, "unregister")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify participant status updated
        self.participant.refresh_from_db()
        self.assertEqual(
            self.participant.registration_status,
            Participant.RegistrationStatus.CANCELLED,
        )

    def test_event_unregistration_not_registered(self):
        """Test unregistration when not registered."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "unregister")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("not registered", response.data["error"].lower())

    def test_event_unregistration_too_late(self):
        """Test unregistration too close to event date."""
        # Set event to start in 12 hours (less than 24 hour policy)
        self.public_event.start_date = timezone.now() + timedelta(hours=12)
        self.public_event.save()

        self.authenticate(self.participant_user)

        url = self.get_event_url(self.public_event.id, "unregister")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("24 hours", response.data["error"].lower())


class EventFavoriteViewTest(BaseViewTestCase):
    """Test cases for event favorites."""

    def test_event_favorite_add(self):
        """Test adding event to favorites."""
        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "favorite")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify favorite was created
        self.assertTrue(
            EventFavorite.objects.filter(
                user=self.random_user, event=self.public_event
            ).exists()
        )

    def test_event_favorite_remove(self):
        """Test removing event from favorites."""
        # Create existing favorite
        EventFavorite.objects.create(user=self.random_user, event=self.public_event)

        self.authenticate(self.random_user)

        url = self.get_event_url(self.public_event.id, "favorite")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify favorite was removed
        self.assertFalse(
            EventFavorite.objects.filter(
                user=self.random_user, event=self.public_event
            ).exists()
        )

    def test_event_favorite_unauthenticated(self):
        """Test favorite functionality without authentication."""
        url = self.get_event_url(self.public_event.id, "favorite")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EventSpecialActionsViewTest(BaseViewTestCase):
    """Test cases for special event actions."""

    def test_featured_events(self):
        """Test featured events endpoint."""
        # Mark event as featured
        self.public_event.is_featured = True
        self.public_event.save()

        url = reverse("events:event-featured")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["title"], "Public Event")

    def test_trending_events(self):
        """Test trending events endpoint."""
        # Create some recent activity
        for i in range(5):
            user = User.objects.create_user(
                username=f"trend_user_{i}",
                email=f"trend_user_{i}@example.com",
                password="testpass123",
            )
            Participant.objects.create(
                user=user,
                event=self.public_event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )

        url = reverse("events:event-trending")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should include public event due to recent activity

    def test_my_events_authenticated(self):
        """Test my events endpoint with authentication."""
        self.authenticate(self.organizer)

        url = reverse("events:event-my-events")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Should include events organized by user
        event_titles = [event["title"] for event in response.data["results"]]
        self.assertIn("Public Event", event_titles)
        self.assertIn("Private Event", event_titles)

    def test_my_events_by_type(self):
        """Test my events filtering by type."""
        self.authenticate(self.organizer)

        # Test organized events
        url = reverse("events:event-my-events")
        response = self.client.get(url, {"type": "organized"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test participating events
        self.authenticate(self.participant_user)
        response = self.client.get(url, {"type": "participating"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_my_events_unauthenticated(self):
        """Test my events endpoint without authentication."""
        url = reverse("events:event-my-events")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class EventSessionsViewTest(BaseViewTestCase):
    """Test cases for event sessions endpoint."""

    def test_event_sessions_list(self):
        """Test listing event sessions."""
        url = self.get_event_url(self.public_event.id, "sessions")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Opening Session")

    def test_event_sessions_filtering(self):
        """Test session filtering."""
        # Create additional session
        Session.objects.create(
            event=self.public_event,
            title="Workshop Session",
            description="A workshop",
            session_type=Session.SessionType.WORKSHOP,
            start_time=self.public_event.start_date + timedelta(hours=11),
            end_time=self.public_event.start_date + timedelta(hours=12),
        )

        url = self.get_event_url(self.public_event.id, "sessions")

        # Filter by type
        response = self.client.get(url, {"type": Session.SessionType.WORKSHOP})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Workshop Session")

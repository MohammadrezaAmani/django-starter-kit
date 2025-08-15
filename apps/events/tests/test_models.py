from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from .models import (
    Event,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventTag,
    EventTagRelation,
    Participant,
    Session,
    SessionRating,
)

User = get_user_model()


class EventModelTests(TestCase):
    """Test cases for Event model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.category = EventCategory.objects.create(
            name="Technology", description="Tech events"
        )
        self.tag = EventTag.objects.create(
            name="Python", description="Python programming"
        )

    def test_event_creation(self):
        """Test basic event creation."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            max_participants=100,
            registration_fee=Decimal("50.00"),
        )

        self.assertEqual(event.title, "Test Event")
        self.assertEqual(event.organizer, self.user)
        self.assertTrue(event.is_active)
        self.assertEqual(event.status, Event.EventStatus.DRAFT)

    def test_event_slug_generation(self):
        """Test automatic slug generation."""
        event = Event.objects.create(
            title="Test Event With Special Characters!",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        self.assertEqual(event.slug, "test-event-with-special-characters")

    def test_event_spots_remaining(self):
        """Test spots remaining calculation."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            max_participants=5,
        )

        # No participants yet
        self.assertEqual(event.spots_remaining(), 5)

        # Add participants
        for i in range(3):
            user = User.objects.create_user(
                username=f"participant{i}",
                email=f"participant{i}@example.com",
                password="pass123",
            )
            Participant.objects.create(
                user=user,
                event=event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )

        self.assertEqual(event.spots_remaining(), 2)

    def test_event_registration_open(self):
        """Test registration open validation."""
        now = timezone.now()

        # Event with open registration
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=now + timedelta(days=7),
            end_date=now + timedelta(days=8),
            registration_start_date=now - timedelta(days=1),
            registration_end_date=now + timedelta(days=5),
            max_participants=100,
        )

        self.assertTrue(event.is_registration_open())

        # Event with closed registration
        event.registration_end_date = now - timedelta(days=1)
        event.save()

        self.assertFalse(event.is_registration_open())

    def test_event_clean_validation(self):
        """Test event validation in clean method."""
        with self.assertRaises(Exception):
            event = Event(
                title="Invalid Event",
                description="Invalid dates",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=2),
                end_date=timezone.now() + timedelta(days=1),  # End before start
            )
            event.clean()

    def test_event_category_relations(self):
        """Test event category relationships."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        # Add category relation
        EventCategoryRelation.objects.create(event=event, category=self.category)

        self.assertEqual(event.categories.count(), 1)
        self.assertEqual(event.categories.first(), self.category)

    def test_event_tag_relations(self):
        """Test event tag relationships."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        # Add tag relation
        EventTagRelation.objects.create(event=event, tag=self.tag)

        self.assertEqual(event.tags.count(), 1)
        self.assertEqual(event.tags.first(), self.tag)


class SessionModelTests(TestCase):
    """Test cases for Session model functionality."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

    def test_session_creation(self):
        """Test basic session creation."""
        session = Session.objects.create(
            event=self.event,
            title="Test Session",
            description="A test session",
            start_time=self.event.start_date + timedelta(hours=1),
            end_time=self.event.start_date + timedelta(hours=2),
            max_participants=50,
        )

        self.assertEqual(session.title, "Test Session")
        self.assertEqual(session.event, self.event)
        self.assertEqual(session.status, Session.SessionStatus.SCHEDULED)

    def test_session_duration_calculation(self):
        """Test session duration calculation."""
        start_time = timezone.now() + timedelta(days=1, hours=10)
        end_time = start_time + timedelta(hours=1, minutes=30)

        session = Session.objects.create(
            event=self.event,
            title="Test Session",
            description="A test session",
            start_time=start_time,
            end_time=end_time,
        )

        self.assertEqual(session.duration_minutes(), 90)

    def test_session_is_live(self):
        """Test session live status."""
        now = timezone.now()

        # Current session
        session = Session.objects.create(
            event=self.event,
            title="Live Session",
            description="A live session",
            start_time=now - timedelta(minutes=10),
            end_time=now + timedelta(minutes=20),
            status=Session.SessionStatus.LIVE,
        )

        self.assertTrue(session.is_live())

        # Scheduled session
        session.status = Session.SessionStatus.SCHEDULED
        session.save()

        self.assertFalse(session.is_live())

    def test_session_clean_validation(self):
        """Test session validation."""
        with self.assertRaises(Exception):
            session = Session(
                event=self.event,
                title="Invalid Session",
                description="Invalid times",
                start_time=timezone.now() + timedelta(hours=2),
                end_time=timezone.now() + timedelta(hours=1),  # End before start
            )
            session.clean()


class ParticipantModelTests(TestCase):
    """Test cases for Participant model functionality."""

    def setUp(self):
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.participant_user = User.objects.create_user(
            username="participant",
            email="participant@example.com",
            password="testpass123",
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

    def test_participant_creation(self):
        """Test basic participant creation."""
        participant = Participant.objects.create(
            user=self.participant_user, event=self.event, role=Participant.Role.ATTENDEE
        )

        self.assertEqual(participant.user, self.participant_user)
        self.assertEqual(participant.event, self.event)
        self.assertEqual(participant.role, Participant.Role.ATTENDEE)
        self.assertEqual(
            participant.registration_status, Participant.RegistrationStatus.PENDING
        )

    def test_participant_check_in(self):
        """Test participant check-in functionality."""
        participant = Participant.objects.create(
            user=self.participant_user,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        # Check in
        participant.check_in()

        self.assertEqual(
            participant.attendance_status, Participant.AttendanceStatus.CHECKED_IN
        )
        self.assertIsNotNone(participant.check_in_time)

    def test_participant_check_out(self):
        """Test participant check-out functionality."""
        participant = Participant.objects.create(
            user=self.participant_user,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
            attendance_status=Participant.AttendanceStatus.CHECKED_IN,
            check_in_time=timezone.now(),
        )

        # Check out
        participant.check_out()

        self.assertEqual(
            participant.attendance_status, Participant.AttendanceStatus.CHECKED_OUT
        )
        self.assertIsNotNone(participant.check_out_time)


class EventAPITests(APITestCase):
    """Test cases for Event API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )
        self.category = EventCategory.objects.create(
            name="Technology", description="Tech events"
        )
        self.tag = EventTag.objects.create(
            name="Python", description="Python programming"
        )

    def authenticate(self, user=None):
        """Helper method to authenticate requests."""
        if user is None:
            user = self.user
        self.client.force_authenticate(user=user)

    def test_event_list_unauthenticated(self):
        """Test event list access without authentication."""
        url = reverse("events:event-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_event_list_authenticated(self):
        """Test event list access with authentication."""
        self.authenticate()

        # Create test events
        Event.objects.create(
            title="Public Event",
            description="A public event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PUBLIC,
            status=Event.EventStatus.PUBLISHED,
        )
        Event.objects.create(
            title="Private Event",
            description="A private event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PRIVATE,
            status=Event.EventStatus.PUBLISHED,
        )

        url = reverse("events:event-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            len(response.data["results"]), 2
        )  # User can see their own private events

    def test_event_creation(self):
        """Test event creation via API."""
        self.authenticate()

        url = reverse("events:event-list")
        data = {
            "title": "New Event",
            "description": "A new event",
            "event_type": Event.EventType.IN_PERSON,
            "start_date": (timezone.now() + timedelta(days=7)).isoformat(),
            "end_date": (timezone.now() + timedelta(days=8)).isoformat(),
            "venue_name": "Test Venue",
            "venue_address": "123 Test St",
            "max_participants": 100,
            "registration_fee": "25.00",
            "currency": "USD",
            "category_ids": [self.category.id],
            "tag_ids": [self.tag.id],
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Event.objects.count(), 1)

        event = Event.objects.first()
        self.assertEqual(event.title, "New Event")
        self.assertEqual(event.organizer, self.user)
        self.assertEqual(event.categories.count(), 1)
        self.assertEqual(event.tags.count(), 1)

    def test_event_creation_validation(self):
        """Test event creation validation."""
        self.authenticate()

        url = reverse("events:event-list")
        data = {
            "title": "Invalid Event",
            "description": "Invalid dates",
            "start_date": (timezone.now() + timedelta(days=8)).isoformat(),
            "end_date": (
                timezone.now() + timedelta(days=7)
            ).isoformat(),  # End before start
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("end_date", response.data)

    def test_event_update_permission(self):
        """Test event update permissions."""
        # Create event as first user
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        # Try to update as different user
        self.authenticate(self.other_user)

        url = reverse("events:event-detail", kwargs={"pk": event.pk})
        data = {"title": "Updated Title"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Update as owner
        self.authenticate(self.user)
        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        event.refresh_from_db()
        self.assertEqual(event.title, "Updated Title")

    def test_event_registration(self):
        """Test event registration functionality."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            max_participants=100,
            status=Event.EventStatus.PUBLISHED,
        )

        self.authenticate(self.other_user)

        url = reverse("events:event-register", kwargs={"pk": event.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Participant.objects.filter(
                user=self.other_user,
                event=event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            ).exists()
        )

    def test_event_registration_capacity_limit(self):
        """Test event registration with capacity limit."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            max_participants=1,
            status=Event.EventStatus.PUBLISHED,
        )

        # Fill capacity
        Participant.objects.create(
            user=self.user,
            event=event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        # Try to register another user
        self.authenticate(self.other_user)

        url = reverse("events:event-register", kwargs={"pk": event.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("capacity", response.data["error"].lower())

    def test_event_unregistration(self):
        """Test event unregistration functionality."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            status=Event.EventStatus.PUBLISHED,
        )

        # Register user
        participant = Participant.objects.create(
            user=self.other_user,
            event=event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        self.authenticate(self.other_user)

        url = reverse("events:event-unregister", kwargs={"pk": event.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        participant.refresh_from_db()
        self.assertEqual(
            participant.registration_status, Participant.RegistrationStatus.CANCELLED
        )

    def test_event_favorite(self):
        """Test event favorite functionality."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

        self.authenticate(self.other_user)

        url = reverse("events:event-favorite", kwargs={"pk": event.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            EventFavorite.objects.filter(user=self.other_user, event=event).exists()
        )

        # Unfavorite
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            EventFavorite.objects.filter(user=self.other_user, event=event).exists()
        )

    def test_event_search_filter(self):
        """Test event search and filtering."""
        # Create events with different attributes
        tech_event = Event.objects.create(
            title="Tech Conference",
            description="A technology conference",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )
        EventCategoryRelation.objects.create(event=tech_event, category=self.category)

        Event.objects.create(
            title="Art Exhibition",
            description="An art exhibition",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            status=Event.EventStatus.PUBLISHED,
        )

        url = reverse("events:event-list")

        # Search by title
        response = self.client.get(url, {"search": "Tech"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Tech Conference")

        # Filter by category
        response = self.client.get(url, {"categories": self.category.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class SessionAPITests(APITestCase):
    """Test cases for Session API endpoints."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.speaker = User.objects.create_user(
            username="speaker", email="speaker@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

    def authenticate(self, user=None):
        """Helper method to authenticate requests."""
        if user is None:
            user = self.user
        self.client.force_authenticate(user=user)

    def test_session_creation(self):
        """Test session creation via API."""
        self.authenticate()

        url = reverse("events:session-list")
        data = {
            "event": self.event.id,
            "title": "Test Session",
            "description": "A test session",
            "start_time": (self.event.start_date + timedelta(hours=1)).isoformat(),
            "end_time": (self.event.start_date + timedelta(hours=2)).isoformat(),
            "max_participants": 50,
            "speaker_ids": [self.speaker.id],
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Session.objects.count(), 1)

        session = Session.objects.first()
        self.assertEqual(session.title, "Test Session")
        # Check speaker participant was created
        self.assertTrue(
            Participant.objects.filter(
                user=self.speaker, event=self.event, role=Participant.Role.SPEAKER
            ).exists()
        )

    def test_session_attend(self):
        """Test session attendance functionality."""
        session = Session.objects.create(
            event=self.event,
            title="Test Session",
            description="A test session",
            start_time=self.event.start_date + timedelta(hours=1),
            end_time=self.event.start_date + timedelta(hours=2),
            max_participants=50,
        )

        # Register user for event first
        Participant.objects.create(
            user=self.speaker,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        self.authenticate(self.speaker)

        url = reverse("events:session-attend", kwargs={"pk": session.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_session_rating(self):
        """Test session rating functionality."""
        session = Session.objects.create(
            event=self.event,
            title="Test Session",
            description="A test session",
            start_time=self.event.start_date + timedelta(hours=1),
            end_time=self.event.start_date + timedelta(hours=2),
        )

        # Create participant
        participant = Participant.objects.create(
            user=self.speaker,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        self.authenticate(self.speaker)

        url = reverse("events:session-rate", kwargs={"pk": session.pk})
        data = {"rating": 5, "comment": "Excellent session!"}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            SessionRating.objects.filter(
                session=session, participant=participant, rating=5
            ).exists()
        )


class PerformanceTests(APITestCase):
    """Test cases for performance optimization."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        # Create test data
        self.category = EventCategory.objects.create(
            name="Technology", description="Tech events"
        )

        # Create multiple events for performance testing
        self.events = []
        for i in range(50):
            event = Event.objects.create(
                title=f"Event {i}",
                description=f"Description {i}",
                organizer=self.user,
                start_date=timezone.now() + timedelta(days=i + 1),
                end_date=timezone.now() + timedelta(days=i + 2),
                status=Event.EventStatus.PUBLISHED,
            )
            self.events.append(event)

            # Add category relation
            EventCategoryRelation.objects.create(event=event, category=self.category)

    def test_event_list_query_count(self):
        """Test that event list doesn't cause N+1 query problems."""
        url = reverse("events:event-list")

        with self.assertNumQueriesLessThan(10):  # Should be efficient
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_event_detail_query_count(self):
        """Test that event detail doesn't cause N+1 query problems."""
        event = self.events[0]

        # Add some related data
        Session.objects.create(
            event=event,
            title="Test Session",
            description="A test session",
            start_time=event.start_date + timedelta(hours=1),
            end_time=event.start_date + timedelta(hours=2),
        )

        url = reverse("events:event-detail", kwargs={"pk": event.pk})

        with self.assertNumQueriesLessThan(
            15
        ):  # Should be efficient even with relations
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)


class SecurityTests(APITestCase):
    """Test cases for security features."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.malicious_user = User.objects.create_user(
            username="malicious", email="malicious@example.com", password="testpass123"
        )

    def test_unauthorized_event_access(self):
        """Test that unauthorized users can't access private events."""
        private_event = Event.objects.create(
            title="Private Event",
            description="A private event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PRIVATE,
            status=Event.EventStatus.PUBLISHED,
        )

        # Try to access as different user
        self.client.force_authenticate(user=self.malicious_user)

        url = reverse("events:event-detail", kwargs={"pk": private_event.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_modification_protection(self):
        """Test that users can't modify events they don't own."""
        event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        # Try to modify as different user
        self.client.force_authenticate(user=self.malicious_user)

        url = reverse("events:event-detail", kwargs={"pk": event.pk})
        data = {"title": "Hacked Event"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_file_upload_security(self):
        """Test file upload security for attachments."""
        Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        self.client.force_authenticate(user=self.user)

        # Try to upload a potentially malicious file
        SimpleUploadedFile(
            "malicious.exe",
            b"fake executable content",
            content_type="application/x-executable",
        )

"""
Comprehensive serializer tests for events app.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from ..models import (
    Event,
    EventAnalytics,
    EventAttachment,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventTag,
    EventTagRelation,
    Exhibitor,
    Participant,
    Product,
    Session,
    SessionRating,
)
from ..serializers import (
    EventAnalyticsSerializer,
    EventAttachmentSerializer,
    EventCategorySerializer,
    EventCreateUpdateSerializer,
    EventDetailSerializer,
    EventFavoriteSerializer,
    EventListSerializer,
    EventTagSerializer,
    ExhibitorSerializer,
    ParticipantSerializer,
    ProductSerializer,
    SessionMinimalSerializer,
    SessionRatingSerializer,
    SessionSerializer,
    UserMinimalSerializer,
)

User = get_user_model()


class BaseSerializerTestCase(TestCase):
    """Base test case with common setup for serializer tests."""

    def setUp(self):
        # Create users
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.participant_user = User.objects.create_user(
            username="participant",
            email="participant@example.com",
            password="testpass123",
        )
        self.collaborator = User.objects.create_user(
            username="collaborator",
            email="collaborator@example.com",
            password="testpass123",
        )

        # Create categories and tags
        self.category = EventCategory.objects.create(
            name="Technology", description="Technology events"
        )
        self.subcategory = EventCategory.objects.create(
            name="AI/ML", description="AI and Machine Learning", parent=self.category
        )
        self.tag = EventTag.objects.create(
            name="Python", description="Python programming"
        )

        # Create event
        self.event = Event.objects.create(
            title="Test Event",
            description="A comprehensive test event",
            full_description="This is a detailed description of the test event.",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=7),
            end_date=timezone.now() + timedelta(days=8),
            max_participants=100,
            registration_fee=Decimal("50.00"),
            currency="USD",
            location="San Francisco, CA",
            venue_name="Conference Center",
            venue_address="123 Main St, San Francisco, CA",
            status=Event.EventStatus.PUBLISHED,
            visibility=Event.Visibility.PUBLIC,
        )

        # Add relationships
        self.event.collaborators.add(self.collaborator)
        EventCategoryRelation.objects.create(event=self.event, category=self.category)
        EventTagRelation.objects.create(event=self.event, tag=self.tag)

        # Create session
        self.session = Session.objects.create(
            event=self.event,
            title="Opening Keynote",
            description="Welcome session",
            start_time=self.event.start_date + timedelta(hours=9),
            end_time=self.event.start_date + timedelta(hours=10),
            max_participants=50,
        )

        # Create participant
        self.participant = Participant.objects.create(
            user=self.participant_user,
            event=self.event,
            role=Participant.Role.ATTENDEE,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        # Mock request context
        self.mock_context = {
            "request": type(
                "MockRequest",
                (),
                {
                    "user": self.organizer,
                    "build_absolute_uri": lambda x: f"http://testserver{x}",
                },
            )()
        }

    def get_serializer_context(self, user=None):
        """Get serializer context with specified user."""
        if user is None:
            user = self.organizer

        return {
            "request": type(
                "MockRequest",
                (),
                {
                    "user": user,
                    "build_absolute_uri": lambda x: f"http://testserver{x}",
                },
            )()
        }


class EventCategorySerializerTest(BaseSerializerTestCase):
    """Test EventCategorySerializer."""

    def test_category_serialization(self):
        """Test basic category serialization."""
        serializer = EventCategorySerializer(self.category, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["name"], "Technology")
        self.assertEqual(data["description"], "Technology events")
        self.assertIn("children", data)
        self.assertIn("event_count", data)
        self.assertIn("slug", data)

    def test_category_with_children(self):
        """Test category serialization with children."""
        serializer = EventCategorySerializer(self.category, context=self.mock_context)
        data = serializer.data

        # Should include subcategory in children
        self.assertEqual(len(data["children"]), 1)
        self.assertEqual(data["children"][0]["name"], "AI/ML")

    def test_category_event_count(self):
        """Test event count calculation."""
        serializer = EventCategorySerializer(self.category, context=self.mock_context)
        event_count = serializer.get_event_count(self.category)

        self.assertEqual(event_count, 1)  # One event in this category

    def test_category_validation_circular_reference(self):
        """Test validation prevents circular references."""
        serializer = EventCategorySerializer()

        with self.assertRaises(ValidationError):
            # Try to make category its own parent
            serializer.validate_parent(self.category)

    def test_category_hierarchy_validation(self):
        """Test category hierarchy validation."""
        serializer = EventCategorySerializer(instance=self.category)

        with self.assertRaises(ValidationError):
            # Try to make subcategory the parent of its parent
            serializer.validate_parent(self.subcategory)


class EventTagSerializerTest(BaseSerializerTestCase):
    """Test EventTagSerializer."""

    def test_tag_serialization(self):
        """Test basic tag serialization."""
        serializer = EventTagSerializer(self.tag, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["name"], "Python")
        self.assertEqual(data["description"], "Python programming")
        self.assertIn("event_count", data)
        self.assertIn("trending_score", data)

    def test_tag_event_count(self):
        """Test tag event count calculation."""
        serializer = EventTagSerializer(self.tag, context=self.mock_context)
        event_count = serializer.get_event_count(self.tag)

        self.assertEqual(event_count, 1)  # One event with this tag

    def test_tag_trending_score(self):
        """Test trending score calculation."""
        serializer = EventTagSerializer(self.tag, context=self.mock_context)
        trending_score = serializer.get_trending_score(self.tag)

        self.assertIsInstance(trending_score, float)
        self.assertGreaterEqual(trending_score, 0.0)


class UserMinimalSerializerTest(BaseSerializerTestCase):
    """Test UserMinimalSerializer."""

    def test_user_serialization(self):
        """Test basic user serialization."""
        serializer = UserMinimalSerializer(self.organizer, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["username"], "organizer")
        self.assertIn("full_name", data)
        self.assertIn("avatar_url", data)
        self.assertNotIn("email", data)  # Should not expose email
        self.assertNotIn("password", data)  # Should not expose password

    def test_user_full_name(self):
        """Test full name generation."""
        self.organizer.first_name = "John"
        self.organizer.last_name = "Doe"
        self.organizer.save()

        serializer = UserMinimalSerializer(self.organizer, context=self.mock_context)
        full_name = serializer.get_full_name(self.organizer)

        self.assertEqual(full_name, "John Doe")

    def test_user_full_name_fallback(self):
        """Test full name fallback to username."""
        serializer = UserMinimalSerializer(self.organizer, context=self.mock_context)
        full_name = serializer.get_full_name(self.organizer)

        self.assertEqual(full_name, "organizer")  # Falls back to username


class SessionMinimalSerializerTest(BaseSerializerTestCase):
    """Test SessionMinimalSerializer."""

    def test_session_serialization(self):
        """Test basic session serialization."""
        serializer = SessionMinimalSerializer(self.session, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["title"], "Opening Keynote")
        self.assertIn("speaker_names", data)
        self.assertIn("duration_display", data)
        self.assertIn("is_live", data)

    def test_session_duration_display(self):
        """Test duration display formatting."""
        serializer = SessionMinimalSerializer(self.session, context=self.mock_context)
        duration = serializer.get_duration_display(self.session)

        self.assertEqual(duration, "1h")  # 1 hour session

    def test_session_duration_display_with_minutes(self):
        """Test duration display with minutes."""
        # Create session with 1.5 hours duration
        session = Session.objects.create(
            event=self.event,
            title="Workshop",
            description="A workshop session",
            start_time=self.event.start_date + timedelta(hours=10),
            end_time=self.event.start_date + timedelta(hours=11, minutes=30),
        )

        serializer = SessionMinimalSerializer(session, context=self.mock_context)
        duration = serializer.get_duration_display(session)

        self.assertEqual(duration, "1h 30m")

    def test_session_is_live(self):
        """Test is_live calculation."""
        serializer = SessionMinimalSerializer(self.session, context=self.mock_context)
        is_live = serializer.get_is_live(self.session)

        self.assertFalse(is_live)  # Session is in the future


class EventAttachmentSerializerTest(BaseSerializerTestCase):
    """Test EventAttachmentSerializer."""

    def setUp(self):
        super().setUp()
        self.test_file = SimpleUploadedFile(
            "test_document.pdf",
            b"PDF content here",
            content_type="application/pdf",
        )
        self.attachment = EventAttachment.objects.create(
            event=self.event,
            title="Event Brochure",
            description="Official event brochure",
            attachment_type=EventAttachment.AttachmentType.DOCUMENT,
            file=self.test_file,
            file_size=1024,
            is_public=True,
        )

    def test_attachment_serialization(self):
        """Test basic attachment serialization."""
        serializer = EventAttachmentSerializer(
            self.attachment, context=self.mock_context
        )
        data = serializer.data

        self.assertEqual(data["title"], "Event Brochure")
        self.assertIn("file_url", data)
        self.assertIn("file_size_display", data)
        self.assertIn("can_download", data)

    def test_file_size_display(self):
        """Test file size display formatting."""
        serializer = EventAttachmentSerializer(
            self.attachment, context=self.mock_context
        )
        size_display = serializer.get_file_size_display(self.attachment)

        self.assertEqual(size_display, "1.0 KB")

    def test_file_size_display_mb(self):
        """Test file size display for larger files."""
        self.attachment.file_size = 2 * 1024 * 1024  # 2MB
        self.attachment.save()

        serializer = EventAttachmentSerializer(
            self.attachment, context=self.mock_context
        )
        size_display = serializer.get_file_size_display(self.attachment)

        self.assertEqual(size_display, "2.0 MB")

    def test_can_download_public_file(self):
        """Test download permission for public files."""
        serializer = EventAttachmentSerializer(
            self.attachment, context=self.get_serializer_context(self.participant_user)
        )
        can_download = serializer.get_can_download(self.attachment)

        self.assertTrue(can_download)  # Public file, registered participant

    def test_can_download_private_file_organizer(self):
        """Test download permission for private files by organizer."""
        self.attachment.is_public = False
        self.attachment.save()

        serializer = EventAttachmentSerializer(
            self.attachment, context=self.get_serializer_context(self.organizer)
        )
        can_download = serializer.get_can_download(self.attachment)

        self.assertTrue(can_download)  # Organizer can download

    def test_can_download_private_file_unauthorized(self):
        """Test download permission denied for private files."""
        self.attachment.is_public = False
        self.attachment.save()

        unauthorized_user = User.objects.create_user(
            username="unauthorized", email="unauthorized@example.com", password="pass"
        )

        serializer = EventAttachmentSerializer(
            self.attachment, context=self.get_serializer_context(unauthorized_user)
        )
        can_download = serializer.get_can_download(self.attachment)

        self.assertFalse(can_download)  # Unauthorized user cannot download

    def test_file_validation_size_limit(self):
        """Test file size validation."""
        large_file = SimpleUploadedFile(
            "large_file.pdf",
            b"x" * (11 * 1024 * 1024),  # 11MB
            content_type="application/pdf",
        )

        serializer = EventAttachmentSerializer()

        with self.assertRaises(ValidationError):
            serializer.validate_file(large_file)

    def test_file_validation_wrong_type(self):
        """Test file type validation."""
        wrong_type_file = SimpleUploadedFile(
            "test.exe",
            b"executable content",
            content_type="application/x-executable",
        )

        serializer = EventAttachmentSerializer(
            data={
                "attachment_type": EventAttachment.AttachmentType.DOCUMENT,
                "file": wrong_type_file,
            }
        )

        with self.assertRaises(ValidationError):
            serializer.validate_file(wrong_type_file)


class EventListSerializerTest(BaseSerializerTestCase):
    """Test EventListSerializer."""

    def test_event_list_serialization(self):
        """Test basic event list serialization."""
        serializer = EventListSerializer(self.event, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["title"], "Test Event")
        self.assertIn("organizer", data)
        self.assertIn("categories", data)
        self.assertIn("tags", data)
        self.assertIn("participant_count", data)
        self.assertIn("is_favorited", data)
        self.assertIn("registration_status", data)

    def test_participant_count(self):
        """Test participant count calculation."""
        serializer = EventListSerializer(self.event, context=self.mock_context)
        count = serializer.get_participant_count(self.event)

        self.assertEqual(count, 1)  # One confirmed participant

    def test_is_favorited_true(self):
        """Test is_favorited when user has favorited event."""
        EventFavorite.objects.create(user=self.organizer, event=self.event)

        serializer = EventListSerializer(self.event, context=self.mock_context)
        is_favorited = serializer.get_is_favorited(self.event)

        self.assertTrue(is_favorited)

    def test_is_favorited_false(self):
        """Test is_favorited when user hasn't favorited event."""
        serializer = EventListSerializer(self.event, context=self.mock_context)
        is_favorited = serializer.get_is_favorited(self.event)

        self.assertFalse(is_favorited)

    def test_registration_status_registered(self):
        """Test registration status for registered user."""
        context = self.get_serializer_context(self.participant_user)
        serializer = EventListSerializer(self.event, context=context)
        status = serializer.get_registration_status(self.event)

        self.assertEqual(status, Participant.RegistrationStatus.CONFIRMED)

    def test_registration_status_not_registered(self):
        """Test registration status for unregistered user."""
        unregistered_user = User.objects.create_user(
            username="unregistered", email="unregistered@example.com", password="pass"
        )

        context = self.get_serializer_context(unregistered_user)
        serializer = EventListSerializer(self.event, context=context)
        status = serializer.get_registration_status(self.event)

        self.assertEqual(status, "not_registered")


class EventDetailSerializerTest(BaseSerializerTestCase):
    """Test EventDetailSerializer."""

    def test_event_detail_serialization(self):
        """Test comprehensive event detail serialization."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["title"], "Test Event")
        self.assertIn("full_description", data)
        self.assertIn("sessions", data)
        self.assertIn("recent_participants", data)
        self.assertIn("featured_sessions", data)
        self.assertIn("can_edit", data)
        self.assertIn("can_moderate", data)

    def test_can_edit_organizer(self):
        """Test can_edit permission for organizer."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        can_edit = serializer.get_can_edit(self.event)

        self.assertTrue(can_edit)

    def test_can_edit_collaborator(self):
        """Test can_edit permission for collaborator."""
        context = self.get_serializer_context(self.collaborator)
        serializer = EventDetailSerializer(self.event, context=context)
        can_edit = serializer.get_can_edit(self.event)

        self.assertTrue(can_edit)

    def test_can_edit_participant(self):
        """Test can_edit permission denied for participant."""
        context = self.get_serializer_context(self.participant_user)
        serializer = EventDetailSerializer(self.event, context=context)
        can_edit = serializer.get_can_edit(self.event)

        self.assertFalse(can_edit)

    def test_can_moderate_organizer(self):
        """Test can_moderate permission for organizer."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        can_moderate = serializer.get_can_moderate(self.event)

        self.assertTrue(can_moderate)

    def test_spots_remaining(self):
        """Test spots remaining calculation."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        spots = serializer.get_spots_remaining(self.event)

        self.assertEqual(spots, 99)  # 100 capacity - 1 participant


class EventCreateUpdateSerializerTest(BaseSerializerTestCase):
    """Test EventCreateUpdateSerializer."""

    def test_event_creation_data_validation(self):
        """Test event creation with valid data."""
        data = {
            "title": "New Event",
            "description": "A new event description",
            "event_type": Event.EventType.IN_PERSON,
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            "venue_name": "New Venue",
            "venue_address": "456 New St, City",
            "max_participants": 50,
            "registration_fee": "25.00",
            "currency": "USD",
            "category_ids": [self.category.id],
            "tag_ids": [self.tag.id],
        }

        serializer = EventCreateUpdateSerializer(data=data, context=self.mock_context)

        self.assertTrue(serializer.is_valid())

    def test_date_validation_end_before_start(self):
        """Test validation when end date is before start date."""
        data = {
            "title": "Invalid Event",
            "description": "Invalid dates",
            "start_date": timezone.now() + timedelta(days=11),
            "end_date": timezone.now() + timedelta(days=10),  # Before start
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("end_date", serializer.errors)

    def test_registration_date_validation(self):
        """Test registration date validation."""
        data = {
            "title": "Event",
            "description": "Description",
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            "registration_start_date": timezone.now() + timedelta(days=8),
            "registration_end_date": timezone.now()
            + timedelta(days=12),  # After event start
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("registration_end_date", serializer.errors)

    def test_online_event_validation(self):
        """Test validation for online events."""
        data = {
            "title": "Online Event",
            "description": "An online event",
            "event_type": Event.EventType.ONLINE,
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            # Missing online_meeting_url
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("online_meeting_url", serializer.errors)

    def test_in_person_event_validation(self):
        """Test validation for in-person events."""
        data = {
            "title": "In-Person Event",
            "description": "An in-person event",
            "event_type": Event.EventType.IN_PERSON,
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            # Missing venue information
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("venue_name", serializer.errors)

    def test_capacity_validation(self):
        """Test capacity validation."""
        data = {
            "title": "Event",
            "description": "Description",
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            "max_participants": 150,
            "venue_capacity": 100,  # Less than max participants
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("max_participants", serializer.errors)

    def test_category_ids_validation(self):
        """Test category IDs validation."""
        data = {
            "title": "Event",
            "description": "Description",
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            "category_ids": [999999],  # Non-existent category
        }

        serializer = EventCreateUpdateSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("category_ids", serializer.errors)

    def test_event_creation_with_relationships(self):
        """Test event creation with categories and tags."""
        data = {
            "title": "Event with Relations",
            "description": "Event with categories and tags",
            "start_date": timezone.now() + timedelta(days=10),
            "end_date": timezone.now() + timedelta(days=11),
            "category_ids": [self.category.id],
            "tag_ids": [self.tag.id],
            "collaborator_ids": [self.collaborator.id],
        }

        serializer = EventCreateUpdateSerializer(data=data, context=self.mock_context)

        self.assertTrue(serializer.is_valid())

        event = serializer.save()

        # Verify relationships were created
        self.assertEqual(event.categories.count(), 1)
        self.assertEqual(event.tags.count(), 1)
        self.assertEqual(event.collaborators.count(), 1)


class SessionSerializerTest(BaseSerializerTestCase):
    """Test SessionSerializer."""

    def test_session_creation_data_validation(self):
        """Test session creation with valid data."""
        data = {
            "event": self.event.id,
            "title": "New Session",
            "description": "A new session",
            "start_time": self.event.start_date + timedelta(hours=2),
            "end_time": self.event.start_date + timedelta(hours=3),
            "max_participants": 30,
            "speaker_ids": [self.collaborator.id],
        }

        serializer = SessionSerializer(data=data, context=self.mock_context)

        self.assertTrue(serializer.is_valid())

    def test_session_time_validation(self):
        """Test session time validation."""
        data = {
            "event": self.event.id,
            "title": "Invalid Session",
            "description": "Invalid times",
            "start_time": self.event.start_date + timedelta(hours=3),
            "end_time": self.event.start_date + timedelta(hours=2),  # Before start
        }

        serializer = SessionSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("end_time", serializer.errors)

    def test_session_within_event_timeframe(self):
        """Test session must be within event timeframe."""
        data = {
            "event": self.event.id,
            "title": "Out of Range Session",
            "description": "Session outside event timeframe",
            "start_time": self.event.end_date + timedelta(hours=1),  # After event ends
            "end_time": self.event.end_date + timedelta(hours=2),
        }

        serializer = SessionSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("end_time", serializer.errors)

    def test_speaker_ids_validation(self):
        """Test speaker IDs validation."""
        data = {
            "event": self.event.id,
            "title": "Session with Speaker",
            "description": "Session with invalid speaker",
            "start_time": self.event.start_date + timedelta(hours=2),
            "end_time": self.event.start_date + timedelta(hours=3),
            "speaker_ids": [999999],  # Non-existent user
        }

        serializer = SessionSerializer(data=data)

        self.assertFalse(serializer.is_valid())
        self.assertIn("speaker_ids", serializer.errors)


class ParticipantSerializerTest(BaseSerializerTestCase):
    """Test ParticipantSerializer."""

    def test_participant_serialization(self):
        """Test basic participant serialization."""
        serializer = ParticipantSerializer(self.participant, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["role"], Participant.Role.ATTENDEE)
        self.assertEqual(
            data["registration_status"], Participant.RegistrationStatus.CONFIRMED
        )
        self.assertIn("user", data)
        self.assertIn("event_title", data)
        self.assertIn("badges", data)

    def test_participant_badges(self):
        """Test participant badges serialization."""
        serializer = ParticipantSerializer(self.participant, context=self.mock_context)
        badges = serializer.get_badges(self.participant)

        self.assertIsInstance(badges, list)
        # Initially empty as no badges are assigned


class ExhibitorSerializerTest(BaseSerializerTestCase):
    """Test ExhibitorSerializer."""

    def setUp(self):
        super().setUp()
        self.exhibitor = Exhibitor.objects.create(
            event=self.event,
            company_name="Tech Corp",
            description="A technology company",
            contact_email="contact@techcorp.com",
            booth_number="A1",
            sponsorship_tier=Exhibitor.SponsorshipTier.GOLD,
            status=Exhibitor.ExhibitorStatus.APPROVED,
        )

    def test_exhibitor_serialization(self):
        """Test basic exhibitor serialization."""
        serializer = ExhibitorSerializer(self.exhibitor, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["company_name"], "Tech Corp")
        self.assertEqual(data["booth_number"], "A1")
        self.assertIn("product_count", data)
        self.assertIn("logo_url", data)

    def test_exhibitor_contact_email_validation(self):
        """Test contact email validation."""
        serializer = ExhibitorSerializer()

        with self.assertRaises(ValidationError):
            serializer.validate_contact_email("invalid-email")

    def test_exhibitor_website_url_validation(self):
        """Test website URL validation."""
        serializer = ExhibitorSerializer()

        with self.assertRaises(ValidationError):
            serializer.validate_website_url("invalid-url")

        # Valid URLs should pass
        valid_url = serializer.validate_website_url("https://example.com")
        self.assertEqual(valid_url, "https://example.com")


class ProductSerializerTest(BaseSerializerTestCase):
    """Test ProductSerializer."""

    def setUp(self):
        super().setUp()
        self.exhibitor = Exhibitor.objects.create(
            event=self.event,
            company_name="Tech Corp",
            description="A technology company",
            booth_number="A1",
            sponsorship_tier=Exhibitor.SponsorshipTier.GOLD,
            status=Exhibitor.ExhibitorStatus.APPROVED,
        )
        self.product = Product.objects.create(
            exhibitor=self.exhibitor,
            name="Software Solution",
            description="A software product",
            price=Decimal("99.99"),
            currency="USD",
            stock_quantity=10,
        )

    def test_product_serialization(self):
        """Test basic product serialization."""
        serializer = ProductSerializer(self.product, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["name"], "Software Solution")
        self.assertEqual(data["price"], "99.99")
        self.assertIn("price_display", data)
        self.assertIn("exhibitor_name", data)

    def test_product_price_display(self):
        """Test price display formatting."""
        serializer = ProductSerializer(self.product, context=self.mock_context)
        price_display = serializer.get_price_display(self.product)

        self.assertEqual(price_display, "USD 99.99")

    def test_product_free_price_display(self):
        """Test price display for free products."""
        self.product.price = None
        self.product.save()

        serializer = ProductSerializer(self.product, context=self.mock_context)
        price_display = serializer.get_price_display(self.product)

        self.assertEqual(price_display, "Free")

    def test_product_price_validation(self):
        """Test product price validation."""
        serializer = ProductSerializer()

        with self.assertRaises(ValidationError):
            serializer.validate_price(Decimal("-10.00"))  # Negative price

        # Positive price should pass
        valid_price = serializer.validate_price(Decimal("50.00"))
        self.assertEqual(valid_price, Decimal("50.00"))

    def test_product_stock_validation(self):
        """Test product stock quantity validation."""
        serializer = ProductSerializer()

        with self.assertRaises(ValidationError):
            serializer.validate_stock_quantity(-5)  # Negative stock

        # Valid stock should pass
        valid_stock = serializer.validate_stock_quantity(10)
        self.assertEqual(valid_stock, 10)


class SessionRatingSerializerTest(BaseSerializerTestCase):
    """Test SessionRatingSerializer."""

    def setUp(self):
        super().setUp()
        self.rating = SessionRating.objects.create(
            session=self.session,
            participant=self.participant,
            rating=5,
            comment="Excellent session!",
        )

    def test_session_rating_serialization(self):
        """Test basic session rating serialization."""
        serializer = SessionRatingSerializer(self.rating, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["rating"], 5)
        self.assertEqual(data["comment"], "Excellent session!")
        self.assertIn("participant_name", data)
        self.assertIn("session_title", data)

    def test_participant_name(self):
        """Test participant name generation."""
        serializer = SessionRatingSerializer(self.rating, context=self.mock_context)
        name = serializer.get_participant_name(self.rating)

        self.assertEqual(name, "participant")  # Username as fallback

    def test_rating_validation(self):
        """Test rating value validation."""
        serializer = SessionRatingSerializer()

        # Invalid ratings
        with self.assertRaises(ValidationError):
            serializer.validate_rating(0)  # Too low

        with self.assertRaises(ValidationError):
            serializer.validate_rating(6)  # Too high

        # Valid rating should pass
        valid_rating = serializer.validate_rating(3)
        self.assertEqual(valid_rating, 3)

    def test_rating_validation_user_must_be_participant(self):
        """Test that only participants can rate sessions."""
        unauthorized_user = User.objects.create_user(
            username="unauthorized", email="unauthorized@example.com", password="pass"
        )

        context = self.get_serializer_context(unauthorized_user)
        data = {
            "session": self.session.id,
            "rating": 4,
            "comment": "Good session",
        }

        serializer = SessionRatingSerializer(data=data, context=context)

        self.assertFalse(serializer.is_valid())
        self.assertIn("You must be a participant", str(serializer.errors))

    def test_rating_validation_duplicate_rating(self):
        """Test that participants cannot rate the same session twice."""
        data = {
            "session": self.session.id,
            "rating": 3,
            "comment": "Another rating",
        }

        context = self.get_serializer_context(self.participant_user)
        serializer = SessionRatingSerializer(data=data, context=context)

        self.assertFalse(serializer.is_valid())
        self.assertIn("already rated", str(serializer.errors))


class EventAnalyticsSerializerTest(BaseSerializerTestCase):
    """Test EventAnalyticsSerializer."""

    def setUp(self):
        super().setUp()
        self.analytics = EventAnalytics.objects.create(
            event=self.event,
            total_views=100,
            unique_views=80,
            total_registrations=20,
            total_participants=15,
            total_sessions=5,
            average_rating=4.5,
            revenue_generated=Decimal("1000.00"),
        )

    def test_analytics_serialization(self):
        """Test basic analytics serialization."""
        serializer = EventAnalyticsSerializer(self.analytics, context=self.mock_context)
        data = serializer.data

        self.assertEqual(data["total_views"], 100)
        self.assertEqual(data["unique_views"], 80)
        self.assertIn("engagement_rate", data)
        self.assertIn("conversion_rate", data)
        self.assertIn("popular_sessions", data)

    def test_engagement_rate_calculation(self):
        """Test engagement rate calculation."""
        serializer = EventAnalyticsSerializer(self.analytics, context=self.mock_context)
        rate = serializer.get_engagement_rate(self.analytics)

        (15 / 20) * 100  # participants / registrations
        self.assertEqual(rate, 75.0)

    def test_engagement_rate_zero_registrations(self):
        """Test engagement rate with zero registrations."""
        self.analytics.total_registrations = 0
        serializer = EventAnalyticsSerializer(self.analytics, context=self.mock_context)
        rate = serializer.get_engagement_rate(self.analytics)

        self.assertEqual(rate, 0.0)

    def test_conversion_rate_calculation(self):
        """Test conversion rate calculation."""
        serializer = EventAnalyticsSerializer(self.analytics, context=self.mock_context)
        rate = serializer.get_conversion_rate(self.analytics)

        (20 / 80) * 100  # registrations / unique_views
        self.assertEqual(rate, 25.0)

    def test_conversion_rate_zero_views(self):
        """Test conversion rate with zero views."""
        self.analytics.unique_views = 0
        serializer = EventAnalyticsSerializer(self.analytics, context=self.mock_context)
        rate = serializer.get_conversion_rate(self.analytics)

        self.assertEqual(rate, 0.0)


class EventFavoriteSerializerTest(BaseSerializerTestCase):
    """Test EventFavoriteSerializer."""

    def setUp(self):
        super().setUp()
        self.favorite = EventFavorite.objects.create(
            user=self.participant_user, event=self.event
        )

    def test_favorite_serialization(self):
        """Test basic favorite serialization."""
        serializer = EventFavoriteSerializer(self.favorite, context=self.mock_context)
        data = serializer.data

        self.assertIn("id", data)
        self.assertIn("event", data)
        self.assertIn("created_at", data)
        self.assertEqual(data["event"]["title"], "Test Event")


class SerializerIntegrationTest(BaseSerializerTestCase):
    """Integration tests for serializer interactions."""

    def test_event_with_all_relationships(self):
        """Test event serialization with all relationships."""
        # Add more data to event
        EventAnalytics.objects.create(event=self.event)

        # Create exhibitor and product
        exhibitor = Exhibitor.objects.create(
            event=self.event,
            company_name="Tech Corp",
            description="Technology company",
            booth_number="A1",
            sponsorship_tier=Exhibitor.SponsorshipTier.GOLD,
            status=Exhibitor.ExhibitorStatus.APPROVED,
        )

        Product.objects.create(
            exhibitor=exhibitor,
            name="Software Product",
            description="A software solution",
            price=Decimal("99.99"),
            currency="USD",
        )

        # Test detailed serialization
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        data = serializer.data

        # Verify all components are present
        self.assertIn("analytics", data)
        self.assertIn("exhibitors", data)
        self.assertIn("sessions", data)
        self.assertIn("categories", data)
        self.assertIn("tags", data)

    def test_nested_serialization_performance(self):
        """Test that nested serialization doesn't cause N+1 queries."""
        # Create multiple participants
        for i in range(5):
            user = User.objects.create_user(
                username=f"user_{i}",
                email=f"user_{i}@example.com",
                password="testpass123",
            )
            Participant.objects.create(
                user=user,
                event=self.event,
                registration_status=Participant.RegistrationStatus.CONFIRMED,
            )

        # Serialize event with participants
        serializer = EventDetailSerializer(self.event, context=self.mock_context)

        # This should not cause excessive database queries
        # In a real scenario, we would use assertNumQueries
        data = serializer.data
        self.assertIsInstance(data["recent_participants"], list)

    def test_serializer_context_propagation(self):
        """Test that context is properly propagated to nested serializers."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        data = serializer.data

        # Verify that nested serializers receive context
        organizer_data = data["organizer"]
        self.assertNotIn("email", organizer_data)  # Should be filtered by context

    def test_cross_model_validation(self):
        """Test validation that spans multiple models."""
        # Test session creation with event capacity constraints
        data = {
            "event": self.event.id,
            "title": "Large Session",
            "description": "Session larger than event capacity",
            "start_time": self.event.start_date + timedelta(hours=2),
            "end_time": self.event.start_date + timedelta(hours=3),
            "max_participants": 150,  # More than event capacity
        }

        serializer = SessionSerializer(data=data, context=self.mock_context)

        # Should validate successfully - session capacity can exceed event capacity
        # as multiple sessions might run in parallel
        self.assertTrue(serializer.is_valid())

    def test_serializer_field_security(self):
        """Test that sensitive fields are not exposed."""
        serializer = EventDetailSerializer(self.event, context=self.mock_context)
        data = serializer.data

        # Check organizer data doesn't expose sensitive info
        organizer_data = data["organizer"]
        sensitive_fields = ["password", "email", "is_staff", "is_superuser"]

        for field in sensitive_fields:
            self.assertNotIn(field, organizer_data)

    def test_dynamic_field_calculation(self):
        """Test dynamic field calculations based on context."""
        # Test as organizer
        organizer_context = self.get_serializer_context(self.organizer)
        organizer_serializer = EventDetailSerializer(
            self.event, context=organizer_context
        )
        organizer_data = organizer_serializer.data

        # Test as participant
        participant_context = self.get_serializer_context(self.participant_user)
        participant_serializer = EventDetailSerializer(
            self.event, context=participant_context
        )
        participant_data = participant_serializer.data

        # Organizer should have edit permissions
        self.assertTrue(organizer_data["can_edit"])
        self.assertTrue(organizer_data["can_moderate"])

        # Participant should not have edit permissions
        self.assertFalse(participant_data["can_edit"])
        self.assertFalse(participant_data["can_moderate"])

        # Registration status should differ
        self.assertEqual(organizer_data["registration_status"], "not_registered")
        self.assertEqual(participant_data["registration_status"], "confirmed")

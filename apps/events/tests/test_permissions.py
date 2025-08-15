"""
Comprehensive permission tests for events app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from guardian.shortcuts import assign_perm
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import (
    Event,
    EventAnalytics,
    Participant,
    Session,
)
from ..permissions import (
    CanAccessAnalytics,
    CanModerateEvent,
    CanRateSession,
    CanViewEvent,
    IsEventOrganizerOrCollaborator,
    IsOwnerOrReadOnly,
    IsParticipantOrOrganizer,
    IsRegisteredParticipant,
    IsSessionSpeakerOrOrganizer,
)

User = get_user_model()


class BasePermissionTestCase(TestCase):
    """Base test case with common setup for permission tests."""

    def setUp(self):
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

        # Create event
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PUBLIC,
            status=Event.EventStatus.PUBLISHED,
        )

        # Add collaborator
        self.event.collaborators.add(self.collaborator)

        # Create participant
        self.participant = Participant.objects.create(
            user=self.participant_user,
            event=self.event,
            role=Participant.Role.ATTENDEE,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        # Create session
        self.session = Session.objects.create(
            event=self.event,
            title="Test Session",
            description="A test session",
            start_time=self.event.start_date + timedelta(hours=1),
            end_time=self.event.start_date + timedelta(hours=2),
        )

    def create_mock_request(self, user):
        """Create a mock request with user."""
        from unittest.mock import Mock

        request = Mock()
        request.user = user
        request.method = "GET"
        return request


class IsOwnerOrReadOnlyTest(BasePermissionTestCase):
    """Test IsOwnerOrReadOnly permission."""

    def setUp(self):
        super().setUp()
        self.permission = IsOwnerOrReadOnly()

    def test_owner_can_modify(self):
        """Test that owner can modify object."""
        request = self.create_mock_request(self.organizer)
        request.method = "POST"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_non_owner_cannot_modify(self):
        """Test that non-owner cannot modify object."""
        request = self.create_mock_request(self.random_user)
        request.method = "POST"

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_anyone_can_read(self):
        """Test that anyone can read object."""
        request = self.create_mock_request(self.random_user)
        request.method = "GET"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )


class IsEventOrganizerOrCollaboratorTest(BasePermissionTestCase):
    """Test IsEventOrganizerOrCollaborator permission."""

    def setUp(self):
        super().setUp()
        self.permission = IsEventOrganizerOrCollaborator()

    def test_organizer_can_modify(self):
        """Test that organizer can modify event."""
        request = self.create_mock_request(self.organizer)
        request.method = "PATCH"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_collaborator_can_modify(self):
        """Test that collaborator can modify event."""
        request = self.create_mock_request(self.collaborator)
        request.method = "PATCH"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_participant_cannot_modify(self):
        """Test that participant cannot modify event."""
        request = self.create_mock_request(self.participant_user)
        request.method = "PATCH"

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_random_user_cannot_modify(self):
        """Test that random user cannot modify event."""
        request = self.create_mock_request(self.random_user)
        request.method = "PATCH"

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_user_with_explicit_permission_can_modify(self):
        """Test that user with explicit permission can modify event."""
        assign_perm("events.change_event", self.random_user, self.event)

        request = self.create_mock_request(self.random_user)
        request.method = "PATCH"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_safe_methods_allowed(self):
        """Test that safe methods are allowed for anyone."""
        request = self.create_mock_request(self.random_user)
        request.method = "GET"

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )


class CanModerateEventTest(BasePermissionTestCase):
    """Test CanModerateEvent permission."""

    def setUp(self):
        super().setUp()
        self.permission = CanModerateEvent()

    def test_staff_can_moderate(self):
        """Test that staff can moderate any event."""
        request = self.create_mock_request(self.staff_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_organizer_can_moderate(self):
        """Test that organizer can moderate their event."""
        request = self.create_mock_request(self.organizer)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_user_with_moderate_permission_can_moderate(self):
        """Test that user with explicit permission can moderate."""
        assign_perm("events.moderate_event", self.random_user, self.event)

        request = self.create_mock_request(self.random_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_random_user_cannot_moderate(self):
        """Test that random user cannot moderate event."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_unauthenticated_user_cannot_moderate(self):
        """Test that unauthenticated user cannot moderate."""
        from django.contrib.auth.models import AnonymousUser

        request = self.create_mock_request(AnonymousUser())

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )


class IsParticipantOrOrganizerTest(BasePermissionTestCase):
    """Test IsParticipantOrOrganizer permission."""

    def setUp(self):
        super().setUp()
        self.permission = IsParticipantOrOrganizer()

    def test_participant_can_access_own_record(self):
        """Test that participant can access their own record."""
        request = self.create_mock_request(self.participant_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.participant)
        )

    def test_organizer_can_access_participant_record(self):
        """Test that organizer can access participant records."""
        request = self.create_mock_request(self.organizer)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.participant)
        )

    def test_collaborator_can_access_participant_record(self):
        """Test that collaborator can access participant records."""
        request = self.create_mock_request(self.collaborator)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.participant)
        )

    def test_random_user_cannot_access_participant_record(self):
        """Test that random user cannot access participant records."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.participant)
        )


class CanViewEventTest(BasePermissionTestCase):
    """Test CanViewEvent permission."""

    def setUp(self):
        super().setUp()
        self.permission = CanViewEvent()

    def test_public_event_viewable_by_anyone(self):
        """Test that public events are viewable by anyone."""
        from django.contrib.auth.models import AnonymousUser

        request = self.create_mock_request(AnonymousUser())

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_private_event_viewable_by_organizer(self):
        """Test that private events are viewable by organizer."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        request = self.create_mock_request(self.organizer)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_private_event_viewable_by_collaborator(self):
        """Test that private events are viewable by collaborators."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        request = self.create_mock_request(self.collaborator)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_private_event_viewable_by_participant(self):
        """Test that private events are viewable by participants."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        request = self.create_mock_request(self.participant_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_private_event_not_viewable_by_random_user(self):
        """Test that private events are not viewable by random users."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_private_event_not_viewable_by_anonymous(self):
        """Test that private events are not viewable by anonymous users."""
        from django.contrib.auth.models import AnonymousUser

        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        request = self.create_mock_request(AnonymousUser())

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )


class IsSessionSpeakerOrOrganizerTest(BasePermissionTestCase):
    """Test IsSessionSpeakerOrOrganizer permission."""

    def setUp(self):
        super().setUp()
        self.permission = IsSessionSpeakerOrOrganizer()

        # Create speaker
        self.speaker = User.objects.create_user(
            username="speaker", email="speaker@example.com", password="testpass123"
        )

        # Create speaker participant
        self.speaker_participant = Participant.objects.create(
            user=self.speaker,
            event=self.event,
            role=Participant.Role.SPEAKER,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

    def test_organizer_can_manage_session(self):
        """Test that organizer can manage sessions."""
        request = self.create_mock_request(self.organizer)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.session)
        )

    def test_collaborator_can_manage_session(self):
        """Test that collaborator can manage sessions."""
        request = self.create_mock_request(self.collaborator)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.session)
        )

    def test_speaker_can_manage_own_session(self):
        """Test that speaker can manage their own session."""
        # Add speaker to session
        self.session.participants.add(self.speaker_participant)

        request = self.create_mock_request(self.speaker)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.session)
        )

    def test_random_user_cannot_manage_session(self):
        """Test that random user cannot manage sessions."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.session)
        )


class CanAccessAnalyticsTest(BasePermissionTestCase):
    """Test CanAccessAnalytics permission."""

    def setUp(self):
        super().setUp()
        self.permission = CanAccessAnalytics()
        self.analytics = EventAnalytics.objects.create(event=self.event)

    def test_staff_can_access_analytics(self):
        """Test that staff can access any analytics."""
        request = self.create_mock_request(self.staff_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.analytics)
        )

    def test_organizer_can_access_analytics(self):
        """Test that organizer can access their event analytics."""
        request = self.create_mock_request(self.organizer)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.analytics)
        )

    def test_collaborator_can_access_analytics(self):
        """Test that collaborator can access event analytics."""
        request = self.create_mock_request(self.collaborator)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.analytics)
        )

    def test_participant_cannot_access_analytics(self):
        """Test that participant cannot access analytics."""
        request = self.create_mock_request(self.participant_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.analytics)
        )

    def test_random_user_cannot_access_analytics(self):
        """Test that random user cannot access analytics."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.analytics)
        )


class IsRegisteredParticipantTest(BasePermissionTestCase):
    """Test IsRegisteredParticipant permission."""

    def setUp(self):
        super().setUp()
        self.permission = IsRegisteredParticipant()

    def test_registered_participant_has_access(self):
        """Test that registered participant has access."""
        request = self.create_mock_request(self.participant_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_unregistered_user_has_no_access(self):
        """Test that unregistered user has no access."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_cancelled_participant_has_no_access(self):
        """Test that cancelled participant has no access."""
        self.participant.registration_status = Participant.RegistrationStatus.CANCELLED
        self.participant.save()

        request = self.create_mock_request(self.participant_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )

    def test_pending_participant_has_no_access(self):
        """Test that pending participant has no access."""
        self.participant.registration_status = Participant.RegistrationStatus.PENDING
        self.participant.save()

        request = self.create_mock_request(self.participant_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.event)
        )


class CanRateSessionTest(BasePermissionTestCase):
    """Test CanRateSession permission."""

    def setUp(self):
        super().setUp()
        self.permission = CanRateSession()

    def test_confirmed_participant_can_rate(self):
        """Test that confirmed participant can rate sessions."""
        request = self.create_mock_request(self.participant_user)

        self.assertTrue(
            self.permission.has_object_permission(request, None, self.session)
        )

    def test_unregistered_user_cannot_rate(self):
        """Test that unregistered user cannot rate sessions."""
        request = self.create_mock_request(self.random_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.session)
        )

    def test_cancelled_participant_cannot_rate(self):
        """Test that cancelled participant cannot rate sessions."""
        self.participant.registration_status = Participant.RegistrationStatus.CANCELLED
        self.participant.save()

        request = self.create_mock_request(self.participant_user)

        self.assertFalse(
            self.permission.has_object_permission(request, None, self.session)
        )


class PermissionIntegrationTest(APITestCase):
    """Integration tests for permissions with API endpoints."""

    def setUp(self):
        self.client = APIClient()

        # Create users
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.random_user = User.objects.create_user(
            username="random", email="random@example.com", password="testpass123"
        )

        # Create event
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PUBLIC,
            status=Event.EventStatus.PUBLISHED,
        )

    def test_event_update_permission_denied(self):
        """Test that non-organizer cannot update event."""
        self.client.force_authenticate(user=self.random_user)

        url = f"/api/v1/events/{self.event.id}/"
        data = {"title": "Updated Title"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_event_update_permission_granted(self):
        """Test that organizer can update event."""
        self.client.force_authenticate(user=self.organizer)

        url = f"/api/v1/events/{self.event.id}/"
        data = {"title": "Updated Title"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_event_access_denied(self):
        """Test that private event is not accessible to unauthorized users."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        self.client.force_authenticate(user=self.random_user)

        url = f"/api/v1/events/{self.event.id}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_private_event_access_granted(self):
        """Test that private event is accessible to organizer."""
        self.event.visibility = Event.Visibility.PRIVATE
        self.event.save()

        self.client.force_authenticate(user=self.organizer)

        url = f"/api/v1/events/{self.event.id}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_analytics_access_denied(self):
        """Test that analytics access is denied to non-organizers."""
        self.client.force_authenticate(user=self.random_user)

        url = f"/api/v1/events/{self.event.id}/analytics/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_analytics_access_granted(self):
        """Test that analytics access is granted to organizer."""
        self.client.force_authenticate(user=self.organizer)

        url = f"/api/v1/events/{self.event.id}/analytics/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

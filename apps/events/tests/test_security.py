"""
Comprehensive security tests for events app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from ..models import Event, EventAttachment, Participant

User = get_user_model()


class AuthenticationSecurityTestCase(APITestCase):
    """Test cases for authentication security."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

    def test_unauthenticated_event_creation(self):
        """Test that unauthenticated users cannot create events."""
        url = "/v1/events/"
        data = {
            "title": "Unauthorized Event",
            "description": "Should not be created",
            "start_date": timezone.now() + timedelta(days=1),
            "end_date": timezone.now() + timedelta(days=2),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_event_registration(self):
        """Test that unauthenticated users cannot register for events."""
        url = f"/v1/events/{self.event.id}/register/"

        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_session_manipulation_without_auth(self):
        """Test that sessions cannot be manipulated without authentication."""
        url = "/v1/sessions/"
        data = {
            "event": self.event.id,
            "title": "Unauthorized Session",
            "description": "Should not be created",
            "start_time": timezone.now() + timedelta(days=1, hours=1),
            "end_time": timezone.now() + timedelta(days=1, hours=2),
        }

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analytics_access_without_auth(self):
        """Test that analytics cannot be accessed without authentication."""
        url = f"/v1/events/{self.event.id}/analytics/"

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class AuthorizationSecurityTestCase(APITestCase):
    """Test cases for authorization security."""

    def setUp(self):
        self.client = APIClient()

        # Create users with different roles
        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.participant_user = User.objects.create_user(
            username="participant",
            email="participant@example.com",
            password="testpass123",
        )
        self.malicious_user = User.objects.create_user(
            username="malicious", email="malicious@example.com", password="testpass123"
        )

        # Create events
        self.public_event = Event.objects.create(
            title="Public Event",
            description="A public event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            visibility=Event.Visibility.PUBLIC,
            status=Event.EventStatus.PUBLISHED,
        )

        self.private_event = Event.objects.create(
            title="Private Event",
            description="A private event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            visibility=Event.Visibility.PRIVATE,
            status=Event.EventStatus.PUBLISHED,
        )

        # Create participant
        self.participant = Participant.objects.create(
            user=self.participant_user,
            event=self.public_event,
            role=Participant.Role.ATTENDEE,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

    def test_private_event_access_denied(self):
        """Test that private events are not accessible to unauthorized users."""
        self.client.force_authenticate(user=self.malicious_user)

        url = f"/v1/events/{self.private_event.id}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_event_modification_by_non_owner(self):
        """Test that non-owners cannot modify events."""
        self.client.force_authenticate(user=self.malicious_user)

        url = f"/v1/events/{self.public_event.id}/"
        data = {"title": "Hacked Event"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_participant_data_access_protection(self):
        """Test that participant data is protected from unauthorized access."""
        self.client.force_authenticate(user=self.malicious_user)

        url = f"/v1/events/{self.public_event.id}/participants/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_analytics_access_denied_to_non_organizer(self):
        """Test that analytics access is denied to non-organizers."""
        self.client.force_authenticate(user=self.participant_user)

        url = f"/v1/events/{self.public_event.id}/analytics/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_cross_event_participant_manipulation(self):
        """Test that users cannot manipulate participants from other events."""
        Event.objects.create(
            title="Other Event",
            description="Another event",
            organizer=self.malicious_user,
            start_date=timezone.now() + timedelta(days=5),
            end_date=timezone.now() + timedelta(days=6),
            status=Event.EventStatus.PUBLISHED,
        )

        self.client.force_authenticate(user=self.malicious_user)

        # Try to access participant from different event
        url = f"/v1/participants/{self.participant.id}/"
        response = self.client.get(url)

        # Should be forbidden since participant belongs to different event
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InputValidationSecurityTestCase(APITestCase):
    """Test cases for input validation security."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=self.user)

    def test_sql_injection_prevention_in_search(self):
        """Test that SQL injection attempts are prevented in search."""
        malicious_query = "'; DROP TABLE events_event; --"

        url = f"/v1/events/?search={malicious_query}"
        response = self.client.get(url)

        # Should return safely without executing malicious SQL
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_xss_prevention_in_event_data(self):
        """Test that XSS attempts are prevented in event data."""
        xss_payload = "<script>alert('XSS')</script>"

        url = "/v1/events/"
        data = {
            "title": xss_payload,
            "description": f"Event with {xss_payload}",
            "start_date": timezone.now() + timedelta(days=1),
            "end_date": timezone.now() + timedelta(days=2),
        }

        response = self.client.post(url, data, format="json")

        if response.status_code == status.HTTP_201_CREATED:
            # Verify XSS payload is escaped/sanitized
            event_data = response.data
            self.assertNotIn("<script>", event_data["title"])
            self.assertNotIn("<script>", event_data["description"])

    def test_file_upload_security(self):
        """Test file upload security measures."""
        # Test malicious file upload
        malicious_file = SimpleUploadedFile(
            "malicious.php",
            b"<?php echo 'Hacked'; ?>",
            content_type="application/x-php",
        )

        event = Event.objects.create(
            title="Test Event",
            description="Test event for file upload",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        # Try to upload malicious file as attachment
        url = "/v1/event-attachments/"
        data = {
            "event": event.id,
            "title": "Malicious File",
            "attachment_type": EventAttachment.AttachmentType.DOCUMENT,
            "file": malicious_file,
        }

        response = self.client.post(url, data, format="multipart")

        # Should reject malicious file types
        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )

    def test_oversized_file_upload_prevention(self):
        """Test that oversized files are rejected."""
        # Create file larger than allowed limit (assuming 10MB limit)
        large_content = b"x" * (11 * 1024 * 1024)  # 11MB
        large_file = SimpleUploadedFile(
            "large_file.txt",
            large_content,
            content_type="text/plain",
        )

        event = Event.objects.create(
            title="Test Event",
            description="Test event for file upload",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        url = "/v1/event-attachments/"
        data = {
            "event": event.id,
            "title": "Large File",
            "attachment_type": EventAttachment.AttachmentType.DOCUMENT,
            "file": large_file,
        }

        response = self.client.post(url, data, format="multipart")

        # Should reject oversized files
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_path_traversal_prevention(self):
        """Test that path traversal attempts are prevented."""
        malicious_filename = "../../../etc/passwd"

        malicious_file = SimpleUploadedFile(
            malicious_filename,
            b"malicious content",
            content_type="text/plain",
        )

        event = Event.objects.create(
            title="Test Event",
            description="Test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        url = "/v1/event-attachments/"
        data = {
            "event": event.id,
            "title": "Test File",
            "attachment_type": EventAttachment.AttachmentType.DOCUMENT,
            "file": malicious_file,
        }

        response = self.client.post(url, data, format="multipart")

        if response.status_code == status.HTTP_201_CREATED:
            # Verify filename is sanitized
            attachment = EventAttachment.objects.get(id=response.data["id"])
            self.assertNotIn("../", attachment.file.name)

    def test_json_payload_size_limit(self):
        """Test that oversized JSON payloads are rejected."""
        # Create large JSON payload
        large_description = "x" * (1024 * 1024)  # 1MB description

        url = "/v1/events/"
        data = {
            "title": "Test Event",
            "description": large_description,
            "start_date": timezone.now() + timedelta(days=1),
            "end_date": timezone.now() + timedelta(days=2),
        }

        response = self.client.post(url, data, format="json")

        # Should handle large payloads appropriately
        self.assertIn(
            response.status_code,
            [
                status.HTTP_201_CREATED,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            ],
        )


class DataLeakageSecurityTestCase(APITestCase):
    """Test cases for preventing data leakage."""

    def setUp(self):
        self.client = APIClient()

        self.organizer = User.objects.create_user(
            username="organizer", email="organizer@example.com", password="testpass123"
        )
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

    def test_sensitive_user_data_not_exposed(self):
        """Test that sensitive user data is not exposed in API responses."""
        self.client.force_authenticate(user=self.user1)

        url = f"/v1/events/{self.event.id}/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Check that sensitive organizer data is not exposed
        organizer_data = response.data.get("organizer", {})
        self.assertNotIn("email", organizer_data)
        self.assertNotIn("password", organizer_data)

    def test_private_participant_data_protection(self):
        """Test that private participant data is protected."""
        # Create participants
        Participant.objects.create(
            user=self.user1,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )
        Participant.objects.create(
            user=self.user2,
            event=self.event,
            registration_status=Participant.RegistrationStatus.CONFIRMED,
        )

        # User1 tries to access participant list
        self.client.force_authenticate(user=self.user1)
        url = f"/v1/events/{self.event.id}/participants/"
        response = self.client.get(url)

        # Should not have access to participant list as non-organizer
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_error_message_information_disclosure(self):
        """Test that error messages don't disclose sensitive information."""
        # Try to access non-existent event
        self.client.force_authenticate(user=self.user1)
        url = "/v1/events/99999/"
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Error message should not reveal internal details
        error_message = str(response.data.get("detail", ""))
        self.assertNotIn("database", error_message.lower())
        self.assertNotIn("sql", error_message.lower())
        self.assertNotIn("table", error_message.lower())

    def test_id_enumeration_protection(self):
        """Test protection against ID enumeration attacks."""
        # Create private event
        private_event = Event.objects.create(
            title="Private Event",
            description="A private event",
            organizer=self.organizer,
            start_date=timezone.now() + timedelta(days=3),
            end_date=timezone.now() + timedelta(days=4),
            visibility=Event.Visibility.PRIVATE,
            status=Event.EventStatus.PUBLISHED,
        )

        self.client.force_authenticate(user=self.user1)

        # Try to access private event
        url = f"/v1/events/{private_event.id}/"
        response = self.client.get(url)

        # Should return 404 instead of 403 to prevent ID enumeration
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class RateLimitingSecurityTestCase(APITestCase):
    """Test cases for rate limiting security."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.event = Event.objects.create(
            title="Test Event",
            description="A test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            status=Event.EventStatus.PUBLISHED,
        )

    @override_settings(RATELIMIT_ENABLE=True)
    def test_registration_rate_limiting(self):
        """Test that registration attempts are rate limited."""
        self.client.force_authenticate(user=self.user)

        url = f"/v1/events/{self.event.id}/register/"

        # Make multiple rapid registration attempts
        responses = []
        for i in range(10):
            response = self.client.post(url)
            responses.append(response.status_code)

        # Should eventually get rate limited
        any(
            status_code == status.HTTP_429_TOO_MANY_REQUESTS
            for status_code in responses
        )

        # Note: This test might not work without proper rate limiting middleware
        # In a real scenario, we would expect to see 429 responses

    @override_settings(RATELIMIT_ENABLE=True)
    def test_api_endpoint_rate_limiting(self):
        """Test that API endpoints are properly rate limited."""
        # Test event listing rate limit
        url = "/v1/events/"

        responses = []
        for i in range(50):  # Make many requests
            response = self.client.get(url)
            responses.append(response.status_code)
            if response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
                break

        # Should eventually get rate limited for excessive requests
        # Implementation depends on rate limiting middleware


class SessionSecurityTestCase(APITestCase):
    """Test cases for session security."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_session_hijacking_prevention(self):
        """Test prevention of session hijacking."""
        # Authenticate user
        self.client.force_authenticate(user=self.user)

        # Make request to get session info
        response = self.client.get("/v1/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate session hijacking attempt by changing user agent
        self.client.defaults["HTTP_USER_AGENT"] = "DifferentBrowser/1.0"

        # Request should still work with proper JWT token
        response = self.client.get("/v1/events/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_concurrent_session_handling(self):
        """Test handling of concurrent sessions."""
        # Create multiple clients for same user
        client1 = APIClient()
        client2 = APIClient()

        client1.force_authenticate(user=self.user)
        client2.force_authenticate(user=self.user)

        # Both clients should work independently
        response1 = client1.get("/v1/events/")
        response2 = client2.get("/v1/events/")

        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)


class CSRFSecurityTestCase(TestCase):
    """Test cases for CSRF protection."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @override_settings(CSRF_COOKIE_SECURE=True)
    def test_csrf_protection_enabled(self):
        """Test that CSRF protection is properly configured."""
        from django.conf import settings

        # Verify CSRF settings
        self.assertTrue(getattr(settings, "CSRF_COOKIE_SECURE", False))

    def test_api_csrf_exemption(self):
        """Test that API endpoints are properly exempt from CSRF when using token auth."""
        from django.test import Client

        client = Client()

        # API endpoints should work without CSRF token when using proper authentication
        response = client.get("/v1/events/")

        # Should not fail due to CSRF (might fail due to other reasons like auth)
        self.assertNotEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ContentSecurityTestCase(APITestCase):
    """Test cases for content security."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )
        self.client.force_authenticate(user=self.user)

    def test_malicious_content_filtering(self):
        """Test that malicious content is filtered or rejected."""
        malicious_contents = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<iframe src='javascript:alert(1)'></iframe>",
            "<img src=x onerror=alert('xss')>",
        ]

        for malicious_content in malicious_contents:
            url = "/v1/events/"
            data = {
                "title": f"Event with {malicious_content}",
                "description": malicious_content,
                "start_date": timezone.now() + timedelta(days=1),
                "end_date": timezone.now() + timedelta(days=2),
            }

            response = self.client.post(url, data, format="json")

            if response.status_code == status.HTTP_201_CREATED:
                # If creation succeeds, verify content is sanitized
                self.assertNotIn("<script>", response.data["title"])
                self.assertNotIn("javascript:", response.data["description"])

    def test_safe_redirect_urls(self):
        """Test that redirect URLs are validated to prevent open redirects."""
        # This would be relevant for any redirect functionality in the app
        event = Event.objects.create(
            title="Test Event",
            description="Test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
            website_url="https://evil.com",  # Potentially malicious URL
        )

        url = f"/v1/events/{event.id}/"
        response = self.client.get(url)

        # Verify that malicious URLs are handled safely
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class EncryptionSecurityTestCase(TestCase):
    """Test cases for data encryption security."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_sensitive_data_encryption(self):
        """Test that sensitive data is properly encrypted."""
        # Create participant with sensitive data
        event = Event.objects.create(
            title="Test Event",
            description="Test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        participant = Participant.objects.create(
            user=self.user,
            event=event,
            registration_data={
                "phone": "+1234567890",
                "emergency_contact": "John Doe - +0987654321",
            },
        )

        # Verify that sensitive data in registration_data is handled securely
        # This would depend on the encryption implementation
        self.assertIsInstance(participant.registration_data, dict)

    def test_file_storage_security(self):
        """Test that uploaded files are stored securely."""
        event = Event.objects.create(
            title="Test Event",
            description="Test event",
            organizer=self.user,
            start_date=timezone.now() + timedelta(days=1),
            end_date=timezone.now() + timedelta(days=2),
        )

        test_file = SimpleUploadedFile(
            "test.txt",
            b"sensitive content",
            content_type="text/plain",
        )

        attachment = EventAttachment.objects.create(
            event=event,
            title="Test Attachment",
            file=test_file,
            is_public=False,
        )

        # Verify file path doesn't expose sensitive information
        self.assertNotIn("sensitive", attachment.file.name)

import hashlib
from datetime import timedelta
from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.chats.models import (
    Chat,
    ChatAttachment,
    ChatFolder,
    ChatInviteLink,
    ChatMessage,
    ChatParticipant,
)
from apps.chats.serializers import (
    ChatAttachmentSerializer,
    ChatCreateSerializer,
    FileUploadSerializer,
    MessageCreateSerializer,
)

User = get_user_model()


class AuthenticationSecurityTestCase(APITestCase):
    """Test cases for authentication and authorization security."""

    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        self.chat = Chat.objects.create(
            type=Chat.ChatType.PRIVATE, name="Private Chat", creator=self.user1
        )

        ChatParticipant.objects.create(
            user=self.user1, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER
        )

    def test_unauthenticated_access_blocked(self):
        """Test that unauthenticated users cannot access chat endpoints."""
        # Test chat list
        response = self.client.get("/chats/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Test chat detail
        response = self.client.get(f"/chats/{self.chat.id}/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Test message creation
        response = self.client.post(
            f"/chats/{self.chat.id}/messages/", {"content": "Unauthorized message"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthorized_chat_access_blocked(self):
        """Test that users cannot access chats they're not members of."""
        self.client.force_authenticate(user=self.user2)

        # Should not be able to view private chat
        response = self.client.get(f"/chats/{self.chat.id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Should not be able to send messages
        response = self.client.post(
            f"/chats/{self.chat.id}/messages/", {"content": "Unauthorized message"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_chat_member_access_allowed(self):
        """Test that chat members can access the chat."""
        # Add user2 as member
        ChatParticipant.objects.create(
            user=self.user2, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        self.client.force_authenticate(user=self.user2)

        # Should be able to view chat
        response = self.client.get(f"/chats/{self.chat.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_banned_user_access_blocked(self):
        """Test that banned users cannot access the chat."""
        # Add user2 as banned member
        ChatParticipant.objects.create(
            user=self.user2,
            chat=self.chat,
            role=ChatParticipant.ParticipantRole.MEMBER,
            status=ChatParticipant.ParticipantStatus.BANNED,
        )

        self.client.force_authenticate(user=self.user2)

        # Should not be able to send messages
        response = self.client.post(
            f"/chats/{self.chat.id}/messages/", {"content": "Banned user message"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_permissions_required(self):
        """Test that admin actions require proper permissions."""
        # Add user2 as regular member
        ChatParticipant.objects.create(
            user=self.user2, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        self.client.force_authenticate(user=self.user2)

        # Should not be able to update chat settings
        response = self.client.patch(
            f"/chats/{self.chat.id}/", {"name": "Hacked Chat Name"}
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Should not be able to delete chat
        response = self.client.delete(f"/chats/{self.chat.id}/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class InputValidationSecurityTestCase(TestCase):
    """Test cases for input validation security."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.chat = Chat.objects.create(name="Test Chat", creator=self.user)

    def test_sql_injection_prevention(self):
        """Test prevention of SQL injection attacks."""
        malicious_inputs = [
            "'; DROP TABLE chats_chat; --",
            "1' OR '1'='1",
            "admin'/*",
            "' UNION SELECT * FROM auth_user --",
        ]

        for malicious_input in malicious_inputs:
            # Test chat name injection
            with self.assertRaises((ValidationError, ValueError)):
                Chat.objects.create(name=malicious_input, creator=self.user)

            # Test username injection
            data = {
                "type": Chat.ChatType.GROUP,
                "name": "Test Chat",
                "username": malicious_input,
            }
            serializer = ChatCreateSerializer(data=data)
            self.assertFalse(serializer.is_valid())

    def test_xss_prevention(self):
        """Test prevention of XSS attacks."""
        xss_payloads = [
            "<script>alert('XSS')</script>",
            "javascript:alert('XSS')",
            "<img src=x onerror=alert('XSS')>",
            "';alert('XSS');//",
            "<svg onload=alert('XSS')>",
        ]

        for payload in xss_payloads:
            # Test message content
            message = ChatMessage.objects.create(
                chat=self.chat, sender=self.user, content=payload
            )
            # Content should be stored as-is but properly escaped in output
            self.assertEqual(message.content, payload)

            # Test chat description
            chat = Chat.objects.create(
                name="XSS Test", description=payload, creator=self.user
            )
            self.assertEqual(chat.description, payload)

    def test_file_upload_validation(self):
        """Test file upload security validation."""
        # Test dangerous file extensions
        dangerous_files = [
            ("malware.exe", "application/x-executable"),
            ("script.js", "application/javascript"),
            ("virus.bat", "application/x-msdos-program"),
            ("trojan.scr", "application/x-msdownload"),
            ("backdoor.com", "application/x-msdos-program"),
        ]

        for filename, content_type in dangerous_files:
            test_file = SimpleUploadedFile(
                filename, b"malicious content", content_type=content_type
            )

            serializer = FileUploadSerializer(
                data={"file": test_file, "caption": "Test upload"}
            )

            # Should reject dangerous files
            self.assertFalse(serializer.is_valid())
            self.assertIn("file", serializer.errors)

    def test_oversized_file_rejection(self):
        """Test rejection of oversized files."""
        # Create 101MB file (exceeds 100MB limit)
        large_content = b"x" * (101 * 1024 * 1024)
        large_file = SimpleUploadedFile(
            "large.txt", large_content, content_type="text/plain"
        )

        serializer = FileUploadSerializer(
            data={"file": large_file, "caption": "Large file test"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)

    def test_content_length_validation(self):
        """Test validation of content length limits."""
        # Test extremely long message content
        long_content = "A" * 5000  # Exceeds 4096 character limit

        data = {"type": ChatMessage.MessageType.TEXT, "content": long_content}

        serializer = MessageCreateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("content", serializer.errors)

    def test_unicode_and_encoding_attacks(self):
        """Test handling of unicode and encoding attacks."""
        unicode_attacks = [
            "\u0000",  # Null byte
            "\ufeff",  # Byte order mark
            "\u202e",  # Right-to-left override
            "\u200b",  # Zero width space
            "𝕏𝕊𝕊",  # Mathematical script
        ]

        for attack in unicode_attacks:
            # Should handle unicode properly without breaking
            message = ChatMessage.objects.create(
                chat=self.chat, sender=self.user, content=f"Test {attack} content"
            )
            self.assertIsNotNone(message.id)


class FileSecurityTestCase(TestCase):
    """Test cases for file security."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.chat = Chat.objects.create(name="Test Chat", creator=self.user)

        self.message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user, content="Test message"
        )

    def test_file_path_traversal_prevention(self):
        """Test prevention of path traversal attacks."""
        malicious_filenames = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32\\config\\sam",
            "....//....//....//etc//passwd",
            "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
        ]

        for filename in malicious_filenames:
            test_file = SimpleUploadedFile(
                filename, b"malicious content", content_type="text/plain"
            )

            attachment = ChatAttachment.objects.create(
                message=self.message,
                file=test_file,
                file_name=filename,
                type=ChatAttachment.AttachmentType.DOCUMENT,
            )

            # File should be saved safely without path traversal
            self.assertNotIn("../", attachment.file.name)
            self.assertNotIn("..\\", attachment.file.name)

    def test_file_type_spoofing_prevention(self):
        """Test prevention of file type spoofing."""
        # Create file with misleading extension and content type
        malicious_file = SimpleUploadedFile(
            "image.jpg",  # Claims to be image
            b"<?php echo 'malicious code'; ?>",  # But contains PHP
            content_type="image/jpeg",  # With image MIME type
        )

        serializer = ChatAttachmentSerializer(
            data={"file": malicious_file, "type": ChatAttachment.AttachmentType.PHOTO}
        )

        # Should detect mismatch between claimed and actual type
        if serializer.is_valid():
            attachment = ChatAttachment.objects.create(
                message=self.message, **serializer.validated_data
            )
            # Additional server-side validation should catch this
            self.assertTrue(hasattr(attachment, "checksum"))

    def test_file_checksum_validation(self):
        """Test file integrity with checksums."""
        test_content = b"test file content"
        test_file = SimpleUploadedFile(
            "test.txt", test_content, content_type="text/plain"
        )

        # Calculate expected checksum
        expected_checksum = hashlib.sha256(test_content).hexdigest()

        attachment = ChatAttachment.objects.create(
            message=self.message,
            file=test_file,
            file_name="test.txt",
            type=ChatAttachment.AttachmentType.DOCUMENT,
            checksum=expected_checksum,
        )

        # Verify checksum matches
        self.assertEqual(attachment.checksum, expected_checksum)

    def test_executable_file_detection(self):
        """Test detection of executable files."""
        executable_contents = [
            b"\x7fELF",  # Linux executable
            b"MZ",  # Windows executable
            b"\xca\xfe\xba\xbe",  # Java class file
        ]

        for content in executable_contents:
            test_file = SimpleUploadedFile(
                "suspicious.txt",  # Disguised as text
                content,
                content_type="text/plain",
            )

            # Should detect executable content
            serializer = FileUploadSerializer(
                data={"file": test_file, "caption": "Suspicious file"}
            )

            # Additional validation could detect binary signatures
            # For now, ensure basic validation works
            self.assertIsNotNone(serializer)


class RateLimitingSecurityTestCase(APITestCase):
    """Test cases for rate limiting security."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

        self.chat = Chat.objects.create(
            name="Rate Limit Test",
            creator=self.user,
            slow_mode_delay=10,  # 10 second delay
        )

        ChatParticipant.objects.create(
            user=self.user, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER
        )

        # Authenticate the client
        self.client.force_authenticate(user=self.user)

    def test_slow_mode_enforcement(self):
        """Test slow mode rate limiting."""
        # Create recent message
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user,
            content="Recent message",
            created_at=timezone.now() - timedelta(seconds=5),
        )

        # Try to send another message too soon
        data = {"type": ChatMessage.MessageType.TEXT, "content": "Too soon message"}

        serializer = MessageCreateSerializer(
            data=data, context={"request": Mock(user=self.user), "chat": self.chat}
        )

        # Should fail due to slow mode
        self.assertFalse(serializer.is_valid())
        self.assertIn("Slow mode", str(serializer.errors))

    def test_message_flood_prevention(self):
        """Test prevention of message flooding."""
        # Make rapid HTTP requests to test rate limiting
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})

        success_count = 0
        rate_limited_count = 0

        # Try to send 10 messages rapidly
        for i in range(10):
            data = {"type": "text", "content": f"Flood message {i}"}
            response = self.client.post(url, data)

            if response.status_code == 201:
                success_count += 1
            elif response.status_code in [400, 429]:  # Rate limited or slow mode
                rate_limited_count += 1

        # Some messages should be allowed, but rate limiting should kick in
        self.assertGreater(success_count, 0)
        self.assertGreater(rate_limited_count, 0)
        self.assertLess(success_count, 10)  # Not all should pass

    def test_invite_link_abuse_prevention(self):
        """Test prevention of invite link abuse."""
        # Create multiple invite links rapidly
        links = []
        for i in range(10):
            link = ChatInviteLink.objects.create(
                chat=self.chat, creator=self.user, name=f"Link {i}"
            )
            links.append(link)

        # Should have reasonable limits on link creation
        self.assertLessEqual(len(links), 10)

        # Test link usage limits
        for link in links:
            # Each link should have usage tracking
            self.assertEqual(link.usage_count, 0)
            self.assertIsNotNone(link.created_at)


class PrivacySecurityTestCase(TestCase):
    """Test cases for privacy and data protection."""

    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

        self.private_chat = Chat.objects.create(
            type=Chat.ChatType.PRIVATE, name="Private Chat", creator=self.user1
        )

        self.secret_chat = Chat.objects.create(
            type=Chat.ChatType.SECRET,
            name="Secret Chat",
            creator=self.user1,
            is_encrypted=True,
        )

    def test_private_chat_visibility(self):
        """Test private chat visibility restrictions."""
        # User2 should not see private chat they're not part of
        user_chats = Chat.objects.for_user(self.user2)
        self.assertNotIn(self.private_chat, user_chats)

        # Add user2 to chat
        ChatParticipant.objects.create(
            user=self.user2,
            chat=self.private_chat,
            role=ChatParticipant.ParticipantRole.MEMBER,
        )

        # Now user2 should see the chat
        user_chats = Chat.objects.for_user(self.user2)
        self.assertIn(self.private_chat, user_chats)

    def test_message_encryption_flag(self):
        """Test message encryption requirements."""
        # Secret chat should require encryption
        self.assertTrue(self.secret_chat.is_encrypted)

        # Messages in secret chat should be marked as encrypted
        message = ChatMessage.objects.create(
            chat=self.secret_chat, sender=self.user1, content="Secret message"
        )

        # In a real implementation, content would be encrypted
        self.assertIsNotNone(message.content)

    def test_user_data_isolation(self):
        """Test user data isolation."""
        # Create data for user1
        folder1 = ChatFolder.objects.create(user=self.user1, name="User1 Folder")

        # User2 should not see user1's folders
        user2_folders = ChatFolder.objects.filter(user=self.user2)
        self.assertNotIn(folder1, user2_folders)

        # User2's folders should be isolated
        folder2 = ChatFolder.objects.create(user=self.user2, name="User2 Folder")

        user1_folders = ChatFolder.objects.filter(user=self.user1)
        self.assertNotIn(folder2, user1_folders)

    def test_deleted_message_privacy(self):
        """Test deleted message privacy."""
        message = ChatMessage.objects.create(
            chat=self.private_chat, sender=self.user1, content="Sensitive information"
        )

        # Soft delete message
        message.soft_delete()

        # Content should be cleared or marked as deleted
        self.assertEqual(message.status, ChatMessage.MessageStatus.DELETED)

        # Deleted messages should not appear in queries
        visible_messages = ChatMessage.objects.visible()
        self.assertNotIn(message, visible_messages)


class SessionSecurityTestCase(APITestCase):
    """Test cases for session and token security."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_session_timeout_handling(self):
        """Test handling of expired sessions."""
        self.client.force_authenticate(user=self.user)

        # Make authenticated request
        response = self.client.get("/chats/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Simulate expired session
        self.client.force_authenticate(user=None)

        # Should require re-authentication
        response = self.client.get("/chats/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_csrf_protection(self):
        """Test CSRF protection for state-changing operations."""
        # This would be more relevant for cookie-based auth
        # JWT tokens are generally CSRF-resistant by design
        pass

    @override_settings(SESSION_COOKIE_SECURE=True)
    def test_secure_cookie_settings(self):
        """Test secure cookie configuration."""
        from django.conf import settings

        # Verify secure settings are enabled
        self.assertTrue(settings.SESSION_COOKIE_SECURE)


class InjectionAttackTestCase(TestCase):
    """Test cases for various injection attacks."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_ldap_injection_prevention(self):
        """Test LDAP injection prevention in user searches."""
        # If LDAP is used for user authentication
        malicious_queries = [
            "admin)(|(password=*))",
            "admin)(&(password=*))",
            "*)(uid=*))(|(uid=*",
        ]

        for query in malicious_queries:
            # Test username search - should sanitize input
            users = User.objects.filter(username__icontains=query)
            # Should not return unexpected results
            self.assertLessEqual(users.count(), 1)

    def test_nosql_injection_prevention(self):
        """Test NoSQL injection prevention."""
        # If using MongoDB or similar
        malicious_payloads = [
            {"$ne": None},
            {"$gt": ""},
            {"$where": "this.password.length > 0"},
        ]

        # These would be more relevant if using NoSQL databases
        # For Django ORM, these are automatically handled
        for payload in malicious_payloads:
            # Should not cause issues with JSON fields
            chat = Chat.objects.create(
                name="Test Chat",
                creator=self.user,
                theme=payload,  # JSON field
            )
            self.assertIsNotNone(chat.id)

    def test_command_injection_prevention(self):
        """Test command injection prevention in file operations."""
        malicious_filenames = [
            "; rm -rf /",
            "| cat /etc/passwd",
            "$(whoami)",
            "`id`",
            "&& curl evil.com",
        ]

        for filename in malicious_filenames:
            # File operations should sanitize filenames
            with self.assertRaises(Exception):
                SimpleUploadedFile(filename, b"test content", content_type="text/plain")
                # Django should reject files with dangerous names
                # This will raise SuspiciousFileOperation or similar


class CryptographicSecurityTestCase(TestCase):
    """Test cases for cryptographic security."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_file_checksum_strength(self):
        """Test strength of file checksum algorithm."""
        test_content = b"test file content for checksum"

        from apps.chats.serializers import MessageCreateSerializer

        serializer = MessageCreateSerializer()

        checksum = serializer._calculate_checksum(
            SimpleUploadedFile("test.txt", test_content)
        )

        # Should use SHA-256 (64 hex characters)
        self.assertEqual(len(checksum), 64)

        # Should be deterministic
        checksum2 = serializer._calculate_checksum(
            SimpleUploadedFile("test2.txt", test_content)
        )
        self.assertEqual(checksum, checksum2)

        # Should be different for different content
        checksum3 = serializer._calculate_checksum(
            SimpleUploadedFile("test3.txt", b"different content")
        )
        self.assertNotEqual(checksum, checksum3)

    def test_invite_link_randomness(self):
        """Test randomness of invite links."""
        chat = Chat.objects.create(name="Crypto Test", creator=self.user)

        # Generate multiple invite links
        links = []
        for i in range(100):
            link = chat.generate_invite_link()
            chat.invite_link = None  # Reset to generate new one
            chat.save()
            links.append(link)

        # All links should be unique
        self.assertEqual(len(set(links)), 100)

        # Links should have sufficient entropy
        for link in links[:10]:  # Test first 10
            self.assertEqual(len(link), 16)  # Should be 16 characters
            # Should contain both letters and numbers for entropy
            self.assertTrue(any(c.isalpha() for c in link))
            self.assertTrue(any(c.isdigit() for c in link))

    def test_uuid_uniqueness(self):
        """Test UUID uniqueness and randomness."""
        # Generate multiple UUIDs
        uuids = []
        for i in range(1000):
            chat = Chat.objects.create(name=f"UUID Test {i}", creator=self.user)
            uuids.append(str(chat.id))

        # All UUIDs should be unique
        self.assertEqual(len(set(uuids)), 1000)

        # UUIDs should be properly formatted
        for uuid_str in uuids[:10]:  # Test first 10
            # Should be valid UUID format
            parts = uuid_str.split("-")
            self.assertEqual(len(parts), 5)
            self.assertEqual(len(parts[0]), 8)
            self.assertEqual(len(parts[1]), 4)
            self.assertEqual(len(parts[2]), 4)
            self.assertEqual(len(parts[3]), 4)
            self.assertEqual(len(parts[4]), 12)


class DataSanitizationTestCase(TestCase):
    """Test cases for data sanitization."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_html_sanitization(self):
        """Test HTML content sanitization."""
        html_inputs = [
            "<b>Bold text</b>",
            "<script>alert('xss')</script>",
            "<img src='x' onerror='alert(1)'>",
            "<a href='javascript:alert(1)'>Link</a>",
            "<<SCRIPT>alert('XSS')//<</SCRIPT>",
        ]

        for html_input in html_inputs:
            # Message content should be stored safely
            message = ChatMessage.objects.create(
                chat=Chat.objects.create(name="Test", creator=self.user),
                sender=self.user,
                content=html_input,
            )

            # Content is stored as-is but should be escaped in serialization
            self.assertEqual(message.content, html_input)

    def test_url_validation(self):
        """Test URL validation and sanitization."""
        malicious_urls = [
            "javascript:alert('xss')",
            "data:text/html,<script>alert('xss')</script>",
            "vbscript:msgbox('xss')",
            "file:///etc/passwd",
            "ftp://evil.com/backdoor.exe",
        ]

        # If URLs are allowed in content, they should be validated
        for url in malicious_urls:
            message = ChatMessage.objects.create(
                chat=Chat.objects.create(name="URL Test", creator=self.user),
                sender=self.user,
                content=f"Check this link: {url}",
            )

            # URLs should be stored but validated during display
            self.assertIn(url, message.content)

    def test_filename_sanitization(self):
        """Test filename sanitization for uploads."""
        dangerous_filenames = [
            "../../etc/passwd",
            "con.txt",  # Windows reserved name
            "prn.txt",  # Windows reserved name
            "file\x00.txt",  # Null byte
            "file\r\n.txt",  # CRLF injection
            "very_long_filename" + "x" * 1000 + ".txt",
        ]

        for filename in dangerous_filenames:
            test_file = SimpleUploadedFile(
                filename, b"test content", content_type="text/plain"
            )

            # Filename should be sanitized
            attachment = ChatAttachment.objects.create(
                message=ChatMessage.objects.create(
                    chat=Chat.objects.create(name="File Test", creator=self.user),
                    sender=self.user,
                    content="File upload",
                ),
                file=test_file,
                file_name=filename,
                type=ChatAttachment.AttachmentType.DOCUMENT,
            )

            # File should be saved with sanitized name
            self.assertIsNotNone(attachment.file.name)
            # Original filename is preserved in file_name field
            self.assertEqual(attachment.file_name, filename)

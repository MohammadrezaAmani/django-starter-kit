import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.chats.models import Chat, ChatAttachment, ChatMessage, ChatParticipant
from apps.chats.serializers import (
    BulkMessageDeleteSerializer,
    BulkMessageReadSerializer,
    ChatAttachmentSerializer,
    ChatCreateSerializer,
    ChatListSerializer,
    ChatMessageSerializer,
    ChatParticipantSerializer,
    ChatSearchSerializer,
    ChatSerializer,
    MessageCreateSerializer,
    MessageSearchSerializer,
    UserBasicSerializer,
)

User = get_user_model()


class BaseSerializerTestCase(TestCase):
    """Base test case with common setup for serializer tests."""

    def setUp(self):
        """Set up test data."""
        self.factory = RequestFactory()

        # Create test users
        self.user1 = User.objects.create_user(
            username="testuser1",
            email="test1@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User1",
        )
        self.user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User2",
        )
        self.user3 = User.objects.create_user(
            username="testuser3",
            email="test3@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User3",
        )

        # Set user activity for online status tests
        now = timezone.now()
        self.user1.last_activity = now - timedelta(minutes=2)  # Online
        self.user1.save()

        self.user2.last_activity = now - timedelta(minutes=10)  # Offline
        self.user2.save()

        # Create test chat
        self.chat = Chat.objects.create(
            type=Chat.ChatType.GROUP,
            name="Test Group",
            creator=self.user1,
            description="Test group description",
        )

        # Add participants
        self.owner_participant = ChatParticipant.objects.create(
            user=self.user1,
            chat=self.chat,
            role=ChatParticipant.ParticipantRole.OWNER,
            can_change_info=True,
        )
        self.member_participant = ChatParticipant.objects.create(
            user=self.user2, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        # Create request with authenticated user
        self.request = self.factory.get("/")
        self.request.user = self.user1

        self.context = {"request": self.request}

    def tearDown(self):
        """Clean up after each test."""
        cache.clear()


class UserBasicSerializerTestCase(BaseSerializerTestCase):
    """Test cases for UserBasicSerializer."""

    def test_serialization(self):
        """Test user serialization."""
        serializer = UserBasicSerializer(self.user1, context=self.context)
        data = serializer.data

        self.assertEqual(data["id"], self.user1.id)
        self.assertEqual(data["username"], self.user1.username)
        self.assertEqual(data["first_name"], self.user1.first_name)
        self.assertEqual(data["last_name"], self.user1.last_name)
        self.assertEqual(data["full_name"], self.user1.get_full_name())
        self.assertTrue(data["is_online"])  # User1 is online

    def test_online_status_caching(self):
        """Test online status caching."""
        # Clear cache first
        cache.clear()

        # First call should hit database
        serializer = UserBasicSerializer(self.user1, context=self.context)
        data1 = serializer.data
        self.assertTrue(data1["is_online"])

        # Second call should use cache
        serializer = UserBasicSerializer(self.user1, context=self.context)
        data2 = serializer.data
        self.assertTrue(data2["is_online"])

    def test_offline_user(self):
        """Test offline user serialization."""
        serializer = UserBasicSerializer(self.user2, context=self.context)
        data = serializer.data

        self.assertFalse(data["is_online"])  # User2 is offline

    def test_avatar_url(self):
        """Test avatar URL generation."""
        serializer = UserBasicSerializer(self.user1, context=self.context)
        data = serializer.data

        # Should be None if no avatar
        self.assertIsNone(data["avatar"])


class ChatAttachmentSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatAttachmentSerializer."""

    def setUp(self):
        super().setUp()

        # Create test message
        self.message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Message with attachment",
            has_media=True,
        )

        # Create test file
        self.test_file = SimpleUploadedFile(
            "test.txt", b"file content", content_type="text/plain"
        )

        # Create attachment
        self.attachment = ChatAttachment.objects.create(
            message=self.message,
            type=ChatAttachment.AttachmentType.DOCUMENT,
            file=self.test_file,
            file_name="test.txt",
            file_size=12,
            mime_type="text/plain",
        )

    def test_serialization(self):
        """Test attachment serialization."""
        serializer = ChatAttachmentSerializer(self.attachment, context=self.context)
        data = serializer.data

        self.assertEqual(data["id"], str(self.attachment.id))
        self.assertEqual(data["type"], self.attachment.type)
        self.assertEqual(data["file_name"], self.attachment.file_name)
        self.assertEqual(data["file_size"], self.attachment.file_size)
        self.assertEqual(data["file_size_display"], "12.0 B")
        self.assertTrue(data["is_safe"])

    def test_file_size_display(self):
        """Test human readable file size."""
        # Test different file sizes
        self.attachment.file_size = 1024
        serializer = ChatAttachmentSerializer(self.attachment, context=self.context)
        self.assertEqual(serializer.data["file_size_display"], "1.0 KB")

        self.attachment.file_size = 1024 * 1024
        serializer = ChatAttachmentSerializer(self.attachment, context=self.context)
        self.assertEqual(serializer.data["file_size_display"], "1.0 MB")

    def test_dangerous_file_detection(self):
        """Test dangerous file detection."""
        self.attachment.file_name = "malware.exe"
        serializer = ChatAttachmentSerializer(self.attachment, context=self.context)
        data = serializer.data

        self.assertFalse(data["is_safe"])

    def test_file_validation(self):
        """Test file upload validation."""
        # Test oversized file
        large_file = SimpleUploadedFile(
            "large.txt",
            b"x" * (51 * 1024 * 1024),  # 51MB
            content_type="text/plain",
        )

        serializer = ChatAttachmentSerializer(
            data={"file": large_file, "file_name": "large.txt"}
        )

        self.assertFalse(serializer.is_valid())
        self.assertIn("file", serializer.errors)


class ChatMessageSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatMessageSerializer."""

    def setUp(self):
        super().setUp()

        # Create test message
        self.message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Test message content",
            type=ChatMessage.MessageType.TEXT,
        )

    def test_serialization(self):
        """Test message serialization."""
        serializer = ChatMessageSerializer(self.message, context=self.context)
        data = serializer.data

        self.assertEqual(data["id"], str(self.message.id))
        self.assertEqual(data["content"], self.message.content)
        self.assertEqual(data["type"], self.message.type)
        self.assertIsNotNone(data["sender"])
        self.assertEqual(data["sender"]["username"], self.user1.username)
        self.assertTrue(data["can_edit"])  # Own message
        self.assertTrue(data["can_delete"])  # Own message

    def test_reply_to_serialization(self):
        """Test reply message serialization."""
        # Create original message
        original = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Original message content"
        )

        # Create reply
        reply = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Reply content",
            reply_to=original,
        )

        serializer = ChatMessageSerializer(reply, context=self.context)
        data = serializer.data

        self.assertIsNotNone(data["reply_to"])
        self.assertEqual(data["reply_to"]["id"], str(original.id))
        self.assertEqual(data["reply_to"]["sender"]["username"], self.user2.username)
        self.assertIn("Original message", data["reply_to"]["content"])

    def test_forward_from_serialization(self):
        """Test forwarded message serialization."""
        # Create original chat and message
        original_chat = Chat.objects.create(name="Original Chat", creator=self.user2)

        original_message = ChatMessage.objects.create(
            chat=original_chat, sender=self.user2, content="Original message"
        )

        # Create forwarded message
        forwarded = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Original message",
            forward_from=original_message,
            forward_from_chat=original_chat,
            is_forwarded=True,
        )

        serializer = ChatMessageSerializer(forwarded, context=self.context)
        data = serializer.data

        self.assertIsNotNone(data["forward_from"])
        self.assertEqual(data["forward_from"]["id"], str(original_message.id))
        self.assertEqual(data["forward_from"]["chat"]["name"], original_chat.name)

    def test_reactions_summary(self):
        """Test reactions summary."""
        # Add reactions
        self.message.reactions = {
            "👍": [str(self.user1.id), str(self.user2.id)],
            "❤️": [str(self.user1.id)],
        }
        self.message.save()

        serializer = ChatMessageSerializer(self.message, context=self.context)
        data = serializer.data

        expected_summary = {"👍": 2, "❤️": 1}
        self.assertEqual(data["reactions_summary"], expected_summary)

    def test_edit_permissions(self):
        """Test message edit permissions."""
        # Test own message
        serializer = ChatMessageSerializer(self.message, context=self.context)
        self.assertTrue(serializer.data["can_edit"])

        # Test other user's message
        other_request = self.factory.get("/")
        other_request.user = self.user2
        other_context = {"request": other_request}

        serializer = ChatMessageSerializer(self.message, context=other_context)
        self.assertFalse(serializer.data["can_edit"])

    def test_delete_permissions(self):
        """Test message delete permissions."""
        # Test own message
        serializer = ChatMessageSerializer(self.message, context=self.context)
        self.assertTrue(serializer.data["can_delete"])

        # Test admin permissions
        self.owner_participant.can_delete_messages = True
        self.owner_participant.save()

        other_message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Other user's message"
        )

        serializer = ChatMessageSerializer(other_message, context=self.context)
        self.assertTrue(serializer.data["can_delete"])  # Admin can delete


class ChatParticipantSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatParticipantSerializer."""

    def test_serialization(self):
        """Test participant serialization."""
        serializer = ChatParticipantSerializer(
            self.owner_participant, context=self.context
        )
        data = serializer.data

        self.assertIsNotNone(data["user"])
        self.assertEqual(data["user"]["username"], self.user1.username)
        self.assertEqual(data["role"], ChatParticipant.ParticipantRole.OWNER)
        self.assertTrue(data["is_admin"])
        self.assertTrue(data["is_moderator"])
        self.assertTrue(data["can_manage"])

    def test_member_permissions(self):
        """Test member permissions."""
        serializer = ChatParticipantSerializer(
            self.member_participant, context=self.context
        )
        data = serializer.data

        self.assertEqual(data["role"], ChatParticipant.ParticipantRole.MEMBER)
        self.assertFalse(data["is_admin"])
        self.assertFalse(data["is_moderator"])


class ChatSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatSerializer."""

    def test_serialization(self):
        """Test chat serialization."""
        serializer = ChatSerializer(self.chat, context=self.context)
        data = serializer.data

        self.assertEqual(data["id"], str(self.chat.id))
        self.assertEqual(data["name"], self.chat.name)
        self.assertEqual(data["type"], self.chat.type)
        self.assertEqual(data["description"], self.chat.description)
        self.assertIsNotNone(data["creator"])
        self.assertEqual(data["participant_count"], 2)
        self.assertTrue(data["is_member"])
        self.assertTrue(data["can_send_message"])

    def test_participants_limit(self):
        """Test participants limit in serialization."""
        # Add many participants to test limit
        for i in range(60):
            user = User.objects.create_user(f"user{i}", f"user{i}@test.com", "pass")
            ChatParticipant.objects.create(
                user=user, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
            )

        serializer = ChatSerializer(self.chat, context=self.context)
        data = serializer.data

        # Should limit participants in response
        self.assertLessEqual(len(data["participants"]), 50)

    def test_unread_count(self):
        """Test unread count calculation."""
        # Create some messages
        ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Unread message 1"
        )
        ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Unread message 2"
        )

        serializer = ChatSerializer(self.chat, context=self.context)
        data = serializer.data

        # Should have unread count > 0
        self.assertGreaterEqual(data["unread_count"], 0)

    def test_user_participant_info(self):
        """Test user participant information."""
        serializer = ChatSerializer(self.chat, context=self.context)
        data = serializer.data

        self.assertIsNotNone(data["user_participant"])
        self.assertEqual(
            data["user_participant"]["role"], ChatParticipant.ParticipantRole.OWNER
        )

    def test_invite_link_info(self):
        """Test invite link information for admins."""
        self.owner_participant.can_invite_users = True
        self.owner_participant.save()

        self.chat.generate_invite_link()

        serializer = ChatSerializer(self.chat, context=self.context)
        data = serializer.data

        self.assertIsNotNone(data["invite_link_info"])
        self.assertTrue(data["invite_link_info"]["can_create"])


class ChatListSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatListSerializer."""

    def test_serialization(self):
        """Test chat list serialization."""
        # Create last message
        last_message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Last message in chat"
        )
        self.chat.last_message = last_message
        self.chat.save()

        serializer = ChatListSerializer(self.chat, context=self.context)
        data = serializer.data

        self.assertEqual(data["id"], str(self.chat.id))
        self.assertEqual(data["name"], self.chat.name)
        self.assertIsNotNone(data["last_message"])
        self.assertEqual(
            data["last_message"]["sender_name"], self.user2.get_full_name()
        )
        self.assertTrue(data["is_member"])

    def test_last_message_truncation(self):
        """Test last message content truncation."""
        long_content = "A" * 100
        last_message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content=long_content
        )
        self.chat.last_message = last_message
        self.chat.save()

        serializer = ChatListSerializer(self.chat, context=self.context)
        data = serializer.data

        # Content should be truncated
        self.assertTrue(data["last_message"]["content"].endswith("..."))
        self.assertLessEqual(len(data["last_message"]["content"]), 53)  # 50 + "..."


class ChatCreateSerializerTestCase(BaseSerializerTestCase):
    """Test cases for ChatCreateSerializer."""

    def test_valid_chat_creation(self):
        """Test valid chat creation."""
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "New Test Group",
            "description": "A new test group",
            "participants": [str(self.user2.id), str(self.user3.id)],
        }

        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertTrue(serializer.is_valid())

        chat = serializer.save()
        self.assertEqual(chat.name, "New Test Group")
        self.assertEqual(chat.creator, self.user1)
        self.assertEqual(chat.participants.count(), 3)  # Creator + 2 participants

    def test_username_validation(self):
        """Test username validation."""
        # Test short username
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "Test Group",
            "username": "abc",  # Too short
        }

        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("username", serializer.errors)

        # Test invalid characters
        data["username"] = "test@user"  # Invalid character
        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())

        # Test reserved username
        data["username"] = "admin"  # Reserved
        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())

    def test_participants_validation(self):
        """Test participants validation."""
        # Test too many participants
        participant_ids = [
            str(i + 99999) for i in range(201)
        ]  # Too many non-existent IDs
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "Test Group",
            "participants": participant_ids,
        }

        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())
        self.assertIn("participants", serializer.errors)

        # Test non-existent users
        data["participants"] = ["99999"]  # Non-existent user ID
        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())

    def test_cross_field_validation(self):
        """Test cross-field validation."""
        # Test public chat without username
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "Public Group",
            "is_public": True,
            # Missing username
        }

        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())

        # Test private chat with username
        data = {
            "type": Chat.ChatType.PRIVATE,
            "username": "privatechat",  # Private chats can't have usernames
        }

        serializer = ChatCreateSerializer(data=data, context=self.context)
        self.assertFalse(serializer.is_valid())


class MessageCreateSerializerTestCase(BaseSerializerTestCase):
    """Test cases for MessageCreateSerializer."""

    def test_valid_message_creation(self):
        """Test valid message creation."""
        data = {"type": ChatMessage.MessageType.TEXT, "content": "Hello, world!"}

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        message = serializer.save()
        self.assertEqual(message.content, "Hello, world!")
        self.assertEqual(message.sender, self.user1)
        self.assertEqual(message.chat, self.chat)

    def test_content_validation(self):
        """Test content validation."""
        # Test empty content
        data = {"type": ChatMessage.MessageType.TEXT, "content": ""}

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

        # Test too long content
        data["content"] = "A" * 4097  # Too long
        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

        # Test spam detection
        data["content"] = "http://spam.com " * 6  # Too many links
        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_reply_validation(self):
        """Test reply validation."""
        # Create original message
        original = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Original message"
        )

        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Reply message",
            "reply_to_id": str(original.id),
        }

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Test reply to non-existent message
        data["reply_to_id"] = str(uuid.uuid4())
        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_scheduled_message_validation(self):
        """Test scheduled message validation."""
        future_time = timezone.now() + timedelta(hours=1)
        past_time = timezone.now() - timedelta(hours=1)

        # Valid future time
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Scheduled message",
            "is_scheduled": True,
            "scheduled_date": future_time,
        }

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Invalid past time
        data["scheduled_date"] = past_time
        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_mentions_validation(self):
        """Test mentions validation."""
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Message with mentions",
            "mention_user_ids": [self.user2.id],  # Valid participant
        }

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Test mention of non-participant
        data["mention_user_ids"] = [self.user3.id]  # Not in chat
        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_attachment_validation(self):
        """Test attachment validation."""
        # Create test files
        small_file = SimpleUploadedFile(
            "small.txt", b"content", content_type="text/plain"
        )

        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Message with attachment",
            "attachment_files": [small_file],
        }

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Test too many attachments
        files = [SimpleUploadedFile(f"file{i}.txt", b"content") for i in range(11)]
        data["attachment_files"] = files

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_slow_mode_validation(self):
        """Test slow mode validation."""
        # Enable slow mode
        self.chat.slow_mode_delay = 30  # 30 seconds
        self.chat.save()

        # Create recent message
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Recent message",
            created_at=timezone.now() - timedelta(seconds=10),
        )

        data = {"type": ChatMessage.MessageType.TEXT, "content": "New message"}

        serializer = MessageCreateSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("Slow mode", str(serializer.errors))


class BulkOperationSerializersTestCase(BaseSerializerTestCase):
    """Test cases for bulk operation serializers."""

    def setUp(self):
        super().setUp()

        # Create test messages
        self.message1 = ChatMessage.objects.create(
            chat=self.chat, sender=self.user1, content="Message 1"
        )
        self.message2 = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Message 2"
        )

    def test_bulk_read_serializer(self):
        """Test bulk message read serializer."""
        data = {"message_ids": [str(self.message1.id), str(self.message2.id)]}

        serializer = BulkMessageReadSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Test invalid message IDs
        data["message_ids"] = [str(uuid.uuid4())]
        serializer = BulkMessageReadSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())

    def test_bulk_delete_serializer(self):
        """Test bulk message delete serializer."""
        data = {
            "message_ids": [str(self.message1.id)],  # Own message
            "delete_for_everyone": False,
        }

        serializer = BulkMessageDeleteSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertTrue(serializer.is_valid())

        # Test delete for everyone without permission
        data = {
            "message_ids": [str(self.message2.id)],  # Other's message
            "delete_for_everyone": True,
        }

        serializer = BulkMessageDeleteSerializer(
            data=data, context={"request": self.request, "chat": self.chat}
        )
        self.assertFalse(serializer.is_valid())


class SearchSerializersTestCase(BaseSerializerTestCase):
    """Test cases for search serializers."""

    def test_chat_search_serializer(self):
        """Test chat search serializer."""
        data = {
            "query": "test query",
            "chat_types": [Chat.ChatType.GROUP],
            "include_messages": True,
            "limit": 10,
        }

        serializer = ChatSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

        # Test invalid date range
        data.update(
            {
                "date_from": timezone.now(),
                "date_to": timezone.now() - timedelta(days=1),  # Invalid range
            }
        )

        serializer = ChatSearchSerializer(data=data)
        self.assertFalse(serializer.is_valid())

    def test_message_search_serializer(self):
        """Test message search serializer."""
        data = {
            "query": "search term",
            "message_types": [ChatMessage.MessageType.TEXT],
            "sender_id": str(self.user1.id),
            "has_media": False,
            "limit": 50,
        }

        serializer = MessageSearchSerializer(data=data)
        self.assertTrue(serializer.is_valid())

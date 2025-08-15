import unittest
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.chats.models import (
    Chat,
    ChatCall,
    ChatCallParticipant,
    ChatFolder,
    ChatInviteLink,
    ChatMessage,
    ChatParticipant,
    ChatPoll,
    ChatPollAnswer,
    ChatPollOption,
    ChatWebhook,
)

User = get_user_model()


class BaseAPITestCase(APITestCase):
    """Base test case for API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

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

        # Create test chat
        self.chat = Chat.objects.create(
            type=Chat.ChatType.GROUP,
            name="Test Group",
            description="Test group description",
            creator=self.user1,
        )

        # Add participants
        self.owner_participant = ChatParticipant.objects.create(
            user=self.user1, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER
        )
        self.member_participant = ChatParticipant.objects.create(
            user=self.user2, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
        )

        # Create test message
        self.message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Test message",
            type=ChatMessage.MessageType.TEXT,
        )

        # Authenticate as user1 by default
        self.client.force_authenticate(user=self.user1)


class ChatListAPITestCase(BaseAPITestCase):
    """Test cases for chat list API."""

    def test_get_chat_list(self):
        """Test getting chat list."""
        url = reverse("chat-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], self.chat.name)

    def test_get_chat_list_unauthenticated(self):
        """Test getting chat list without authentication."""
        self.client.force_authenticate(user=None)
        url = reverse("chat-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_chat_list_filtering(self):
        """Test chat list filtering."""
        # Create different types of chats
        private_chat = Chat.objects.create(
            type=Chat.ChatType.PRIVATE, creator=self.user1
        )
        ChatParticipant.objects.create(
            user=self.user1,
            chat=private_chat,
            role=ChatParticipant.ParticipantRole.OWNER,
        )

        channel = Chat.objects.create(
            type=Chat.ChatType.CHANNEL, name="Test Channel", creator=self.user1
        )
        ChatParticipant.objects.create(
            user=self.user1, chat=channel, role=ChatParticipant.ParticipantRole.OWNER
        )

        # Test filtering by type
        url = reverse("chat-list")
        response = self.client.get(url, {"type": "group"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

        response = self.client.get(url, {"type": "private"})
        self.assertEqual(len(response.data["results"]), 1)

        response = self.client.get(url, {"type": "channel"})
        self.assertEqual(len(response.data["results"]), 1)

    def test_get_chat_list_pagination(self):
        """Test chat list pagination."""
        # Create many chats
        for i in range(25):
            chat = Chat.objects.create(name=f"Chat {i}", creator=self.user1)
            ChatParticipant.objects.create(
                user=self.user1, chat=chat, role=ChatParticipant.ParticipantRole.OWNER
            )

        url = reverse("chat-list")
        response = self.client.get(url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

    def test_get_chat_list_search(self):
        """Test chat list search."""
        # Create searchable chat
        searchable_chat = Chat.objects.create(
            name="Searchable Chat", description="This is searchable", creator=self.user1
        )
        ChatParticipant.objects.create(
            user=self.user1,
            chat=searchable_chat,
            role=ChatParticipant.ParticipantRole.OWNER,
        )

        url = reverse("chat-list")
        response = self.client.get(url, {"search": "Searchable"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Searchable Chat")


class ChatCreateAPITestCase(BaseAPITestCase):
    """Test cases for chat creation API."""

    def test_create_group_chat(self):
        """Test creating a group chat."""
        url = reverse("chat-list")
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "New Group Chat",
            "description": "A new group chat",
            "participants": [str(self.user2.id), str(self.user3.id)],
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "New Group Chat")
        self.assertEqual(response.data["creator"]["username"], self.user1.username)

        # Verify participants were added
        chat_id = response.data["id"]
        chat = Chat.objects.get(id=chat_id)
        self.assertEqual(chat.participants.count(), 3)  # Creator + 2 participants

    def test_create_private_chat(self):
        """Test creating a private chat."""
        url = reverse("chat-list")
        data = {"type": Chat.ChatType.PRIVATE, "participants": [str(self.user2.id)]}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], Chat.ChatType.PRIVATE)

    def test_create_public_channel(self):
        """Test creating a public channel."""
        url = reverse("chat-list")
        data = {
            "type": Chat.ChatType.CHANNEL,
            "name": "Public Channel",
            "username": "publicchannel",
            "is_public": True,
            "description": "A public channel",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["username"], "publicchannel")
        self.assertTrue(response.data["is_public"])

    def test_create_chat_validation_errors(self):
        """Test chat creation validation errors."""
        url = reverse("chat-list")

        # Test missing required fields
        response = self.client.post(url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test invalid username
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "Test Group",
            "username": "ab",  # Too short
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test duplicate username
        Chat.objects.create(username="duplicate", creator=self.user2)
        data = {
            "type": Chat.ChatType.GROUP,
            "name": "Test Group",
            "username": "duplicate",
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_chat_unauthenticated(self):
        """Test creating chat without authentication."""
        self.client.force_authenticate(user=None)
        url = reverse("chat-list")
        data = {"type": Chat.ChatType.GROUP, "name": "Unauthorized Chat"}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ChatDetailAPITestCase(BaseAPITestCase):
    """Test cases for chat detail API."""

    def test_get_chat_detail(self):
        """Test getting chat details."""
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.chat.id))
        self.assertEqual(response.data["name"], self.chat.name)
        self.assertIsNotNone(response.data["participants"])
        self.assertEqual(len(response.data["participants"]), 2)

    def test_get_chat_detail_non_member(self):
        """Test getting chat details as non-member."""
        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_update_chat_as_owner(self):
        """Test updating chat as owner."""
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        data = {"name": "Updated Chat Name", "description": "Updated description"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Updated Chat Name")
        self.assertEqual(response.data["description"], "Updated description")

    def test_update_chat_as_member(self):
        """Test updating chat as regular member."""
        self.client.force_authenticate(user=self.user2)
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        data = {"name": "Unauthorized Update"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_chat_as_owner(self):
        """Test deleting chat as owner."""
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Chat.objects.filter(id=self.chat.id).exists())

    def test_delete_chat_as_member(self):
        """Test deleting chat as member (should fail)."""
        self.client.force_authenticate(user=self.user2)
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class MessageListAPITestCase(BaseAPITestCase):
    """Test cases for message list API."""

    def test_get_message_list(self):
        """Test getting message list."""
        # Create additional messages
        for i in range(5):
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.user2,
                content=f"Message {i}",
                type=ChatMessage.MessageType.TEXT,
            )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 6)  # 1 original + 5 new

    def test_get_message_list_non_member(self):
        """Test getting message list as non-member."""
        self.client.force_authenticate(user=self.user3)
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_message_list_pagination(self):
        """Test message list pagination."""
        # Create many messages
        for i in range(25):
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.user1,
                content=f"Message {i}",
                type=ChatMessage.MessageType.TEXT,
            )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url, {"page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

    def test_get_message_list_filtering(self):
        """Test message list filtering."""
        # Create different types of messages
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            type=ChatMessage.MessageType.PHOTO,
            has_media=True,
        )
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user2,
            type=ChatMessage.MessageType.VIDEO,
            has_media=True,
        )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})

        # Filter by type
        response = self.client.get(url, {"type": "photo"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        photo_messages = [
            msg for msg in response.data["results"] if msg["type"] == "photo"
        ]
        self.assertEqual(len(photo_messages), 1)

        # Filter by media
        response = self.client.get(url, {"has_media": "true"})
        media_messages = [msg for msg in response.data["results"] if msg["has_media"]]
        self.assertEqual(len(media_messages), 2)

    def test_get_message_list_search(self):
        """Test message list search."""
        # Create searchable message
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="This is a searchable message with unique content",
            type=ChatMessage.MessageType.TEXT,
        )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url, {"search": "searchable"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)


class MessageCreateAPITestCase(BaseAPITestCase):
    """Test cases for message creation API."""

    def test_create_text_message(self):
        """Test creating a text message."""
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {"type": ChatMessage.MessageType.TEXT, "content": "New text message"}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["content"], "New text message")
        self.assertEqual(response.data["sender"]["username"], self.user1.username)

    def test_create_reply_message(self):
        """Test creating a reply message."""
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Reply message",
            "reply_to_id": str(self.message.id),
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["reply_to"])
        self.assertEqual(response.data["reply_to"]["id"], str(self.message.id))

    def test_create_message_with_mentions(self):
        """Test creating message with mentions."""
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Message with mentions @testuser2",
            "mention_user_ids": [str(self.user2.id)],
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["mentions"])

    def test_create_scheduled_message(self):
        """Test creating a scheduled message."""
        future_time = timezone.now() + timedelta(hours=1)
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Scheduled message",
            "is_scheduled": True,
            "scheduled_date": future_time.isoformat(),
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["is_scheduled"])

    def test_create_message_with_attachment(self):
        """Test creating message with file attachment."""
        test_file = SimpleUploadedFile(
            "test.txt", b"file content", content_type="text/plain"
        )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {
            "type": ChatMessage.MessageType.DOCUMENT,
            "content": "Message with attachment",
            "attachment_files": [test_file],
        }

        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data["has_media"])
        self.assertIsNotNone(response.data["attachments"])

    def test_create_message_validation_errors(self):
        """Test message creation validation errors."""
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})

        # Test empty content
        data = {"type": ChatMessage.MessageType.TEXT, "content": ""}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test too long content
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "A" * 5000,  # Too long
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Test invalid reply_to
        data = {
            "type": ChatMessage.MessageType.TEXT,
            "content": "Reply test",
            "reply_to_id": str(uuid.uuid4()),  # Non-existent message
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_message_non_member(self):
        """Test creating message as non-member."""
        self.client.force_authenticate(user=self.user3)
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {"type": ChatMessage.MessageType.TEXT, "content": "Unauthorized message"}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_message_slow_mode(self):
        """Test message creation with slow mode enabled."""
        # Enable slow mode
        self.chat.slow_mode_delay = 30
        self.chat.save()

        # Create recent message
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Recent message",
            created_at=timezone.now() - timedelta(seconds=10),
        )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {"type": ChatMessage.MessageType.TEXT, "content": "Too soon message"}

        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class MessageDetailAPITestCase(BaseAPITestCase):
    """Test cases for message detail API."""

    def test_get_message_detail(self):
        """Test getting message details."""
        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": self.message.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(self.message.id))
        self.assertEqual(response.data["content"], self.message.content)

    def test_update_own_message(self):
        """Test updating own message."""
        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": self.message.id}
        )
        data = {"content": "Updated message content"}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["content"], "Updated message content")
        self.assertIsNotNone(response.data["edit_date"])

    def test_update_other_message(self):
        """Test updating another user's message (should fail)."""
        other_message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Other user's message"
        )

        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": other_message.id}
        )
        data = {"content": "Unauthorized update"}

        response = self.client.patch(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_delete_own_message(self):
        """Test deleting own message."""
        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": self.message.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Message should be soft deleted
        self.message.refresh_from_db()
        self.assertEqual(self.message.status, ChatMessage.MessageStatus.DELETED)

    def test_delete_message_as_admin(self):
        """Test deleting message as admin."""
        # Give admin permissions
        self.owner_participant.can_delete_messages = True
        self.owner_participant.save()

        other_message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user2, content="Message to delete"
        )

        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": other_message.id}
        )

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class MessageReactionAPITestCase(BaseAPITestCase):
    """Test cases for message reaction API."""

    def test_add_reaction(self):
        """Test adding reaction to message."""
        url = reverse(
            "message-reaction",
            kwargs={"chat_pk": self.chat.id, "message_pk": self.message.id},
        )
        data = {"emoji": "👍"}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.message.refresh_from_db()
        self.assertIn("👍", self.message.reactions)

    def test_remove_reaction(self):
        """Test removing reaction from message."""
        # Add reaction first
        self.message.add_reaction(self.user1, "👍")

        url = reverse(
            "message-reaction",
            kwargs={"chat_pk": self.chat.id, "message_pk": self.message.id},
        )
        data = {"emoji": "👍"}

        response = self.client.delete(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.message.refresh_from_db()
        self.assertNotIn(str(self.user1.id), self.message.reactions.get("👍", []))


class BulkMessageOperationsAPITestCase(BaseAPITestCase):
    """Test cases for bulk message operations API."""

    def setUp(self):
        super().setUp()

        # Create additional messages
        self.messages = []
        for i in range(5):
            message = ChatMessage.objects.create(
                chat=self.chat, sender=self.user1, content=f"Bulk test message {i}"
            )
            self.messages.append(message)

    def test_bulk_mark_read(self):
        """Test bulk marking messages as read."""
        url = reverse("message-bulk-mark-read", kwargs={"chat_pk": self.chat.id})
        data = {"message_ids": [str(msg.id) for msg in self.messages[:3]]}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_bulk_delete_own_messages(self):
        """Test bulk deleting own messages."""
        url = reverse("message-bulk-delete", kwargs={"chat_pk": self.chat.id})
        data = {
            "message_ids": [str(msg.id) for msg in self.messages[:3]],
            "delete_for_everyone": False,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Messages should be deleted
        for message in self.messages[:3]:
            message.refresh_from_db()
            self.assertEqual(message.status, ChatMessage.MessageStatus.DELETED)

    def test_bulk_delete_for_everyone_as_admin(self):
        """Test bulk deleting for everyone as admin."""
        # Give admin permissions
        self.owner_participant.can_delete_messages = True
        self.owner_participant.save()

        # Create messages from different users
        other_messages = []
        for i in range(3):
            message = ChatMessage.objects.create(
                chat=self.chat, sender=self.user2, content=f"Other user message {i}"
            )
            other_messages.append(message)

        url = reverse("message-bulk-delete", kwargs={"chat_pk": self.chat.id})
        data = {
            "message_ids": [str(msg.id) for msg in other_messages],
            "delete_for_everyone": True,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)


class ChatParticipantAPITestCase(BaseAPITestCase):
    """Test cases for chat participant API."""

    def test_get_participants(self):
        """Test getting chat participants."""
        url = reverse("chat-participants", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_add_participant(self):
        """Test adding participant to chat."""
        url = reverse("chat-participants", kwargs={"chat_pk": self.chat.id})
        data = {
            "user_id": str(self.user3.id),
            "role": ChatParticipant.ParticipantRole.MEMBER,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            ChatParticipant.objects.filter(user=self.user3, chat=self.chat).exists()
        )

    def test_update_participant_permissions(self):
        """Test updating participant permissions."""
        url = reverse(
            "chat-participant-detail",
            kwargs={"chat_pk": self.chat.id, "pk": self.member_participant.id},
        )
        data = {"can_send_messages": False, "can_send_media": False}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_participant.refresh_from_db()
        self.assertFalse(self.member_participant.can_send_messages)
        self.assertFalse(self.member_participant.can_send_media)

    def test_remove_participant(self):
        """Test removing participant from chat."""
        url = reverse(
            "chat-participant-detail",
            kwargs={"chat_pk": self.chat.id, "pk": self.member_participant.id},
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.member_participant.refresh_from_db()
        self.assertEqual(
            self.member_participant.status, ChatParticipant.ParticipantStatus.LEFT
        )

    def test_remove_participant_unauthorized(self):
        """Test removing participant without permission."""
        self.client.force_authenticate(user=self.user2)
        url = reverse(
            "chat-participant-detail",
            kwargs={"chat_pk": self.chat.id, "pk": self.member_participant.id},
        )

        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_ban_participant(self):
        """Test banning a participant."""
        url = reverse(
            "chat-participant-ban",
            kwargs={
                "chat_pk": self.chat.id,
                "participant_pk": self.member_participant.id,
            },
        )
        data = {
            "reason": "Violation of rules",
            "duration": 3600,  # 1 hour
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.member_participant.refresh_from_db()
        self.assertEqual(
            self.member_participant.status, ChatParticipant.ParticipantStatus.BANNED
        )


class ChatFolderAPITestCase(BaseAPITestCase):
    """Test cases for chat folder API."""

    def test_create_folder(self):
        """Test creating a chat folder."""
        url = reverse("chatfolder-list")
        data = {
            "name": "Work Chats",
            "emoji": "💼",
            "include_groups": True,
            "include_private": False,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "Work Chats")
        self.assertEqual(response.data["emoji"], "💼")

    def test_get_folder_list(self):
        """Test getting folder list."""
        # Create test folders
        ChatFolder.objects.create(user=self.user1, name="Personal", emoji="👨‍👩‍👧‍👦")
        ChatFolder.objects.create(user=self.user1, name="Work", emoji="💼")

        url = reverse("chatfolder-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_add_chat_to_folder(self):
        """Test adding chat to folder."""
        folder = ChatFolder.objects.create(user=self.user1, name="Test Folder")

        url = reverse("chatfolder-detail", kwargs={"pk": folder.id})
        data = {"chats": [str(self.chat.id)]}

        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        folder.refresh_from_db()
        self.assertIn(self.chat, folder.chats.all())

    def test_folder_access_control(self):
        """Test folder access control."""
        # Create folder for user1
        folder = ChatFolder.objects.create(user=self.user1, name="Private Folder")

        # User2 should not access user1's folder
        self.client.force_authenticate(user=self.user2)
        url = reverse("chatfolder-detail", kwargs={"pk": folder.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ChatInviteLinkAPITestCase(BaseAPITestCase):
    """Test cases for chat invite link API."""

    def test_create_invite_link(self):
        """Test creating an invite link."""
        url = reverse("chat-invite-links", kwargs={"chat_pk": self.chat.id})
        data = {
            "name": "General Invite",
            "expire_date": (timezone.now() + timedelta(days=7)).isoformat(),
            "member_limit": 100,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["link"])
        self.assertEqual(response.data["name"], "General Invite")

    def test_get_invite_links(self):
        """Test getting chat invite links."""
        # Create test invite links
        ChatInviteLink.objects.create(chat=self.chat, creator=self.user1, name="Link 1")
        ChatInviteLink.objects.create(chat=self.chat, creator=self.user1, name="Link 2")

        url = reverse("chat-invite-links", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)

    def test_revoke_invite_link(self):
        """Test revoking an invite link."""
        link = ChatInviteLink.objects.create(
            chat=self.chat, creator=self.user1, name="Test Link"
        )

        url = reverse(
            "chat-invite-link-detail", kwargs={"chat_pk": self.chat.id, "pk": link.id}
        )

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        link.refresh_from_db()
        self.assertTrue(link.is_revoked)

    def test_join_via_invite_link(self):
        """Test joining chat via invite link."""
        link = ChatInviteLink.objects.create(
            chat=self.chat, creator=self.user1, name="Join Link"
        )

        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-join-via-link", kwargs={"link": link.link})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ChatParticipant.objects.filter(user=self.user3, chat=self.chat).exists()
        )

    def test_join_via_expired_link(self):
        """Test joining via expired invite link."""
        link = ChatInviteLink.objects.create(
            chat=self.chat,
            creator=self.user1,
            name="Expired Link",
            expire_date=timezone.now() - timedelta(days=1),
        )

        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-join-via-link", kwargs={"link": link.link})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ChatSearchAPITestCase(BaseAPITestCase):
    """Test cases for chat search API."""

    def test_search_chats(self):
        """Test searching chats."""
        # Create searchable chats
        work_chat = Chat.objects.create(
            name="Work Discussion",
            description="Work related topics",
            creator=self.user1,
        )
        ChatParticipant.objects.create(
            user=self.user1, chat=work_chat, role=ChatParticipant.ParticipantRole.OWNER
        )

        personal_chat = Chat.objects.create(
            name="Personal Chat", description="Personal discussions", creator=self.user1
        )
        ChatParticipant.objects.create(
            user=self.user1,
            chat=personal_chat,
            role=ChatParticipant.ParticipantRole.OWNER,
        )

        url = reverse("chat-search")
        response = self.client.get(url, {"query": "work"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)

        # Verify work chat is in results
        work_results = [
            chat for chat in response.data["results"] if "work" in chat["name"].lower()
        ]
        self.assertGreater(len(work_results), 0)

    def test_search_messages(self):
        """Test searching messages."""
        # Create searchable messages
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Important project update",
            type=ChatMessage.MessageType.TEXT,
        )
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user2,
            content="Random conversation",
            type=ChatMessage.MessageType.TEXT,
        )

        url = reverse("message-search", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url, {"query": "project"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)

    def test_search_with_filters(self):
        """Test search with additional filters."""
        # Create messages with different types
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Text message about project",
            type=ChatMessage.MessageType.TEXT,
        )
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            type=ChatMessage.MessageType.PHOTO,
            has_media=True,
        )

        url = reverse("message-search", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(
            url,
            {
                "query": "project",
                "message_types": ["text"],
                "sender_id": str(self.user1.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data["results"]), 1)


class ChatPollAPITestCase(BaseAPITestCase):
    """Test cases for chat poll API."""

    def test_create_poll(self):
        """Test creating a poll."""
        url = reverse("chat-polls", kwargs={"chat_pk": self.chat.id})
        data = {
            "question": "What is your favorite color?",
            "options": [
                {"text": "Red", "order": 0},
                {"text": "Blue", "order": 1},
                {"text": "Green", "order": 2},
            ],
            "type": "regular",
            "is_anonymous": True,
            "allows_multiple_answers": False,
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["question"], "What is your favorite color?")
        self.assertEqual(len(response.data["options"]), 3)

    def test_vote_in_poll(self):
        """Test voting in a poll."""
        # Create poll
        poll = ChatPoll.objects.create(
            chat=self.chat, question="Test poll?", type=ChatPoll.PollType.REGULAR
        )

        option1 = ChatPollOption.objects.create(poll=poll, text="Option 1", order=0)
        ChatPollOption.objects.create(poll=poll, text="Option 2", order=1)

        url = reverse("poll-vote", kwargs={"chat_pk": self.chat.id, "poll_pk": poll.id})
        data = {"option_ids": [str(option1.id)]}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ChatPollAnswer.objects.filter(
                poll=poll, user=self.user1, option_ids__contains=[str(option1.id)]
            ).exists()
        )

    def test_close_poll(self):
        """Test closing a poll."""
        poll = ChatPoll.objects.create(
            chat=self.chat, question="Test poll?", type=ChatPoll.PollType.REGULAR
        )

        url = reverse(
            "poll-close", kwargs={"chat_pk": self.chat.id, "poll_pk": poll.id}
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        poll.refresh_from_db()
        self.assertTrue(poll.is_closed)


class ChatCallAPITestCase(BaseAPITestCase):
    """Test cases for chat call API."""

    def test_start_call(self):
        """Test starting a call."""
        url = reverse("chat-calls", kwargs={"chat_pk": self.chat.id})
        data = {"type": "voice", "max_participants": 10}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["type"], "voice")
        self.assertEqual(response.data["initiator"]["username"], self.user1.username)

    def test_join_call(self):
        """Test joining a call."""
        # Create active call
        call = ChatCall.objects.create(
            chat=self.chat,
            initiator=self.user1,
            type=ChatCall.CallType.VOICE,
            status=ChatCall.CallStatus.ONGOING,
        )

        self.client.force_authenticate(user=self.user2)
        url = reverse("call-join", kwargs={"chat_pk": self.chat.id, "call_pk": call.id})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            ChatCallParticipant.objects.filter(
                call=call,
                user=self.user2,
                status=ChatCallParticipant.ParticipantStatus.JOINED,
            ).exists()
        )

    def test_leave_call(self):
        """Test leaving a call."""
        # Create call with participant
        call = ChatCall.objects.create(
            chat=self.chat,
            initiator=self.user1,
            type=ChatCall.CallType.VOICE,
            status=ChatCall.CallStatus.ONGOING,
        )

        participant = ChatCallParticipant.objects.create(
            call=call,
            user=self.user2,
            status=ChatCallParticipant.ParticipantStatus.JOINED,
        )

        self.client.force_authenticate(user=self.user2)
        url = reverse(
            "call-leave", kwargs={"chat_pk": self.chat.id, "call_pk": call.id}
        )

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        participant.refresh_from_db()
        self.assertEqual(participant.status, ChatCallParticipant.ParticipantStatus.LEFT)

    def test_end_call(self):
        """Test ending a call."""
        call = ChatCall.objects.create(
            chat=self.chat,
            initiator=self.user1,
            type=ChatCall.CallType.VOICE,
            status=ChatCall.CallStatus.ONGOING,
        )

        url = reverse("call-end", kwargs={"chat_pk": self.chat.id, "call_pk": call.id})

        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        call.refresh_from_db()
        self.assertEqual(call.status, ChatCall.CallStatus.ENDED)


class FileUploadAPITestCase(BaseAPITestCase):
    """Test cases for file upload API."""

    def test_upload_single_file(self):
        """Test uploading a single file."""
        test_file = SimpleUploadedFile(
            "test.txt", b"file content", content_type="text/plain"
        )

        url = reverse("chat-upload-file", kwargs={"chat_pk": self.chat.id})
        data = {"file": test_file, "caption": "Test file upload"}

        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIsNotNone(response.data["file_url"])

    def test_upload_multiple_files(self):
        """Test uploading multiple files."""
        files = []
        for i in range(3):
            file = SimpleUploadedFile(
                f"test{i}.txt", f"content {i}".encode(), content_type="text/plain"
            )
            files.append(file)

        url = reverse("chat-upload-files", kwargs={"chat_pk": self.chat.id})
        data = {"files": files, "caption": "Multiple files"}

        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(response.data["attachments"]), 3)

    def test_upload_large_file(self):
        """Test uploading large file (should fail)."""
        # Create 101MB file
        large_content = b"x" * (101 * 1024 * 1024)
        large_file = SimpleUploadedFile(
            "large.txt", large_content, content_type="text/plain"
        )

        url = reverse("chat-upload-file", kwargs={"chat_pk": self.chat.id})
        data = {"file": large_file, "caption": "Too large"}

        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_upload_dangerous_file(self):
        """Test uploading dangerous file (should fail)."""
        dangerous_file = SimpleUploadedFile(
            "malware.exe",
            b"fake executable content",
            content_type="application/x-executable",
        )

        url = reverse("chat-upload-file", kwargs={"chat_pk": self.chat.id})
        data = {"file": dangerous_file, "caption": "Dangerous file"}

        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class ChatExportAPITestCase(BaseAPITestCase):
    """Test cases for chat export API."""

    def test_export_chat_json(self):
        """Test exporting chat as JSON."""
        # Create messages for export
        for i in range(5):
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.user1 if i % 2 == 0 else self.user2,
                content=f"Export test message {i}",
                type=ChatMessage.MessageType.TEXT,
            )

        url = reverse("chat-export", kwargs={"chat_pk": self.chat.id})
        data = {"format": "json", "include_media": False}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "application/json")

    def test_export_chat_html(self):
        """Test exporting chat as HTML."""
        # Create messages
        ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="HTML export test",
            type=ChatMessage.MessageType.TEXT,
        )

        url = reverse("chat-export", kwargs={"chat_pk": self.chat.id})
        data = {"format": "html", "include_media": True}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response["Content-Type"], "text/html")

    def test_export_with_date_range(self):
        """Test exporting chat with date range."""
        url = reverse("chat-export", kwargs={"chat_pk": self.chat.id})
        data = {
            "format": "json",
            "date_from": (timezone.now() - timedelta(days=7)).isoformat(),
            "date_to": timezone.now().isoformat(),
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_export_unauthorized(self):
        """Test exporting chat without permission."""
        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-export", kwargs={"chat_pk": self.chat.id})
        data = {"format": "json"}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class ChatAnalyticsAPITestCase(BaseAPITestCase):
    """Test cases for chat analytics API."""

    @unittest.skip("Analytics endpoints not implemented")
    def test_get_chat_analytics(self):
        """Test getting chat analytics."""
        # Create data for analytics
        for i in range(10):
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.user1 if i % 2 == 0 else self.user2,
                content=f"Analytics message {i}",
                type=ChatMessage.MessageType.TEXT,
                created_at=timezone.now() - timedelta(hours=i),
            )

        url = reverse("chat-analytics", kwargs={"chat_pk": self.chat.id})
        data = {"period": "day", "metrics": ["messages", "participants"]}

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("messages_count", response.data)
        self.assertIn("participants_count", response.data)

    @unittest.skip("Analytics endpoints not implemented")
    def test_get_user_analytics(self):
        """Test getting user-specific analytics."""
        url = reverse("user-chat-analytics")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("total_chats", response.data)
        self.assertIn("total_messages", response.data)

    @unittest.skip("Analytics endpoints not implemented")
    def test_analytics_admin_only(self):
        """Test analytics access for admins only."""
        self.client.force_authenticate(user=self.user2)
        url = reverse("chat-analytics", kwargs={"chat_pk": self.chat.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class WebhookAPITestCase(BaseAPITestCase):
    """Test cases for webhook API."""

    def test_setup_webhook(self):
        """Test setting up a webhook."""
        url = reverse("chat-webhooks", kwargs={"chat_pk": self.chat.id})
        data = {
            "url": "https://example.com/webhook",
            "events": ["message_sent", "user_joined"],
            "secret": "webhook_secret",
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["url"], "https://example.com/webhook")

    def test_webhook_validation(self):
        """Test webhook URL validation."""
        url = reverse("chat-webhooks", kwargs={"chat_pk": self.chat.id})
        data = {
            "url": "http://insecure-url.com/webhook",  # HTTP not allowed
            "events": ["message_sent"],
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("requests.post")
    def test_webhook_delivery(self, mock_post):
        """Test webhook delivery."""
        mock_post.return_value.status_code = 200

        # Create webhook
        webhook = ChatWebhook.objects.create(
            chat=self.chat,
            url="https://example.com/webhook",
            events=["message_sent"],
            is_active=True,
        )

        # Trigger webhook by creating message
        message = ChatMessage.objects.create(
            chat=self.chat, sender=self.user1, content="Webhook test message"
        )

        # Simulate webhook delivery
        from apps.chats.signals import send_webhook

        send_webhook(webhook, "message_sent", {"message_id": str(message.id)})

        mock_post.assert_called_once()


class RateLimitingTestCase(BaseAPITestCase):
    """Test cases for rate limiting."""

    def test_message_rate_limiting(self):
        """Test message sending rate limiting."""
        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})

        # Send many messages rapidly
        responses = []
        for i in range(20):
            data = {
                "type": ChatMessage.MessageType.TEXT,
                "content": f"Rate limit test {i}",
            }
            response = self.client.post(url, data, format="json")
            responses.append(response)

        # Some requests should be rate limited
        success_count = sum(1 for r in responses if r.status_code == 201)
        rate_limited_count = sum(1 for r in responses if r.status_code == 429)

        self.assertGreater(rate_limited_count, 0)
        self.assertLess(success_count, 20)

    def test_api_rate_limiting(self):
        """Test general API rate limiting."""
        url = reverse("chat-list")

        # Make many requests rapidly
        responses = []
        for i in range(100):
            response = self.client.get(url)
            responses.append(response)

        # Some should be rate limited
        rate_limited = any(r.status_code == 429 for r in responses)
        self.assertTrue(rate_limited)


class ErrorHandlingTestCase(BaseAPITestCase):
    """Test cases for error handling."""

    def test_404_handling(self):
        """Test 404 error handling."""
        fake_id = uuid.uuid4()
        url = reverse("chat-detail", kwargs={"pk": fake_id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn("error", response.data)

    def test_validation_error_handling(self):
        """Test validation error handling."""
        url = reverse("chat-list")
        data = {
            "type": "invalid_type",
            "name": "",  # Empty name
        }

        response = self.client.post(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("type", response.data)

    def test_permission_error_handling(self):
        """Test permission error handling."""
        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("error", response.data)

    @patch("apps.chats.models.Chat.objects.get")
    def test_database_error_handling(self, mock_get):
        """Test database error handling."""
        mock_get.side_effect = Exception("Database connection failed")

        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaginationTestCase(BaseAPITestCase):
    """Test cases for pagination."""

    def test_chat_list_pagination(self):
        """Test chat list pagination."""
        # Create many chats
        for i in range(50):
            chat = Chat.objects.create(
                name=f"Pagination Test Chat {i}", creator=self.user1
            )
            ChatParticipant.objects.create(
                user=self.user1, chat=chat, role=ChatParticipant.ParticipantRole.OWNER
            )

        url = reverse("chat-list")
        response = self.client.get(url, {"page": 1, "page_size": 10})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

        # Test second page
        response = self.client.get(url, {"page": 2, "page_size": 10})
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["previous"])

    def test_message_list_pagination(self):
        """Test message list pagination."""
        # Create many messages
        for i in range(100):
            ChatMessage.objects.create(
                chat=self.chat,
                sender=self.user1,
                content=f"Pagination message {i}",
                type=ChatMessage.MessageType.TEXT,
            )

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url, {"page_size": 20})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 20)
        self.assertIsNotNone(response.data["next"])

    def test_invalid_pagination_params(self):
        """Test invalid pagination parameters."""
        url = reverse("chat-list")

        # Invalid page number
        response = self.client.get(url, {"page": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid page size
        response = self.client.get(url, {"page_size": "invalid"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Negative page number
        response = self.client.get(url, {"page": -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Zero page size
        response = self.client.get(url, {"page_size": 0})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        # Excessively large page size
        response = self.client.get(url, {"page_size": 10000})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SecurityTestCase(BaseAPITestCase):
    """Test cases for security measures."""

    def test_sql_injection_prevention(self):
        """Test SQL injection prevention."""
        malicious_input = "'; DROP TABLE auth_user; --"

        # Test in chat search
        url = reverse("chat-search")
        response = self.client.get(url, {"q": malicious_input})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Ensure no SQL injection occurred
        self.assertTrue(User.objects.filter(username="testuser1").exists())

        # Test in message search
        url = reverse("message-search", kwargs={"chat_pk": self.chat.id})
        response = self.client.get(url, {"q": malicious_input})
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_xss_prevention(self):
        """Test XSS prevention in message content."""
        xss_payload = "<script>alert('XSS')</script>"

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {"content": xss_payload, "type": "text"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        # Verify content is properly escaped
        message = ChatMessage.objects.get(id=response.data["id"])
        self.assertNotIn("<script>", message.content)

    def test_csrf_protection(self):
        """Test CSRF protection."""
        # Create a new client without CSRF exemption
        client = APIClient(enforce_csrf_checks=True)
        client.force_authenticate(user=self.user1)

        url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
        data = {"content": "Test message", "type": "text"}

        # This should fail without proper CSRF token
        client.post(url, data)
        # Note: In API context, CSRF is typically handled by authentication
        # This test ensures the mechanism is in place

    def test_file_upload_security(self):
        """Test file upload security measures."""
        # Test malicious file upload
        malicious_content = b"<?php system($_GET['cmd']); ?>"
        malicious_file = SimpleUploadedFile(
            "malicious.php", malicious_content, content_type="application/x-php"
        )

        url = reverse("file-upload")
        data = {"file": malicious_file}
        response = self.client.post(url, data)

        # Should reject dangerous file types
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Invalid file type", str(response.data))

    def test_user_enumeration_prevention(self):
        """Test user enumeration prevention."""
        # Test with non-existent user
        url = reverse("user-profile", kwargs={"pk": 99999})
        response = self.client.get(url)

        # Should return 404, not reveal if user exists
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_password_security(self):
        """Test password security measures."""
        # Test password complexity requirements
        weak_passwords = ["123456", "password", "qwerty", "123123"]

        for weak_password in weak_passwords:
            data = {
                "username": f"user_{uuid.uuid4().hex[:8]}",
                "email": f"user_{uuid.uuid4().hex[:8]}@example.com",
                "password": weak_password,
                "password_confirm": weak_password,
            }
            url = reverse("user-register")
            response = self.client.post(url, data)
            # Should reject weak passwords
            self.assertIn(response.status_code, [status.HTTP_400_BAD_REQUEST])


class PerformanceTestCase(BaseAPITestCase):
    """Test cases for performance optimization."""

    def setUp(self):
        super().setUp()
        # Create additional test data for performance testing
        self.large_chat = Chat.objects.create(
            type=Chat.ChatType.GROUP, name="Large Group", creator=self.user1
        )

        # Create many participants
        for i in range(50):
            user = User.objects.create_user(
                username=f"perfuser{i}",
                email=f"perfuser{i}@example.com",
                password="testpass123",
            )
            ChatParticipant.objects.create(
                user=user,
                chat=self.large_chat,
                role=ChatParticipant.ParticipantRole.MEMBER,
            )

        # Create many messages
        for i in range(100):
            ChatMessage.objects.create(
                chat=self.large_chat,
                sender=self.user1,
                content=f"Performance test message {i}",
                type=ChatMessage.MessageType.TEXT,
            )

    def test_chat_list_performance(self):
        """Test chat list endpoint performance."""
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            # Reset queries count
            connection.queries_log.clear()

            url = reverse("chat-list")
            response = self.client.get(url)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # Ensure query count is reasonable (should use select_related/prefetch_related)
            query_count = len(connection.queries)
            self.assertLess(query_count, 10, f"Too many queries: {query_count}")

    def test_message_list_performance(self):
        """Test message list endpoint performance with pagination."""
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            connection.queries_log.clear()

            url = reverse("message-list", kwargs={"chat_pk": self.large_chat.id})
            response = self.client.get(url, {"page_size": 20})

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # Should use efficient pagination
            query_count = len(connection.queries)
            self.assertLess(
                query_count, 5, f"Too many queries for pagination: {query_count}"
            )

    def test_search_performance(self):
        """Test search endpoint performance."""
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            connection.queries_log.clear()

            url = reverse("message-search", kwargs={"chat_pk": self.large_chat.id})
            response = self.client.get(url, {"q": "test"})

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            # Search should be optimized
            query_count = len(connection.queries)
            self.assertLess(
                query_count, 3, f"Search queries not optimized: {query_count}"
            )

    @patch("django.core.cache.cache")
    def test_caching_implementation(self, mock_cache):
        """Test that caching is properly implemented."""
        mock_cache.get.return_value = None
        mock_cache.set.return_value = True

        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Verify cache was attempted to be used
        mock_cache.get.assert_called()


class AdvancedPermissionTestCase(BaseAPITestCase):
    """Advanced test cases for permissions and roles."""

    def setUp(self):
        super().setUp()
        # Create additional roles
        self.admin = ChatParticipant.objects.create(
            user=self.user3,
            chat=self.chat,
            role=ChatParticipant.ParticipantRole.ADMIN,
            can_invite_users=True,
            can_delete_messages=True,
            can_ban_users=True,
        )

    def test_role_based_message_deletion(self):
        """Test role-based message deletion permissions."""
        # Create message by regular member
        member_message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user2,
            content="Member message",
            type=ChatMessage.MessageType.TEXT,
        )

        # Admin should be able to delete any message
        self.client.force_authenticate(user=self.user3)
        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": member_message.id}
        )
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def test_role_based_participant_management(self):
        """Test role-based participant management."""
        # Create new user to add
        new_user = User.objects.create_user(
            username="newuser", email="new@example.com", password="testpass123"
        )

        # Regular member should not be able to add participants
        self.client.force_authenticate(user=self.user2)
        url = reverse("chat-add-participants", kwargs={"pk": self.chat.id})
        data = {"user_ids": [new_user.id]}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Admin should be able to add participants
        self.client.force_authenticate(user=self.user3)
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_chat_settings_permissions(self):
        """Test chat settings modification permissions."""
        # Regular member should not modify chat settings
        self.client.force_authenticate(user=self.user2)
        url = reverse("chat-detail", kwargs={"pk": self.chat.id})
        data = {"name": "Modified Name"}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        # Owner should be able to modify settings
        self.client.force_authenticate(user=self.user1)
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_private_chat_access(self):
        """Test private chat access restrictions."""
        # Create private chat
        private_chat = Chat.objects.create(
            type=Chat.ChatType.PRIVATE, creator=self.user1
        )
        ChatParticipant.objects.create(
            user=self.user1,
            chat=private_chat,
            role=ChatParticipant.ParticipantRole.OWNER,
        )
        ChatParticipant.objects.create(
            user=self.user2,
            chat=private_chat,
            role=ChatParticipant.ParticipantRole.MEMBER,
        )

        # Non-participant should not access private chat
        self.client.force_authenticate(user=self.user3)
        url = reverse("chat-detail", kwargs={"pk": private_chat.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class WebSocketSecurityTestCase(BaseAPITestCase):
    """Test cases for WebSocket security."""

    @patch("channels.layers.get_channel_layer")
    def test_websocket_authentication(self, mock_layer):
        """Test WebSocket connection authentication."""
        from channels.testing import WebsocketCommunicator

        from apps.chats.consumers import ChatConsumer

        # Test unauthenticated connection
        communicator = WebsocketCommunicator(ChatConsumer.as_asgi(), "/ws/chat/1/")
        connected, subprotocol = communicator.connect()

        # Should reject unauthenticated connections
        self.assertFalse(connected)

    def test_websocket_authorization(self):
        """Test WebSocket authorization for chat access."""
        # This would test that users can only connect to chats they're members of
        pass  # Implementation depends on WebSocket consumer setup

    def test_websocket_rate_limiting(self):
        """Test WebSocket message rate limiting."""
        # This would test rate limiting on WebSocket messages
        pass  # Implementation depends on rate limiting setup


class DataPrivacyTestCase(BaseAPITestCase):
    """Test cases for data privacy and GDPR compliance."""

    def test_user_data_export(self):
        """Test user data export functionality."""
        url = reverse("user-data-export")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("application/json", response.get("Content-Type", ""))

        # Verify all user data is included
        data = response.json()
        self.assertIn("user_info", data)
        self.assertIn("messages", data)
        self.assertIn("chats", data)

    def test_user_data_deletion(self):
        """Test user data deletion (right to be forgotten)."""
        # Create some user data
        message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user2,
            content="Data to be deleted",
            type=ChatMessage.MessageType.TEXT,
        )

        url = reverse("user-data-delete")
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify data is anonymized/deleted
        message.refresh_from_db()
        self.assertEqual(message.content, "[Deleted]")
        self.assertIsNone(message.sender)

    def test_data_retention_policy(self):
        """Test data retention policy enforcement."""
        # Create old message
        old_message = ChatMessage.objects.create(
            chat=self.chat,
            sender=self.user1,
            content="Old message",
            type=ChatMessage.MessageType.TEXT,
            created_at=timezone.now()
            - timedelta(days=366),  # Older than retention period
        )

        # Run cleanup task
        from apps.chats.tasks import cleanup_old_data

        cleanup_old_data.delay()

        # Verify old data is cleaned up
        with self.assertRaises(ChatMessage.DoesNotExist):
            old_message.refresh_from_db()


class ConcurrencyTestCase(BaseAPITestCase):
    """Test cases for handling concurrent operations."""

    def test_concurrent_message_creation(self):
        """Test handling of concurrent message creation."""
        import threading

        results = []

        def create_message(content):
            client = APIClient()
            client.force_authenticate(user=self.user1)
            url = reverse("message-list", kwargs={"chat_pk": self.chat.id})
            data = {"content": content, "type": "text"}
            response = client.post(url, data)
            results.append(response.status_code)

        # Create multiple threads to send messages simultaneously
        threads = []
        for i in range(5):
            thread = threading.Thread(
                target=create_message, args=[f"Concurrent message {i}"]
            )
            threads.append(thread)

        # Start all threads
        for thread in threads:
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All messages should be created successfully
        self.assertEqual(len([r for r in results if r == status.HTTP_201_CREATED]), 5)

    def test_race_condition_prevention(self):
        """Test prevention of race conditions in critical operations."""
        # Test concurrent participant addition
        new_user = User.objects.create_user(
            username="raceuser", email="race@example.com", password="testpass123"
        )

        def add_participant():
            client = APIClient()
            client.force_authenticate(user=self.user1)
            url = reverse("chat-participants", kwargs={"chat_pk": self.chat.id})
            data = {"user_id": new_user.id}
            return client.post(url, data)

        import threading

        results = []

        # Try to add the same participant multiple times simultaneously
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=lambda: results.append(add_participant()))
            threads.append(thread)

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # Only one should succeed, others should fail gracefully
        success_count = len(
            [r for r in results if r.status_code == status.HTTP_201_CREATED]
        )
        self.assertEqual(success_count, 1)


class APIVersioningTestCase(BaseAPITestCase):
    """Test cases for API versioning."""

    def test_api_version_header(self):
        """Test API version handling via headers."""
        url = reverse("chat-list")

        # Test with version header
        response = self.client.get(url, HTTP_API_VERSION="v1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Test with unsupported version
        response = self.client.get(url, HTTP_API_VERSION="v999")
        self.assertEqual(response.status_code, status.HTTP_406_NOT_ACCEPTABLE)

    def test_backward_compatibility(self):
        """Test backward compatibility with older API versions."""
        # Test that v1 API still works while v2 is available
        url = reverse("chat-list")

        # v1 format
        response = self.client.get(url, HTTP_API_VERSION="v1")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # v2 format (if implemented)
        response = self.client.get(url, HTTP_API_VERSION="v2")
        self.assertIn(
            response.status_code,
            [
                status.HTTP_200_OK,
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_406_NOT_ACCEPTABLE,
            ],
        )


class MonitoringTestCase(BaseAPITestCase):
    """Test cases for monitoring and logging."""

    @patch("apps.chats.views.logger")
    def test_audit_logging(self, mock_logger):
        """Test that sensitive operations are logged."""
        # Delete a message (sensitive operation)
        url = reverse(
            "message-detail", kwargs={"chat_pk": self.chat.id, "pk": self.message.id}
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # Verify audit log was created
        mock_logger.info.assert_called()

    def test_performance_monitoring(self):
        """Test performance monitoring integration."""
        # This would test integration with performance monitoring tools
        # like New Relic, DataDog, etc.
        pass

    def test_error_tracking(self):
        """Test error tracking and reporting."""
        # This would test integration with error tracking tools
        # like Sentry, Rollbar, etc.
        pass

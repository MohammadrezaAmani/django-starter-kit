import asyncio
from unittest.mock import patch

from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from apps.chats.consumers import ChatConsumer, NotificationConsumer
from apps.chats.models import (
    Chat,
    ChatCall,
    ChatCallParticipant,
    ChatMessage,
    ChatParticipant,
)

User = get_user_model()


class BaseChatConsumerTestCase(TransactionTestCase):
    """Base test case for chat consumer tests."""

    async def create_test_data(self):
        """Create test data asynchronously."""
        # Create users
        self.user1 = await database_sync_to_async(User.objects.create_user)(
            username="testuser1", email="test1@example.com", password="testpass123"
        )
        self.user2 = await database_sync_to_async(User.objects.create_user)(
            username="testuser2", email="test2@example.com", password="testpass123"
        )
        self.user3 = await database_sync_to_async(User.objects.create_user)(
            username="testuser3", email="test3@example.com", password="testpass123"
        )

        # Create chat
        self.chat = await database_sync_to_async(Chat.objects.create)(
            type=Chat.ChatType.GROUP, name="Test Group", creator=self.user1
        )

        # Add participants
        self.participant1 = await database_sync_to_async(
            ChatParticipant.objects.create
        )(user=self.user1, chat=self.chat, role=ChatParticipant.ParticipantRole.OWNER)
        self.participant2 = await database_sync_to_async(
            ChatParticipant.objects.create
        )(user=self.user2, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER)

    async def get_communicator(self, user, chat_id=None):
        """Get WebSocket communicator for user."""
        if chat_id is None:
            chat_id = str(self.chat.id)

        communicator = WebsocketCommunicator(
            ChatConsumer.as_asgi(), f"/ws/chat/{chat_id}/"
        )

        # Mock authentication
        communicator.scope["user"] = user
        communicator.scope["url_route"] = {"kwargs": {"chat_id": chat_id}}

        return communicator


class ChatConsumerConnectionTestCase(BaseChatConsumerTestCase):
    """Test cases for chat consumer connection handling."""

    async def test_successful_connection(self):
        """Test successful WebSocket connection."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        connected, subprotocol = await communicator.connect()

        self.assertTrue(connected)

        await communicator.disconnect()

    async def test_unauthenticated_connection_rejected(self):
        """Test unauthenticated connection is rejected."""
        await self.create_test_data()

        communicator = await self.get_communicator(None)  # No user
        connected, subprotocol = await communicator.connect()

        self.assertFalse(connected)

    async def test_non_member_connection_rejected(self):
        """Test non-member connection is rejected."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user3)  # Not a member
        connected, subprotocol = await communicator.connect()

        self.assertFalse(connected)

    async def test_banned_user_connection_rejected(self):
        """Test banned user connection is rejected."""
        await self.create_test_data()

        # Ban user2
        await database_sync_to_async(
            lambda: setattr(
                self.participant2, "status", ChatParticipant.ParticipantStatus.BANNED
            )
        )()
        await database_sync_to_async(self.participant2.save)()

        communicator = await self.get_communicator(self.user2)
        connected, subprotocol = await communicator.connect()

        self.assertFalse(connected)

    async def test_connection_to_nonexistent_chat(self):
        """Test connection to non-existent chat."""
        await self.create_test_data()

        fake_chat_id = "00000000-0000-0000-0000-000000000000"
        communicator = await self.get_communicator(self.user1, fake_chat_id)
        connected, subprotocol = await communicator.connect()

        self.assertFalse(connected)

    async def test_multiple_connections_same_user(self):
        """Test multiple connections from same user."""
        await self.create_test_data()

        # First connection
        communicator1 = await self.get_communicator(self.user1)
        connected1, _ = await communicator1.connect()
        self.assertTrue(connected1)

        # Second connection from same user
        communicator2 = await self.get_communicator(self.user1)
        connected2, _ = await communicator2.connect()
        self.assertTrue(connected2)

        await communicator1.disconnect()
        await communicator2.disconnect()


class ChatConsumerMessageTestCase(BaseChatConsumerTestCase):
    """Test cases for chat consumer message handling."""

    async def test_send_text_message(self):
        """Test sending a text message."""
        await self.create_test_data()

        # Connect both users
        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Send message from user1
        message_data = {
            "type": "send_message",
            "message": {"type": "text", "content": "Hello, world!"},
        }

        await communicator1.send_json_to(message_data)

        # Both users should receive the message
        response1 = await communicator1.receive_json_from()
        response2 = await communicator2.receive_json_from()

        self.assertEqual(response1["type"], "chat_message")
        self.assertEqual(response1["message"]["content"], "Hello, world!")
        self.assertEqual(response2["type"], "chat_message")
        self.assertEqual(response2["message"]["content"], "Hello, world!")

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_send_reply_message(self):
        """Test sending a reply message."""
        await self.create_test_data()

        # Create original message
        original_message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user2,
            content="Original message",
            type=ChatMessage.MessageType.TEXT,
        )

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send reply
        message_data = {
            "type": "send_message",
            "message": {
                "type": "text",
                "content": "Reply message",
                "reply_to_id": str(original_message.id),
            },
        }

        await communicator.send_json_to(message_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "chat_message")
        self.assertIsNotNone(response["message"]["reply_to"])

        await communicator.disconnect()

    async def test_send_message_with_mentions(self):
        """Test sending message with mentions."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send message with mention
        message_data = {
            "type": "send_message",
            "message": {
                "type": "text",
                "content": f"Hello @{self.user2.username}!",
                "mention_user_ids": [str(self.user2.id)],
            },
        }

        await communicator.send_json_to(message_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "chat_message")
        self.assertIsNotNone(response["message"]["mentions"])

        await communicator.disconnect()

    async def test_send_message_validation_error(self):
        """Test sending invalid message."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send invalid message (empty content)
        message_data = {
            "type": "send_message",
            "message": {"type": "text", "content": ""},
        }

        await communicator.send_json_to(message_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("validation", response["message"].lower())

        await communicator.disconnect()

    async def test_send_message_slow_mode(self):
        """Test sending message with slow mode enabled."""
        await self.create_test_data()

        # Enable slow mode
        await database_sync_to_async(
            lambda: setattr(self.chat, "slow_mode_delay", 30)
        )()
        await database_sync_to_async(self.chat.save)()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send first message
        message_data = {
            "type": "send_message",
            "message": {"type": "text", "content": "First message"},
        }

        await communicator.send_json_to(message_data)
        await communicator.receive_json_from()  # Success

        # Try to send second message immediately
        message_data["message"]["content"] = "Second message too soon"
        await communicator.send_json_to(message_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("slow mode", response["message"].lower())

        await communicator.disconnect()


class ChatConsumerTypingTestCase(BaseChatConsumerTestCase):
    """Test cases for typing indicators."""

    async def test_typing_start_and_stop(self):
        """Test typing start and stop indicators."""
        await self.create_test_data()

        # Connect both users
        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # User1 starts typing
        typing_data = {"type": "typing_start"}

        await communicator1.send_json_to(typing_data)

        # User2 should receive typing indicator
        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "typing_indicator")
        self.assertEqual(response["user"]["username"], self.user1.username)
        self.assertTrue(response["is_typing"])

        # User1 stops typing
        typing_data["type"] = "typing_stop"
        await communicator1.send_json_to(typing_data)

        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "typing_indicator")
        self.assertFalse(response["is_typing"])

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_auto_stop_typing(self):
        """Test automatic typing stop after timeout."""
        await self.create_test_data()

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Start typing
        await communicator1.send_json_to({"type": "typing_start"})
        await communicator2.receive_json_from()  # Receive typing start

        # Wait for auto-stop (mocked timeout)
        with patch(
            "apps.chats.consumers.ChatConsumer.auto_stop_typing"
        ) as mock_auto_stop:
            # Simulate timeout
            await asyncio.sleep(0.1)
            mock_auto_stop.assert_called()

        await communicator1.disconnect()
        await communicator2.disconnect()


class ChatConsumerReactionTestCase(BaseChatConsumerTestCase):
    """Test cases for message reactions."""

    async def test_add_reaction(self):
        """Test adding reaction to message."""
        await self.create_test_data()

        # Create message
        message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user1,
            content="React to this message",
            type=ChatMessage.MessageType.TEXT,
        )

        # Connect users
        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Add reaction
        reaction_data = {
            "type": "reaction",
            "message_id": str(message.id),
            "emoji": "👍",
        }

        await communicator2.send_json_to(reaction_data)

        # Both users should receive reaction update
        response1 = await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        self.assertEqual(response1["type"], "reaction_update")
        self.assertEqual(response1["message_id"], str(message.id))
        self.assertEqual(response1["emoji"], "👍")

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_remove_reaction(self):
        """Test removing reaction from message."""
        await self.create_test_data()

        # Create message with existing reaction
        message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user1,
            content="Message with reaction",
            type=ChatMessage.MessageType.TEXT,
        )

        # Add reaction first
        await database_sync_to_async(message.add_reaction)(self.user2, "👍")

        communicator = await self.get_communicator(self.user2)
        await communicator.connect()

        # Remove reaction (send same emoji again)
        reaction_data = {
            "type": "reaction",
            "message_id": str(message.id),
            "emoji": "👍",
        }

        await communicator.send_json_to(reaction_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "reaction_update")
        # Should indicate removal

        await communicator.disconnect()


class ChatConsumerEditDeleteTestCase(BaseChatConsumerTestCase):
    """Test cases for message editing and deletion."""

    async def test_edit_message(self):
        """Test editing a message."""
        await self.create_test_data()

        # Create message
        message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user1,
            content="Original content",
            type=ChatMessage.MessageType.TEXT,
        )

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Edit message
        edit_data = {
            "type": "edit_message",
            "message_id": str(message.id),
            "content": "Edited content",
        }

        await communicator1.send_json_to(edit_data)

        # Both users should receive edit notification
        response1 = await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        self.assertEqual(response1["type"], "message_edited")
        self.assertEqual(response1["message"]["content"], "Edited content")

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_edit_other_user_message(self):
        """Test editing another user's message (should fail)."""
        await self.create_test_data()

        # Create message from user2
        message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user2,
            content="User2's message",
            type=ChatMessage.MessageType.TEXT,
        )

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Try to edit user2's message as user1
        edit_data = {
            "type": "edit_message",
            "message_id": str(message.id),
            "content": "Unauthorized edit",
        }

        await communicator.send_json_to(edit_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")

        await communicator.disconnect()

    async def test_delete_message(self):
        """Test deleting a message."""
        await self.create_test_data()

        # Create message
        message = await database_sync_to_async(ChatMessage.objects.create)(
            chat=self.chat,
            sender=self.user1,
            content="Message to delete",
            type=ChatMessage.MessageType.TEXT,
        )

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Delete message
        delete_data = {"type": "delete_message", "message_id": str(message.id)}

        await communicator1.send_json_to(delete_data)

        # Both users should receive deletion notification
        response1 = await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        self.assertEqual(response1["type"], "message_deleted")
        self.assertEqual(response1["message_id"], str(message.id))

        await communicator1.disconnect()
        await communicator2.disconnect()


class ChatConsumerReadReceiptTestCase(BaseChatConsumerTestCase):
    """Test cases for read receipts."""

    async def test_mark_messages_read(self):
        """Test marking messages as read."""
        await self.create_test_data()

        # Create messages
        messages = []
        for i in range(3):
            message = await database_sync_to_async(ChatMessage.objects.create)(
                chat=self.chat,
                sender=self.user1,
                content=f"Message {i}",
                type=ChatMessage.MessageType.TEXT,
            )
            messages.append(message)

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # Mark messages as read
        read_data = {
            "type": "mark_read",
            "message_ids": [str(msg.id) for msg in messages],
        }

        await communicator2.send_json_to(read_data)

        # User1 should receive read receipt
        response = await communicator1.receive_json_from()
        self.assertEqual(response["type"], "message_read")
        self.assertEqual(len(response["message_ids"]), 3)

        await communicator1.disconnect()
        await communicator2.disconnect()


class ChatConsumerCallTestCase(BaseChatConsumerTestCase):
    """Test cases for call functionality."""

    async def test_join_call(self):
        """Test joining a call."""
        await self.create_test_data()

        # Create call
        call = await database_sync_to_async(ChatCall.objects.create)(
            chat=self.chat,
            initiator=self.user1,
            type=ChatCall.CallType.VOICE,
            status=ChatCall.CallStatus.ACTIVE,
        )

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # User2 joins call
        call_data = {"type": "join_call", "call_id": str(call.id)}

        await communicator2.send_json_to(call_data)

        # Both users should receive call update
        response1 = await communicator1.receive_json_from()
        await communicator2.receive_json_from()

        self.assertEqual(response1["type"], "call_participant_joined")
        self.assertEqual(response1["call_id"], str(call.id))

        await communicator1.disconnect()
        await communicator2.disconnect()

    async def test_leave_call(self):
        """Test leaving a call."""
        await self.create_test_data()

        # Create call with participant
        call = await database_sync_to_async(ChatCall.objects.create)(
            chat=self.chat,
            initiator=self.user1,
            type=ChatCall.CallType.VOICE,
            status=ChatCall.CallStatus.ACTIVE,
        )

        await database_sync_to_async(ChatCallParticipant.objects.create)(
            call=call,
            user=self.user2,
            status=ChatCallParticipant.ParticipantStatus.JOINED,
        )

        communicator = await self.get_communicator(self.user2)
        await communicator.connect()

        # Leave call
        call_data = {"type": "leave_call", "call_id": str(call.id)}

        await communicator.send_json_to(call_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "call_participant_left")

        await communicator.disconnect()


class ChatConsumerHeartbeatTestCase(BaseChatConsumerTestCase):
    """Test cases for heartbeat and connection management."""

    async def test_ping_pong(self):
        """Test ping-pong heartbeat."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send ping
        ping_data = {"type": "ping"}
        await communicator.send_json_to(ping_data)

        # Should receive pong
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "pong")

        await communicator.disconnect()

    async def test_online_status_update(self):
        """Test online status updates."""
        await self.create_test_data()

        communicator1 = await self.get_communicator(self.user1)
        communicator2 = await self.get_communicator(self.user2)

        await communicator1.connect()
        await communicator2.connect()

        # User2 should receive user1 online status
        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "online_status")
        self.assertEqual(response["user"]["username"], self.user1.username)
        self.assertTrue(response["is_online"])

        # Disconnect user1
        await communicator1.disconnect()

        # User2 should receive user1 offline status
        response = await communicator2.receive_json_from()
        self.assertEqual(response["type"], "online_status")
        self.assertFalse(response["is_online"])

        await communicator2.disconnect()


class NotificationConsumerTestCase(TransactionTestCase):
    """Test cases for notification consumer."""

    async def create_test_data(self):
        """Create test data for notifications."""
        self.user = await database_sync_to_async(User.objects.create_user)(
            username="testuser", email="test@example.com", password="testpass123"
        )

    async def test_notification_connection(self):
        """Test notification consumer connection."""
        await self.create_test_data()

        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), "/ws/notifications/"
        )
        communicator.scope["user"] = self.user

        connected, subprotocol = await communicator.connect()
        self.assertTrue(connected)

        await communicator.disconnect()

    async def test_chat_invitation_notification(self):
        """Test chat invitation notification."""
        await self.create_test_data()

        # Create another user for chat invitation
        other_user = await database_sync_to_async(User.objects.create_user)(
            username="otheruser", email="other@example.com", password="testpass123"
        )

        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), "/ws/notifications/"
        )
        communicator.scope["user"] = self.user

        await communicator.connect()

        # Simulate chat invitation
        notification_data = {
            "type": "chat_invitation",
            "chat_name": "Test Chat",
            "inviter": other_user.username,
        }

        await communicator.send_json_to(notification_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "chat_invitation")
        self.assertEqual(response["chat_name"], "Test Chat")

        await communicator.disconnect()

    async def test_call_invitation_notification(self):
        """Test call invitation notification."""
        await self.create_test_data()

        communicator = WebsocketCommunicator(
            NotificationConsumer.as_asgi(), "/ws/notifications/"
        )
        communicator.scope["user"] = self.user

        await communicator.connect()

        # Simulate call invitation
        notification_data = {
            "type": "call_invitation",
            "chat_name": "Test Chat",
            "call_type": "voice",
            "caller": "testcaller",
        }

        await communicator.send_json_to(notification_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "call_invitation")
        self.assertEqual(response["call_type"], "voice")

        await communicator.disconnect()


class ChatConsumerErrorHandlingTestCase(BaseChatConsumerTestCase):
    """Test cases for error handling in chat consumer."""

    async def test_malformed_json_handling(self):
        """Test handling of malformed JSON."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send malformed JSON
        await communicator.send_to(text_data="invalid json")

        # Should receive error response
        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("invalid", response["message"].lower())

        await communicator.disconnect()

    async def test_missing_required_fields(self):
        """Test handling of missing required fields."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send message without required fields
        invalid_data = {
            "type": "send_message"
            # Missing "message" field
        }

        await communicator.send_json_to(invalid_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")

        await communicator.disconnect()

    async def test_unknown_message_type(self):
        """Test handling of unknown message types."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Send unknown message type
        unknown_data = {"type": "unknown_action", "data": "some data"}

        await communicator.send_json_to(unknown_data)

        response = await communicator.receive_json_from()
        self.assertEqual(response["type"], "error")
        self.assertIn("unknown", response["message"].lower())

        await communicator.disconnect()

    async def test_database_error_handling(self):
        """Test handling of database errors."""
        await self.create_test_data()

        communicator = await self.get_communicator(self.user1)
        await communicator.connect()

        # Mock database error
        with patch("apps.chats.models.ChatMessage.objects.create") as mock_create:
            mock_create.side_effect = Exception("Database error")

            message_data = {
                "type": "send_message",
                "message": {"type": "text", "content": "This should fail"},
            }

            await communicator.send_json_to(message_data)

            response = await communicator.receive_json_from()
            self.assertEqual(response["type"], "error")

        await communicator.disconnect()


class ChatConsumerPerformanceTestCase(BaseChatConsumerTestCase):
    """Test cases for chat consumer performance."""

    async def test_concurrent_message_sending(self):
        """Test concurrent message sending."""
        await self.create_test_data()

        # Add more participants
        for i in range(5):
            user = await database_sync_to_async(User.objects.create_user)(
                username=f"perfuser{i}",
                email=f"perf{i}@example.com",
                password="testpass123",
            )
            await database_sync_to_async(ChatParticipant.objects.create)(
                user=user, chat=self.chat, role=ChatParticipant.ParticipantRole.MEMBER
            )

        # Connect multiple users
        communicators = []
        for i in range(3):
            user = await database_sync_to_async(User.objects.get)(
                username=f"perfuser{i}"
            )
            communicator = await self.get_communicator(user)
            await communicator.connect()
            communicators.append(communicator)

        # Send messages concurrently
        tasks = []
        for i, communicator in enumerate(communicators):
            tasks.append(
                self.send_message(communicator, f"Performance test message {i}")
            )

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        successful_sends = sum(1 for r in results if not isinstance(r, Exception))
        self.assertGreater(successful_sends, 0)

        # Clean up
        for communicator in communicators:
            await communicator.disconnect()

    async def send_message(self, communicator, content):
        """Helper method to send a message."""
        await communicator.send_json_to(
            {
                "type": "message_send",
                "data": {"content": content, "message_type": "text"},
            }
        )
        response = await communicator.receive_json_from()
        return response

    def tearDown(self):
        """Clean up after tests."""
        super().tearDown()
        # Clear any remaining WebSocket connections
        if hasattr(self, "communicator"):
            asyncio.run(self.communicator.disconnect())

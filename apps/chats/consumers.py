import asyncio
import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from jwt import decode as jwt_decode
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import UntypedToken

from .models import Chat, ChatCache, ChatCall, ChatMessage, ChatParticipant

User = get_user_model()
logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for real-time chat functionality.
    Handles message sending, typing indicators, online status, and more.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.chat_id = None
        self.chat = None
        self.participant = None
        self.room_group_name = None
        self.user_group_name = None
        self.typing_task = None
        self.heartbeat_task = None

    async def connect(self):
        """Handle WebSocket connection."""
        print(self.scope)
        print("kir")
        try:
            # Extract chat ID from URL
            self.chat_id = self.scope["url_route"]["kwargs"]["chat_id"]

            # Authenticate user
            await self.authenticate_user()
            if not self.user:
                await self.close(code=4001)
                return

            # Verify chat access
            await self.verify_chat_access()
            if not self.chat or not self.participant:
                await self.close(code=4003)
                return

            # Set up group names
            self.room_group_name = f"chat_{self.chat_id}"
            self.user_group_name = f"user_{self.user.id}"

            # Join room groups
            await self.channel_layer.group_add(self.room_group_name, self.channel_name)
            await self.channel_layer.group_add(self.user_group_name, self.channel_name)

            # Accept connection
            await self.accept()

            # Update online status
            await self.update_online_status(True)

            # Start heartbeat
            self.heartbeat_task = asyncio.create_task(self.heartbeat_loop())

            # Send connection confirmation
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "connection_established",
                        "chat_id": str(self.chat_id),
                        "user_id": str(self.user.id),
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

            # Send recent messages if requested
            await self.send_recent_messages()

            logger.info(f"User {self.user.username} connected to chat {self.chat_id}")

        except Exception as e:
            logger.error(f"Error in connect: {e}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        try:
            if self.heartbeat_task:
                self.heartbeat_task.cancel()

            if self.typing_task:
                self.typing_task.cancel()

            # Update online status
            if self.user:
                await self.update_online_status(False)

            # Leave room groups
            if self.room_group_name:
                await self.channel_layer.group_discard(
                    self.room_group_name, self.channel_name
                )
            if self.user_group_name:
                await self.channel_layer.group_discard(
                    self.user_group_name, self.channel_name
                )

            logger.info(
                f"User {self.user.username if self.user else 'Unknown'} disconnected from chat {self.chat_id}"
            )

        except Exception as e:
            logger.error(f"Error in disconnect: {e}", exc_info=True)

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "send_message":
                await self.handle_send_message(data)
            elif message_type == "typing_start":
                await self.handle_typing_start(data)
            elif message_type == "typing_stop":
                await self.handle_typing_stop(data)
            elif message_type == "mark_read":
                await self.handle_mark_read(data)
            elif message_type == "join_call":
                await self.handle_join_call(data)
            elif message_type == "leave_call":
                await self.handle_leave_call(data)
            elif message_type == "reaction":
                await self.handle_reaction(data)
            elif message_type == "edit_message":
                await self.handle_edit_message(data)
            elif message_type == "delete_message":
                await self.handle_delete_message(data)
            elif message_type == "ping":
                await self.handle_ping(data)
            else:
                await self.send_error(
                    "unknown_message_type", f"Unknown message type: {message_type}"
                )

        except json.JSONDecodeError:
            await self.send_error("invalid_json", "Invalid JSON format")
        except Exception as e:
            logger.error(f"Error in receive: {e}", exc_info=True)
            await self.send_error("internal_error", "Internal server error")

    async def authenticate_user(self):
        """Authenticate user from query parameters or headers."""
        print(self.scope)
        try:
            # Try to get token from query parameters
            query_string = self.scope.get("query_string", b"").decode()
            token = None
            print(query_string)
            for param in query_string.split("&"):
                if param.startswith("token="):
                    token = param.split("=", 1)[1]
                    break

            if not token:
                # Try to get from headers
                headers = dict(self.scope["headers"])
                auth_header = headers.get(b"authorization", b"").decode()
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]

            if not token:
                logger.warning("No authentication token provided")
                return

            # Validate JWT token
            try:
                UntypedToken(token)
                decoded_data = jwt_decode(
                    token, settings.SECRET_KEY, algorithms=["HS256"]
                )
                user_id = decoded_data.get("user_id")
            except (InvalidToken, TokenError, Exception) as e:
                logger.warning(f"Invalid token: {e}")
                return

            # Get user
            self.user = await database_sync_to_async(User.objects.get)(id=user_id)

            if not self.user.is_active:
                logger.warning(f"Inactive user {user_id} attempted to connect")
                self.user = None
                return

            # Update last activity
            await database_sync_to_async(self.user.update_last_activity)()

        except User.DoesNotExist:
            logger.warning(f"User {user_id} not found")
        except Exception as e:
            logger.error(f"Authentication error: {e}", exc_info=True)

    async def verify_chat_access(self):
        """Verify user has access to the chat."""
        try:
            self.chat = await database_sync_to_async(Chat.objects.get)(id=self.chat_id)
            self.participant = await database_sync_to_async(
                ChatParticipant.objects.get
            )(
                user=self.user,
                chat=self.chat,
                status=ChatParticipant.ParticipantStatus.ACTIVE,
            )
        except (Chat.DoesNotExist, ChatParticipant.DoesNotExist):
            logger.warning(
                f"User {self.user.username} attempted to access unauthorized chat {self.chat_id}"
            )

    async def handle_send_message(self, data):
        """Handle sending a new message."""
        try:
            content = data.get("content", "").strip()
            message_type = data.get("message_type", "text")
            reply_to_id = data.get("reply_to")

            if not content and message_type == "text":
                await self.send_error(
                    "empty_message", "Message content cannot be empty"
                )
                return

            # Check if user can send messages
            if not await database_sync_to_async(
                lambda: self.participant.can_send_messages
            )():
                await self.send_error(
                    "permission_denied", "You don't have permission to send messages"
                )
                return

            # Check slow mode
            if await self.check_slow_mode():
                await self.send_error(
                    "slow_mode", "Please wait before sending another message"
                )
                return

            # Get reply_to message if specified
            reply_to = None
            if reply_to_id:
                try:
                    reply_to = await database_sync_to_async(ChatMessage.objects.get)(
                        id=reply_to_id, chat=self.chat
                    )
                except ChatMessage.DoesNotExist:
                    pass

            # Create message
            message = await database_sync_to_async(ChatMessage.objects.create)(
                chat=self.chat,
                sender=self.user,
                type=message_type,
                content=content,
                reply_to=reply_to,
                status=ChatMessage.MessageStatus.SENT,
            )

            # Send confirmation to sender
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "message_sent",
                        "message_id": str(message.id),
                        "timestamp": message.created_at.isoformat(),
                    }
                )
            )

            logger.info(f"Message sent by {self.user.username} in chat {self.chat_id}")

        except Exception as e:
            logger.error(f"Error sending message: {e}", exc_info=True)
            await self.send_error("send_failed", "Failed to send message")

    async def handle_typing_start(self, data):
        """Handle typing indicator start."""
        try:
            # Update participant typing status
            await database_sync_to_async(self.participant.set_typing)(5)  # 5 seconds

            # Cancel existing typing task
            if self.typing_task:
                self.typing_task.cancel()

            # Send typing indicator to other participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "is_typing": True,
                    "timestamp": timezone.now().isoformat(),
                    "exclude_sender": self.channel_name,
                },
            )

            # Schedule typing stop
            self.typing_task = asyncio.create_task(self.auto_stop_typing())

        except Exception as e:
            logger.error(f"Error handling typing start: {e}", exc_info=True)

    async def handle_typing_stop(self, data):
        """Handle typing indicator stop."""
        try:
            # Cancel typing task
            if self.typing_task:
                self.typing_task.cancel()

            # Update participant typing status
            await database_sync_to_async(
                lambda: setattr(self.participant, "typing_until", None)
            )()
            await database_sync_to_async(self.participant.save)(
                update_fields=["typing_until"]
            )

            # Send typing stop to other participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_indicator",
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "is_typing": False,
                    "timestamp": timezone.now().isoformat(),
                    "exclude_sender": self.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"Error handling typing stop: {e}", exc_info=True)

    async def handle_mark_read(self, data):
        """Handle marking messages as read."""
        try:
            message_id = data.get("message_id")
            if not message_id:
                return

            # Update read status
            await database_sync_to_async(self.participant.update_last_read)(message_id)

            # Send read receipt to chat
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "message_read",
                    "message_id": message_id,
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "timestamp": timezone.now().isoformat(),
                    "exclude_sender": self.channel_name,
                },
            )

        except Exception as e:
            logger.error(f"Error marking message as read: {e}", exc_info=True)

    async def handle_reaction(self, data):
        """Handle message reactions."""
        try:
            message_id = data.get("message_id")
            emoji = data.get("emoji")

            if not message_id or not emoji:
                await self.send_error(
                    "invalid_data", "Message ID and emoji are required"
                )
                return

            # Get message
            try:
                message = await database_sync_to_async(ChatMessage.objects.get)(
                    id=message_id, chat=self.chat
                )
            except ChatMessage.DoesNotExist:
                await self.send_error("message_not_found", "Message not found")
                return

            # Add/remove reaction
            await database_sync_to_async(message.add_reaction)(self.user, emoji)

            # Send reaction update to chat
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "reaction_update",
                    "message_id": message_id,
                    "reactions": message.reactions,
                    "user_id": str(self.user.id),
                    "emoji": emoji,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error handling reaction: {e}", exc_info=True)
            await self.send_error("reaction_failed", "Failed to add reaction")

    async def handle_edit_message(self, data):
        """Handle message editing."""
        try:
            message_id = data.get("message_id")
            new_content = data.get("content", "").strip()

            if not message_id or not new_content:
                await self.send_error(
                    "invalid_data", "Message ID and content are required"
                )
                return

            # Get message
            try:
                message = await database_sync_to_async(ChatMessage.objects.get)(
                    id=message_id, chat=self.chat, sender=self.user
                )
            except ChatMessage.DoesNotExist:
                await self.send_error(
                    "message_not_found", "Message not found or not yours"
                )
                return

            # Check if message can be edited
            if not await database_sync_to_async(message.can_be_edited)(self.user):
                await self.send_error("edit_denied", "Message cannot be edited")
                return

            # Update message
            await database_sync_to_async(self._edit_message)(message, new_content)

        except Exception as e:
            logger.error(f"Error editing message: {e}", exc_info=True)
            await self.send_error("edit_failed", "Failed to edit message")

    async def handle_delete_message(self, data):
        """Handle message deletion."""
        try:
            message_id = data.get("message_id")
            delete_for_everyone = data.get("delete_for_everyone", False)

            if not message_id:
                await self.send_error("invalid_data", "Message ID is required")
                return

            # Get message
            try:
                message = await database_sync_to_async(ChatMessage.objects.get)(
                    id=message_id, chat=self.chat
                )
            except ChatMessage.DoesNotExist:
                await self.send_error("message_not_found", "Message not found")
                return

            # Check permissions
            if not await database_sync_to_async(message.can_be_deleted)(self.user):
                await self.send_error("delete_denied", "You cannot delete this message")
                return

            # Delete message
            delete_type = (
                ChatMessage.DeleteType.FOR_EVERYONE
                if delete_for_everyone
                else ChatMessage.DeleteType.FOR_ME
            )
            await database_sync_to_async(message.soft_delete)(delete_type, self.user)

        except Exception as e:
            logger.error(f"Error deleting message: {e}", exc_info=True)
            await self.send_error("delete_failed", "Failed to delete message")

    async def handle_join_call(self, data):
        """Handle joining a call."""
        try:
            call_id = data.get("call_id")

            if not call_id:
                await self.send_error("invalid_data", "Call ID is required")
                return

            # Get call
            try:
                call = await database_sync_to_async(ChatCall.objects.get)(
                    id=call_id, chat=self.chat
                )
            except ChatCall.DoesNotExist:
                await self.send_error("call_not_found", "Call not found")
                return

            # Add participant to call
            from .models import ChatCallParticipant

            participant, created = await database_sync_to_async(
                ChatCallParticipant.objects.get_or_create
            )(
                call=call,
                user=self.user,
                defaults={"status": ChatCallParticipant.ParticipantStatus.JOINED},
            )

            if not created:
                participant.status = ChatCallParticipant.ParticipantStatus.JOINED
                participant.joined_at = timezone.now()
                await database_sync_to_async(participant.save)()

            # Notify other participants
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "call_participant_joined",
                    "call_id": str(call_id),
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error joining call: {e}", exc_info=True)
            await self.send_error("join_call_failed", "Failed to join call")

    async def handle_leave_call(self, data):
        """Handle leaving a call."""
        try:
            call_id = data.get("call_id")

            if not call_id:
                await self.send_error("invalid_data", "Call ID is required")
                return

            # Update participant status
            from .models import ChatCallParticipant

            try:
                participant = await database_sync_to_async(
                    ChatCallParticipant.objects.get
                )(call_id=call_id, user=self.user)
                participant.status = ChatCallParticipant.ParticipantStatus.LEFT
                participant.left_at = timezone.now()
                await database_sync_to_async(participant.save)()

                # Notify other participants
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "call_participant_left",
                        "call_id": str(call_id),
                        "user_id": str(self.user.id),
                        "username": self.user.username,
                        "timestamp": timezone.now().isoformat(),
                    },
                )

            except ChatCallParticipant.DoesNotExist:
                pass

        except Exception as e:
            logger.error(f"Error leaving call: {e}", exc_info=True)

    async def handle_ping(self, data):
        """Handle ping message for keeping connection alive."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "pong",
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

    # Group message handlers
    async def chat_message(self, event):
        """Send message to WebSocket."""
        if event.get("exclude_sender") == self.channel_name:
            return
        await self.send(text_data=json.dumps(event))

    async def message_edited(self, event):
        """Send message edit notification."""
        await self.send(text_data=json.dumps(event))

    async def message_deleted(self, event):
        """Send message deletion notification."""
        await self.send(text_data=json.dumps(event))

    async def message_read(self, event):
        """Send read receipt notification."""
        if event.get("exclude_sender") == self.channel_name:
            return
        await self.send(text_data=json.dumps(event))

    async def typing_indicator(self, event):
        """Send typing indicator."""
        if event.get("exclude_sender") == self.channel_name:
            return
        await self.send(text_data=json.dumps(event))

    async def online_status(self, event):
        """Send online status update."""
        await self.send(text_data=json.dumps(event))

    async def reaction_update(self, event):
        """Send reaction update."""
        await self.send(text_data=json.dumps(event))

    async def call_started(self, event):
        """Send call started notification."""
        await self.send(text_data=json.dumps(event))

    async def call_ended(self, event):
        """Send call ended notification."""
        await self.send(text_data=json.dumps(event))

    async def call_participant_joined(self, event):
        """Send call participant joined notification."""
        await self.send(text_data=json.dumps(event))

    async def call_participant_left(self, event):
        """Send call participant left notification."""
        await self.send(text_data=json.dumps(event))

    async def participant_joined(self, event):
        """Send participant joined notification."""
        await self.send(text_data=json.dumps(event))

    async def moderation_action(self, event):
        """Send moderation action notification."""
        await self.send(text_data=json.dumps(event))

    async def poll_created(self, event):
        """Send poll created notification."""
        await self.send(text_data=json.dumps(event))

    # Utility methods
    async def send_error(self, error_code: str, message: str):
        """Send error message to WebSocket."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "error_code": error_code,
                    "message": message,
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

    async def update_online_status(self, is_online: bool):
        """Update user's online status."""
        try:
            if is_online:
                ChatCache.add_online_user(self.chat_id, self.user.id)
            else:
                ChatCache.remove_online_user(self.chat_id, self.user.id)

            # Broadcast status to chat
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "online_status",
                    "user_id": str(self.user.id),
                    "username": self.user.username,
                    "is_online": is_online,
                    "timestamp": timezone.now().isoformat(),
                },
            )

        except Exception as e:
            logger.error(f"Error updating online status: {e}", exc_info=True)

    async def check_slow_mode(self) -> bool:
        """Check if user is in slow mode."""
        try:
            if self.chat.slow_mode_delay == 0:
                return False

            if await database_sync_to_async(lambda: self.participant.is_admin())():
                return False

            cache_key = f"slow_mode_{self.user.id}_{self.chat_id}"
            last_message_time = cache.get(cache_key)

            if last_message_time:
                time_diff = (timezone.now() - last_message_time).total_seconds()
                if time_diff < self.chat.slow_mode_delay:
                    return True

            # Update cache
            cache.set(cache_key, timezone.now(), self.chat.slow_mode_delay)
            return False

        except Exception as e:
            logger.error(f"Error checking slow mode: {e}", exc_info=True)
            return False

    async def send_recent_messages(self, limit: int = 50):
        """Send recent messages to newly connected user."""
        try:
            messages = await database_sync_to_async(list)(
                ChatMessage.objects.filter(
                    chat=self.chat,
                    status__in=[
                        ChatMessage.MessageStatus.SENT,
                        ChatMessage.MessageStatus.DELIVERED,
                        ChatMessage.MessageStatus.READ,
                    ],
                )
                .select_related("sender")
                .order_by("-created_at")[:limit]
            )

            messages_data = []
            for message in reversed(messages):
                message_data = {
                    "id": str(message.id),
                    "sender_id": str(message.sender.id) if message.sender else None,
                    "sender_username": (
                        message.sender.username if message.sender else "System"
                    ),
                    "sender_name": (
                        message.sender.get_full_name() if message.sender else "System"
                    ),
                    "type": message.type,
                    "content": message.content,
                    "reactions": message.reactions,
                    "is_forwarded": message.is_forwarded,
                    "is_pinned": message.is_pinned,
                    "reply_to": str(message.reply_to.id) if message.reply_to else None,
                    "created_at": message.created_at.isoformat(),
                    "edit_date": (
                        message.edit_date.isoformat() if message.edit_date else None
                    ),
                }
                messages_data.append(message_data)

            await self.send(
                text_data=json.dumps(
                    {
                        "type": "recent_messages",
                        "messages": messages_data,
                        "count": len(messages_data),
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

        except Exception as e:
            logger.error(f"Error sending recent messages: {e}", exc_info=True)

    async def auto_stop_typing(self):
        """Automatically stop typing after 5 seconds."""
        try:
            await asyncio.sleep(5)
            await self.handle_typing_stop({})
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in auto stop typing: {e}", exc_info=True)

    async def heartbeat_loop(self):
        """Send periodic heartbeat to keep connection alive."""
        try:
            while True:
                await asyncio.sleep(30)  # Send heartbeat every 30 seconds
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "heartbeat",
                            "timestamp": timezone.now().isoformat(),
                        }
                    )
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error in heartbeat loop: {e}", exc_info=True)

    def _edit_message(self, message, new_content):
        """Edit message (sync function for database_sync_to_async)."""
        message.original_content = message.content
        message.content = new_content
        message.edit_date = timezone.now()
        message.edit_count += 1
        message.status = ChatMessage.MessageStatus.EDITED
        message.save(
            update_fields=[
                "content",
                "edit_date",
                "edit_count",
                "status",
                "original_content",
            ]
        )


class NotificationConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for user notifications.
    Handles general notifications outside of specific chats.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = None
        self.user_group_name = None

    async def connect(self):
        """Handle WebSocket connection."""
        try:
            # Authenticate user
            await self.authenticate_user()
            if not self.user:
                await self.close(code=4001)
                return

            # Set up group name
            self.user_group_name = f"user_{self.user.id}"

            # Join user group
            await self.channel_layer.group_add(self.user_group_name, self.channel_name)

            # Accept connection
            await self.accept()

            # Send connection confirmation
            await self.send(
                text_data=json.dumps(
                    {
                        "type": "connection_established",
                        "user_id": str(self.user.id),
                        "timestamp": timezone.now().isoformat(),
                    }
                )
            )

            logger.info(f"User {self.user.username} connected to notifications")

        except Exception as e:
            logger.error(f"Error in notification connect: {e}", exc_info=True)
            await self.close(code=4000)

    async def disconnect(self, close_code):
        """Handle WebSocket disconnection."""
        try:
            # Leave user group
            if self.user_group_name:
                await self.channel_layer.group_discard(
                    self.user_group_name, self.channel_name
                )

            logger.info(
                f"User {self.user.username if self.user else 'Unknown'} disconnected from notifications"
            )

        except Exception as e:
            logger.error(f"Error in notification disconnect: {e}", exc_info=True)

    async def receive(self, text_data):
        """Handle incoming WebSocket messages."""
        try:
            data = json.loads(text_data)
            message_type = data.get("type")

            if message_type == "ping":
                await self.send(
                    text_data=json.dumps(
                        {
                            "type": "pong",
                            "timestamp": timezone.now().isoformat(),
                        }
                    )
                )

        except json.JSONDecodeError:
            await self.send_error("invalid_json", "Invalid JSON format")
        except Exception as e:
            logger.error(f"Error in notification receive: {e}", exc_info=True)

    async def authenticate_user(self):
        """Authenticate user from query parameters."""
        try:
            query_string = self.scope.get("query_string", b"").decode()
            token = None

            for param in query_string.split("&"):
                if param.startswith("token="):
                    token = param.split("=", 1)[1]
                    break

            if not token:
                return

            # Validate JWT token
            try:
                UntypedToken(token)
                decoded_data = jwt_decode(
                    token, settings.SECRET_KEY, algorithms=["HS256"]
                )
                user_id = decoded_data.get("user_id")
            except (InvalidToken, TokenError, Exception):
                return

            # Get user
            self.user = await database_sync_to_async(User.objects.get)(id=user_id)

            if not self.user.is_active:
                self.user = None

        except User.DoesNotExist:
            pass
        except Exception as e:
            logger.error(f"Notification authentication error: {e}", exc_info=True)

    # Group message handlers
    async def send_notification(self, event):
        """Send notification to WebSocket."""
        await self.send(text_data=json.dumps(event))

    async def chat_invitation(self, event):
        """Send chat invitation notification."""
        await self.send(text_data=json.dumps(event))

    async def call_invitation(self, event):
        """Send call invitation notification."""
        await self.send(text_data=json.dumps(event))

    async def send_error(self, error_code: str, message: str):
        """Send error message to WebSocket."""
        await self.send(
            text_data=json.dumps(
                {
                    "type": "error",
                    "error_code": error_code,
                    "message": message,
                    "timestamp": timezone.now().isoformat(),
                }
            )
        )

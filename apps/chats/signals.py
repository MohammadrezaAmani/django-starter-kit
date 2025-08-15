import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.cache import cache
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.notifications.utils import send_notification

from .models import (
    Chat,
    ChatCache,
    ChatCall,
    ChatJoinRequest,
    ChatMessage,
    ChatModerationLog,
    ChatParticipant,
    ChatPoll,
)

logger = logging.getLogger(__name__)
channel_layer = get_channel_layer()


@receiver(post_save, sender=ChatMessage)
def handle_new_message(sender, instance, created, **kwargs):
    """Handle new message creation."""
    if not created:
        return

    # Update chat's last message
    instance.chat.last_message = instance
    instance.chat.updated_at = timezone.now()
    instance.chat.messages_count += 1
    instance.chat.save(update_fields=["last_message", "updated_at", "messages_count"])

    # Update unread counts for all participants except sender
    participants = ChatParticipant.objects.filter(
        chat=instance.chat, status=ChatParticipant.ParticipantStatus.ACTIVE
    ).exclude(user=instance.sender)

    for participant in participants:
        if not participant.is_muted:
            participant.unread_count += 1

            # Check for mentions
            if instance.content and f"@{participant.user.username}" in instance.content:
                participant.unread_mentions_count += 1

            participant.save(update_fields=["unread_count", "unread_mentions_count"])

            # Invalidate cache
            ChatCache.invalidate_unread_count(participant.user.id, instance.chat.id)

    # Send WebSocket notification to all chat participants
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{instance.chat.id}",
            {
                "type": "chat_message",
                "message": {
                    "id": str(instance.id),
                    "chat_id": str(instance.chat.id),
                    "sender_id": str(instance.sender.id) if instance.sender else None,
                    "sender_name": (
                        instance.sender.get_full_name() if instance.sender else "System"
                    ),
                    "sender_username": (
                        instance.sender.username if instance.sender else "system"
                    ),
                    "type": instance.type,
                    "content": instance.content,
                    "has_media": instance.has_media,
                    "is_forwarded": instance.is_forwarded,
                    "reply_to": (
                        str(instance.reply_to.id) if instance.reply_to else None
                    ),
                    "reactions": instance.reactions,
                    "created_at": instance.created_at.isoformat(),
                    "edit_date": (
                        instance.edit_date.isoformat() if instance.edit_date else None
                    ),
                },
            },
        )

    # Send push notifications for offline users
    offline_participants = participants.filter(
        user__last_activity__lt=timezone.now() - timezone.timedelta(minutes=5)
    ).exclude(notification_level=ChatParticipant.NotificationLevel.DISABLED)

    for participant in offline_participants:
        # Skip if user muted this chat
        if participant.is_muted:
            continue

        # Skip if mentions only and no mention
        if (
            participant.notification_level == ChatParticipant.NotificationLevel.MENTIONS
            and f"@{participant.user.username}" not in instance.content
        ):
            continue

        # Determine notification content
        if instance.chat.type == Chat.ChatType.PRIVATE:
            title = instance.sender.get_full_name() if instance.sender else "Message"
            chat_name = ""
        else:
            title = instance.chat.name or "Group Chat"
            chat_name = f" in {title}"

        # Create notification
        notification_content = instance.content[:100] + (
            "..." if len(instance.content) > 100 else ""
        )

        # Handle sender name for system messages
        sender_name = instance.sender.get_full_name() if instance.sender else "System"

        send_notification(
            user=participant.user,
            message=f"{sender_name}{chat_name}: {notification_content}",
            subject=title,
            channels=["IN_APP", "WEBSOCKET"],
            category="chat",
            metadata={
                "chat_id": str(instance.chat.id),
                "message_id": str(instance.id),
                "action": "new_message",
                "link": f"/chats/{instance.chat.id}",
            },
        )


@receiver(post_save, sender=ChatMessage)
def handle_message_edit(sender, instance, created, **kwargs):
    """Handle message editing."""
    if created or not instance.edit_date:
        return

    # Send WebSocket notification for message edit
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{instance.chat.id}",
            {
                "type": "message_edited",
                "message": {
                    "id": str(instance.id),
                    "content": instance.content,
                    "edit_date": instance.edit_date.isoformat(),
                    "edit_count": instance.edit_count,
                },
            },
        )


@receiver(post_save, sender=ChatParticipant)
def handle_participant_change(sender, instance, created, **kwargs):
    """Handle participant joining/leaving."""
    if created:
        # User joined chat
        instance.chat.participants_count += 1
        instance.chat.save(update_fields=["participants_count"])

        # Create system message for join
        if instance.chat.type in [Chat.ChatType.GROUP, Chat.ChatType.SUPERGROUP]:
            ChatMessage.objects.create(
                chat=instance.chat,
                sender=None,
                type=ChatMessage.MessageType.SYSTEM,
                content=f"{instance.user.get_full_name()} joined the chat",
                action="user_joined",
                action_user=instance.user,
            )

        # Send WebSocket notification
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{instance.chat.id}",
                {
                    "type": "participant_joined",
                    "user": {
                        "id": str(instance.user.id),
                        "username": instance.user.username,
                        "full_name": instance.user.get_full_name(),
                        "role": instance.role,
                    },
                },
            )

    # Handle status changes
    if not created and instance.status == ChatParticipant.ParticipantStatus.LEFT:
        # User left chat
        instance.chat.participants_count -= 1
        instance.chat.save(update_fields=["participants_count"])

        # Create system message for leave
        if instance.chat.type in [Chat.ChatType.GROUP, Chat.ChatType.SUPERGROUP]:
            ChatMessage.objects.create(
                chat=instance.chat,
                sender=None,
                type=ChatMessage.MessageType.SYSTEM,
                content=f"{instance.user.get_full_name()} left the chat",
                action="user_left",
                action_user=instance.user,
            )


@receiver(post_save, sender=ChatCall)
def handle_call_events(sender, instance, created, **kwargs):
    """Handle call state changes."""
    if created:
        # New call started
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{instance.chat.id}",
                {
                    "type": "call_started",
                    "call": {
                        "id": str(instance.id),
                        "type": instance.type,
                        "initiator": (
                            {
                                "id": str(instance.initiator.id),
                                "username": instance.initiator.username,
                                "full_name": instance.initiator.get_full_name(),
                            }
                            if instance.initiator
                            else None
                        ),
                        "start_time": instance.start_time.isoformat(),
                    },
                },
            )

    elif instance.status == ChatCall.CallStatus.ENDED:
        # Call ended
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{instance.chat.id}",
                {
                    "type": "call_ended",
                    "call": {
                        "id": str(instance.id),
                        "duration": instance.duration,
                        "end_time": (
                            instance.end_time.isoformat() if instance.end_time else None
                        ),
                    },
                },
            )


@receiver(post_save, sender=ChatPoll)
def handle_poll_creation(sender, instance, created, **kwargs):
    """Handle poll creation."""
    if created:
        # Send WebSocket notification
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{instance.message.chat.id}",
                {
                    "type": "poll_created",
                    "poll": {
                        "id": str(instance.id),
                        "question": instance.question,
                        "type": instance.type,
                        "is_anonymous": instance.is_anonymous,
                        "allows_multiple_answers": instance.allows_multiple_answers,
                        "message_id": str(instance.message.id),
                    },
                },
            )


@receiver(post_save, sender=ChatModerationLog)
def handle_moderation_action(sender, instance, created, **kwargs):
    """Handle moderation actions."""
    if not created:
        return

    # Send notification to affected user (except for message deletions)
    if instance.target_user and instance.action not in [
        ChatModerationLog.ActionType.DELETE_MESSAGE
    ]:
        action_messages = {
            ChatModerationLog.ActionType.BAN_USER: "You have been banned from",
            ChatModerationLog.ActionType.RESTRICT_USER: "Your permissions have been restricted in",
            ChatModerationLog.ActionType.PROMOTE_USER: "You have been promoted in",
            ChatModerationLog.ActionType.DEMOTE_USER: "You have been demoted in",
        }

        message = action_messages.get(instance.action)
        if message:
            send_notification(
                user=instance.target_user,
                message=f"{message} {instance.chat.name or 'chat'}",
                subject="Chat Moderation Action",
                channels=["IN_APP", "WEBSOCKET"],
                category="moderation",
                metadata={
                    "chat_id": str(instance.chat.id),
                    "action": instance.action,
                    "reason": instance.reason,
                    "moderator": (
                        instance.moderator.get_full_name()
                        if instance.moderator
                        else "System"
                    ),
                },
            )

    # Send WebSocket notification to chat
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{instance.chat.id}",
            {
                "type": "moderation_action",
                "action": {
                    "type": instance.action,
                    "moderator": (
                        {
                            "id": str(instance.moderator.id),
                            "username": instance.moderator.username,
                            "full_name": instance.moderator.get_full_name(),
                        }
                        if instance.moderator
                        else None
                    ),
                    "target_user": (
                        {
                            "id": str(instance.target_user.id),
                            "username": instance.target_user.username,
                            "full_name": instance.target_user.get_full_name(),
                        }
                        if instance.target_user
                        else None
                    ),
                    "reason": instance.reason,
                    "created_at": instance.created_at.isoformat(),
                },
            },
        )


@receiver(post_save, sender=ChatJoinRequest)
def handle_join_request(sender, instance, created, **kwargs):
    """Handle join requests."""
    if created:
        # Notify chat admins about new join request
        admins = ChatParticipant.objects.filter(
            chat=instance.chat,
            role__in=[
                ChatParticipant.ParticipantRole.OWNER,
                ChatParticipant.ParticipantRole.ADMIN,
            ],
            status=ChatParticipant.ParticipantStatus.ACTIVE,
        )

        for admin in admins:
            send_notification(
                user=admin.user,
                message=f"{instance.user.get_full_name()} wants to join {instance.chat.name or 'chat'}",
                subject="New Join Request",
                channels=["IN_APP", "WEBSOCKET"],
                category="join_request",
                metadata={
                    "chat_id": str(instance.chat.id),
                    "requester_id": str(instance.user.id),
                    "request_id": str(instance.id),
                    "bio": instance.bio,
                    "action": "new_join_request",
                },
            )

    elif instance.status == ChatJoinRequest.RequestStatus.APPROVED:
        # Notify user that request was approved
        send_notification(
            user=instance.user,
            message=f"Your request to join {instance.chat.name or 'chat'} has been approved",
            subject="Join Request Approved",
            channels=["IN_APP", "WEBSOCKET"],
            category="join_request",
            metadata={
                "chat_id": str(instance.chat.id),
                "approved_by": (
                    instance.approved_by.get_full_name()
                    if instance.approved_by
                    else "Admin"
                ),
                "action": "request_approved",
            },
        )

    elif instance.status == ChatJoinRequest.RequestStatus.DECLINED:
        # Notify user that request was declined
        send_notification(
            user=instance.user,
            message=f"Your request to join {instance.chat.name or 'chat'} has been declined",
            subject="Join Request Declined",
            channels=["IN_APP", "WEBSOCKET"],
            category="join_request",
            metadata={"chat_id": str(instance.chat.id), "action": "request_declined"},
        )


@receiver(post_delete, sender=ChatMessage)
def handle_message_deletion(sender, instance, **kwargs):
    """Handle message deletion."""
    # Send WebSocket notification
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{instance.chat.id}",
            {
                "type": "message_deleted",
                "message_id": str(instance.id),
                "deleted_at": timezone.now().isoformat(),
            },
        )

    # Update chat message count
    instance.chat.messages_count = max(0, instance.chat.messages_count - 1)
    instance.chat.save(update_fields=["messages_count"])


@receiver(m2m_changed, sender=ChatMessage.read_by.through)
def handle_read_receipts(sender, instance, action, pk_set, **kwargs):
    """Handle read receipts."""
    if action == "post_add" and pk_set:
        # Send WebSocket notification for read receipts
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"chat_{instance.chat.id}",
                {
                    "type": "message_read",
                    "message_id": str(instance.id),
                    "read_by": list(pk_set),
                    "read_at": timezone.now().isoformat(),
                },
            )


def send_typing_indicator(chat_id, user_id, is_typing=True):
    """Send typing indicator via WebSocket."""
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "typing_indicator",
                "user_id": str(user_id),
                "is_typing": is_typing,
                "timestamp": timezone.now().isoformat(),
            },
        )


def send_online_status(chat_id, user_id, is_online=True):
    """Send online status via WebSocket."""
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "online_status",
                "user_id": str(user_id),
                "is_online": is_online,
                "last_seen": timezone.now().isoformat(),
            },
        )


def send_reaction_update(chat_id, message_id, reactions):
    """Send reaction update via WebSocket."""
    if channel_layer:
        async_to_sync(channel_layer.group_send)(
            f"chat_{chat_id}",
            {
                "type": "reaction_update",
                "message_id": str(message_id),
                "reactions": reactions,
                "updated_at": timezone.now().isoformat(),
            },
        )


# Cache invalidation signals
@receiver(post_save, sender=ChatParticipant)
def invalidate_participant_cache(sender, instance, **kwargs):
    """Invalidate participant-related cache."""
    cache_key = f"chat_participants_{instance.chat.id}"
    cache.delete(cache_key)

    ChatCache.invalidate_unread_count(instance.user.id, instance.chat.id)


@receiver(post_delete, sender=ChatParticipant)
def invalidate_participant_cache_on_delete(sender, instance, **kwargs):
    """Invalidate participant cache on deletion."""
    cache_key = f"chat_participants_{instance.chat.id}"
    cache.delete(cache_key)


# Performance optimization: Update last activity
@receiver(post_save, sender=ChatMessage)
def update_sender_activity(sender, instance, created, **kwargs):
    """Update sender's last activity."""
    if created and instance.sender:
        instance.sender.last_activity = timezone.now()
        instance.sender.save(update_fields=["last_activity"])

        # Update participant's last activity
        try:
            participant = ChatParticipant.objects.get(
                user=instance.sender, chat=instance.chat
            )
            participant.last_activity_at = timezone.now()
            participant.save(update_fields=["last_activity_at"])
        except ChatParticipant.DoesNotExist:
            pass


# Cleanup signals
@receiver(post_save, sender=ChatMessage)
def cleanup_old_typing_indicators(sender, instance, created, **kwargs):
    """Clean up old typing indicators when message is sent."""
    if not created:
        return

    # Clear typing indicator for sender
    if instance.sender:
        try:
            participant = ChatParticipant.objects.get(
                user=instance.sender, chat=instance.chat
            )
            participant.typing_until = None
            participant.save(update_fields=["typing_until"])

            # Send WebSocket to clear typing
            send_typing_indicator(instance.chat.id, instance.sender.id, False)
        except ChatParticipant.DoesNotExist:
            pass


# Auto-delete expired messages
@receiver(post_save, sender=ChatMessage)
def schedule_message_deletion(sender, instance, created, **kwargs):
    """Schedule message deletion if TTL is set."""
    if created and instance.ttl_seconds:
        from datetime import timedelta

        from django.utils import timezone

        instance.auto_delete_date = timezone.now() + timedelta(
            seconds=instance.ttl_seconds
        )
        instance.save(update_fields=["auto_delete_date"])

        # TODO: Schedule celery task for deletion
        # delete_message_task.apply_async(
        #     args=[str(instance.id)],
        #     eta=instance.auto_delete_date
        # )


# Error handling and logging
logger = logging.getLogger("chats.signals")


def log_signal_error(signal_name, instance, error):
    """Log signal processing errors."""
    logger.error(
        f"Error in {signal_name} signal for {instance.__class__.__name__} {instance.pk}: {error}",
        exc_info=True,
        extra={
            "signal": signal_name,
            "model": instance.__class__.__name__,
            "instance_id": str(instance.pk),
        },
    )


# Wrap signal handlers with error handling
def safe_signal_handler(handler_func):
    """Decorator to safely handle signal errors."""

    def wrapper(sender, instance, **kwargs):
        try:
            return handler_func(sender, instance, **kwargs)
        except Exception as e:
            log_signal_error(handler_func.__name__, instance, e)

    return wrapper


# Apply error handling to critical signals
handle_new_message = safe_signal_handler(handle_new_message)
handle_participant_change = safe_signal_handler(handle_participant_change)
handle_moderation_action = safe_signal_handler(handle_moderation_action)


def send_webhook(webhook, event_type, data):
    """Send webhook notification."""
    import hashlib
    import hmac
    import json

    import requests

    if not webhook.is_active or event_type not in webhook.events:
        return

    payload = {
        "event": event_type,
        "timestamp": timezone.now().isoformat(),
        "data": data,
    }

    headers = {"Content-Type": "application/json", "User-Agent": "ChatApp-Webhook/1.0"}

    # Add signature if secret is provided
    if webhook.secret:
        payload_json = json.dumps(payload, sort_keys=True)
        signature = hmac.new(
            webhook.secret.encode(), payload_json.encode(), hashlib.sha256
        ).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={signature}"

    try:
        response = requests.post(webhook.url, json=payload, headers=headers, timeout=30)

        webhook.delivery_count += 1
        webhook.last_delivery = timezone.now()

        if response.status_code >= 400:
            webhook.error_count += 1

        webhook.save(update_fields=["delivery_count", "last_delivery", "error_count"])

    except Exception as e:
        webhook.error_count += 1
        webhook.save(update_fields=["error_count"])
        logger.error(f"Webhook delivery failed: {e}")

from datetime import timedelta

from celery import shared_task
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Chat, ChatMessage

User = get_user_model()


@shared_task
def cleanup_old_data():
    """
    Clean up old data based on data retention policies.
    """
    # Delete messages older than 1 year
    old_messages = ChatMessage.objects.filter(
        created_at__lt=timezone.now() - timedelta(days=365)
    )
    old_messages_count = old_messages.count()
    old_messages.delete()

    # Delete inactive chats older than 6 months
    inactive_chats = Chat.objects.filter(
        updated_at__lt=timezone.now() - timedelta(days=180),
        status=Chat.ChatStatus.ARCHIVED,
    )
    inactive_chats_count = inactive_chats.count()
    inactive_chats.delete()

    return {
        "deleted_messages": old_messages_count,
        "deleted_chats": inactive_chats_count,
    }


@shared_task
def send_notification(user_id, message, notification_type="general"):
    """
    Send notification to user.
    """
    try:
        user = User.objects.get(id=user_id)
        # Implement notification sending logic here
        return {"status": "sent", "user": user.username}
    except User.DoesNotExist:
        return {"status": "error", "message": "User not found"}


@shared_task
def process_file_upload(file_path, chat_id):
    """
    Process uploaded file (virus scan, thumbnails, etc.)
    """
    # Implement file processing logic here
    return {"status": "processed", "file_path": file_path}


@shared_task
def update_user_activity(user_id):
    """
    Update user's last activity timestamp.
    """
    try:
        user = User.objects.get(id=user_id)
        user.last_activity = timezone.now()
        user.save(update_fields=["last_activity"])
        return {"status": "updated", "user": user.username}
    except User.DoesNotExist:
        return {"status": "error", "message": "User not found"}


@shared_task
def cleanup_expired_invite_links():
    """
    Clean up expired invite links.
    """
    from .models import ChatInviteLink

    expired_links = ChatInviteLink.objects.filter(
        expire_date__lt=timezone.now(), is_active=True
    )
    expired_count = expired_links.count()
    expired_links.update(is_active=False)

    return {"expired_links": expired_count}


@shared_task
def process_webhook_event(webhook_id, event_data):
    """
    Process webhook event delivery.
    """
    from .models import ChatWebhook

    try:
        webhook = ChatWebhook.objects.get(id=webhook_id, is_active=True)
        # Implement webhook delivery logic here
        return {"status": "delivered", "webhook_url": webhook.url}
    except ChatWebhook.DoesNotExist:
        return {"status": "error", "message": "Webhook not found"}

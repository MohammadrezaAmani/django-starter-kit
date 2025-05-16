import logging

from notifications.utils import send_notification

from .models import AuditLog

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """Extract client IP from request."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def log_user_action(
    request=None,
    user=None,
    action_type=None,
    status=AuditLog.Status.SUCCESS,
    content_object=None,
    changes=None,
    error_message=None,
    priority=None,
    notify=False,
):
    """Log a user action and optionally send a notification."""
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    metadata = {
        "url": request.build_absolute_uri() if request else "",
        "method": request.method if request else "",
    }

    # Automatically notify for high-priority actions if not specified
    if priority == AuditLog.Priority.HIGH and notify is False:
        notify = True

    AuditLog.log_action(
        user=user
        or (request.user if request and request.user.is_authenticated else None),
        action_type=action_type,
        status=status,
        priority=priority,
        ip_address=ip_address,
        user_agent=user_agent,
        content_object=content_object,
        object_repr=str(content_object) if content_object else "",
        changes=changes or {},
        metadata=metadata,
        error_message=error_message or "",
    )

    if notify and user:
        send_notification(
            user=user,
            message=f"High-priority action {action_type} performed on {str(content_object) or 'system'}.",
            category="system",
            priority=AuditLog.Priority.HIGH,  # type: ignore
            channels=["IN_APP", "WEBSOCKET"],
            metadata={"audit_log_action": action_type},
        )

    logger.info(
        f"Logged {action_type} (Priority: {priority or 'Default'}) for user {user or 'Anonymous'}"
    )

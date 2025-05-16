import os
from datetime import timedelta
from pathlib import Path

from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent


LOGS_DIR = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(exist_ok=True)
STATICFILES_DIRS = []


SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-96heki=*w5p#^#!6x#k#urqnn=43(a06uyt(#dq_^he6&#l0e!",
)
DEBUG = os.environ.get("DJANGO_DEBUG", "True") == "True"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    "http://localhost,https://localhost,https://*.bank.test,https://yourdomain.com",
).split(",")
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"


INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "guardian",
    "channels",
    "django_ratelimit",
    "mptt",
    "django_countries",
    "encrypted_model_fields",
    "drf_spectacular",
    "corsheaders",
    "azbankgateways",
    "accounts",
    "notifications",
    "audit_log",
    "common",
    "payment",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # "audit_log.middleware.AuditLogMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.i18n",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.postgresql",
#         "NAME": os.environ.get("DB_NAME", "starter-kit"),
#         "USER": os.environ.get("DB_USER", "amani"),
#         "PASSWORD": os.environ.get("DB_PASSWORD", "your_password"),
#         "HOST": os.environ.get("DB_HOST", "localhost"),
#         "PORT": os.environ.get("DB_PORT", "5432"),
#     }
# }

# sqlite
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True
LANGUAGES = [
    ("fa", _("Persian")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]


STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


AUTH_USER_MODEL = "accounts.User"
GUARDIAN_RAISE_EXCEPTION = True
AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
)
STATICFILES_DIRS = []

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
}


SPECTACULAR_SETTINGS = {
    "TITLE": "Your Project API",
    "DESCRIPTION": "A comprehensive API for authentication, notifications, audit logging, common models, and payment processing.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": True,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "displayOperationId": True,
        "tryItOutEnabled": True,
    },
    "TAGS": [
        {
            "name": "Authentication",
            "description": "Endpoints for user login, logout, and token management",
        },
        {
            "name": "User Management",
            "description": "Endpoints for user registration and profile retrieval",
        },
        {
            "name": "Password Reset",
            "description": "Endpoints for password reset requests and confirmation",
        },
        {
            "name": "Notifications",
            "description": "Endpoints for managing user notifications",
        },
        {"name": "Audit Log", "description": "Endpoints for tracking user actions"},
        {
            "name": "Common",
            "description": "Endpoints for tags, comments, locations, etc.",
        },
        {
            "name": "Payment",
            "description": "Endpoints for payment processing and refunds",
        },
    ],
    "SECURITY": [
        {"BearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}
    ],
    "ENUM_NAME_OVERRIDES": {
        "ErrorEnum": {
            "invalid_credentials": "Invalid username or password",
            "account_disabled": "User account is disabled",
            "invalid_token": "Token is invalid or expired",
            "blacklisted_token": "Token has been blacklisted",
        }
    },
    "POSTPROCESSING_HOOKS": ["drf_spectacular.hooks.postprocess_schema_enums"],
}


SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("JWT_SECRET_KEY", "your-secret-key"),
    "VERIFYING_KEY": None,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}


REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = os.environ.get("REDIS_PORT", 6379)
REDIS_DB = os.environ.get("REDIS_DB", 0)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}
SESSION_ENGINE = "django.contrib.sessions.backends.cache"
SESSION_CACHE_ALIAS = "default"


CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [(REDIS_HOST, REDIS_PORT)],
        },
    },
}


EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = os.environ.get("EMAIL_PORT", 587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "your-email@gmail.com")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "your-email-password")
DEFAULT_FROM_EMAIL = os.environ.get("EMAIL_HOST_USER", "your-email@gmail.com")


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "file": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOGS_DIR / "app.log",
            "maxBytes": 1024 * 1024 * 5,
            "backupCount": 5,
            "formatter": "verbose",
        },
        "console": {
            "level": "INFO",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": True,
        },
        "django": {
            "handlers": ["file", "console"],
            "level": "INFO",
            "propagate": False,
        },
        "payment": {
            "handlers": ["file", "console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}


# GDAL_LIBRARY_PATH = os.environ.get("GDAL_LIBRARY_PATH", "/usr/lib/libgdal.so")
# GEOS_LIBRARY_PATH = os.environ.get("GEOS_LIBRARY_PATH", "/usr/lib/libgeos_c.so")
SPATIALITE_LIBRARY_PATH = os.environ.get("SPATIALITE_LIBRARY_PATH", "mod_spatialite")


CORS_ALLOW_ALL_ORIGINS = DEBUG
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:8000,https://yourdomain.com,https://*.bank.test",
).split(",")
CORS_ALLOW_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
CORS_ALLOW_HEADERS = [
    "accept",
    "authorization",
    "content-type",
    "x-csrftoken",
    "x-requested-with",
]


RATELIMIT_ENABLE = True
RATELIMIT_CACHE = "default"
RATELIMIT_KEY = "user_or_ip"
RATELIMIT_RATE = "100/m"


FIELD_ENCRYPTION_KEY = os.environ.get(
    "FIELD_ENCRYPTION_KEY", "q7lJgCoBmfTBzEa-3uWZIxWwl9p-zvX7VXXHHBvwBUQ="
)


AZ_IRANIAN_BANK_GATEWAYS = {
    "GATEWAYS": {
        "BMI": {
            "MERCHANT_CODE": os.environ.get("BMI_MERCHANT_CODE", ""),
            "TERMINAL_CODE": os.environ.get("BMI_TERMINAL_CODE", ""),
            "SECRET_KEY": os.environ.get("BMI_SECRET_KEY", ""),
        },
        "SEP": {
            "MERCHANT_CODE": os.environ.get("SEP_MERCHANT_CODE", ""),
            "TERMINAL_CODE": os.environ.get("SEP_TERMINAL_CODE", ""),
        },
        "ZARINPAL": {
            "MERCHANT_CODE": os.environ.get("ZARINPAL_MERCHANT_CODE", ""),
            "SANDBOX": int(os.environ.get("ZARINPAL_SANDBOX", 0)),
        },
        "IDPAY": {
            "MERCHANT_CODE": os.environ.get("IDPAY_MERCHANT_CODE", ""),
            "METHOD": "POST",
            "X_SANDBOX": int(os.environ.get("IDPAY_X_SANDBOX", 0)),
        },
        "ZIBAL": {
            "MERCHANT_CODE": os.environ.get("ZIBAL_MERCHANT_CODE", ""),
        },
        "BAHAMTA": {
            "MERCHANT_CODE": os.environ.get("BAHAMTA_MERCHANT_CODE", ""),
        },
        "MELLAT": {
            "TERMINAL_CODE": os.environ.get("MELLAT_TERMINAL_CODE", ""),
            "USERNAME": os.environ.get("MELLAT_USERNAME", ""),
            "PASSWORD": os.environ.get("MELLAT_PASSWORD", ""),
        },
        "PAYV1": {
            "MERCHANT_CODE": os.environ.get("PAYV1_MERCHANT_CODE", ""),
            "X_SANDBOX": int(os.environ.get("PAYV1_X_SANDBOX", 0)),
        },
    },
    "IS_SAMPLE_FORM_ENABLE": DEBUG,
    "DEFAULT": "SEP",
    "CURRENCY": "IRR",
    "TRACKING_CODE_QUERY_PARAM": "tc",
    "TRACKING_CODE_LENGTH": 16,
    "SETTING_VALUE_READER_CLASS": "azbankgateways.readers.DefaultReader",
    "BANK_PRIORITIES": [
        "SEP",
        "BMI",
        "ZARINPAL",
        "IDPAY",
        "ZIBAL",
        "BAHAMTA",
        "MELLAT",
        "PAYV1",
    ],
    "IS_SAFE_GET_GATEWAY_PAYMENT": True,
    "CUSTOM_APP": "payment",
    "CALLBACK_NAMESPACE": "payment:callback",
}
from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "action_type",
        "status",
        "priority",
        "ip_address",
        "object_repr",
        "created_at",
    )
    list_filter = ("action_type", "status", "priority", "created_at")
    search_fields = ("user__username", "object_repr", "error_message", "ip_address")
    readonly_fields = [field.name for field in AuditLog._meta.fields]  # type: ignore
    ordering = ("-created_at",)
from django.apps import AppConfig


class AuditLogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"  # type: ignore
    name = "audit_log"

    def ready(self):
        import audit_log.signals  # noqa: F401 type: ignore
from .models import AuditLog
from .utils import log_user_action


class AuditLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if request.method in ["POST", "PUT", "PATCH", "DELETE"]:
            action_type = {
                "POST": AuditLog.ActionType.CREATE,
                "PUT": AuditLog.ActionType.UPDATE,
                "PATCH": AuditLog.ActionType.UPDATE,
                "DELETE": AuditLog.ActionType.DELETE,
            }.get(request.method, AuditLog.ActionType.VIEW)

            priority = {
                "POST": AuditLog.Priority.MEDIUM,
                "PUT": AuditLog.Priority.MEDIUM,
                "PATCH": AuditLog.Priority.MEDIUM,
                "DELETE": AuditLog.Priority.HIGH,
            }.get(request.method, AuditLog.Priority.LOW)

            log_user_action(
                request=request,
                action_type=action_type,
                status=(
                    AuditLog.Status.SUCCESS
                    if response.status_code < 400
                    else AuditLog.Status.FAILED
                ),
                priority=priority,
                notify=action_type == AuditLog.ActionType.DELETE,
            )

        return response
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _

User = get_user_model()


class AuditLog(models.Model):
    """Stores detailed logs of user and system actions."""

    class ActionType(models.TextChoices):
        LOGIN = "LOGIN", _("Login")
        LOGOUT = "LOGOUT", _("Logout")
        CREATE = "CREATE", _("Create")
        UPDATE = "UPDATE", _("Update")
        DELETE = "DELETE", _("Delete")
        VIEW = "VIEW", _("View")
        SYSTEM = "SYSTEM", _("System")

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", _("Success")
        FAILED = "FAILED", _("Failed")

    class Priority(models.TextChoices):
        LOW = "LOW", _("Low")
        MEDIUM = "MED", _("Medium")
        HIGH = "HIGH", _("High")

    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        help_text=_("User who performed the action, if applicable."),
    )
    action_type = models.CharField(
        max_length=20,
        choices=ActionType.choices,
        help_text=_("Type of action performed."),
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS,
        help_text=_("Status of the action."),
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.LOW,
        help_text=_("Priority level of the action."),
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        help_text=_("IP address of the client."),
    )
    user_agent = models.TextField(
        blank=True,
        help_text=_("User agent of the client (browser/server details)."),
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text=_("Model associated with the action."),
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=_("ID of the object affected."),  # type: ignore
    )
    content_object = GenericForeignKey("content_type", "object_id")
    object_repr = models.TextField(
        blank=True,
        help_text=_("String representation of the affected object."),
    )
    changes = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Changes made (before and after) in JSON format."),
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=_("Additional metadata (e.g., request URL, method)."),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    error_message = models.TextField(
        blank=True,
        help_text=_("Error message if the action failed."),
    )

    class Meta:
        verbose_name = _("audit log")
        verbose_name_plural = _("audit logs")
        indexes = [
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["action_type"]),
            models.Index(fields=["status"]),
            models.Index(fields=["priority"]),  # New index for priority
            models.Index(fields=["content_type", "object_id"]),
            models.Index(fields=["ip_address"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        user = self.user.username if self.user else "Anonymous"  # type: ignore
        return f"{self.action_type} ({self.priority}) by {user} at {self.created_at}"

    @classmethod
    def log_action(
        cls,
        user=None,
        action_type=None,
        status=Status.SUCCESS,
        priority=None,
        ip_address=None,
        user_agent=None,
        content_object=None,
        object_repr=None,
        changes=None,
        metadata=None,
        error_message=None,
    ):
        """Helper method to create an audit log entry."""
        content_type = None
        object_id = None
        if content_object:
            content_type = ContentType.objects.get_for_model(content_object)
            object_id = content_object.pk

        # Set default priority based on action_type if not provided
        if priority is None:
            priority_map = {
                cls.ActionType.LOGIN: cls.Priority.LOW,
                cls.ActionType.LOGOUT: cls.Priority.LOW,
                cls.ActionType.VIEW: cls.Priority.LOW,
                cls.ActionType.CREATE: cls.Priority.MEDIUM,
                cls.ActionType.UPDATE: cls.Priority.MEDIUM,
                cls.ActionType.DELETE: cls.Priority.HIGH,
                cls.ActionType.SYSTEM: cls.Priority.HIGH,
            }
            priority = priority_map.get(action_type, cls.Priority.LOW)  # type: ignore

        cls.objects.create(  # type: ignore
            user=user,
            action_type=action_type,
            status=status,
            priority=priority,
            ip_address=ip_address,
            user_agent=user_agent,
            content_type=content_type,
            object_id=object_id,
            object_repr=object_repr or (str(content_object) if content_object else ""),
            changes=changes or {},
            metadata=metadata or {},
            error_message=error_message or "",
        )
from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    content_type = serializers.StringRelatedField()
    user = serializers.StringRelatedField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "user",
            "action_type",
            "status",
            "priority",
            "ip_address",
            "user_agent",
            "content_type",
            "object_id",
            "object_repr",
            "changes",
            "metadata",
            "created_at",
            "error_message",
        ]
        read_only_fields = fields
import json

from django.core.serializers import serialize
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from audit_log.models import AuditLog
from audit_log.utils import log_user_action


@receiver(pre_save)
def log_model_update(sender, instance, **kwargs):
    if not hasattr(instance, "_audit_log_user"):
        return
    user = instance._audit_log_user
    if instance.pk:
        old_instance = sender.objects.filter(pk=instance.pk).first()
        if old_instance:
            old_data = json.loads(serialize("json", [old_instance]))[0]["fields"]
            new_data = json.loads(serialize("json", [instance]))[0]["fields"]
            changes = {
                k: {"old": old_data.get(k), "new": new_data.get(k)}
                for k in old_data
                if old_data.get(k) != new_data.get(k)
            }
            log_user_action(
                user=user,
                action_type=AuditLog.ActionType.UPDATE,
                content_object=instance,
                changes=changes,
                priority=AuditLog.Priority.MEDIUM,
            )


@receiver(post_save)
def log_model_create(sender, instance, created, **kwargs):
    if not created or not hasattr(instance, "_audit_log_user"):
        return
    user = instance._audit_log_user
    log_user_action(
        user=user,
        action_type=AuditLog.ActionType.CREATE,
        content_object=instance,
        priority=AuditLog.Priority.MEDIUM,
    )


@receiver(pre_delete)
def log_model_delete(sender, instance, **kwargs):
    if not hasattr(instance, "_audit_log_user"):
        return
    user = instance._audit_log_user
    data = json.loads(serialize("json", [instance]))[0]["fields"]
    log_user_action(
        user=user,
        action_type=AuditLog.ActionType.DELETE,
        content_object=instance,
        changes={"deleted": data},
        priority=AuditLog.Priority.HIGH,
        notify=True,
    )

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import AuditLogViewSet

router = DefaultRouter()
router.register(r"logs", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("api/", include(router.urls)),
]
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
    metadata=None,
):
    """Log a user action and optionally send a notification."""
    ip_address = get_client_ip(request) if request else None
    user_agent = request.META.get("HTTP_USER_AGENT", "") if request else ""
    metadata = metadata or {
        "url": request.build_absolute_uri() if request else "",
        "method": request.method if request else "",
    }
    if "url" not in metadata:
        metadata["url"] = request.build_absolute_uri() if request else ""
    if "method" not in metadata:
        metadata["method"] = request.method if request else ""
    if "user_agent" not in metadata:
        metadata["user_agent"] = user_agent
    if "ip_address" not in metadata:
        metadata["ip_address"] = ip_address

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
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated

from .models import AuditLog
from .serializers import AuditLogSerializer


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 1000


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()  # type: ignore
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = AuditLogPagination
    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]
    filterset_fields = [
        "action_type",
        "status",
        "priority",
        "ip_address",
        "content_type",
        "created_at",
    ]
    ordering_fields = ["created_at", "action_type", "status", "priority"]
    search_fields = ["user__username", "object_repr", "error_message"]

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return AuditLog.objects.all()  # type: ignore
        return AuditLog.objects.filter(user=user)  # type: ignore

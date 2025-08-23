import logging
import secrets
from datetime import timedelta
from typing import Any, Dict, Optional

import jwt
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.tokens import default_token_generator
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import ActivityLog, User
from apps.accounts.serializers import (
    EmailChangeSerializer,
    ForgotPasswordSerializer,
    LoginSerializer,
    PasswordChangeSerializer,
    RefreshSerializer,
    RegisterSerializer,
    ResetPasswordSerializer,
    TokenResponseSerializer,
    UserSerializer,
    VerifySerializer,
)
from apps.audit_log.models import AuditLog
from apps.common.mixins import SecurityMixin
from apps.common.utils import get_client_ip, get_user_agent

logger = logging.getLogger(__name__)


class LoginRateThrottle(AnonRateThrottle):
    """Custom rate limiting for login attempts"""

    scope = "login"


class PasswordResetRateThrottle(AnonRateThrottle):
    """Custom rate limiting for password reset attempts"""

    scope = "password_reset"


def get_tokens_for_user(user: User) -> Dict[str, Any]:
    """
    Generate JWT tokens for user with custom claims
    """
    refresh = RefreshToken.for_user(user)

    # Add custom claims
    refresh["user_id"] = user.id
    refresh["username"] = user.username
    refresh["email"] = user.email
    refresh["is_verified"] = user.is_verified
    refresh["profile_completed"] = (
        hasattr(user, "profile") and user.profile.bio is not None
    )

    access_token = refresh.access_token

    # Set token expiration
    access_token.set_exp(
        from_time=timezone.now(),
        lifetime=settings.SIMPLE_JWT.get(
            "ACCESS_TOKEN_LIFETIME", timedelta(minutes=30)
        ),
    )

    return {
        "access_token": str(access_token),
        "refresh_token": str(refresh),
        "expires_at": timezone.now()
        + settings.SIMPLE_JWT.get("ACCESS_TOKEN_LIFETIME", timedelta(minutes=30)),
        "token_type": "Bearer",
    }


@extend_schema_view(
    post=extend_schema(
        summary="User Login",
        description="Authenticate user and return JWT tokens",
        request=LoginSerializer,
        responses={
            200: TokenResponseSerializer,
            400: "Bad Request",
            401: "Invalid credentials",
            429: "Too many login attempts",
        },
    )
)
class LoginView(SecurityMixin, APIView):
    """
    Advanced login view with security features:
    - Rate limiting
    - Account lockout protection
    - Activity logging
    - IP tracking
    - Device tracking
    """

    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]
    serializer_class = LoginSerializer

    def get_lockout_key(self, identifier: str) -> str:
        """Generate cache key for account lockout"""
        return f"lockout:{identifier}"

    def get_attempt_key(self, identifier: str, ip: str) -> str:
        """Generate cache key for login attempts"""
        return f"attempts:{identifier}:{ip}"

    def is_account_locked(self, identifier: str) -> bool:
        """Check if account is locked"""
        return cache.get(self.get_lockout_key(identifier), False)

    def increment_failed_attempts(self, identifier: str, ip: str) -> int:
        """Increment failed login attempts"""
        key = self.get_attempt_key(identifier, ip)
        attempts = cache.get(key, 0) + 1
        cache.set(key, attempts, 900)  # 15 minutes

        # Lock account after 5 failed attempts
        if attempts >= 5:
            lockout_key = self.get_lockout_key(identifier)
            cache.set(lockout_key, True, 1800)  # 30 minutes lockout

        return attempts

    def clear_failed_attempts(self, identifier: str, ip: str) -> None:
        """Clear failed login attempts on successful login"""
        cache.delete(self.get_attempt_key(identifier, ip))
        cache.delete(self.get_lockout_key(identifier))

    def log_activity(
        self,
        user: Optional[User],
        request: Request,
        action: str,
        success: bool,
        **kwargs,
    ) -> None:
        """Log authentication activity"""
        try:
            ActivityLog.objects.create(
                user=user,
                activity_type=(
                    ActivityLog.ActivityType.LOGIN
                    if action == "login"
                    else ActivityLog.ActivityType.LOGIN_FAILED
                ),
                description=f"{action} {'successful' if success else 'failed'}",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                metadata={
                    "timestamp": timezone.now().isoformat(),
                    "success": success,
                    **kwargs,
                },
            )

            # Also create audit log for security tracking
            AuditLog.objects.create(
                user=user,
                action=action,
                resource_type="authentication",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
                success=success,
                metadata=kwargs,
            )
        except Exception as e:
            logger.error(f"Failed to log activity: {e}")

    def post(self, request: Request) -> Response:
        """Handle user login with advanced security"""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        identifier = serializer.validated_data.get(
            "username"
        ) or serializer.validated_data.get("email")
        password = serializer.validated_data["password"]
        ip_address = get_client_ip(request)

        # Check if account is locked
        if self.is_account_locked(identifier):
            self.log_activity(None, request, "login", False, reason="account_locked")
            return Response(
                {"error": "Account temporarily locked due to multiple failed attempts"},
                status=status.HTTP_423_LOCKED,
            )

        # Attempt authentication
        user = authenticate(request, username=identifier, password=password)

        if user is None:
            # Try with email if username failed
            try:
                user_obj = User.objects.get(email=identifier)
                user = authenticate(
                    request, username=user_obj.username, password=password
                )
            except User.DoesNotExist:
                pass

        if user is None:
            attempts = self.increment_failed_attempts(identifier, ip_address)
            self.log_activity(
                None,
                request,
                "login",
                False,
                reason="invalid_credentials",
                attempts=attempts,
            )

            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )

        # Check if user is active
        if not user.is_active:
            self.log_activity(user, request, "login", False, reason="inactive_account")
            return Response(
                {"error": "Account is inactive"}, status=status.HTTP_403_FORBIDDEN
            )

        # Check if email is verified (optional based on settings)
        if (
            getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False)
            and not user.is_verified
        ):
            self.log_activity(user, request, "login", False, reason="unverified_email")
            return Response(
                {"error": "Please verify your email before logging in"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Successful login
        self.clear_failed_attempts(identifier, ip_address)

        # Update user's last login and activity
        with transaction.atomic():
            user.last_login = timezone.now()
            user.save(update_fields=["last_login"])

            if hasattr(user, "profile"):
                user.update_last_activity()

        # Generate tokens
        tokens = get_tokens_for_user(user)

        # Log successful login
        self.log_activity(user, request, "login", True)

        # Prepare response data
        user_serializer = UserSerializer(user, context={"request": request})

        response_data = {
            **tokens,
            "user": user_serializer.data,
            "user_config": {
                "theme": (
                    getattr(user.profile, "theme", "light")
                    if hasattr(user, "profile")
                    else "light"
                ),
                "language": (
                    getattr(user.profile, "language", "en")
                    if hasattr(user, "profile")
                    else "en"
                ),
                "timezone": (
                    getattr(user.profile, "timezone", "UTC")
                    if hasattr(user, "profile")
                    else "UTC"
                ),
            },
        }

        return Response(response_data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="User Logout",
        description="Logout user and blacklist refresh token",
        responses={
            200: "Logout successful",
            400: "Bad Request",
        },
    )
)
class LogoutView(APIView):
    """
    Advanced logout view with token blacklisting
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle user logout"""
        try:
            refresh_token = request.data.get("refresh_token")

            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()

            # Log logout activity
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.LOGOUT,
                description="User logged out",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
            )

            return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Logout error: {e}")
            return Response(
                {"error": "Logout failed"}, status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema_view(
    get=extend_schema(
        summary="Get Current User",
        description="Get current authenticated user information",
        responses={
            200: UserSerializer,
            401: "Unauthorized",
        },
    )
)
class MeView(APIView):
    """
    Get current user information
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request: Request) -> Response:
        """Get current user data"""
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)


@extend_schema_view(
    post=extend_schema(
        summary="Refresh Token",
        description="Refresh access token using refresh token",
        request=RefreshSerializer,
        responses={
            200: TokenResponseSerializer,
            401: "Invalid refresh token",
        },
    )
)
class RefreshView(APIView):
    """
    Token refresh view with security checks
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle token refresh"""
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        refresh_token = serializer.validated_data["refresh_token"]

        try:
            token = RefreshToken(refresh_token)

            # Verify token is not blacklisted
            if token.check_blacklist():
                return Response(
                    {"error": "Token is blacklisted"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Get user from token
            user_id = token.payload.get("user_id")
            user = User.objects.get(id=user_id, is_active=True)

            # Generate new tokens
            new_tokens = get_tokens_for_user(user)

            # Log token refresh
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.TOKEN_REFRESH,
                description="Token refreshed",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
            )

            return Response(new_tokens, status=status.HTTP_200_OK)

        except jwt.ExpiredSignatureError:
            return Response(
                {"error": "Refresh token has expired"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except jwt.InvalidTokenError:
            return Response(
                {"error": "Invalid refresh token"}, status=status.HTTP_401_UNAUTHORIZED
            )
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_401_UNAUTHORIZED
            )


@extend_schema_view(
    post=extend_schema(
        summary="Verify Token",
        description="Verify if access token is valid",
        request=VerifySerializer,
        responses={
            200: "Token is valid",
            401: "Invalid token",
        },
    )
)
class VerifyView(APIView):
    """
    Token verification view
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request: Request) -> Response:
        """Verify access token"""
        serializer = VerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]

        try:
            # Verify token
            jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])

            return Response({"valid": True}, status=status.HTTP_200_OK)

        except jwt.ExpiredSignatureError:
            return Response(
                {"valid": False, "error": "Token has expired"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        except jwt.InvalidTokenError:
            return Response(
                {"valid": False, "error": "Invalid token"},
                status=status.HTTP_401_UNAUTHORIZED,
            )


@extend_schema_view(
    post=extend_schema(
        summary="User Registration",
        description="Register new user account",
        request=RegisterSerializer,
        responses={
            201: UserSerializer,
            400: "Validation Error",
        },
    )
)
class RegisterView(APIView):
    """
    User registration with email verification
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle user registration"""
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                user = serializer.save()

                # Log registration
                ActivityLog.objects.create(
                    user=user,
                    activity_type=ActivityLog.ActivityType.REGISTER,
                    description="User registered",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                )

                # Send verification email if enabled
                if getattr(settings, "REQUIRE_EMAIL_VERIFICATION", False):
                    self.send_verification_email(user, request)

                # Return user data
                user_serializer = UserSerializer(user, context={"request": request})
                return Response(user_serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Email verification error: {e}")
            return Response(
                {"error": "Verification failed"}, status=status.HTTP_400_BAD_REQUEST
            )


@extend_schema_view(
    get=extend_schema(
        summary="Get Current User Profile",
        description="Get current user profile with all related data",
        responses={200: UserSerializer},
    ),
    patch=extend_schema(
        summary="Update Current User Profile",
        description="Update current user profile information",
        responses={200: UserSerializer},
    ),
)
class ProfileMeView(APIView):
    """
    Handle current user profile operations
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def get(self, request: Request) -> Response:
        """Get current user profile"""
        try:
            user = request.user
            serializer = UserSerializer(user, context={"request": request})
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Profile get error: {e}")
            return Response(
                {"error": "Failed to get profile"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request: Request) -> Response:
        """Update current user profile"""
        try:
            user = request.user
            serializer = UserSerializer(
                user, data=request.data, partial=True, context={"request": request}
            )

            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data, status=status.HTTP_200_OK)

            return Response(
                {"errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.error(f"Profile update error: {e}")
            return Response(
                {"error": "Failed to update profile"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def send_verification_email(self, user: User, request: Request) -> None:
        """Send email verification"""
        try:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            verification_url = f"{settings.FRONTEND_URL}/verify-email/{uid}/{token}/"

            send_mail(
                subject="Verify your email address",
                message=f"Please verify your email by clicking: {verification_url}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")


@extend_schema_view(
    post=extend_schema(
        summary="Forgot Password",
        description="Send password reset email",
        request=ForgotPasswordSerializer,
        responses={
            200: "Reset email sent",
            404: "User not found",
        },
    )
)
class ForgotPasswordView(APIView):
    """
    Password reset request with rate limiting
    """

    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle password reset request"""
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]

        try:
            user = User.objects.get(email=email, is_active=True)

            # Generate reset token
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            # Store reset token in cache for security
            reset_key = f"password_reset:{uid}:{token}"
            cache.set(reset_key, user.id, 3600)  # 1 hour expiry

            # Send reset email
            reset_url = f"{settings.FRONTEND_URL}/reset-password/{uid}/{token}/"

            send_mail(
                subject="Password Reset Request",
                message=f"Reset your password by clicking: {reset_url}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )

            # Log password reset request
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.PASSWORD_RESET_REQUEST,
                description="Password reset requested",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
            )

            return Response(
                {"message": "Password reset email sent"}, status=status.HTTP_200_OK
            )

        except User.DoesNotExist:
            # Don't reveal if user exists for security
            return Response(
                {"message": "If the email exists, a reset link has been sent"},
                status=status.HTTP_200_OK,
            )


@extend_schema_view(
    post=extend_schema(
        summary="Reset Password",
        description="Reset password using reset token",
        request=ResetPasswordSerializer,
        responses={
            200: "Password reset successful",
            400: "Invalid token or password",
        },
    )
)
class ResetPasswordView(APIView):
    """
    Password reset confirmation
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle password reset confirmation"""
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uid = serializer.validated_data["uid"]
        token = serializer.validated_data["token"]
        password = serializer.validated_data["password"]

        try:
            # Verify reset token from cache
            reset_key = f"password_reset:{uid}:{token}"
            cached_user_id = cache.get(reset_key)

            if not cached_user_id:
                return Response(
                    {"error": "Invalid or expired reset token"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get user
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)

            # Verify token is valid for user
            if not default_token_generator.check_token(user, token):
                return Response(
                    {"error": "Invalid reset token"}, status=status.HTTP_400_BAD_REQUEST
                )

            # Reset password
            with transaction.atomic():
                user.set_password(password)
                user.save()

                # Clear reset token
                cache.delete(reset_key)

                # Log password reset
                ActivityLog.objects.create(
                    user=user,
                    activity_type=ActivityLog.ActivityType.PASSWORD_RESET,
                    description="Password reset completed",
                    ip_address=get_client_ip(request),
                    user_agent=get_user_agent(request),
                )

            return Response(
                {"message": "Password reset successful"}, status=status.HTTP_200_OK
            )

        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response(
                {"error": "Invalid reset parameters"},
                status=status.HTTP_400_BAD_REQUEST,
            )


@extend_schema_view(
    post=extend_schema(
        summary="Change Password",
        description="Change user password (authenticated)",
        request=PasswordChangeSerializer,
        responses={
            200: "Password changed successfully",
            400: "Invalid current password",
        },
    )
)
class PasswordChangeView(APIView):
    """
    Change password for authenticated user
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle password change"""
        serializer = PasswordChangeSerializer(
            data=request.data, context={"user": request.user}
        )
        serializer.is_valid(raise_exception=True)

        new_password = serializer.validated_data["new_password"]

        with transaction.atomic():
            request.user.set_password(new_password)
            request.user.save()

            # Log password change
            ActivityLog.objects.create(
                user=request.user,
                activity_type=ActivityLog.ActivityType.PASSWORD_CHANGE,
                description="Password changed",
                ip_address=get_client_ip(request),
                user_agent=get_user_agent(request),
            )

        return Response(
            {"message": "Password changed successfully"}, status=status.HTTP_200_OK
        )


@extend_schema_view(
    post=extend_schema(
        summary="Change Email",
        description="Change user email address",
        request=EmailChangeSerializer,
        responses={
            200: "Email change initiated",
            400: "Invalid email",
        },
    )
)
class EmailChangeView(APIView):
    """
    Change email address with verification
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [UserRateThrottle]

    def post(self, request: Request) -> Response:
        """Handle email change request"""
        serializer = EmailChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        new_email = serializer.validated_data["new_email"]

        # Generate verification token
        token = secrets.token_urlsafe(32)
        verification_key = f"email_change:{request.user.id}:{token}"

        # Store in cache with new email
        cache.set(verification_key, new_email, 3600)  # 1 hour

        # Send verification email
        verification_url = f"{settings.FRONTEND_URL}/verify-email-change/{token}/"

        send_mail(
            subject="Verify your new email address",
            message=f"Please verify your new email by clicking: {verification_url}",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[new_email],
            fail_silently=False,
        )

        # Log email change request
        ActivityLog.objects.create(
            user=request.user,
            activity_type=ActivityLog.ActivityType.EMAIL_CHANGE_REQUEST,
            description=f"Email change requested to {new_email}",
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        return Response(
            {"message": "Verification email sent to new address"},
            status=status.HTTP_200_OK,
        )

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from django.db import models
from .models import (
    Achievement,
    ActivityLog,
    Certification,
    Connection,
    Department,
    Education,
    Experience,
    Follow,
    Language,
    Message,
    Network,
    NetworkMembership,
    Notification,
    ProfileStats,
    ProfileView,
    Project,
    ProjectImage,
    Publication,
    Recommendation,
    Resume,
    Role,
    SavedSearch,
    Skill,
    SkillEndorsement,
    SocialLink,
    Task,
    TaskComment,
    UserFile,
    UserProfile,
    UserRole,
    Volunteer,
)

User = get_user_model()


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        max_length=150, required=True, help_text=_("Username to authenticate with")
    )
    password = serializers.CharField(
        max_length=128,
        required=True,
        write_only=True,
        help_text=_("Password for authentication"),
    )

    def validate(self, attrs):
        return attrs


class SocialLinkSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = SocialLink
        fields = ["id", "platform", "url", "title", "is_visible"]
        extra_kwargs = {
            "id": {"read_only": True},
        }


class ExperienceSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Experience
        fields = [
            "id",
            "title",
            "company",
            "company_url",
            "location",
            "start_date",
            "end_date",
            "is_current",
            "description",
            "skills",
            "achievements",
            "type",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }

    def validate(self, attrs):
        if attrs.get("end_date") and attrs.get("start_date"):
            if attrs["end_date"] < attrs["start_date"]:
                raise serializers.ValidationError(
                    _("End date cannot be before start date")
                )
        return attrs


class EducationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Education
        fields = [
            "id",
            "institution",
            "degree",
            "field_of_study",
            "start_date",
            "end_date",
            "is_current",
            "gpa",
            "description",
            "achievements",
            "activities",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class CertificationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Certification
        fields = [
            "id",
            "name",
            "issuer",
            "issue_date",
            "expiration_date",
            "credential_id",
            "credential_url",
            "description",
            "skills",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class ProjectImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProjectImage
        fields = ["id", "image", "caption", "order"]


class ProjectSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    images = ProjectImageSerializer(many=True, read_only=True)

    class Meta:
        model = Project
        fields = [
            "id",
            "title",
            "description",
            "thumbnail",
            "images",
            "start_date",
            "end_date",
            "is_current",
            "url",
            "github_url",
            "technologies",
            "role",
            "team_size",
            "category",
            "status",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class SkillEndorsementSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    endorser_name = serializers.CharField(
        source="endorser.get_full_name", read_only=True
    )
    endorser_avatar = serializers.ImageField(
        source="endorser.profile_picture", read_only=True
    )
    endorser_title = serializers.CharField(source="endorser.headline", read_only=True)

    class Meta:
        model = SkillEndorsement
        fields = [
            "id",
            "endorser",
            "endorser_name",
            "endorser_avatar",
            "endorser_title",
            "message",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "endorser": {"read_only": True},
            "created_at": {"read_only": True},
        }


class SkillSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    is_endorsed = serializers.BooleanField(read_only=True)
    endorsements = SkillEndorsementSerializer(many=True, read_only=True)
    endorsement_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Skill
        fields = [
            "id",
            "name",
            "category",
            "level",
            "years_of_experience",
            "is_endorsed",
            "endorsements",
            "endorsement_count",
            "last_used",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class LanguageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Language
        fields = ["id", "name", "code", "proficiency", "certifications", "created_at"]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }


class AchievementSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Achievement
        fields = [
            "id",
            "title",
            "description",
            "issuer",
            "date",
            "category",
            "url",
            "image",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }


class PublicationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Publication
        fields = [
            "id",
            "title",
            "description",
            "publisher",
            "publication_date",
            "url",
            "authors",
            "category",
            "tags",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }


class VolunteerSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Volunteer
        fields = [
            "id",
            "organization",
            "role",
            "cause",
            "start_date",
            "end_date",
            "is_current",
            "description",
            "skills",
            "hours_contributed",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }


class UserFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFile
        fields = [
            "id",
            "file",
            "name",
            "file_type",
            "description",
            "is_public",
            "size",
            "created_at",
        ]
        extra_kwargs = {
            "size": {"read_only": True},
            "created_at": {"read_only": True},
        }


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "activity_type",
            "description",
            "ip_address",
            "user_agent",
            "location",
            "metadata",
            "created_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }


class ProfileStatsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProfileStats
        fields = [
            "profile_views",
            "profile_views_this_week",
            "profile_views_this_month",
            "connections_count",
            "endorsements_count",
            "project_views",
            "search_appearances",
            "last_updated",
        ]
        read_only_fields = fields


class UserProfileSerializer(serializers.ModelSerializer):
    social_links = SocialLinkSerializer(
        source="user.social_links", many=True, read_only=True
    )
    experiences = ExperienceSerializer(
        source="user.experiences", many=True, read_only=True
    )
    educations = EducationSerializer(
        source="user.educations", many=True, read_only=True
    )
    certifications = CertificationSerializer(
        source="user.certifications", many=True, read_only=True
    )
    projects = ProjectSerializer(source="user.projects", many=True, read_only=True)
    skills = SkillSerializer(source="user.skills", many=True, read_only=True)
    languages = LanguageSerializer(source="user.languages", many=True, read_only=True)
    achievements = AchievementSerializer(
        source="user.achievements", many=True, read_only=True
    )
    publications = PublicationSerializer(
        source="user.publications", many=True, read_only=True
    )
    volunteer_work = VolunteerSerializer(
        source="user.volunteer_work", many=True, read_only=True
    )
    files = UserFileSerializer(source="user.files", many=True, read_only=True)
    activity_logs = ActivityLogSerializer(
        source="user.activity_logs", many=True, read_only=True
    )
    stats = ProfileStatsSerializer(source="user.stats", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "display_name",
            "cover_image",
            "website",
            "interests",
            "profile_visibility",
            "show_contact_info",
            "show_experience",
            "show_education",
            "show_skills",
            "show_projects",
            "show_achievements",
            "show_publications",
            "show_volunteer",
            "allow_endorsements",
            "allow_messages",
            "allow_connections",
            "show_last_seen",
            "searchable",
            "email_notifications",
            "push_notifications",
            "theme",
            "language",
            "date_format",
            "time_format",
            "two_factor_enabled",
            "login_alerts",
            "data_processing",
            "analytics_tracking",
            "personalized_ads",
            "third_party_sharing",
            "location_tracking",
            "activity_tracking",
            "social_links",
            "experiences",
            "educations",
            "certifications",
            "projects",
            "skills",
            "languages",
            "achievements",
            "publications",
            "volunteer_work",
            "files",
            "activity_logs",
            "stats",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer(read_only=True)
    full_name = serializers.CharField(source="get_full_name", read_only=True)
    connections_count = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    following_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "headline",
            "current_position",
            "current_company",
            "location",
            "timezone",
            "status",
            "is_online",
            "bio",
            "date_of_birth",
            "profile_picture",
            "phone_number",
            "last_login",
            "date_joined",
            "is_verified",
            "last_activity",
            "profile",
            "connections_count",
            "followers_count",
            "following_count",
        ]
        read_only_fields = [
            "id",
            "last_login",
            "date_joined",
            "last_activity",
            "full_name",
            "connections_count",
            "followers_count",
            "following_count",
        ]

    def get_connections_count(self, obj):
        return Connection.objects.filter(
            models.Q(from_user=obj) | models.Q(to_user=obj),
            status=Connection.ConnectionStatus.ACCEPTED,
        ).count()

    def get_followers_count(self, obj):
        return obj.followers.count()

    def get_following_count(self, obj):
        return obj.following.count()


class UserBasicSerializer(serializers.ModelSerializer):
    """Lightweight user serializer for lists and references."""

    full_name = serializers.CharField(source="get_full_name", read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "first_name",
            "last_name",
            "full_name",
            "headline",
            "current_position",
            "current_company",
            "profile_picture",
            "is_online",
            "status",
        ]
        read_only_fields = fields


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text=_("JWT access token"))
    refresh = serializers.CharField(help_text=_("JWT refresh token"))
    user = UserSerializer(help_text=_("User details"))


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        required=True, help_text=_("JWT refresh token to get a new access token")
    )


class VerifySerializer(serializers.Serializer):
    access = serializers.CharField(
        required=True, help_text=_("JWT access token to verify")
    )


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={"input_type": "password"},
        help_text=_("Password must be at least 8 characters"),
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "headline",
            "current_position",
            "current_company",
            "location",
        ]
        extra_kwargs = {
            "username": {"required": True},
            "email": {"required": True},
            "first_name": {"required": False},
            "last_name": {"required": False},
        }

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError(_("Email already exists"))
        return value.lower()

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(_("Username already exists"))
        return value

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data["email"],
            password=validated_data["password"],
            first_name=validated_data.get("first_name", ""),
            last_name=validated_data.get("last_name", ""),
            headline=validated_data.get("headline", ""),
            current_position=validated_data.get("current_position", ""),
            current_company=validated_data.get("current_company", ""),
            location=validated_data.get("location", ""),
        )
        return user


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(
        required=True, help_text=_("Email address to send password reset link")
    )


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(required=True, help_text=_("Password reset token"))
    uid = serializers.CharField(
        required=True, help_text=_("User identifier for password reset")
    )
    password = serializers.CharField(
        write_only=True,
        required=True,
        min_length=8,
        style={"input_type": "password"},
        help_text=_("New password (minimum 8 characters)"),
    )

    def validate_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ConnectionSerializer(serializers.ModelSerializer):
    from_user = UserBasicSerializer(read_only=True)
    to_user = UserBasicSerializer(read_only=True)

    class Meta:
        model = Connection
        fields = [
            "id",
            "from_user",
            "to_user",
            "status",
            "message",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class ConnectionRequestSerializer(serializers.Serializer):
    to_user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)


class FollowSerializer(serializers.ModelSerializer):
    follower = UserBasicSerializer(read_only=True)
    following = UserBasicSerializer(read_only=True)

    class Meta:
        model = Follow
        fields = ["id", "follower", "following", "created_at"]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }


class ProfileViewSerializer(serializers.ModelSerializer):
    viewer = UserBasicSerializer(read_only=True)

    class Meta:
        model = ProfileView
        fields = ["id", "viewer", "ip_address", "user_agent", "referrer", "created_at"]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id",
            "name",
            "description",
            "is_system_role",
            "permissions",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class UserRoleSerializer(serializers.ModelSerializer):
    role = RoleSerializer(read_only=True)
    assigned_by = UserBasicSerializer(read_only=True)

    class Meta:
        model = UserRole
        fields = ["id", "role", "assigned_by", "assigned_at", "expires_at", "is_active"]
        extra_kwargs = {
            "assigned_at": {"read_only": True},
        }


class DepartmentSerializer(serializers.ModelSerializer):
    head = UserBasicSerializer(read_only=True)
    sub_departments = serializers.SerializerMethodField()
    members_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "name",
            "description",
            "parent",
            "head",
            "sub_departments",
            "members_count",
            "created_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }

    def get_sub_departments(self, obj):
        return DepartmentSerializer(obj.sub_departments.all(), many=True).data

    def get_members_count(self, obj):
        return obj.members.count()


class TaskCommentSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)

    class Meta:
        model = TaskComment
        fields = ["id", "user", "content", "created_at"]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }


class TaskSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    assignee = UserBasicSerializer(read_only=True)
    created_by = UserBasicSerializer(read_only=True)
    project = ProjectSerializer(read_only=True)
    comments = TaskCommentSerializer(many=True, read_only=True)
    watchers = UserBasicSerializer(many=True, read_only=True)

    class Meta:
        model = Task
        fields = [
            "id",
            "title",
            "description",
            "assignee",
            "created_by",
            "project",
            "status",
            "priority",
            "due_date",
            "completed_at",
            "estimated_hours",
            "actual_hours",
            "tags",
            "watchers",
            "comments",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class ResumeSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Resume
        fields = [
            "id",
            "title",
            "template",
            "content",
            "file",
            "status",
            "is_default",
            "download_count",
            "last_downloaded",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "download_count": {"read_only": True},
            "last_downloaded": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class NetworkSerializer(serializers.ModelSerializer):
    created_by = UserBasicSerializer(read_only=True)
    admins = UserBasicSerializer(many=True, read_only=True)

    class Meta:
        model = Network
        fields = [
            "id",
            "name",
            "description",
            "industry",
            "location",
            "website",
            "logo",
            "is_verified",
            "is_public",
            "member_count",
            "created_by",
            "admins",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "member_count": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class NetworkMembershipSerializer(serializers.ModelSerializer):
    user = UserBasicSerializer(read_only=True)
    network = NetworkSerializer(read_only=True)

    class Meta:
        model = NetworkMembership
        fields = ["id", "user", "network", "status", "role", "joined_at", "updated_at"]
        extra_kwargs = {
            "joined_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class RecommendationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    recommender = UserBasicSerializer(read_only=True)
    recommendee = UserBasicSerializer(read_only=True)

    class Meta:
        model = Recommendation
        fields = [
            "id",
            "recommender",
            "recommendee",
            "relationship_type",
            "title",
            "content",
            "skills_highlighted",
            "is_public",
            "is_featured",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
            "updated_at": {"read_only": True},
        }


class MessageSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    sender = UserBasicSerializer(read_only=True)
    recipient = UserBasicSerializer(read_only=True)
    replies = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            "id",
            "sender",
            "recipient",
            "subject",
            "content",
            "status",
            "attachment",
            "parent",
            "replies",
            "read_at",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }

    def get_replies(self, obj):
        if obj.replies.exists():
            return MessageSerializer(obj.replies.all(), many=True).data
        return []


class NotificationSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(read_only=True)
    sender = UserBasicSerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "sender",
            "notification_type",
            "title",
            "message",
            "data",
            "is_read",
            "read_at",
            "created_at",
        ]
        extra_kwargs = {
            "id": {"read_only": True},
            "created_at": {"read_only": True},
        }


class SavedSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = SavedSearch
        fields = [
            "id",
            "name",
            "query_params",
            "alert_enabled",
            "last_run",
            "created_at",
        ]
        extra_kwargs = {
            "created_at": {"read_only": True},
        }


# Search and filtering serializers
class ProfileSearchSerializer(serializers.Serializer):
    query = serializers.CharField(required=False, allow_blank=True)
    skills = serializers.ListField(
        child=serializers.CharField(), required=False, allow_empty=True
    )
    location = serializers.CharField(required=False, allow_blank=True)
    company = serializers.CharField(required=False, allow_blank=True)
    experience = serializers.CharField(required=False, allow_blank=True)
    education = serializers.CharField(required=False, allow_blank=True)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    limit = serializers.IntegerField(
        required=False, min_value=1, max_value=100, default=20
    )
    sort_by = serializers.ChoiceField(
        choices=["relevance", "name", "experience", "connections"],
        required=False,
        default="relevance",
    )
    sort_order = serializers.ChoiceField(
        choices=["asc", "desc"], required=False, default="desc"
    )


class SkillEndorseSerializer(serializers.Serializer):
    skill_id = serializers.UUIDField(required=True)
    message = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BulkOperationSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=100
    )
    action = serializers.CharField(max_length=50)


# Profile update serializers
class ProfileBasicInfoSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False)
    display_name = serializers.CharField(max_length=100, required=False)
    headline = serializers.CharField(max_length=220, required=False)
    bio = serializers.CharField(max_length=500, required=False)
    current_position = serializers.CharField(max_length=100, required=False)
    current_company = serializers.CharField(max_length=100, required=False)
    location = serializers.CharField(max_length=100, required=False)


class ContactInfoSerializer(serializers.Serializer):
    email = serializers.EmailField()
    phone = serializers.CharField(max_length=15, required=False, allow_blank=True)
    location = serializers.CharField(max_length=100, required=False, allow_blank=True)
    timezone = serializers.CharField(max_length=50, required=False, allow_blank=True)
    website = serializers.URLField(required=False, allow_blank=True)
    social_links = SocialLinkSerializer(many=True, required=False)


class ProfileSettingsSerializer(serializers.Serializer):
    profile_visibility = serializers.ChoiceField(
        choices=UserProfile.ProfileVisibility.choices
    )
    show_contact_info = serializers.BooleanField()
    show_experience = serializers.BooleanField()
    show_education = serializers.BooleanField()
    show_skills = serializers.BooleanField()
    show_projects = serializers.BooleanField()
    show_achievements = serializers.BooleanField()
    show_publications = serializers.BooleanField()
    show_volunteer = serializers.BooleanField()
    allow_endorsements = serializers.BooleanField()
    allow_messages = serializers.BooleanField()
    allow_connections = serializers.BooleanField()
    show_last_seen = serializers.BooleanField()
    searchable = serializers.BooleanField()
    email_notifications = serializers.DictField()
    push_notifications = serializers.DictField()


class AccountSettingsSerializer(serializers.Serializer):
    theme = serializers.ChoiceField(
        choices=[("light", "Light"), ("dark", "Dark"), ("system", "System")]
    )
    language = serializers.CharField(max_length=10)
    timezone = serializers.CharField(max_length=50)
    date_format = serializers.ChoiceField(
        choices=[
            ("MM/DD/YYYY", "MM/DD/YYYY"),
            ("DD/MM/YYYY", "DD/MM/YYYY"),
            ("YYYY-MM-DD", "YYYY-MM-DD"),
        ]
    )
    time_format = serializers.ChoiceField(choices=[("12h", "12h"), ("24h", "24h")])
    two_factor_enabled = serializers.BooleanField()
    login_alerts = serializers.BooleanField()


class PrivacySettingsSerializer(serializers.Serializer):
    data_processing = serializers.BooleanField()
    analytics_tracking = serializers.BooleanField()
    personalized_ads = serializers.BooleanField()
    third_party_sharing = serializers.BooleanField()
    location_tracking = serializers.BooleanField()
    activity_tracking = serializers.BooleanField()


class ProfileFormDataSerializer(serializers.Serializer):
    basic_info = ProfileBasicInfoSerializer()
    contact_info = ContactInfoSerializer()
    experiences = ExperienceSerializer(many=True, required=False)
    educations = EducationSerializer(many=True, required=False)
    certifications = CertificationSerializer(many=True, required=False)
    projects = ProjectSerializer(many=True, required=False)
    skills = SkillSerializer(many=True, required=False)
    languages = LanguageSerializer(many=True, required=False)
    achievements = AchievementSerializer(many=True, required=False)
    publications = PublicationSerializer(many=True, required=False)
    volunteer_work = VolunteerSerializer(many=True, required=False)
    interests = serializers.ListField(
        child=serializers.CharField(max_length=100), required=False
    )


# Response serializers for API documentation
class ProfileResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = UserSerializer()
    message = serializers.CharField(required=False)


class ProfileListResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    data = UserSerializer(many=True)
    pagination = serializers.DictField()
    message = serializers.CharField(required=False)


# Additional utility serializers
class StatusUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=User.UserStatus.choices)


class OnlineStatusSerializer(serializers.Serializer):
    is_online = serializers.BooleanField()
    last_seen = serializers.DateTimeField(read_only=True)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError(_("Passwords do not match"))
        return attrs

    def validate_new_password(self, value):
        try:
            password_validation.validate_password(value)
        except ValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class EmailChangeSerializer(serializers.Serializer):
    new_email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_new_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError(_("Email already exists"))
        return value.lower()


class UsernameChangeSerializer(serializers.Serializer):
    new_username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True)

    def validate_new_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError(_("Username already exists"))
        return value


class ProfilePictureUploadSerializer(serializers.Serializer):
    profile_picture = serializers.ImageField()


class CoverImageUploadSerializer(serializers.Serializer):
    cover_image = serializers.ImageField()


class FileUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserFile
        fields = ["file", "name", "file_type", "description", "is_public"]

    def validate_file(self, value):
        # Limit file size to 10MB
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError(_("File size cannot exceed 10MB"))
        return value


class ProfileAnalyticsSerializer(serializers.Serializer):
    profile_views_data = serializers.DictField()
    connection_growth = serializers.DictField()
    skill_endorsements_data = serializers.DictField()
    search_appearances_data = serializers.DictField()
    top_viewers = UserBasicSerializer(many=True)
    recent_activities = ActivityLogSerializer(many=True)

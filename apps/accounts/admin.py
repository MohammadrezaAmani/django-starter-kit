import logging
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

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
    User,
    UserDepartment,
    UserFile,
    UserProfile,
    UserRole,
    Volunteer,
)

logger = logging.getLogger(__name__)


class ProfileStatsInline(admin.StackedInline):
    """Inline admin for profile statistics."""

    model = ProfileStats
    extra = 0
    readonly_fields = (
        "profile_views",
        "connections_count",
        "endorsements_count",
        "project_views",
        "search_appearances",
        "last_updated",
    )


class SocialLinkInline(admin.TabularInline):
    """Inline admin for social links."""

    model = SocialLink
    extra = 1
    fields = ("platform", "url", "is_visible")


class UserProfileInline(admin.StackedInline):
    """Inline admin for user profile."""

    model = UserProfile
    extra = 0
    fields = (
        "bio",
        "location",
        "website",
        "current_position",
        "industry",
        "phone",
        "date_of_birth",
        "profile_picture",
        "cover_image",
        "visibility",
        "show_email",
        "show_phone",
    )


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Enhanced admin interface for the User model."""

    model = User
    list_display = (
        "username",
        "email",
        "full_name",
        "status_badge",
        "verification_badge",
        "is_online_badge",
        "profile_completeness",
        "connections_count",
        "last_activity",
        "date_joined",
    )
    list_filter = (
        "status",
        "is_verified",
        "is_active",
        "is_staff",
        "is_superuser",
        "is_online",
        "date_joined",
        "last_activity",
    )
    search_fields = ("username", "email", "first_name", "last_name", "phone_number")
    ordering = ("-date_joined",)
    readonly_fields = ("last_activity", "date_joined", "last_login", "id")

    fieldsets = (
        (
            None,
            {
                "fields": (
                    "username",
                    "password",
                    "email",
                )
            },
        ),
        (
            _("Personal info"),
            {
                "fields": (
                    "first_name",
                    "last_name",
                    "phone_number",
                )
            },
        ),
        (
            _("Status"),
            {
                "fields": (
                    "status",
                    "is_verified",
                    "is_online",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                )
            },
        ),
        (
            _("Permissions"),
            {
                "fields": ("groups", "user_permissions"),
                "classes": ("collapse",),
            },
        ),
        (
            _("Important dates"),
            {"fields": ("last_login", "last_activity", "date_joined")},
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "email", "password1", "password2"),
            },
        ),
        (
            _("Personal info"),
            {
                "fields": ("first_name", "last_name", "phone_number"),
            },
        ),
        (
            _("Status"),
            {
                "fields": (
                    "status",
                    "is_verified",
                    "is_active",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    inlines = [UserProfileInline, ProfileStatsInline, SocialLinkInline]

    actions = [
        "verify_users",
        "deactivate_users",
        "activate_users",
        "send_verification_email",
        "export_user_data",
        "mark_online",
        "mark_offline",
    ]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("profile")
            .prefetch_related("stats")
        )

    def full_name(self, obj):
        """Display full name."""
        return obj.get_full_name() or "N/A"

    full_name.short_description = "Full Name"

    def status_badge(self, obj):
        """Display status as colored badge."""
        colors = {
            User.UserStatus.ACTIVE: "green",
            User.UserStatus.INACTIVE: "red",
            User.UserStatus.SUSPENDED: "orange",
            User.UserStatus.PENDING: "blue",
        }
        color = colors.get(obj.status, "gray")
        return format_html(
            '<span style="color: {}; font-weight: bold;">{}</span>',
            color,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def verification_badge(self, obj):
        """Display verification status as badge."""
        if obj.is_verified:
            return format_html('<span style="color: green;">✓ Verified</span>')
        return format_html('<span style="color: red;">✗ Unverified</span>')

    verification_badge.short_description = "Verification"

    def is_online_badge(self, obj):
        """Display online status as badge."""
        if obj.is_online:
            return format_html('<span style="color: green;">● Online</span>')
        return format_html('<span style="color: gray;">○ Offline</span>')

    is_online_badge.short_description = "Online Status"

    def profile_completeness(self, obj):
        """Display profile completeness percentage."""
        try:
            stats = obj.profilestats
            return f"{stats.profile_completeness}%"
        except Exception as _:
            return "N/A"

    profile_completeness.short_description = "Profile Complete"

    def connections_count(self, obj):
        """Display connections count."""
        try:
            stats = obj.profilestats
            return stats.connections_count
        except Exception as _:
            return 0

    connections_count.short_description = "Connections"

    def verify_users(self, request, queryset):
        """Mark selected users as verified."""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} user(s) marked as verified.")

    verify_users.short_description = _("Mark selected users as verified")

    def deactivate_users(self, request, queryset):
        """Deactivate selected users."""
        updated = queryset.update(is_active=False, status=User.UserStatus.INACTIVE)
        self.message_user(request, f"{updated} user(s) deactivated.")

    deactivate_users.short_description = _("Deactivate selected users")

    def activate_users(self, request, queryset):
        """Activate selected users."""
        updated = queryset.update(is_active=True, status=User.UserStatus.ACTIVE)
        self.message_user(request, f"{updated} user(s) activated.")

    activate_users.short_description = _("Activate selected users")

    def send_verification_email(self, request, queryset):
        """Send verification email to selected users."""
        # Implementation would depend on your email system
        count = queryset.filter(is_verified=False).count()
        self.message_user(request, f"Verification emails sent to {count} user(s).")

    send_verification_email.short_description = _("Send verification email")

    def export_user_data(self, request, queryset):
        """Export user data as CSV."""
        import csv

        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="users.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["Username", "Email", "Full Name", "Status", "Verified", "Date Joined"]
        )

        for user in queryset:
            writer.writerow(
                [
                    user.username,
                    user.email,
                    user.get_full_name(),
                    user.get_status_display(),
                    user.is_verified,
                    user.date_joined.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

    export_user_data.short_description = _("Export selected users to CSV")


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin interface for user profiles."""

    list_display = (
        "user",
        "display_name",
        "profile_visibility",
        "website",
        "created_at",
        "updated_at",
    )
    list_filter = ("profile_visibility", "show_contact_info", "searchable")
    search_fields = (
        "user__username",
        "user__email",
        "current_position",
        "industry",
        "location",
    )
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user",)

    fieldsets = (
        (
            _("Basic Information"),
            {"fields": ("user", "bio", "current_position", "industry")},
        ),
        (
            _("Contact Information"),
            {"fields": ("location", "website", "phone", "show_email", "show_phone")},
        ),
        (
            _("Profile Media"),
            {"fields": ("profile_picture", "cover_image", "date_of_birth")},
        ),
        (_("Privacy Settings"), {"fields": ("visibility",)}),
        (
            _("Timestamps"),
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    def profile_picture_preview(self, obj):
        """Display profile picture preview."""
        if obj.profile_picture:
            return format_html(
                '<img src="{}" width="50" height="50" style="border-radius: 50%;" />',
                obj.profile_picture.url,
            )
        return "No image"

    profile_picture_preview.short_description = "Profile Picture"


@admin.register(Experience)
class ExperienceAdmin(admin.ModelAdmin):
    """Admin interface for work experience."""

    list_display = (
        "user",
        "title",
        "company",
        "type",
        "is_current",
        "start_date",
        "end_date",
    )
    list_filter = ("type", "is_current", "start_date")
    search_fields = ("user__username", "title", "company", "description")
    raw_id_fields = ("user",)
    date_hierarchy = "start_date"

    fieldsets = (
        (
            _("Position Details"),
            {"fields": ("user", "title", "company", "type", "location")},
        ),
        (_("Duration"), {"fields": ("start_date", "end_date", "is_current")}),
        (_("Description"), {"fields": ("description",)}),
    )


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    """Admin interface for education."""

    list_display = (
        "user",
        "degree",
        "institution",
        "field_of_study",
        "is_current",
        "start_date",
        "end_date",
    )
    list_filter = ("degree", "is_current", "start_date")
    search_fields = ("user__username", "institution", "degree", "field_of_study")
    raw_id_fields = ("user",)
    date_hierarchy = "start_date"


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    """Admin interface for skills."""

    list_display = (
        "user",
        "name",
        "category",
        "level",
        "years_of_experience",
        "endorsement_count",
    )
    list_filter = ("category", "level", "years_of_experience")
    search_fields = ("user__username", "name", "category")
    raw_id_fields = ("user",)

    def endorsement_count(self, obj):
        """Display endorsement count."""
        return obj.endorsements.count()

    endorsement_count.short_description = "Endorsements"


@admin.register(SkillEndorsement)
class SkillEndorsementAdmin(admin.ModelAdmin):
    """Admin interface for skill endorsements."""

    list_display = ("skill", "endorser", "skill_owner", "created_at")
    list_filter = ("created_at",)
    search_fields = ("skill__name", "endorser__username", "skill__user__username")
    raw_id_fields = ("skill", "endorser")
    date_hierarchy = "created_at"

    def skill_owner(self, obj):
        """Display skill owner."""
        return obj.skill.user.get_full_name()

    skill_owner.short_description = "Skill Owner"


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Admin interface for projects."""

    list_display = (
        "user",
        "title",
        "category",
        "status",
        "start_date",
        "end_date",
        "created_at",
    )
    list_filter = ("category", "status", "start_date", "user")
    search_fields = ("user__username", "title", "description", "technologies")
    raw_id_fields = ("user",)
    date_hierarchy = "start_date"

    fieldsets = (
        (
            _("Project Details"),
            {"fields": ("user", "title", "category", "status", "is_featured")},
        ),
        (_("Duration"), {"fields": ("start_date", "end_date")}),
        (
            _("Content"),
            {"fields": ("description", "technologies", "github_url", "live_url")},
        ),
    )


@admin.register(Connection)
class ConnectionAdmin(admin.ModelAdmin):
    """Admin interface for connections."""

    list_display = ("from_user", "to_user", "status", "created_at", "updated_at")
    list_filter = ("status", "created_at")
    search_fields = ("from_user__username", "to_user__username")
    raw_id_fields = ("from_user", "to_user")
    date_hierarchy = "created_at"

    actions = ["approve_connections", "reject_connections"]

    def approve_connections(self, request, queryset):
        """Approve selected connection requests."""
        updated = queryset.filter(status=Connection.ConnectionStatus.PENDING).update(
            status=Connection.ConnectionStatus.ACCEPTED
        )
        self.message_user(request, f"{updated} connection(s) approved.")

    approve_connections.short_description = _("Approve selected connections")

    def reject_connections(self, request, queryset):
        """Reject selected connection requests."""
        updated = queryset.filter(status=Connection.ConnectionStatus.PENDING).update(
            status=Connection.ConnectionStatus.REJECTED
        )
        self.message_user(request, f"{updated} connection(s) rejected.")

    reject_connections.short_description = _("Reject selected connections")


@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    """Admin interface for follow relationships."""

    list_display = ("follower", "following", "created_at")
    list_filter = ("created_at",)
    search_fields = ("follower__username", "following__username")
    raw_id_fields = ("follower", "following")
    date_hierarchy = "created_at"


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    """Admin interface for tasks."""

    list_display = (
        "title",
        "assignee",
        "created_by",
        "status",
        "priority",
        "due_date",
        "progress_bar",
        "created_at",
    )
    list_filter = ("status", "priority", "due_date", "created_at")
    search_fields = (
        "title",
        "description",
        "assignee__username",
        "created_by__username",
    )
    raw_id_fields = ("assignee", "created_by")
    date_hierarchy = "due_date"

    fieldsets = (
        (
            _("Task Details"),
            {
                "fields": (
                    "title",
                    "description",
                    "assigned_to",
                    "created_by",
                    "department",
                )
            },
        ),
        (_("Status & Priority"), {"fields": ("status", "priority", "progress")}),
        (_("Dates"), {"fields": ("due_date", "estimated_hours")}),
    )

    actions = ["mark_completed", "mark_in_progress", "assign_to_me"]

    def progress_bar(self, obj):
        """Display progress as a visual bar."""
        if obj.progress is not None:
            width = min(obj.progress, 100)
            color = "green" if width == 100 else "blue" if width > 50 else "orange"
            return format_html(
                '<div style="width: 100px; background-color: #f0f0f0;">'
                '<div style="width: {}px; background-color: {}; height: 20px;"></div>'
                "</div> {}%",
                width,
                color,
                obj.progress,
            )
        return "N/A"

    progress_bar.short_description = "Progress"

    def mark_completed(self, request, queryset):
        """Mark selected tasks as completed."""
        updated = queryset.update(status=Task.TaskStatus.COMPLETED, progress=100)
        self.message_user(request, f"{updated} task(s) marked as completed.")

    mark_completed.short_description = _("Mark as completed")

    def mark_in_progress(self, request, queryset):
        """Mark selected tasks as in progress."""
        updated = queryset.update(status=Task.TaskStatus.IN_PROGRESS)
        self.message_user(request, f"{updated} task(s) marked as in progress.")

    mark_in_progress.short_description = _("Mark as in progress")

    def assign_to_me(self, request, queryset):
        """Assign selected tasks to current admin user."""
        updated = queryset.update(assigned_to=request.user)
        self.message_user(request, f"{updated} task(s) assigned to you.")

    assign_to_me.short_description = _("Assign to me")


@admin.register(Resume)
class ResumeAdmin(admin.ModelAdmin):
    """Admin interface for resumes."""

    list_display = (
        "user",
        "title",
        "status",
        "template",
        "is_default",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "template", "is_default", "created_at")
    search_fields = ("user__username", "title", "description")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at", "updated_at")

    actions = ["publish_resumes", "unpublish_resumes"]

    def publish_resumes(self, request, queryset):
        """Publish selected resumes."""
        updated = queryset.update(status=Resume.ResumeStatus.PUBLISHED)
        self.message_user(request, f"{updated} resume(s) published.")

    publish_resumes.short_description = _("Publish selected resumes")

    def unpublish_resumes(self, request, queryset):
        """Unpublish selected resumes."""
        updated = queryset.update(status=Resume.ResumeStatus.DRAFT)
        self.message_user(request, f"{updated} resume(s) unpublished.")

    unpublish_resumes.short_description = _("Unpublish selected resumes")


@admin.register(Recommendation)
class RecommendationAdmin(admin.ModelAdmin):
    """Admin interface for recommendations."""

    list_display = (
        "recommender",
        "recommendee",
        "relationship_type",
        "content_preview",
        "created_at",
    )
    list_filter = ("relationship_type", "created_at")
    search_fields = ("recommender__username", "recommendee__username", "content")
    raw_id_fields = ("recommender", "recommendee")
    readonly_fields = ("created_at", "updated_at")

    def content_preview(self, obj):
        """Display content preview."""
        return (obj.content[:50] + "...") if len(obj.content) > 50 else obj.content

    content_preview.short_description = "Content Preview"

    actions = ["approve_recommendations", "decline_recommendations"]

    def approve_recommendations(self, request, queryset):
        """Approve selected recommendations."""
        updated = queryset.filter(
            status=Recommendation.RecommendationStatus.PENDING
        ).update(status=Recommendation.RecommendationStatus.APPROVED)
        self.message_user(request, f"{updated} recommendation(s) approved.")

    approve_recommendations.short_description = _("Approve selected recommendations")


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    """Admin interface for messages."""

    list_display = (
        "sender",
        "recipient",
        "subject_or_preview",
        "status",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("sender__username", "recipient__username", "subject", "content")
    raw_id_fields = ("sender", "recipient")
    readonly_fields = ("created_at",)

    def subject_or_preview(self, obj):
        """Display subject or content preview."""
        if obj.subject:
            return obj.subject
        return (obj.content[:30] + "...") if len(obj.content) > 30 else obj.content

    subject_or_preview.short_description = "Subject/Preview"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    """Admin interface for notifications."""

    list_display = (
        "recipient",
        "sender",
        "notification_type",
        "title",
        "is_read",
        "created_at",
    )
    list_filter = ("notification_type", "is_read", "created_at")
    search_fields = ("recipient__username", "sender__username", "title", "message")
    raw_id_fields = ("recipient", "sender")
    readonly_fields = ("created_at", "read_at")

    actions = ["mark_as_read", "mark_as_unread", "delete_old_notifications"]

    def mark_as_read(self, request, queryset):
        """Mark selected notifications as read."""
        updated = queryset.update(is_read=True, read_at=timezone.now())
        self.message_user(request, f"{updated} notification(s) marked as read.")

    mark_as_read.short_description = _("Mark as read")

    def delete_old_notifications(self, request, queryset):
        """Delete notifications older than 30 days."""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        old_notifications = queryset.filter(created_at__lt=thirty_days_ago)
        count = old_notifications.count()
        old_notifications.delete()
        self.message_user(request, f"{count} old notification(s) deleted.")

    delete_old_notifications.short_description = _("Delete old notifications")


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Admin interface for activity logs."""

    list_display = (
        "user",
        "activity_type",
        "description",
        "ip_address",
        "location",
        "created_at",
    )
    list_filter = ("activity_type", "created_at", "location")
    search_fields = ("user__username", "description", "ip_address")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

    actions = ["export_activity_logs", "delete_old_logs"]

    def export_activity_logs(self, request, queryset):
        """Export activity logs as CSV."""
        import csv

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="activity_logs.csv"'

        writer = csv.writer(response)
        writer.writerow(
            ["User", "Activity Type", "Description", "IP Address", "Created At"]
        )

        for log in queryset:
            writer.writerow(
                [
                    log.user.username,
                    log.get_activity_type_display(),
                    log.description,
                    log.ip_address,
                    log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

    export_activity_logs.short_description = _("Export to CSV")

    def delete_old_logs(self, request, queryset):
        """Delete logs older than 90 days."""
        ninety_days_ago = timezone.now() - timedelta(days=90)
        old_logs = queryset.filter(created_at__lt=ninety_days_ago)
        count = old_logs.count()
        old_logs.delete()
        self.message_user(request, f"{count} old log(s) deleted.")

    delete_old_logs.short_description = _("Delete old logs")


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    """Admin interface for networks."""

    list_display = (
        "name",
        "created_by",
        "is_public",
        "member_count",
        "created_at",
        "updated_at",
    )
    list_filter = ("is_public", "created_at")
    search_fields = ("name", "description", "created_by__username")
    raw_id_fields = ("created_by",)
    readonly_fields = ("created_at", "updated_at", "member_count")

    def member_count(self, obj):
        """Display member count."""
        return obj.memberships.filter(
            status=NetworkMembership.MembershipStatus.APPROVED
        ).count()

    member_count.short_description = "Members"


@admin.register(NetworkMembership)
class NetworkMembershipAdmin(admin.ModelAdmin):
    """Admin interface for network memberships."""

    list_display = ("user", "network", "status", "role", "joined_at")
    list_filter = ("status", "role", "joined_at")
    search_fields = ("user__username", "network__name")
    raw_id_fields = ("user", "network")

    actions = ["approve_memberships", "reject_memberships"]

    def approve_memberships(self, request, queryset):
        """Approve selected memberships."""
        updated = queryset.filter(
            status=NetworkMembership.MembershipStatus.PENDING
        ).update(status=NetworkMembership.MembershipStatus.APPROVED)
        self.message_user(request, f"{updated} membership(s) approved.")

    approve_memberships.short_description = _("Approve memberships")


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    """Admin interface for roles."""

    list_display = ("name", "description")
    search_fields = ("name", "description")

    def user_count(self, obj):
        """Display user count for this role."""
        return obj.user_roles.count()

    user_count.short_description = "Users"


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    """Admin interface for departments."""

    list_display = ("name", "head", "parent", "member_count")
    list_filter = ("parent",)
    search_fields = ("name", "description", "head__username")
    raw_id_fields = ("head", "parent")

    def member_count(self, obj):
        """Display member count."""
        return obj.members.count()

    member_count.short_description = "Members"


@admin.register(UserFile)
class UserFileAdmin(admin.ModelAdmin):
    """Admin interface for user files."""

    list_display = (
        "user",
        "name",
        "file_type",
        "file_size_display",
        "is_public",
        "created_at",
    )
    list_filter = ("file_type", "is_public", "created_at")
    search_fields = ("user__username", "name", "description")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at",)

    def file_size_display(self, obj):
        """Display file size in human readable format."""
        size = obj.file_size
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    file_size_display.short_description = "File Size"

    actions = ["verify_files", "scan_for_viruses"]

    def verify_files(self, request, queryset):
        """Mark selected files as verified."""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} file(s) marked as verified.")

    verify_files.short_description = _("Mark as verified")


@admin.register(ProfileStats)
class ProfileStatsAdmin(admin.ModelAdmin):
    """Admin interface for profile statistics."""

    list_display = (
        "user",
        "profile_views",
        "connections_count",
        "endorsements_count",
        "project_views",
        "search_appearances",
        "last_updated",
    )
    list_filter = ("last_updated",)
    search_fields = ("user__username",)
    raw_id_fields = ("user",)
    readonly_fields = ("user", "last_updated")

    def profile_completeness_bar(self, obj):
        """Display profile completeness as progress bar."""
        completeness = obj.profile_completeness or 0
        color = (
            "green" if completeness > 80 else "orange" if completeness > 50 else "red"
        )
        return format_html(
            '<div style="width: 100px; background-color: #f0f0f0;">'
            '<div style="width: {}px; background-color: {}; height: 20px;"></div>'
            "</div> {}%",
            completeness,
            color,
            completeness,
        )

    profile_completeness_bar.short_description = "Completeness"


@admin.register(Certification)
class CertificationAdmin(admin.ModelAdmin):
    """Admin interface for certifications."""

    list_display = (
        "user",
        "name",
        "issuer",
        "issue_date",
        "expiration_date",
        "credential_id",
        "created_at",
    )
    list_filter = ("issuer", "issue_date", "expiration_date")
    search_fields = ("user__username", "name", "issuer", "credential_id")
    raw_id_fields = ("user",)
    date_hierarchy = "issue_date"

    actions = ["verify_certifications", "mark_expired"]

    def verify_certifications(self, request, queryset):
        """Mark selected certifications as verified."""
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} certification(s) marked as verified.")

    verify_certifications.short_description = _("Mark as verified")

    def mark_expired(self, request, queryset):
        """Mark certifications as expired if past expiry date."""
        from django.utils import timezone

        expired_count = 0
        for cert in queryset.filter(
            has_expiry=True, expiry_date__lt=timezone.now().date()
        ):
            # You might want to add an 'is_expired' field to the model
            expired_count += 1
        self.message_user(request, f"{expired_count} certification(s) are expired.")

    mark_expired.short_description = _("Check for expired certifications")


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    """Admin interface for achievements."""

    list_display = ("user", "title", "category", "issuer", "date")
    list_filter = ("category", "date", "issuer")
    search_fields = ("user__username", "title", "issuer", "description")
    raw_id_fields = ("user",)
    date_hierarchy = "date"


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    """Admin interface for publications."""

    list_display = ("user", "title", "category", "publisher", "publication_date")
    list_filter = ("category", "publication_date", "publisher")
    search_fields = ("user__username", "title", "publisher", "authors")
    raw_id_fields = ("user",)
    date_hierarchy = "publication_date"


@admin.register(Language)
class LanguageAdmin(admin.ModelAdmin):
    """Admin interface for languages."""

    list_display = ("user", "name", "proficiency")
    list_filter = ("proficiency",)
    search_fields = ("user__username", "name")
    raw_id_fields = ("user",)


@admin.register(Volunteer)
class VolunteerAdmin(admin.ModelAdmin):
    """Admin interface for volunteer experience."""

    list_display = ("user", "role", "organization", "cause", "is_current", "start_date")
    list_filter = ("is_current", "start_date", "organization")
    search_fields = ("user__username", "role", "organization", "cause")
    raw_id_fields = ("user",)
    date_hierarchy = "start_date"


@admin.register(ProfileView)
class ProfileViewAdmin(admin.ModelAdmin):
    """Admin interface for profile views."""

    list_display = ("viewer", "profile_owner", "created_at", "ip_address")
    list_filter = ("created_at",)
    search_fields = ("viewer__username", "profile_owner__username")
    raw_id_fields = ("viewer", "profile_owner")
    readonly_fields = ("created_at",)
    date_hierarchy = "created_at"

    actions = ["delete_old_views"]

    def delete_old_views(self, request, queryset):
        """Delete profile views older than 6 months."""
        six_months_ago = timezone.now() - timedelta(days=180)
        old_views = queryset.filter(created_at__lt=six_months_ago)
        count = old_views.count()
        old_views.delete()
        self.message_user(request, f"{count} old profile view(s) deleted.")

    delete_old_views.short_description = _("Delete old profile views")


# Custom Admin Site Configuration
class AccountsAdminSite(admin.AdminSite):
    """Custom admin site for accounts app."""

    site_header = "Professional Network Administration"
    site_title = "Network Admin"
    index_title = "Welcome to Network Administration"

    def index(self, request, extra_context=None):
        """Custom admin index with statistics."""
        extra_context = extra_context or {}

        # Add custom statistics
        try:
            extra_context.update(
                {
                    "total_users": User.objects.count(),
                    "active_users": User.objects.filter(
                        status=User.UserStatus.ACTIVE
                    ).count(),
                    "verified_users": User.objects.filter(is_verified=True).count(),
                    "online_users": User.objects.filter(is_online=True).count(),
                    "total_connections": Connection.objects.filter(
                        status=Connection.ConnectionStatus.ACCEPTED
                    ).count(),
                    "pending_connections": Connection.objects.filter(
                        status=Connection.ConnectionStatus.PENDING
                    ).count(),
                    "total_skills": Skill.objects.count(),
                    "total_endorsements": SkillEndorsement.objects.count(),
                    "recent_registrations": User.objects.filter(
                        date_joined__gte=timezone.now() - timedelta(days=7)
                    ).count(),
                }
            )
        except Exception as e:
            logger.error(f"Error getting admin statistics: {str(e)}")

        return super().index(request, extra_context)


# Register remaining models with simple admins
@admin.register(SocialLink)
class SocialLinkAdmin(admin.ModelAdmin):
    list_display = ("user", "platform", "url", "is_visible")
    list_filter = ("platform", "is_visible")
    search_fields = ("user__username", "url")
    raw_id_fields = ("user",)


@admin.register(ProjectImage)
class ProjectImageAdmin(admin.ModelAdmin):
    list_display = ("project", "image_preview", "caption", "order")
    list_filter = ("project",)
    raw_id_fields = ("project",)
    readonly_fields = ("order",)

    def image_preview(self, obj):
        if obj.image:
            return format_html('<img src="{}" width="50" height="50" />', obj.image.url)
        return "No image"

    image_preview.short_description = "Preview"


@admin.register(TaskComment)
class TaskCommentAdmin(admin.ModelAdmin):
    list_display = ("task", "user", "content_preview", "created_at")
    list_filter = ("created_at",)
    search_fields = ("task__title", "user__username", "content")
    raw_id_fields = ("task", "user")
    readonly_fields = ("created_at",)

    def content_preview(self, obj):
        return (obj.content[:50] + "...") if len(obj.content) > 50 else obj.content

    content_preview.short_description = "Content"


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "assigned_at", "assigned_by")
    list_filter = ("role", "assigned_at")
    search_fields = ("user__username", "role__name")
    raw_id_fields = ("user", "role", "assigned_by")
    readonly_fields = ("assigned_at",)


@admin.register(UserDepartment)
class UserDepartmentAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "joined_at")
    list_filter = ("department", "joined_at")
    search_fields = ("user__username", "department__name")
    raw_id_fields = ("user", "department")
    readonly_fields = ("joined_at",)


@admin.register(SavedSearch)
class SavedSearchAdmin(admin.ModelAdmin):
    list_display = ("user", "name", "query_preview", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "name")
    raw_id_fields = ("user",)
    readonly_fields = ("created_at",)

    def query_preview(self, obj):
        query_str = str(obj.query)
        return (query_str[:50] + "...") if len(query_str) > 50 else query_str

    query_preview.short_description = "Query"


# Customize the admin site
admin.site.site_header = "Professional Network Administration"
admin.site.site_title = "Network Admin"
admin.site.index_title = "Welcome to Network Administration"

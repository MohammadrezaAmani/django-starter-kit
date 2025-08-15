from django.contrib import admin
from django.utils.html import format_html
from mptt.admin import MPTTModelAdmin

from .models import (
    Event,
    EventAnalytics,
    EventAttachment,
    EventBadge,
    EventCategory,
    EventCategoryRelation,
    EventFavorite,
    EventModerationLog,
    EventTag,
    EventTagRelation,
    EventView,
    Exhibitor,
    Participant,
    ParticipantBadge,
    Product,
    Session,
    SessionRating,
)


class EventCategoryRelationInline(admin.TabularInline):
    model = EventCategoryRelation
    extra = 1
    autocomplete_fields = ["category"]


class EventTagRelationInline(admin.TabularInline):
    model = EventTagRelation
    extra = 1
    autocomplete_fields = ["tag"]


class SessionInline(admin.TabularInline):
    model = Session
    extra = 0
    fields = ["title", "type", "start_time", "end_time", "track", "room", "status"]
    readonly_fields = ["attendee_count", "rating_avg"]
    show_change_link = True


class ParticipantInline(admin.TabularInline):
    model = Participant
    extra = 0
    fields = ["user", "role", "registration_status", "attendance_status", "ticket_type"]
    readonly_fields = ["points", "level", "registered_at"]
    show_change_link = True
    autocomplete_fields = ["user"]


class ExhibitorInline(admin.TabularInline):
    model = Exhibitor
    extra = 0
    fields = ["company_name", "sponsorship_tier", "booth_number", "status"]
    readonly_fields = ["view_count", "connection_count"]
    show_change_link = True


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "organizer",
        "type",
        "status",
        "start_date",
        "city",
        "registration_count",
        "view_count",
        "is_featured",
        "is_verified",
    ]
    list_filter = [
        "type",
        "status",
        "visibility",
        "is_featured",
        "is_trending",
        "is_verified",
        "registration_required",
        "approval_required",
        "is_free",
        "timezone",
        "start_date",
        "end_date",
        "created_at",
    ]
    search_fields = [
        "name",
        "raw_description",
        "city",
        "country",
        "venue_name",
        "organizer__username",
        "organizer__first_name",
        "organizer__last_name",
    ]
    autocomplete_fields = [
        "organizer",
        "co_organizers",
        "speakers",
        "moderators",
        "linked_project",
        "linked_task",
        "linked_network",
        "linked_chat",
        "linked_blog",
    ]
    readonly_fields = [
        "slug",
        "view_count",
        "registration_count",
        "attendance_count",
        "engagement_score",
        "content_hash",
        "created_at",
        "updated_at",
        "published_at",
        "spots_remaining_display",
        "is_live_display",
        "is_registration_open_display",
    ]
    inlines = [
        EventCategoryRelationInline,
        EventTagRelationInline,
        SessionInline,
        ParticipantInline,
        ExhibitorInline,
    ]
    actions = [
        "make_featured",
        "remove_featured",
        "make_verified",
        "make_trending",
        "publish_events",
    ]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "name",
                    "slug",
                    "description",
                    "raw_description",
                    "excerpt",
                    "type",
                    "status",
                    "visibility",
                )
            },
        ),
        (
            "Schedule & Location",
            {
                "fields": (
                    "start_date",
                    "end_date",
                    "timezone",
                    "registration_start",
                    "registration_end",
                    "location",
                    "address",
                    "city",
                    "country",
                    "venue_name",
                    "virtual_link",
                )
            },
        ),
        (
            "Organization",
            {"fields": ("organizer", "co_organizers", "speakers", "moderators")},
        ),
        (
            "Media",
            {
                "fields": ("logo", "banner", "gallery", "venue_map"),
                "classes": ("collapse",),
            },
        ),
        (
            "Registration & Capacity",
            {
                "fields": (
                    "capacity",
                    "max_tickets_per_user",
                    "registration_required",
                    "approval_required",
                    "waitlist_enabled",
                )
            },
        ),
        (
            "Pricing",
            {
                "fields": ("is_free", "currency", "ticket_types", "discount_codes"),
                "classes": ("collapse",),
            },
        ),
        (
            "Features",
            {
                "fields": (
                    "allow_comments",
                    "allow_reviews",
                    "enable_networking",
                    "enable_chat",
                    "enable_qr_checkin",
                    "enable_live_streaming",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "SEO & Metadata",
            {
                "fields": (
                    "seo_title",
                    "seo_description",
                    "seo_keywords",
                    "canonical_url",
                    "language",
                    "languages",
                    "translations",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Integration",
            {
                "fields": (
                    "linked_project",
                    "linked_task",
                    "linked_network",
                    "linked_chat",
                    "linked_blog",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Customization",
            {
                "fields": ("custom_theme", "custom_fields", "branding"),
                "classes": ("collapse",),
            },
        ),
        (
            "Status & Analytics",
            {
                "fields": (
                    "is_featured",
                    "is_trending",
                    "is_verified",
                    "view_count",
                    "registration_count",
                    "attendance_count",
                    "engagement_score",
                    "spots_remaining_display",
                    "is_live_display",
                    "is_registration_open_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "AI & Advanced",
            {
                "fields": ("ai_recommendations_enabled", "ai_metadata"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "published_at", "content_hash"),
                "classes": ("collapse",),
            },
        ),
    )

    date_hierarchy = "start_date"
    ordering = ["-start_date"]
    save_on_top = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related("organizer", "analytics").prefetch_related(
            "co_organizers", "speakers", "participants", "sessions", "exhibitors"
        )

    def spots_remaining_display(self, obj):
        remaining = obj.spots_remaining
        if remaining == float("inf"):
            return "Unlimited"
        elif remaining <= 0:
            return format_html('<span style="color: red;">Full</span>')
        elif remaining <= 10:
            return format_html('<span style="color: orange;">{}</span>', remaining)
        return remaining

    spots_remaining_display.short_description = "Spots Remaining"

    def is_live_display(self, obj):
        if obj.is_live:
            return format_html('<span style="color: green;">● Live</span>')
        return format_html('<span style="color: gray;">○ Not Live</span>')

    is_live_display.short_description = "Live Status"

    def is_registration_open_display(self, obj):
        if obj.is_registration_open:
            return format_html('<span style="color: green;">● Open</span>')
        return format_html('<span style="color: red;">● Closed</span>')

    is_registration_open_display.short_description = "Registration"

    def make_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f"{updated} events marked as featured.")

    make_featured.short_description = "Mark selected events as featured"

    def remove_featured(self, request, queryset):
        updated = queryset.update(is_featured=False)
        self.message_user(request, f"{updated} events removed from featured.")

    remove_featured.short_description = "Remove featured status"

    def make_verified(self, request, queryset):
        updated = queryset.update(is_verified=True)
        self.message_user(request, f"{updated} events marked as verified.")

    make_verified.short_description = "Mark selected events as verified"

    def make_trending(self, request, queryset):
        updated = queryset.update(is_trending=True)
        self.message_user(request, f"{updated} events marked as trending.")

    make_trending.short_description = "Mark selected events as trending"

    def publish_events(self, request, queryset):
        updated = queryset.update(status=Event.EventStatus.PUBLISHED)
        self.message_user(request, f"{updated} events published.")

    publish_events.short_description = "Publish selected events"


@admin.register(EventCategory)
class EventCategoryAdmin(MPTTModelAdmin):
    list_display = ["name", "parent", "is_active", "sort_order", "event_count_display"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["slug", "created_at"]
    mptt_level_indent = 20

    fieldsets = (
        ("Basic Information", {"fields": ("name", "slug", "description", "parent")}),
        ("Display", {"fields": ("icon", "color", "is_active", "sort_order")}),
        ("Metadata", {"fields": ("created_at",), "classes": ("collapse",)}),
    )

    def event_count_display(self, obj):
        count = obj.eventcategoryrelation_set.count()
        return count

    event_count_display.short_description = "Events"


@admin.register(EventTag)
class EventTagAdmin(admin.ModelAdmin):
    list_display = ["name", "usage_count", "is_trending", "created_at"]
    list_filter = ["is_trending", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["slug", "usage_count", "created_at"]
    actions = ["make_trending", "remove_trending"]

    def make_trending(self, request, queryset):
        updated = queryset.update(is_trending=True)
        self.message_user(request, f"{updated} tags marked as trending.")

    make_trending.short_description = "Mark selected tags as trending"

    def remove_trending(self, request, queryset):
        updated = queryset.update(is_trending=False)
        self.message_user(request, f"{updated} tags removed from trending.")

    remove_trending.short_description = "Remove trending status"


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "event",
        "type",
        "start_time",
        "track",
        "room",
        "status",
        "attendee_count",
        "rating_avg",
    ]
    list_filter = [
        "type",
        "status",
        "track",
        "is_paid",
        "is_recorded",
        "is_live_streamed",
        "requires_registration",
        "start_time",
    ]
    search_fields = [
        "title",
        "raw_description",
        "track",
        "room",
        "location",
        "event__name",
        "speakers__username",
    ]
    autocomplete_fields = ["event", "speakers", "moderator"]
    readonly_fields = [
        "slug",
        "attendee_count",
        "rating_avg",
        "rating_count",
        "duration_minutes_display",
        "is_live_display",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "event",
                    "title",
                    "slug",
                    "description",
                    "raw_description",
                    "type",
                    "status",
                )
            },
        ),
        (
            "Schedule",
            {
                "fields": (
                    "start_time",
                    "end_time",
                    "timezone",
                    "duration_minutes_display",
                )
            },
        ),
        ("Location", {"fields": ("track", "room", "location", "virtual_link")}),
        ("People", {"fields": ("speakers", "moderator")}),
        (
            "Settings",
            {
                "fields": (
                    "capacity",
                    "is_paid",
                    "is_recorded",
                    "is_live_streamed",
                    "requires_registration",
                )
            },
        ),
        (
            "Content",
            {"fields": ("materials", "recording_url"), "classes": ("collapse",)},
        ),
        (
            "Analytics",
            {
                "fields": (
                    "attendee_count",
                    "rating_avg",
                    "rating_count",
                    "is_live_display",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

    date_hierarchy = "start_time"
    ordering = ["start_time"]

    def duration_minutes_display(self, obj):
        return f"{obj.duration_minutes} minutes"

    duration_minutes_display.short_description = "Duration"

    def is_live_display(self, obj):
        if obj.is_live:
            return format_html('<span style="color: green;">● Live</span>')
        return format_html('<span style="color: gray;">○ Not Live</span>')

    is_live_display.short_description = "Live Status"


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "event",
        "role",
        "registration_status",
        "attendance_status",
        "points",
        "level",
        "registered_at",
    ]
    list_filter = [
        "role",
        "registration_status",
        "attendance_status",
        "is_public_profile",
        "allow_networking",
        "registered_at",
    ]
    search_fields = [
        "user__username",
        "user__first_name",
        "user__last_name",
        "user__email",
        "company",
        "job_title",
        "ticket_code",
    ]
    autocomplete_fields = ["user", "event", "sessions_attended"]
    readonly_fields = [
        "ticket_code",
        "points",
        "level",
        "last_activity",
        "total_session_time",
        "engagement_score",
        "registered_at",
        "updated_at",
    ]
    actions = ["approve_registrations", "check_in_participants", "add_points"]

    fieldsets = (
        (
            "Registration",
            {
                "fields": (
                    "user",
                    "event",
                    "role",
                    "registration_status",
                    "attendance_status",
                )
            },
        ),
        (
            "Ticket Information",
            {
                "fields": (
                    "ticket_type",
                    "ticket_code",
                    "ticket_price",
                    "payment_status",
                )
            },
        ),
        (
            "Profile",
            {
                "fields": ("bio", "company", "job_title", "website", "social_links"),
                "classes": ("collapse",),
            },
        ),
        (
            "Privacy & Preferences",
            {
                "fields": (
                    "is_public_profile",
                    "allow_networking",
                    "allow_messages",
                    "interests",
                    "dietary_requirements",
                    "accessibility_needs",
                    "session_preferences",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Gamification",
            {"fields": ("points", "level", "badges"), "classes": ("collapse",)},
        ),
        (
            "Attendance",
            {
                "fields": (
                    "check_in_time",
                    "check_out_time",
                    "sessions_attended",
                    "total_session_time",
                    "engagement_score",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "Additional Data",
            {"fields": ("registration_data", "notes"), "classes": ("collapse",)},
        ),
        (
            "Timestamps",
            {
                "fields": ("registered_at", "updated_at", "last_activity"),
                "classes": ("collapse",),
            },
        ),
    )

    date_hierarchy = "registered_at"
    ordering = ["-registered_at"]

    def approve_registrations(self, request, queryset):
        updated = queryset.update(
            registration_status=Participant.RegistrationStatus.CONFIRMED
        )
        self.message_user(request, f"{updated} registrations approved.")

    approve_registrations.short_description = "Approve selected registrations"

    def check_in_participants(self, request, queryset):
        count = 0
        for participant in queryset:
            if (
                participant.attendance_status
                == Participant.AttendanceStatus.NOT_ATTENDED
            ):
                participant.check_in()
                count += 1
        self.message_user(request, f"{count} participants checked in.")

    check_in_participants.short_description = "Check in selected participants"

    def add_points(self, request, queryset):
        for participant in queryset:
            participant.add_points(10, "Manual admin addition")
        self.message_user(
            request, f"Added 10 points to {queryset.count()} participants."
        )

    add_points.short_description = "Add 10 points to selected participants"


@admin.register(Exhibitor)
class ExhibitorAdmin(admin.ModelAdmin):
    list_display = [
        "company_name",
        "event",
        "sponsorship_tier",
        "booth_number",
        "status",
        "view_count",
        "connection_count",
    ]
    list_filter = ["sponsorship_tier", "status", "created_at", "approved_at"]
    search_fields = [
        "company_name",
        "raw_description",
        "booth_number",
        "contact_email",
        "representatives__username",
    ]
    autocomplete_fields = ["event", "representatives", "primary_contact"]
    readonly_fields = [
        "slug",
        "view_count",
        "connection_count",
        "lead_count",
        "created_at",
        "updated_at",
        "approved_at",
    ]
    actions = ["approve_exhibitors", "reject_exhibitors"]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "event",
                    "company_name",
                    "slug",
                    "description",
                    "raw_description",
                )
            },
        ),
        ("Media", {"fields": ("logo", "banner", "gallery")}),
        (
            "Booth Information",
            {
                "fields": (
                    "booth_number",
                    "booth_size",
                    "booth_location",
                    "booth_map_coordinates",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "website",
                    "contact_email",
                    "contact_phone",
                    "social_links",
                    "representatives",
                    "primary_contact",
                )
            },
        ),
        (
            "Sponsorship",
            {
                "fields": (
                    "sponsorship_tier",
                    "sponsorship_amount",
                    "sponsorship_benefits",
                )
            },
        ),
        (
            "Status & Analytics",
            {
                "fields": ("status", "view_count", "connection_count", "lead_count"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {
                "fields": ("created_at", "updated_at", "approved_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def approve_exhibitors(self, request, queryset):
        updated = queryset.update(status=Exhibitor.ExhibitorStatus.APPROVED)
        self.message_user(request, f"{updated} exhibitors approved.")

    approve_exhibitors.short_description = "Approve selected exhibitors"

    def reject_exhibitors(self, request, queryset):
        updated = queryset.update(status=Exhibitor.ExhibitorStatus.REJECTED)
        self.message_user(request, f"{updated} exhibitors rejected.")

    reject_exhibitors.short_description = "Reject selected exhibitors"


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "exhibitor",
        "category",
        "price",
        "currency",
        "view_count",
        "favorite_count",
    ]
    list_filter = ["category", "currency", "created_at"]
    search_fields = [
        "name",
        "raw_description",
        "category",
        "exhibitor__company_name",
        "event__name",
    ]
    autocomplete_fields = ["exhibitor", "event"]
    readonly_fields = [
        "slug",
        "view_count",
        "favorite_count",
        "inquiry_count",
        "created_at",
        "updated_at",
    ]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": (
                    "event",
                    "exhibitor",
                    "name",
                    "slug",
                    "description",
                    "raw_description",
                )
            },
        ),
        ("Media", {"fields": ("image", "gallery")}),
        (
            "Details",
            {
                "fields": (
                    "category",
                    "price",
                    "currency",
                    "availability",
                    "features",
                    "specifications",
                )
            },
        ),
        (
            "Resources",
            {"fields": ("website", "demo_url", "documentation_url", "brochure")},
        ),
        (
            "Analytics",
            {
                "fields": ("view_count", "favorite_count", "inquiry_count"),
                "classes": ("collapse",),
            },
        ),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )


@admin.register(EventAnalytics)
class EventAnalyticsAdmin(admin.ModelAdmin):
    list_display = [
        "event",
        "total_registrations",
        "attendance_rate",
        "avg_session_rating",
        "total_revenue",
        "last_calculated",
    ]
    list_filter = ["last_calculated"]
    search_fields = ["event__name"]
    readonly_fields = [
        "total_registrations",
        "confirmed_registrations",
        "cancelled_registrations",
        "total_attendance",
        "attendance_rate",
        "avg_session_attendance",
        "total_sessions",
        "avg_session_rating",
        "total_exhibitors",
        "total_products",
        "last_calculated",
    ]
    actions = ["recalculate_analytics"]

    def recalculate_analytics(self, request, queryset):
        for analytics in queryset:
            analytics.recalculate()
        self.message_user(
            request, f"Recalculated analytics for {queryset.count()} events."
        )

    recalculate_analytics.short_description = "Recalculate analytics"


@admin.register(EventBadge)
class EventBadgeAdmin(admin.ModelAdmin):
    list_display = ["name", "points_required", "is_active", "created_at"]
    list_filter = ["is_active", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at"]


@admin.register(ParticipantBadge)
class ParticipantBadgeAdmin(admin.ModelAdmin):
    list_display = ["participant", "badge", "earned_at"]
    list_filter = ["badge", "earned_at"]
    search_fields = [
        "participant__user__username",
        "participant__event__name",
        "badge__name",
    ]
    autocomplete_fields = ["participant", "badge"]
    readonly_fields = ["earned_at"]


@admin.register(EventAttachment)
class EventAttachmentAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "type",
        "file_size_display",
        "download_count",
        "is_public",
        "created_at",
    ]
    list_filter = ["type", "is_public", "created_at"]
    search_fields = ["title", "description"]
    readonly_fields = ["file_size", "mime_type", "download_count", "created_at"]
    autocomplete_fields = ["uploaded_by"]

    def file_size_display(self, obj):
        if obj.file_size:
            if obj.file_size > 1024 * 1024:
                return f"{obj.file_size / (1024 * 1024):.1f} MB"
            elif obj.file_size > 1024:
                return f"{obj.file_size / 1024:.1f} KB"
            return f"{obj.file_size} bytes"
        return "N/A"

    file_size_display.short_description = "File Size"


@admin.register(SessionRating)
class SessionRatingAdmin(admin.ModelAdmin):
    list_display = ["session", "participant", "rating", "helpful_count", "created_at"]
    list_filter = ["rating", "created_at"]
    search_fields = ["session__title", "participant__user__username", "review"]
    autocomplete_fields = ["session", "participant"]
    readonly_fields = ["helpful_count", "created_at", "updated_at"]


@admin.register(EventFavorite)
class EventFavoriteAdmin(admin.ModelAdmin):
    list_display = ["user", "event", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__username", "event__name"]
    autocomplete_fields = ["user", "event"]
    readonly_fields = ["created_at"]


@admin.register(EventView)
class EventViewAdmin(admin.ModelAdmin):
    list_display = ["event", "user", "duration_display", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["event__name", "user__username", "ip_address"]
    autocomplete_fields = ["event", "user"]
    readonly_fields = ["created_at"]

    def duration_display(self, obj):
        if obj.duration:
            minutes = obj.duration // 60
            seconds = obj.duration % 60
            return f"{minutes}m {seconds}s"
        return "N/A"

    duration_display.short_description = "Duration"


@admin.register(EventModerationLog)
class EventModerationLogAdmin(admin.ModelAdmin):
    list_display = ["event", "moderator", "action", "created_at"]
    list_filter = ["action", "created_at"]
    search_fields = ["event__name", "moderator__username", "reason"]
    autocomplete_fields = ["event", "moderator"]
    readonly_fields = ["created_at"]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

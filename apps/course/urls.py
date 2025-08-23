from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_nested import routers

from .views import (
    AssessmentViewSet,
    CourseViewSet,
    DiscussionViewSet,
    FeedbackViewSet,
    LanguageViewSet,
    LessonViewSet,
    ModuleViewSet,
    QuestionViewSet,
    StepViewSet,
    UserProgressViewSet,
    VocabularyViewSet,
)

app_name = "course"

# Create the main router
router = DefaultRouter()

# Register main viewsets
router.register(r"languages", LanguageViewSet, basename="language")
router.register(r"courses", CourseViewSet, basename="course")
router.register(r"modules", ModuleViewSet, basename="module")
router.register(r"lessons", LessonViewSet, basename="lesson")
router.register(r"steps", StepViewSet, basename="step")
router.register(r"vocabulary", VocabularyViewSet, basename="vocabulary")
router.register(r"questions", QuestionViewSet, basename="question")
router.register(r"progress", UserProgressViewSet, basename="progress")
router.register(r"assessments", AssessmentViewSet, basename="assessment")
router.register(r"feedback", FeedbackViewSet, basename="feedback")
router.register(r"discussions", DiscussionViewSet, basename="discussion")

# Create nested routers for hierarchical relationships
courses_router = routers.NestedDefaultRouter(router, r"courses", lookup="course")
courses_router.register(r"modules", ModuleViewSet, basename="course-modules")
courses_router.register(
    r"assessments", AssessmentViewSet, basename="course-assessments"
)
courses_router.register(r"feedback", FeedbackViewSet, basename="course-feedback")
courses_router.register(
    r"discussions", DiscussionViewSet, basename="course-discussions"
)

modules_router = routers.NestedDefaultRouter(
    courses_router, r"modules", lookup="module"
)
modules_router.register(r"lessons", LessonViewSet, basename="module-lessons")
modules_router.register(
    r"assessments", AssessmentViewSet, basename="module-assessments"
)

lessons_router = routers.NestedDefaultRouter(
    modules_router, r"lessons", lookup="lesson"
)
lessons_router.register(r"steps", StepViewSet, basename="lesson-steps")
lessons_router.register(r"vocabulary", VocabularyViewSet, basename="lesson-vocabulary")
lessons_router.register(
    r"assessments", AssessmentViewSet, basename="lesson-assessments"
)

steps_router = routers.NestedDefaultRouter(lessons_router, r"steps", lookup="step")
steps_router.register(r"questions", QuestionViewSet, basename="step-questions")

# URL patterns
urlpatterns = [
    # Main API routes
    path("", include(router.urls)),
    # Nested routes
    path("", include(courses_router.urls)),
    path("", include(modules_router.urls)),
    path("", include(lessons_router.urls)),
    path("", include(steps_router.urls)),
    # # Additional custom endpoints
    # path(
    #     "api/search/",
    #     include(
    #         [
    #             path(
    #                 "courses/",
    #                 CourseViewSet.as_view({"get": "list"}),
    #                 name="search-courses",
    #             ),
    #             path(
    #                 "lessons/",
    #                 LessonViewSet.as_view({"get": "list"}),
    #                 name="search-lessons",
    #             ),
    #             path(
    #                 "vocabulary/",
    #                 VocabularyViewSet.as_view({"get": "list"}),
    #                 name="search-vocabulary",
    #             ),
    #         ]
    #     ),
    # ),
    # # Dashboard and analytics endpoints
    # path(
    #     "api/dashboard/",
    #     UserProgressViewSet.as_view({"get": "dashboard"}),
    #     name="dashboard",
    # ),
    # # Learning path endpoints
    # path(
    #     "api/learning-path/",
    #     include(
    #         [
    #             path(
    #                 "next-lesson/",
    #                 LessonViewSet.as_view({"get": "next_lesson"}),
    #                 name="next-lesson",
    #             ),
    #             path(
    #                 "recommended/",
    #                 CourseViewSet.as_view({"get": "recommended"}),
    #                 name="recommended-courses",
    #             ),
    #             path(
    #                 "review-items/",
    #                 VocabularyViewSet.as_view({"get": "for_review"}),
    #                 name="review-items",
    #             ),
    #         ]
    #     ),
    # ),
    # # Statistics and analytics
    # path(
    #     "api/analytics/",
    #     include(
    #         [
    #             path(
    #                 "course/<uuid:course_id>/stats/",
    #                 CourseViewSet.as_view({"get": "statistics"}),
    #                 name="course-stats",
    #             ),
    #             path(
    #                 "instructor/dashboard/",
    #                 CourseViewSet.as_view({"get": "instructor_dashboard"}),
    #                 name="instructor-dashboard",
    #             ),
    #             path(
    #                 "leaderboard/",
    #                 UserProgressViewSet.as_view({"get": "leaderboard"}),
    #                 name="leaderboard",
    #             ),
    #         ]
    #     ),
    # ),
    # # Bulk operations
    # path(
    #     "api/bulk/",
    #     include(
    #         [
    #             path(
    #                 "courses/",
    #                 CourseViewSet.as_view({"post": "bulk_action"}),
    #                 name="bulk-courses",
    #             ),
    #             path(
    #                 "lessons/",
    #                 LessonViewSet.as_view({"post": "bulk_action"}),
    #                 name="bulk-lessons",
    #             ),
    #             path(
    #                 "questions/",
    #                 QuestionViewSet.as_view({"post": "bulk_action"}),
    #                 name="bulk-questions",
    #             ),
    #         ]
    #     ),
    # ),
    # # Import/Export endpoints
    # path(
    #     "api/import-export/",
    #     include(
    #         [
    #             path(
    #                 "courses/export/",
    #                 CourseViewSet.as_view({"get": "export"}),
    #                 name="export-courses",
    #             ),
    #             path(
    #                 "courses/import/",
    #                 CourseViewSet.as_view({"post": "import_courses"}),
    #                 name="import-courses",
    #             ),
    #             path(
    #                 "vocabulary/export/",
    #                 VocabularyViewSet.as_view({"get": "export"}),
    #                 name="export-vocabulary",
    #             ),
    #             path(
    #                 "vocabulary/import/",
    #                 VocabularyViewSet.as_view({"post": "import_vocabulary"}),
    #                 name="import-vocabulary",
    #             ),
    #         ]
    #     ),
    # ),
    # # Assessment specific endpoints
    # path(
    #     "api/assessments/",
    #     include(
    #         [
    #             path(
    #                 "<uuid:pk>/start/",
    #                 AssessmentViewSet.as_view({"post": "start"}),
    #                 name="start-assessment",
    #             ),
    #             path(
    #                 "<uuid:pk>/submit/",
    #                 AssessmentViewSet.as_view({"post": "submit"}),
    #                 name="submit-assessment",
    #             ),
    #             path(
    #                 "<uuid:pk>/results/",
    #                 AssessmentViewSet.as_view({"get": "results"}),
    #                 name="assessment-results",
    #             ),
    #             path(
    #                 "attempts/<uuid:attempt_id>/",
    #                 AssessmentViewSet.as_view({"get": "get_attempt"}),
    #                 name="assessment-attempt",
    #             ),
    #         ]
    #     ),
    # ),
    # # Gamification endpoints
    # path(
    #     "api/gamification/",
    #     include(
    #         [
    #             path(
    #                 "achievements/",
    #                 UserProgressViewSet.as_view({"get": "achievements"}),
    #                 name="user-achievements",
    #             ),
    #             path(
    #                 "badges/",
    #                 UserProgressViewSet.as_view({"get": "badges"}),
    #                 name="user-badges",
    #             ),
    #             path(
    #                 "streaks/",
    #                 UserProgressViewSet.as_view({"get": "streaks"}),
    #                 name="learning-streaks",
    #             ),
    #             path(
    #                 "xp-history/",
    #                 UserProgressViewSet.as_view({"get": "xp_history"}),
    #                 name="xp-history",
    #             ),
    #         ]
    #     ),
    # ),
    # # Social features
    # path(
    #     "api/social/",
    #     include(
    #         [
    #             path(
    #                 "discussions/<uuid:thread_id>/posts/",
    #                 DiscussionViewSet.as_view({"get": "posts"}),
    #                 name="thread-posts",
    #             ),
    #             path(
    #                 "discussions/<uuid:thread_id>/join/",
    #                 DiscussionViewSet.as_view({"post": "join"}),
    #                 name="join-discussion",
    #             ),
    #             path(
    #                 "discussions/<uuid:thread_id>/leave/",
    #                 DiscussionViewSet.as_view({"post": "leave"}),
    #                 name="leave-discussion",
    #             ),
    #             path(
    #                 "study-groups/",
    #                 DiscussionViewSet.as_view({"get": "study_groups"}),
    #                 name="study-groups",
    #             ),
    #             path(
    #                 "peer-reviews/",
    #                 FeedbackViewSet.as_view({"get": "peer_reviews"}),
    #                 name="peer-reviews",
    #             ),
    #         ]
    #     ),
    # ),
    # # AI and personalization
    # path(
    #     "api/ai/",
    #     include(
    #         [
    #             path(
    #                 "recommendations/",
    #                 UserProgressViewSet.as_view({"get": "get_recommendations"}),
    #                 name="ai-recommendations",
    #             ),
    #             path(
    #                 "difficulty-adjustment/",
    #                 LessonViewSet.as_view({"post": "adjust_difficulty"}),
    #                 name="adjust-difficulty",
    #             ),
    #             path(
    #                 "personalized-path/",
    #                 UserProgressViewSet.as_view({"get": "personalized_path"}),
    #                 name="personalized-path",
    #             ),
    #             path(
    #                 "content-generation/",
    #                 CourseViewSet.as_view({"post": "generate_content"}),
    #                 name="generate-content",
    #             ),
    #         ]
    #     ),
    # ),
    # # Spaced repetition
    # path(
    #     "api/spaced-repetition/",
    #     include(
    #         [
    #             path(
    #                 "due-items/",
    #                 VocabularyViewSet.as_view({"get": "due_for_review"}),
    #                 name="due-items",
    #             ),
    #             path(
    #                 "schedule-review/",
    #                 VocabularyViewSet.as_view({"post": "schedule_review"}),
    #                 name="schedule-review",
    #             ),
    #             path(
    #                 "update-schedule/",
    #                 VocabularyViewSet.as_view({"post": "update_review_schedule"}),
    #                 name="update-schedule",
    #             ),
    #         ]
    #     ),
    # ),
    # # Mobile app specific endpoints
    # path(
    #     "api/mobile/",
    #     include(
    #         [
    #             path(
    #                 "sync/",
    #                 UserProgressViewSet.as_view({"post": "sync_progress"}),
    #                 name="mobile-sync",
    #             ),
    #             path(
    #                 "offline-content/",
    #                 CourseViewSet.as_view({"get": "offline_content"}),
    #                 name="offline-content",
    #             ),
    #             path(
    #                 "quick-lesson/",
    #                 LessonViewSet.as_view({"get": "quick_lesson"}),
    #                 name="quick-lesson",
    #             ),
    #         ]
    #     ),
    # ),
    # # Advanced search and filtering
    # path(
    #     "api/advanced-search/",
    #     include(
    #         [
    #             path(
    #                 "global/",
    #                 CourseViewSet.as_view({"get": "global_search"}),
    #                 name="global-search",
    #             ),
    #             path(
    #                 "smart-search/",
    #                 CourseViewSet.as_view({"get": "smart_search"}),
    #                 name="smart-search",
    #             ),
    #         ]
    #     ),
    # ),
    # # Reporting and exports for instructors
    # path(
    #     "api/reports/",
    #     include(
    #         [
    #             path(
    #                 "course-analytics/<uuid:course_id>/",
    #                 CourseViewSet.as_view({"get": "detailed_analytics"}),
    #                 name="course-analytics",
    #             ),
    #             path(
    #                 "student-progress/<uuid:course_id>/",
    #                 UserProgressViewSet.as_view({"get": "student_progress_report"}),
    #                 name="student-progress",
    #             ),
    #             path(
    #                 "assessment-analytics/<uuid:assessment_id>/",
    #                 AssessmentViewSet.as_view({"get": "assessment_analytics"}),
    #                 name="assessment-analytics",
    #             ),
    #             path(
    #                 "engagement-report/",
    #                 UserProgressViewSet.as_view({"get": "engagement_report"}),
    #                 name="engagement-report",
    #             ),
    #         ]
    #     ),
    # ),
    # # Content management
    # path(
    #     "api/content/",
    #     include(
    #         [
    #             path(
    #                 "duplicate/<uuid:pk>/",
    #                 CourseViewSet.as_view({"post": "duplicate"}),
    #                 name="duplicate-course",
    #             ),
    #             path(
    #                 "archive/<uuid:pk>/",
    #                 CourseViewSet.as_view({"post": "archive"}),
    #                 name="archive-course",
    #             ),
    #             path(
    #                 "publish/<uuid:pk>/",
    #                 CourseViewSet.as_view({"post": "publish"}),
    #                 name="publish-course",
    #             ),
    #             path(
    #                 "preview/<uuid:pk>/",
    #                 CourseViewSet.as_view({"get": "preview"}),
    #                 name="preview-course",
    #             ),
    #         ]
    #     ),
    # ),
    # # Certification
    # path(
    #     "api/certification/",
    #     include(
    #         [
    #             path(
    #                 "eligible-courses/",
    #                 CourseViewSet.as_view({"get": "certification_eligible"}),
    #                 name="certification-eligible",
    #             ),
    #             path(
    #                 "generate-certificate/<uuid:course_id>/",
    #                 CourseViewSet.as_view({"post": "generate_certificate"}),
    #                 name="generate-certificate",
    #             ),
    #             path(
    #                 "verify-certificate/<str:verification_code>/",
    #                 CourseViewSet.as_view({"get": "verify_certificate"}),
    #                 name="verify-certificate",
    #             ),
    #         ]
    #     ),
    # ),
    # # Admin and moderation
    # # Integration endpoints
    # path(
    #     "api/integrations/",
    #     include(
    #         [
    #             path(
    #                 "lms-export/",
    #                 CourseViewSet.as_view({"get": "lms_export"}),
    #                 name="lms-export",
    #             ),
    #             path(
    #                 "calendar-integration/",
    #                 UserProgressViewSet.as_view({"get": "calendar_events"}),
    #                 name="calendar-integration",
    #             ),
    #             path(
    #                 "webhook/<str:event_type>/",
    #                 CourseViewSet.as_view({"post": "webhook_handler"}),
    #                 name="webhook",
    #             ),
    #         ]
    #     ),
    # ),
]

import logging

from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from .models import (
    Achievement,
    Assessment,
    Certificate,
    Course,
    DiscussionPost,
    Feedback,
    LeaderboardEntry,
    SpacedRepetition,
    UserAchievement,
    UserAnalytics,
    UserAssessmentAttempt,
    UserProgress,
    UserResponse,
    Vocabulary,
)

logger = logging.getLogger(__name__)


# Course-related signals
@receiver(post_save, sender=Course)
def course_post_save(sender, instance, created, **kwargs):
    """Handle course creation and updates"""
    try:
        if created:
            # Create default modules/structure if needed
            logger.info(f"Course created: {instance.title}")

            # Update language learning resources count
            if instance.target_language:
                instance.target_language.learning_resources_count += 1
                instance.target_language.save(
                    update_fields=["learning_resources_count"]
                )

            # Create initial analytics entry for instructor
            if instance.instructor:
                today = timezone.now().date()
                UserAnalytics.objects.get_or_create(
                    user=instance.instructor, date=today, defaults={"courses_taught": 1}
                )
        else:
            # Handle course updates
            if instance.is_published and not getattr(instance, "_was_published", False):
                logger.info(f"Course published: {instance.title}")
                # Notify enrolled users about course publication
                _notify_course_published(instance)

            # Clear course-related cache
            cache.delete(f"course_stats_{instance.id}")
            cache.delete(f"course_modules_{instance.id}")

    except Exception as e:
        logger.error(f"Error in course_post_save: {str(e)}", exc_info=True)


@receiver(pre_save, sender=Course)
def course_pre_save(sender, instance, **kwargs):
    """Handle course pre-save operations"""
    try:
        if instance.pk:
            # Store previous state for comparison
            old_instance = Course.objects.get(pk=instance.pk)
            instance._was_published = old_instance.is_published
    except Course.DoesNotExist:
        instance._was_published = False


# Progress tracking signals
@receiver(post_save, sender=UserProgress)
def user_progress_post_save(sender, instance, created, **kwargs):
    """Handle progress updates and achievement checks"""
    try:
        if created:
            logger.info(
                f"Progress created for user {instance.user} in {instance.course or instance.lesson}"
            )

            # Set first_accessed if not set
            if not instance.first_accessed:
                instance.first_accessed = timezone.now()
                instance.save(update_fields=["first_accessed"])

        # Check for achievements when progress is updated
        if instance.is_completed and instance.completed_at:
            _check_achievements(instance.user, instance)
            _update_user_analytics(instance.user, instance)
            _update_leaderboard(instance.user)

        # Update course statistics
        if instance.course:
            _update_course_statistics(instance.course)

        # Update spaced repetition items for completed content
        if instance.is_completed and instance.lesson:
            _create_spaced_repetition_items(instance.user, instance.lesson)

    except Exception as e:
        logger.error(f"Error in user_progress_post_save: {str(e)}", exc_info=True)


@receiver(post_save, sender=UserResponse)
def user_response_post_save(sender, instance, created, **kwargs):
    """Handle user response analytics and spaced repetition updates"""
    try:
        if created:
            # Update question analytics
            question = instance.question
            question.attempt_count += 1

            # Calculate new success rate
            total_responses = UserResponse.objects.filter(question=question).count()
            correct_responses = UserResponse.objects.filter(
                question=question, is_correct=True
            ).count()
            question.success_rate = (
                (correct_responses / total_responses) * 100
                if total_responses > 0
                else 0
            )

            # Update average response time
            avg_time = (
                UserResponse.objects.filter(question=question).aggregate(
                    avg_time=models.Avg("time_taken_seconds")
                )["avg_time"]
                or 0
            )
            question.average_response_time = int(avg_time)

            question.save(
                update_fields=["attempt_count", "success_rate", "average_response_time"]
            )

            # Update spaced repetition schedule if this is vocabulary-related
            if question.step and question.step.lesson:
                _update_spaced_repetition_from_response(instance)

            # Update user analytics
            _update_daily_analytics(instance.user, instance)

    except Exception as e:
        logger.error(f"Error in user_response_post_save: {str(e)}", exc_info=True)


@receiver(post_save, sender=UserAssessmentAttempt)
def assessment_attempt_post_save(sender, instance, created, **kwargs):
    """Handle assessment attempt completion and statistics"""
    try:
        if instance.status == "completed":
            # Update assessment statistics
            assessment = instance.assessment

            # Calculate new statistics
            completed_attempts = UserAssessmentAttempt.objects.filter(
                assessment=assessment, status="completed"
            )

            total_attempts = completed_attempts.count()
            passed_attempts = completed_attempts.filter(passed=True).count()

            assessment.attempt_count = total_attempts
            assessment.completion_rate = (
                (passed_attempts / total_attempts * 100) if total_attempts > 0 else 0
            )
            assessment.average_score = (
                completed_attempts.aggregate(avg_score=models.Avg("percentage_score"))[
                    "avg_score"
                ]
                or 0
            )

            assessment.save(
                update_fields=["attempt_count", "completion_rate", "average_score"]
            )

            # Award certificate if eligible
            if instance.passed and assessment.certificate_required:
                _award_certificate(
                    instance.user, assessment.course, instance.percentage_score
                )

            # Check for achievements
            _check_assessment_achievements(instance.user, instance)

            # Update user progress for course completion
            if instance.passed and assessment.course:
                _check_course_completion(instance.user, assessment.course)

    except Exception as e:
        logger.error(f"Error in assessment_attempt_post_save: {str(e)}", exc_info=True)


# Achievement and gamification signals
@receiver(post_save, sender=UserAchievement)
def user_achievement_post_save(sender, instance, created, **kwargs):
    """Handle achievement unlocking"""
    try:
        if created:
            achievement = instance.achievement
            user = instance.user

            logger.info(f"Achievement unlocked: {achievement.name} for user {user}")

            # Update achievement unlock count
            achievement.unlock_count += 1
            achievement.save(update_fields=["unlock_count"])

            # Award XP and bonus rewards
            if achievement.xp_reward > 0:
                # Add XP to user's overall progress
                user_progress = UserProgress.objects.filter(
                    user=user, course__isnull=False
                ).first()
                if user_progress:
                    user_progress.xp_earned += achievement.xp_reward
                    user_progress.save(update_fields=["xp_earned"])

            # Process bonus rewards
            if achievement.bonus_rewards:
                _process_bonus_rewards(user, achievement.bonus_rewards)

            # Send achievement notification
            _send_achievement_notification(user, achievement)

            # Update leaderboard
            _update_leaderboard(user)

    except Exception as e:
        logger.error(f"Error in user_achievement_post_save: {str(e)}", exc_info=True)


# Discussion and social signals
@receiver(post_save, sender=DiscussionPost)
def discussion_post_post_save(sender, instance, created, **kwargs):
    """Handle discussion post creation and updates"""
    try:
        thread = instance.thread

        if created:
            # Update thread statistics
            thread.posts_count += 1
            thread.last_post_at = instance.created_at
            thread.last_post_by = instance.author

            # Update participants count
            unique_participants = (
                DiscussionPost.objects.filter(thread=thread, is_active=True)
                .values("author")
                .distinct()
                .count()
            )
            thread.participants_count = unique_participants

            thread.save(
                update_fields=[
                    "posts_count",
                    "last_post_at",
                    "last_post_by",
                    "participants_count",
                ]
            )

            # Award XP for community participation
            if instance.author:
                _award_discussion_xp(instance.author)

            # Update user analytics
            _update_social_analytics(instance.author)

        # Update parent post replies count if this is a reply
        if instance.parent_post:
            parent = instance.parent_post
            parent.replies_count = parent.replies.filter(is_active=True).count()
            parent.save(update_fields=["replies_count"])

    except Exception as e:
        logger.error(f"Error in discussion_post_post_save: {str(e)}", exc_info=True)


@receiver(post_delete, sender=DiscussionPost)
def discussion_post_post_delete(sender, instance, **kwargs):
    """Handle discussion post deletion"""
    try:
        thread = instance.thread

        # Update thread statistics
        thread.posts_count = max(0, thread.posts_count - 1)

        # Update last post information
        latest_post = (
            DiscussionPost.objects.filter(thread=thread, is_active=True)
            .order_by("-created_at")
            .first()
        )

        if latest_post:
            thread.last_post_at = latest_post.created_at
            thread.last_post_by = latest_post.author
        else:
            thread.last_post_at = None
            thread.last_post_by = None

        # Update participants count
        unique_participants = (
            DiscussionPost.objects.filter(thread=thread, is_active=True)
            .values("author")
            .distinct()
            .count()
        )
        thread.participants_count = unique_participants

        thread.save(
            update_fields=[
                "posts_count",
                "last_post_at",
                "last_post_by",
                "participants_count",
            ]
        )

        # Update parent post replies count if this was a reply
        if instance.parent_post:
            parent = instance.parent_post
            parent.replies_count = parent.replies.filter(is_active=True).count()
            parent.save(update_fields=["replies_count"])

    except Exception as e:
        logger.error(f"Error in discussion_post_post_delete: {str(e)}", exc_info=True)


# Feedback signals
@receiver(post_save, sender=Feedback)
def feedback_post_save(sender, instance, created, **kwargs):
    """Handle feedback creation and updates"""
    try:
        if created:
            logger.info(f"New feedback received from {instance.user}")

            # Update user analytics for feedback given
            _update_feedback_analytics(instance.user)

            # Auto-prioritize high severity feedback
            if instance.severity == "high":
                instance.status = "in_review"
                instance.save(update_fields=["status"])
                _notify_high_priority_feedback(instance)

        # Handle status changes
        if instance.status == "resolved" and instance.resolved_at:
            _send_feedback_resolution_notification(instance)

    except Exception as e:
        logger.error(f"Error in feedback_post_save: {str(e)}", exc_info=True)


# Analytics and caching signals
@receiver(post_save, sender=UserAnalytics)
def user_analytics_post_save(sender, instance, created, **kwargs):
    """Handle user analytics updates"""
    try:
        # Clear relevant cache entries
        cache.delete(f"user_stats_{instance.user.id}")
        cache.delete(f"daily_analytics_{instance.user.id}_{instance.date}")

        # Update streak information
        _update_learning_streak(instance.user, instance.date)

    except Exception as e:
        logger.error(f"Error in user_analytics_post_save: {str(e)}", exc_info=True)


# Spaced repetition signals
@receiver(post_save, sender=SpacedRepetition)
def spaced_repetition_post_save(sender, instance, created, **kwargs):
    """Handle spaced repetition schedule updates"""
    try:
        if created:
            logger.info(f"Spaced repetition item created for user {instance.user}")

        # Update due status based on next_review date
        if instance.next_review:
            now = timezone.now()
            instance.is_due = now >= instance.next_review
            if instance.is_due != instance.__dict__.get("is_due"):
                instance.save(update_fields=["is_due"])

    except Exception as e:
        logger.error(f"Error in spaced_repetition_post_save: {str(e)}", exc_info=True)


# Helper functions
def _notify_course_published(course):
    """Notify users about course publication"""
    try:
        # Get enrolled users
        enrolled_users = (
            UserProgress.objects.filter(course=course)
            .values_list("user", flat=True)
            .distinct()
        )

        # Send notifications (implementation depends on notification system)
        logger.info(
            f"Notifying {enrolled_users.count()} users about course publication: {course.title}"
        )
    except Exception as e:
        logger.error(f"Error notifying course publication: {str(e)}", exc_info=True)


def _check_achievements(user, progress):
    """Check and award achievements based on progress"""
    try:
        achievements_to_check = Achievement.objects.filter(is_active=True)

        for achievement in achievements_to_check:
            # Check if user already has this achievement
            if UserAchievement.objects.filter(
                user=user, achievement=achievement
            ).exists():
                continue

            # Check achievement criteria
            if _meets_achievement_criteria(user, achievement, progress):
                UserAchievement.objects.create(
                    user=user,
                    achievement=achievement,
                    progress_data={"triggered_by": str(progress.id)},
                )

    except Exception as e:
        logger.error(f"Error checking achievements: {str(e)}", exc_info=True)


def _meets_achievement_criteria(user, achievement, progress):
    """Check if user meets specific achievement criteria"""
    try:
        criteria = achievement.criteria

        # Course completion achievements
        if "courses_completed" in criteria:
            completed_courses = UserProgress.objects.filter(
                user=user, course__isnull=False, is_completed=True
            ).count()
            if completed_courses < criteria["courses_completed"]:
                return False

        # Score-based achievements
        if "min_average_score" in criteria:
            avg_score = (
                UserProgress.objects.filter(user=user).aggregate(
                    avg_score=models.Avg("average_score")
                )["avg_score"]
                or 0
            )
            if avg_score < criteria["min_average_score"]:
                return False

        # Streak achievements
        if "min_streak_days" in criteria:
            max_streak = (
                UserProgress.objects.filter(user=user).aggregate(
                    max_streak=models.Max("longest_streak")
                )["max_streak"]
                or 0
            )
            if max_streak < criteria["min_streak_days"]:
                return False

        # XP achievements
        if "total_xp" in criteria:
            total_xp = (
                UserProgress.objects.filter(user=user).aggregate(
                    total_xp=models.Sum("xp_earned")
                )["total_xp"]
                or 0
            )
            if total_xp < criteria["total_xp"]:
                return False

        return True

    except Exception as e:
        logger.error(f"Error checking achievement criteria: {str(e)}", exc_info=True)
        return False


def _update_user_analytics(user, progress):
    """Update user analytics when progress is made"""
    try:
        today = timezone.now().date()
        analytics, created = UserAnalytics.objects.get_or_create(
            user=user,
            date=today,
            course=progress.course,
            defaults={
                "lessons_completed": 1 if progress.lesson else 0,
                "xp_gained": progress.xp_earned,
            },
        )

        if not created and progress.lesson and progress.is_completed:
            analytics.lessons_completed += 1
            analytics.xp_gained += progress.xp_earned
            analytics.save(update_fields=["lessons_completed", "xp_gained"])

    except Exception as e:
        logger.error(f"Error updating user analytics: {str(e)}", exc_info=True)


def _update_leaderboard(user):
    """Update leaderboard entries for user"""
    try:
        # Global leaderboard
        total_xp = (
            UserProgress.objects.filter(user=user).aggregate(
                total_xp=models.Sum("xp_earned")
            )["total_xp"]
            or 0
        )

        entry, created = LeaderboardEntry.objects.get_or_create(
            user=user, leaderboard_type="global", defaults={"total_xp": total_xp}
        )

        if not created:
            entry.total_xp = total_xp
            entry.save(update_fields=["total_xp"])

        # Update rankings (this could be done periodically instead)
        _update_leaderboard_rankings("global")

    except Exception as e:
        logger.error(f"Error updating leaderboard: {str(e)}", exc_info=True)


def _update_leaderboard_rankings(leaderboard_type):
    """Update rankings for a specific leaderboard type"""
    try:
        entries = LeaderboardEntry.objects.filter(
            leaderboard_type=leaderboard_type
        ).order_by("-total_xp")

        for rank, entry in enumerate(entries, 1):
            if entry.current_rank != rank:
                entry.previous_rank = entry.current_rank
                entry.current_rank = rank
                entry.save(update_fields=["previous_rank", "current_rank"])

    except Exception as e:
        logger.error(f"Error updating leaderboard rankings: {str(e)}", exc_info=True)


def _create_spaced_repetition_items(user, lesson):
    """Create spaced repetition items for lesson vocabulary"""
    try:
        vocabulary_items = lesson.vocabulary.filter(is_active=True)

        for vocab in vocabulary_items:
            SpacedRepetition.objects.get_or_create(
                user=user,
                content_type=ContentType.objects.get_for_model(Vocabulary),
                object_id=vocab.id,
                defaults={
                    "next_review": timezone.now() + timezone.timedelta(days=1),
                    "created_by": user,
                },
            )

    except Exception as e:
        logger.error(f"Error creating spaced repetition items: {str(e)}", exc_info=True)


def _update_spaced_repetition_from_response(response):
    """Update spaced repetition schedule based on user response"""
    try:
        # Find related vocabulary or content
        if response.question.step and response.question.step.lesson:
            lesson = response.question.step.lesson
            vocabulary_items = lesson.vocabulary.all()

            for vocab in vocabulary_items:
                sr_item = SpacedRepetition.objects.filter(
                    user=response.user,
                    content_type=ContentType.objects.get_for_model(Vocabulary),
                    object_id=vocab.id,
                ).first()

                if sr_item:
                    # Update schedule based on response correctness
                    quality_rating = 5 if response.is_correct else 2
                    sr_item.update_schedule(quality_rating)

    except Exception as e:
        logger.error(
            f"Error updating spaced repetition from response: {str(e)}", exc_info=True
        )


def _update_course_statistics(course):
    """Update course-level statistics"""
    try:
        # Update enrollment and completion counts
        total_progress = UserProgress.objects.filter(course=course)

        course.enrollment_count = total_progress.values("user").distinct().count()
        course.completion_count = (
            total_progress.filter(is_completed=True).values("user").distinct().count()
        )

        # Update average rating (if ratings system is implemented)
        # This would depend on how ratings are stored

        course.save(update_fields=["enrollment_count", "completion_count"])

        # Clear cache
        cache.delete(f"course_stats_{course.id}")

    except Exception as e:
        logger.error(f"Error updating course statistics: {str(e)}", exc_info=True)


def _award_certificate(user, course, final_score):
    """Award certificate to user for course completion"""
    try:
        certificate, created = Certificate.objects.get_or_create(
            user=user,
            course=course,
            defaults={
                "final_score": final_score,
                "completion_time_hours": 0,  # Calculate actual time
                "created_by": user,
            },
        )

        if created:
            logger.info(f"Certificate awarded to {user} for course {course}")

    except Exception as e:
        logger.error(f"Error awarding certificate: {str(e)}", exc_info=True)


def _check_assessment_achievements(user, attempt):
    """Check for assessment-specific achievements"""
    try:
        # Perfect score achievement
        if attempt.percentage_score == 100:
            perfect_score_achievement = Achievement.objects.filter(
                name="Perfect Score", is_active=True
            ).first()

            if (
                perfect_score_achievement
                and not UserAchievement.objects.filter(
                    user=user, achievement=perfect_score_achievement
                ).exists()
            ):
                UserAchievement.objects.create(
                    user=user, achievement=perfect_score_achievement
                )

    except Exception as e:
        logger.error(f"Error checking assessment achievements: {str(e)}", exc_info=True)


def _check_course_completion(user, course):
    """Check if user has completed all requirements for course"""
    try:
        # Check if all mandatory assessments are passed
        mandatory_assessments = Assessment.objects.filter(course=course, is_active=True)

        passed_assessments = (
            UserAssessmentAttempt.objects.filter(
                user=user, assessment__in=mandatory_assessments, passed=True
            )
            .values("assessment")
            .distinct()
            .count()
        )

        if passed_assessments == mandatory_assessments.count():
            # Mark course as completed
            course_progress, created = UserProgress.objects.get_or_create(
                user=user,
                course=course,
                defaults={"completion_percentage": 100, "is_completed": True},
            )

            if not course_progress.is_completed:
                course_progress.completion_percentage = 100
                course_progress.is_completed = True
                course_progress.completed_at = timezone.now()
                course_progress.save()

    except Exception as e:
        logger.error(f"Error checking course completion: {str(e)}", exc_info=True)


def _update_daily_analytics(user, response):
    """Update daily analytics from user response"""
    try:
        today = timezone.now().date()
        analytics, created = UserAnalytics.objects.get_or_create(
            user=user,
            date=today,
            defaults={
                "questions_answered": 1,
                "correct_answers": 1 if response.is_correct else 0,
            },
        )

        if not created:
            analytics.questions_answered += 1
            if response.is_correct:
                analytics.correct_answers += 1
            analytics.calculate_metrics()

    except Exception as e:
        logger.error(f"Error updating daily analytics: {str(e)}", exc_info=True)


def _award_discussion_xp(user):
    """Award XP for discussion participation"""
    try:
        xp_amount = 5  # Small amount for community participation

        # Add to user's progress
        latest_progress = UserProgress.objects.filter(user=user).first()
        if latest_progress:
            latest_progress.xp_earned += xp_amount
            latest_progress.save(update_fields=["xp_earned"])

    except Exception as e:
        logger.error(f"Error awarding discussion XP: {str(e)}", exc_info=True)


def _update_social_analytics(user):
    """Update social analytics for user"""
    try:
        today = timezone.now().date()
        analytics, created = UserAnalytics.objects.get_or_create(
            user=user, date=today, defaults={"discussions_participated": 1}
        )

        if not created:
            analytics.discussions_participated += 1
            analytics.save(update_fields=["discussions_participated"])

    except Exception as e:
        logger.error(f"Error updating social analytics: {str(e)}", exc_info=True)


def _update_feedback_analytics(user):
    """Update analytics for feedback given"""
    try:
        today = timezone.now().date()
        analytics, created = UserAnalytics.objects.get_or_create(
            user=user, date=today, defaults={"feedback_given": 1}
        )

        if not created:
            analytics.feedback_given += 1
            analytics.save(update_fields=["feedback_given"])

    except Exception as e:
        logger.error(f"Error updating feedback analytics: {str(e)}", exc_info=True)


def _update_learning_streak(user, date):
    """Update learning streak for user"""
    try:
        # Get user's progress records
        progress_records = UserProgress.objects.filter(user=user)

        if not progress_records.exists():
            return

        # Calculate current streak
        current_streak = 0
        check_date = date

        while True:
            has_activity = UserAnalytics.objects.filter(
                user=user, date=check_date, total_time_spent_minutes__gt=0
            ).exists()

            if has_activity:
                current_streak += 1
                check_date -= timezone.timedelta(days=1)
            else:
                break

        # Update progress records with new streak
        progress_records.update(current_streak=current_streak)

        # Update longest streak if necessary
        for progress in progress_records:
            if current_streak > progress.longest_streak:
                progress.longest_streak = current_streak
                progress.save(update_fields=["longest_streak"])

    except Exception as e:
        logger.error(f"Error updating learning streak: {str(e)}", exc_info=True)


def _process_bonus_rewards(user, bonus_rewards):
    """Process bonus rewards from achievements"""
    try:
        # Implementation depends on reward types
        # Could include course unlocks, premium features, etc.
        logger.info(f"Processing bonus rewards for user {user}: {bonus_rewards}")

    except Exception as e:
        logger.error(f"Error processing bonus rewards: {str(e)}", exc_info=True)


def _send_achievement_notification(user, achievement):
    """Send notification about achievement unlock"""
    try:
        # Implementation depends on notification system
        logger.info(
            f"Sending achievement notification to {user} for {achievement.name}"
        )

    except Exception as e:
        logger.error(f"Error sending achievement notification: {str(e)}", exc_info=True)


def _notify_high_priority_feedback(feedback):
    """Notify administrators about high priority feedback"""
    try:
        logger.warning(
            f"High priority feedback received from {feedback.user}: {feedback.feedback_type}"
        )

    except Exception as e:
        logger.error(f"Error notifying high priority feedback: {str(e)}", exc_info=True)


def _send_feedback_resolution_notification(feedback):
    """Send notification when feedback is resolved"""
    try:
        logger.info(f"Sending feedback resolution notification to {feedback.user}")

    except Exception as e:
        logger.error(
            f"Error sending feedback resolution notification: {str(e)}", exc_info=True
        )

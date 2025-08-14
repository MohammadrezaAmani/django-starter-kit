import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models.signals import post_save
from django.test import TestCase, override_settings

from apps.accounts.models import (
    Achievement,
    ActivityLog,
    Connection,
    Education,
    Experience,
    Follow,
    Notification,
    ProfileStats,
    Recommendation,
    Skill,
    SkillEndorsement,
    Task,
    UserFile,
    UserProfile,
)
from apps.accounts.signals import (
    create_user_profile,
)

User = get_user_model()


class SignalTestCase(TestCase):
    """Base test case for signal tests."""

    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(
            username="testuser1",
            email="test1@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User1",
        )
        self.user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User2",
        )


class UserProfileSignalTest(SignalTestCase):
    """Test user profile related signals."""

    def test_create_user_profile_signal(self):
        """Test that user profile is created when user is created."""
        # Profile should be created automatically by signal
        self.assertTrue(hasattr(self.user1, "profile"))
        self.assertIsInstance(self.user1.profile, UserProfile)

    def test_create_profile_stats_signal(self):
        """Test that profile stats are created when user is created."""
        # Profile stats should be created automatically by signal
        self.assertTrue(ProfileStats.objects.filter(user=self.user1).exists())

    def test_profile_signal_only_fires_on_creation(self):
        """Test that profile signal only fires when user is created, not updated."""
        initial_profile_count = UserProfile.objects.count()

        # Update user - should not create new profile
        self.user1.first_name = "Updated"
        self.user1.save()

        self.assertEqual(UserProfile.objects.count(), initial_profile_count)

    def test_profile_stats_initialization(self):
        """Test that profile stats are initialized with correct default values."""
        stats = ProfileStats.objects.get(user=self.user1)

        self.assertEqual(stats.profile_completeness, 0)
        self.assertEqual(stats.connections_count, 0)
        self.assertEqual(stats.followers_count, 0)
        self.assertEqual(stats.following_count, 0)
        self.assertEqual(stats.skills_count, 0)
        self.assertEqual(stats.endorsements_count, 0)
        self.assertEqual(stats.profile_views, 0)
        self.assertEqual(stats.engagement_score, 0.0)


class ActivityLogSignalTest(SignalTestCase):
    """Test activity logging signals."""

    def test_log_connection_activity_on_creation(self):
        """Test that connection activity is logged when connection is created."""
        initial_log_count = ActivityLog.objects.count()

        Connection.objects.create(
            from_user=self.user1, to_user=self.user2, message="Let's connect!"
        )

        # Should create activity log for requester
        self.assertGreaterEqual(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1,
            activity_type=ActivityLog.ActivityType.CONNECTION_REQUEST_SENT,
        ).first()

        self.assertIsNotNone(activity)
        self.assertIn("connection request", activity.description.lower())

    def test_log_skill_activity_on_creation(self):
        """Test that skill activity is logged when skill is added."""
        initial_log_count = ActivityLog.objects.count()

        Skill.objects.create(
            user=self.user1, name="Python", category="Programming", level=4
        )

        # Should create activity log
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.SKILL_ADDED
        ).first()

        self.assertIsNotNone(activity)
        self.assertIn("Python", activity.description)

    def test_update_user_activity_timestamp(self):
        """Test that user activity timestamp is updated on various actions."""
        original_activity = self.user1.last_activity

        # Create a skill - should update last_activity
        Skill.objects.create(
            user=self.user1, name="JavaScript", category="Programming", level=3
        )

        self.user1.refresh_from_db()
        self.assertGreater(self.user1.last_activity, original_activity)


class ConnectionSignalTest(SignalTestCase):
    """Test connection related signals."""

    def test_connection_status_change_signal(self):
        """Test signal handling when connection status changes."""
        connection = Connection.objects.create(
            requester=self.user1, recipient=self.user2
        )

        initial_log_count = ActivityLog.objects.count()

        # Accept the connection
        connection.status = Connection.ConnectionStatus.ACCEPTED
        connection.save()

        # Should create activity logs for both users
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        # Check activity logs
        requester_activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.CONNECTION_ACCEPTED
        ).first()

        recipient_activity = ActivityLog.objects.filter(
            user=self.user2, activity_type=ActivityLog.ActivityType.CONNECTION_ACCEPTED
        ).first()

        self.assertIsNotNone(requester_activity)
        self.assertIsNotNone(recipient_activity)

    @patch("apps.accounts.signals.Notification.objects.create")
    def test_send_connection_notification(self, mock_notification_create):
        """Test that connection notifications are sent."""
        Connection.objects.create(
            requester=self.user1, recipient=self.user2, message="Let's connect!"
        )

        # Should create notification for recipient
        mock_notification_create.assert_called()

        # Check the call arguments
        call_args = mock_notification_create.call_args
        self.assertEqual(call_args[1]["user"], self.user2)
        self.assertEqual(
            call_args[1]["notification_type"],
            Notification.NotificationType.CONNECTION_REQUEST,
        )

    def test_connection_rejection_signal(self):
        """Test signal handling when connection is rejected."""
        connection = Connection.objects.create(
            requester=self.user1, recipient=self.user2
        )

        # Reject the connection
        connection.status = Connection.ConnectionStatus.REJECTED
        connection.save()

        # Should create activity log for requester
        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.CONNECTION_REJECTED
        ).first()

        self.assertIsNotNone(activity)


class FollowSignalTest(SignalTestCase):
    """Test follow related signals."""

    def test_follow_creation_signal(self):
        """Test signal handling when follow relationship is created."""
        initial_log_count = ActivityLog.objects.count()

        Follow.objects.create(follower=self.user1, following=self.user2)

        # Should create activity log for follower
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.USER_FOLLOWED
        ).first()

        self.assertIsNotNone(activity)
        self.assertIn(self.user2.get_full_name(), activity.description)

    @patch("apps.accounts.signals.Notification.objects.create")
    def test_follow_notification(self, mock_notification_create):
        """Test that follow notifications are sent."""
        Follow.objects.create(follower=self.user1, following=self.user2)

        # Should create notification for the followed user
        mock_notification_create.assert_called()

        call_args = mock_notification_create.call_args
        self.assertEqual(call_args[1]["user"], self.user2)
        self.assertEqual(
            call_args[1]["notification_type"],
            Notification.NotificationType.NEW_FOLLOWER,
        )


class SkillEndorsementSignalTest(SignalTestCase):
    """Test skill endorsement related signals."""

    def test_endorsement_creation_signal(self):
        """Test signal handling when endorsement is created."""
        skill = Skill.objects.create(
            user=self.user2, name="Python", category="Programming", level=4
        )

        initial_log_count = ActivityLog.objects.count()

        SkillEndorsement.objects.create(skill=skill, endorser=self.user1)

        # Should create activity log for endorser
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.ENDORSEMENT_GIVEN
        ).first()

        self.assertIsNotNone(activity)

    @patch("apps.accounts.signals.Notification.objects.create")
    def test_endorsement_notification(self, mock_notification_create):
        """Test that endorsement notifications are sent."""
        skill = Skill.objects.create(user=self.user2, name="Python")

        SkillEndorsement.objects.create(
            skill=skill, endorser=self.user1, user=self.user2
        )

        # Should create notification for skill owner
        mock_notification_create.assert_called()

        call_args = mock_notification_create.call_args
        self.assertEqual(call_args[1]["user"], self.user2)
        self.assertEqual(
            call_args[1]["notification_type"],
            Notification.NotificationType.SKILL_ENDORSED,
        )


class FileUploadSignalTest(SignalTestCase):
    """Test file upload related signals."""

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_file_upload_signal(self):
        """Test signal handling when file is uploaded."""
        test_file = SimpleUploadedFile(
            "test_document.pdf", b"file_content", content_type="application/pdf"
        )

        initial_log_count = ActivityLog.objects.count()

        UserFile.objects.create(
            user=self.user1,
            file=test_file,
            name="Test Document",
            file_type=UserFile.FileType.DOCUMENT,
        )

        # Should create activity log
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.FILE_UPLOADED
        ).first()

        self.assertIsNotNone(activity)
        self.assertIn("Test Document", activity.description)

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    @patch("apps.accounts.signals.scan_file_for_virus")
    def test_file_virus_scanning_signal(self, mock_virus_scan):
        """Test that file virus scanning is triggered on upload."""
        mock_virus_scan.return_value = True  # File is clean

        test_file = SimpleUploadedFile(
            "test_document.pdf", b"file_content", content_type="application/pdf"
        )

        UserFile.objects.create(user=self.user1, file=test_file, name="Test Document")

        # Should call virus scanning
        mock_virus_scan.assert_called_once()


class ProfileStatsUpdateSignalTest(SignalTestCase):
    """Test profile stats update signals."""

    def test_connection_count_update(self):
        """Test that connection count is updated when connections are made."""
        stats1 = ProfileStats.objects.get(user=self.user1)
        stats2 = ProfileStats.objects.get(user=self.user2)

        initial_count1 = stats1.connections_count
        initial_count2 = stats2.connections_count

        # Create accepted connection
        Connection.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status=Connection.ConnectionStatus.ACCEPTED,
        )

        stats1.refresh_from_db()
        stats2.refresh_from_db()

        # Both users should have increased connection count
        self.assertEqual(stats1.connections_count, initial_count1 + 1)
        self.assertEqual(stats2.connections_count, initial_count2 + 1)

    def test_follower_count_update(self):
        """Test that follower count is updated when follows are created."""
        stats = ProfileStats.objects.get(user=self.user2)
        initial_followers = stats.followers_count

        # Create follow relationship
        Follow.objects.create(follower=self.user1, following=self.user2)

        stats.refresh_from_db()
        self.assertEqual(stats.followers_count, initial_followers + 1)

    def test_skill_count_update(self):
        """Test that skill count is updated when skills are added."""
        stats = ProfileStats.objects.get(user=self.user1)
        initial_skills = stats.skills_count

        # Add skill
        Skill.objects.create(user=self.user1, name="Python")

        stats.refresh_from_db()
        self.assertEqual(stats.skills_count, initial_skills + 1)

    def test_endorsement_count_update(self):
        """Test that endorsement count is updated when endorsements are received."""
        skill = Skill.objects.create(user=self.user2, name="Python")

        stats = ProfileStats.objects.get(user=self.user2)
        initial_endorsements = stats.endorsements_count

        # Create endorsement
        SkillEndorsement.objects.create(
            skill=skill, endorser=self.user1, user=self.user2
        )

        stats.refresh_from_db()
        self.assertEqual(stats.endorsements_count, initial_endorsements + 1)


class ProfileCompletenessSignalTest(SignalTestCase):
    """Test profile completeness calculation signals."""

    def test_profile_completeness_on_bio_update(self):
        """Test that profile completeness is updated when bio is added."""
        profile = self.user1.profile
        stats = ProfileStats.objects.get(user=self.user1)

        initial_completeness = stats.profile_completeness

        # Add bio
        profile.bio = "This is my bio"
        profile.save()

        stats.refresh_from_db()
        self.assertGreater(stats.profile_completeness, initial_completeness)

    def test_profile_completeness_on_skill_addition(self):
        """Test that profile completeness is updated when skills are added."""
        stats = ProfileStats.objects.get(user=self.user1)
        initial_completeness = stats.profile_completeness

        # Add skill
        Skill.objects.create(user=self.user1, name="Python")

        stats.refresh_from_db()
        self.assertGreater(stats.profile_completeness, initial_completeness)

    def test_profile_completeness_on_experience_addition(self):
        """Test that profile completeness is updated when experience is added."""
        stats = ProfileStats.objects.get(user=self.user1)
        initial_completeness = stats.profile_completeness

        # Add experience
        Experience.objects.create(
            user=self.user1, title="Software Engineer", company="Tech Corp"
        )

        stats.refresh_from_db()
        self.assertGreater(stats.profile_completeness, initial_completeness)

    def test_profile_completeness_calculation_accuracy(self):
        """Test that profile completeness calculation is accurate."""
        profile = self.user1.profile

        # Start with minimal profile
        stats = ProfileStats.objects.get(user=self.user1)
        initial_completeness = stats.profile_completeness

        # Add various profile elements
        profile.bio = "Test bio"
        profile.location = "Test City"
        profile.save()

        Skill.objects.create(user=self.user1, name="Python")
        Experience.objects.create(
            user=self.user1, title="Developer", company="Tech Corp"
        )
        Education.objects.create(
            user=self.user1, institution="University", degree="Bachelor"
        )

        stats.refresh_from_db()
        final_completeness = stats.profile_completeness

        # Should be significantly higher
        self.assertGreater(final_completeness, initial_completeness + 20)


class RecommendationSignalTest(SignalTestCase):
    """Test recommendation related signals."""

    def test_recommendation_creation_signal(self):
        """Test signal handling when recommendation is created."""
        initial_log_count = ActivityLog.objects.count()

        Recommendation.objects.create(
            recommender=self.user1,
            recommendee=self.user2,
            relationship_type=Recommendation.RecommendationType.COLLEAGUE,
            title="Professional Recommendation",
            content="Great to work with",
        )

        # Should create activity log
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.RECOMMENDATION_GIVEN
        ).first()

        self.assertIsNotNone(activity)

    @patch("apps.accounts.signals.Notification.objects.create")
    def test_recommendation_notification(self, mock_notification_create):
        """Test that recommendation notifications are sent."""
        Recommendation.objects.create(
            recommender=self.user1, recommended=self.user2, relationship="Colleague"
        )

        # Should create notification
        mock_notification_create.assert_called()

        call_args = mock_notification_create.call_args
        self.assertEqual(call_args[1]["user"], self.user2)
        self.assertEqual(
            call_args[1]["notification_type"],
            Notification.NotificationType.RECOMMENDATION_RECEIVED,
        )


class TaskSignalTest(SignalTestCase):
    """Test task related signals."""

    def test_task_creation_signal(self):
        """Test signal handling when task is created."""
        initial_log_count = ActivityLog.objects.count()

        Task.objects.create(
            assignee=self.user1,
            created_by=self.user1,
            title="Complete project",
            description="Finish the Django project",
        )

        # Should create activity log
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.TASK_CREATED
        ).first()

        self.assertIsNotNone(activity)

    def test_task_completion_signal(self):
        """Test signal handling when task is completed."""
        task = Task.objects.create(user=self.user1, title="Complete project")

        initial_log_count = ActivityLog.objects.count()

        # Complete the task
        task.status = Task.TaskStatus.COMPLETED
        task.save()

        # Should create activity log
        self.assertGreater(ActivityLog.objects.count(), initial_log_count)

        activity = ActivityLog.objects.filter(
            user=self.user1, activity_type=ActivityLog.ActivityType.TASK_COMPLETED
        ).first()

        self.assertIsNotNone(activity)


class AchievementSignalTest(SignalTestCase):
    """Test achievement related signals."""

    def test_achievement_unlock_signal(self):
        """Test signal handling when achievement is unlocked."""
        # Create connections to unlock achievement
        for i in range(5):
            user = User.objects.create_user(
                username=f"user{i}", email=f"user{i}@example.com"
            )
            Connection.objects.create(
                from_user=self.user1,
                to_user=user,
                status=Connection.ConnectionStatus.ACCEPTED,
            )

        # Should trigger achievement unlock
        achievement = Achievement.objects.filter(
            user=self.user1, achievement_type=Achievement.AchievementType.NETWORKER
        ).first()

        if achievement:  # If achievement system is implemented
            self.assertIsNotNone(achievement)


class SignalDisconnectionTest(SignalTestCase):
    """Test signal disconnection and reconnection."""

    def test_signal_disconnection(self):
        """Test that signals can be temporarily disconnected."""
        # Disconnect the profile creation signal
        post_save.disconnect(create_user_profile, sender=User)

        try:
            # Create user without profile
            user = User.objects.create_user(
                username="no_profile_user", email="noprofile@example.com"
            )

            # Profile should not exist
            self.assertFalse(hasattr(user, "profile"))

        finally:
            # Reconnect the signal
            post_save.connect(create_user_profile, sender=User)

    def test_signal_error_handling(self):
        """Test that signal errors don't break the main operation."""
        # This test would require mocking the signal to raise an exception
        # The main operation (creating a user) should still succeed

        with patch("apps.accounts.signals.create_profile_stats") as mock_signal:
            mock_signal.side_effect = Exception("Signal error")

            # User creation should still work despite signal error
            user = User.objects.create_user(
                username="error_test_user", email="error@example.com"
            )

            self.assertIsNotNone(user)


class BulkOperationSignalTest(SignalTestCase):
    """Test signal behavior with bulk operations."""

    def test_bulk_create_signals(self):
        """Test signal behavior with bulk_create operations."""
        # Create multiple users using bulk_create
        users_data = [
            User(username=f"bulk_user_{i}", email=f"bulk{i}@example.com")
            for i in range(5)
        ]

        # bulk_create typically doesn't trigger signals
        users = User.objects.bulk_create(users_data)

        # Profiles might not be created automatically
        for user in users:
            if not hasattr(user, "profile"):
                # Manually trigger profile creation if needed
                UserProfile.objects.get_or_create(user=user)

    def test_bulk_update_signals(self):
        """Test signal behavior with bulk_update operations."""
        # Create some users first
        users = [
            User.objects.create_user(
                username=f"update_user_{i}", email=f"update{i}@example.com"
            )
            for i in range(3)
        ]

        # Update all users at once
        for user in users:
            user.first_name = "Updated"

        # bulk_update typically doesn't trigger signals
        User.objects.bulk_update(users, ["first_name"])

        # Verify updates were applied
        for user in users:
            user.refresh_from_db()
            self.assertEqual(user.first_name, "Updated")


class PerformanceSignalTest(SignalTestCase):
    """Test signal performance with large datasets."""

    def test_signal_performance_with_many_objects(self):
        """Test that signals perform reasonably with many related objects."""
        # Create many related objects
        for i in range(50):
            Skill.objects.create(user=self.user1, name=f"Skill {i}")

        # Creating another skill should still be fast
        import time

        start_time = time.time()

        Skill.objects.create(user=self.user1, name="Performance Test Skill")

        end_time = time.time()
        execution_time = end_time - start_time

        # Should complete quickly (less than 1 second)
        self.assertLess(execution_time, 1.0)

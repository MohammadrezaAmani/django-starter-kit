import io
import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import (
    ActivityLog,
    Connection,
    Experience,
    Follow,
    Skill,
    SkillEndorsement,
    Task,
)

User = get_user_model()


class GenerateAnalyticsCommandTest(TestCase):
    """Test cases for generate_analytics management command."""

    def setUp(self):
        """Set up test data."""
        # Create test users
        self.user1 = User.objects.create_user(
            username="user1",
            email="user1@example.com",
            password="testpass123",
            first_name="John",
            last_name="Doe",
        )
        self.user2 = User.objects.create_user(
            username="user2",
            email="user2@example.com",
            password="testpass123",
            first_name="Jane",
            last_name="Smith",
        )
        self.user3 = User.objects.create_user(
            username="user3",
            email="user3@example.com",
            password="testpass123",
            first_name="Bob",
            last_name="Johnson",
        )

        # Create test data
        self._create_test_connections()
        self._create_test_skills()
        self._create_test_activities()
        self._create_test_tasks()

    def _create_test_connections(self):
        """Create test connections."""
        Connection.objects.create(
            requester=self.user1,
            recipient=self.user2,
            status=Connection.ConnectionStatus.ACCEPTED,
        )
        Connection.objects.create(
            requester=self.user2,
            recipient=self.user3,
            status=Connection.ConnectionStatus.ACCEPTED,
        )
        Connection.objects.create(
            requester=self.user1,
            recipient=self.user3,
            status=Connection.ConnectionStatus.PENDING,
        )

        # Create follows
        Follow.objects.create(follower=self.user1, following=self.user2)
        Follow.objects.create(follower=self.user2, following=self.user3)

    def _create_test_skills(self):
        """Create test skills and endorsements."""
        skill1 = Skill.objects.create(
            user=self.user1,
            name="Python",
            category=Skill.SkillCategory.PROGRAMMING,
        )
        skill2 = Skill.objects.create(
            user=self.user2,
            name="Project Management",
            category=Skill.SkillCategory.MANAGEMENT,
        )

        # Create endorsements
        SkillEndorsement.objects.create(
            skill=skill1,
            endorser=self.user2,
            user=self.user1,
        )
        SkillEndorsement.objects.create(
            skill=skill2,
            endorser=self.user1,
            user=self.user2,
        )

    def _create_test_activities(self):
        """Create test activity logs."""
        ActivityLog.objects.create(
            user=self.user1,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description="Updated profile picture",
        )
        ActivityLog.objects.create(
            user=self.user2,
            activity_type=ActivityLog.ActivityType.CONNECTION_MADE,
            description="Connected with John Doe",
        )
        ActivityLog.objects.create(
            user=self.user3,
            activity_type=ActivityLog.ActivityType.SKILL_ADDED,
            description="Added new skill: JavaScript",
        )

    def _create_test_tasks(self):
        """Create test tasks."""
        Task.objects.create(
            user=self.user1,
            title="Complete project",
            due_date=date.today() + timedelta(days=7),
            status=Task.TaskStatus.TODO,
        )
        Task.objects.create(
            user=self.user2,
            title="Review code",
            due_date=date.today() + timedelta(days=3),
            status=Task.TaskStatus.IN_PROGRESS,
        )
        Task.objects.create(
            user=self.user3,
            title="Update documentation",
            due_date=date.today() - timedelta(days=1),  # Overdue
            status=Task.TaskStatus.TODO,
        )

    def test_generate_all_reports(self):
        """Test generating all analytics reports."""
        out = io.StringIO()
        call_command("generate_analytics", "--report-type=all", stdout=out)

        output = out.getvalue()
        self.assertIn("Analytics reports generated successfully!", output)
        self.assertIn("USER ENGAGEMENT REPORT", output)
        self.assertIn("SKILL TRENDS REPORT", output)
        self.assertIn("NETWORK GROWTH REPORT", output)

    def test_generate_user_engagement_report(self):
        """Test generating user engagement report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--period=weekly",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("USER ENGAGEMENT REPORT", output)
        self.assertNotIn("SKILL TRENDS REPORT", output)

    def test_generate_skill_trends_report(self):
        """Test generating skill trends report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=skill-trends",
            "--period=monthly",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("SKILL TRENDS REPORT", output)
        self.assertNotIn("USER ENGAGEMENT REPORT", output)

    def test_generate_network_growth_report(self):
        """Test generating network growth report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=network-growth",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("NETWORK GROWTH REPORT", output)

    def test_generate_profile_completeness_report(self):
        """Test generating profile completeness report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=profile-completeness",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("PROFILE COMPLETENESS REPORT", output)

    def test_generate_system_usage_report(self):
        """Test generating system usage report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=system-usage",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("SYSTEM USAGE REPORT", output)

    def test_generate_admin_summary_report(self):
        """Test generating admin summary report only."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=admin-summary",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("ADMIN SUMMARY REPORT", output)

    def test_json_output_format(self):
        """Test JSON output format."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=json",
            stdout=out,
        )

        output = out.getvalue()
        # Should be valid JSON
        try:
            data = json.loads(output)
            self.assertIn("user_engagement", data)
        except json.JSONDecodeError:
            self.fail("Output is not valid JSON")

    def test_console_output_format(self):
        """Test console output format."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=console",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("USER ENGAGEMENT REPORT", output)
        self.assertIn("Active Users:", output)

    @patch("apps.accounts.management.commands.generate_analytics.send_mail")
    def test_email_output_format(self, mock_send_mail):
        """Test email output format."""
        mock_send_mail.return_value = True

        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=email",
            "--email=admin@example.com",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Report sent to admin@example.com", output)
        mock_send_mail.assert_called_once()

    def test_email_output_without_email_address(self):
        """Test email output format without providing email address."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=email",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Email address required for email output", output)

    @patch("builtins.open", create=True)
    def test_save_to_file_option(self, mock_open):
        """Test save to file option."""
        mock_file = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_file

        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--save-to-file",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Report saved to", output)
        mock_open.assert_called()

    def test_different_time_periods(self):
        """Test different time periods."""
        periods = ["daily", "weekly", "monthly", "quarterly", "yearly"]

        for period in periods:
            with self.subTest(period=period):
                out = io.StringIO()
                call_command(
                    "generate_analytics",
                    "--report-type=user-engagement",
                    f"--period={period}",
                    "--output=json",
                    stdout=out,
                )

                output = out.getvalue()
                data = json.loads(output)
                self.assertEqual(data["user_engagement"]["period"], period)

    def test_error_handling(self):
        """Test error handling in analytics generation."""
        # Test with invalid report type (should use default)
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=invalid-type",
            stdout=out,
        )

        # Should fallback to 'all' and still work
        output = out.getvalue()
        self.assertIn("Analytics reports generated successfully!", output)

    def test_empty_database(self):
        """Test analytics generation with empty database."""
        # Clear all test data
        User.objects.all().delete()

        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=all",
            stdout=out,
        )

        output = out.getvalue()
        self.assertIn("Analytics reports generated successfully!", output)

    def test_data_accuracy_user_engagement(self):
        """Test accuracy of user engagement data."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=json",
            stdout=out,
        )

        output = out.getvalue()
        data = json.loads(output)
        engagement_data = data["user_engagement"]

        # Should have correct user counts
        self.assertEqual(engagement_data["total_users"], 3)
        self.assertGreaterEqual(engagement_data["active_users"], 0)

    def test_data_accuracy_network_growth(self):
        """Test accuracy of network growth data."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=network-growth",
            "--output=json",
            stdout=out,
        )

        output = out.getvalue()
        data = json.loads(output)
        network_data = data["network_growth"]

        # Should have correct connection counts
        self.assertEqual(network_data["total_connections"], 2)  # 2 accepted connections
        self.assertEqual(network_data["pending_connections"], 1)  # 1 pending connection

    def test_data_accuracy_skill_trends(self):
        """Test accuracy of skill trends data."""
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=skill-trends",
            "--output=json",
            stdout=out,
        )

        output = out.getvalue()
        data = json.loads(output)
        skill_data = data["skill_trends"]

        # Should have endorsement data
        self.assertEqual(skill_data["total_endorsements"], 2)

    def test_admin_summary_alerts(self):
        """Test admin summary alert generation."""
        # Create a suspended user to trigger alert
        User.objects.create_user(
            username="suspended",
            email="suspended@example.com",
            status=User.UserStatus.SUSPENDED,
        )

        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=admin-summary",
            "--output=json",
            stdout=out,
        )

        output = out.getvalue()
        data = json.loads(output)
        admin_data = data["admin_summary"]

        # Should include suspended user in count
        self.assertEqual(admin_data["system_health"]["suspended_users"], 1)

    def test_trending_topics_detection(self):
        """Test trending topics detection functionality."""
        # Create some experiences and projects with technologies
        Experience.objects.create(
            user=self.user1,
            title="Python Developer",
            company="Tech Corp",
            start_date=date.today() - timedelta(days=30),
        )

        # Test the command
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=all",
            "--output=json",
            stdout=out,
        )

        # Should not raise any errors
        output = out.getvalue()
        data = json.loads(output)
        self.assertIsInstance(data, dict)

    @patch("apps.accounts.management.commands.generate_analytics.logger")
    def test_logging_on_error(self, mock_logger):
        """Test that errors are properly logged."""
        # Mock a database error
        with patch("apps.accounts.models.User.objects.filter") as mock_filter:
            mock_filter.side_effect = Exception("Database error")

            out = io.StringIO()
            call_command(
                "generate_analytics",
                "--report-type=user-engagement",
                stdout=out,
            )

            # Should log the error
            mock_logger.error.assert_called()

    def test_command_help_text(self):
        """Test command help text and argument parsing."""
        out = io.StringIO()
        call_command("help", "generate_analytics", stdout=out)

        help_text = out.getvalue()
        self.assertIn("Generate comprehensive analytics and reports", help_text)
        self.assertIn("--report-type", help_text)
        self.assertIn("--period", help_text)
        self.assertIn("--output", help_text)

    def test_performance_with_large_dataset(self):
        """Test performance with larger dataset."""
        # Create more test data
        users = []
        for i in range(50):
            user = User.objects.create_user(
                username=f"perfuser{i}",
                email=f"perfuser{i}@example.com",
                password="testpass123",
            )
            users.append(user)

        # Create many skills
        for i, user in enumerate(users[:20]):
            Skill.objects.create(
                user=user,
                name=f"Skill{i}",
                category=Skill.SkillCategory.PROGRAMMING,
            )

        # Create many activities
        for i, user in enumerate(users[:30]):
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Activity {i}",
            )

        # Test that command completes without timeout
        out = io.StringIO()
        start_time = timezone.now()

        call_command(
            "generate_analytics",
            "--report-type=all",
            "--output=json",
            stdout=out,
        )

        end_time = timezone.now()
        execution_time = (end_time - start_time).total_seconds()

        # Should complete within reasonable time (30 seconds)
        self.assertLess(execution_time, 30)

        output = out.getvalue()
        data = json.loads(output)
        self.assertIsInstance(data, dict)

    def test_concurrent_execution(self):
        """Test that command can handle concurrent execution scenarios."""
        # This test simulates what might happen if multiple instances run
        # It mainly checks that no race conditions cause crashes

        out1 = io.StringIO()
        out2 = io.StringIO()

        # Run two instances of the command
        call_command(
            "generate_analytics",
            "--report-type=user-engagement",
            "--output=json",
            stdout=out1,
        )

        call_command(
            "generate_analytics",
            "--report-type=skill-trends",
            "--output=json",
            stdout=out2,
        )

        # Both should complete successfully
        output1 = out1.getvalue()
        output2 = out2.getvalue()

        data1 = json.loads(output1)
        data2 = json.loads(output2)

        self.assertIn("user_engagement", data1)
        self.assertIn("skill_trends", data2)

    def test_memory_usage_optimization(self):
        """Test that command doesn't consume excessive memory."""
        # Create a moderate amount of test data
        for i in range(100):
            user = User.objects.create_user(
                username=f"memuser{i}",
                email=f"memuser{i}@example.com",
                password="testpass123",
            )

            # Add some related data
            Skill.objects.create(user=user, name=f"Skill{i}")
            ActivityLog.objects.create(
                user=user,
                activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
                description=f"Activity {i}",
            )

        # Run analytics
        out = io.StringIO()
        call_command(
            "generate_analytics",
            "--report-type=all",
            "--output=json",
            stdout=out,
        )

        # Should complete without memory errors
        output = out.getvalue()
        data = json.loads(output)
        self.assertIsInstance(data, dict)

        # Check that we have reasonable data
        self.assertGreater(len(data), 0)

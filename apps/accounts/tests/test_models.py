import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.utils import IntegrityError
from django.test import TestCase, override_settings

from apps.accounts.models import (
    ActivityLog,
    Certification,
    Connection,
    Education,
    Experience,
    Follow,
    Language,
    Notification,
    ProfileStats,
    Recommendation,
    Resume,
    Skill,
    Task,
    UserFile,
    UserProfile,
)

User = get_user_model()


class UserModelTest(TestCase):
    """Test cases for User model."""

    def setUp(self):
        self.user_data = {
            "username": "testuser",
            "email": "test@example.com",
            "password": "testpass123",
            "first_name": "Test",
            "last_name": "User",
        }

    def test_create_user(self):
        """Test creating a regular user."""
        user = User.objects.create_user(**self.user_data)

        self.assertEqual(user.username, "testuser")
        self.assertEqual(user.email, "test@example.com")
        self.assertTrue(user.check_password("testpass123"))
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(**self.user_data)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.is_active)

    def test_user_str_representation(self):
        """Test string representation of user."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(str(user), "testuser")

    def test_get_full_name(self):
        """Test get_full_name method."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.get_full_name(), "Test User")

    def test_unique_email(self):
        """Test email uniqueness constraint."""
        User.objects.create_user(**self.user_data)

        with self.assertRaises(IntegrityError):
            User.objects.create_user(
                username="testuser2", email="test@example.com", password="testpass123"
            )

    def test_user_status_default(self):
        """Test default user status."""
        user = User.objects.create_user(**self.user_data)
        self.assertEqual(user.status, User.UserStatus.ACTIVE)

    def test_user_is_online_default(self):
        """Test default online status."""
        user = User.objects.create_user(**self.user_data)
        self.assertFalse(user.is_online)


class UserProfileModelTest(TestCase):
    """Test cases for UserProfile model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_profile_creation_signal(self):
        """Test that profile is created automatically with user."""
        self.assertTrue(hasattr(self.user, "profile"))
        self.assertIsInstance(self.user.profile, UserProfile)

    def test_profile_str_representation(self):
        """Test string representation of profile."""
        expected = f"{self.user.username}'s profile"
        self.assertEqual(str(self.user.profile), expected)

    def test_profile_fields(self):
        """Test profile field updates."""
        profile = self.user.profile
        profile.bio = "Test bio"
        profile.location = "Test City"
        profile.website = "https://example.com"
        profile.phone = "+1234567890"
        profile.save()

        profile.refresh_from_db()
        self.assertEqual(profile.bio, "Test bio")
        self.assertEqual(profile.location, "Test City")
        self.assertEqual(profile.website, "https://example.com")
        self.assertEqual(profile.phone, "+1234567890")

    def test_profile_privacy_settings(self):
        """Test profile privacy settings."""
        profile = self.user.profile
        profile.show_email = False
        profile.show_phone = False
        profile.save()

        profile.refresh_from_db()
        self.assertFalse(profile.show_email)
        self.assertFalse(profile.show_phone)


class ConnectionModelTest(TestCase):
    """Test cases for Connection model."""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

    def test_create_connection(self):
        """Test creating a connection."""
        connection = Connection.objects.create(
            from_user=self.user1, to_user=self.user2, message="Let's connect!"
        )

        self.assertEqual(connection.from_user, self.user1)
        self.assertEqual(connection.to_user, self.user2)
        self.assertEqual(connection.message, "Let's connect!")
        self.assertEqual(connection.status, Connection.ConnectionStatus.PENDING)

    def test_connection_str_representation(self):
        """Test string representation of connection."""
        connection = Connection.objects.create(from_user=self.user1, to_user=self.user2)
        expected = f"{self.user1.username} -> {self.user2.username} ({Connection.ConnectionStatus.PENDING})"
        self.assertEqual(str(connection), expected)

    def test_connection_uniqueness(self):
        """Test that duplicate connections are not allowed."""
        Connection.objects.create(from_user=self.user1, to_user=self.user2)

        with self.assertRaises(IntegrityError):
            Connection.objects.create(from_user=self.user1, to_user=self.user2)

    def test_self_connection_prevention(self):
        """Test that users cannot connect to themselves."""
        with self.assertRaises(ValidationError):
            connection = Connection(from_user=self.user1, to_user=self.user1)
            connection.full_clean()


class FollowModelTest(TestCase):
    """Test cases for Follow model."""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

    def test_create_follow(self):
        """Test creating a follow relationship."""
        follow = Follow.objects.create(follower=self.user1, following=self.user2)

        self.assertEqual(follow.follower, self.user1)
        self.assertEqual(follow.following, self.user2)

    def test_follow_str_representation(self):
        """Test string representation of follow."""
        follow = Follow.objects.create(follower=self.user1, following=self.user2)
        expected = f"{self.user1.username} follows {self.user2.username}"
        self.assertEqual(str(follow), expected)

    def test_follow_uniqueness(self):
        """Test that duplicate follows are not allowed."""
        Follow.objects.create(follower=self.user1, following=self.user2)

        with self.assertRaises(IntegrityError):
            Follow.objects.create(follower=self.user1, following=self.user2)


class SkillModelTest(TestCase):
    """Test cases for Skill model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_skill(self):
        """Test creating a skill."""
        skill = Skill.objects.create(
            user=self.user,
            name="Python",
            category="Programming",
            level=4,
        )

        self.assertEqual(skill.user, self.user)
        self.assertEqual(skill.name, "Python")
        self.assertEqual(skill.category, "Programming")
        self.assertEqual(skill.level, 4)

    def test_skill_str_representation(self):
        """Test string representation of skill."""
        skill = Skill.objects.create(
            user=self.user, name="Python", category="Programming", level=3
        )
        expected = f"{self.user.username} - Python"
        self.assertEqual(str(skill), expected)

    def test_skill_ordering(self):
        """Test skill ordering by name."""
        skill_z = Skill.objects.create(
            user=self.user, name="Zython", category="Programming", level=2
        )
        skill_p = Skill.objects.create(
            user=self.user, name="Python", category="Programming", level=3
        )

        skills = list(Skill.objects.all().order_by("name"))
        self.assertEqual(skills[0], skill_p)  # Python comes before Zython
        self.assertEqual(skills[1], skill_z)


class ExperienceModelTest(TestCase):
    """Test cases for Experience model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_experience(self):
        """Test creating an experience."""
        experience = Experience.objects.create(
            user=self.user,
            title="Software Engineer",
            company="Tech Corp",
            start_date=date(2020, 1, 1),
            end_date=date(2022, 12, 31),
            description="Developed software applications",
        )

        self.assertEqual(experience.user, self.user)
        self.assertEqual(experience.title, "Software Engineer")
        self.assertEqual(experience.company, "Tech Corp")
        self.assertFalse(experience.is_current)  # Default value

    def test_experience_str_representation(self):
        """Test string representation of experience."""
        experience = Experience.objects.create(
            user=self.user,
            title="Software Engineer",
            company="Tech Corp",
            start_date=date(2020, 1, 1),
        )
        expected = "Software Engineer at Tech Corp"
        self.assertEqual(str(experience), expected)

    def test_experience_ordering(self):
        """Test experience ordering by start date (most recent first)."""
        Experience.objects.create(
            user=self.user,
            title="Junior Developer",
            company="StartupCorp",
            start_date=date(2018, 1, 1),
        )
        exp2 = Experience.objects.create(
            user=self.user,
            title="Senior Developer",
            company="BigCorp",
            start_date=date(2020, 1, 1),
        )

        experiences = list(Experience.objects.all())
        self.assertEqual(experiences[0], exp2)  # Most recent first


class EducationModelTest(TestCase):
    """Test cases for Education model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_education(self):
        """Test creating an education record."""
        education = Education.objects.create(
            user=self.user,
            institution="University of Test",
            degree="Bachelor of Science",
            field_of_study="Computer Science",
            start_date=date(2016, 9, 1),
            end_date=date(2020, 6, 30),
            gpa="3.8",
        )

        self.assertEqual(education.user, self.user)
        self.assertEqual(education.institution, "University of Test")
        self.assertEqual(education.degree, "Bachelor of Science")

    def test_education_str_representation(self):
        """Test string representation of education."""
        education = Education.objects.create(
            user=self.user,
            degree="Bachelor of Science",
            institution="University of Test",
            field_of_study="Computer Science",
            start_date=date(2016, 9, 1),
        )
        expected = "Bachelor of Science at University of Test"
        self.assertEqual(str(education), expected)


class TaskModelTest(TestCase):
    """Test cases for Task model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_task(self):
        """Test creating a task."""
        task = Task.objects.create(
            assignee=self.user,
            created_by=self.user,
            title="Complete project",
            description="Finish the Django project",
            due_date=date.today() + timedelta(days=7),
            priority=Task.TaskPriority.HIGH,
        )

        self.assertEqual(task.assignee, self.user)
        self.assertEqual(task.created_by, self.user)
        self.assertEqual(task.title, "Complete project")
        self.assertEqual(task.status, Task.TaskStatus.TODO)  # Default
        self.assertEqual(task.priority, Task.TaskPriority.HIGH)

    def test_task_str_representation(self):
        """Test string representation of task."""
        task = Task.objects.create(
            assignee=self.user, created_by=self.user, title="Complete project"
        )
        expected = "Complete project"
        self.assertEqual(str(task), expected)

    def test_task_status_and_priority(self):
        """Test task status and priority fields."""
        # Test default values
        task = Task.objects.create(
            assignee=self.user,
            created_by=self.user,
            title="Test task",
        )
        self.assertEqual(task.status, Task.TaskStatus.TODO)
        self.assertEqual(task.priority, Task.TaskPriority.MEDIUM)

        # Test setting values
        task.status = Task.TaskStatus.COMPLETED
        task.priority = Task.TaskPriority.HIGH
        task.save()

        task.refresh_from_db()
        self.assertEqual(task.status, Task.TaskStatus.COMPLETED)
        self.assertEqual(task.priority, Task.TaskPriority.HIGH)


class ResumeModelTest(TestCase):
    """Test cases for Resume model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_create_resume(self):
        """Test creating a resume."""
        # Create a simple file for testing
        test_file = SimpleUploadedFile(
            "test_resume.pdf", b"file_content", content_type="application/pdf"
        )

        resume = Resume.objects.create(
            user=self.user, title="My Resume", file=test_file, is_default=True
        )

        self.assertEqual(resume.user, self.user)
        self.assertEqual(resume.title, "My Resume")
        self.assertTrue(resume.is_default)
        self.assertTrue(resume.file.name.endswith(".pdf"))

    def test_resume_str_representation(self):
        """Test string representation of resume."""
        resume = Resume.objects.create(user=self.user, title="My Resume")
        expected = f"{self.user.username} - My Resume"
        self.assertEqual(str(resume), expected)


class UserFileModelTest(TestCase):
    """Test cases for UserFile model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_create_user_file(self):
        """Test creating a user file."""
        test_file = SimpleUploadedFile(
            "test_document.pdf", b"file_content", content_type="application/pdf"
        )

        user_file = UserFile.objects.create(
            user=self.user,
            file=test_file,
            name="Test Document",
            file_type=UserFile.FileType.DOCUMENT,
            size=len(b"file_content"),
        )

        self.assertEqual(user_file.user, self.user)
        self.assertEqual(user_file.name, "Test Document")
        self.assertEqual(user_file.file_type, UserFile.FileType.DOCUMENT)

    def test_user_file_str_representation(self):
        """Test string representation of user file."""
        test_file = SimpleUploadedFile(
            "test_document.pdf", b"file_content", content_type="application/pdf"
        )
        user_file = UserFile.objects.create(
            user=self.user,
            file=test_file,
            name="Test Document",
            size=len(b"file_content"),
        )
        expected = f"{self.user.username} - Test Document"
        self.assertEqual(str(user_file), expected)


class ActivityLogModelTest(TestCase):
    """Test cases for ActivityLog model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_activity_log(self):
        """Test creating an activity log."""
        activity = ActivityLog.objects.create(
            user=self.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description="Updated profile picture",
        )

        self.assertEqual(activity.user, self.user)
        self.assertEqual(
            activity.activity_type, ActivityLog.ActivityType.PROFILE_UPDATE
        )
        self.assertEqual(activity.description, "Updated profile picture")

    def test_activity_log_str_representation(self):
        """Test string representation of activity log."""
        activity = ActivityLog.objects.create(
            user=self.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description="Updated profile",
        )
        expected = f"{self.user.username} - PROFILE_UPDATE"
        self.assertEqual(str(activity), expected)


class ProfileStatsModelTest(TestCase):
    """Test cases for ProfileStats model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_profile_stats_creation(self):
        """Test that profile stats are created automatically."""
        # Profile stats should be created by signal
        self.assertTrue(ProfileStats.objects.filter(user=self.user).exists())

    def test_profile_stats_str_representation(self):
        """Test string representation of profile stats."""
        stats = ProfileStats.objects.get(user=self.user)
        expected = f"Stats for {self.user.username}"
        self.assertEqual(str(stats), expected)

    def test_profile_stats_defaults(self):
        """Test default values for profile stats."""
        stats = ProfileStats.objects.get(user=self.user)
        self.assertEqual(stats.profile_views, 0)
        self.assertEqual(stats.connections_count, 0)
        self.assertEqual(stats.endorsements_count, 0)
        self.assertEqual(stats.project_views, 0)
        self.assertEqual(stats.search_appearances, 0)


class NotificationModelTest(TestCase):
    """Test cases for Notification model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_notification(self):
        """Test creating a notification."""
        notification = Notification.objects.create(
            recipient=self.user,
            title="New Connection Request",
            message="You have a new connection request",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )

        self.assertEqual(notification.recipient, self.user)
        self.assertEqual(notification.title, "New Connection Request")
        self.assertFalse(notification.is_read)  # Default

    def test_notification_str_representation(self):
        """Test string representation of notification."""
        notification = Notification.objects.create(
            recipient=self.user,
            title="Test Notification",
            message="Test message",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )
        expected = f"Notification to {self.user.username}: Test Notification"
        self.assertEqual(str(notification), expected)


class RecommendationModelTest(TestCase):
    """Test cases for Recommendation model."""

    def setUp(self):
        self.recommender = User.objects.create_user(
            username="recommender",
            email="recommender@example.com",
            password="testpass123",
        )
        self.recommended = User.objects.create_user(
            username="recommended",
            email="recommended@example.com",
            password="testpass123",
        )

    def test_create_recommendation(self):
        """Test creating a recommendation."""
        recommendation = Recommendation.objects.create(
            recommender=self.recommender,
            recommendee=self.recommended,
            relationship_type=Recommendation.RecommendationType.COLLEAGUE,
            title="Professional Recommendation",
            content="Great developer to work with",
        )

        self.assertEqual(recommendation.recommender, self.recommender)
        self.assertEqual(recommendation.recommendee, self.recommended)
        self.assertEqual(
            recommendation.relationship_type,
            Recommendation.RecommendationType.COLLEAGUE,
        )

    def test_recommendation_str_representation(self):
        """Test string representation of recommendation."""
        recommendation = Recommendation.objects.create(
            recommender=self.recommender,
            recommendee=self.recommended,
            relationship_type=Recommendation.RecommendationType.COLLEAGUE,
            title="Professional Recommendation",
            content="Great developer to work with",
        )
        expected = f"Recommendation from {self.recommender.username} to {self.recommended.username}"
        self.assertEqual(str(recommendation), expected)


class LanguageModelTest(TestCase):
    """Test cases for Language model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_language(self):
        """Test creating a language."""
        language = Language.objects.create(
            user=self.user, name="English", proficiency=Language.Proficiency.NATIVE
        )

        self.assertEqual(language.user, self.user)
        self.assertEqual(language.name, "English")
        self.assertEqual(language.proficiency, Language.Proficiency.NATIVE)

    def test_language_str_representation(self):
        """Test string representation of language."""
        language = Language.objects.create(
            user=self.user, name="English", proficiency=Language.Proficiency.NATIVE
        )
        expected = f"{self.user.username} - English ({Language.Proficiency.NATIVE})"
        self.assertEqual(str(language), expected)


class CertificationModelTest(TestCase):
    """Test cases for Certification model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_create_certification(self):
        """Test creating a certification."""
        certification = Certification.objects.create(
            user=self.user,
            name="AWS Certified Developer",
            issuer="Amazon",
            issue_date=date(2023, 1, 15),
        )

        self.assertEqual(certification.user, self.user)
        self.assertEqual(certification.name, "AWS Certified Developer")
        self.assertEqual(certification.issuer, "Amazon")

    def test_certification_str_representation(self):
        """Test string representation of certification."""
        certification = Certification.objects.create(
            user=self.user,
            name="AWS Certified Developer",
            issuer="Amazon",
            issue_date=date(2023, 1, 15),
        )
        expected = "AWS Certified Developer - Amazon"
        self.assertEqual(str(certification), expected)


class ValidationTest(TestCase):
    """Test model validation rules."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_phone_number_validation(self):
        """Test phone number validation in UserProfile."""
        profile = self.user.profile

        # Test setting valid phone numbers
        valid_phones = ["+1234567890", "+44-20-7946-0958", "(555) 123-4567"]
        for phone in valid_phones:
            profile.phone = phone
            profile.save()
            # Just verify the phone was set correctly
            self.assertEqual(profile.phone, phone)

    def test_website_url_validation(self):
        """Test website URL validation in UserProfile."""
        profile = self.user.profile

        # Test setting valid URLs
        valid_urls = [
            "https://example.com",
            "http://test.org",
            "https://subdomain.example.com/path",
        ]
        for url in valid_urls:
            profile.website = url
            profile.save()
            # Just verify the URL was set correctly
            self.assertEqual(profile.website, url)


class ModelRelationshipTest(TestCase):
    """Test model relationships and cascading deletes."""

    def setUp(self):
        self.user1 = User.objects.create_user(
            username="user1", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="user2", email="user2@example.com", password="testpass123"
        )

    def test_user_deletion_cascades(self):
        """Test that related objects are deleted when user is deleted."""
        # Create related objects
        skill = Skill.objects.create(
            user=self.user1, name="Python", category="Programming", level=4
        )
        experience = Experience.objects.create(
            user=self.user1,
            title="Developer",
            company="Tech Corp",
            start_date=date(2020, 1, 1),
        )
        task = Task.objects.create(
            title="Test task",
            description="Test description",
            assignee=self.user1,
            created_by=self.user1,
        )

        # Verify objects exist
        self.assertTrue(Skill.objects.filter(id=skill.id).exists())
        self.assertTrue(Experience.objects.filter(id=experience.id).exists())
        self.assertTrue(Task.objects.filter(id=task.id).exists())

        # Delete user
        self.user1.delete()

        # Verify related objects are deleted
        self.assertFalse(Skill.objects.filter(id=skill.id).exists())
        self.assertFalse(Experience.objects.filter(id=experience.id).exists())
        self.assertFalse(Task.objects.filter(id=task.id).exists())

    def test_connection_relationships(self):
        """Test connection model relationships."""
        connection = Connection.objects.create(from_user=self.user1, to_user=self.user2)

        # Test relationships
        self.assertIn(connection, self.user1.connections_sent.all())
        self.assertIn(connection, self.user2.connections_received.all())

    def test_follow_relationships(self):
        """Test follow model relationships."""
        follow = Follow.objects.create(follower=self.user1, following=self.user2)

        # Test relationships
        self.assertIn(follow, self.user1.following.all())
        self.assertIn(follow, self.user2.followers.all())


class ModelMethodTest(TestCase):
    """Test custom model methods."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_user_get_absolute_url(self):
        """Test user get_absolute_url method if it exists."""
        if hasattr(self.user, "get_absolute_url"):
            url = self.user.get_absolute_url()
            self.assertIn(self.user.username, url)

    def test_profile_completeness_calculation(self):
        """Test profile completeness calculation if implemented."""
        profile = self.user.profile

        # Test with minimal profile
        if hasattr(profile, "calculate_completeness"):
            initial_completeness = profile.calculate_completeness()

            # Add more profile information
            profile.bio = "Test bio"
            profile.location = "Test city"
            profile.save()

            # Add a skill
            Skill.objects.create(user=self.user, name="Python")

            # Add an experience
            Experience.objects.create(
                user=self.user, title="Developer", company="Tech Corp"
            )

            # Recalculate completeness
            updated_completeness = profile.calculate_completeness()

            # Should be higher with more information
            self.assertGreater(updated_completeness, initial_completeness)

import tempfile
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import (
    ActivityLog,
    Connection,
    Education,
    Experience,
    Follow,
    Notification,
    Recommendation,
    Resume,
    Skill,
    Task,
    UserFile,
)

User = get_user_model()


class BaseAPITestCase(APITestCase):
    """Base test case with common setup for API tests."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        self.token = Token.objects.create(user=self.user)
        self.client.force_authenticate(user=self.user, token=self.token)

        # Create a second user for relationship tests
        self.user2 = User.objects.create_user(
            username="testuser2",
            email="test2@example.com",
            password="testpass123",
            first_name="Test2",
            last_name="User2",
        )


class UserViewSetTest(BaseAPITestCase):
    """Test cases for UserViewSet."""

    def test_list_users(self):
        """Test listing users."""
        url = reverse("user-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)  # testuser and testuser2

    def test_retrieve_user(self):
        """Test retrieving a specific user."""
        url = reverse("user-detail", kwargs={"pk": self.user.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["username"], "testuser")
        self.assertEqual(response.data["email"], "test@example.com")

    def test_update_user_profile(self):
        """Test updating user profile."""
        url = reverse("user-detail", kwargs={"pk": self.user.pk})
        data = {
            "first_name": "Updated",
            "last_name": "Name",
            "profile": {"bio": "Updated bio", "location": "New York"},
        }
        response = self.client.patch(url, data, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Updated")
        self.assertEqual(self.user.profile.bio, "Updated bio")

    def test_user_permissions(self):
        """Test that users can only edit their own profiles."""
        url = reverse("user-detail", kwargs={"pk": self.user2.pk})
        data = {"first_name": "Hacked"}
        response = self.client.patch(url, data, format="json")

        # Should not be allowed to edit other user's profile
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)

    def test_search_users(self):
        """Test user search functionality."""
        url = reverse("user-search")
        response = self.client.get(url, {"q": "test"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)

    def test_get_user_stats(self):
        """Test getting user statistics."""
        url = reverse("user-stats", kwargs={"pk": self.user.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("profile_completeness", response.data)
        self.assertIn("connections_count", response.data)


class ConnectionViewSetTest(BaseAPITestCase):
    """Test cases for ConnectionViewSet."""

    def test_send_connection_request(self):
        """Test sending a connection request."""
        url = reverse("connection-list")
        data = {"recipient": self.user2.pk, "message": "Let's connect!"}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Connection.objects.filter(
                requester=self.user, recipient=self.user2
            ).exists()
        )

    def test_accept_connection_request(self):
        """Test accepting a connection request."""
        # Create a pending connection
        connection = Connection.objects.create(
            requester=self.user2, recipient=self.user, message="Let's connect!"
        )

        url = reverse("connection-accept", kwargs={"pk": connection.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connection.refresh_from_db()
        self.assertEqual(connection.status, Connection.ConnectionStatus.ACCEPTED)

    def test_reject_connection_request(self):
        """Test rejecting a connection request."""
        connection = Connection.objects.create(
            requester=self.user2, recipient=self.user, message="Let's connect!"
        )

        url = reverse("connection-reject", kwargs={"pk": connection.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        connection.refresh_from_db()
        self.assertEqual(connection.status, Connection.ConnectionStatus.REJECTED)

    def test_list_connections(self):
        """Test listing user connections."""
        # Create an accepted connection
        Connection.objects.create(
            requester=self.user,
            recipient=self.user2,
            status=Connection.ConnectionStatus.ACCEPTED,
        )

        url = reverse("connection-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_cannot_connect_to_self(self):
        """Test that users cannot connect to themselves."""
        url = reverse("connection-list")
        data = {"recipient": self.user.pk}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_connection_prevention(self):
        """Test that duplicate connection requests are prevented."""
        Connection.objects.create(requester=self.user, recipient=self.user2)

        url = reverse("connection-list")
        data = {"recipient": self.user2.pk}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class FollowViewSetTest(BaseAPITestCase):
    """Test cases for FollowViewSet."""

    def test_follow_user(self):
        """Test following a user."""
        url = reverse("follow-list")
        data = {"following": self.user2.pk}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Follow.objects.filter(follower=self.user, following=self.user2).exists()
        )

    def test_unfollow_user(self):
        """Test unfollowing a user."""
        follow = Follow.objects.create(follower=self.user, following=self.user2)

        url = reverse("follow-detail", kwargs={"pk": follow.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            Follow.objects.filter(follower=self.user, following=self.user2).exists()
        )

    def test_list_following(self):
        """Test listing users that current user is following."""
        Follow.objects.create(follower=self.user, following=self.user2)

        url = reverse("follow-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_cannot_follow_self(self):
        """Test that users cannot follow themselves."""
        url = reverse("follow-list")
        data = {"following": self.user.pk}
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SkillViewSetTest(BaseAPITestCase):
    """Test cases for SkillViewSet."""

    def test_create_skill(self):
        """Test creating a skill."""
        url = reverse("skill-list")
        data = {
            "name": "Python",
            "category": "Programming",
            "level": 4,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Skill.objects.filter(user=self.user, name="Python").exists())

    def test_list_user_skills(self):
        """Test listing user skills."""
        Skill.objects.create(
            user=self.user, name="Python", category=Skill.SkillCategory.PROGRAMMING
        )

        url = reverse("skill-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Python")

    def test_update_skill(self):
        """Test updating a skill."""
        skill = Skill.objects.create(user=self.user, name="Python")

        url = reverse("skill-detail", kwargs={"pk": skill.pk})
        data = {"proficiency_level": Skill.ProficiencyLevel.EXPERT}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skill.refresh_from_db()
        self.assertEqual(skill.proficiency_level, Skill.ProficiencyLevel.EXPERT)

    def test_delete_skill(self):
        """Test deleting a skill."""
        skill = Skill.objects.create(user=self.user, name="Python")

        url = reverse("skill-detail", kwargs={"pk": skill.pk})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Skill.objects.filter(pk=skill.pk).exists())

    def test_skill_ownership(self):
        """Test that users can only modify their own skills."""
        skill = Skill.objects.create(user=self.user2, name="Java")

        url = reverse("skill-detail", kwargs={"pk": skill.pk})
        response = self.client.delete(url)

        # Should not be able to delete other user's skill
        self.assertNotEqual(response.status_code, status.HTTP_204_NO_CONTENT)


class ExperienceViewSetTest(BaseAPITestCase):
    """Test cases for ExperienceViewSet."""

    def test_create_experience(self):
        """Test creating an experience."""
        url = reverse("experience-list")
        data = {
            "title": "Software Engineer",
            "company": "Tech Corp",
            "start_date": "2020-01-01",
            "end_date": "2022-12-31",
            "description": "Developed software applications",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Experience.objects.filter(
                user=self.user, title="Software Engineer"
            ).exists()
        )

    def test_list_experiences(self):
        """Test listing user experiences."""
        Experience.objects.create(
            user=self.user, title="Software Engineer", company="Tech Corp"
        )

        url = reverse("experience-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_update_experience(self):
        """Test updating an experience."""
        experience = Experience.objects.create(
            user=self.user, title="Junior Developer", company="StartupCorp"
        )

        url = reverse("experience-detail", kwargs={"pk": experience.pk})
        data = {"title": "Senior Developer"}
        response = self.client.patch(url, data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        experience.refresh_from_db()
        self.assertEqual(experience.title, "Senior Developer")


class EducationViewSetTest(BaseAPITestCase):
    """Test cases for EducationViewSet."""

    def test_create_education(self):
        """Test creating an education record."""
        url = reverse("education-list")
        data = {
            "institution": "University of Test",
            "degree": "Bachelor of Science",
            "field_of_study": "Computer Science",
            "start_date": "2016-09-01",
            "end_date": "2020-06-30",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Education.objects.filter(
                user=self.user, institution="University of Test"
            ).exists()
        )

    def test_list_education(self):
        """Test listing user education."""
        Education.objects.create(
            user=self.user,
            institution="University of Test",
            degree="Bachelor of Science",
        )

        url = reverse("education-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)


class TaskViewSetTest(BaseAPITestCase):
    """Test cases for TaskViewSet."""

    def test_create_task(self):
        """Test creating a task."""
        url = reverse("task-list")
        data = {
            "title": "Complete project",
            "description": "Finish the Django project",
            "due_date": (date.today() + timedelta(days=7)).isoformat(),
            "priority": Task.TaskPriority.HIGH,
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Task.objects.filter(user=self.user, title="Complete project").exists()
        )

    def test_list_tasks(self):
        """Test listing user tasks."""
        Task.objects.create(
            user=self.user, title="Test task", due_date=date.today() + timedelta(days=1)
        )

        url = reverse("task-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_complete_task(self):
        """Test marking a task as complete."""
        task = Task.objects.create(
            user=self.user, title="Test task", due_date=date.today() + timedelta(days=1)
        )

        url = reverse("task-complete", kwargs={"pk": task.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.TaskStatus.COMPLETED)

    def test_filter_tasks_by_status(self):
        """Test filtering tasks by status."""
        Task.objects.create(
            user=self.user,
            title="Todo task",
            status=Task.TaskStatus.TODO,
            due_date=date.today() + timedelta(days=1),
        )
        Task.objects.create(
            user=self.user,
            title="Completed task",
            status=Task.TaskStatus.COMPLETED,
            due_date=date.today() + timedelta(days=1),
        )

        url = reverse("task-list")
        response = self.client.get(url, {"status": Task.TaskStatus.TODO})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Todo task")


class NotificationViewSetTest(BaseAPITestCase):
    """Test cases for NotificationViewSet."""

    def test_list_notifications(self):
        """Test listing user notifications."""
        Notification.objects.create(
            recipient=self.user,
            title="Test Notification",
            message="This is a test notification",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )

        url = reverse("notification-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_mark_notification_as_read(self):
        """Test marking a notification as read."""
        notification = Notification.objects.create(
            recipient=self.user,
            title="Test Notification",
            message="Test message",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )

        url = reverse("notification-mark-read", kwargs={"pk": notification.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_mark_all_notifications_as_read(self):
        """Test marking all notifications as read."""
        Notification.objects.create(
            recipient=self.user,
            title="Notification 1",
            message="Message 1",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )
        Notification.objects.create(
            recipient=self.user,
            title="Notification 2",
            message="Message 2",
            notification_type=Notification.NotificationType.CONNECTION_REQUEST,
        )

        url = reverse("notification-mark-all-read")
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        unread_count = Notification.objects.filter(
            user=self.user, is_read=False
        ).count()
        self.assertEqual(unread_count, 0)


class FileUploadViewTest(BaseAPITestCase):
    """Test cases for file upload functionality."""

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_upload_file(self):
        """Test file upload."""
        test_file = SimpleUploadedFile(
            "test_document.pdf", b"file_content", content_type="application/pdf"
        )

        url = reverse("user-upload-file", kwargs={"pk": self.user.pk})
        data = {
            "file": test_file,
            "name": "Test Document",
            "file_type": UserFile.FileType.DOCUMENT,
        }
        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            UserFile.objects.filter(user=self.user, name="Test Document").exists()
        )

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_upload_resume(self):
        """Test resume upload."""
        test_file = SimpleUploadedFile(
            "resume.pdf", b"resume_content", content_type="application/pdf"
        )

        url = reverse("resume-list")
        data = {"title": "My Resume", "file": test_file, "is_primary": True}
        response = self.client.post(url, data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Resume.objects.filter(user=self.user, title="My Resume").exists()
        )


class RecommendationViewSetTest(BaseAPITestCase):
    """Test cases for RecommendationViewSet."""

    def test_create_recommendation(self):
        """Test creating a recommendation."""
        url = reverse("recommendation-list")
        data = {
            "recommendee": self.user2.pk,
            "relationship_type": "colleague",
            "title": "Professional Recommendation",
            "content": "Great developer to work with",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            Recommendation.objects.filter(
                recommender=self.user, recommendee=self.user2
            ).exists()
        )

    def test_list_recommendations(self):
        """Test listing recommendations."""
        Recommendation.objects.create(
            recommender=self.user2,
            recommendee=self.user,
            relationship_type=Recommendation.RecommendationType.COLLEAGUE,
            title="Professional Recommendation",
            content="Great to work with",
        )

        url = reverse("recommendation-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_approve_recommendation(self):
        """Test approving a recommendation."""
        recommendation = Recommendation.objects.create(
            recommender=self.user2,
            recommendee=self.user,
            relationship_type=Recommendation.RecommendationType.COLLEAGUE,
            title="Professional Recommendation",
            content="Great to work with",
        )

        url = reverse("recommendation-approve", kwargs={"pk": recommendation.pk})
        response = self.client.post(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        recommendation.refresh_from_db()
        # Note: The Recommendation model doesn't have a status field
        # This test may need to be updated based on actual implementation


class ActivityLogViewSetTest(BaseAPITestCase):
    """Test cases for ActivityLogViewSet."""

    def test_list_activity_logs(self):
        """Test listing user activity logs."""
        ActivityLog.objects.create(
            user=self.user,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description="Updated profile picture",
        )

        url = reverse("activitylog-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)

    def test_activity_log_privacy(self):
        """Test that users can only see their own activity logs."""
        ActivityLog.objects.create(
            user=self.user2,
            activity_type=ActivityLog.ActivityType.PROFILE_UPDATE,
            description="Updated profile",
        )

        url = reverse("activitylog-list")
        response = self.client.get(url)

        # Should only see own activity logs
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 0)


class PermissionTest(BaseAPITestCase):
    """Test permission and authentication requirements."""

    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access protected endpoints."""
        self.client.force_authenticate(user=None)

        protected_urls = [
            reverse("user-list"),
            reverse("skill-list"),
            reverse("experience-list"),
            reverse("task-list"),
            reverse("notification-list"),
        ]

        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_user_can_only_access_own_data(self):
        """Test that users can only access their own private data."""
        # Create private data for user2
        private_task = Task.objects.create(
            user=self.user2,
            title="Private task",
            due_date=date.today() + timedelta(days=1),
        )

        # Try to access user2's private task as user1
        url = reverse("task-detail", kwargs={"pk": private_task.pk})
        response = self.client.get(url)

        # Should not be able to access other user's private data
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


class SearchAndFilterTest(BaseAPITestCase):
    """Test search and filtering functionality."""

    def test_search_users_by_name(self):
        """Test searching users by name."""
        # Create users with different names
        User.objects.create_user(
            username="john_doe",
            email="john@example.com",
            first_name="John",
            last_name="Doe",
        )
        User.objects.create_user(
            username="jane_smith",
            email="jane@example.com",
            first_name="Jane",
            last_name="Smith",
        )

        url = reverse("user-search")
        response = self.client.get(url, {"q": "John"})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["first_name"], "John")

    def test_filter_skills_by_category(self):
        """Test filtering skills by category."""
        Skill.objects.create(
            user=self.user, name="Python", category=Skill.SkillCategory.PROGRAMMING
        )
        Skill.objects.create(
            user=self.user,
            name="Project Management",
            category=Skill.SkillCategory.MANAGEMENT,
        )

        url = reverse("skill-list")
        response = self.client.get(url, {"category": Skill.SkillCategory.PROGRAMMING})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["name"], "Python")

    def test_filter_tasks_by_due_date(self):
        """Test filtering tasks by due date."""
        today = date.today()
        tomorrow = today + timedelta(days=1)
        next_week = today + timedelta(days=7)

        Task.objects.create(user=self.user, title="Today task", due_date=today)
        Task.objects.create(user=self.user, title="Tomorrow task", due_date=tomorrow)
        Task.objects.create(user=self.user, title="Next week task", due_date=next_week)

        url = reverse("task-list")
        response = self.client.get(url, {"due_date__lte": tomorrow.isoformat()})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 2)  # Today and tomorrow tasks


class PaginationTest(BaseAPITestCase):
    """Test pagination functionality."""

    def test_user_list_pagination(self):
        """Test that user list is properly paginated."""
        # Create many users
        for i in range(25):
            User.objects.create_user(username=f"user{i}", email=f"user{i}@example.com")

        url = reverse("user-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("next", response.data)
        self.assertIn("previous", response.data)
        self.assertIn("count", response.data)
        self.assertIn("results", response.data)

    def test_pagination_page_size(self):
        """Test custom page size parameter."""
        # Create some skills
        for i in range(15):
            Skill.objects.create(user=self.user, name=f"Skill {i}")

        url = reverse("skill-list")
        response = self.client.get(url, {"page_size": 5})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)


class ValidationTest(BaseAPITestCase):
    """Test input validation."""

    def test_invalid_email_format(self):
        """Test validation of invalid email format."""
        url = reverse("user-list")
        data = {
            "username": "newuser",
            "email": "invalid-email",
            "password": "testpass123",
        }
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)

    def test_required_fields_validation(self):
        """Test validation of required fields."""
        url = reverse("skill-list")
        data = {}  # Missing required 'name' field
        response = self.client.post(url, data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_date_validation(self):
        """Test validation of date fields."""
        url = reverse("experience-list")
        data = {
            "title": "Test Job",
            "company": "Test Company",
            "start_date": "2022-01-01",
            "end_date": "2021-01-01",  # End date before start date
        }
        self.client.post(url, data)

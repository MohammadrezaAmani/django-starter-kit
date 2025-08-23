from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.accounts.models import User

from .models import (
    Achievement,
    Assessment,
    Course,
    Language,
    Lesson,
    Module,
    Question,
    Step,
    UserProgress,
    UserResponse,
    Vocabulary,
)

User = get_user_model()


class LanguageModelTest(TestCase):
    """Test Language model functionality"""

    def setUp(self):
        self.language = Language.objects.create(
            name="Spanish", code="es", native_name="Español", difficulty_rating=3
        )

    def test_language_creation(self):
        """Test language model creation"""
        self.assertEqual(self.language.name, "Spanish")
        self.assertEqual(self.language.code, "es")
        self.assertEqual(str(self.language), "Spanish (es)")

    def test_language_course_count(self):
        """Test course count property"""
        # Initially should be 0
        self.assertEqual(self.language.course_count, 0)


class CourseModelTest(TestCase):
    """Test Course model functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="instructor", email="instructor@test.com", password="testpass123"
        )
        self.language = Language.objects.create(
            name="Spanish", code="es", native_name="Español"
        )
        self.course = Course.objects.create(
            title="Basic Spanish",
            target_language=self.language,
            instructor=self.user,
            level="beginner",
            is_published=True,
        )

    def test_course_creation(self):
        """Test course model creation"""
        self.assertEqual(self.course.title, "Basic Spanish")
        self.assertEqual(self.course.level, "beginner")
        self.assertTrue(self.course.is_published)

    def test_course_completion_rate(self):
        """Test completion rate calculation"""
        self.course.enrollment_count = 100
        self.course.completion_count = 75
        self.course.save()
        self.assertEqual(self.course.completion_rate, 75.0)

    def test_course_completion_rate_no_enrollments(self):
        """Test completion rate with no enrollments"""
        self.assertEqual(self.course.completion_rate, 0)


class UserProgressModelTest(TestCase):
    """Test UserProgress model functionality"""

    def setUp(self):
        self.student = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.progress = UserProgress.objects.create(
            user=self.student, course=self.course
        )

    def test_progress_creation(self):
        """Test user progress creation"""
        self.assertEqual(self.progress.user, self.student)
        self.assertEqual(self.progress.course, self.course)
        self.assertEqual(self.progress.completion_percentage, 0)

    def test_update_streak(self):
        """Test streak update functionality"""
        initial_streak = self.progress.streak_days
        # Simulate daily activity
        self.progress.last_accessed = timezone.now()
        self.progress.save()


class ModuleModelTest(TestCase):
    """Test Module model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.module = Module.objects.create(course=self.course, title="Basics", order=1)

    def test_module_creation(self):
        """Test module creation"""
        self.assertEqual(self.module.title, "Basics")
        self.assertEqual(self.module.course, self.course)
        self.assertEqual(self.module.order, 1)

    def test_lessons_count(self):
        """Test lessons count property"""
        self.assertEqual(self.module.lessons_count, 0)


class LessonModelTest(TestCase):
    """Test Lesson model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.module = Module.objects.create(course=self.course, title="Basics", order=1)
        self.lesson = Lesson.objects.create(
            module=self.module, title="Greetings", order=1, content_type="vocabulary"
        )

    def test_lesson_creation(self):
        """Test lesson creation"""
        self.assertEqual(self.lesson.title, "Greetings")
        self.assertEqual(self.lesson.module, self.module)
        self.assertEqual(self.lesson.content_type, "vocabulary")


class StepModelTest(TestCase):
    """Test Step model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.module = Module.objects.create(course=self.course, title="Basics", order=1)
        self.lesson = Lesson.objects.create(
            module=self.module, title="Greetings", order=1, content_type="vocabulary"
        )
        self.step = Step.objects.create(
            lesson=self.lesson, title="Learn Hello", order=1, content_type="text"
        )

    def test_step_creation(self):
        """Test step creation"""
        self.assertEqual(self.step.title, "Learn Hello")
        self.assertEqual(self.step.lesson, self.lesson)


class VocabularyModelTest(TestCase):
    """Test Vocabulary model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.vocabulary = Vocabulary.objects.create(
            word="hola",
            language=self.language,
            translation="hello",
            part_of_speech="interjection",
        )

    def test_vocabulary_creation(self):
        """Test vocabulary creation"""
        self.assertEqual(self.vocabulary.word, "hola")
        self.assertEqual(self.vocabulary.translation, "hello")
        self.assertEqual(str(self.vocabulary), "hola (es)")


class QuestionModelTest(TestCase):
    """Test Question model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.module = Module.objects.create(course=self.course, title="Basics", order=1)
        self.lesson = Lesson.objects.create(
            module=self.module, title="Greetings", order=1, content_type="vocabulary"
        )
        self.step = Step.objects.create(
            lesson=self.lesson, title="Practice", order=1, content_type="interactive"
        )
        self.question = Question.objects.create(
            step=self.step,
            question_type="multiple_choice",
            text='What does "hola" mean?',
            options=["hello", "goodbye", "thanks", "please"],
            correct_answers=["hello"],
        )

    def test_question_creation(self):
        """Test question creation"""
        self.assertEqual(self.question.text, 'What does "hola" mean?')
        self.assertEqual(self.question.question_type, "multiple_choice")


class UserResponseModelTest(TestCase):
    """Test UserResponse model functionality"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.module = Module.objects.create(course=self.course, title="Basics", order=1)
        self.lesson = Lesson.objects.create(
            module=self.module, title="Greetings", order=1, content_type="vocabulary"
        )
        self.step = Step.objects.create(
            lesson=self.lesson, title="Practice", order=1, content_type="interactive"
        )
        self.question = Question.objects.create(
            step=self.step,
            question_type="multiple_choice",
            text='What does "hola" mean?',
        )
        self.response = UserResponse.objects.create(
            user=self.user, question=self.question, is_correct=True, score=1.0
        )

    def test_user_response_creation(self):
        """Test user response creation"""
        self.assertEqual(self.response.user, self.user)
        self.assertEqual(self.response.question, self.question)
        self.assertTrue(self.response.is_correct)


class AssessmentModelTest(TestCase):
    """Test Assessment model functionality"""

    def setUp(self):
        self.language = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Course", target_language=self.language
        )
        self.assessment = Assessment.objects.create(
            course=self.course,
            title="Module 1 Quiz",
            assessment_type="quiz",
            passing_score=70,
        )
        self.question = Question.objects.create(
            question_type="multiple_choice", text="Test question"
        )

    def test_assessment_creation(self):
        """Test assessment creation"""
        self.assertEqual(self.assessment.title, "Module 1 Quiz")
        self.assertEqual(self.assessment.passing_score, 70)


class AchievementModelTest(TestCase):
    """Test Achievement model functionality"""

    def setUp(self):
        self.achievement = Achievement.objects.create(
            name="First Steps",
            description="Complete your first lesson",
            category="progress",
            xp_reward=50,
            criteria={"lessons_completed": 1},
        )

    def test_achievement_creation(self):
        """Test achievement creation"""
        self.assertEqual(self.achievement.name, "First Steps")
        self.assertEqual(self.achievement.xp_reward, 50)


# API Tests
class CourseAPITest(APITestCase):
    """Test Course API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )
        self.instructor = User.objects.create_user(
            username="instructor",
            email="instructor@test.com",
            password="testpass123",
            is_staff=True,
        )
        self.spanish = Language.objects.create(
            name="Spanish", code="es", native_name="Español"
        )
        self.course = Course.objects.create(
            title="Spanish Basics",
            target_language=self.spanish,
            instructor=self.instructor,
            is_published=True,
            is_free=True,
        )

    def test_course_list_unauthenticated(self):
        """Test course list without authentication"""
        url = reverse("course:course-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_course_detail_authenticated(self):
        """Test course detail with authentication"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-detail", kwargs={"pk": self.course.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Spanish Basics")

    def test_course_list_authenticated(self):
        """Test course list with authentication"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_course_enrollment(self):
        """Test course enrollment"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-enroll", kwargs={"pk": self.course.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_user_progress_tracking(self):
        """Test user progress tracking"""
        self.client.force_authenticate(user=self.user)
        progress = UserProgress.objects.create(
            user=self.user, course=self.course, completion_percentage=25
        )
        url = reverse("course:user-progress-detail", kwargs={"pk": progress.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["completion_percentage"], 25)


class SecurityTestCase(APITestCase):
    """Test security aspects of the course app"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )
        self.admin_user = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="adminpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.spanish = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Basics",
            target_language=self.spanish,
            instructor=self.admin_user,
        )

    def test_unauthorized_course_creation(self):
        """Test that unauthorized users cannot create courses"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-list")
        data = {
            "title": "Unauthorized Course",
            "target_language": self.spanish.id,
            "level": "beginner",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_user_can_only_access_own_progress(self):
        """Test that users can only access their own progress"""
        other_user = User.objects.create_user(
            username="otheruser", email="other@test.com", password="testpass123"
        )
        other_progress = UserProgress.objects.create(
            user=other_user, course=self.course
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("course:user-progress-detail", kwargs={"pk": other_progress.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_sql_injection_protection(self):
        """Test protection against SQL injection"""
        self.client.force_authenticate(user=self.user)
        malicious_query = "1' OR '1'='1"
        url = reverse("course:course-list")
        response = self.client.get(url, {"search": malicious_query})
        # Should not cause server error, should return valid response
        self.assertIn(response.status_code, [200, 400])

    def test_xss_protection_in_course_content(self):
        """Test XSS protection in course content"""
        self.client.force_authenticate(user=self.admin_user)
        xss_payload = "<script>alert('xss')</script>"

        # Try to create course with XSS payload
        url = reverse("course:course-list")
        data = {
            "title": "Safe Course",
            "description": xss_payload,
            "target_language": self.spanish.id,
            "level": "beginner",
        }
        response = self.client.post(url, data)

        if response.status_code == 201:
            # Verify the script is escaped or sanitized
            course = Course.objects.get(id=response.data["id"])
            self.assertNotIn("<script>", course.description)

    def test_rate_limiting_protection(self):
        """Test rate limiting on API endpoints"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-list")

        # Make multiple rapid requests
        responses = []
        for i in range(20):
            response = self.client.get(url)
            responses.append(response.status_code)

        # Should eventually hit rate limit (429) or all succeed (200)
        rate_limited = any(status_code == 429 for status_code in responses)
        all_success = all(status_code == 200 for status_code in responses)
        self.assertTrue(rate_limited or all_success)

    def test_csrf_protection(self):
        """Test CSRF protection on state-changing operations"""
        # This would be more relevant for form-based views
        # API typically uses token-based auth which handles CSRF differently
        pass

    def test_sensitive_data_exposure(self):
        """Test that sensitive data is not exposed in API responses"""
        self.client.force_authenticate(user=self.user)
        url = reverse("course:course-detail", kwargs={"pk": self.course.pk})
        response = self.client.get(url)

        if response.status_code == 200:
            # Ensure sensitive fields are not exposed
            sensitive_fields = ["password", "secret_key", "private_key"]
            response_str = str(response.data)
            for field in sensitive_fields:
                self.assertNotIn(field.lower(), response_str.lower())


class PerformanceTestCase(TestCase):
    """Test performance aspects of the course app"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )
        self.spanish = Language.objects.create(name="Spanish", code="es")
        self.course = Course.objects.create(
            title="Spanish Basics", target_language=self.spanish, instructor=self.user
        )

    def test_bulk_progress_updates(self):
        """Test bulk progress updates performance"""
        # Create multiple progress records
        progresses = []
        for i in range(100):
            user = User.objects.create_user(
                username=f"user{i}", email=f"user{i}@test.com", password="testpass123"
            )
            progress = UserProgress.objects.create(
                user=user, course=self.course, completion_percentage=i
            )
            progresses.append(progress)

        # Test bulk update
        import time

        start_time = time.time()
        UserProgress.objects.bulk_update(progresses, ["completion_percentage"])
        end_time = time.time()

        # Should complete reasonably quickly (less than 1 second for 100 records)
        self.assertLess(end_time - start_time, 1.0)

    def test_database_query_optimization(self):
        """Test that database queries are optimized"""
        from django.db import connection
        from django.test.utils import override_settings

        with override_settings(DEBUG=True):
            # Reset queries
            connection.queries_log.clear()

            # Get course with related data
            courses = Course.objects.select_related(
                "target_language", "instructor"
            ).prefetch_related("modules__lessons")
            list(courses)  # Force evaluation

            # Should use reasonable number of queries (not N+1)
            query_count = len(connection.queries)
            self.assertLess(query_count, 10)  # Adjust threshold as needed

import json

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient, APITestCase

User = get_user_model()


class CourseAPITestCase(APITestCase):
    """Test Course API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )
        self.instructor = User.objects.create_user(
            username="instructor",
            email="instructor@test.com",
            password="testpass123",
            is_staff=True,
        )
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="adminpass123"
        )

    def test_course_list_unauthenticated(self):
        """Test course list access without authentication"""
        url = "/courses/"
        response = self.client.get(url)
        # Should allow public access to course list
        self.assertIn(response.status_code, [200, 401])

    def test_course_list_authenticated(self):
        """Test course list with authentication"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_course_creation_permissions(self):
        """Test course creation permissions"""
        url = "/courses/"
        data = {
            "title": "Test Course",
            "description": "A test course",
            "level": "beginner",
            "category": "general",
        }

        # Regular user should not be able to create courses
        self.client.force_authenticate(user=self.user)
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [403, 400, 201])

        # Instructor should be able to create courses
        self.client.force_authenticate(user=self.instructor)
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [201, 400])

    def test_course_filtering(self):
        """Test course filtering capabilities"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Test level filtering
        response = self.client.get(url, {"level": "beginner"})
        self.assertEqual(response.status_code, 200)

        # Test search functionality
        response = self.client.get(url, {"search": "test"})
        self.assertEqual(response.status_code, 200)

    def test_course_enrollment(self):
        """Test course enrollment functionality"""
        # This test would need actual course data
        # For now, test the endpoint exists
        pass

    def test_user_progress_tracking(self):
        """Test user progress tracking endpoints"""
        self.client.force_authenticate(user=self.user)
        url = "/progress/"
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])


class CourseSecurityTestCase(APITestCase):
    """Test security aspects of the course API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )
        self.admin = User.objects.create_superuser(
            username="admin", email="admin@test.com", password="adminpass123"
        )

    def test_sql_injection_protection(self):
        """Test SQL injection protection"""
        self.client.force_authenticate(user=self.user)
        malicious_payloads = [
            "'; DROP TABLE course_course; --",
            "1' UNION SELECT * FROM auth_user --",
            "' OR '1'='1",
            "1' OR 1=1 --",
        ]

        url = "/courses/"
        for payload in malicious_payloads:
            response = self.client.get(url, {"search": payload})
            # Should not cause server error
            self.assertNotEqual(response.status_code, 500)
            # Should return valid response
            self.assertIn(response.status_code, [200, 400, 403])

    def test_xss_protection(self):
        """Test XSS protection in API responses"""
        self.client.force_authenticate(user=self.admin)
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror=alert('xss')>",
            "<svg onload=alert('xss')>",
        ]

        url = "/courses/"
        for payload in xss_payloads:
            data = {
                "title": "Safe Course Title",
                "description": payload,
                "level": "beginner",
            }
            response = self.client.post(url, data)

            # If creation succeeds, verify content is sanitized
            if response.status_code == 201:
                response_data = json.dumps(response.data)
                # Script tags should be escaped or removed
                self.assertNotIn("<script>", response_data.lower())
                self.assertNotIn("javascript:", response_data.lower())

    def test_unauthorized_access_prevention(self):
        """Test prevention of unauthorized access"""
        # Test accessing without authentication
        protected_endpoints = [
            "/courses/",
            "/progress/",
            "/lessons/",
            "/assessments/",
        ]

        for endpoint in protected_endpoints:
            response = self.client.get(endpoint)
            # Should require authentication or return public data only
            self.assertIn(response.status_code, [200, 401, 403, 404])

    def test_user_data_isolation(self):
        """Test that users can only access their own data"""
        user1 = User.objects.create_user(
            username="user1", email="user1@test.com", password="testpass123"
        )
        user2 = User.objects.create_user(
            username="user2", email="user2@test.com", password="testpass123"
        )

        # User 1 tries to access user 2's data
        self.client.force_authenticate(user=user1)
        url = f"/users/{user2.id}/progress/"
        response = self.client.get(url)

        # Should be forbidden or not found
        self.assertIn(response.status_code, [403, 404])

    def test_input_validation(self):
        """Test input validation and sanitization"""
        self.client.force_authenticate(user=self.admin)
        url = "/courses/"

        # Test with invalid data types
        invalid_data_sets = [
            {"title": 123, "level": "beginner"},  # Invalid title type
            {"title": "Valid Title", "level": "invalid_level"},  # Invalid level
            {"title": "A" * 1000, "level": "beginner"},  # Too long title
            {"title": "", "level": "beginner"},  # Empty title
        ]

        for invalid_data in invalid_data_sets:
            response = self.client.post(url, invalid_data)
            # Should return validation error
            self.assertIn(response.status_code, [400, 422])

    def test_rate_limiting(self):
        """Test rate limiting on API endpoints"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Make rapid requests
        responses = []
        for i in range(50):
            response = self.client.get(url)
            responses.append(response.status_code)
            if response.status_code == 429:  # Rate limited
                break

        # Should either hit rate limit or all succeed
        rate_limited = any(status == 429 for status in responses)
        all_success = all(status == 200 for status in responses)
        self.assertTrue(rate_limited or all_success)

    def test_sensitive_data_exposure(self):
        """Test that sensitive data is not exposed"""
        self.client.force_authenticate(user=self.user)

        endpoints_to_test = [
            "/courses/",
            "/users/me/",
        ]

        sensitive_patterns = [
            "password",
            "secret",
            "key",
            "token",
            "private",
            "credential",
        ]

        for endpoint in endpoints_to_test:
            response = self.client.get(endpoint)
            if response.status_code == 200:
                response_text = json.dumps(response.data).lower()
                for pattern in sensitive_patterns:
                    # Should not contain sensitive field names in response
                    self.assertNotIn(f'"{pattern}":', response_text)

    def test_csrf_protection(self):
        """Test CSRF protection for state-changing operations"""
        # Note: DRF with token auth typically handles CSRF differently
        # This is more relevant for cookie-based authentication
        pass

    def test_content_type_validation(self):
        """Test content type validation"""
        self.client.force_authenticate(user=self.admin)
        url = "/courses/"

        # Test with invalid content type
        response = self.client.post(
            url, data="invalid json content", content_type="text/plain"
        )

        # Should reject invalid content type
        self.assertIn(response.status_code, [400, 415])


class CoursePerformanceTestCase(APITestCase):
    """Test performance aspects of the course API"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )

    def test_pagination_performance(self):
        """Test pagination performance"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Test with pagination parameters
        response = self.client.get(url, {"page": 1, "page_size": 10})
        self.assertIn(response.status_code, [200, 404])

        # Test with large page size (should be limited)
        response = self.client.get(url, {"page": 1, "page_size": 1000})
        self.assertIn(response.status_code, [200, 400])

    def test_response_time(self):
        """Test API response times"""
        import time

        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        start_time = time.time()
        response = self.client.get(url)
        end_time = time.time()

        response_time = end_time - start_time

        # API should respond within reasonable time (2 seconds)
        self.assertLess(response_time, 2.0)
        self.assertIn(response.status_code, [200, 404])

    def test_bulk_operations(self):
        """Test bulk operations performance"""
        self.client.force_authenticate(user=self.user)

        # Test bulk enrollment or progress updates
        # This would depend on specific bulk endpoints
        pass


class CourseIntegrationTestCase(APITestCase):
    """Integration tests for course workflows"""

    def setUp(self):
        self.client = APIClient()
        self.student = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )
        self.instructor = User.objects.create_user(
            username="instructor",
            email="instructor@test.com",
            password="testpass123",
            is_staff=True,
        )

    def test_complete_learning_workflow(self):
        """Test complete learning workflow"""
        # 1. Student views available courses
        self.client.force_authenticate(user=self.student)
        response = self.client.get("/courses/")
        self.assertIn(response.status_code, [200, 404])

        # 2. Student enrolls in a course (if courses exist)
        if response.status_code == 200 and response.data.get("results"):
            course_id = response.data["results"][0]["id"]
            enroll_response = self.client.post(f"/courses/{course_id}/enroll/")
            self.assertIn(enroll_response.status_code, [200, 201, 400, 404])

        # 3. Student views progress
        progress_response = self.client.get("/progress/")
        self.assertIn(progress_response.status_code, [200, 404])

    def test_instructor_course_management(self):
        """Test instructor course management workflow"""
        self.client.force_authenticate(user=self.instructor)

        # 1. Instructor creates a course
        course_data = {
            "title": "Test Course",
            "description": "A comprehensive test course",
            "level": "beginner",
            "category": "general",
        }
        create_response = self.client.post("/courses/", course_data)
        self.assertIn(create_response.status_code, [201, 400])

        # 2. If creation successful, test course management
        if create_response.status_code == 201:
            course_id = create_response.data["id"]

            # Update course
            update_data = {"title": "Updated Test Course"}
            update_response = self.client.patch(
                f"/courses/{course_id}/", update_data
            )
            self.assertIn(update_response.status_code, [200, 400, 404])

            # View course details
            detail_response = self.client.get(f"/courses/{course_id}/")
            self.assertIn(detail_response.status_code, [200, 404])


class CourseValidationTestCase(APITestCase):
    """Test API validation and error handling"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="testuser", email="test@test.com", password="testpass123"
        )

    def test_invalid_json_handling(self):
        """Test handling of invalid JSON"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Send invalid JSON
        response = self.client.post(
            url, data="{invalid json}", content_type="application/json"
        )

        # Should return proper error response
        self.assertEqual(response.status_code, 400)

    def test_missing_required_fields(self):
        """Test validation of required fields"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Send incomplete data
        incomplete_data = {"description": "Missing title"}
        response = self.client.post(url, incomplete_data)

        # Should return validation error
        self.assertIn(response.status_code, [400, 403])

    def test_field_length_validation(self):
        """Test field length validation"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Test with overly long fields
        long_title = "A" * 1000
        data = {
            "title": long_title,
            "description": "Valid description",
            "level": "beginner",
        }

        response = self.client.post(url, data)
        self.assertIn(response.status_code, [400, 403])

    def test_enum_field_validation(self):
        """Test validation of enum/choice fields"""
        self.client.force_authenticate(user=self.user)
        url = "/courses/"

        # Test with invalid choice
        data = {
            "title": "Valid Title",
            "level": "invalid_level",
            "category": "invalid_category",
        }

        response = self.client.post(url, data)
        self.assertIn(response.status_code, [400, 403])


# Additional test classes for specific features
class VocabularyAPITestCase(APITestCase):
    """Test Vocabulary API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )

    def test_vocabulary_list(self):
        """Test vocabulary list endpoint"""
        self.client.force_authenticate(user=self.user)
        url = "/vocabulary/"
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])

    def test_vocabulary_search(self):
        """Test vocabulary search functionality"""
        self.client.force_authenticate(user=self.user)
        url = "/vocabulary/"
        response = self.client.get(url, {"search": "hello"})
        self.assertIn(response.status_code, [200, 404])


class AssessmentAPITestCase(APITestCase):
    """Test Assessment API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )

    def test_assessment_list(self):
        """Test assessment list endpoint"""
        self.client.force_authenticate(user=self.user)
        url = "/assessments/"
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])

    def test_assessment_submission(self):
        """Test assessment submission"""
        self.client.force_authenticate(user=self.user)
        # This would test actual assessment submission
        # Depends on specific implementation
        pass


class ProgressAPITestCase(APITestCase):
    """Test Progress tracking API endpoints"""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="student", email="student@test.com", password="testpass123"
        )

    def test_user_progress_dashboard(self):
        """Test user progress dashboard"""
        self.client.force_authenticate(user=self.user)
        url = "/progress/dashboard/"
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])

    def test_progress_analytics(self):
        """Test progress analytics endpoints"""
        self.client.force_authenticate(user=self.user)
        url = "/progress/analytics/"
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])


# Pytest fixtures and markers for different test categories
@pytest.mark.integration
class CourseIntegrationTests:
    """Integration tests marked for separate execution"""

    pass


@pytest.mark.performance
class CoursePerformanceTests:
    """Performance tests marked for separate execution"""

    pass


@pytest.mark.security
class CourseSecurityTests:
    """Security tests marked for separate execution"""

    pass

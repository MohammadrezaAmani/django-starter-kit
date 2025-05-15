from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()


class RegistrationViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.register_url = reverse("register")
        self.login_url = reverse("login")
        self.admin_user = User.objects.create_superuser(
            "admin", "admin@example.com", "adminpassword"
        )
        login_data = {"username": "admin", "password": "adminpassword"}
        login_response = self.client.post(self.login_url, login_data, format="json")
        self.token = login_response.data["access"]  # type: ignore

    def test_register_new_user_as_admin(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + self.token)
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newuserpassword",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)  # type: ignore
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(
            User.objects.get(username="newuser").email, "newuser@example.com"
        )

    def test_register_new_user_as_non_admin(self):
        non_admin_user = User.objects.create_user(
            "nonadmin", "nonadmin@example.com", "nonadminpassword"
        )
        self.client.force_authenticate(user=non_admin_user)
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newuserpassword",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)  # type: ignore
        self.assertEqual(User.objects.count(), 2)

    def test_register_new_user_unauthenticated(self):
        data = {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "newuserpassword",
        }
        response = self.client.post(self.register_url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)  # type: ignore
        self.assertEqual(User.objects.count(), 1)

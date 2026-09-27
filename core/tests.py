from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class HomePageTests(TestCase):
    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shared Household Chores")


class UserModelTests(TestCase):
    def test_user_can_be_created_with_email_without_username(self):
        user = User.objects.create_user(" Alice@Example.com ")

        self.assertEqual(user.email, "alice@example.com")
        self.assertEqual(User.USERNAME_FIELD, "email")
        self.assertEqual(User.REQUIRED_FIELDS, [])
        self.assertNotIn("username", {field.name for field in User._meta.fields})
        self.assertFalse(user.has_usable_password())

    def test_manager_rejects_missing_or_blank_email(self):
        for email in (None, "", "   "):
            with self.subTest(email=email):
                with self.assertRaises(ValueError):
                    User.objects.create_user(email)

    def test_model_validation_rejects_blank_email(self):
        user = User(email="   ")

        with self.assertRaises(ValidationError):
            user.full_clean()

    def test_email_address_must_be_unique(self):
        User.objects.create_user("person@example.com")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                User.objects.create_user("PERSON@example.com")

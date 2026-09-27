from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch

from .models import Household, HouseholdMember, SignInLink


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


class HouseholdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("alice@example.com")

    def test_creation_redirects_and_displays_saved_name_and_creator_admin(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("household-create"), {"name": "  Flat 12  "})

        household = Household.objects.get()
        self.assertRedirects(response, reverse("household-detail", args=[household.pk]))
        self.assertContains(self.client.get(response.url), "Flat 12")
        membership = HouseholdMember.objects.get(household=household, user=self.user)
        self.assertEqual(membership.role, HouseholdMember.ADMIN)
        self.assertEqual(household.name, "Flat 12")

    def test_blank_or_whitespace_name_does_not_create_household(self):
        self.client.force_login(self.user)
        for name in ("", "   ", "\t\n"):
            with self.subTest(name=name):
                response = self.client.post(reverse("household-create"), {"name": name})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "A household name is required.")
                self.assertEqual(Household.objects.count(), 0)
                self.assertEqual(HouseholdMember.objects.count(), 0)

    def test_database_prevents_duplicate_membership(self):
        household = Household.objects.create(name="Flat 12")
        HouseholdMember.objects.create(household=household, user=self.user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                HouseholdMember.objects.create(household=household, user=self.user)

    def test_full_clean_rejects_invalid_role(self):
        household = Household.objects.create(name="Flat 12")
        membership = HouseholdMember(household=household, user=self.user, role="owner")
        with self.assertRaises(ValidationError):
            membership.full_clean()

    def test_household_page_access_for_member_anonymous_and_non_member(self):
        household = Household.objects.create(name="Flat 12")
        HouseholdMember.objects.create(household=household, user=self.user)
        url = reverse("household-detail", args=[household.pk])

        self.client.force_login(self.user)
        self.assertContains(self.client.get(url), "Flat 12")

        self.client.logout()
        response = self.client.get(url)
        self.assertRedirects(response, f"{reverse('sign-in')}?next={url}")

        outsider = User.objects.create_user("bob@example.com")
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(url).status_code, 404)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class PasswordlessSignInTests(TestCase):
    def request_link(self, email):
        return self.client.post(reverse("sign-in"), {"email": email})

    def token_from_email(self):
        return mail.outbox[-1].body.split("/sign-in/", 1)[1].splitlines()[0].removesuffix("/")

    def test_known_and_unknown_addresses_get_same_confirmation_and_delivery(self):
        existing = User.objects.create_user("known@example.com")
        responses = []
        for email in (existing.email, "new@example.com"):
            response = self.request_link(email)
            responses.append((response.status_code, response.content))

        self.assertEqual(responses[0], responses[1])
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[0].to, ["known@example.com"])
        self.assertEqual(mail.outbox[1].to, ["new@example.com"])
        self.assertIn("/sign-in/", mail.outbox[0].body)

    def test_blank_and_malformed_addresses_are_rejected_without_mail(self):
        for email in ("", "   ", "not-an-email"):
            with self.subTest(email=email):
                response = self.request_link(email)
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="errorlist"', status_code=200)
        self.assertEqual(mail.outbox, [])

    def test_link_signs_in_existing_user_and_creates_unknown_user(self):
        existing = User.objects.create_user("known@example.com")
        self.request_link(existing.email)
        response = self.client.get(reverse("sign-in-complete", kwargs={"token": self.token_from_email()}))
        self.assertRedirects(response, reverse("home"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), existing.pk)

        self.client.logout()
        self.request_link("new@example.com")
        response = self.client.get(reverse("sign-in-complete", kwargs={"token": self.token_from_email()}))
        self.assertRedirects(response, reverse("home"))
        created = User.objects.get(email="new@example.com")
        self.assertEqual(int(self.client.session["_auth_user_id"]), created.pk)

    def test_link_expires_after_fifteen_minutes(self):
        instant = timezone.now()
        with patch("core.views.timezone.now", return_value=instant):
            self.request_link("person@example.com")
        token = self.token_from_email()
        with patch("core.views.timezone.now", return_value=instant + timedelta(minutes=16)):
            response = self.client.get(reverse("sign-in-complete", kwargs={"token": token}))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "expired", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.filter(email="person@example.com").exists())

    def test_altered_link_is_rejected(self):
        self.request_link("person@example.com")
        token = self.token_from_email()
        altered = token[:-1] + ("a" if token[-1] != "a" else "b")
        response = self.client.get(reverse("sign-in-complete", kwargs={"token": altered}))
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "invalid", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertFalse(User.objects.filter(email="person@example.com").exists())

    def test_link_cannot_be_reused(self):
        self.request_link("person@example.com")
        url = reverse("sign-in-complete", kwargs={"token": self.token_from_email()})
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.logout()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "already been used", status_code=400)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(SignInLink.objects.filter(used_at__isnull=False).count(), 1)

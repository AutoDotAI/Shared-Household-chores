from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core import mail
from django.db import IntegrityError, OperationalError, close_old_connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from threading import Barrier, Thread
from unittest.mock import patch

from .models import Chore, Household, HouseholdMember, SignInLink
from .services import claim_chore


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


class ChoreBoardTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("alice@example.com")
        self.member = User.objects.create_user("bob@example.com")
        self.outsider = User.objects.create_user("eve@example.com")
        self.household = Household.objects.create(name="Flat 12")
        self.other_household = Household.objects.create(name="Other flat")
        HouseholdMember.objects.create(household=self.household, user=self.admin, role=HouseholdMember.ADMIN)
        HouseholdMember.objects.create(household=self.household, user=self.member)
        HouseholdMember.objects.create(household=self.other_household, user=self.outsider)

    def make_chore(self, *, household=None, title="Wash dishes", assignee=None, due_date=None, status=Chore.TODO):
        return Chore.objects.create(
            household=household or self.household,
            title=title,
            assignee=assignee,
            due_date=due_date or timezone.localdate(),
            status=status,
            created_by=self.admin,
        )

    def test_model_allows_open_chore_and_rejects_assignee_from_another_household(self):
        chore = self.make_chore(assignee=None)
        self.assertIsNone(chore.assignee)

        invalid = Chore(
            household=self.household,
            title="Wrong household",
            assignee=self.outsider,
            due_date=timezone.localdate(),
            created_by=self.admin,
        )
        with self.assertRaises(ValidationError) as error:
            invalid.full_clean()
        self.assertIn("assignee", error.exception.message_dict)

    def test_board_groups_todo_cards_and_shows_card_fields_without_other_household_data(self):
        self.make_chore(title="Open job")
        assigned = self.make_chore(title="Bob's job", assignee=self.member)
        self.make_chore(title="Completed job", status=Chore.DONE)
        self.make_chore(household=self.other_household, title="Private job", assignee=self.outsider)

        self.client.force_login(self.admin)
        response = self.client.get(reverse("household-detail", args=[self.household.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Open")
        self.assertContains(response, "alice@example.com")
        self.assertContains(response, "bob@example.com")
        self.assertContains(response, "Open job")
        self.assertContains(response, "Bob&#x27;s job")
        self.assertContains(response, "Assignee: bob@example.com")
        self.assertContains(response, assigned.due_date.strftime("%b %-d, %Y"))
        self.assertContains(response, "Status: To do")
        self.assertNotContains(response, "Completed job")
        self.assertNotContains(response, "Private job")

    def test_overdue_uses_local_date_and_due_today_is_not_overdue(self):
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)
        self.make_chore(title="Late", due_date=yesterday)
        self.make_chore(title="Due now", due_date=today)

        self.client.force_login(self.member)
        response = self.client.get(reverse("household-detail", args=[self.household.pk]))

        self.assertContains(response, "Late")
        self.assertContains(response, 'class="chore-card overdue"')
        self.assertContains(response, "Overdue")
        self.assertContains(response, "Due now")
        self.assertNotContains(response, 'class="chore-card overdue"><h3>Due now')

    def test_open_chores_show_claim_action_and_member_claim_moves_chore_to_member_column(self):
        chore = self.make_chore(title="Claim me")
        self.client.force_login(self.member)
        board_url = reverse("household-detail", args=[self.household.pk])
        response = self.client.get(board_url)
        self.assertContains(response, f'action="{reverse("chore-claim", args=[chore.pk])}"')
        self.assertContains(response, ">Claim</button>")

        response = self.client.post(reverse("chore-claim", args=[chore.pk]))
        self.assertRedirects(response, board_url)
        chore.refresh_from_db()
        self.assertEqual(chore.assignee, self.member)
        board = self.client.get(board_url)
        self.assertContains(board, "Assignee: bob@example.com")
        self.assertNotContains(board, f'action="{reverse("chore-claim", args=[chore.pk])}"')

    def test_claim_is_first_wins_and_never_transfers_an_assignment(self):
        chore = self.make_chore()
        self.client.force_login(self.member)
        self.client.post(reverse("chore-claim", args=[chore.pk]))
        self.client.force_login(self.admin)
        self.client.post(reverse("chore-claim", args=[chore.pk]))
        chore.refresh_from_db()
        self.assertEqual(chore.assignee, self.member)

    def test_claim_lock_contention_returns_false_and_preserves_assignment(self):
        chore = self.make_chore()
        with patch("django.db.models.query.QuerySet.update", side_effect=OperationalError("database is locked")):
            self.assertFalse(claim_chore(chore_id=chore.pk, user=self.member))
        chore.refresh_from_db()
        self.assertIsNone(chore.assignee)

    def test_claim_rejects_done_and_cross_household_chores_without_changes(self):
        done = self.make_chore(title="Done", status=Chore.DONE)
        foreign = self.make_chore(household=self.other_household, title="Foreign", assignee=self.outsider)
        self.client.force_login(self.member)
        self.client.post(reverse("chore-claim", args=[done.pk]))
        done.refresh_from_db()
        self.assertIsNone(done.assignee)
        self.assertEqual(done.status, Chore.DONE)
        response = self.client.post(reverse("chore-claim", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.assignee, self.outsider)

    def test_member_and_admin_can_complete_allowed_chores_and_store_completion_details(self):
        assigned = self.make_chore(title="Assigned", assignee=self.member)
        open_chore = self.make_chore(title="Open")
        instant = timezone.now()
        self.client.force_login(self.member)
        board = self.client.get(reverse("household-detail", args=[self.household.pk]))
        self.assertContains(board, f'action="{reverse("chore-complete", args=[assigned.pk])}"')
        self.assertNotContains(board, f'action="{reverse("chore-complete", args=[open_chore.pk])}"')
        response = self.client.post(reverse("chore-complete", args=[assigned.pk]))
        self.assertRedirects(response, reverse("household-detail", args=[self.household.pk]))
        assigned.refresh_from_db()
        self.assertEqual(assigned.status, Chore.DONE)
        self.assertEqual(assigned.completed_by, self.member)
        self.assertGreaterEqual(assigned.completed_at, instant)

        self.client.force_login(self.admin)
        board = self.client.get(reverse("household-detail", args=[self.household.pk]))
        self.assertContains(board, f'action="{reverse("chore-complete", args=[open_chore.pk])}"')
        self.client.post(reverse("chore-complete", args=[open_chore.pk]))
        open_chore.refresh_from_db()
        self.assertEqual(open_chore.status, Chore.DONE)
        self.assertEqual(open_chore.completed_by, self.admin)
        self.assertIsNotNone(open_chore.completed_at)

    def test_member_cannot_complete_another_members_chore_and_outsider_cannot_access_household_chore(self):
        chore = self.make_chore(title="Bob's job", assignee=self.admin)
        self.client.force_login(self.member)
        board = self.client.get(reverse("household-detail", args=[self.household.pk]))
        self.assertNotContains(board, f'action="{reverse("chore-complete", args=[chore.pk])}"')
        self.client.post(reverse("chore-complete", args=[chore.pk]))
        chore.refresh_from_db()
        self.assertEqual((chore.status, chore.completed_at, chore.completed_by_id), (Chore.TODO, None, None))

        self.client.force_login(self.outsider)
        response = self.client.post(reverse("chore-complete", args=[chore.pk]))
        self.assertEqual(response.status_code, 404)
        chore.refresh_from_db()
        self.assertEqual((chore.status, chore.completed_at, chore.completed_by_id), (Chore.TODO, None, None))

    def test_repeated_completion_does_not_overwrite_completion_details(self):
        chore = self.make_chore(assignee=self.member)
        self.client.force_login(self.member)
        self.client.post(reverse("chore-complete", args=[chore.pk]))
        chore.refresh_from_db()
        original = (chore.status, chore.completed_at, chore.completed_by_id)

        self.client.force_login(self.admin)
        self.client.post(reverse("chore-complete", args=[chore.pk]))
        chore.refresh_from_db()
        self.assertEqual((chore.status, chore.completed_at, chore.completed_by_id), original)

    def test_member_cannot_complete_chore_in_another_household(self):
        foreign = self.make_chore(household=self.other_household, title="Foreign", assignee=self.outsider)
        self.client.force_login(self.member)
        response = self.client.post(reverse("chore-complete", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual((foreign.status, foreign.completed_at, foreign.completed_by_id), (Chore.TODO, None, None))

    def test_outsider_cannot_claim_household_chore(self):
        chore = self.make_chore()
        self.client.force_login(self.outsider)
        response = self.client.post(reverse("chore-claim", args=[chore.pk]))
        self.assertEqual(response.status_code, 404)
        chore.refresh_from_db()
        self.assertIsNone(chore.assignee)

    def test_empty_state_when_household_has_no_todo_chores(self):
        self.make_chore(title="Already done", status=Chore.DONE)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("household-detail", args=[self.household.pk]))

        self.assertContains(response, "There are no chores to do right now.")
        self.assertNotContains(response, "Already done")

    def test_household_access_is_member_only_including_changed_household_id(self):
        url = reverse("household-detail", args=[self.household.pk])
        self.client.force_login(self.member)
        self.assertEqual(self.client.get(url).status_code, 200)

        self.client.force_login(self.outsider)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("household-detail", args=[self.other_household.pk])).status_code,
            200,
        )

    def test_admin_can_create_open_or_assigned_chore_and_board_shows_it(self):
        self.client.force_login(self.admin)
        url = reverse("chore-create", args=[self.household.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"title": "  Sweep floor  ", "due_date": "2026-10-01", "assignee": ""})
        chore = Chore.objects.get()
        self.assertRedirects(response, reverse("household-detail", args=[self.household.pk]))
        self.assertEqual(chore.title, "Sweep floor")
        self.assertEqual(chore.status, Chore.TODO)
        self.assertIsNone(chore.assignee)
        self.assertContains(self.client.get(response.url), "Sweep floor")

        response = self.client.post(url, {"title": "Feed cat", "due_date": "2026-10-02", "assignee": str(self.member.pk)})
        assigned = Chore.objects.get(title="Feed cat")
        self.assertEqual(assigned.assignee, self.member)
        self.assertContains(self.client.get(response.url), "Feed cat")
        self.assertContains(self.client.get(response.url), "Assignee: bob@example.com")
        self.assertContains(self.client.get(response.url), "New chore")
        self.assertContains(self.client.get(response.url), "Edit")
        self.assertContains(self.client.get(response.url), "Delete")
        self.client.force_login(self.member)
        board = self.client.get(response.url)
        self.assertNotContains(board, "New chore")
        self.assertNotContains(board, "Edit")
        self.assertNotContains(board, "Delete")

    def test_admin_can_edit_and_unassign_chore(self):
        chore = self.make_chore(assignee=self.member)
        self.client.force_login(self.admin)
        url = reverse("chore-edit", args=[chore.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        response = self.client.post(url, {"title": "New title", "due_date": "2026-10-03", "assignee": ""})
        self.assertRedirects(response, reverse("household-detail", args=[self.household.pk]))
        chore.refresh_from_db()
        self.assertEqual((chore.title, chore.due_date, chore.assignee), ("New title", timezone.datetime(2026, 10, 3).date(), None))
        self.assertContains(self.client.get(response.url), "New title")
        self.assertContains(self.client.get(response.url), "New title", count=1)

    def test_empty_title_whitespace_title_and_missing_due_date_are_rejected_without_changes(self):
        chore = self.make_chore(title="Original", assignee=self.member)
        original = (chore.title, chore.due_date, chore.assignee_id, chore.status)
        self.client.force_login(self.admin)
        create_url = reverse("chore-create", args=[self.household.pk])
        edit_url = reverse("chore-edit", args=[chore.pk])
        for title, due_date in (("", "2026-10-04"), (" \t ", "2026-10-04"), ("Changed", "")):
            with self.subTest(title=title, due_date=due_date):
                response = self.client.post(create_url, {"title": title, "due_date": due_date, "assignee": ""})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="errorlist"')
                self.assertEqual(Chore.objects.count(), 1)
                response = self.client.post(edit_url, {"title": title, "due_date": due_date, "assignee": str(self.member.pk)})
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'class="errorlist"')
                chore.refresh_from_db()
                self.assertEqual((chore.title, chore.due_date, chore.assignee_id, chore.status), original)

    def test_foreign_assignee_is_rejected_for_create_and_edit(self):
        chore = self.make_chore(title="Original", assignee=self.member)
        self.client.force_login(self.admin)
        for url, title in (
            (reverse("chore-create", args=[self.household.pk]), "Invalid new"),
            (reverse("chore-edit", args=[chore.pk]), "Invalid edit"),
        ):
            response = self.client.post(url, {"title": title, "due_date": "2026-10-05", "assignee": str(self.outsider.pk)})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'class="errorlist"')
            self.assertFalse(Chore.objects.filter(title=title).exists())
        chore.refresh_from_db()
        self.assertEqual((chore.title, chore.assignee_id), ("Original", self.member.pk))

    def test_admin_can_delete_chore(self):
        chore = self.make_chore()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("chore-delete", args=[chore.pk])).status_code, 200)
        response = self.client.post(reverse("chore-delete", args=[chore.pk]))
        self.assertRedirects(response, reverse("household-detail", args=[self.household.pk]))
        self.assertFalse(Chore.objects.filter(pk=chore.pk).exists())
        self.assertNotContains(self.client.get(response.url), "Wash dishes")

    def test_member_and_outsider_cannot_mutate_chore_or_create_it(self):
        chore = self.make_chore(title="Protected", assignee=self.member)
        create_url = reverse("chore-create", args=[self.household.pk])
        edit_url = reverse("chore-edit", args=[chore.pk])
        delete_url = reverse("chore-delete", args=[chore.pk])
        for user in (self.member, self.outsider):
            self.client.force_login(user)
            for method, url in (("post", create_url), ("post", edit_url), ("post", delete_url), ("get", edit_url)):
                response = getattr(self.client, method)(url, {"title": "Tampered", "due_date": "2026-10-06", "assignee": ""})
                self.assertEqual(response.status_code, 404)
            chore.refresh_from_db()
            self.assertEqual((chore.title, chore.assignee_id), ("Protected", self.member.pk))
            self.assertFalse(Chore.objects.filter(title="Tampered").exists())
            self.assertEqual(Chore.objects.count(), 1)


class ConcurrentClaimTests(TransactionTestCase):
    reset_sequences = True

    def test_simultaneous_claimants_produce_one_winner_without_database_lock_error(self):
        admin = User.objects.create_user("admin@example.com")
        first = User.objects.create_user("first@example.com")
        second = User.objects.create_user("second@example.com")
        household = Household.objects.create(name="Flat")
        for user in (admin, first, second):
            HouseholdMember.objects.create(household=household, user=user)
        chore = Chore.objects.create(
            household=household,
            title="Claim race",
            due_date=timezone.localdate(),
            created_by=admin,
        )
        barrier = Barrier(2)
        outcomes = []
        errors = []

        def claim(user_id):
            close_old_connections()
            try:
                user = User.objects.get(pk=user_id)
                barrier.wait()
                outcomes.append(claim_chore(chore_id=chore.pk, user=user))
            except Exception as error:
                errors.append(error)
            finally:
                close_old_connections()

        threads = [Thread(target=claim, args=(user.pk,)) for user in (first, second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(errors, [])
        self.assertEqual(sorted(outcomes), [False, True])
        chore.refresh_from_db()
        self.assertIn(chore.assignee_id, (first.pk, second.pk))


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

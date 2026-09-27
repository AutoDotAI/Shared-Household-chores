from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if email is None:
            raise ValueError("An email address is required.")

        email = self.normalize_email(email.strip()).lower()
        if not email:
            raise ValueError("An email address is required.")

        user = self.model(email=email, **extra_fields)
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=~Q(email=""),
                name="core_user_email_not_empty",
            ),
        ]

    def clean(self):
        super().clean()
        if self.email is not None:
            self.email = self.email.strip().lower()
        if not self.email:
            raise ValidationError({"email": "An email address is required."})

    def save(self, *args, **kwargs):
        if self.email is not None:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class SignInLink(models.Model):
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)


class Household(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        super().clean()
        self.name = self.name.strip()
        if not self.name:
            raise ValidationError({"name": "A household name is required."})

    def __str__(self):
        return self.name


class HouseholdMember(models.Model):
    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(ADMIN, "Admin"), (MEMBER, "Member")]

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="household_memberships")
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["household", "user"], name="unique_household_user_membership"),
        ]

    def __str__(self):
        return f"{self.user} in {self.household} ({self.role})"


class Invitation(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    token_digest = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if self.email is not None:
            self.email = self.email.strip().lower()
        return super().save(*args, **kwargs)


class RecurrenceRule(models.Model):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    FREQUENCY_CHOICES = [(DAILY, "Daily"), (WEEKLY, "Weekly"), (MONTHLY, "Monthly")]

    frequency = models.CharField(max_length=10, choices=FREQUENCY_CHOICES)
    interval = models.PositiveIntegerField(default=1)
    # Comma separated ISO weekdays: Monday=1 through Sunday=7.
    weekdays = models.CharField(max_length=13, blank=True, default="")
    day_of_month = models.PositiveSmallIntegerField(null=True, blank=True)

    def clean(self):
        super().clean()
        errors = {}
        if self.interval < 1:
            errors["interval"] = "The interval must be positive."
        days = self.weekdays.split(",") if self.weekdays else []
        if self.frequency == self.WEEKLY:
            try:
                parsed = [int(day) for day in days]
            except ValueError:
                parsed = []
            if not parsed or any(day < 1 or day > 7 for day in parsed) or len(set(parsed)) != len(parsed):
                errors["weekdays"] = "Select at least one weekday (Monday is 1 and Sunday is 7)."
        elif days:
            errors["weekdays"] = "Weekdays are only used for weekly schedules."
        if self.frequency == self.MONTHLY:
            if self.day_of_month is None or not 1 <= self.day_of_month <= 31:
                errors["day_of_month"] = "Choose a day from 1 through 31."
        elif self.day_of_month is not None:
            errors["day_of_month"] = "A day of month is only used for monthly schedules."
        if errors:
            raise ValidationError(errors)


class ChoreSeries(models.Model):
    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="chore_series")
    rule = models.OneToOneField(RecurrenceRule, on_delete=models.CASCADE, related_name="series")
    created_at = models.DateTimeField(auto_now_add=True)


class Chore(models.Model):
    TODO = "todo"
    DONE = "done"
    STATUS_CHOICES = [(TODO, "To do"), (DONE, "Done")]

    household = models.ForeignKey(Household, on_delete=models.CASCADE, related_name="chores")
    series = models.ForeignKey(ChoreSeries, null=True, blank=True, on_delete=models.SET_NULL, related_name="occurrences")
    title = models.CharField(max_length=200)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_chores",
    )
    due_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=TODO)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_chores",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_chores"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        super().clean()
        if self.assignee_id and self.household_id and not HouseholdMember.objects.filter(
            household_id=self.household_id, user_id=self.assignee_id
        ).exists():
            raise ValidationError({"assignee": "The assignee must be a member of this household."})

    def __str__(self):
        return self.title

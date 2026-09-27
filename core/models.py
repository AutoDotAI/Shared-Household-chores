from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
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

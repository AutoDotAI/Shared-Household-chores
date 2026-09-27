import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import SignInRequestForm
from .models import SignInLink


def home(request):
    return HttpResponse("<h1>Shared Household Chores</h1>")


SIGN_IN_LINK_MAX_AGE = 15 * 60
SIGN_IN_LINK_SALT = "core.sign-in-link"


def request_sign_in(request):
    if request.method == "POST":
        form = SignInRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            nonce = secrets.token_urlsafe(32)
            token = signing.dumps({"email": email, "nonce": nonce}, salt=SIGN_IN_LINK_SALT)
            SignInLink.objects.create(
                email=email,
                token_digest=hashlib.sha256(token.encode()).hexdigest(),
                expires_at=timezone.now() + timedelta(seconds=SIGN_IN_LINK_MAX_AGE),
            )
            link = request.build_absolute_uri(
                reverse("sign-in-complete", kwargs={"token": token})
            )
            send_mail(
                "Your sign-in link",
                f"Use this one-time link to sign in: {link}\nIt expires in 15 minutes.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
            )
            return render(request, "core/sign_in_sent.html")
    else:
        form = SignInRequestForm()
    return render(request, "core/sign_in.html", {"form": form})


def complete_sign_in(request, token):
    try:
        payload = signing.loads(
            token, salt=SIGN_IN_LINK_SALT, max_age=SIGN_IN_LINK_MAX_AGE
        )
        email = payload["email"]
        digest = hashlib.sha256(token.encode()).hexdigest()
        with transaction.atomic():
            sign_in_link = SignInLink.objects.select_for_update().get(
                email=email,
                token_digest=digest,
                used_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            sign_in_link.used_at = timezone.now()
            sign_in_link.save(update_fields=["used_at"])
            user, _ = get_user_model().objects.get_or_create(email=email)
    except (signing.BadSignature, KeyError, TypeError, SignInLink.DoesNotExist):
        return render(request, "core/sign_in_error.html", status=400)

    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("home")

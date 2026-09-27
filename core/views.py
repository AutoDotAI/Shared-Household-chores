import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.utils import timezone

from .forms import ChoreForm, HouseholdCreateForm, InvitationForm, SignInRequestForm
from .models import Chore, Household, HouseholdMember, Invitation, SignInLink
from .services import claim_chore, complete_chore


def home(request):
    return HttpResponse("<h1>Shared Household Chores</h1>")


@login_required(login_url="sign-in")
def create_household(request):
    if request.method == "POST":
        form = HouseholdCreateForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                household = form.save()
                HouseholdMember.objects.create(
                    household=household,
                    user=request.user,
                    role=HouseholdMember.ADMIN,
                )
            return redirect("household-detail", household_id=household.pk)
    else:
        form = HouseholdCreateForm()
    return render(request, "core/household_form.html", {"form": form})


@login_required(login_url="sign-in")
def household_detail(request, household_id):
    household = get_object_or_404(Household, pk=household_id)
    viewer_membership = HouseholdMember.objects.filter(household=household, user=request.user).first()
    if viewer_membership is None:
        raise Http404
    members = list(
        HouseholdMember.objects.filter(household=household)
        .select_related("user")
        .order_by("joined_at", "pk")
    )
    chores = Chore.objects.filter(household=household, status=Chore.TODO).select_related("assignee")
    open_chores = chores.filter(assignee__isnull=True).order_by("due_date", "pk")
    for membership in members:
        membership.chores = chores.filter(assignee=membership.user).order_by("due_date", "pk")
    return render(
        request,
        "core/household_detail.html",
        {
            "household": household,
            "members": members,
            "open_chores": open_chores,
            "has_chores": chores.exists(),
            "today": timezone.localdate(),
            "is_admin": viewer_membership.role == HouseholdMember.ADMIN,
        },
    )


def _admin_household_or_404(user, household_id):
    membership = get_object_or_404(
        HouseholdMember.objects.select_related("household"),
        household_id=household_id,
        user=user,
        role=HouseholdMember.ADMIN,
    )
    return membership.household


@login_required(login_url="sign-in")
def chore_create(request, household_id):
    household = _admin_household_or_404(request.user, household_id)
    if request.method == "POST":
        form = ChoreForm(request.POST, household=household)
        if form.is_valid():
            chore = form.save(commit=False)
            chore.created_by = request.user
            chore.status = Chore.TODO
            chore.save()
            return redirect("household-detail", household_id=household.pk)
    else:
        form = ChoreForm(household=household)
    return render(request, "core/chore_form.html", {"form": form, "household": household})


@login_required(login_url="sign-in")
def chore_edit(request, chore_id):
    chore = get_object_or_404(Chore.objects.select_related("household"), pk=chore_id)
    household = _admin_household_or_404(request.user, chore.household_id)
    if request.method == "POST":
        form = ChoreForm(request.POST, instance=chore, household=household)
        if form.is_valid():
            form.save()
            return redirect("household-detail", household_id=household.pk)
    else:
        form = ChoreForm(instance=chore, household=household)
    return render(request, "core/chore_form.html", {"form": form, "household": household, "chore": chore})


@login_required(login_url="sign-in")
def chore_delete(request, chore_id):
    chore = get_object_or_404(Chore.objects.select_related("household"), pk=chore_id)
    household = _admin_household_or_404(request.user, chore.household_id)
    if request.method == "POST":
        chore.delete()
        return redirect("household-detail", household_id=household.pk)
    return render(request, "core/chore_confirm_delete.html", {"chore": chore, "household": household})


@login_required(login_url="sign-in")
@require_POST
def chore_claim(request, chore_id):
    chore = get_object_or_404(Chore, pk=chore_id)
    if not HouseholdMember.objects.filter(household_id=chore.household_id, user=request.user).exists():
        raise Http404
    claim_chore(chore_id=chore.pk, user=request.user)
    return redirect("household-detail", household_id=chore.household_id)


@login_required(login_url="sign-in")
@require_POST
def chore_complete(request, chore_id):
    chore = get_object_or_404(Chore, pk=chore_id)
    if not HouseholdMember.objects.filter(household_id=chore.household_id, user=request.user).exists():
        raise Http404
    complete_chore(chore_id=chore.pk, user=request.user)
    return redirect("household-detail", household_id=chore.household_id)


INVITATION_MAX_AGE = 7 * 24 * 60 * 60
INVITATION_LINK_SALT = "core.household-invitation"


@login_required(login_url="sign-in")
def invite_member(request, household_id):
    household = _admin_household_or_404(request.user, household_id)
    if request.method == "POST":
        form = InvitationForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"]
            nonce = secrets.token_urlsafe(32)
            invitation = Invitation.objects.create(
                household=household,
                email=email,
                token_digest=hashlib.sha256(nonce.encode()).hexdigest(),
                expires_at=timezone.now() + timedelta(seconds=INVITATION_MAX_AGE),
            )
            token = signing.dumps(
                {"invitation_id": invitation.pk, "nonce": nonce},
                salt=INVITATION_LINK_SALT,
            )
            invitation.token_digest = hashlib.sha256(token.encode()).hexdigest()
            invitation.save(update_fields=["token_digest"])
            link = request.build_absolute_uri(
                reverse("invitation-accept", kwargs={"token": token})
            )
            send_mail(
                f"Join {household.name}",
                f"You have been invited to join {household.name}. Use this one-time link: {link}\nIt expires in seven days.",
                settings.DEFAULT_FROM_EMAIL,
                [email],
            )
            return redirect("household-detail", household_id=household.pk)
    else:
        form = InvitationForm()
    return render(request, "core/invitation_form.html", {"form": form, "household": household})


def accept_invitation(request, token):
    try:
        payload = signing.loads(token, salt=INVITATION_LINK_SALT, max_age=INVITATION_MAX_AGE)
        invitation_id = payload["invitation_id"]
        digest = hashlib.sha256(token.encode()).hexdigest()
        with transaction.atomic():
            invitation = Invitation.objects.select_for_update().select_related("household").get(
                pk=invitation_id,
                token_digest=digest,
                accepted_at__isnull=True,
                expires_at__gt=timezone.now(),
            )
            email = invitation.email.strip().lower()
            if request.user.is_authenticated and request.user.email.strip().lower() != email:
                return render(request, "core/invitation_error.html", {
                    "error": "This invitation was sent to a different email address. Sign in with the invited account to accept it."}, status=400)
            user = request.user if request.user.is_authenticated else get_user_model().objects.get_or_create(email=email)[0]
            HouseholdMember.objects.get_or_create(
                household=invitation.household,
                user=user,
                defaults={"role": HouseholdMember.MEMBER},
            )
            invitation.accepted_at = timezone.now()
            invitation.save(update_fields=["accepted_at"])
    except (signing.BadSignature, KeyError, TypeError, ValueError, Invitation.DoesNotExist):
        return render(request, "core/invitation_error.html", {
            "error": "This invitation link is invalid, expired, or has already been used."}, status=400)

    if not request.user.is_authenticated:
        login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return redirect("household-detail", household_id=invitation.household_id)


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

from django import forms

from .models import Chore, Household, HouseholdMember


class SignInRequestForm(forms.Form):
    email = forms.EmailField()


class InvitationForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class HouseholdCreateForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("A household name is required.")
        return name


class ChoreForm(forms.ModelForm):
    class Meta:
        model = Chore
        fields = ["title", "assignee", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        self.fields["assignee"].queryset = (
            HouseholdMember.objects.filter(household=household)
            .select_related("user")
            .order_by("joined_at", "pk")
        )
        self.fields["assignee"].label_from_instance = lambda membership: membership.user.email
        self.fields["assignee"].to_field_name = "user_id"

    def clean_title(self):
        title = self.cleaned_data["title"].strip()
        if not title:
            raise forms.ValidationError("A chore title is required.")
        return title

    def clean_assignee(self):
        membership = self.cleaned_data.get("assignee")
        return membership.user if membership else None

    def save(self, commit=True):
        chore = super().save(commit=False)
        chore.household = self.household
        if commit:
            chore.save()
        return chore

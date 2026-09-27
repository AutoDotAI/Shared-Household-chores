from django import forms
from django.db import transaction

from .models import Chore, ChoreSeries, Household, HouseholdMember, RecurrenceRule


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


class HouseholdSettingsForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("A household name is required.")
        return name


class ChoreForm(forms.ModelForm):
    ONE_OFF = "one_off"
    recurrence = forms.ChoiceField(
        choices=[(ONE_OFF, "Does not repeat"), *RecurrenceRule.FREQUENCY_CHOICES],
        required=False,
        label="Repeats",
    )
    interval = forms.IntegerField(min_value=1, initial=1, required=False, label="Repeat every")
    weekdays = forms.MultipleChoiceField(
        choices=[(str(day), label) for day, label in enumerate(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], 1
        )],
        required=False,
        label="Weekdays",
        widget=forms.CheckboxSelectMultiple,
    )
    day_of_month = forms.IntegerField(min_value=1, max_value=31, required=False, label="Day of month")

    class Meta:
        model = Chore
        fields = ["title", "assignee", "due_date"]
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, household, **kwargs):
        super().__init__(*args, **kwargs)
        self.household = household
        series = self.instance.series if self.instance and self.instance.pk else None
        if series:
            rule = series.rule
            self.initial.update({
                "recurrence": rule.frequency,
                "interval": rule.interval,
                "weekdays": rule.weekdays.split(",") if rule.weekdays else [],
                "day_of_month": rule.day_of_month,
            })
        else:
            self.initial.setdefault("recurrence", self.ONE_OFF)
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

    def clean(self):
        cleaned = super().clean()
        recurrence = cleaned.get("recurrence")
        if not recurrence:
            cleaned["recurrence"] = recurrence = self.ONE_OFF
        if recurrence != self.ONE_OFF and cleaned.get("interval") is None and "interval" not in self.errors:
            self.add_error("interval", "Enter a positive interval.")
        if recurrence == RecurrenceRule.WEEKLY and not cleaned.get("weekdays"):
            self.add_error("weekdays", "Select at least one weekday.")
        if recurrence == RecurrenceRule.MONTHLY and cleaned.get("day_of_month") is None:
            self.add_error("day_of_month", "Choose a day from 1 through 31.")
        return cleaned

    def save(self, commit=True):
        chore = super().save(commit=False)
        chore.household = self.household
        if commit:
            with transaction.atomic():
                chore.save()
                self.save_recurrence(chore)
        return chore

    def save_recurrence(self, chore):
        frequency = self.cleaned_data["recurrence"]
        if frequency == self.ONE_OFF:
            chore.series = None
            chore.save(update_fields=["series"])
            return
        values = {
            "frequency": frequency,
            "interval": self.cleaned_data["interval"],
            "weekdays": ",".join(sorted(self.cleaned_data["weekdays"], key=int)) if frequency == RecurrenceRule.WEEKLY else "",
            "day_of_month": self.cleaned_data["day_of_month"] if frequency == RecurrenceRule.MONTHLY else None,
        }
        if chore.series_id:
            rule = chore.series.rule
            for key, value in values.items():
                setattr(rule, key, value)
            rule.full_clean()
            rule.save()
        else:
            rule = RecurrenceRule(**values)
            rule.full_clean()
            rule.save()
            series = ChoreSeries.objects.create(household=self.household, rule=rule)
            chore.series = series
            chore.save(update_fields=["series"])

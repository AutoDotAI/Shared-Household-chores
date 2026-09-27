from django import forms

from .models import Household


class SignInRequestForm(forms.Form):
    email = forms.EmailField()


class HouseholdCreateForm(forms.ModelForm):
    class Meta:
        model = Household
        fields = ["name"]

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("A household name is required.")
        return name

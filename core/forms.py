from django import forms


class SignInRequestForm(forms.Form):
    email = forms.EmailField()


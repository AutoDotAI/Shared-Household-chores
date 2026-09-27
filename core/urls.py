from django.urls import path

from . import views


urlpatterns = [
    path("sign-in/", views.request_sign_in, name="sign-in"),
    path("sign-in/<str:token>/", views.complete_sign_in, name="sign-in-complete"),
]

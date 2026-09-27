from django.urls import path

from . import views


urlpatterns = [
    path("households/new/", views.create_household, name="household-create"),
    path("households/<int:household_id>/chores/new/", views.chore_create, name="chore-create"),
    path("households/<int:household_id>/", views.household_detail, name="household-detail"),
    path("chores/<int:chore_id>/edit/", views.chore_edit, name="chore-edit"),
    path("chores/<int:chore_id>/delete/", views.chore_delete, name="chore-delete"),
    path("sign-in/", views.request_sign_in, name="sign-in"),
    path("sign-in/<str:token>/", views.complete_sign_in, name="sign-in-complete"),
]

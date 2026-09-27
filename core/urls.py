from django.urls import path

from . import views


urlpatterns = [
    path("households/new/", views.create_household, name="household-create"),
    path("households/<int:household_id>/invite/", views.invite_member, name="household-invite"),
    path("households/<int:household_id>/chores/new/", views.chore_create, name="chore-create"),
    path("households/<int:household_id>/", views.household_detail, name="household-detail"),
    path("chores/<int:chore_id>/edit/", views.chore_edit, name="chore-edit"),
    path("chores/<int:chore_id>/delete/", views.chore_delete, name="chore-delete"),
    path("chores/<int:chore_id>/claim/", views.chore_claim, name="chore-claim"),
    path("chores/<int:chore_id>/complete/", views.chore_complete, name="chore-complete"),
    path("sign-in/", views.request_sign_in, name="sign-in"),
    path("sign-in/<str:token>/", views.complete_sign_in, name="sign-in-complete"),
    path("invitations/<str:token>/", views.accept_invitation, name="invitation-accept"),
]

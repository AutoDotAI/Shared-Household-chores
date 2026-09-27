from django.db import OperationalError

from .models import Chore, HouseholdMember


def claim_chore(*, chore_id, user):
    """Assign an open to-do chore to a household member, if it is still claimable."""
    household_id = Chore.objects.filter(pk=chore_id).values_list("household_id", flat=True).first()
    if household_id is None or not HouseholdMember.objects.filter(
        household_id=household_id, user=user
    ).exists():
        return False

    # A conditional UPDATE is the arbitration point: concurrent claimants can
    # only succeed while the row remains open and to-do.
    try:
        return Chore.objects.filter(
            pk=chore_id,
            household_id=household_id,
            status=Chore.TODO,
            assignee__isnull=True,
        ).update(assignee=user) == 1
    except OperationalError as error:
        # SQLite can reject the losing writer during lock contention before
        # evaluating the conditional UPDATE. Treat that request as a lost
        # claim; other database errors should still surface.
        if "locked" not in str(error).lower():
            raise
        return False

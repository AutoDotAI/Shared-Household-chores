import calendar
from datetime import date, timedelta

from django.db import OperationalError, transaction
from django.utils import timezone

from .models import Chore, HouseholdMember, RecurrenceRule


def _next_due_date(chore):
    """Return the next scheduled date, anchored to the series' first occurrence."""
    rule = chore.series.rule
    if rule.frequency == RecurrenceRule.DAILY:
        return chore.due_date + timedelta(days=rule.interval)

    first_due_date = chore.series.occurrences.order_by("due_date", "pk").values_list(
        "due_date", flat=True
    ).first()
    if rule.frequency == RecurrenceRule.WEEKLY:
        anchor_monday = first_due_date - timedelta(days=first_due_date.weekday())
        current_monday = chore.due_date - timedelta(days=chore.due_date.weekday())
        current_week = (current_monday - anchor_monday).days // 7
        weekdays = sorted(int(day) for day in rule.weekdays.split(","))
        for week in range(max(current_week, 0), max(current_week, 0) + rule.interval * 2 + 2):
            if week % rule.interval:
                continue
            for weekday in weekdays:
                candidate = anchor_monday + timedelta(weeks=week, days=weekday - 1)
                if candidate > chore.due_date:
                    return candidate
        raise ValueError("Could not calculate the next weekly chore occurrence.")

    if rule.frequency == RecurrenceRule.MONTHLY:
        anchor_month = first_due_date.year * 12 + first_due_date.month - 1
        current_month = chore.due_date.year * 12 + chore.due_date.month - 1
        months_since_anchor = current_month - anchor_month
        next_month_offset = (months_since_anchor // rule.interval + 1) * rule.interval
        next_month_index = anchor_month + next_month_offset
        year, zero_based_month = divmod(next_month_index, 12)
        month = zero_based_month + 1
        day = min(rule.day_of_month, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    raise ValueError(f"Unsupported recurrence frequency: {rule.frequency}")


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


def complete_chore(*, chore_id, user):
    """Complete a to-do chore when the user is its assignee or a household admin."""
    chore = Chore.objects.filter(pk=chore_id).values("household_id", "assignee_id").first()
    if chore is None:
        return False

    membership = HouseholdMember.objects.filter(
        household_id=chore["household_id"], user=user
    ).values_list("role", flat=True).first()
    if membership is None:
        return False
    if membership != HouseholdMember.ADMIN and chore["assignee_id"] != user.pk:
        return False

    # The conditional update is the arbitration point for repeated or
    # concurrent completion requests. Create the successor in the same
    # transaction so a successful completion cannot lose its next occurrence.
    with transaction.atomic():
        completed = Chore.objects.filter(pk=chore_id, status=Chore.TODO).update(
            status=Chore.DONE,
            completed_at=timezone.now(),
            completed_by=user,
        )
        if not completed:
            return False

        chore = Chore.objects.select_related("series__rule").get(pk=chore_id)
        if chore.series_id is not None:
            has_future = Chore.objects.filter(
                series=chore.series,
                status=Chore.TODO,
                due_date__gt=chore.due_date,
            ).exists()
            if not has_future:
                Chore.objects.create(
                    household_id=chore.household_id,
                    series=chore.series,
                    title=chore.title,
                    assignee_id=chore.assignee_id,
                    due_date=_next_due_date(chore),
                    created_by_id=chore.created_by_id,
                )
        return True

from django.db import transaction
from .models import Event, Membership


def _member_ids(poll):
    return set(Membership.objects.filter(circle=poll.circle).values_list('user_id', flat=True))


def _yes_ids(poll, member_ids):
    return set(poll.votes.filter(choice='yes').values_list('user_id', flat=True)) & member_ids


def target_user_ids(poll):
    """Who gets the event, depending on poll type."""
    members = _member_ids(poll)
    if poll.poll_type == Event.POLL_MAJORITY_ALL:
        return members
    return _yes_ids(poll, members)  # majority_voters and optin


def poll_is_ready(poll):
    """Has this poll met its resolution condition?"""
    if poll.poll_type == Event.POLL_OPTIN:
        members = _member_ids(poll)
        voted = set(poll.votes.values_list('user_id', flat=True)) & members
        return bool(members) and voted == members and bool(_yes_ids(poll, members))
    return poll.has_passed_threshold()  # both majority types: yes > 50% of all members


@transaction.atomic
def resolve_poll(poll):
    """Approve the poll and create calendar events. Returns the set of user ids who got it."""
    targets = target_user_ids(poll)
    if not targets:
        return set()

    # The poll row itself becomes one calendar event, so give it to the proposer if they
    # qualify, otherwise to the lowest-id target. Everyone else gets a copy.
    anchor = poll.proposed_by_id if poll.proposed_by_id in targets else min(targets)
    poll.status = 'approved'
    poll.user_id = anchor
    poll.save()

    for uid in targets - {anchor}:
        Event.objects.get_or_create(
            user_id=uid, circle=poll.circle,
            start_time=poll.start_time, end_time=poll.end_time, event_name=poll.event_name,
            defaults={
                'event_description': poll.event_description,
                'status': 'approved',
                'proposed_by': poll.proposed_by,
            },
        )
    return targets
from .models import Event

# Statuses that represent time actually blocked on a user's personal calendar.
# Pending proposals have user=None, so they never match anyway.
BLOCKING_STATUSES = ('personal', 'approved')

SUMMARY_LIMIT = 3


def overlaps(a_start, a_end, b_start, b_end):
    """Standard overlap rule: (ProposedStart < ExistingEnd) AND (ProposedEnd > ExistingStart)."""
    return a_start < b_end and a_end > b_start


def _busy_queryset(user, range_start, range_end):
    return (
        Event.objects
        .filter(
            user=user,
            status__in=BLOCKING_STATUSES,
            start_time__lt=range_end,   # DB-side use of the same overlap rule
            end_time__gt=range_start,
        )
        .only('id', 'event_name', 'start_time', 'end_time')
        .order_by('start_time')
    )


def find_conflicts(user, start, end):
    return list(_busy_queryset(user, start, end))

def annotate_conflicts(user, proposals):
    """
    Attach `.conflicts` (list of Events) and `.conflict_summary` (str) to every proposal.

    Uses ONE query: fetch the user's events inside the bounding window of all
    proposals, then run the overlap check in memory. No per-proposal queries.
    """
    proposals = list(proposals)
    if not proposals:
        return proposals

    range_start = min(p.start_time for p in proposals)
    range_end = max(p.end_time for p in proposals)
    busy = list(_busy_queryset(user, range_start, range_end))

    for p in proposals:
        p.conflicts = [
            e for e in busy
            if overlaps(p.start_time, p.end_time, e.start_time, e.end_time)
        ]
        p.conflict_summary = ", ".join(e.event_name for e in p.conflicts[:SUMMARY_LIMIT])
        if len(p.conflicts) > SUMMARY_LIMIT:
            p.conflict_summary += f" +{len(p.conflicts) - SUMMARY_LIMIT} more"
    return proposals
from datetime import timedelta
from django.utils import timezone
from .models import Membership, Event, ProposalVote

def notifications(request):
    if not request.user.is_authenticated:
        return {}

    circle_ids = Membership.objects.filter(user=request.user).values_list('circle_id', flat=True)
    voted_ids = ProposalVote.objects.filter(user=request.user).values_list('event_id', flat=True)

    pending_qs = Event.objects.filter(
        circle_id__in=circle_ids, status='pending',
    ).exclude(id__in=voted_ids).exclude(proposed_by=request.user).select_related('circle').order_by('-proposed_at')

    recent_cutoff = timezone.now() - timedelta(days=7)
    approved_qs = Event.objects.filter(
        user=request.user, status='approved', proposed_at__gte=recent_cutoff,
    ).exclude(proposed_by=request.user).select_related('circle').order_by('-proposed_at')

    return {
        'nav_pending_proposals': pending_qs[:10],
        'nav_recent_approved': approved_qs[:10],
        'nav_notification_count': pending_qs.count() + approved_qs.count(),
    }
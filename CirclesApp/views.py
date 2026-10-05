from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from . forms import (
    RegisterForm, CircleForm, CalendarForm, JoinCircleForm, EventProposalForm,
    ProfileForm, EventForm, ICSUploadForm, AccountForm, DeleteAccountForm,
    PollProposalForm
)
from . models import Circle, Membership, Event, ProposalVote, UserProfile, create_code
from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponse, JsonResponse
from django.contrib import messages
from datetime import timedelta, datetime, time
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.mail import send_mail
from icalendar import Calendar as ICalCalendar, Event as ICalEvent
from .conflicts import annotate_conflicts, find_conflicts
from django.db.models import Count, F, Q
from django.db import transaction
from django.views.decorators.http import require_POST
from .forms import PollProposalForm   # add to the existing forms import
from .polls import poll_is_ready, resolve_poll
import io
import zipfile
import recurring_ical_events

HOURS = range(0, 24)


def notify_circle_members(circle, subject, message, exclude_user=None):
    recipients = Membership.objects.filter(circle=circle).exclude(user=exclude_user).select_related('user')
    emails = [m.user.email for m in recipients if m.user.email]
    if emails:
        send_mail(subject, message, None, emails, fail_silently=True)


def get_week_monday(request):
    day = None
    week_param = request.GET.get('week')
    if week_param:
        try:
            day = datetime.strptime(week_param, '%Y-%m-%d').date()
        except ValueError:
            day = None
    if day is None:
        day = timezone.localdate()
    return day - timedelta(days=day.weekday())


def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect('login')
    return redirect('home')


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = User.objects.create_user(
                username=username,
                password=password,
                email=form.cleaned_data.get('email', '')
            )
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    error_message = None

    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next')
            # Only follow redirects that stay on this site (prevents open redirects)
            if not next_url or not url_has_allowed_host_and_scheme(
                next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
            ):
                next_url = 'home'
            return redirect(next_url)
        else:
            error_message = "Invalid Credentials"
    return render(request, 'accounts/login.html', {'error': error_message})


@login_required
def create_circles_view(request):
    if request.method == "POST":
        form = CircleForm(request.POST)
        if form.is_valid():
            circle = form.save()
            Membership.objects.create(user=request.user, circle=circle, role='owner')
            return redirect('home')
    else:
        form = CircleForm()

    return render(request, 'circles_app/create_circle.html', {'form': form})


@login_required
def calendar_view(request):
    if request.method == "POST":
        form = CalendarForm(request.POST)
        if form.is_valid():
            weekdays = {int(d) for d in form.cleaned_data['weekdays']}
            if weekdays:
                start_dt = form.cleaned_data['start_time']
                duration = form.cleaned_data['end_time'] - start_dt
                first_day = start_dt.date()
                week1_monday = first_day - timedelta(days=first_day.weekday())
                weekdays.add(first_day.weekday())   # the event you entered is always created

                new_events = []
                for week in range(form.cleaned_data['num_weeks']):
                    for wd in sorted(weekdays):
                        day = week1_monday + timedelta(weeks=week, days=wd)
                        if day < first_day:
                            continue
                        occurrence_start = timezone.make_aware(datetime.combine(day, start_dt.time()))
                        new_events.append(Event(
                            user=request.user,
                            start_time=occurrence_start,
                            end_time=occurrence_start + duration,
                            event_name=form.cleaned_data['event_name'],
                            event_description=form.cleaned_data['event_description'],
                        ))
                Event.objects.bulk_create(new_events)
                messages.success(request, f"Added {len(new_events)} events.")
            else:
                event = form.save(commit=False)
                event.user = request.user
                event.save()
            return redirect('calendar')
    else:
        form = CalendarForm()

    monday = get_week_monday(request)
    days = [monday + timedelta(days=i) for i in range(7)]
    week_start = timezone.make_aware(datetime.combine(days[0], time.min))
    week_end = timezone.make_aware(datetime.combine(days[-1], time.max))

    week_events = list(Event.objects.filter(
        user=request.user, start_time__lt=week_end, end_time__gt=week_start,
    ).select_related('circle'))

    grid = []
    for hour in HOURS:
        cells = []
        for day in days:
            cell_start = timezone.make_aware(datetime.combine(day, time(hour=hour)))
            cell_end = cell_start + timedelta(hours=1)
            matches = [e for e in week_events if e.start_time < cell_end and cell_start < e.end_time]
            cells.append({'events': matches, 'start': cell_start, 'end': cell_end})
        grid.append({'hour': hour, 'cells': cells})

    user_events = Event.objects.filter(user=request.user).order_by('start_time')
    return render(request, 'circles_app/calendar.html', {
        'form': form, 'events': user_events,
        'grid': grid, 'days': days,
        'prev_week': monday - timedelta(days=7), 'next_week': monday + timedelta(days=7),
    })


@login_required
def circle_detail_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()

    
    if not is_member:
        raise Http404

    is_owner = Membership.objects.filter(user=request.user, circle=circle, role='owner').exists()

    memberships = circle.memberships.all()

    monday = get_week_monday(request)
    days = [monday + timedelta(days=i) for i in range(7)]

    member_ids = Membership.objects.filter(circle=circle).values_list('user_id', flat=True)
    total_members = member_ids.count()

    members_info = {}
    for u in User.objects.filter(id__in=member_ids).select_related('profile'):
        prof = getattr(u, 'profile', None)
        members_info[u.id] = {
            'username': u.username,
            'avatar': prof.avatar.url if prof and prof.avatar else '',
        }

    week_start = timezone.make_aware(datetime.combine(days[0], time.min))
    week_end = timezone.make_aware(datetime.combine(days[-1], time.max))

    events = Event.objects.filter(
        user_id__in=member_ids,
        start_time__lt=week_end,
        end_time__gt=week_start,
    )

    grid = []
    for hour in HOURS:
        cells = []
        for day in days:
            cell_start = timezone.make_aware(datetime.combine(day, time(hour=hour)))
            cell_end = cell_start + timedelta(hours=1)
            busy_users = set()
            labels = set()
            for e in events:
                if e.start_time < cell_end and cell_start < e.end_time:
                    busy_users.add(e.user_id)
                    if e.status == 'approved' and e.circle_id == circle.id:
                        labels.add(e.event_name)
            free = total_members - len(busy_users)
            ratio = free / total_members if total_members else 0
            cells.append({
                'free': free, 'total': total_members, 'ratio': ratio,
                'labels': labels, 'start': cell_start, 'end': cell_end,
                'busy': sorted(busy_users),
            })
        grid.append({'hour': hour, 'cells': cells})

    SLEEP_HOURS = set(range(22, 24)) | set(range(0, 6))  # 10PM–6AM
    SLEEP_PENALTY = 2  # ranking-only: treat a sleep-hour slot as if this many fewer people were free

    now = timezone.now()  # aware, so it compares correctly with the aware cell datetimes

    best_slot = None
    best_score = None
    if total_members > 1:
        for row in grid:
            penalty = SLEEP_PENALTY if row['hour'] in SLEEP_HOURS else 0
            for cell in row['cells']:
                if cell['start'] < now:
                    continue  # slot has already started, so it can't be proposed
                score = cell['free'] - penalty
                if best_score is None or score > best_score:
                    best_score = score
                    best_slot = cell

    proposals = annotate_conflicts(
        request.user,
        Event.objects.filter(circle=circle, status='pending').order_by('-proposed_at'),
    )
    user_votes = {
        v.event_id: v.choice
        for v in ProposalVote.objects.filter(user=request.user, event__circle=circle)
    }

    # --- Circle analytics (last 30 days) ---
    cutoff = timezone.now() - timedelta(days=30)

    # Approving a proposal copies the event onto each yes-voter's calendar, so count
    # distinct (name, start, end) rather than rows. The circle export uses the same dedupe.
    events_this_month = (
        Event.objects
        .filter(circle=circle, status='approved', proposed_at__gte=cutoff)
        .values('event_name', 'start_time', 'end_time')
        .distinct()
        .count()
    )

    active_members = (
        ProposalVote.objects
        .filter(event__circle=circle, voted_at__gte=cutoff, user_id__in=member_ids)
        .values('user_id')
        .distinct()
        .count()
    )
    active_member_pct = round(active_members * 100 / total_members) if total_members else 0

    return render(request, 'circles_app/circle_detail.html', {
        'circle': circle,
        'memberships': memberships,
        'days': days,
        'grid': grid,
        'prev_week': monday - timedelta(days=7),
        'next_week': monday + timedelta(days=7),
        'proposals': proposals,
        'user_votes': user_votes,
        'best_slot': best_slot,
        'members_info': members_info,
        'events_this_month': events_this_month,
        'active_member_pct': active_member_pct,
        'is_owner': is_owner,
    })


@login_required
def join_circle_view(request, code):
    circle = get_object_or_404(Circle, invite_code=code)
    already_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if request.method == "POST":
        membership, created = Membership.objects.get_or_create(
            user=request.user, circle=circle, defaults={'role': 'member'},
        )
        if created:
            owners = Membership.objects.filter(circle=circle, role='owner').select_related('user')
            owner_emails = [m.user.email for m in owners if m.user.email]
            if owner_emails:
                send_mail(
                    f"New member joined {circle.circle_name}",
                    f"{request.user.username} joined your circle!",
                    None, owner_emails, fail_silently=True,
                )
        return redirect('circle_detail', circle_id=circle.id)
    return render(request, 'circles_app/join_preview.html', {'circle': circle, 'already_member': already_member})


@login_required
def find_circle_view(request):
    if request.method == "POST":
        form = JoinCircleForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data['invite_code']
            if Circle.objects.filter(invite_code=code).exists():
                return redirect('join_circle', code=code)
            else:
                messages.error(request, "No circle found with that invite code.")
        else:
            messages.error(request, "Please enter an invite code.")
    return redirect('home')


@login_required
def home_view(request):
    user_memberships = Membership.objects.filter(user=request.user)
    join_form = JoinCircleForm()
    upcoming_events = Event.objects.filter(
        user=request.user, start_time__gte=timezone.now(),
    ).order_by('start_time')[:5]

    # Yes / No poll votes in one query
    vote_totals = ProposalVote.objects.filter(user=request.user).aggregate(
        yes=Count('id', filter=Q(choice='yes')),
        no=Count('id', filter=Q(choice='no')),
    )

    # Top 3 circles by activity = approved events on the user's own calendar
    # for that circle + poll votes the user cast in it.
    # distinct=True is required because both counts join through multi-valued relations.
    top_circles = (
        Circle.objects
        .filter(memberships__user=request.user)
        .annotate(
            event_count=Count(
                'circle_events',
                filter=Q(circle_events__user=request.user, circle_events__status='approved'),
                distinct=True,
            ),
            vote_count=Count(
                'circle_events__votes',
                filter=Q(circle_events__votes__user=request.user),
                distinct=True,
            ),
        )
        .annotate(activity=F('event_count') + F('vote_count'))
        .filter(activity__gt=0)
        .order_by('-activity', 'circle_name')[:3]
    )
    circle_ids = list(user_memberships.values_list('circle_id', flat=True))
    voted_ids = ProposalVote.objects.filter(user=request.user).values_list('event_id', flat=True)
    pending_proposals = (
        Event.objects
        .filter(circle_id__in=circle_ids, status='pending')
        .exclude(id__in=voted_ids)
        .select_related('circle')
        .order_by('start_time')
    )
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    free_now_count = (
        UserProfile.objects
        .filter(user__membership__circle_id__in=circle_ids, free_until__gt=timezone.now())
        .exclude(user=request.user)
        .distinct()
        .count()
    )

    return render(request, 'circles_app/home.html', {
        'memberships': user_memberships, 'join_form': join_form,
        'upcoming_events': upcoming_events,
        'quick_event_form': CalendarForm(),
        'user_accepted_polls': vote_totals['yes'],
        'user_rejected_polls': vote_totals['no'],
        'top_circles': top_circles,
    })


@login_required
def propose_event_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    if not Membership.objects.filter(user=request.user, circle=circle).exists():
        raise Http404

    if request.method == "POST":
        form = PollProposalForm(request.POST)
        if form.is_valid():
            proposal = form.save(commit=False)
            proposal.circle = circle
            proposal.proposed_by = request.user
            proposal.status = 'pending'
            proposal.user = None
            proposal.save()
            messages.success(request, "Event proposed! Circle members can now vote.")
            notify_circle_members(
                circle,
                f"New event proposed in {circle.circle_name}",
                f"{request.user.username} proposed '{proposal.event_name}'. Log in to vote!",
                exclude_user=request.user,
            )
            return redirect('circle_detail', circle_id=circle.id)
    else:
        initial = {}
        try:
            day = datetime.strptime(request.GET.get('date', ''), '%Y-%m-%d').date()
            start_t = datetime.strptime(request.GET.get('start_time', ''), '%H:%M').time()
            end_t = datetime.strptime(request.GET.get('end_time', ''), '%H:%M').time()
        except ValueError:
            pass
        else:
            start_dt = datetime.combine(day, start_t)
            end_dt = datetime.combine(day, end_t)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
            initial = {
                'start_time': start_dt.strftime('%Y-%m-%dT%H:%M'),
                'end_time': end_dt.strftime('%Y-%m-%dT%H:%M'),
            }
        form = PollProposalForm(initial=initial)

    return render(request, 'circles_app/propose_event.html', {'form': form, 'circle': circle})
def _redirect_after_vote(request, proposal):
    next_url = request.POST.get('next')
    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(next_url)
    return redirect('circle_detail', circle_id=proposal.circle.id)

def _wants_json(request):
    return request.headers.get('x-requested-with') == 'XMLHttpRequest'


def _poll_payload(proposal, message, choice=None, resolved=False):
    return {
        'message': message, 'choice': choice, 'resolved': resolved,
        'yes': proposal.yes_votes(), 'no': proposal.no_votes(),
        'total': proposal.total_members(),
    }


def _notify_targets(proposal, target_ids):
    emails = list(User.objects.filter(id__in=target_ids).exclude(email='').values_list('email', flat=True))
    if emails:
        send_mail(
            f"Event approved in {proposal.circle.circle_name}",
            f"'{proposal.event_name}' was added to your calendar.",
            None, emails, fail_silently=True,
        )


def _resolved_message(proposal, targets):
    if proposal.poll_type == 'majority_all':
        return f"'{proposal.event_name}' passed! Added to every member's calendar."
    return f"'{proposal.event_name}' is set! Added to the calendars of {len(targets)} member(s) who voted yes."

@login_required
def vote_proposal_view(request, proposal_id):
    proposal = get_object_or_404(Event, id=proposal_id, status='pending')
    if not Membership.objects.filter(user=request.user, circle=proposal.circle).exists():
        raise Http404
    if request.method != "POST":
        return redirect('circle_detail', circle_id=proposal.circle.id)

    wants_json = _wants_json(request)

    def respond(message, level='success', status=200, **extra):
        if wants_json:
            return JsonResponse(_poll_payload(proposal, message, **extra), status=status)
        getattr(messages, level)(request, message)
        return redirect('circle_detail', circle_id=proposal.circle.id)

    choice = request.POST.get('choice')
    if choice not in ('yes', 'no'):
        return respond("Invalid vote.", 'error', status=400)

    ProposalVote.objects.update_or_create(
        event=proposal, user=request.user, defaults={'choice': choice}
    )

    if poll_is_ready(proposal):
        targets = resolve_poll(proposal)
        if targets:
            message = _resolved_message(proposal, targets)
            _notify_targets(proposal, targets)
            return respond(message, choice=choice, resolved=True)

    return respond("Vote recorded.", choice=choice)

@login_required
def profile_settings_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect('home')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'circles_app/profile_settings.html', {'form': form})


@login_required
def account_settings_view(request):
    account_form = AccountForm(instance=request.user)
    delete_form = DeleteAccountForm()

    if request.method == "POST":
        if request.POST.get('action') == 'edit':
            account_form = AccountForm(request.POST, instance=request.user)
            if account_form.is_valid():
                account_form.save()
                messages.success(request, "Account updated.")
                return redirect('account_settings')
        elif request.POST.get('action') == 'delete':
            delete_form = DeleteAccountForm(request.POST)
            if delete_form.is_valid():
                if request.user.check_password(delete_form.cleaned_data['password']):
                    user = request.user
                    logout(request)
                    user.delete()
                    messages.success(request, "Your account has been deleted.")
                    return redirect('home')
                else:
                    delete_form.add_error('password', "Incorrect password.")

    return render(request, 'circles_app/account_settings.html', {
        'account_form': account_form, 'delete_form': delete_form,
    })


@login_required
def time_block_detail_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if not is_member:
        raise Http404

    try:
        cell_start = timezone.make_aware(datetime.strptime(request.GET.get('start', ''), '%Y-%m-%dT%H:%M'))
        cell_end = timezone.make_aware(datetime.strptime(request.GET.get('end', ''), '%Y-%m-%dT%H:%M'))
    except ValueError:
        raise Http404

    member_ids = Membership.objects.filter(circle=circle).values_list('user_id', flat=True)
    overlapping = Event.objects.filter(
        user_id__in=member_ids, start_time__lt=cell_end, end_time__gt=cell_start,
    ).select_related('user')

    entries = []
    for e in overlapping:
        shared = (e.status == 'approved' and e.circle_id == circle.id)
        mine = (e.user_id == request.user.id)
        if shared or mine:
            entries.append({'user': e.user.username, 'name': e.event_name, 'description': e.event_description, 'masked': False})
        else:
            entries.append({'user': e.user.username, 'name': 'Busy', 'description': '', 'masked': True})

    return render(request, 'circles_app/time_block_detail.html', {
        'circle': circle, 'cell_start': cell_start, 'cell_end': cell_end, 'entries': entries,
    })




@login_required
def export_calendar_view(request):
    cal = ICalCalendar()
    cal.add('prodid', '-//Circles App//mxm.dk//')
    cal.add('version', '2.0')

    for e in Event.objects.filter(user=request.user):
        ical_event = ICalEvent()
        ical_event.add('summary', e.event_name)
        ical_event.add('dtstart', e.start_time)
        ical_event.add('dtend', e.end_time)
        ical_event.add('description', e.event_description)
        cal.add_component(ical_event)

    response = HttpResponse(cal.to_ical(), content_type='text/calendar')
    response['Content-Disposition'] = 'attachment; filename="my_calendar.ics"'
    return response


MAX_IMPORT_EVENTS = 3000


def _to_aware(value):
    """datetime -> aware datetime; date -> midnight in the user's timezone."""
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    return timezone.make_aware(datetime.combine(value, time.min))


def _event_bounds(comp):
    start_raw = comp['dtstart'].dt
    if 'dtend' in comp:
        end_raw = comp['dtend'].dt
    elif 'duration' in comp:
        end_raw = start_raw + comp['duration'].dt
    elif isinstance(start_raw, datetime):
        end_raw = start_raw + timedelta(hours=1)
    else:
        end_raw = start_raw + timedelta(days=1)   # all-day, DTEND is exclusive
    start, end = _to_aware(start_raw), _to_aware(end_raw)
    if end <= start:
        end = start + timedelta(hours=1)
    return start, end


def _load_calendars(uploaded):
    data = uploaded.read()
    if uploaded.name.lower().endswith('.zip'):   # Google's export is a zip of .ics files
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            return [ICalCalendar.from_ical(zf.read(n))
                    for n in zf.namelist() if n.lower().endswith('.ics')]
    return [ICalCalendar.from_ical(data)]


@login_required
def import_calendar_view(request):
    if request.method == "POST":
        form = ICSUploadForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                calendars = _load_calendars(form.cleaned_data['ics_file'])
            except Exception:
                messages.error(request, "That doesn't look like a valid .ics (or .zip) file.")
                return redirect('import_calendar')

            existing = set(
                Event.objects.filter(user=request.user)
                .values_list('event_name', 'start_time', 'end_time')
            )
            new_events, capped = [], False
            window_end = timezone.localdate() + timedelta(days=366)   # expand repeats up to 1 year out

            for cal in calendars:
                starts = []
                for c in cal.walk('VEVENT'):
                    if 'dtstart' in c:
                        d = c['dtstart'].dt
                        starts.append(d.date() if isinstance(d, datetime) else d)
                if not starts:
                    continue
                occurrences = recurring_ical_events.of(cal).between(min(starts), window_end)

                for comp in occurrences:
                    if 'dtstart' not in comp or str(comp.get('status', '')).upper() == 'CANCELLED':
                        continue
                    start, end = _event_bounds(comp)
                    name = str(comp.get('summary', 'Imported Event'))[:32]
                    key = (name, start, end)
                    if key in existing:
                        continue
                    existing.add(key)
                    new_events.append(Event(
                        user=request.user, start_time=start, end_time=end,
                        event_name=name, event_description=str(comp.get('description', '')),
                    ))
                    if len(new_events) >= MAX_IMPORT_EVENTS:
                        capped = True
                        break
                if capped:
                    break

            Event.objects.bulk_create(new_events)
            msg = f"Imported {len(new_events)} events."
            if capped:
                msg += f" Stopped at {MAX_IMPORT_EVENTS}; repeating events were expanded one year ahead."
            messages.success(request, msg)
            return redirect('calendar')
    else:
        form = ICSUploadForm()
    return render(request, 'circles_app/import_calendar.html', {'form': form})

# CRUD FUNCTIONS FOR EVENTS, CIRCLES

@login_required
def edit_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id, user=request.user)
    if request.method == "POST":
        form = EventForm(request.POST, instance=event)
        if form.is_valid():
            form.save()
            messages.success(request, "Event updated.")
            return redirect('calendar')
    else:
        form = EventForm(instance=event)
    return render(request, 'circles_app/edit_event.html', {'form': form, 'event': event})


@login_required
def delete_event_view(request, event_id):
    event = get_object_or_404(Event, id=event_id, user=request.user)
    if request.method == "POST":
        event.delete()
        messages.success(request, "Event deleted.")
        return redirect('calendar')
    return render(request, 'circles_app/delete_event_confirm.html', {'event': event})


@login_required
def edit_circle_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_owner = Membership.objects.filter(user=request.user, circle=circle, role='owner').exists()
    if not is_owner:
        raise Http404
    if request.method == "POST":
        form = CircleForm(request.POST, instance=circle)
        if form.is_valid():
            form.save()
            messages.success(request, "Circle updated.")
            return redirect('circle_detail', circle_id=circle.id)
    else:
        form = CircleForm(instance=circle)
    return render(request, 'circles_app/edit_circle.html', {'form': form, 'circle': circle})


@login_required
def delete_circle_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_owner = Membership.objects.filter(user=request.user, circle=circle, role='owner').exists()
    if not is_owner:
        raise Http404
    if request.method == "POST":
        circle.delete()
        messages.success(request, "Circle deleted.")
        return redirect('home')
    return render(request, 'circles_app/delete_circle_confirm.html', {'circle': circle})


@login_required
def leave_circle_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    membership = get_object_or_404(Membership, user=request.user, circle=circle)
    if membership.role == 'owner':
        messages.error(request, "Owners can't leave their own circle. Delete it instead, or transfer ownership first.")
        return redirect('circle_detail', circle_id=circle.id)
    if request.method == "POST":
        membership.delete()
        messages.success(request, f"You left {circle.circle_name}.")
        return redirect('home')
    return render(request, 'circles_app/leave_circle_confirm.html', {'circle': circle})


@login_required
def quick_approve_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_owner = Membership.objects.filter(user=request.user, circle=circle, role='owner').exists()
    if not is_owner:
        raise Http404

    if request.method == "POST":
        form = EventProposalForm(request.POST)
        if form.is_valid():
            event = form.save(commit=False)
            event.circle = circle
            event.proposed_by = request.user
            event.user = request.user
            event.status = 'approved'
            event.save()

            members = Membership.objects.filter(circle=circle).exclude(user=request.user).select_related('user')
            for member in members:
                Event.objects.get_or_create(
                    user=member.user, circle=circle,
                    start_time=event.start_time, end_time=event.end_time, event_name=event.event_name,
                    defaults={'event_description': event.event_description, 'status': 'approved', 'proposed_by': request.user},
                )
            messages.success(request, f"'{event.event_name}' added to everyone's calendar.")
            notify_circle_members(
                circle, f"New event in {circle.circle_name}",
                f"{request.user.username} added '{event.event_name}' directly to everyone's calendar!",
                exclude_user=request.user,
            )
            return redirect('circle_detail', circle_id=circle.id)
    else:
        form = EventProposalForm()
    return render(request, 'circles_app/quick_approve.html', {'form': form, 'circle': circle})


@login_required
def export_circle_calendar_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if not is_member:
        raise Http404

    cal = ICalCalendar()
    cal.add('prodid', '-//Circles App//mxm.dk//')
    cal.add('version', '2.0')

    shared = Event.objects.filter(circle=circle, status='approved').values(
        'event_name', 'start_time', 'end_time', 'event_description'
    ).distinct()
    for e in shared:
        ical_event = ICalEvent()
        ical_event.add('summary', e['event_name'])
        ical_event.add('dtstart', e['start_time'])
        ical_event.add('dtend', e['end_time'])
        ical_event.add('description', e['event_description'])
        cal.add_component(ical_event)

    response = HttpResponse(cal.to_ical(), content_type='text/calendar')
    response['Content-Disposition'] = f'attachment; filename="{circle.circle_name}.ics"'
    return response

@login_required
def check_conflicts_view(request):
    """Live conflict check while a user fills out the propose-event form."""
    try:
        start = timezone.make_aware(datetime.strptime(request.GET.get('start', ''), '%Y-%m-%dT%H:%M'))
        end = timezone.make_aware(datetime.strptime(request.GET.get('end', ''), '%Y-%m-%dT%H:%M'))
    except ValueError:
        return JsonResponse({'conflicts': []})
    if start >= end:
        return JsonResponse({'conflicts': []})

    return JsonResponse({'conflicts': [
        {
            'name': e.event_name,
            'start': timezone.localtime(e.start_time).strftime('%b %d, %H:%M'),
            'end': timezone.localtime(e.end_time).strftime('%H:%M'),
        }
        for e in find_conflicts(request.user, start, end)
    ]})

@login_required
def toggle_free_status_view(request):
    if request.method != "POST":
        return redirect('home')

    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if profile.is_free:
        profile.free_until = None
        profile.save(update_fields=['free_until'])
        messages.success(request, "You're set as busy.")
        return redirect('home')

    try:
        hours = int(request.POST.get('hours', 2))
    except (TypeError, ValueError):
        hours = 2
    hours = max(1, min(hours, 4))  # only 1-4 hours are offered, so clamp anything else

    profile.free_until = timezone.now() + timedelta(hours=hours)
    profile.save(update_fields=['free_until'])

    circle_ids = Membership.objects.filter(user=request.user).values_list('circle_id', flat=True)
    emails = list(
        User.objects.filter(membership__circle_id__in=circle_ids)
        .exclude(id=request.user.id).exclude(email='')
        .distinct().values_list('email', flat=True)
    )
    label = f"{hours} hour{'s' if hours != 1 else ''}"
    if emails:
        send_mail(
            f"{request.user.username} is free right now!",
            f"{request.user.username} just marked themselves as free for the next {label}. Hang out?",
            None, emails, fail_silently=True,
        )
    messages.success(request, f"You're marked as free for the next {label}.")
    return redirect('home')

# CIRCLE OWNER MANAGEMENT

def _require_owner(user, circle):
    """Only the circle owner may manage members and the invite code."""
    if not Membership.objects.filter(user=user, circle=circle, role='owner').exists():
        raise Http404


@login_required
@require_POST
def transfer_ownership(request, circle_id, member_id):
    circle = get_object_or_404(Circle, id=circle_id)
    _require_owner(request.user, circle)

    if member_id == request.user.id:
        messages.error(request, "You already own this circle.")
        return redirect('circle_detail', circle_id=circle.id)

    target = get_object_or_404(
        Membership.objects.select_related('user'), circle=circle, user_id=member_id,
    )

    with transaction.atomic():
        # Demote every current owner first so the circle never ends up with two.
        Membership.objects.filter(circle=circle, role='owner').update(role='member')
        target.role = 'owner'
        target.save(update_fields=['role'])

    messages.success(request, f"{target.user.username} is now the owner of {circle.circle_name}.")
    return redirect('circle_detail', circle_id=circle.id)


@login_required
@require_POST
def remove_member(request, circle_id, member_id):
    circle = get_object_or_404(Circle, id=circle_id)
    _require_owner(request.user, circle)

    if member_id == request.user.id:
        messages.error(request, "Owners can't remove themselves. Transfer ownership first, then leave.")
        return redirect('circle_detail', circle_id=circle.id)

    target = get_object_or_404(
        Membership.objects.select_related('user'), circle=circle, user_id=member_id,
    )
    username = target.user.username

    with transaction.atomic():
        # Drop their votes on open proposals so they no longer count toward the majority.
        ProposalVote.objects.filter(
            event__circle=circle, event__status='pending', user_id=member_id,
        ).delete()
        target.delete()

    messages.success(request, f"{username} was removed from {circle.circle_name}.")
    return redirect('circle_detail', circle_id=circle.id)


@login_required
@require_POST
def regenerate_invite_code(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    _require_owner(request.user, circle)

    code = create_code()
    while Circle.objects.filter(invite_code=code).exists():
        code = create_code()

    circle.invite_code = code
    circle.save(update_fields=['invite_code'])

    messages.success(request, "New invite link generated. The old link no longer works.")
    return redirect('circle_detail', circle_id=circle.id)

@login_required
@require_POST
def finalize_poll_view(request, proposal_id):
    """Opt-in polls: proposer or circle owner closes the poll and creates the events."""
    proposal = get_object_or_404(Event, id=proposal_id, status='pending')
    membership = get_object_or_404(Membership, user=request.user, circle=proposal.circle)
    if proposal.proposed_by_id != request.user.id and membership.role != 'owner':
        raise Http404
    if proposal.poll_type != 'optin':
        messages.error(request, "Only opt-in polls can be finalized manually.")
    else:
        targets = resolve_poll(proposal)
        if targets:
            messages.success(request, _resolved_message(proposal, targets))
            _notify_targets(proposal, targets)
        else:
            messages.warning(request, "Nobody has opted in yet, so there's nothing to add.")
    return redirect('circle_detail', circle_id=proposal.circle.id)
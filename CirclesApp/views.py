from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from . forms import RegisterForm, CircleForm, CalendarForm, JoinCircleForm, EventProposalForm, ProfileForm
from . models import Circle, Membership, Event, ProposalVote, UserProfile
from django.shortcuts import get_object_or_404
from django.http import Http404, HttpResponse
from django.contrib import messages
from datetime import timedelta, datetime, time
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.core.mail import send_mail
from icalendar import Calendar as ICalCalendar, Event as ICalEvent

HOURS = range(0,24)

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
                username = username, 
                password = password,
                email=form.cleaned_data.get('email', '')
                )
            UserProfile.objects.create(user=user)
            login(request, user)
            return redirect('home')
    else: 
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form':form})


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
            Membership.objects.create(user = request.user, circle = circle, role = 'owner')
            return redirect('home')
    else:
        form = CircleForm()

    return render(request, 'circles_app/create_circle.html', {'form':form})

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
                created = 0
                for offset in range(form.cleaned_data['num_weeks'] * 7):
                    day = first_day + timedelta(days=offset)
                    if day.weekday() in weekdays:
                        occurrence_start = timezone.make_aware(datetime.combine(day, start_dt.time()))
                        Event.objects.create(
                            user=request.user,
                            start_time=occurrence_start,
                            end_time=occurrence_start + duration,
                            event_name=form.cleaned_data['event_name'],
                            event_description=form.cleaned_data['event_description'],
                        )
                        created += 1
                messages.success(request, f"Added {created} events.")
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
    circle = get_object_or_404(Circle, id = circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if not is_member:
        raise Http404

    memberships = circle.memberships.all()

    monday = get_week_monday(request)
    days = [monday + timedelta(days=i) for i in range(7)]

    member_ids = Membership.objects.filter(circle=circle).values_list('user_id', flat=True)
    total_members = member_ids.count()

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
            })
        grid.append({'hour': hour, 'cells': cells})

    SLEEP_HOURS = set(range(22, 24)) | set(range(0, 6))  # 10PM–6AM
    SLEEP_PENALTY = 2  # ranking-only: treat a sleep-hour slot as if this many fewer people were free

    best_slot = None
    best_score = None
    if total_members > 1:   
        for row in grid:
            penalty = SLEEP_PENALTY if row['hour'] in SLEEP_HOURS else 0
            for cell in row['cells']:
                score = cell['free'] - penalty
                if best_score is None or score > best_score:
                    best_score = score
                    best_slot = cell

    proposals = Event.objects.filter(circle=circle, status='pending').order_by('-proposed_at')
    user_votes = {
        v.event_id: v.choice
        for v in ProposalVote.objects.filter(user=request.user, event__circle=circle)
    }

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
    return render(request, 'circles_app/home.html',
                  {'memberships': user_memberships, 'join_form': join_form})


@login_required
def propose_event_view(request, circle_id):
    circle = get_object_or_404(Circle, id=circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if not is_member:
        raise Http404

    if request.method == "POST":
        form = EventProposalForm(request.POST)
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
        form = EventProposalForm()

    return render(request, 'circles_app/propose_event.html', {'form': form, 'circle': circle})


@login_required
def vote_proposal_view(request, proposal_id):
    proposal = get_object_or_404(Event, id=proposal_id, status='pending')
    is_member = Membership.objects.filter(user=request.user, circle=proposal.circle).exists()
    if not is_member:
        raise Http404

    if request.method == "POST":
        choice = request.POST.get('choice')
        if choice not in ('yes', 'no'):
            messages.error(request, "Invalid vote.")
            return redirect('circle_detail', circle_id=proposal.circle.id)

        ProposalVote.objects.update_or_create(
            event=proposal, user=request.user, defaults={'choice': choice}
        )

        if proposal.has_passed_threshold():
            proposal.status = 'approved'
            proposal.user = proposal.proposed_by
            proposal.save()

            members = Membership.objects.filter(circle=proposal.circle).exclude(
                user=proposal.proposed_by
            ).select_related('user')
            for member in members:
                Event.objects.get_or_create(
                    user=member.user,
                    circle=proposal.circle,
                    start_time=proposal.start_time,
                    end_time=proposal.end_time,
                    event_name=proposal.event_name,
                    defaults={
                        'event_description': proposal.event_description,
                        'status': 'approved',
                        'proposed_by': proposal.proposed_by,
                    },
                )
            messages.success(request, f"'{proposal.event_name}' passed and was added to everyone's calendar!")
            notify_circle_members(
                proposal.circle,
                f"Event approved in {proposal.circle.circle_name}",
                f"'{proposal.event_name}' passed and was added to everyone's calendar!",
            )
        else:
            messages.success(request, "Vote recorded.")

    return redirect('circle_detail', circle_id=proposal.circle.id)

@login_required
def profile_settings_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, "Timezone updated.")
            return redirect('home')
    else:
        form = ProfileForm(instance=profile)
    return render(request, 'circles_app/profile_settings.html', {'form': form})

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
def import_calendar_view(request):
    if request.method == "POST":
        form = ICSUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['ics_file']
            try:
                cal = ICalCalendar.from_ical(uploaded_file.read())
            except ValueError:
                messages.error(request, "That doesn't look like a valid .ics file.")
                return redirect('import_calendar')

            created = 0
            for component in cal.walk('VEVENT'):
                raw_start = component.get('dtstart')
                raw_end = component.get('dtend')
                if raw_start is None or raw_end is None:
                    continue

                start_dt = _ics_value_to_aware(raw_start.dt, end_of_day=False)
                end_dt = _ics_value_to_aware(raw_end.dt, end_of_day=True)

                Event.objects.create(
                    user=request.user,
                    start_time=start_dt,
                    end_time=end_dt,
                    event_name=str(component.get('summary', 'Imported Event'))[:32],
                    event_description=str(component.get('description', '')),
                )
                created += 1

            messages.success(request, f"Imported {created} events.")
            return redirect('calendar')
    else:
        form = ICSUploadForm()
    return render(request, 'circles_app/import_calendar.html', {'form': form})

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

def _ics_value_to_aware(value, end_of_day):
    if isinstance(value, datetime):
        return value if timezone.is_aware(value) else timezone.make_aware(value)
    clock = time.max if end_of_day else time.min
    return timezone.make_aware(datetime.combine(value, clock))

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
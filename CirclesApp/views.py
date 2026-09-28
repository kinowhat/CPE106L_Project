from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib.auth.models import User
from . forms import RegisterForm, CircleForm, CalendarForm, JoinCircleForm
from . models import Circle, Membership, Event
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.contrib import messages
from datetime import timedelta, datetime, time
from django.utils import timezone

HOURS = range(0,24)

def get_week_monday(request):
    week_param = request.GET.get('week')
    if week_param:
        try:
            day = datetime.strptime(week_param, '%Y-%m-%d').date()
        except ValueError:
            day = timezone.localdate
    else:
        day = timezone.localdate()
        return day - timedelta(days=day.weekday())


def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data.get("username")
            password = form.cleaned_data.get("password")
            user = User.objects.create_user(username = username, password = password)
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
        user = authenticate(request, username=username, password = password)
        if user is not None:
            login(request, user)
            next_url = request.POST.get('next') or request.GET.get('next') or 'home'
            return redirect(next_url)
        else:
            error_message = "Invalid Credentials"
    return render(request, 'accounts/login.html', {'error': error_message})

def logout_view(request):
    if request.method == "POST":
        logout(request)
        return redirect('login')
    else:
        return redirect('home')

@login_required
def home_view(request):
    user_memberships = Membership.objects.filter(user = request.user)
    join_form = JoinCircleForm()
    return render(request, 'circles_app/home.html', {'memberships': user_memberships, 'join_form':join_form})

class ProtectedView(LoginRequiredMixin, View):
    login_url = '/login/'
    redirect_field_name = 'redirect_to'

    def get(self, request):
        return render(request, 'registration/protected.html')

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

    user_events = Event.objects.filter(user=request.user).order_by('start_time')
    return render(request, 'circles_app/calendar.html', {'form': form, 'events': user_events})

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
            cell_start = timezone.make_aware(datetime.combine(day,time(hour=hour)))
            cell_end = cell_start + timedelta(hours=1)
            busy_users = {e.user_id for e in events if e.start_time < e.cell_end and cell_start < e.end_time}
            free = total_members - len(busy_users)
            ratio = free / total_members if total_members else 0
            cells.append({'free':free, 'total': total_members, 'ratio':ratio})
        grid.append({'hour':hour, 'cells':cells})

    return render(request, 'circles_app/circle_detail.html', {
        'circle':circle, 
        'memberships':memberships,
        'days':days,
        'grid':grid,
        'prev_week': monday - timedelta(days=7),
        'next_week': monday + timedelta(days=7),
        })

@login_required
def join_circle_view(request, code):
    circle = get_object_or_404(Circle, invite_code=code)
    already_member = Membership.objects.filter(user=request.user, circle = circle).exists()
    if request.method == "POST":
        Membership.objects.get_or_create(user=request.user,circle=circle,defaults={'role': 'member'},)
        return redirect('circle_detail', circle_id=circle.id)
    return render(request, 'circles_app/join_preview.html', {'circle':circle, 'already_member':already_member})

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
def add_repeating_event_view(request):
    if request.method == "POST":
        form = RepeatingEventForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            selected_weekdays = {int(d) for d in data['weekdays']}
            first_date = data['start_date']
            num_days = data['num_weeks'] * 7

            created_count = 0
            for offset in range(num_days):
                day = first_date + timedelta(days=offset)
                if day.weekday() in selected_weekdays:
                    start_dt = timezone.make_aware(datetime.combine(day, data['start_time']))
                    end_dt = timezone.make_aware(datetime.combine(day, data['end_time']))
                    Event.objects.create(
                        user=request.user,
                        start_time=start_dt,
                        end_time=end_dt,
                        event_name=data['event_name'],
                        event_description=data['event_description'],
                    )
                    created_count += 1

            messages.success(request, f"Created {created_count} events.")
            return redirect('calendar')
    else:
        form = RepeatingEventForm()

    return render(request, 'circles_app/add_repeating_event.html', {'form': form})



#Home View
# Using the decorator


# Create your views here.

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
            calendar = form.save(commit = False)
            calendar.user = request.user
            calendar.save()

            return redirect('calendar')
    else:
        form = CalendarForm()

    user_events = Event.objects.filter(user=request.user).order_by('start_time')
    return render(request, 'circles_app/calendar.html', {'form':form, 'events':user_events})


@login_required
def circle_detail_view(request, circle_id):
    circle = get_object_or_404(Circle, id = circle_id)
    is_member = Membership.objects.filter(user=request.user, circle=circle).exists()
    if not is_member:
        raise Http404

    memberships = circle.memberships.all()
    return render(request, 'circles_app/circle_detail.html', {'circle':circle, 'memberships':memberships,})

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
    




#Home View
# Using the decorator


# Create your views here.

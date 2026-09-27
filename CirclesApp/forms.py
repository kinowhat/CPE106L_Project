from django import forms
from django.contrib.auth.models import User
from . models import Circle, User, Event

class RegisterForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    password_confirm = forms.CharField(widget=forms.PasswordInput, label="Confirm Password")

    class Meta:
        model = User
        fields = ['username', 'password', 'password_confirm']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            raise forms.ValidationError("Passwords do not match!")
        return cleaned_data

class CircleForm(forms.ModelForm):
    class Meta:
        model = Circle
        fields = ['circle_name', 'circle_tag']

class CalendarForm(forms.ModelForm):
    start_time = forms.DateTimeField(widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))
    end_time = forms.DateTimeField(widget=forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'}))

    class Meta:
        model = Event
        fields = ['start_time', 'end_time', 'event_name', 'event_description']

    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        if start_time and end_time and start_time >= end_time: 
            raise forms.ValidationError("Start and End times are in the wrong order!")
        return cleaned_data
class JoinCircleForm(forms.Form):
    invite_code = forms.CharField(max_length=12, label = "Invite Code")
    

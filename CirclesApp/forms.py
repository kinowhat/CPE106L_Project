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

class CalendarForm(forms.ModelForm)
    class META:
        model = Event
        fields = ['start_time, end_time, event_name, event_description']

    

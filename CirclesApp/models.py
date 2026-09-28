from django.db import models
import secrets
from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.timezone import localdate
# Create your models here.
def create_code():
    return secrets.token_urlsafe(6)

def get_start_of_day():
    return timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

def get_end_of_day():
    return timezone.now().replace(hour=23, minute=59, second=59, microsecond=9999)

class Circle(models.Model):
    circle_name = models.CharField(max_length=32)
    creation_date = models.DateTimeField(auto_now_add=True)
    invite_code = models.CharField(max_length=12, unique=True, default=create_code)
    circle_tag = models.CharField(max_length=64)
 
    def __str__(self):
        return self.circle_name


class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name = "memberships")
    role = models.CharField(max_length=10, default="member")
    class Meta:
        unique_together =("user", "circle")

class Event(models.Model):
    STATUS_CHOICES = [
        ('personal', 'Personal'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    circle = models.ForeignKey(
        Circle, on_delete=models.CASCADE, null=True, blank=True, related_name='circle_events'
    )
    proposed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='proposed_events'
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='personal')
    proposed_at = models.DateTimeField(null=True, blank=True, auto_now_add=True)

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    event_name = models.CharField(max_length=32)
    event_description = models.TextField()

    def __str__(self):
        return f"{self.event_name} - {self.user.username if self.user else 'proposal'}"

    def yes_votes(self):
        return self.votes.filter(choice='yes').count()

    def no_votes(self):
        return self.votes.filter(choice='no').count()

    def total_members(self):
        return self.circle.memberships.count() if self.circle else 0

    def has_passed_threshold(self):
        total = self.total_members()
        return total > 0 and self.yes_votes() > total / 2


class ProposalVote(models.Model):
    CHOICE_CHOICES = [('yes', 'Yes'), ('no', 'No')]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='votes')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    choice = models.CharField(max_length=3, choices=CHOICE_CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('event', 'user')
    



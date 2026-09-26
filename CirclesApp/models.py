from django.db import models
import secrets
from django.contrib.auth.models import User
# Create your models here.
def create_code():
    return secrets.token_urlsafe(6)

class Circle(models.Model):
    circle_name = models.CharField(max_length=32)
    creation_date = models.DateTimeField(auto_now_add=True)
    invite_code = models.CharField(max_length=12, unique=True, default=create_code )
    circle_tag = models.CharField(max_length=64)

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name = "memberships")
    role = models.CharField(max_length=10, default="member")
    class Meta:
        unique_together =("user", "circle")

class Event(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    event_name = models.CharField(max_length=32)
    event_description = models.TextField(max_length=300)

    def __str__(self):
        return f"{self.event_name} - {self.user.username}"
    



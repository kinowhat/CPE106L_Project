from django.db import models
import secrets
from django.contrib.auth.models import User
# Create your models here.
def create_code():
    return secrets.token_urlsafe(6)

class Circle(models.Model):
    name = models.CharField(max_length=32)
    creation_date = models.DateTimeField(auto_now_add=True)
    invite_code = models.CharField(max_length=12, unique=True, default=create_code() )

class Membership(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    circle = models.ForeignKey(Circle, on_delete=models.CASCADE, related_name = "memberships")
    role = models.CharField(max_length=10, default="member")
    class Meta:
        unique_together =("user", "circle")



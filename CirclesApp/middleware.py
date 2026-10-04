from django.utils import timezone
from .models import UserProfile
import zoneinfo

class TimezoneMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                tz_name = request.user.profile.timezone
                timezone.activate(zoneinfo.ZoneInfo(tz_name))
            except (UserProfile.DoesNotExist, zoneinfo.ZoneInfoNotFoundError):
                timezone.deactivate()
        else:
            timezone.deactivate()
        return self.get_response(request)
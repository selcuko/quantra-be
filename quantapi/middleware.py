

from django.conf import settings
from django.http import Http404, HttpResponseForbidden
from quantapi.models import WhitelistedUser

class WhitelistedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'accounts' in request.path:
            return self.get_response(request)
        whitelisted_default = settings.WHITELISTED_DEFAULT_EMAILS
        if request.user.is_anonymous or request.user.is_staff or request.user.is_superuser:
            return self.get_response(request)
        if request.user.is_authenticated and request.user.email in whitelisted_default:
            return self.get_response(request)
        elif WhitelistedUser.objects.filter(user=request.user, allowed=True).exists():
            return self.get_response(request)
        else:
            return HttpResponseForbidden('Forbidden')

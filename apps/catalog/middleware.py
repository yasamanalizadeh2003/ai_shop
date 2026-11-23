from urllib.parse import unquote

from django.http import HttpResponsePermanentRedirect

from .models import Redirect


class RedirectFallbackMiddleware:
    """On a 404, look the path up in the redirects table and answer with a 301."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code != 404:
            return response
        path = unquote(request.path)
        target = Redirect.objects.filter(old_path=path).values_list("new_path", flat=True).first()
        if target:
            query = request.META.get("QUERY_STRING")
            return HttpResponsePermanentRedirect(f"{target}?{query}" if query else target)
        return response

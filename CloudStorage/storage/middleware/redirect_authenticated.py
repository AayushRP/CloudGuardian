from django.shortcuts import redirect
from django.urls import reverse

class RedirectAuthenticatedUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == reverse('login') or request.path == reverse('sign_up'):
            if request.user.is_authenticated:
                return redirect('home')  # use correct name

        return self.get_response(request)

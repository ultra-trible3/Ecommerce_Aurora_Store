from django.template.loader import render_to_string
from django.http import HttpRequest
from django.contrib.auth import get_user_model

User = get_user_model()
request = HttpRequest()
request.user = User.objects.get(email='admin@example.com')
request.META = {'HTTP_HOST': 'localhost'}

html = render_to_string('includes/header.html', request=request)
print('mobileSearchBtn:', 'mobileSearch' in html)
print('mobileTopbar:', 'au-mobile-topbar' in html)
print('mobileSearch offcanvas:', 'id="mobileSearch"' in html)
print('mobileNav offcanvas:', 'id="mobileNav"' in html)
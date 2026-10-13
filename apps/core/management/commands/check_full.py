from django.template.loader import render_to_string
from django.http import HttpRequest
from django.contrib.auth import get_user_model

User = get_user_model()
request = HttpRequest()
request.user = User.objects.get(email='admin@example.com')
request.META = {'HTTP_HOST': 'localhost'}

# Render the full base template
html = render_to_string('base.html', request=request)

print('mobileSearchBtn:', 'mobileSearch' in html)
print('mobileTopbar:', 'au-mobile-topbar' in html)
print('mobileSearch offcanvas:', 'id=\"mobileSearch\"' in html)
print('mobileNav offcanvas:', 'id=\"mobileNav\"' in html)

idx = html.find('mobileSearch')
if idx >= 0:
    print('Found mobileSearch at:', idx)
    print(html[max(0,idx-100):idx+200])
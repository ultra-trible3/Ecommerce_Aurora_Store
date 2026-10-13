from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission

class CheckPerms(TestCase):
    def test_check(self):
        User = get_user_model()
        for u in User.objects.filter(is_staff=True):
            groups = list(u.groups.values_list('name', flat=True))
            perms = list(u.user_permissions.filter(codename__icontains='order').values_list('codename', flat=True))
            group_perms = []
            for g in u.groups.all():
                group_perms.extend(list(g.permissions.filter(codename__icontains='order').values_list('codename', flat=True)))
            print(f'{u.email}: role={u.role}, is_superuser={u.is_superuser}, is_staff={u.is_staff}')
            print(f'  groups: {groups}')
            print(f'  user perms (order): {perms}')
            print(f'  group perms (order): {group_perms}')
            print()
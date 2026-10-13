# Aurora Store — Test & Code Audit Report

**Date:** 2026-10-11 · **Django:** 5.2.17 · **Suite:** `python manage.py test -v 1`

---

## 1. Test execution summary

| Metric | Result |
|---|---|
| Tests found | 133 |
| Passed | **133** |
| Failed / errors | **0** |
| System checks | 0 issues, 0 silenced |
| Runtime | ~8s |

Suites: `apps/core` (smoke, theme, admin, check-perms, i18n), `apps/accounts`, `apps/cart`, `apps/orders`, `apps/dashboard` (permissions), `apps/notifications`, `apps/payments`.

### Failures found during this audit (now fixed)

| # | Failure | Root cause | Fix |
|---|---|---|---|
| F1 | `test_stripe_option_hidden_without_keys`, `test_unconfigured_stripe_rejected_server_side` | Tests were not hermetic — they assumed no Stripe keys, but the new `.env` provides them, so the Stripe option legitimately appeared | Added `@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLIC_KEY="")` in `apps/payments/tests_payments.py` |
| F2 | *(silent, caught while auditing)* Checkout showed the PayPal blurb for **every** payment method and **no prices** on shipping rows | On Django 5.x, `BoundWidget` has no `choice_value` attribute; templates fail silently, so `{% if radio.choice_value == 'cod' %}` was always False | Replaced `radio.choice_value` → `radio.data.value` in `templates/checkout/checkout.html` (3 spots); added regression test `test_each_payment_option_shows_its_own_description` |

**Verified visually:** checkout page now renders correct per-method copy and shipping prices ($7.99 / $14.99 / $0.00, free-over-$75 badge).

---

## 2. Bugs & vulnerabilities (open findings)

### C1 — CRITICAL: Account takeover via empty email-verification token
**Location:** `apps/accounts/views.py:113-125` · `apps/accounts/models.py:36`

`verification_token` is `CharField(blank=True)` — its value for every fresh user is `""`, and after successful verification it is **cleared back to `""`**. The view does:

```python
token = request.GET.get("token", "")
user = User.objects.filter(verification_token=token).first()
...
login(request, user)   # anonymous visitor is logged in as that user
```

Visiting `/accounts/verify/?token=` (empty) matches the **first user with an empty token** and logs the attacker in as them. Affects most users of the site.

**Fix:**
```python
token = request.GET.get("token", "")
if not token:
    messages.error(request, "That confirmation link is invalid or expired.")
    return redirect("accounts:login")
user = User.objects.filter(verification_token=token).first()
```
Longer term: give the field `default=None, null=True` (migration) so empty can never match, and add token expiry.

### H1 — HIGH: Open redirect after register/login
**Location:** `apps/accounts/views.py:63` (register — **no validation at all**) and `:94-96` (login — `startswith("/")` only)

`redirect(request.GET.get("next"))` accepts any absolute URL (`/accounts/register/?next=https://evil.com`). The login check is bypassable with protocol-relative URLs: `?next=//evil.com`.

**Fix (both views):**
```python
from django.utils.http import url_has_allowed_host_and_scheme
next_url = request.GET.get("next")
if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
    return redirect(next_url)
```

### M1 — MEDIUM: Stored XSS in search-autocomplete dropdown
**Location:** `apps/catalog/views.py:214-224` → `static/js/main.js:104-113`

Product `name` / `category` are injected into the DOM via `innerHTML` string concatenation. Django autoescapes them in server-rendered templates, but the JSON endpoint returns raw values. Requires product-creation rights (staff/management portal) to plant the payload; any shopper triggers it.

**Fix (JS side, recommended):** build entries with `textContent` / `createElement`, or escape:
```js
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
```
and wrap `${p.name}` / `${p.category}` / `${p.url}` / `${p.image}` in `esc(...)`.

### m2 — MINOR (cosmetic): Shipping fallback text misleading
Shipping methods with a blank `description` all render the fallback "Standard delivery" — so "Express shipping — 1-2 business days" also says "Standard delivery" (`templates/checkout/checkout.html:166`). Suggest a neutral fallback (e.g. "Delivery to your door") or per-method seed data.

### Passed review (no action)
- **Settings/security headers:** `DEBUG` env-driven (default off in prod), HSTS/SSL redirect/secure cookies in `production.py`, `X_FRAME_OPTIONS=DENY`, nosniff, referrer policy, HttpOnly cookies.
- **Catalog queries:** `select_related`/`prefetch_related` used consistently (`apps/catalog/services.py`, detail view); no obvious N+1.
- **CSRF/throttling:** cart/checkout POSTs CSRF-protected; login + search-suggest throttled by IP.

---

## 3. Coverage gaps

| App / area | Status |
|---|---|
| `banners` | **No dedicated tests** (show-once modal, seen/impression endpoints untested) |
| `coupons` | Only covered indirectly via cart smoke test (apply + totals); no expiry/over-limit/invalid-code cases |
| `inventory` | Stock decrement covered by guest-checkout test; no adjustment/low-stock/threshold tests |
| `reviews` | No tests (submission, moderation, approval gating) |
| Payments | `tests_payments.py` covers COD/Stripe availability/ordering; **webhook failure paths, PayPal happy-path, refund flow untested** |
| Security findings above | No regression tests for verify-email / `next` validation / autocomplete escaping |

---

## 4. Actionable recommendations (priority order)

1. **C1** — reject empty `verification_token` in `verify_email` (+ migration to `null=True` default). 5-minute fix, prevents full account takeover.
2. **H1** — replace both `next` handlers with `url_has_allowed_host_and_scheme`.
3. **M1** — escape autocomplete fields in `main.js`.
4. Add regression tests: `verify_email?token=` returns redirect-to-login and does **not** authenticate; `?next=//evil.com` lands on dashboard, not external host.
5. Add small suites for banners, coupons edge cases, review moderation.
6. **m2** — neutralize shipping-description fallback copy.

Items 1–3 were intentionally **not** auto-applied — say the word and I'll implement them with tests.

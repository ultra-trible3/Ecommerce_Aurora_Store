# Aurora Store — Django E-commerce Platform

A production-oriented e-commerce storefront **and** a custom management portal,
built with **Django** and server-rendered templates (no SPA). Everything runs on
SQLite for local development and is PostgreSQL-ready for production. Cash on
delivery works out of the box, while **Stripe** card payments and **PayPal**
light up automatically as soon as their keys are configured.

The interface is fully bilingual — **English (LTR)** and **Arabic (RTL)** — down
to translated catalogue fields, floored prices (`$`, Western digits) and a
per-request language switcher.

---

## Table of contents

- [Highlights](#highlights)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Demo accounts](#demo-accounts)
- [URL map](#url-map)
- [Internationalization (English / Arabic)](#internationalization-english--arabic)
- [Single-device login](#single-device-login)
- [Management commands](#management-commands)
- [Testing & quality checks](#testing--quality-checks)
- [Project layout](#project-layout)
- [Configuration](#configuration)
- [Payments](#payments)
- [Production deployment](#production-deployment)
- [Security](#security)
- [Documentation](#documentation)

---

## Highlights

### Storefront
- **Faceted shop** — keyword search with live suggestions, category / brand /
  price / rating / colour filters, sorting, pagination, variants, related
  products, wishlist and side-by-side compare.
- **Cart** — a session cart for guests that is merged into a database cart on
  login, with server-side pricing and coupon validation on every mutation.
- **Checkout** — a multi-step flow (contact → address → shipping quote →
  payment → review → confirmation) with guest checkout, saved addresses and a
  server-authoritative total.
- **Orders** — order history, cancellation with automatic stock restore, public
  order tracking, printable invoice and a generated **PDF invoice**.
- **Payments** — cash on delivery always available; Stripe Elements and PayPal
  when configured.
- **Reviews** — moderated product reviews (verified-purchase badge), Q&A and
  storefront replies.
- **Accounts** — email-based registration with verification, password reset,
  profile and address book, avatar upload with cropper.
- **Engagement** — notification centre with a 15-second poll, newsletter
  signup, stock alerts, promo banners and deal pop-ups.
- **SEO** — `sitemap.xml`, `robots.txt`, canonical and Open Graph tags,
  semantic markup.

### Management portal — `/management/`
- **Dashboard** with revenue charts, order-status breakdown, low-stock and
  moderation queues.
- **Catalogue** — product / category / brand CRUD, archiving, variants and
  stock adjustments backed by a full stock ledger.
- **Orders** — detail views with guarded status transitions, payment marking,
  refunds, returns workflow, internal notes, invoice and CSV export.
- **People** — customers, newsletter subscribers, notifications.
- **Promotions** — coupon CRUD, review moderation, banners.
- **Operations** — inventory movements history, adjustment log, audit trail.
- **Reports** — sales / category / customer / product reports with CSV and PDF
  export.
- **Settings** — editable store settings (name, support details, tax, etc.).
- **RBAC** — permission groups for **Admin**, **Inventory Manager**,
  **Order Manager**, **Content Manager** and **Support Agent**.

### Platform
- Custom user model with **email login** and roles (Customer / Staff / Admin).
- **Bilingual EN/AR with RTL** — `django-modeltranslation` for content plus a
  full PO catalogue for the UI and JavaScript.
- **Single-device login** — signing in on a new device signs the previous one
  out (see below).
- Generic notifications, inline-styled transactional emails (HTML + text),
  cache-backed rate limiting, security headers and WhiteNoise static serving.

---

## Tech stack

| Layer | Technology |
| --- | --- |
| Language | Python 3.11+ |
| Framework | Django 5 (MVT, no SPA) |
| Database | SQLite (dev) · PostgreSQL via `psycopg2` (prod) |
| Content i18n | `django-modeltranslation` |
| Cache | LocMemCache (dev) · Redis (optional, production) |
| Static files | WhiteNoise + compressed manifest storage |
| Frontend | Bootstrap 5, vanilla ES6 JS, Bootstrap Icons, Chart.js (all vendored) |
| Payments | Stripe (PaymentIntents) · PayPal (Checkout) · Cash on delivery |
| Documents | `reportlab` (PDF invoices/reports) · `openpyxl` (XLSX) |
| Arabic support | `arabic-reshaper` + `python-bidi` (PDF rendering) |
| Email | Console backend (dev) · SMTP (prod) |
| Testing | Django `TestCase` |

---

## Quick start

### Prerequisites
- Python **3.11+**
- (Optional) GNU gettext — required only to compile translations
  (`msgfmt` on `PATH`; on Windows: `C:\gettext\bin`).

### Setup (Windows / PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1

pip install -r requirements.txt
Copy-Item .env.example .env          # optional — every value has a safe default

python manage.py migrate
python manage.py seed_demo           # demo catalogue, accounts and orders
python manage.py runserver
```

On macOS / Linux the equivalent commands are `source .venv/bin/activate`,
`cp .env.example .env` and the same `manage.py` calls.

Then open:

- Storefront → <http://localhost:8000/>
- Management portal → <http://localhost:8000/management/>
- Django admin → <http://localhost:8000/django-admin/>

> `python manage.py seed_demo --reset` rebuilds the demo data from scratch.

---

## Demo accounts

Created by `seed_demo` (passwords can be overridden with `--admin-password`
and per-user flags):

| Email | Password | Access |
| --- | --- | --- |
| `admin@example.com` | `admin12345` | Superuser — portal + Django admin |
| `inventory@example.com` | `admin12345` | Inventory Manager group |
| `orders@example.com` | `admin12345` | Order Manager group |
| `content@example.com` | `admin12345` | Content Manager group |
| `support@example.com` | `admin12345` | Support Agent group |
| `mia@example.com` | `customer12345` | Customer account |
| `jordan@example.com` | `customer12345` | Customer account |
| `sam@example.com` | `customer12345` | Customer account |

---

## URL map

| Path | Purpose |
| --- | --- |
| `/` | Home (deals, banners, featured) |
| `/shop/`, `/shop/category/<slug>/`, `/shop/brand/<slug>/` | Faceted catalogue |
| `/product/<slug>/`, `/search/`, `/brands/` | Product detail, search, brands |
| `/cart/`, `/wishlist/`, `/compare/` | Cart, wishlist and compare (AJAX + drawers) |
| `/checkout/…`, `/orders/…`, `/orders/track/<no>/` | Checkout, orders, tracking |
| `/accounts/…` | Login, register, profile, addresses, password reset |
| `/payments/…` | Stripe / PayPal callbacks and webhook |
| `/reviews/…`, `/notifications/…`, `/newsletter/…` | Reviews, notifications, newsletter |
| `/management/…` | Custom management portal (staff only) |
| `/django-admin/` | Stock Django admin |
| `/i18n/setlang/` | Language switcher endpoint |
| `/sitemap.xml`, `/robots.txt` | SEO |

---

## Internationalization (English / Arabic)

- **UI strings** live in a single PO catalogue: `locale/en` and `locale/ar`
  (`LOCALE_PATHS = [BASE_DIR / "locale"]`). Views use `gettext`, models,
  forms, validators, emails and admin use `gettext_lazy`.
- **Client-side strings** are exported to JS through
  `apps/core/i18n_catalog.py` → `window.aul10n` / `t()` / `ts()`, so AJAX
  fragments are translated too.
- **Content fields** (product/category/brand names, descriptions, SEO copy,
  banners, shipping labels…) are translated with `django-modeltranslation`.
  English never falls back to Arabic; Arabic falls back to English.
- **RTL** is handled with logical CSS properties plus a bundled
  `static/css/rtl.css`; the document direction comes from
  `{% get_current_language_bidi %}`.
- Prices keep the `$` symbol and Western digits in both languages.

Compile the catalogues after changing any `gettext` string:

```powershell
$env:PATH += ";C:\gettext\bin"        # Windows, if gettext is not already on PATH
python manage.py makemessages -l en -l ar
python manage.py compilemessages
python manage.py check_i18n           # verifies the catalogues are complete
```

`check_i18n` fails on untranslated / fuzzy / obsolete entries, mismatched
`%(name)s` tokens, or plural forms that do not match the header’s `nplurals`.

---

## Single-device login

Each account may stay signed in on **one device at a time**; a new login signs
the previous device out near-instantly.

- Every browser is tagged with a persistent, HttpOnly `device_id` cookie,
  generated server-side on first contact.
- On every successful login, a `user_logged_in` signal
  (`apps/accounts/signals.py`) records the freshly rotated session key plus the
  device id on the user — a single choke point that also covers registration
  auto-login, email-verification auto-login and the Django admin.
- `SingleDeviceSessionMiddleware` (`apps/core/middleware.py`) signs out any
  authenticated session whose key no longer matches:
  - navigation → redirect to the login page with an explanatory notice;
  - AJAX → `{"authenticated": false, "session_kicked": true}`.
- The storefront notification poll (every 15 s) reacts to the revoked session
  and returns the user to the login page; a short-lived marker cookie lets the
  login page explain *why* even when a background request notices first.

---

## Management commands

| Command | Purpose |
| --- | --- |
| `python manage.py seed_demo [--reset]` | Seed a demo catalogue, accounts, reviews, promos and orders |
| `python manage.py setup_groups` | Create/refresh portal permission groups and their permissions |
| `python manage.py check_i18n` | Verify PO catalogues and the JS message catalogue |
| `python manage.py send_abandoned_cart_emails` | Send recovery emails for idle carts |
| `python manage.py cleanup_payments` | Clean up expired/abandoned payment records |
| `python manage.py collectstatic` | Gather static assets (production) |
| `python manage.py createsuperuser` | Create an admin account manually |

(`apps/core/management/commands/` also ships a couple of developer
diagnostics such as `check_full`.)

---

## Testing & quality checks

```powershell
python manage.py check           # system checks
python manage.py test            # full test suite (200+ tests)
python manage.py check_i18n      # translation integrity
```

The suite covers the full guest and authenticated purchase flows
(cart → coupon → checkout → stock deduction → confirmation email), account
flows, payment webhooks, the management portal, the i18n catalogues, the
single-device login and every transactional email template.

> On Windows, a `logging` shutdown line may be printed and the process may exit
> with code `1` even when every check passes — inspect the output, not the exit
> code.

---

## Project layout

```
apps/
  core/           shared models, middleware, context processors, sitemaps, utils
  accounts/       custom user, addresses, auth signals, single-device login
  catalog/        categories, brands, products, variants, attributes, stock alerts
  inventory/      stock ledger and adjustments
  cart/           session + database carts, wishlist, compare
  coupons/        promotions and redemptions
  orders/         checkout, shipping quotes, order lifecycle, returns, invoices
  payments/       COD, Stripe, PayPal, webhooks, refunds
  reviews/        moderated reviews, Q&A
  notifications/  in-app notifications, newsletter, transactional email
  banners/        hero slider + deal pop-ups with targeting and scheduling
  dashboard/      the /management/ portal (views, RBAC, reports, exports)
config/
  settings/       base / dev / production settings packages
  urls.py         root URL configuration
  logging_setup.py structured logging configuration
templates/        storefront, management portal, emails, errors
static/           css (main, dark, rtl, management), js, vendored libs, fonts
locale/           en/ and ar/ PO catalogues
media/            user uploads (git-ignored)
docs/             audit reports and notes
```

---

## Configuration

All configuration is read from environment variables, optionally loaded from a
`.env` file at the project root (see `.env.example` for the full documented
list). Nothing secret is hard-coded.

Key settings:

| Variable | Default | Notes |
| --- | --- | --- |
| `SECRET_KEY` | insecure dev value | **set in production** |
| `DEBUG` | `True` (dev) | `False` in production |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | comma-separated |
| `CSRF_TRUSTED_ORIGINS` | — | required behind a proxy |
| `DATABASE_URL` | SQLite | e.g. `postgres://user:pass@host:5432/store` |
| `REDIS_URL` | — | enables the Redis cache backend |
| `SITE_NAME`, `SITE_TAGLINE`, `SUPPORT_EMAIL`, `SUPPORT_PHONE` | Aurora Store | editable in `/management/settings/` |
| `CURRENCY`, `CURRENCY_SYMBOL`, `TAX_RATE` | `USD`, `$`, `0.0` | |
| `EMAIL_*` | console backend | set SMTP values for production |
| `STRIPE_SECRET_KEY`, `STRIPE_PUBLIC_KEY`, `STRIPE_WEBHOOK_SECRET` | — | enable card payments |
| `PAYPAL_CLIENT_ID`, `PAYPAL_SECRET`, `PAYPAL_MODE` | — | enable PayPal |
| `ENABLE_SSL` | `False` | turns on HSTS + secure cookies + SSL redirect |
| `SESSION_COOKIE_AGE` | 14 days | |
| `RATELIMIT_ENABLE` | `True` | cache-backed throttling |

---

## Payments

- **Cash on delivery** — needs no configuration and is always offered.
- **Stripe** — set `STRIPE_SECRET_KEY` and `STRIPE_PUBLIC_KEY`, then configure
  the webhook endpoint `/payments/stripe/webhook/` in the Stripe dashboard with
  `STRIPE_WEBHOOK_SECRET`. Webhooks are idempotent (keyed on the PaymentIntent
  id).
- **PayPal** — set `PAYPAL_CLIENT_ID` and `PAYPAL_SECRET` (and `PAYPAL_MODE`)
  to enable the Checkout capture-on-return flow.

The checkout only shows a gateway once its keys are present; totals, stock and
coupon validity are always recomputed server-side.

---

## Production deployment

```powershell
$env:DJANGO_SETTINGS_MODULE = "config.settings.production"
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application      # or any WSGI server
```

Production mode:

- uses PostgreSQL when `DATABASE_URL` is set;
- serves compressed static files through WhiteNoise;
- enables the cache middleware (Redis when `REDIS_URL` is set, LocMemCache
  otherwise);
- hardens cookies; set `ENABLE_SSL=True` behind HTTPS to turn on HSTS, secure
  cookies and the SSL redirect.

---

## Security

- CSRF protection on all state-changing requests; secure, HttpOnly session and
  CSRF cookies in production.
- Server-side price, stock and coupon validation — client values are never
  trusted.
- Password validators (minimum length 8, similarity, common-password and
  numeric checks).
- Cache-backed rate limiting plus per-endpoint throttling on sensitive actions
  (login, password reset, checkout).
- Security headers (`X-Content-Type-Options`, `Referrer-Policy`,
  `X-Frame-Options: DENY`), upload type/size validation, and open-redirect
  protection on `next` parameters.
- Single-device login to limit session hijacking damage.

---

## Documentation

- `docs/ecommerce-audit.md` — full platform audit (features, findings, plan).
- `docs/TEST-AUDIT.md` — security-related regression notes and tests.

---

*Built with Django. Server-rendered, bilingual and production-minded.*

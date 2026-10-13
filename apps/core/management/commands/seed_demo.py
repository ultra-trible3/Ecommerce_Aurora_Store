"""Seed a demo storefront: catalog, accounts, promos and orders."""
import io
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Address
from apps.catalog.models import Brand, Category, Product
from apps.coupons.models import Coupon
from apps.inventory.models import StockTransaction
from apps.notifications.models import NewsletterSubscriber, Notification
from apps.orders.models import Order, OrderItem, OrderStatusHistory, ShippingMethod
from apps.payments.models import Payment
from apps.reviews.models import Review
from apps.reviews.services import refresh_product_rating

User = get_user_model()

CATEGORIES = [
    ("Apparel", "Technical layers built for shifting weather."),
    ("Footwear", "Grip, cushioning and comfort for long days outside."),
    ("Accessories", "The small kit that makes a big difference."),
    ("Gear", "Shelter, sleep systems and camp essentials."),
]

SUBCATEGORIES = [
    ("Tents & Shelter", "Gear", "Roomy, light and storm ready."),
    ("Lighting", "Gear", "Headlamps and camp lights."),
]

BRANDS = [
    ("Aurora", "Designed in the Rockies for everyday exploration."),
    ("Northbound", "Hardwearing kit for cold mornings and long trails."),
    ("Solstice", "Sun friendly, packable and light."),
]

PRODUCTS = [
    ("Trailshell Jacket", "TSJ-100", "Apparel", "Aurora", 189, 159, 24,
     "Waterproof shell with pit zips and a packable hood.",
     "A three-layer waterproof shell cut for movement. Pit zips dump heat on "
     "the climb, taped seams keep the rain out and the hood stows flat when "
     "the sky clears.", True, True, False),
    ("Summit Fleece", "SF-110", "Apparel", "Northbound", 98, None, 40,
     "Grid fleece that breathes hard on the up.",
     "Mid-weight grid fleece with a full zip, thumb loops and a chin guard. "
     "Warm where you need it, vented where you do not.", False, False, False),
    ("Base Layer Crew", "BL-120", "Apparel", "Northbound", 45, None, 60,
     "Merino blend crew that stays fresh for days.",
     "A 17.5 micron merino blend that wicks fast and resists odour. Flatlock "
     "seams sit smoothly under a pack.", False, False, True),
    ("Rain Poncho", "RP-130", "Apparel", "Solstice", 59, 45, 12,
     "Packable poncho that covers you and your pack.",
     "Sealed seams, a two-way hood and a stuff sack small enough for a "
     "hipbelt pocket.", False, False, True),
    ("Alpine Beanie", "AB-140", "Apparel", "Aurora", 28, None, 80,
     "Fine gauge merino beanie, cuffed.",
     "Warm, itch free and low profile under a helmet.", False, False, False),
    ("Ridgeline Boot", "RB-200", "Footwear", "Northbound", 210, 179, 18,
     "Leather hiker with a grippy Vibram style outsole.",
     "Full grain leather upper, cushioned midsole and a lugged outsole that "
     "bites on wet rock. Recraftable, so one pair lasts seasons.", True, True, False),
    ("Trailrunner Sneaker", "TR-210", "Footwear", "Solstice", 135, None, 30,
     "Light trainer for road to trail days.",
     "Breathable mesh, a rock plate and a 6 mm drop that feels fast without "
     "being harsh.", False, True, False),
    ("Camp Sandal", "CS-220", "Footwear", "Solstice", 72, None, 2,
     "Strappy camp sandal for evenings off the trail.",
     "Adjustable straps, a grippy sole and a footbed that drains fast.",
     False, False, False),
    ("Trek Sock 3-Pack", "SS-230", "Footwear", "Northbound", 26, None, 90,
     "Cushioned crew socks with a mesh vent zone.",
     "Blister resistant heel and toe, arch band and mesh over the instep.",
     False, True, False),
    ("Meridian Daypack", "MB-300", "Accessories", "Aurora", 118, 95, 22,
     "24 L daypack with a vented back panel.",
     "Roll top closure, hydration sleeve, pole loops and a hipbelt that "
     "actually transfers load.", True, False, False),
    ("Trail Belt Pouch", "TB-310", "Accessories", "Aurora", 34, None, 5,
     "Zip pouch for phone, keys and gels.",
     "Fits a large phone, has a key clip and sits flat under a harness.",
     False, False, False),
    ("Trekking Poles", "TP-320", "Accessories", "Northbound", 89, None, 16,
     "Three section aluminium poles with cork grips.",
     "Fast lock adjust, tungsten tips and snow baskets included.",
     False, False, True),
    ("Solar Charger", "SC-330", "Accessories", "Solstice", 79, 65, 9,
     "Foldable 21 W panel for top ups on the move.",
     "USB-C and USB-A output, a kickstand and a weatherproof housing.",
     False, False, False),
    ("Aurora 2P Tent", "AT-400", "Gear", "Aurora", 320, 279, 7,
     "Two person tent that pitches fast in wind.",
     "Two doors, two vestibules, a full footprint and cross winds tested "
     "to 60 km/h. 2.1 kg packed.", True, True, False),
    ("Ultralight Sleeping Bag", "US-410", "Gear", "Northbound", 175, None, 11,
     "650 fill down bag rated to 5 C.",
     "Box baffle construction, a contoured hood and a full length zip "
     "draft tube. Packs to the size of a water bottle.", False, False, False),
    ("Camp Stove", "CS-420", "Gear", "Aurora", 64, 52, 4,
     "Stable canister stove with a simmer ring.",
     "Boils half a litre in under three minutes and fine tunes from a "
     "rolling boil to a low simmer.", False, False, False),
    ("Trail Headlamp", "HL-430", "Gear", "Solstice", 42, None, 35,
     "450 lumen headlamp with a red mode.",
     "USB-C rechargeable, three brightness levels plus red night vision and "
     "a lock so it cannot fire in your pack.", False, False, True),
    ("Insulated Bottle", "IB-440", "Accessories", "Aurora", 32, None, 100,
     "750 ml double wall bottle, cold for 24 hours.",
     "Keeps drinks icy for a day and hot for eight hours. Fits most cup "
     "holders and pack side pockets.", False, True, False),
]

COUPONS = [
    dict(code="WELCOME10", type="percentage", value=Decimal("10"),
         description="10% off your first order", per_user_limit=1),
    dict(code="SAVE5", type="fixed", value=Decimal("5"),
         description="$5 off orders over $50",
         min_order_amount=Decimal("50")),
    dict(code="SUMMER20", type="percentage", value=Decimal("20"),
         description="20% off summer kit", usage_limit=100),
]

REVIEW_SEEDS = [
    ("Trailshell Jacket", "mia@example.com", 5, "Worth every penny",
     "Wore it through two days of rain and stayed dry. The pit zips are the "
     "real deal.", "approved"),
    ("Trailshell Jacket", "jordan@example.com", 4, "Great, runs a touch slim",
     "Solid build. Size up if you layer a lot underneath.", "approved"),
    ("Aurora 2P Tent", "sam@example.com", 5, "Pitches in five minutes",
     "Stood up to a windy night with no drama.", "approved"),
    ("Ridgeline Boot", "mia@example.com", 5, "No break-in needed",
     "Comfortable straight out of the box on a 14 km hike.", "approved"),
    ("Meridian Daypack", "jordan@example.com", 4, "Loads of pockets",
     "Ventilated back panel really works on hot days.", "pending"),
    ("Camp Stove", "sam@example.com", 3, "Fine but noisy",
     "Boils fast. The flame adjustment could be finer.", "pending"),
    ("Solar Charger", "mia@example.com", 1, "Charging issues",
     "Would not hold a charge after a week.", "spam"),
]

ORDER_PLAN = [
    ("ORD-20260901-0001", "mia@example.com", "delivered", "stripe",
     [("Trailshell Jacket", 1), ("Trek Sock 3-Pack", 2)], 22, "SUMMER20"),
    ("ORD-20260905-0002", "jordan@example.com", "shipped", "cod",
     [("Meridian Daypack", 1)], 18, None),
    ("ORD-20260909-0003", "sam@example.com", "processing", "stripe",
     [("Aurora 2P Tent", 1), ("Camp Stove", 1)], 14, "WELCOME10"),
    ("ORD-20260913-0004", "mia@example.com", "confirmed", "cod",
     [("Ridgeline Boot", 1)], 9, None),
    ("ORD-20260917-0005", "jordan@example.com", "pending", "cod",
     [("Trail Headlamp", 2), ("Insulated Bottle", 1)], 4, None),
    ("ORD-20260919-0006", "sam@example.com", "delivered", "paypal",
     [("Summit Fleece", 1), ("Base Layer Crew", 1)], 25, "SAVE5"),
    ("ORD-20260922-0007", "mia@example.com", "cancelled", "cod",
     [("Rain Poncho", 1)], 12, None),
    ("ORD-20260924-0008", "jordan@example.com", "processing", "stripe",
     [("Trekking Poles", 1), ("Solar Charger", 1)], 5, "WELCOME10"),
]

CUSTOMER_ACCOUNTS = [
    ("mia@example.com", "Mia", "Alvarez"),
    ("jordan@example.com", "Jordan", "Blake"),
    ("sam@example.com", "Sam", "Kim"),
]

SUBSCRIBERS = [
    ("nora@example.com", True), ("liam@example.com", True),
    ("ava@example.com", True), ("noah@example.com", False),
    ("emma@example.com", True), ("owen@example.com", False),
]

STAFF_ACCOUNTS = [
    ("inventory@example.com", "Ingrid", "Ito", "Inventory Manager"),
    ("orders@example.com", "Omar", "Haddad", "Order Manager"),
    ("content@example.com", "Clara", "Nguyen", "Content Manager"),
    ("support@example.com", "Sam", "Rivera", "Support Agent"),
]

FONT_CANDIDATES_BOLD = [
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
]
FONT_CANDIDATES_REGULAR = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

BG = "#f4f4f5"
FRAME = "#e4e4e7"
MONOGRAM = "#d4d4d8"
INK = "#52525b"
MUTED = "#71717a"
FAINT = "#a1a1aa"


def _load_font(size, bold=True):
    from PIL import ImageFont

    for path in FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _draw_tracked(draw, cx, cy, text, font, fill, tracking=0):
    """Draw letter-spaced text centred horizontally on (cx, cy)."""
    widths = [draw.textlength(ch, font=font) for ch in text]
    total = sum(widths) + tracking * max(len(text) - 1, 0)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        draw.text((x, cy), ch, font=font, fill=fill, anchor="lm")
        x += w + tracking


def _product_image(sku, name, brand):
    from PIL import Image, ImageDraw

    size = 1200
    img = Image.new("RGB", (size, size), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([36, 36, size - 37, size - 37], outline=FRAME, width=3)

    monogram = sku.split("-")[0][:3].upper()
    mono_font = _load_font(330, bold=True)
    draw.text((size / 2, 540), monogram, font=mono_font, fill=MONOGRAM,
              anchor="mm")

    name_font = _load_font(44, bold=True)
    _draw_tracked(draw, size / 2, 1000, name.upper(), name_font, INK, tracking=6)
    meta_font = _load_font(27, bold=False)
    _draw_tracked(draw, size / 2, 1062, f"{brand} · {sku}", meta_font, FAINT,
                  tracking=3)
    return img


def _category_image(name):
    from PIL import Image, ImageDraw

    w, h = 1200, 900
    img = Image.new("RGB", (w, h), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([30, 30, w - 31, h - 31], outline=FRAME, width=3)

    font = _load_font(64, bold=True)
    _draw_tracked(draw, w / 2, h / 2, name.upper(), font, INK, tracking=10)
    rule_font = _load_font(24, bold=False)
    _draw_tracked(draw, w / 2, h / 2 + 74, "SHOP THE COLLECTION", rule_font,
                  FAINT, tracking=6)
    return img


def _png_bytes(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


class Command(BaseCommand):
    help = "Seed demo catalog, accounts, promos and orders for local use."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete existing demo data before seeding")
        parser.add_argument("--images", action="store_true",
                            help="(Re)generate placeholder product images")
        parser.add_argument("--admin-password", default="admin12345")

    def handle(self, *args, **options):
        if options["reset"]:
            self._reset()
        with transaction.atomic():
            admin = self._users(options["admin_password"])
            self._seed(force_images=options["images"])
        self.stdout.write(self.style.SUCCESS(
            f"Seeded demo data. Admin login: admin@example.com / "
            f"{options['admin_password']}"))
        self.stdout.write(f"Staff logins: {', '.join(e for e, *_ in STAFF_ACCOUNTS)}")
        self.stdout.write(f"Customers: {', '.join(e for e, *_ in CUSTOMER_ACCOUNTS)}")
        self.stdout.write(f"Superuser: {admin.email}")

    def _reset(self):
        Order.objects.all().delete()
        Review.objects.all().delete()
        Coupon.objects.all().delete()
        StockTransaction.objects.all().delete()
        Notification.objects.all().delete()
        NewsletterSubscriber.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Brand.objects.all().delete()
        ShippingMethod.objects.all().delete()
        Address.objects.all().delete()
        User.objects.all().delete()
        self.stdout.write("Removed existing demo data.")

    def _seed(self, force_images=False):
        self._shipping()
        categories = self._categories()
        brands = self._brands()
        products = self._products(categories, brands)
        self._images(products, categories, force=force_images)
        self._coupons()
        customers = self._customers()
        self._reviews(products, customers)
        self._orders(products, customers)
        self._subscribers()
        self._notifications()

    def _images(self, products, categories, force=False):
        """Attach monochrome placeholder images so the catalog never looks empty."""
        attached = 0
        for product in products.values():
            if product.main_image and not force:
                continue
            if force and product.main_image:
                product.main_image.delete(save=False)
            img = _product_image(product.sku, product.name,
                                 product.brand.name if product.brand else "")
            product.main_image.save(
                f"{product.sku.lower()}.png",
                ContentFile(_png_bytes(img)), save=True)
            attached += 1
        for category in categories.values():
            if category.image and not force:
                continue
            if force and category.image:
                category.image.delete(save=False)
            img = _category_image(category.name)
            category.image.save(
                f"{category.slug}.png",
                ContentFile(_png_bytes(img)), save=True)
            attached += 1
        if attached:
            self.stdout.write(f"Generated {attached} placeholder images.")

    def _shipping(self):
        for name, code, cost, days, free_over in [
            ("Standard shipping", "standard", Decimal("7.99"),
             "3-5 business days", Decimal("75")),
            ("Express shipping", "express", Decimal("14.99"),
             "1-2 business days", None),
            ("Store pickup", "pickup", Decimal("0.00"),
             "Ready in 2 hours", None),
        ]:
            ShippingMethod.objects.update_or_create(
                code=code,
                defaults={"name": name, "cost": cost, "estimated_days": days,
                          "free_over": free_over, "is_active": True},
            )

    def _categories(self):
        out = {}
        for name, description in CATEGORIES:
            obj, _ = Category.objects.get_or_create(
                name=name, defaults={"description": description,
                                     "is_featured": True})
            out[name] = obj
        for name, parent, description in SUBCATEGORIES:
            obj, _ = Category.objects.get_or_create(
                name=name, defaults={"parent": out[parent],
                                     "description": description})
            out[name] = obj
        return out

    def _brands(self):
        out = {}
        for name, description in BRANDS:
            obj, _ = Brand.objects.get_or_create(
                name=name, defaults={"description": description})
            out[name] = obj
        return out

    def _products(self, categories, brands):
        rng = random.Random(7)
        out = {}
        for i, (name, sku, cat, brand, price, sale, stock, short, full,
                featured, best, new) in enumerate(PRODUCTS):
            obj, created = Product.objects.get_or_create(
                sku=sku,
                defaults={
                    "name": name, "category": categories[cat],
                    "brand": brands[brand],
                    "price": Decimal(price),
                    "sale_price": Decimal(sale) if sale else None,
                    "cost_price": Decimal(price) * Decimal("0.55"),
                    "short_description": short, "full_description": full,
                    "stock_quantity": stock,
                    "min_stock_level": 5,
                    "status": Product.Status.ACTIVE,
                    "is_featured": featured, "is_best_seller": best,
                    "is_new_arrival": new,
                    "view_count": rng.randint(40, 1400),
                },
            )
            out[name] = obj
            if created:
                StockTransaction.objects.create(
                    product=obj, transaction_type="purchase",
                    quantity=stock, stock_after=stock,
                    note="Initial demo stock", created_by=None,
                )
        return out

    def _coupons(self):
        for data in COUPONS:
            Coupon.objects.update_or_create(
                code=data["code"], defaults={**data, "is_active": True,
                                             "valid_from": timezone.now() -
                                             timedelta(days=30)},
            )

    def _customers(self):
        out = {}
        for email, first, last in CUSTOMER_ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=email.split("@")[0], email=email,
                defaults={"first_name": first, "last_name": last,
                          "email_verified": True},
            )
            if created:
                user.set_password("customer12345")
                user.save()
            out[email] = user
        first = next(iter(out.values()))
        Address.objects.get_or_create(
            user=first, address_type="shipping",
            defaults={"full_name": f"{first.first_name} {first.last_name}",
                      "address_line1": "1420 Summit Ridge Rd",
                      "city": "Boulder", "state": "CO",
                      "country": "United States", "postal_code": "80301",
                      "is_default": True},
        )
        return out

    def _users(self, admin_password):
        admin, created = User.objects.get_or_create(
            username="admin", email="admin@example.com",
            defaults={"first_name": "Store", "last_name": "Admin",
                      "is_staff": True, "is_superuser": True,
                      "role": User.Role.ADMIN},
        )
        if created:
            admin.set_password(admin_password)
            admin.save()
        for email, first, last, group_name in STAFF_ACCOUNTS:
            user, created = User.objects.get_or_create(
                username=email.split("@")[0], email=email,
                defaults={"first_name": first, "last_name": last,
                          "is_staff": True, "role": User.Role.STAFF},
            )
            if created:
                user.set_password(admin_password)
                user.save()
            if group_name:
                from django.contrib.auth.models import Group

                group = Group.objects.filter(name=group_name).first()
                if group:
                    user.groups.add(group)
        return admin

    def _reviews(self, products, customers):
        for product_name, email, rating, title, body, status in REVIEW_SEEDS:
            Review.objects.update_or_create(
                product=products[product_name], user=customers[email],
                defaults={"rating": rating, "title": title, "body": body,
                          "status": status,
                          "is_verified_purchase": status == "approved"},
            )
            refresh_product_rating(products[product_name])

    def _orders(self, products, customers):
        rng = random.Random(21)
        now = timezone.now()
        for number, email, status, provider, lines, days_ago, coupon_code in ORDER_PLAN:
            if Order.objects.filter(order_number=number).exists():
                continue
            user = customers[email]
            coupon = None
            discount = Decimal("0")
            if coupon_code:
                coupon = Coupon.objects.filter(code=coupon_code).first()
            items = []
            subtotal = Decimal("0")
            for product_name, qty in lines:
                product = products[product_name]
                unit = product.sale_price or product.price
                line_total = unit * qty
                subtotal += line_total
                items.append((product, qty, unit, line_total))
            if coupon:
                if coupon.type == Coupon.Type.PERCENTAGE:
                    discount = (subtotal * coupon.value / 100).quantize(
                        Decimal("0.01"))
                else:
                    discount = min(coupon.value, subtotal)
                if coupon.max_discount:
                    discount = min(discount, coupon.max_discount)
            shipping = Decimal("0")
            total = subtotal - discount + shipping
            order = Order.objects.create(
                order_number=number, user=user, email=email,
                shipping_full_name=f"{user.first_name} {user.last_name}",
                shipping_address_line1="1420 Summit Ridge Rd",
                shipping_city="Boulder", shipping_state="CO",
                shipping_postal_code="80301", shipping_country="United States",
                shipping_method_name="Standard shipping",
                shipping_method_code="standard",
                shipping_method_price=shipping,
                payment_method=provider,
                payment_status=(
                    "paid" if status not in ("pending", "cancelled")
                    else "pending"),
                status=status, subtotal=subtotal, discount=discount,
                shipping_cost=shipping, total=total,
                coupon=coupon, coupon_code=coupon_code or "",
                notes="Seeded demo order",
            )
            for product, qty, unit, line_total in items:
                OrderItem.objects.create(
                    order=order, product=product, product_name=product.name,
                    product_slug=product.slug, product_sku=product.sku,
                    unit_price=unit, original_price=product.price,
                    quantity=qty, line_total=line_total,
                )
                product.sold_count += qty
                product.save(update_fields=["sold_count"])
            OrderStatusHistory.objects.create(
                order=order, from_status="", to_status=status,
                note="Seeded demo order", is_customer_visible=False,
            )
            if provider != "cod" and status not in ("pending", "cancelled"):
                Payment.objects.create(
                    order=order, provider=provider, status="paid",
                    amount=total, transaction_id=f"demo_{number.lower()}",
                    paid_at=now - timedelta(days=days_ago),
                )
            if coupon:
                coupon.used_count += 1
                coupon.save(update_fields=["used_count"])
            Order.objects.filter(pk=order.pk).update(
                created_at=now - timedelta(days=days_ago),
                updated_at=now - timedelta(days=days_ago),
            )

    def _subscribers(self):
        for email, active in SUBSCRIBERS:
            NewsletterSubscriber.objects.get_or_create(
                email=email, defaults={"is_active": active,
                                       "source": "footer form"},
            )

    def _notifications(self):
        admin = User.objects.filter(email="admin@example.com").first()
        if not admin:
            return
        for title, body, ntype in [
            ("New order ORD-20260924-0008", "Payment captured via Stripe.",
             "order"),
            ("Low stock: Camp Sandal", "2 units left, reorder soon.",
             "stock"),
            ("3 reviews awaiting moderation", "Pending reviews need a decision.",
             "review"),
        ]:
            Notification.objects.get_or_create(
                user=admin, title=title,
                defaults={"body": body, "type": ntype},
            )

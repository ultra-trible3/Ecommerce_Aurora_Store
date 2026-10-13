"""Catalog management: products, categories and brands."""
from django.contrib import messages
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductImage,
    both_languages_q,
    product_name_q,
)
from apps.catalog import services as catalog_services
from apps.core.utils import paginate
from .decorators import management_required, permission_required
from .forms import BrandForm, CategoryForm, ColorFormSet, ProductForm


def _append_gallery(product, files):
    """Store uploaded album images, ordered after the existing ones."""
    if not files:
        return
    top = product.images.aggregate(top=Max("position"))["top"]
    position = (top or -1) + 1
    for f in files:
        ProductImage.objects.create(
            product=product, image=f, alt=product.name, position=position
        )
        position += 1


def _color_initial(product):
    """Existing colour variants, pre-filling the colour formset on edits."""
    if product is None:
        return []
    return [
        {
            "variant_id": variant.pk,
            "name": variant.name,
            "color_hex": variant.color_hex,
            "stock_quantity": variant.stock_quantity,
            "price": variant.price,
            "sku": variant.sku,
        }
        for variant in product.variants.all()
    ]


def _build_color_formset(request, product):
    """Build the colour formset, tolerating posts without the section.

    Older callers (and the API/tests) post the product form with no colour
    keys; in that case we skip colour handling entirely instead of failing on
    the missing management form.
    """
    if request.method == "POST":
        if "colors-TOTAL_FORMS" not in request.POST:
            return None
        return ColorFormSet(request.POST, prefix="colors")
    return ColorFormSet(prefix="colors", initial=_color_initial(product))


def _color_rows(formset):
    """Turn a bound colour formset into plain dictionaries for the service."""
    rows = []
    for form in formset.forms:
        data = getattr(form, "cleaned_data", None)
        if not data:
            continue
        rows.append(
            {
                "variant_id": data.get("variant_id"),
                "name": data.get("name"),
                "color_hex": data.get("color_hex"),
                "stock_quantity": data.get("stock_quantity"),
                "price": data.get("price"),
                "sku": data.get("sku"),
                "delete": data.get("DELETE"),
            }
        )
    return rows


# --------------------------------------------------------------------------
# Products
# --------------------------------------------------------------------------
@management_required
@permission_required("catalog.view_product")
def products(request):
    qs = Product.objects.select_related("category", "brand").order_by("-created_at")
    q = (request.GET.get("q") or "").strip()
    if q:
        qs = qs.filter(product_name_q(q))
    status = request.GET.get("status", "")
    if status:
        qs = qs.filter(status=status)
    category_id = request.GET.get("category", "")
    if category_id:
        qs = qs.filter(category_id=category_id)

    page_obj = paginate(request, qs, per_page=20)
    context = {
        "nav": "products",
        "page_obj": page_obj,
        "products": page_obj.object_list,
        "q": q,
        "status_filter": status,
        "status_choices": Product.Status.choices,
        "categories": Category.objects.filter(is_active=True),
        "total_count": qs.count(),
    }
    return render(request, "management/products/list.html", context)


@management_required
@permission_required("catalog.add_product")
@require_http_methods(["GET", "POST"])
def product_create(request):
    form = ProductForm(request.POST or None, request.FILES or None)
    color_formset = _build_color_formset(request, None)
    colors_valid = color_formset is None or color_formset.is_valid()
    if request.method == "POST" and form.is_valid() and colors_valid:
        product = form.save()
        _append_gallery(product, request.FILES.getlist("gallery_images"))
        if color_formset is not None:
            catalog_services.sync_product_colors(product, _color_rows(color_formset))
        messages.success(
            request,
            _("Product “%(name)s” created.") % {"name": product.name},
        )
        return redirect("dashboard:product_detail", pk=product.pk)
    if color_formset is None:
        color_formset = ColorFormSet(prefix="colors")
    return render(
        request, "management/products/form.html",
        {
            "nav": "products", "form": form, "mode": "create",
            "color_formset": color_formset,
        },
    )


@management_required
@permission_required("catalog.change_product")
@require_http_methods(["GET", "POST"])
def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    form = ProductForm(
        request.POST or None, request.FILES or None, instance=product
    )
    color_formset = _build_color_formset(request, product)
    colors_valid = color_formset is None or color_formset.is_valid()
    if request.method == "POST" and form.is_valid() and colors_valid:
        form.save()
        remove_ids = [
            i for i in request.POST.getlist("remove_gallery") if i.isdigit()
        ]
        if remove_ids:
            product.images.filter(pk__in=remove_ids).delete()
        _append_gallery(product, request.FILES.getlist("gallery_images"))
        if color_formset is not None:
            catalog_services.sync_product_colors(product, _color_rows(color_formset))
        messages.success(
            request,
            _("Product “%(name)s” updated.") % {"name": product.name},
        )
        return redirect("dashboard:product_detail", pk=product.pk)
    if color_formset is None:
        color_formset = ColorFormSet(
            prefix="colors", initial=_color_initial(product)
        )
    return render(
        request, "management/products/form.html",
        {
            "nav": "products", "form": form, "mode": "edit",
            "product": product, "color_formset": color_formset,
        },
    )


@management_required
@permission_required("catalog.change_product")
def product_detail(request, pk):
    product = get_object_or_404(
        Product.objects.select_related("category", "brand"), pk=pk
    )
    movements = product.stock_transactions.select_related(
        "created_by", "variant"
    )[:20]
    product_reviews = product.reviews.select_related("user").order_by(
        "-created_at"
    )[:10]
    context = {
        "nav": "products",
        "product": product,
        "movements": movements,
        "reviews": product_reviews,
        "variants": product.variants.all(),
    }
    return render(request, "management/products/detail.html", context)


@management_required
@permission_required("catalog.delete_product")
@require_POST
def product_archive(request, pk):
    product = get_object_or_404(Product, pk=pk)
    new_status = (
        Product.Status.ACTIVE
        if product.status != Product.Status.ACTIVE
        else Product.Status.ARCHIVED
    )
    Product.objects.filter(pk=pk).update(status=new_status)
    messages.success(
        request,
        _("“%(name)s” is now %(status)s.")
        % {
            "name": product.name,
            "status": Product.Status(new_status).label.lower(),
        },
    )
    return redirect("dashboard:products")


# --------------------------------------------------------------------------
# Categories
# --------------------------------------------------------------------------
@management_required
@permission_required("catalog.view_category")
def categories(request):
    qs = Category.objects.select_related("parent").order_by("position", "name")
    if request.GET.get("q"):
        qs = qs.filter(both_languages_q("name", request.GET["q"]))
    rows = [
        {
            "category": c,
            "product_count": c.products.filter(
                status=Product.Status.ACTIVE
            ).count(),
        }
        for c in qs
    ]
    return render(
        request,
        "management/categories/list.html",
        {"nav": "categories", "rows": rows},
    )


@management_required
@permission_required("catalog.add_category")
@require_http_methods(["GET", "POST"])
def category_edit(request, pk=None):
    category = (
        get_object_or_404(Category, pk=pk) if pk else None
    )
    form = CategoryForm(
        request.POST or None, request.FILES or None, instance=category
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(
            request,
            _("Category “%(name)s” %(action)s.")
            % {
                "name": obj.name,
                "action": _("updated") if pk else _("created"),
            },
        )
        return redirect("dashboard:categories")
    return render(
        request,
        "management/categories/form.html",
        {
            "nav": "categories",
            "form": form,
            "category": category,
            "mode": "edit" if pk else "create",
        },
    )


@management_required
@permission_required("catalog.delete_category")
@require_POST
def category_toggle(request, pk):
    category = get_object_or_404(Category, pk=pk)
    category.is_active = not category.is_active
    category.save(update_fields=["is_active"])
    messages.success(
        request,
        _("Category “%(name)s” %(action)s.")
        % {
            "name": category.name,
            "action": _("activated") if category.is_active else _("deactivated"),
        },
    )
    return redirect("dashboard:categories")


# --------------------------------------------------------------------------
# Brands
# --------------------------------------------------------------------------
@management_required
@permission_required("catalog.view_brand")
def brands(request):
    qs = Brand.objects.order_by("name")
    if request.GET.get("q"):
        qs = qs.filter(both_languages_q("name", request.GET["q"]))
    rows = [
        {"brand": b, "product_count": b.products.filter(
            status=Product.Status.ACTIVE
        ).count()}
        for b in qs
    ]
    return render(
        request, "management/brands/list.html", {"nav": "brands", "rows": rows}
    )


@management_required
@permission_required("catalog.add_brand")
@require_http_methods(["GET", "POST"])
def brand_edit(request, pk=None):
    brand = get_object_or_404(Brand, pk=pk) if pk else None
    form = BrandForm(
        request.POST or None, request.FILES or None, instance=brand
    )
    if request.method == "POST" and form.is_valid():
        obj = form.save()
        messages.success(
            request,
            _("Brand “%(name)s” %(action)s.")
            % {
                "name": obj.name,
                "action": _("updated") if pk else _("created"),
            },
        )
        return redirect("dashboard:brands")
    return render(
        request,
        "management/brands/form.html",
        {
            "nav": "brands",
            "form": form,
            "brand": brand,
            "mode": "edit" if pk else "create",
        },
    )


@management_required
@permission_required("catalog.delete_brand")
@require_POST
def brand_toggle(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    brand.is_active = not brand.is_active
    brand.save(update_fields=["is_active"])
    messages.success(
        request,
        _("Brand “%(name)s” %(action)s.")
        % {
            "name": brand.name,
            "action": _("activated") if brand.is_active else _("deactivated"),
        },
    )
    return redirect("dashboard:brands")

"""Branded PDF generation for the management Reports section.

Builds multipage A4 documents with ReportLab Platypus and native charts, so
the whole Reports area under ``/management/reports/`` can be downloaded as a
real PDF file.  The brand palette, language/font handling (Helvetica for
English, bundled Amiri for Arabic), page header/footer and table helpers are
shared with the order invoice PDF via ``apps/core/pdf_theme.py``, so every
generated document keeps the same wine/sand look and follows the active site
language.
"""
from __future__ import annotations

from django.utils.translation import gettext as _

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.legends import Legend
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.piecharts import Pie
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from apps.core.pdf_theme import (
    CONTENT_WIDTH,
    HALF_WIDTH,
    INK,
    MUTED2,
    PALETTE,
    SAND,
    SLATE,
    STEEL,
    TA_LEFT,
    TA_RIGHT,
    Theme,
    WHITE,
    WINE,
    _cell_style,
    _data_table,
    _empty_row,
    _esc,
    _money,
    _section,
    _side_by_side,
    build_pdf,
)

from . import services


def _kpi_cards(theme, items):
    """``items`` is a list of (label, value, bg, label_color, value_color)."""
    items = list(items)
    if theme.rtl:
        items = list(reversed(items))
    gap = 4 * mm
    card_w = (CONTENT_WIDTH - gap * (len(items) - 1)) / len(items)
    cards = []
    for label, value, bg, label_color, value_color in items:
        card = Table(
            [[Paragraph(_esc(theme.tu(label)), _cell_style(theme, TA_LEFT, label_color, 6.5, bold=True))],
             [Paragraph(_esc(theme.shape(value)), _cell_style(theme, TA_LEFT, value_color, 14, bold=True))]],
            colWidths=[card_w],
        )
        card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("ROUNDEDCORNERS", [7, 7, 7, 7]),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (0, 0), 8),
            ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ("TOPPADDING", (0, 1), (-1, 1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ]))
        cards.append(card)

    row = Table([cards], colWidths=[card_w + gap] * (len(items) - 1) + [card_w],
                hAlign="RIGHT" if theme.rtl else "LEFT")
    row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row


def _chart_or_empty(theme, drawing_fn, labels):
    if not labels:
        return Paragraph(_esc(theme.t(_("No chart data for this period."))),
                         _cell_style(theme, TA_LEFT, MUTED2, 8))
    return drawing_fn()


# --------------------------------------------------------------------------
# Charts (native ReportLab graphics, no extra dependency)
# --------------------------------------------------------------------------
def _line_chart(theme, labels, values):
    width, height = CONTENT_WIDTH, 52 * mm
    drawing = Drawing(width, height)
    chart = HorizontalLineChart()
    chart.x = 40
    chart.y = 28
    chart.width = width - 52
    chart.height = height - 46
    chart.data = [[float(v) for v in (values or [0])]]
    chart.joinedLines = 1
    chart.categoryAxis.categoryNames = [theme.shape(x) for x in (labels or [""])]
    chart.categoryAxis.labels.fontName = theme.regular
    chart.categoryAxis.labels.fontSize = 5
    chart.categoryAxis.labels.angle = 40
    chart.categoryAxis.labels.dy = -6
    chart.valueAxis.labels.fontName = theme.regular
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.valueMin = 0
    chart.lines[0].strokeColor = WINE
    chart.lines[0].strokeWidth = 1.6
    drawing.add(chart)
    return drawing


def _bar_chart(theme, labels, values):
    width, height = CONTENT_WIDTH, 48 * mm
    drawing = Drawing(width, height)
    chart = VerticalBarChart()
    chart.x = 40
    chart.y = 28
    chart.width = width - 52
    chart.height = height - 46
    chart.data = [[float(v) for v in (values or [0])]]
    chart.categoryAxis.categoryNames = [theme.shape(x) for x in (labels or [""])]
    chart.categoryAxis.labels.fontName = theme.regular
    chart.categoryAxis.labels.fontSize = 4.5
    chart.valueAxis.labels.fontName = theme.regular
    chart.valueAxis.labels.fontSize = 6
    chart.valueAxis.valueMin = 0
    chart.bars[0].fillColor = WINE
    chart.barSpacing = 0.5
    drawing.add(chart)
    return drawing


def _pie_chart(theme, labels, values, palette=None):
    palette = palette or PALETTE
    width, height = HALF_WIDTH, 62 * mm
    drawing = Drawing(width, height)
    diameter = height - 10

    pie = Pie()
    pie.x = 4
    pie.y = (height - diameter) / 2
    pie.width = diameter
    pie.height = diameter
    pie.data = [float(v) for v in values] or [1.0]
    pie.labels = None
    pie.startAngle = 90
    pie.slices.strokeColor = WHITE
    pie.slices.strokeWidth = 1.5
    for i in range(len(pie.data)):
        pie.slices[i].fillColor = colors.HexColor(palette[i % len(palette)])
    drawing.add(pie)

    legend = Legend()
    legend.x = diameter + 14
    legend.y = height - 14
    legend.fontName = theme.regular
    legend.fontSize = 7
    legend.dxTextSpace = 5
    legend.alignment = "right"
    legend.columnMaximum = 12
    legend.colorNamePairs = [
        (pie.slices[i].fillColor, theme.shape(str(labels[i]))[:28])
        for i in range(len(pie.data))
    ] if labels else []
    drawing.add(legend)
    return drawing


# --------------------------------------------------------------------------
# Document assembly
# --------------------------------------------------------------------------
def _build(theme, title, date_from, date_to, story):
    return build_pdf(
        theme,
        theme.t(title),
        theme.shape(f"{date_from:%b %d, %Y} \u2014 {date_to:%b %d, %Y}"),
        story,
    )


# --------------------------------------------------------------------------
# Report builders — each returns (buffer, date_from, date_to)
# --------------------------------------------------------------------------
def render_overview_pdf(request):
    theme = Theme()
    sales = services.sales_overview(request)
    categories = services.sales_by_category(request)
    customers = services.customer_analytics(request)
    ds, de = sales["date_from"], sales["date_to"]
    kpis = sales["kpis"]

    story = [_kpi_cards(theme, [
        (_("Total Revenue"), _money(kpis["total_revenue"]), WINE, colors.HexColor("#f3d9dc"), WHITE),
        (_("Total Orders"), kpis["total_orders"], STEEL, colors.HexColor("#e6eef4"), WHITE),
        (_("Conversion Rate"), f"{kpis['conversion_rate']}%", SAND, SLATE, INK),
        (_("New Customers"), customers["new_customers"], colors.HexColor("#1f2937"), colors.HexColor("#cbd5e1"), WHITE),
    ]), Spacer(1, 7 * mm)]

    story += _section(theme, _("Daily Revenue"), [
        _chart_or_empty(
            theme,
            lambda: _line_chart(theme, [r["label"] for r in sales["daily_series"]],
                                [r["revenue"] for r in sales["daily_series"]]),
            sales["daily_series"],
        ),
    ])

    top_rows = [
        [p["items__product_name"], p["items__product_sku"],
         p["units_sold"], _money(p["revenue"])]
        for p in sales["top_products"]
    ] or _empty_row(theme, [_("Product"), _("SKU"), _("Units"), _("Revenue")])
    story += _section(theme, _("Top Selling Products"), [_data_table(
        theme, [_("Product"), _("SKU"), _("Units"), _("Revenue")], top_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT],
    )])

    category_rows = [
        [c["items__product__category__name"] or "\u2014", _money(c["revenue"]),
         c["units"], c["orders"]]
        for c in categories["by_category"]
    ] or _empty_row(theme, [_("Category"), _("Revenue"), _("Units"), _("Orders")])
    story += _section(theme, _("Sales by Category"), [_data_table(
        theme, [_("Category"), _("Revenue"), _("Units"), _("Orders")], category_rows,
        aligns=[TA_LEFT, TA_RIGHT, TA_RIGHT, TA_RIGHT],
    )])

    customer_rows = [
        [f"{c['user__first_name']} {c['user__last_name']}".strip() or "\u2014",
         c["user__email"], c["order_count"], _money(c["total_spent"])]
        for c in customers["top_customers"]
    ] or _empty_row(theme, [_("Customer"), _("Email"), _("Orders"), _("Spent")])
    story += _section(theme, _("Top Customers"), [_data_table(
        theme, [_("Customer"), _("Email"), _("Orders"), _("Spent")], customer_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT],
    )])

    return _build(theme, _("Reports & Analytics"), ds, de, story), ds, de


def render_sales_pdf(request):
    theme = Theme()
    sales = services.sales_overview(request)
    ds, de = sales["date_from"], sales["date_to"]
    kpis = sales["kpis"]

    story = [_kpi_cards(theme, [
        (_("Total Revenue"), _money(kpis["total_revenue"]), WINE, colors.HexColor("#f3d9dc"), WHITE),
        (_("Total Orders"), kpis["total_orders"], STEEL, colors.HexColor("#e6eef4"), WHITE),
        (_("Avg. Order Value"), _money(kpis["avg_order_value"]), SAND, SLATE, INK),
        (_("Conversion Rate"), f"{kpis['conversion_rate']}%", colors.HexColor("#1f2937"), colors.HexColor("#cbd5e1"), WHITE),
    ]), Spacer(1, 7 * mm)]

    story += _section(theme, _("Daily Revenue"), [
        _chart_or_empty(
            theme,
            lambda: _line_chart(theme, [r["label"] for r in sales["daily_series"]],
                                [r["revenue"] for r in sales["daily_series"]]),
            sales["daily_series"],
        ),
    ])

    payments = sales["payment_breakdown"]
    shipping = sales["shipping_breakdown"]
    left = _chart_or_empty(
        theme,
        lambda: _pie_chart(
            theme,
            [str(p["payment_method"]).upper() for p in payments],
            [p["revenue"] or 0 for p in payments],
            ["#5b7f96", "#790d16", "#3b82f6", "#e5d3af"],
        ),
        payments,
    )
    right = _chart_or_empty(
        theme,
        lambda: _pie_chart(
            theme,
            [s["shipping_method_name"] or "UNKNOWN" for s in shipping],
            [s["revenue"] or 0 for s in shipping],
        ),
        shipping,
    )
    story += _section(theme, _("Payment & shipping breakdown"), [_side_by_side(theme, left, right)])

    story += _section(theme, _("Orders by Hour"), [
        _chart_or_empty(
            theme,
            lambda: _bar_chart(theme, [h["hour"].strftime("%H:00") for h in sales["hourly_orders"]],
                               [h["count"] for h in sales["hourly_orders"]]),
            sales["hourly_orders"],
        ),
    ])

    top_rows = [
        [p["items__product_name"], p["items__product_sku"],
         p["units_sold"], _money(p["revenue"])]
        for p in sales["top_products"]
    ] or _empty_row(theme, [_("Product"), _("SKU"), _("Units"), _("Revenue")])
    story += _section(theme, _("Top Selling Products"), [_data_table(
        theme, [_("Product"), _("SKU"), _("Units"), _("Revenue")], top_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT],
    )])

    return _build(theme, _("Sales Report"), ds, de, story), ds, de


def render_categories_pdf(request):
    theme = Theme()
    categories = services.sales_by_category(request)
    ds, de = categories["date_from"], categories["date_to"]
    by_category = categories["by_category"]

    story = []
    story += _section(theme, _("Revenue by Category"), [
        _chart_or_empty(
            theme,
            lambda: _pie_chart(
                theme,
                [c["items__product__category__name"] or "\u2014" for c in by_category],
                [c["revenue"] or 0 for c in by_category],
            ),
            by_category,
        ),
    ])

    category_rows = [
        [c["items__product__category__name"] or "\u2014",
         c["items__product__category__slug"] or "",
         _money(c["revenue"]), c["units"], c["orders"]]
        for c in by_category
    ] or _empty_row(theme, [_("Category"), _("Slug"), _("Revenue"), _("Units"), _("Orders")])
    story += _section(theme, _("Category Breakdown"), [_data_table(
        theme, [_("Category"), _("Slug"), _("Revenue"), _("Units"), _("Orders")], category_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT, TA_RIGHT],
    )])

    return _build(theme, _("Sales by Category"), ds, de, story), ds, de


def render_customers_pdf(request):
    theme = Theme()
    customers = services.customer_analytics(request)
    ds, de = customers["date_from"], customers["date_to"]

    story = [_kpi_cards(theme, [
        (_("Unique Buyers"), customers["total_ordering_customers"], colors.HexColor("#1f2937"), colors.HexColor("#cbd5e1"), WHITE),
        (_("New Customers"), customers["new_customers"], WINE, colors.HexColor("#f3d9dc"), WHITE),
        (_("Repeat Rate"), f"{customers['repeat_rate']}%", STEEL, colors.HexColor("#e6eef4"), WHITE),
        (_("Avg. Customer Value"), _money(customers["customer_lifetime_value"]), SAND, SLATE, INK),
    ]), Spacer(1, 7 * mm)]

    customer_rows = [
        [f"{c['user__first_name']} {c['user__last_name']}".strip() or "\u2014",
         c["user__email"], c["order_count"],
         _money(c["total_spent"]), _money(c["avg_order"])]
        for c in customers["top_customers"]
    ] or _empty_row(theme, [_("Customer"), _("Email"), _("Orders"), _("Total Spent"), _("Avg. Order")])
    story += _section(theme, _("Top Customers by Revenue"), [_data_table(
        theme, [_("Customer"), _("Email"), _("Orders"), _("Total Spent"), _("Avg. Order")], customer_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT, TA_RIGHT],
    )])

    return _build(theme, _("Customer Analytics"), ds, de, story), ds, de


def render_products_pdf(request):
    theme = Theme()
    products = services.product_performance(request)
    ds, de = products["date_from"], products["date_to"]

    story = []

    top_rows = [
        [p["items__product_name"], p["items__product_sku"], p["units_sold"],
         _money(p["revenue"]), p["orders"], _money(p["avg_price"])]
        for p in products["top_selling"]
    ] or _empty_row(theme, [_("Product"), _("SKU"), _("Units"), _("Revenue"), _("Orders"), _("Avg. Price")])
    story += _section(theme, _("Top Selling Products"), [_data_table(
        theme, [_("Product"), _("SKU"), _("Units"), _("Revenue"), _("Orders"), _("Avg. Price")], top_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT, TA_RIGHT, TA_RIGHT, TA_RIGHT],
    )])

    low_rows = [
        [p["name"], p["sku"], p["stock_quantity"]]
        for p in products["low_stock"]
    ] or _empty_row(theme, [_("Product"), _("SKU"), _("Stock")])
    story += _section(theme, _("Low Stock Alerts"), [_data_table(
        theme, [_("Product"), _("SKU"), _("Stock")], low_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT],
    )])

    no_sales_rows = [
        [p["name"], p["sku"], p["stock_quantity"]]
        for p in products["no_sales"]
    ] or _empty_row(theme, [_("Product"), _("SKU"), _("Stock")])
    story += _section(theme, _("No Sales in Period"), [_data_table(
        theme, [_("Product"), _("SKU"), _("Stock")], no_sales_rows,
        aligns=[TA_LEFT, TA_LEFT, TA_RIGHT],
    )])

    return _build(theme, _("Product Performance"), ds, de, story), ds, de

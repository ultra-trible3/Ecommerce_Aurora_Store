"""Branded invoice PDF generation (reportlab).

Shares the wine/sand theme with the management Reports PDFs via
``apps/core/pdf_theme.py`` so the downloaded invoice uses the same logo header
band, sand table headers and wine totals, and follows the active site language
(Helvetica for English, bundled Amiri for Arabic with text shaping + bidi).
"""
from __future__ import annotations

from django.conf import settings
from django.utils.translation import gettext as _

from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

from apps.core.pdf_theme import (
    BORDER,
    CONTENT_WIDTH,
    HALF_WIDTH,
    HEADER_BG,
    INK,
    MUTED,
    MUTED2,
    ROW_LINE,
    SAND,
    SLATE,
    TA_LEFT,
    TA_RIGHT,
    Theme,
    WINE,
    _cell_style,
    _esc,
    _money,
    _side_by_side,
    build_pdf,
    mm,
)


def _address_block(theme, title, full_name, address_line, email=None, phone=None):
    """A sand-tinted address card, mirroring the on-screen invoice."""
    rows = [[Paragraph(_esc(theme.tu(title)), _cell_style(theme, TA_LEFT, MUTED, 6.5, bold=True))]]
    if full_name:
        rows.append([Paragraph(_esc(theme.shape(full_name)), _cell_style(theme, TA_LEFT, INK, 9, bold=True))])
    if address_line:
        rows.append([Paragraph(_esc(theme.shape(address_line)), _cell_style(theme, TA_LEFT, INK, 8.5))])
    if email:
        rows.append([Paragraph(_esc(theme.shape(email)), _cell_style(theme, TA_LEFT, MUTED2, 8))])
    if phone:
        rows.append([Paragraph(_esc(theme.shape(phone)), _cell_style(theme, TA_LEFT, MUTED2, 8))])

    block = Table(rows, colWidths=[HALF_WIDTH])
    block.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
        ("ROUNDEDCORNERS", [9, 9, 9, 9]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
    ]))
    return block


def _items_table(theme, order):
    widths = [CONTENT_WIDTH * 0.50, CONTENT_WIDTH * 0.12,
              CONTENT_WIDTH * 0.19, CONTENT_WIDTH * 0.19]

    header = [
        Paragraph(_esc(theme.t(_("Item"))), _cell_style(theme, TA_LEFT, SLATE, 7.5, bold=True)),
        Paragraph(_esc(theme.t(_("Qty"))), _cell_style(theme, TA_CENTER, SLATE, 7.5, bold=True)),
        Paragraph(_esc(theme.t(_("Unit"))), _cell_style(theme, TA_RIGHT, SLATE, 7.5, bold=True)),
        Paragraph(_esc(theme.t(_("Amount"))), _cell_style(theme, TA_RIGHT, SLATE, 7.5, bold=True)),
    ]

    data = [header]
    for item in order.items.all():
        sku_text = theme.shape(_("SKU %(sku)s") % {"sku": item.product_sku})
        name_cell = Paragraph(
            f'{_esc(theme.shape(item.display_name))}<br/>'
            f'<font size="7" color="#96877e">{_esc(sku_text)}</font>',
            _cell_style(theme, TA_LEFT, INK, 8.5),
        )
        cells = [
            name_cell,
            Paragraph(_esc(str(item.quantity)), _cell_style(theme, TA_CENTER, WINE, 8.5, bold=True)),
            Paragraph(_esc(theme.shape(_money(item.unit_price))), _cell_style(theme, TA_RIGHT, INK, 8.5)),
            Paragraph(_esc(theme.shape(_money(item.line_total))), _cell_style(theme, TA_RIGHT, INK, 8.5, bold=True)),
        ]
        if theme.rtl:
            cells = list(reversed(cells))
        data.append(cells)

    if theme.rtl:
        widths = list(reversed(widths))

    table = Table(data, colWidths=widths, repeatRows=1, hAlign="RIGHT" if theme.rtl else "LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("LINEBELOW", (0, 0), (-1, 0), 1, BORDER),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, ROW_LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return table


def _totals_table(theme, order):
    width = CONTENT_WIDTH * 0.44
    entries = [(_("Subtotal"), _money(order.subtotal))]
    if order.discount:
        entries.append((_("Discount"), f"\u2212{_money(order.discount)}"))
    entries.append((_("Shipping"), _money(order.shipping_cost)))
    entries.append((_("Tax"), _money(order.tax)))

    data = [
        [Paragraph(_esc(theme.t(label)), _cell_style(theme, TA_LEFT, MUTED2, 8.5)),
         Paragraph(_esc(theme.shape(value)), _cell_style(theme, TA_RIGHT, INK, 8.5, bold=True))]
        for label, value in entries
    ]
    data.append([
        Paragraph(_esc(theme.t(_("Total due"))), _cell_style(theme, TA_LEFT, WINE, 10.5, bold=True)),
        Paragraph(_esc(theme.shape(_money(order.total))), _cell_style(theme, TA_RIGHT, WINE, 10.5, bold=True)),
    ])

    widths = [width * 0.58, width * 0.42]
    if theme.rtl:
        data = [list(reversed(row)) for row in data]
        widths = list(reversed(widths))

    table = Table(data, colWidths=widths, hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LINEABOVE", (0, -1), (-1, -1), 1.5, SAND),
    ]))
    return table


def render_invoice_pdf(order):
    """Render a branded A4 invoice PDF for ``order`` and return a BytesIO buffer."""
    theme = Theme()
    title = f'{theme.t(_("Invoice")).upper()} {theme.shape(order.order_number)}'
    subtitle = theme.shape(_("Issued %(issued)s") % {"issued": order.created_at.strftime("%b %d, %Y")})

    billed = _address_block(
        theme, _("Billed to"),
        order.billing_full_name or order.shipping_full_name,
        order.billing_address_line,
        None, order.billing_phone,
    )
    shipped = _address_block(
        theme, _("Ship to"), order.shipping_full_name, order.shipping_address_line,
        order.email, order.shipping_phone,
    )

    note = _("Thank you for your business. Questions about this invoice? Contact %(email)s.") % {
        "email": settings.SUPPORT_EMAIL,
    }

    story = [
        _side_by_side(theme, billed, shipped),
        Spacer(1, 7 * mm),
        _items_table(theme, order),
        Spacer(1, 6 * mm),
        _totals_table(theme, order),
        Spacer(1, 10 * mm),
        Paragraph(_esc(theme.shape(note)), _cell_style(theme, TA_CENTER, MUTED2, 8.5)),
    ]

    return build_pdf(theme, title, subtitle, story, doc_title=f"INVOICE {order.order_number}")

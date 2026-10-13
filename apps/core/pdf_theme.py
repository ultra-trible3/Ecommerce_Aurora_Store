"""Shared ReportLab branding primitives for generated PDFs.

Single source of truth for the wine/sand brand palette, the language-aware
font/theme logic (Helvetica for English, bundled Amiri for Arabic with text
reshaping + bidi), the branded page header/footer and the table helpers used
by the generated documents:

* management Reports PDFs (``apps/dashboard/report_pdf.py``)
* order invoice PDF (``apps/orders/invoice.py``)

Every generated document therefore shares the same branded look and follows
the active site language.
"""
from __future__ import annotations

import io
import re

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils import translation
from django.utils.translation import gettext as _

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from apps.core.utils import money

# --------------------------------------------------------------------------
# Brand palette (kept in sync with the management invoice template)
# --------------------------------------------------------------------------
WINE = colors.HexColor("#790d16")
WINE_DARK = colors.HexColor("#5c0a11")
SAND = colors.HexColor("#e5d3af")
STEEL = colors.HexColor("#5b7f96")
STEEL_LIGHT = colors.HexColor("#aec4d4")
INK = colors.HexColor("#33141b")
SLATE = colors.HexColor("#4a3c36")
MUTED = colors.HexColor("#96877e")
MUTED2 = colors.HexColor("#7a6a62")
HEADER_BG = colors.HexColor("#f5efe1")
BORDER = colors.HexColor("#e7ddcb")
ROW_LINE = colors.HexColor("#f0ebe0")
WHITE = colors.white

PALETTE = [
    "#790d16", "#a3252f", "#5b7f96", "#aec4d4",
    "#10b981", "#f59e0b", "#3b82f6", "#ef4444",
    "#8b5cf6", "#ec4899", "#14b8a6", "#eab308",
]

# --------------------------------------------------------------------------
# Page geometry
# --------------------------------------------------------------------------
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 16 * mm
TOP_MARGIN = 42 * mm
BOTTOM_MARGIN = 20 * mm
CONTENT_WIDTH = PAGE_WIDTH - (2 * MARGIN)
BAND_HEIGHT = 28 * mm
HALF_WIDTH = (CONTENT_WIDTH - 6 * mm) / 2

# --------------------------------------------------------------------------
# Language, fonts and text direction
# --------------------------------------------------------------------------
ARABIC_REGULAR = "Amiri"
ARABIC_BOLD = "Amiri-Bold"
_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]")
_FONTS_REGISTERED = False


def _arabic_font_path(filename):
    """Resolve a bundled font both in dev (static/) and via staticfiles."""
    found = finders.find(f"fonts/arabic/{filename}")
    if found:
        return found
    return str(settings.BASE_DIR / "static" / "fonts" / "arabic" / filename)


def _register_arabic_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont(ARABIC_REGULAR, _arabic_font_path("Amiri-Regular.ttf")))
    pdfmetrics.registerFont(TTFont(ARABIC_BOLD, _arabic_font_path("Amiri-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        ARABIC_REGULAR,
        normal=ARABIC_REGULAR,
        bold=ARABIC_BOLD,
        italic=ARABIC_REGULAR,
        boldItalic=ARABIC_BOLD,
    )
    _FONTS_REGISTERED = True


def _shape_arabic(text):
    """Reshape Arabic and apply the bidi algorithm for ReportLab.

    ReportLab does not perform complex-text shaping, so Arabic letters would
    otherwise render isolated and in logical (reversed) order.  Text without
    Arabic characters is returned untouched, which keeps numbers and Latin
    runs stable.
    """
    if not text:
        return str(text)
    text = str(text)
    if not _ARABIC_RE.search(text):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # pragma: no cover - shaping is best effort
        return text


def _is_rtl():
    return (translation.get_language() or "en").lower().startswith("ar")


class Theme:
    """Per-render language, font and direction settings."""

    def __init__(self):
        self.rtl = _is_rtl()
        self.regular = "Helvetica"
        self.bold = "Helvetica-Bold"
        if self.rtl:
            try:
                _register_arabic_fonts()
                self.regular = ARABIC_REGULAR
                self.bold = ARABIC_BOLD
            except Exception:  # pragma: no cover - never fail the report
                self.rtl = False

    def shape(self, text):
        """Prepare *text* for the active direction without translating it."""
        if text is None:
            return ""
        return _shape_arabic(text) if self.rtl else str(text)

    def t(self, msgid):
        """Translate *msgid* for the active language and shape it."""
        return self.shape(_(msgid))

    def tu(self, msgid):
        """Like :meth:`t` but upper-cased (for small heading labels)."""
        return self.shape(_(msgid).upper())

    def align(self, alignment):
        """Mirror left/right alignment when the document is RTL."""
        if not self.rtl:
            return alignment
        if alignment == TA_LEFT:
            return TA_RIGHT
        if alignment == TA_RIGHT:
            return TA_LEFT
        return alignment


def _cell_style(theme, align=TA_LEFT, color=INK, size=8.5, bold=False):
    return ParagraphStyle(
        f"cell-{theme.rtl}-{align}-{size}-{bold}-{color}",
        fontName=theme.bold if bold else theme.regular,
        fontSize=size,
        leading=size + 2,
        textColor=color,
        alignment=theme.align(align),
    )


def _section_style(theme):
    return ParagraphStyle(
        f"section-{theme.rtl}", fontName=theme.bold, fontSize=8, leading=10,
        textColor=MUTED, spaceAfter=3, alignment=theme.align(TA_LEFT),
    )


def _esc(value):
    from xml.sax.saxutils import escape

    return escape(str(value))


def _money(value):
    """Same formatting as the ``currency`` template filter."""
    return f"{settings.CURRENCY_SYMBOL}{money(value):,.2f}"


# --------------------------------------------------------------------------
# Header / footer drawn on the canvas
# --------------------------------------------------------------------------
def _lerp(a, b, t):
    return colors.Color(
        a.red + (b.red - a.red) * t,
        a.green + (b.green - a.green) * t,
        a.blue + (b.blue - a.blue) * t,
    )


def _gradient_rect(canvas, x, y, w, h, start, end, steps=90):
    for i in range(steps):
        t = i / (steps - 1)
        canvas.setFillColor(_lerp(start, end, t))
        canvas.rect(x, y + h * i / steps, w, (h / steps) + 0.6, fill=1, stroke=0)


def _draw_header(canvas, doc, title, date_label):
    theme = doc._theme
    band_bottom = PAGE_HEIGHT - BAND_HEIGHT
    _gradient_rect(canvas, 0, band_bottom, PAGE_WIDTH, BAND_HEIGHT, WINE, WINE_DARK)

    # Decorative translucent circle, echoing the invoice header.
    canvas.saveState()
    canvas.setFillAlpha(0.12)
    canvas.setFillColor(SAND)
    canvas.circle(PAGE_WIDTH - 14 * mm, PAGE_HEIGHT - 6 * mm, 30 * mm, fill=1, stroke=0)
    canvas.restoreState()

    # Left: logo + store name.
    x_text = MARGIN
    logo_path = finders.find("images/logo.png")
    if logo_path:
        try:
            image = ImageReader(logo_path)
            iw, ih = image.getSize()
            logo_h = 9 * mm
            logo_w = logo_h * iw / ih
            canvas.drawImage(
                logo_path, MARGIN, band_bottom + (BAND_HEIGHT - logo_h) / 2,
                width=logo_w, height=logo_h, mask="auto",
            )
            x_text = MARGIN + logo_w + 3.5 * mm
        except Exception:  # pragma: no cover - never fail the whole report on a logo
            x_text = MARGIN

    canvas.setFillColor(WHITE)
    canvas.setFont(theme.bold, 13)
    canvas.drawString(x_text, band_bottom + BAND_HEIGHT / 2 - 4, theme.shape(settings.SITE_NAME))

    # Right: document title + subtitle (date / issued label).
    canvas.setFont(theme.bold, 13)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, band_bottom + BAND_HEIGHT / 2 + 3, title)
    canvas.setFillColor(colors.HexColor("#f3d9dc"))
    canvas.setFont(theme.regular, 8)
    canvas.drawRightString(PAGE_WIDTH - MARGIN, band_bottom + BAND_HEIGHT / 2 - 8, date_label)


def _draw_footer(canvas, doc):
    theme = doc._theme
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(MARGIN, 14 * mm, PAGE_WIDTH - MARGIN, 14 * mm)
    canvas.setFont(theme.regular, 7.5)
    canvas.setFillColor(MUTED2)

    credit = f'{_("Generated by")} {settings.SITE_NAME} \u00b7 {settings.SUPPORT_EMAIL}'
    page_label = f'{_("Page")} {doc.page}'
    canvas.drawString(MARGIN, 10 * mm, theme.shape(credit))
    canvas.drawRightString(PAGE_WIDTH - MARGIN, 10 * mm, theme.shape(page_label))


def _on_page(canvas, doc):
    _draw_header(canvas, doc, doc._report_title, doc._report_date_label)
    _draw_footer(canvas, doc)


# --------------------------------------------------------------------------
# Flowable helpers
# --------------------------------------------------------------------------
def _section(theme, title, flowables):
    return [
        Paragraph(_esc(theme.tu(title)), _section_style(theme)),
        Spacer(1, 1.5 * mm),
        *flowables,
        Spacer(1, 7 * mm),
    ]


def _data_table(theme, headers, rows, aligns=None, widths=None):
    n = len(headers)
    aligns = list(aligns or ([TA_LEFT] * n))
    widths = list(widths or ([CONTENT_WIDTH / n] * n))
    headers = list(headers)
    rows = [list(row) for row in rows]

    # Right-to-left documents mirror the column order so the first column
    # renders on the right, matching the on-screen layout.
    if theme.rtl:
        headers = list(reversed(headers))
        rows = [list(reversed(row)) for row in rows]
        aligns = list(reversed(aligns))
        widths = list(reversed(widths))

    data = [[Paragraph(_esc(theme.t(h)), _cell_style(theme, TA_LEFT, SLATE, 7.5, bold=True)) for h in headers]]
    for row in rows:
        data.append([
            Paragraph(_esc(theme.shape(cell)), _cell_style(theme, aligns[i], INK, 8.5))
            for i, cell in enumerate(row)
        ])

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


def _empty_row(theme, headers):
    return [[theme.t(_("No data available for this period."))] + [""] * (len(headers) - 1)]


def _side_by_side(theme, left, right):
    if theme.rtl:
        left, right = right, left
    table = Table([[left, right]], colWidths=[HALF_WIDTH, HALF_WIDTH],
                  hAlign="RIGHT" if theme.rtl else "LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return table


def build_pdf(theme, title, subtitle, story, doc_title=None, doc_author=None):
    """Assemble an A4 branded PDF with the header band and footer on every page."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGIN,
        rightMargin=MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"{doc_title or subtitle} \u00b7 {settings.SITE_NAME}",
        author=doc_author or settings.SITE_NAME,
    )
    doc._theme = theme
    doc._report_title = title
    doc._report_date_label = subtitle
    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    buffer.seek(0)
    return buffer
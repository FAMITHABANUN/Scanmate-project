"""
Renders a scan's extracted text as a downloadable branded PNG image or a
multi-page PDF - useful for sharing or printing without needing the app.

Multilingual note: English/Latin text uses the fonts below directly. For
other scripts (Tamil, Hindi and other Indic languages, Chinese, etc.) we
look for a matching system font so the real characters render instead of
boxes/tofu. On Windows this "just works" using fonts Windows already ships
(Nirmala UI for Indic scripts, DengXian for Chinese). On Linux/Docker,
install the `fonts-noto` and `fonts-noto-cjk` packages (see Dockerfile) to
get the same coverage - or drop your own .ttf/.ttc files into
static/fonts/, which is checked first. Scripts with no matching font found
fall back to a short note rather than breaking the download.
"""
import io
import os
import textwrap
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont
from fpdf import FPDF
from fpdf.enums import XPos, YPos

# Brand colors (matching static/css/style.css)
BG_COLOR = (9, 10, 18)
PANEL_COLOR = (20, 22, 42)
TEXT_COLOR = (238, 240, 251)
ACCENT_COLOR = (255, 79, 163)
MUTED_COLOR = (141, 144, 172)

PAGE_WIDTH = 900
MARGIN = 50
LINE_HEIGHT = 28
WRAP_WIDTH = 68

# --- Multi-script font resolution -----------------------------------------
_PROJECT_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static", "fonts")
_WINDOWS_FONT_DIR = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
_FONT_SEARCH_DIRS = [
    _PROJECT_FONT_DIR,                              # drop your own fonts here - checked first
    _WINDOWS_FONT_DIR,                               # Windows built-ins (dev machine)
    "/usr/share/fonts/truetype/noto",                # Debian/Ubuntu `fonts-noto` package
    "/usr/share/fonts/opentype/noto",                # Debian/Ubuntu `fonts-noto-cjk` package
    "/usr/share/fonts/truetype/dejavu",              # always-available Latin/Cyrillic/Greek fallback
]

# Script -> candidate font filenames, checked in order across the search
# dirs above. "latin" covers English and is also the fallback for anything
# unrecognized.
_SCRIPT_FONTS = {
    "latin":    ["arial.ttf", "DejaVuSans.ttf", "NotoSans-Regular.ttf"],
    "cyrillic": ["arial.ttf", "DejaVuSans.ttf", "NotoSans-Regular.ttf"],
    "greek":    ["arial.ttf", "DejaVuSans.ttf", "NotoSans-Regular.ttf"],
    "indic":    ["Nirmala.ttf", "NotoSansTamil-Regular.ttf", "NotoSansDevanagari-Regular.ttf"],
    "arabic":   ["arial.ttf", "NotoSansArabic-Regular.ttf"],
    "cjk":      ["Deng.ttf", "msyh.ttc", "NotoSansCJK-Regular.ttc"],
}
_SCRIPT_FONTS_BOLD = {
    "latin":    ["arialbd.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "cyrillic": ["arialbd.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "greek":    ["arialbd.ttf", "DejaVuSans-Bold.ttf", "NotoSans-Bold.ttf"],
    "indic":    ["Nirmalab.ttf", "NotoSansTamil-Bold.ttf", "NotoSansDevanagari-Bold.ttf"],
    "arabic":   ["arialbd.ttf", "NotoSansArabic-Bold.ttf"],
    "cjk":      ["Deng.ttf", "msyhbd.ttc", "NotoSansCJK-Bold.ttc"],
}

_font_path_cache = {}


def _detect_script(text: str) -> str:
    """Lightweight script detector based on Unicode code point ranges -
    good enough to pick a font, not a full language identifier."""
    for ch in text:
        cp = ord(ch)
        if 0x0900 <= cp <= 0x0D7F:      # Devanagari through Malayalam/Tamil
            return "indic"
        if 0x4E00 <= cp <= 0x9FFF:      # CJK Unified Ideographs
            return "cjk"
        if 0x3040 <= cp <= 0x30FF:      # Hiragana/Katakana
            return "cjk"
        if 0xAC00 <= cp <= 0xD7A3:      # Hangul syllables
            return "cjk"
        if 0x0600 <= cp <= 0x06FF:      # Arabic
            return "arabic"
        if 0x0400 <= cp <= 0x04FF:      # Cyrillic
            return "cyrillic"
        if 0x0370 <= cp <= 0x03FF:      # Greek
            return "greek"
    return "latin"


def _find_font_path(candidates) -> str | None:
    key = tuple(candidates)
    if key in _font_path_cache:
        return _font_path_cache[key]
    for name in candidates:
        for d in _FONT_SEARCH_DIRS:
            path = os.path.join(d, name)
            if os.path.exists(path):
                _font_path_cache[key] = path
                return path
    _font_path_cache[key] = None
    return None


def _font_path_for_script(script: str, bold: bool = False) -> str | None:
    table = _SCRIPT_FONTS_BOLD if bold else _SCRIPT_FONTS
    return _find_font_path(table.get(script, table["latin"]))


# --- Image export -----------------------------------------------------------
_pil_font_cache = {}


def _load_font(text: str, size: int, bold: bool = False):
    script = _detect_script(text) if text else "latin"
    path = _font_path_for_script(script, bold=bold)
    cache_key = (path, size)
    if cache_key in _pil_font_cache:
        return _pil_font_cache[cache_key]

    font = None
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except Exception:
            font = None
    if font is None:
        font = ImageFont.load_default()
    _pil_font_cache[cache_key] = font
    return font


def text_to_image(text: str, category_label: str) -> io.BytesIO:
    """Renders the extracted text onto a branded PNG image, sized to fit
    the content (short scans -> compact image, long scans -> taller image).
    Picks a matching system font per line so non-English scripts render
    correctly instead of showing as boxes."""
    text = text or "No text was extracted from this scan."
    wrapped_lines = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph.strip():
            wrapped_lines.append("")
            continue
        wrapped_lines.extend(textwrap.wrap(paragraph, width=WRAP_WIDTH) or [""])

    header_height = 110
    footer_height = 60
    content_height = max(len(wrapped_lines) * LINE_HEIGHT, LINE_HEIGHT)
    total_height = header_height + content_height + footer_height + (MARGIN * 2)

    img = Image.new("RGB", (PAGE_WIDTH, total_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    title_font = _load_font("ScanMate", 30, bold=True)
    label_font = _load_font(category_label, 16)
    footer_font = _load_font("ScanMate", 13)

    # Header - paste the real logo icon instead of an emoji (PIL's default
    # fonts can't render emoji, which is why it showed as a broken box before)
    try:
        logo_path = __file__.replace("utils/export.py", "static/images/icon-32.png").replace("utils\\export.py", "static\\images\\icon-32.png")
        logo = Image.open(logo_path).convert("RGBA").resize((32, 32))
        img.paste(logo, (MARGIN, MARGIN), logo)
        title_x = MARGIN + 42
    except Exception:
        title_x = MARGIN
    draw.text((title_x, MARGIN + 2), "ScanMate", font=title_font, fill=ACCENT_COLOR)
    draw.text((MARGIN, MARGIN + 42), category_label, font=label_font, fill=MUTED_COLOR)
    draw.line([(MARGIN, MARGIN + 75), (PAGE_WIDTH - MARGIN, MARGIN + 75)], fill=PANEL_COLOR, width=2)

    # Body text - font is picked per line so mixed-script scans (e.g.
    # English + Tamil in the same list) render each line correctly.
    y = MARGIN + header_height
    for line in wrapped_lines:
        body_font = _load_font(line, 18)
        draw.text((MARGIN, y), line, font=body_font, fill=TEXT_COLOR)
        y += LINE_HEIGHT

    # Footer
    footer_y = total_height - footer_height
    draw.line([(MARGIN, footer_y), (PAGE_WIDTH - MARGIN, footer_y)], fill=PANEL_COLOR, width=2)
    draw.text(
        (MARGIN, footer_y + 15),
        f"Generated by ScanMate · {datetime.utcnow().strftime('%d %b %Y')}",
        font=footer_font, fill=MUTED_COLOR,
    )

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


# --- PDF export ---------------------------------------------------------
def _pdf_font_for_script(pdf: FPDF, script: str, bold: bool = False) -> str | None:
    """Registers (once per pdf instance) and returns the FPDF font family
    name to render a given script, or None if no matching font file could
    be found on this machine."""
    path = _font_path_for_script(script, bold=bold)
    if not path:
        return None

    family = f"scanmate-{script}"
    style = "B" if bold else ""
    font_key = family + style
    if font_key not in pdf.fonts:
        try:
            pdf.add_font(family, style, path)
        except Exception:
            return None
    return family, style


def text_to_pdf(text: str, category_label: str) -> io.BytesIO:
    """Renders the extracted text as a clean, multi-page PDF - better than
    an image for longer scans since it paginates automatically. Uses the
    fast built-in Helvetica font for plain English text (unchanged from
    before), and switches to a matching system font per line for other
    scripts so they render as real characters instead of a placeholder."""
    text = text or "No text was extracted from this scan."

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 12, "ScanMate", ln=True)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, category_label, ln=True)
    pdf.cell(0, 8, f"Generated {datetime.utcnow().strftime('%d %b %Y')}", ln=True)
    pdf.ln(4)
    pdf.set_draw_color(200, 200, 200)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(6)

    pdf.set_text_color(20, 20, 20)

    any_unrendered = False
    for paragraph in (text.splitlines() or [""]):
        line = paragraph if paragraph.strip() else " "
        try:
            line.encode("latin-1")
            pdf.set_font("Helvetica", "", 12)
            pdf.multi_cell(0, 7, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            continue
        except UnicodeEncodeError:
            pass

        # Non-Latin-1 line: find a real font for its script.
        script = _detect_script(line)
        registered = _pdf_font_for_script(pdf, script, bold=False)
        if registered:
            family, style = registered
            pdf.set_font(family, style, 12)
            pdf.multi_cell(0, 7, line, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            any_unrendered = True
            pdf.set_font("Helvetica", "", 12)
            pdf.multi_cell(
                0, 7,
                "[Line contains a script this PDF couldn't render - see 'Download as Image' for the accurate version]",
                new_x=XPos.LMARGIN, new_y=YPos.NEXT
            )

    if any_unrendered:
        pdf.ln(4)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(150, 150, 150)
        pdf.multi_cell(
            0, 6,
            "Note: one or more lines used a script that couldn't be rendered "
            "in this PDF (no matching font found on the server). Use "
            "'Download as Image' instead for a fully accurate copy.",
            new_x=XPos.LMARGIN, new_y=YPos.NEXT
        )

    output = pdf.output(dest="S")
    if isinstance(output, str):
        output = output.encode("latin-1")
    buffer = io.BytesIO(output)
    buffer.seek(0)
    return buffer
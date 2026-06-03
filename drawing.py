import re
from functools import lru_cache
from pathlib import Path

import fitz
from PIL import Image, ImageDraw, ImageFont, ImageOps

from constants import SERIF_FONT, DEVA_FONT


@lru_cache(maxsize=32)
def get_font(size: int, path: Path = SERIF_FONT) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1], bb[0], bb[1]


def fit_and_draw(draw, text, cx, cy, max_w, max_h, start_size, color, font_path=SERIF_FONT, canvas=None):
    if canvas is not None and any('ऀ' <= ch <= 'ॿ' for ch in text):
        # Use PyMuPDF for Devanagari along with fitz
        color_str = color if (isinstance(color, str) and color.startswith("#")) else "#000000"
        size = start_size
        img = _render_deva_image(text, max(12, size), color_str)
        while size >= 12 and (img.width > max_w or img.height > max_h):
            size -= 2
            img = _render_deva_image(text, max(12, size), color_str)
        x = cx - img.width // 2
        y = cy - img.height // 2
        canvas.paste(img, (x, y), mask=img.split()[3])
        return
    # Shrink font size until the text fits inside the given box
    size = start_size
    while size >= 12:
        font = get_font(size, font_path)
        tw, th, ox, oy = measure(draw, text, font)
        if tw <= max_w and th <= max_h:
            break
        size -= 2
    font = get_font(size, font_path)
    tw, th, ox, oy = measure(draw, text, font)
    draw.text((cx - tw // 2 - ox, cy - th // 2 - oy), text, fill=color, font=font)


def has_devanagari(text: str) -> bool:
    return any('ऀ' <= ch <= 'ॿ' for ch in text)


_DEVA_RENDER_CACHE: dict[tuple, Image.Image] = {}


def _render_deva_image(text: str, font_size: int, color: str) -> Image.Image:
    """Render Devanagari text via PyMuPDF for correct complex-script shaping.
        along with the use of fitz for correct placement unconditionally.
    """
    key = (text, font_size, color)
    if key in _DEVA_RENDER_CACHE:
        return _DEVA_RENDER_CACHE[key]

    page_w = max(800, len(text) * font_size + 100)
    page_h = int(font_size * 2.5)
    css = (
        f"body {{ font-size: {font_size}px; color: black; "
        f"margin: 0; padding: 0; white-space: nowrap; }}"
        f" p {{ margin: 0; }}"
    )
    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_htmlbox(fitz.Rect(4, 4, page_w - 4, page_h - 4), f"<p>{text}</p>", css=css)
    pix = page.get_pixmap(alpha=False)
    doc.close()

    # Build an RGBA image: use inverted grayscale as alpha, fill with target color.
    gray = Image.frombytes("RGB", [pix.width, pix.height], pix.samples).convert("L")
    alpha = ImageOps.invert(gray)          # black text → 255, white bg → 0

    if isinstance(color, str) and color.startswith("#") and len(color) == 7:
        r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    else:
        r, g, b = 0, 0, 0

    rgba = Image.new("RGBA", gray.size, (r, g, b, 255))
    rgba.putalpha(alpha)

    bbox = rgba.getbbox()
    result = rgba.crop(bbox) if bbox else rgba
    _DEVA_RENDER_CACHE[key] = result
    return result


def english_from_vernacular(vernacular: str) -> str:
    # Names like "नीम (Neem)" -> "Neem"; falls back to the raw value
    m = re.search(r'\(([^)]+)\)', vernacular)
    if m:
        inner = m.group(1).strip()
        if inner and not inner.isdigit():
            return inner
    return vernacular.strip()


def parse_names(vernacular: str) -> tuple[str, str]:
    """Extract (english_name, hindi_name) from a vernacular string.

    Handles formats like:
      नीम (Neem)
      वायविडंग (झाड़ी), आंवला  Indian gooseberry
      सिंदूरी (हरा) (Annatto)
      Ficus benghalensis
    """
    vernacular = vernacular.strip()
    if not vernacular:
        return "", ""

    def _has_deva(text: str) -> bool:
        return any('ऀ' <= ch <= 'ॿ' for ch in text)

    # No Devanagari at all → purely English
    if not _has_deva(vernacular):
        return vernacular, ""

    # Exclusive end of the last Devanagari-containing segment:
    # start at one-past the last Devanagari char, then advance to the
    # closing ) if that char sits inside a parenthesised group.
    raw_end = max(i for i, ch in enumerate(vernacular) if 'ऀ' <= ch <= 'ॿ') + 1
    last_deva_end = raw_end
    for m in re.finditer(r'\([^)]*\)', vernacular):
        if _has_deva(m.group()) and m.start() <= raw_end - 1 < m.end():
            last_deva_end = m.end()

    # 1. Trailing unparenthesised Latin text after last Devanagari segment.
    after = vernacular[last_deva_end:].strip().lstrip(',').strip()
    after_no_parens = re.sub(r'\([^)]*\)', '', after).strip().lstrip(',').strip()
    english_trailing = after_no_parens if after_no_parens and not _has_deva(after_no_parens) else ""

    # 2. Last Latin parenthesised group (fallback when no plain trailing text).
    last_latin_paren = None
    if not english_trailing:
        for m in re.finditer(r'\(([^)]+)\)', vernacular):
            inner = m.group(1).strip()
            if inner and not _has_deva(inner) and not inner.isdigit():
                last_latin_paren = m

    english = english_trailing or (last_latin_paren.group(1).strip() if last_latin_paren else "")

    # Build Hindi by removing the English portion.
    if english_trailing:
        hindi_str = vernacular[:last_deva_end].rstrip(', \t').strip()
    elif last_latin_paren:
        hindi_str = (vernacular[:last_latin_paren.start()] + vernacular[last_latin_paren.end():]).strip()
    else:
        hindi_str = vernacular

    hindi = hindi_str if _has_deva(hindi_str) else ""
    return english, hindi


def split_script_runs(text: str) -> list[tuple[str, bool]]:
    # Splits mixed text into contiguous Devanagari / Latin segments
    if not text:
        return [("", False)]
    runs: list[tuple[str, bool]] = []
    current = text[0]
    current_deva = 'ऀ' <= text[0] <= 'ॿ'
    for ch in text[1:]:
        is_deva = 'ऀ' <= ch <= 'ॿ'
        if is_deva == current_deva:
            current += ch
        else:
            runs.append((current, current_deva))
            current = ch
            current_deva = is_deva
    runs.append((current, current_deva))
    return runs


def measure_mixed(draw, text, deva_font, latin_font) -> tuple[int, int]:
    total_w = max_h = 0
    for seg, is_deva in split_script_runs(text):
        w, h, _, _ = measure(draw, seg, deva_font if is_deva else latin_font)
        total_w += w
        max_h = max(max_h, h)
    return total_w, max_h


def wrap_text_mixed(draw, text, deva_font, latin_font, max_w) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        test = " ".join(current + [word])
        w, _ = measure_mixed(draw, test, deva_font, latin_font)
        if w <= max_w:
            current.append(word)
        else:
            if current:
                lines.append(" ".join(current))
            current = [word]
    if current:
        lines.append(" ".join(current))
    return lines or [""]


def line_script_metrics(text: str, deva_font, latin_font) -> tuple[int, int]:
    """Ascent and descent derived only from the fonts actually used in this line."""
    runs = split_script_runs(text)
    deva_asc, deva_desc = deva_font.getmetrics()
    lat_asc,  lat_desc  = latin_font.getmetrics()
    uses_deva  = any(is_d for _, is_d in runs)
    uses_latin = any(not is_d for _, is_d in runs)
    ascent  = max(deva_asc  if uses_deva  else 0, lat_asc  if uses_latin else 0)
    descent = max(deva_desc if uses_deva  else 0, lat_desc if uses_latin else 0)
    return ascent, descent


def draw_mixed_line(draw, text, x, baseline_y, deva_font, latin_font, color, canvas=None) -> None:
    if canvas is not None and any('ऀ' <= ch <= 'ॿ' for ch in text):
        color_str = color if (isinstance(color, str) and color.startswith("#")) else "#000000"
        font_size = deva_font.size
        img = _render_deva_image(text, font_size, color_str)
        asc, _ = deva_font.getmetrics()
        canvas.paste(img, (int(x), int(baseline_y - asc)), mask=img.split()[3])
        return
    cx = x
    for seg, is_deva in split_script_runs(text):
        font = deva_font if is_deva else latin_font
        draw.text((cx, baseline_y), seg, fill=color, font=font, anchor="ls")
        cx += int(draw.textlength(seg, font=font))

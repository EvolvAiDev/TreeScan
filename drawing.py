import re
from functools import lru_cache
from pathlib import Path

from PIL import ImageDraw, ImageFont

from constants import SERIF_FONT


@lru_cache(maxsize=32)
def get_font(size: int, path: Path = SERIF_FONT) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def measure(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont):
    bb = draw.textbbox((0, 0), text, font=font)
    return bb[2] - bb[0], bb[3] - bb[1], bb[0], bb[1]


def fit_and_draw(draw, text, cx, cy, max_w, max_h, start_size, color, font_path=SERIF_FONT):
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


def english_from_vernacular(vernacular: str) -> str:
    # Names like "नीम (Neem)" -> "Neem"; falls back to the raw value
    m = re.search(r'\(([^)]+)\)', vernacular)
    if m:
        inner = m.group(1).strip()
        if inner and not inner.isdigit():
            return inner
    return vernacular.strip()


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


def draw_mixed_line(draw, text, x, baseline_y, deva_font, latin_font, color) -> None:
    cx = x
    for seg, is_deva in split_script_runs(text):
        font = deva_font if is_deva else latin_font
        draw.text((cx, baseline_y), seg, fill=color, font=font, anchor="ls")
        cx += int(draw.textlength(seg, font=font))

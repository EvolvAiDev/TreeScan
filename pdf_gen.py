import csv
import io
import zipfile
from functools import lru_cache
from pathlib import Path

import openpyxl

import fitz
from PIL import Image, ImageDraw

from constants import (
    SERIF_FONT, DEVA_FONT, TABLE_FONT,
    HEADER_PATH, FOOTER_PATH, PAGE_W, TABLE_ROWS,
)
from drawing import get_font, measure, wrap_text_mixed, draw_mixed_line, line_script_metrics


@lru_cache(maxsize=4)
def _load_header(width: int) -> Image.Image:
    img = Image.open(HEADER_PATH).convert("RGB")
    aspect = img.height / img.width
    return img.resize((width, int(width * aspect)), Image.LANCZOS)


@lru_cache(maxsize=4)
def _load_footer(width: int) -> Image.Image:
    img = Image.open(FOOTER_PATH).convert("RGB")
    img = img.crop((0, 155, img.width, img.height))
    aspect = img.height / img.width
    return img.resize((width, int(width * aspect)), Image.LANCZOS)


def _render_table(row: dict, width: int) -> Image.Image:
    LABEL_W  = int(width * 0.18)
    VAL_W    = width - LABEL_W
    PAD      = 7
    FONT_SZ  = max(14, int(width * 0.0132))
    BORDER   = "#333333"
    LABEL_BG = "#a8b5af"

    label_font = get_font(FONT_SZ, TABLE_FONT)
    deva_font  = get_font(FONT_SZ, DEVA_FONT)
    latin_font = get_font(FONT_SZ, SERIF_FONT)

    # Probe canvas just for text measurement before the real image is sized
    probe_draw = ImageDraw.Draw(Image.new("RGB", (width, 50)))

    deva_ascent,  deva_descent  = deva_font.getmetrics()
    latin_ascent, latin_descent = latin_font.getmetrics()
    # Global lh used only for row height sizing so all rows stay the same height
    lh = max(deva_ascent + deva_descent, latin_ascent + latin_descent)

    row_data: list[tuple[int, list[str]]] = []
    for col_key, _ in TABLE_ROWS:
        val   = row.get(col_key, "")
        lines = wrap_text_mixed(probe_draw, val, deva_font, latin_font, VAL_W - 2 * PAD)
        h     = max(lh * len(lines) + 2 * PAD, 35)
        row_data.append((h, lines))

    tbl  = Image.new("RGB", (width, sum(h for h, _ in row_data) + 2), "white")
    draw = ImageDraw.Draw(tbl)

    y = 0
    for (col_key, col_label), (rh, val_lines) in zip(TABLE_ROWS, row_data):
        draw.rectangle([0, y, LABEL_W - 1, y + rh - 1], fill=LABEL_BG)
        lw, ll_h, lox, loy = measure(draw, col_label, label_font)
        draw.text((PAD, y + (rh - ll_h) // 2 - loy), col_label, fill="#1a1a1a", font=label_font)

        # Use per-line metrics so Latin-only rows (S_No_, Latitude, Longitude)
        # are centered by their actual font, not the taller Devanagari ascent
        per_line = [line_script_metrics(l, deva_font, latin_font) for l in val_lines]
        tv = y + (rh - sum(a + d for a, d in per_line)) // 2
        for line, (asc, desc) in zip(val_lines, per_line):
            draw_mixed_line(draw, line, LABEL_W + PAD, tv + asc, deva_font, latin_font, "#1a1a1a")
            tv += asc + desc

        draw.line([(0, y), (width - 1, y)], fill=BORDER, width=1)
        y += rh

    total_h = tbl.height
    draw.line([(0, total_h - 1), (width - 1, total_h - 1)], fill=BORDER, width=1)
    draw.line([(0, 0),           (0, total_h - 1)],          fill=BORDER, width=2)
    draw.line([(width - 1, 0),   (width - 1, total_h - 1)],  fill=BORDER, width=2)
    draw.line([(LABEL_W, 0),     (LABEL_W, total_h - 1)],    fill=BORDER, width=1)

    return tbl


def _pdf_to_images(pdf_bytes: bytes, width: int) -> list[Image.Image]:
    doc    = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        scale = width / page.rect.width
        pix   = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        img   = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        # Strip the page-number footer rendered into the PDF
        img = img.crop((0, 0, img.width, img.height - int(img.height * 0.07)))
        images.append(img)
    doc.close()
    return images


def build_tree_pdf(pdf_bytes: bytes, row: dict) -> bytes:
    width  = PAGE_W
    margin = 80

    tbl        = _render_table(row, width - 2 * margin)
    tbl_canvas = Image.new("RGB", (width, tbl.height), "white")
    tbl_canvas.paste(tbl, (margin, 0))

    spacer = Image.new("RGB", (width, 12), "white")
    footer = _load_footer(width)
    parts  = [_load_header(width), spacer, tbl_canvas] + _pdf_to_images(pdf_bytes, width)

    body_h = sum(p.height for p in parts)
    canvas = Image.new("RGB", (width, body_h + footer.height - 5), "white")
    y = 0
    for p in parts:
        canvas.paste(p, (0, y))
        y += p.height
    canvas.paste(footer, (0, body_h - 5))

    buf = io.BytesIO()
    canvas.save(buf, format="PDF", resolution=150)
    buf.seek(0)
    return buf.read()


def _read_rows(file_bytes: bytes, filename: str) -> list[dict]:
    if filename.lower().endswith(".xlsx"):
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
        ws = wb.active
        headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        rows = [
            {headers[i]: (str(cell.value) if cell.value is not None else "")
             for i, cell in enumerate(row)}
            for row in ws.iter_rows(min_row=2)
        ]
        wb.close()
        return rows
    return list(csv.DictReader(io.StringIO(file_bytes.decode("utf-8-sig"))))


def process_pdf_zip(
    zip_bytes: bytes, csv_bytes: bytes, filename: str = "data.csv", on_progress=None
) -> tuple[bytes, list[str], list[str]]:
    rows   = {r["S_No_"].strip(): r for r in _read_rows(csv_bytes, filename)}
    in_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))

    all_pdf_names = [n for n in in_zip.namelist() if not n.endswith("/")]
    # Strip whitespace from PDF stems 
    all_pdf_stems = {Path(n).stem.strip() for n in all_pdf_names}
    xlsx_s_nos    = set(rows.keys())

    _sort_key = lambda x: (not x.isdigit(), int(x) if x.isdigit() else x)
    pdf_not_in_xlsx = sorted(all_pdf_stems - xlsx_s_nos, key=_sort_key)
    xlsx_not_in_pdf = sorted(xlsx_s_nos - all_pdf_stems, key=_sort_key)

    matched = [n for n in sorted(all_pdf_names) if Path(n).stem.strip() in rows]
    total   = len(matched)
    out_buf = io.BytesIO()

    with zipfile.ZipFile(out_buf, "w", zipfile.ZIP_DEFLATED) as out_zip:
        for i, name in enumerate(matched):
            s_no = Path(name).stem.strip()          # clean key → looks up row correctly
            out_zip.writestr(f"{s_no}.pdf", build_tree_pdf(in_zip.read(name), rows[s_no]))
            if on_progress:
                on_progress(i + 1, total)

    out_buf.seek(0)
    return out_buf.read(), pdf_not_in_xlsx, xlsx_not_in_pdf

from pathlib import Path

BASE = Path(__file__).parent

SERIF_FONT    = BASE / "fonts" / "NotoSerif-Regular.ttf"
DEVA_FONT     = BASE / "fonts" / "NotoSansDevanagari-Regular.ttf"
TABLE_FONT    = BASE / "fonts" / "font.ttf"
TEMPLATE_PATH = BASE / "template2.png"
HEADER_PATH   = BASE / "header.jpeg"
FOOTER_PATH   = BASE / "footer.png"

TEXT_COLOR = "#1F3D2E"
PAGE_W     = 1240  # ~A4 at 150 DPI

# QR card layout: box where the QR code is pasted, and text zones above it
QR_CX = 627
QR_BOX_X1, QR_BOX_Y1 = 350, 395
QR_BOX_X2, QR_BOX_Y2 = 897, 937
NUM_Y1,  NUM_Y2  = 50,  182
NAME_Y1, NAME_Y2 = 240, 385

# (csv_column, display_label) pairs for the info table in each PDF
TABLE_ROWS = [
    ("S_No_",      "S_No_"),
    ("Vernacular", "Vernacular"),
    ("Scientific", "Scientific"),
    ("Family",     "Family"),
    ("Remarks_",   "Remarks_"),
    ("Latitude",   "Latitude"),
    ("Longitude",  "Longitude"),
    ("Plant_Orig", "Plant_Orig"),
]


"""
Diagnose raw OCR output from both grids so we can design the right parser.
"""
import os
from PIL import Image
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def test_file(path):
    if not os.path.exists(path):
        print(f"  FILE NOT FOUND: {path}")
        return
    img = Image.open(path)
    print(f"  Size: {img.size}, Mode: {img.mode}")
    for psm in [3, 6, 11]:
        text = pytesseract.image_to_string(img, config=f"--psm {psm}")
        print(f"\n  === PSM {psm} ===")
        print(text[:1000])

import glob

# Find the two most recently uploaded timetables
files = sorted(glob.glob("uploads/timetables/*"), key=os.path.getmtime, reverse=True)[:4]
for f in files:
    print(f"\n\n=== FILE: {f} ===")
    test_file(f)


import os, re, glob
from PIL import Image, ImageOps, ImageEnhance
import pytesseract

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

files = sorted(glob.glob("uploads/timetables/*"), key=os.path.getmtime, reverse=True)[:2]

for path in files:
    print(f"\n=== {path} ===")
    img = Image.open(path)
    w, h = img.size
    if max(w,h) < 2000:
        scale = 2000 / max(w, h)
        img = img.resize((int(w*scale), int(h*scale)), Image.LANCZOS)
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(1.5)
    
    import pandas as pd
    data = pytesseract.image_to_data(img, config="--psm 6", output_type=pytesseract.Output.DATAFRAME)
    data = data[(data.conf > 0) & (data.text.str.strip() != "")].copy()
    data["cy"] = data["top"] + data["height"] // 2
    data["cx"] = data["left"] + data["width"] // 2
    data = data.sort_values(["cy", "cx"]).reset_index(drop=True)
    
    # Cluster rows
    row_labels = []
    current_row = 0
    prev_cy = None
    for cy in data["cy"]:
        if prev_cy is None or abs(cy - prev_cy) > 20:
            current_row += 1
        row_labels.append(current_row)
        prev_cy = cy
    data["row"] = row_labels
    
    # Cluster cols
    col_labels = []
    current_col = 0
    prev_cx = None
    for cx in data.sort_values("cx")["cx"]:
        if prev_cx is None or abs(cx - prev_cx) > 30:
            current_col += 1
        col_labels.append(current_col)
        prev_cx = cx
    sorted_cx = data.sort_values("cx").index
    data.loc[sorted_cx, "col"] = col_labels
    
    cells = {}
    for _, row in data.iterrows():
        key = (int(row["row"]), int(row["col"]))
        cells.setdefault(key, []).append(str(row["text"]).strip())
    cells = {k: " ".join(v) for k, v in cells.items()}
    
    rows = sorted(set(r for r, c in cells))
    cols = sorted(set(c for r, c in cells))
    
    print(f"  Total rows: {len(rows)}, cols: {len(cols)}")
    
    # Print first 5 rows
    for r in rows[:5]:
        row_text = {c: cells.get((r, c), "") for c in cols}
        print(f"  Row {r}: {row_text}")
    
    # Time detection
    time_re = re.compile(r"\d{1,2}[:.]?\d{2}\s*[-–—]\s*\d{1,2}[:.]?\d{2}")
    day_re = re.compile(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", re.I)
    
    print("\n  Time matches per row:")
    for r in rows[:5]:
        row_text = " ".join(cells.get((r, c), "") for c in cols)
        matches = time_re.findall(row_text)
        print(f"    Row {r}: {matches}")
    
    print("\n  Day matches per col:")
    for c in cols[:4]:
        col_text = " ".join(cells.get((r, c), "") for r in rows)
        matches = day_re.findall(col_text)
        print(f"    Col {c}: {matches}")

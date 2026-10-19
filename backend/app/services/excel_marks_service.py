from __future__ import annotations

import io
from decimal import Decimal, InvalidOperation
from typing import Sequence
from uuid import UUID

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

from app.models.institution import Cohort
from app.models.user import User
from app.models.class_marks import Exam
from app.services.excel_student_service import sanitize_text_cell


def generate_marks_template(
    cohort: Cohort,
    exam: Exam,
    students: Sequence[User],
) -> bytes:
    """
    Generate an Excel (.xlsx) template for entering marks for a class exam.
    Pre-populates active students from the cohort.
    Applies formula injection protection to all text cells.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Class Marks"

    # Ensure grid lines are visible
    ws.views.sheetView[0].showGridLines = True

    # Styling Palette: Emerald header, dark slate accents
    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid")  # emerald-700
    meta_fill = PatternFill(start_color="F1F5F9", end_color="F1F5F9", fill_type="solid")    # slate-100
    white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    meta_bold = Font(name="Calibri", size=10, bold=True, color="0F172A")
    meta_font = Font(name="Calibri", size=10, color="334155")
    data_font = Font(name="Calibri", size=10, color="0F172A")
    hint_font = Font(name="Calibri", size=9, italic=True, color="64748B")

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    # 1. Metadata rows (Rows 1 - 3)
    ws["A1"] = "Class:"
    ws["B1"] = sanitize_text_cell(f"{cohort.name} ({cohort.academic_year})")
    ws["C1"] = "Exam Title:"
    ws["D1"] = sanitize_text_cell(exam.title)

    ws["A2"] = "Subject:"
    ws["B2"] = sanitize_text_cell(exam.subject)
    ws["C2"] = "Max Marks:"
    ws["D2"] = float(exam.max_marks)

    ws["A3"] = "Instructions:"
    ws["B3"] = "Enter marks (0 to Max Marks) or enter Y in Absent column. Leave blank if not entered yet."

    for r in range(1, 4):
        for c in range(1, 5):
            cell = ws.cell(row=r, column=c)
            cell.fill = meta_fill
            if c in (1, 3):
                cell.font = meta_bold
            elif r == 3:
                cell.font = hint_font
            else:
                cell.font = meta_font

    ws.merge_cells("B3:D3")

    # 2. Table Column Headers (Row 5)
    headers = [
        "Full Name",
        "Email",
        "Username",
        "Max Marks",
        "Marks Obtained",
        "Absent (Y/N)",
    ]

    for col_idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=5, column=col_idx, value=text)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = thin_border

    ws.row_dimensions[5].height = 26

    # 3. Data rows for active students
    row_num = 6
    for st in students:
        full_name = sanitize_text_cell(st.full_name or "")
        email = sanitize_text_cell(st.email or "")
        username = sanitize_text_cell(st.username or "")
        max_marks = float(exam.max_marks)

        ws.cell(row=row_num, column=1, value=full_name).font = data_font
        ws.cell(row=row_num, column=2, value=email).font = data_font
        ws.cell(row=row_num, column=3, value=username).font = data_font
        ws.cell(row=row_num, column=4, value=max_marks).font = data_font
        ws.cell(row=row_num, column=5, value=None).font = data_font  # Blank for marks
        ws.cell(row=row_num, column=6, value=None).font = data_font  # Blank for absent

        for c in range(1, 7):
            ws.cell(row=row_num, column=c).border = thin_border
            if c in (4, 5, 6):
                ws.cell(row=row_num, column=c).alignment = Alignment(horizontal="center")

        ws.row_dimensions[row_num].height = 20
        row_num += 1

    # Adjust column widths
    column_widths = {1: 24, 2: 28, 3: 18, 4: 14, 5: 16, 6: 15}
    for col_idx, width in column_widths.items():
        col_letter = openpyxl.utils.get_column_letter(col_idx)
        ws.column_dimensions[col_letter].width = width

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def parse_and_preview_marks_excel(
    file_bytes: bytes,
    exam: Exam,
    cohort: Cohort,
    active_students: Sequence[User],
) -> tuple[list[dict], list[dict]]:
    """
    Parse an uploaded .xlsx file and validate rows for entering marks.
    Returns (valid_rows, invalid_rows).
    Enforces <= 2MB, <= 500 rows, and strict validation against active students of the cohort.
    """
    if len(file_bytes) > 2 * 1024 * 1024:
        raise ValueError("File exceeds maximum upload size of 2 MB")

    try:
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    except Exception as exc:
        raise ValueError(f"Could not read Excel file (.xlsx format required): {exc}")

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("Uploaded Excel spreadsheet is empty")

    # Locate table header row (look for "marks" and "email" or "username")
    header_row_idx = -1
    col_name_idx = -1
    col_email_idx = -1
    col_username_idx = -1
    col_marks_idx = -1
    col_absent_idx = -1

    for idx, r in enumerate(rows[:15]):  # Search within top 15 rows
        if not r:
            continue
        row_strs = [str(c).strip().lower() if c is not None else "" for c in r]
        # Check if row looks like the header
        has_marks = any("marks" in h for h in row_strs)
        has_id = any("email" in h or "username" in h or "student" in h for h in row_strs)

        if has_marks and has_id:
            header_row_idx = idx
            for c_idx, h in enumerate(row_strs):
                if "full name" in h or "student name" in h:
                    col_name_idx = c_idx
                elif "email" in h:
                    col_email_idx = c_idx
                elif "username" in h:
                    col_username_idx = c_idx
                elif "obtained" in h or "marks" in h and "max" not in h:
                    col_marks_idx = c_idx
                elif "absent" in h:
                    col_absent_idx = c_idx
            break

    if header_row_idx == -1 or (col_email_idx == -1 and col_username_idx == -1) or col_marks_idx == -1:
        raise ValueError(
            "Could not find valid table headers. The file must include columns for Student Email/Username and Marks Obtained."
        )

    # Build active student lookups for this cohort
    student_by_email: dict[str, User] = {
        (s.email or "").strip().lower(): s for s in active_students if s.email
    }
    student_by_username: dict[str, User] = {
        (s.username or "").strip().lower(): s for s in active_students if s.username
    }

    data_rows = rows[header_row_idx + 1:]
    non_empty_rows: list[tuple[int, tuple]] = []

    for r_idx, r in enumerate(data_rows, start=header_row_idx + 2):
        if any(c is not None and str(c).strip() != "" for c in r):
            non_empty_rows.append((r_idx, r))

    if not non_empty_rows:
        raise ValueError("No student mark rows found in the uploaded file")

    if len(non_empty_rows) > 500:
        raise ValueError(f"Upload exceeds maximum limit of 500 rows (found {len(non_empty_rows)} rows)")

    valid_rows: list[dict] = []
    invalid_rows: list[dict] = []
    seen_student_ids: set[UUID] = set()

    for row_num, r in non_empty_rows:
        name_val = str(r[col_name_idx]).strip() if col_name_idx != -1 and len(r) > col_name_idx and r[col_name_idx] is not None else ""
        email_val = str(r[col_email_idx]).strip() if col_email_idx != -1 and len(r) > col_email_idx and r[col_email_idx] is not None else ""
        username_val = str(r[col_username_idx]).strip() if col_username_idx != -1 and len(r) > col_username_idx and r[col_username_idx] is not None else ""
        marks_raw = r[col_marks_idx] if len(r) > col_marks_idx else None
        absent_raw = r[col_absent_idx] if col_absent_idx != -1 and len(r) > col_absent_idx else None

        # Clean formula prefixes if present
        if email_val.startswith("'"): email_val = email_val[1:]
        if username_val.startswith("'"): username_val = username_val[1:]
        if name_val.startswith("'"): name_val = name_val[1:]

        identifier = email_val or username_val or f"Row {row_num}"

        # 1. Match student in cohort
        matched_student = None
        if email_val:
            matched_student = student_by_email.get(email_val.lower())
        if not matched_student and username_val:
            matched_student = student_by_username.get(username_val.lower())

        if not matched_student:
            invalid_rows.append({
                "row_num": row_num,
                "student_id": None,
                "student_identifier": identifier,
                "student_name": name_val or None,
                "marks_obtained": None,
                "is_absent": False,
                "valid": False,
                "error_reason": f"Student '{identifier}' is not an active student in this class ({cohort.name}).",
            })
            continue

        # 2. Check for duplicate student row in the uploaded sheet
        if matched_student.id in seen_student_ids:
            invalid_rows.append({
                "row_num": row_num,
                "student_id": matched_student.id,
                "student_identifier": identifier,
                "student_name": matched_student.full_name or matched_student.username,
                "marks_obtained": None,
                "is_absent": False,
                "valid": False,
                "error_reason": f"Duplicate row for student '{identifier}' in uploaded file.",
            })
            continue

        seen_student_ids.add(matched_student.id)

        # 3. Parse Absent flag
        is_absent = False
        if absent_raw is not None:
            s_absent = str(absent_raw).strip().lower()
            if s_absent in ("y", "yes", "true", "1", "absent"):
                is_absent = True
            elif s_absent in ("n", "no", "false", "0", ""):
                is_absent = False
            else:
                invalid_rows.append({
                    "row_num": row_num,
                    "student_id": matched_student.id,
                    "student_identifier": identifier,
                    "student_name": matched_student.full_name or matched_student.username,
                    "marks_obtained": None,
                    "is_absent": False,
                    "valid": False,
                    "error_reason": f"Invalid Absent value '{absent_raw}'. Must be 'Y' or 'N' (or blank).",
                })
                continue

        # 4. Parse Marks Obtained
        parsed_marks: Decimal | None = None
        if marks_raw is not None and str(marks_raw).strip() != "":
            raw_str = str(marks_raw).strip()
            # Clean leading formula quote if any
            if raw_str.startswith("'"):
                raw_str = raw_str[1:]
            try:
                parsed_marks = round(Decimal(raw_str), 2)
            except (InvalidOperation, ValueError):
                invalid_rows.append({
                    "row_num": row_num,
                    "student_id": matched_student.id,
                    "student_identifier": identifier,
                    "student_name": matched_student.full_name or matched_student.username,
                    "marks_obtained": None,
                    "is_absent": is_absent,
                    "valid": False,
                    "error_reason": f"Marks '{marks_raw}' is not a valid number.",
                })
                continue

        # 5. Validation rules on marks and absence
        if is_absent:
            if parsed_marks is not None and parsed_marks > 0:
                invalid_rows.append({
                    "row_num": row_num,
                    "student_id": matched_student.id,
                    "student_identifier": identifier,
                    "student_name": matched_student.full_name or matched_student.username,
                    "marks_obtained": parsed_marks,
                    "is_absent": True,
                    "valid": False,
                    "error_reason": f"Cannot enter marks ({parsed_marks}) when student is marked Absent.",
                })
                continue
            parsed_marks = None  # Absent means no mark obtained

        if parsed_marks is not None:
            if parsed_marks < 0:
                invalid_rows.append({
                    "row_num": row_num,
                    "student_id": matched_student.id,
                    "student_identifier": identifier,
                    "student_name": matched_student.full_name or matched_student.username,
                    "marks_obtained": parsed_marks,
                    "is_absent": is_absent,
                    "valid": False,
                    "error_reason": "Marks cannot be negative.",
                })
                continue

            if parsed_marks > exam.max_marks:
                invalid_rows.append({
                    "row_num": row_num,
                    "student_id": matched_student.id,
                    "student_identifier": identifier,
                    "student_name": matched_student.full_name or matched_student.username,
                    "marks_obtained": parsed_marks,
                    "is_absent": is_absent,
                    "valid": False,
                    "error_reason": f"Marks ({parsed_marks}) exceed maximum marks ({exam.max_marks}).",
                })
                continue

        valid_rows.append({
            "row_num": row_num,
            "student_id": matched_student.id,
            "student_identifier": identifier,
            "student_name": matched_student.full_name or matched_student.username,
            "marks_obtained": parsed_marks,
            "is_absent": is_absent,
            "valid": True,
            "error_reason": None,
        })

    return valid_rows, invalid_rows


def generate_marks_error_report(invalid_rows: Sequence[dict]) -> bytes:
    """
    Generate an Excel error report spreadsheet listing all rejected rows and reasons.
    Applies formula injection protection.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Marks Errors"
    ws.views.sheetView[0].showGridLines = True

    header_fill = PatternFill(start_color="991B1B", end_color="991B1B", fill_type="solid")  # red-800
    white_bold = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    data_font = Font(name="Calibri", size=10, color="0F172A")
    error_font = Font(name="Calibri", size=10, color="DC2626")  # red-600

    thin_border = Border(
        left=Side(style="thin", color="CBD5E1"),
        right=Side(style="thin", color="CBD5E1"),
        top=Side(style="thin", color="CBD5E1"),
        bottom=Side(style="thin", color="CBD5E1"),
    )

    headers = ["Row", "Student Identifier", "Student Name", "Error Reason"]
    for col_idx, text in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx, value=text)
        cell.font = white_bold
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = thin_border

    ws.row_dimensions[1].height = 24

    for r_idx, item in enumerate(invalid_rows, start=2):
        ws.cell(row=r_idx, column=1, value=item.get("row_num")).font = data_font
        ws.cell(row=r_idx, column=2, value=sanitize_text_cell(item.get("student_identifier"))).font = data_font
        ws.cell(row=r_idx, column=3, value=sanitize_text_cell(item.get("student_name") or "")).font = data_font
        ws.cell(row=r_idx, column=4, value=sanitize_text_cell(item.get("error_reason") or "")).font = error_font

        for c in range(1, 5):
            ws.cell(row=r_idx, column=c).border = thin_border
            if c == 1:
                ws.cell(row=r_idx, column=c).alignment = Alignment(horizontal="center")

        ws.row_dimensions[r_idx].height = 20

    ws.column_dimensions["A"].width = 10
    ws.column_dimensions["B"].width = 28
    ws.column_dimensions["C"].width = 24
    ws.column_dimensions["D"].width = 60

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

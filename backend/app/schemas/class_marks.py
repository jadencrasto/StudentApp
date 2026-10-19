from __future__ import annotations

from uuid import UUID
from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, Field, field_validator


class CreateExamRequest(BaseModel):
    cohort_id: UUID
    exam_type: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=150)
    subject: str = Field(..., min_length=1, max_length=100)
    max_marks: Decimal = Field(..., gt=0, le=1000)
    exam_date: date | None = None

    @field_validator("title", "subject", "exam_type")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Field cannot be blank or whitespace only")
        return s

    @field_validator("max_marks")
    @classmethod
    def round_max_marks(cls, v: Decimal) -> Decimal:
        return round(v, 2)


class UpdateExamRequest(BaseModel):
    title: str | None = None
    exam_type: str | None = None
    subject: str | None = None
    max_marks: Decimal | None = None
    exam_date: date | None = None

    @field_validator("title", "subject", "exam_type")
    @classmethod
    def strip_whitespace(cls, v: str | None) -> str | None:
        if v is not None:
            s = v.strip()
            if not s:
                raise ValueError("Field cannot be blank or whitespace only")
            return s
        return None

    @field_validator("max_marks")
    @classmethod
    def validate_max_marks(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v <= 0 or v > 1000:
                raise ValueError("Max marks must be between 0.01 and 1000")
            return round(v, 2)
        return None


class ExamResponse(BaseModel):
    id: UUID
    institution_id: UUID
    cohort_id: UUID
    cohort_name: str | None = None
    exam_type: str
    title: str
    subject: str
    max_marks: Decimal
    exam_date: date | None = None
    status: str
    published_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    total_students: int = 0
    graded_count: int = 0
    absent_count: int = 0
    unentered_count: int = 0


class PublishExamResponse(BaseModel):
    exam: ExamResponse
    warnings: list[str] = []


class StudentMarkItem(BaseModel):
    student_id: UUID
    student_name: str | None = None
    student_email: str | None = None
    student_username: str | None = None
    marks_obtained: Decimal | None = None
    is_absent: bool = False
    percentage: Decimal | None = None
    status: str = "not_entered"  # graded | absent | not_entered


class StudentMarkEntryInput(BaseModel):
    student_id: UUID
    marks_obtained: Decimal | None = None
    is_absent: bool = False

    @field_validator("marks_obtained")
    @classmethod
    def validate_marks(cls, v: Decimal | None) -> Decimal | None:
        if v is not None:
            if v < 0:
                raise ValueError("Marks obtained cannot be negative")
            return round(v, 2)
        return None


class SaveMarksRequest(BaseModel):
    marks: list[StudentMarkEntryInput]
    reason: str | None = None  # Mandatory if exam is already published


class ExamRosterMarksResponse(BaseModel):
    exam: ExamResponse
    students: list[StudentMarkItem]


class StudentExamMarkResponse(BaseModel):
    exam_id: UUID
    exam_title: str
    exam_type: str
    subject: str
    max_marks: Decimal
    exam_date: date | None = None
    marks_obtained: Decimal | None = None
    is_absent: bool = False
    percentage: Decimal | None = None
    status: str  # graded | absent | not_entered
    display_text: str


class StudentMarksOverviewResponse(BaseModel):
    enrolled: bool
    cohort: dict | None = None
    exams: list[StudentExamMarkResponse] = []
    summary: dict = {
        "total_exams": 0,
        "completed_exams": 0,
        "overall_percentage": None,
    }


class BulkMarksPreviewRow(BaseModel):
    row_num: int
    student_id: UUID | None = None
    student_identifier: str
    student_name: str | None = None
    marks_obtained: Decimal | None = None
    is_absent: bool = False
    valid: bool
    error_reason: str | None = None


class BulkMarksPreviewResponse(BaseModel):
    exam_id: UUID
    total_rows: int
    valid_rows_count: int
    invalid_rows_count: int
    valid_rows: list[BulkMarksPreviewRow]
    invalid_rows: list[BulkMarksPreviewRow]
    error_report_available: bool = False


class BulkMarksConfirmRequest(BaseModel):
    rows: list[StudentMarkEntryInput]
    reason: str | None = None  # Required if published

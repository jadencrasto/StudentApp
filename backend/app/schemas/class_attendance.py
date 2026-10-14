from uuid import UUID
from datetime import date, datetime
from pydantic import BaseModel, Field


class StudentAttendanceItem(BaseModel):
    student_id: UUID
    status: str = Field(..., pattern="^(present|absent)$")
    reason: str | None = Field(default=None, max_length=255)


class BulkMarkAttendanceRequest(BaseModel):
    cohort_id: UUID
    class_date: date
    subject_name: str = Field(..., min_length=1, max_length=100)
    students: list[StudentAttendanceItem]


class StudentAttendanceSummaryItem(BaseModel):
    student_id: UUID
    full_name: str
    email: str
    username: str
    total_classes: int
    present_count: int
    absent_count: int
    attendance_percentage: float
    below_threshold: bool
    status_on_date: str | None = None


class CohortAttendanceResponse(BaseModel):
    cohort_id: UUID
    cohort_name: str
    academic_year: str
    level_type: str
    level_value: str
    class_date: date | None = None
    subject_name: str | None = None
    subjects: list[str]
    students: list[StudentAttendanceSummaryItem]


class StudentSubjectSummary(BaseModel):
    subject_name: str
    total_classes: int
    present_count: int
    absent_count: int
    attendance_percentage: float
    below_threshold: bool
    classes_needed_to_recover: int


class StudentRecordItem(BaseModel):
    id: UUID
    class_date: date
    subject_name: str
    status: str
    created_at: datetime


class StudentClassAttendanceResponse(BaseModel):
    enrolled: bool
    cohort: dict | None = None
    overall_percentage: float
    total_classes: int
    present_count: int
    absent_count: int
    subjects: list[StudentSubjectSummary]
    recent_records: list[StudentRecordItem]

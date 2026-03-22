"""
All Pydantic schemas (request/response validation) in one file.
Split into separate files if the project grows large.
"""
from __future__ import annotations
from datetime import datetime, date, time
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, AliasChoices


# ─── Auth ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:     EmailStr
    username:  str = Field(min_length=3, max_length=100)
    full_name: Optional[str] = None
    password:  str = Field(min_length=8)


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class UserOut(BaseModel):
    id:         UUID
    email:      str
    username:   str
    full_name:  Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Assignment ───────────────────────────────────────────────

class AssignmentCreate(BaseModel):
    title:       str = Field(max_length=500)
    subject:     Optional[str] = None
    task_type:   str = "assignment"
    description: Optional[str] = None
    deadline:    Optional[date] = None
    priority:    str = "medium"


class AssignmentUpdate(BaseModel):
    title:       Optional[str]  = None
    subject:     Optional[str]  = None
    task_type:   Optional[str]  = None
    description: Optional[str]  = None
    deadline:    Optional[date]  = None
    priority:    Optional[str]   = None
    status:      Optional[str]   = None


class AssignmentOut(BaseModel):
    id:                 UUID
    user_id:            UUID
    title:              str
    subject:            Optional[str]
    task_type:          str
    description:        Optional[str]
    deadline:           Optional[date]
    priority:           str
    status:             str
    ai_metadata:        Optional[dict] = None
    source_document_id: Optional[UUID] = None
    classroom_id:       Optional[str]  = None
    created_at:         datetime
    updated_at:         datetime

    model_config = {"from_attributes": True}


# ─── Subject ─────────────────────────────────────────────────

class SubjectCreate(BaseModel):
    name: str = Field(max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)


class SubjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    code: Optional[str] = Field(default=None, max_length=50)


class SubjectOut(BaseModel):
    id:            UUID
    name:          str
    code:          Optional[str]
    total_classes: int
    created_at:    datetime

    model_config = {"from_attributes": True}


# ─── Attendance ───────────────────────────────────────────────

class AttendanceMarkRequest(BaseModel):
    subject_id: UUID
    timetable_entry_id: Optional[UUID] = None
    class_date: date = Field(validation_alias=AliasChoices('class_date', 'date'))
    status:     str  # present | absent | late | excused
    notes:      Optional[str] = None

class AttendanceRecordOut(BaseModel):
    id:          UUID
    subject_id:  UUID
    class_date:  date
    status:      str
    notes:       Optional[str]
    created_at:  datetime

    model_config = {"from_attributes": True}


class AttendanceSummaryOut(BaseModel):
    subject_id:           UUID
    subject_name:         str
    subject_code:         Optional[str]
    total_classes:        int
    present_count:        int
    absent_count:         int
    late_count:           int
    attendance_percentage: float
    below_threshold:      bool   # True if < 75%


# ─── Timetable ───────────────────────────────────────────────

class TimetableEntryBase(BaseModel):
    subject_id: UUID
    day_of_week: int = Field(ge=0, le=6)
    start_time: str
    end_time: str
    room: Optional[str] = None
    notes: Optional[str] = None


class TimetableEntryCreate(TimetableEntryBase):
    pass


class TimetableEntryOut(BaseModel):
    id: UUID
    subject_id: UUID
    subject_name: Optional[str] = None
    day_of_week: int
    start_time: str
    end_time: str
    room: Optional[str]
    notes: Optional[str]
    is_active: bool


class TimetableUploadOut(BaseModel):
    status: str
    document_id: UUID
    entries: list[dict]
    confidence: float = 0.0
    notes: Optional[str] = None
    error: Optional[str] = None


class MorningCheckinClass(BaseModel):
    subject_id: UUID
    subject_name: str
    start_time: str
    end_time: str
    room: Optional[str] = None
    is_marked: bool


class MorningCheckinOut(BaseModel):
    type: str = "morning_checkin"
    classes: list[MorningCheckinClass]
    total: int
    marked: int


class UnmarkedClassOut(BaseModel):
    subject_id: UUID
    subject_name: str
    time: str


class UnmarkedReminderOut(BaseModel):
    type: str = "unmarked"
    classes: list[UnmarkedClassOut]
    count: int


class EndOfDayOut(BaseModel):
    type: str = "end_of_day"
    total_classes: int
    marked_classes: int
    present_count: int
    absent_count: int
    late_count: int
    unmarked_count: int


# ─── Activity ─────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    title:         str = Field(max_length=500)
    category:      Optional[str] = None
    # Not required when a recurrence pattern is set (start/end dates used instead)
    activity_date: Optional[date] = None
    start_time:    Optional[time] = None
    end_time:      Optional[time] = None
    location:      Optional[str] = None
    description:   Optional[str] = None
    # Recurrence
    recurrence_type:       Optional[str] = "none"   # none|daily|every_2_days|...
    recurrence_start_date: Optional[date] = None
    recurrence_end_date:   Optional[date] = None
    custom_interval:       Optional[int]  = None
    custom_interval_unit:  Optional[str]  = None    # days|weeks|months


class ActivityUpdate(BaseModel):
    title:                 Optional[str]  = None
    category:              Optional[str]  = None
    activity_date:         Optional[date] = None
    start_time:            Optional[time] = None
    end_time:              Optional[time] = None
    location:              Optional[str]  = None
    description:           Optional[str]  = None
    recurrence_type:       Optional[str]  = None
    recurrence_start_date: Optional[date] = None
    recurrence_end_date:   Optional[date] = None
    custom_interval:       Optional[int]  = None
    custom_interval_unit:  Optional[str]  = None


class ActivityOut(BaseModel):
    id:             UUID
    title:          str
    category:       Optional[str]
    activity_date:  date
    start_time:     Optional[time]
    end_time:       Optional[time]
    location:       Optional[str]
    description:    Optional[str]
    has_conflict:   bool
    conflict_detail: Optional[str]
    # Recurrence
    recurrence_type:        Optional[str]  = "none"
    recurrence_start_date:  Optional[date] = None
    recurrence_end_date:    Optional[date] = None
    custom_interval:        Optional[int]  = None
    custom_interval_unit:   Optional[str]  = None
    parent_activity_id:     Optional[UUID] = None
    is_recurring_instance:  bool           = False
    created_at:     datetime

    model_config = {"from_attributes": True}


# ─── Document Extraction ──────────────────────────────────────

class ExtractionResult(BaseModel):
    subject:    Optional[str]
    task_type:  Optional[str]
    title:      Optional[str]
    deadline:   Optional[str]   # raw string from AI, parse to date on save
    confidence: float = 0.0


class DocumentOut(BaseModel):
    id:                UUID
    original_filename: Optional[str]
    file_type:         Optional[str]
    extraction_status: str
    extracted_data:    dict
    created_at:        datetime

    model_config = {"from_attributes": True}


class EstimateTimeRequest(BaseModel):
    text: str = Field(min_length=1)
    task_type: Optional[str] = None


# ─── Alert ───────────────────────────────────────────────────

class AlertOut(BaseModel):
    id:          UUID
    alert_type:  str
    severity:    str
    title:       str
    message:     str
    is_read:     bool
    expires_at:  Optional[date]
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─── Dashboard ───────────────────────────────────────────────

class DashboardStatsOut(BaseModel):
    pending_assignments:  int
    attendance_avg:       float
    upcoming_activities:  int
    unread_alerts:        int

class DashboardDeadlineOut(BaseModel):
    id:       str
    title:    str
    subject:  Optional[str] = None
    deadline: str
    status:   str

class DashboardAlertOut(BaseModel):
    id:         str
    title:      str
    message:    str
    type:       str
    created_at: str

class DashboardOut(BaseModel):
    stats:     DashboardStatsOut
    deadlines: list[DashboardDeadlineOut]
    alerts:    list[DashboardAlertOut]


# ─── Chat / Chatbot ──────────────────────────────────────────

class ChatMessageOut(BaseModel):
    id:         UUID
    role:       str
    content:    str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatConversationOut(BaseModel):
    id:          UUID
    title:       str
    mode:        str
    document_id: Optional[UUID] = None
    is_active:   bool
    created_at:  datetime
    updated_at:  datetime

    model_config = {"from_attributes": True}


class ChatConversationDetailOut(ChatConversationOut):
    messages: list[ChatMessageOut] = []

    model_config = {"from_attributes": True}


class ChatSendRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ChatCreateRequest(BaseModel):
    mode:        str = "general"          # "general" | "viva"
    document_id: Optional[UUID] = None    # required when mode == "viva"
    title:       Optional[str]  = None


class VivaStartRequest(BaseModel):
    document_id: UUID
    num_questions: int = Field(default=5, ge=1, le=20)

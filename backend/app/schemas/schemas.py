"""
All Pydantic schemas (request/response validation) in one file.
Split into separate files if the project grows large.
"""
from __future__ import annotations
from datetime import datetime, date, time
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, AliasChoices, field_validator


# ─── Auth ────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email:     EmailStr
    username:  str = Field(min_length=3, max_length=100)
    full_name: Optional[str] = None
    password:  str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        import re
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class LoginRequest(BaseModel):
    email:    EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password:     str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        import re
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v



class InstitutionBriefOut(BaseModel):
    id:       UUID
    name:     str
    type:     str
    location: Optional[str] = None

    model_config = {"from_attributes": True}


class CohortBriefOut(BaseModel):
    id:            UUID
    name:          str
    level_type:    str
    level_value:   str
    academic_year: str
    department:    Optional[str] = None

    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id:                    UUID
    email:                 str
    username:              str
    full_name:             Optional[str]
    created_at:            datetime
    role:                  str = "student"
    must_change_password:  bool = False
    onboarding_completed:  bool = False
    education_level:       Optional[str] = None
    grade_or_year:         Optional[str] = None
    location:              Optional[str] = None
    institution_name_text: Optional[str] = None
    extra_info:            Optional[dict] = None
    institution:           Optional[InstitutionBriefOut] = None
    cohort:                Optional[CohortBriefOut] = None
    join_request_status:   Optional[str] = None

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
    class_date:   date = Field(validation_alias=AliasChoices('class_date', 'date'))
    start_time:   Optional[str] = None   # "HH:MM" — slot identifier for duplicate-subject fix
    end_time:     Optional[str] = None   # informational only
    status:       str  # present | absent | late | excused
    notes:        Optional[str] = None
    marked_at:    Optional[datetime] = None  # client-side timestamp of the click

class AttendanceRecordOut(BaseModel):
    id:               UUID
    subject_id:       UUID
    class_date:       date
    status:           str
    class_start_time: Optional[str] = None
    marked_at:        Optional[datetime] = None
    notes:            Optional[str]
    created_at:       datetime

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
    subject_id:    UUID
    subject_name:  str
    start_time:    str
    end_time:      str
    room:          Optional[str] = None
    is_marked:     bool
    marked_at:     Optional[str] = None   # ISO timestamp set when student marked
    marked_status: Optional[str] = None   # present | absent | late | excused


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


# ─── Phase 5A: Institutions, Cohorts, and Join Requests ───────

class InstitutionCreate(BaseModel):
    name:     str = Field(min_length=1, max_length=255)
    type:     str = Field(pattern="^(school|college)$")
    location: Optional[str] = Field(default=None, max_length=255)


class InstitutionOut(BaseModel):
    id:         UUID
    name:       str
    type:       str
    location:   Optional[str]
    join_code:  str
    is_active:  bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserCreate(BaseModel):
    email:     EmailStr
    username:  str = Field(min_length=3, max_length=100)
    full_name: Optional[str] = None
    password:  str = Field(min_length=8)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        import re
        if len(v.strip()) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        return v


class AdminUserOut(BaseModel):
    id:                   UUID
    email:                str
    username:             str
    full_name:            Optional[str]
    role:                 str
    institution_id:       Optional[UUID]
    must_change_password: bool
    created_at:           datetime

    model_config = {"from_attributes": True}


class AdminUserFullOut(BaseModel):
    """Extended admin output with is_active and institution name."""
    id:                   UUID
    email:                str
    username:             str
    full_name:            Optional[str]
    role:                 str
    institution_id:       Optional[UUID]
    institution_name:     Optional[str] = None
    is_active:            bool
    must_change_password: bool
    created_at:           datetime


class InstitutionWithCountsOut(BaseModel):
    id:             UUID
    name:           str
    type:           str
    location:       Optional[str]
    join_code:      str
    is_active:      bool
    created_at:     datetime
    admin_count:    int = 0
    class_count:    int = 0
    student_count:  int = 0


class ResetPasswordOut(BaseModel):
    temporary_password: str
    message:            str


class CohortCreate(BaseModel):
    name:          str = Field(min_length=1, max_length=100)
    level_type:    str = Field(pattern="^(grade|college_year)$")
    level_value:   str = Field(min_length=1, max_length=50)
    department:    Optional[str] = Field(default=None, max_length=100)
    academic_year: str = Field(min_length=1, max_length=50)


class CohortUpdate(BaseModel):
    name:          Optional[str] = Field(default=None, min_length=1, max_length=100)
    level_type:    Optional[str] = Field(default=None, pattern="^(grade|college_year)$")
    level_value:   Optional[str] = Field(default=None, min_length=1, max_length=50)
    department:    Optional[str] = Field(default=None, max_length=100)
    academic_year: Optional[str] = Field(default=None, min_length=1, max_length=50)
    is_active:     Optional[bool] = None


class CohortOut(BaseModel):
    id:                UUID
    institution_id:    UUID
    name:              str
    level_type:        str
    level_value:       str
    department:        Optional[str]
    academic_year:     str
    is_active:         bool
    join_code:         Optional[str] = None
    join_code_enabled: bool = True
    created_at:        datetime

    model_config = {"from_attributes": True}


class JoinCodeSubmitRequest(BaseModel):
    join_code:           str = Field(min_length=1, max_length=32)
    requested_cohort_id: Optional[UUID] = None


class JoinResponseOut(BaseModel):
    status:  str
    message: str


class JoinRequestDecisionRequest(BaseModel):
    action:    str = Field(pattern="^(approve|reject)$")
    cohort_id: Optional[UUID] = None


class JoinRequestOut(BaseModel):
    id:                    UUID
    user_id:               UUID
    user_email:            Optional[str] = None
    user_username:         Optional[str] = None
    user_full_name:        Optional[str] = None
    institution_id:        UUID
    requested_cohort_id:   Optional[UUID] = None
    requested_cohort_name: Optional[str] = None
    status:                str
    decided_by:            Optional[UUID] = None
    decided_at:            Optional[datetime] = None
    created_at:            datetime

    model_config = {"from_attributes": True}


class UserProfileUpdateRequest(BaseModel):
    education_level:       Optional[str] = Field(default=None, pattern="^(school|college)$")
    grade_or_year:         Optional[str] = Field(default=None, max_length=50)
    location:              Optional[str] = Field(default=None, max_length=255)
    institution_name_text: Optional[str] = Field(default=None, max_length=255)
    extra_info:            Optional[dict] = None


"""
Phase 6C — Class Timetable Pydantic Schemas.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class TimetableSlotSchema(BaseModel):
    day_of_week: int = Field(..., ge=0, le=6, description="0=Monday, 6=Sunday")
    start_time: str = Field(..., description="Start time in HH:MM format (24-hour)")
    end_time: str = Field(..., description="End time in HH:MM format (24-hour)")
    subject: str = Field(..., min_length=1, max_length=100, description="Subject name")
    room: Optional[str] = Field(None, max_length=50, description="Optional room or lab")
    teacher: Optional[str] = Field(None, max_length=100, description="Optional instructor/teacher name")


class SaveDraftRequest(BaseModel):
    entries: List[TimetableSlotSchema] = Field(default_factory=list, description="Timetable class slots")


class PublishRequest(BaseModel):
    force: bool = Field(False, description="Publish anyway even if there are overlapping slots warnings")


class ClassTimetableOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    cohort_id: UUID
    institution_id: UUID
    status: str
    entries: List[Dict[str, Any]]
    published_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime



class TimetableOverviewResponse(BaseModel):
    cohort_id: UUID
    cohort_name: str
    has_draft: bool
    draft: Optional[ClassTimetableOut] = None
    has_published: bool
    published: Optional[ClassTimetableOut] = None


class DraftResponse(BaseModel):
    has_draft: bool
    draft: Optional[ClassTimetableOut] = None
    warnings: List[str] = []


class ExtractTimetableResponse(BaseModel):
    status: str
    extraction_method: str
    message: str
    draft: Optional[ClassTimetableOut] = None
    warnings: List[str] = []
    remaining_attempts: int = 5


class StudentClassTimetableResponse(BaseModel):
    enrolled: bool
    cohort_id: Optional[UUID] = None
    cohort_name: Optional[str] = None
    has_timetable: bool
    published_at: Optional[datetime] = None
    entries: List[Dict[str, Any]] = []

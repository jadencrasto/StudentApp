# Import all models here so Alembic can discover them for migrations
from app.models.user import User
from app.models.assignment import Assignment, TaskType, Priority, AssignmentStatus
from app.models.attendance import Subject, AttendanceRecord, AttendanceStatus
from app.models.activity import Activity
from app.models.document_alert import Document, Alert, AlertType, AlertSeverity, ExtractionStatus
from app.models.timetable import TimetableEntry, TimetableDocument
from app.models.integrations import GoogleToken, CollegeEvent
from app.models.chat import ChatConversation, ChatMessage
from app.models.institution import Institution, Cohort, JoinRequest, generate_join_code
from app.models.class_attendance import ClassAttendanceRecord, ClassAttendanceChangeLog

__all__ = [
    "User",
    "Assignment", "TaskType", "Priority", "AssignmentStatus",
    "Subject", "AttendanceRecord", "AttendanceStatus",
    "Activity",
    "Document", "Alert", "AlertType", "AlertSeverity", "ExtractionStatus",
    "TimetableEntry", "TimetableDocument",
    "GoogleToken", "CollegeEvent",
    "ChatConversation", "ChatMessage",
    "Institution", "Cohort", "JoinRequest", "generate_join_code",
    "ClassAttendanceRecord", "ClassAttendanceChangeLog",
]


from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class ClassroomClient:
    def __init__(self, credentials: Credentials):
        self.service = build("classroom", "v1", credentials=credentials, cache_discovery=False)

    def get_courses(self) -> list[dict[str, Any]]:
        courses: list[dict[str, Any]] = []
        page_token: str | None = None

        while True:
            response = self.service.courses().list(
                pageSize=100,
                courseStates=["ACTIVE", "ARCHIVED"],
                pageToken=page_token,
            ).execute()
            courses.extend(response.get("courses", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return courses

    def _parse_due_date(self, due_date: dict | None, due_time: dict | None) -> datetime | None:
        if not due_date:
            return None

        year = due_date.get("year")
        month = due_date.get("month")
        day = due_date.get("day")

        if not all([year, month, day]):
            return None

        hour = due_time.get("hours", 23) if due_time else 23
        minute = due_time.get("minutes", 59) if due_time else 59

        return datetime(int(year), int(month), int(day), int(hour), int(minute), tzinfo=timezone.utc)

    def _determine_assignment_status(
        self,
        work: dict[str, Any],
        submission: dict[str, Any],
        due_date: datetime | None,
        now: datetime,
    ) -> str:
        submission_state = submission.get("state", "NEW")

        if submission.get("assignedGrade") is not None:
            return "graded"

        if submission_state in ["TURNED_IN", "RETURNED"]:
            return "submitted"

        if due_date:
            if now > due_date and submission_state in ["NEW", "CREATED", "RECLAIMED_BY_STUDENT"]:
                return "missing"
            return "assigned_with_due_date"

        return "assigned_no_due_date"

    def get_all_coursework_with_status(self, course_id: str) -> list[dict[str, Any]]:
        coursework_items: list[dict[str, Any]] = []
        coursework_page_token: str | None = None
        while True:
            coursework_list = self.service.courses().courseWork().list(
                courseId=course_id,
                orderBy="dueDate desc",
                pageSize=100,
                pageToken=coursework_page_token,
            ).execute()
            coursework_items.extend(coursework_list.get("courseWork", []))
            coursework_page_token = coursework_list.get("nextPageToken")
            if not coursework_page_token:
                break

        submissions: list[dict[str, Any]] = []
        submissions_page_token: str | None = None
        while True:
            submissions_list = self.service.courses().courseWork().studentSubmissions().list(
                courseId=course_id,
                courseWorkId="-",
                userId="me",
                pageSize=100,
                pageToken=submissions_page_token,
            ).execute()
            submissions.extend(submissions_list.get("studentSubmissions", []))
            submissions_page_token = submissions_list.get("nextPageToken")
            if not submissions_page_token:
                break

        submission_map = {sub.get("courseWorkId"): sub for sub in submissions if sub.get("courseWorkId")}

        now = datetime.now(timezone.utc)
        result: list[dict[str, Any]] = []
        for work in coursework_items:
            submission = submission_map.get(work.get("id"), {})
            parsed_due_date = self._parse_due_date(work.get("dueDate"), work.get("dueTime"))
            status = self._determine_assignment_status(work, submission, parsed_due_date, now)

            result.append(
                {
                    "google_assignment_id": work.get("id"),
                    "title": work.get("title"),
                    "description": work.get("description", ""),
                    "due_date": parsed_due_date,
                    "max_points": work.get("maxPoints"),
                    "submission_url": work.get("alternateLink"),
                    "submission_state": submission.get("state", "NEW"),
                    "assigned_grade": submission.get("assignedGrade"),
                    "status": status,
                    "is_overdue": bool(parsed_due_date and parsed_due_date < now),
                    "posted_at": work.get("creationTime"),
                    "attachments": self._extract_attachments(work.get("materials")),
                }
            )

        return result

    def get_assignments_by_status(self, course_id: str) -> dict[str, list[dict[str, Any]]]:
        all_assignments = self.get_all_coursework_with_status(course_id)

        grouped: dict[str, list[dict[str, Any]]] = {
            "assigned_with_due_date": [],
            "assigned_no_due_date": [],
            "submitted": [],
            "missing": [],
            "graded": [],
        }

        for assignment in all_assignments:
            status = assignment["status"]
            if status in grouped:
                grouped[status].append(assignment)

        return grouped

    def get_announcements(self, course_id: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            resp = self.service.courses().announcements().list(
                courseId=course_id,
                pageSize=100,
                pageToken=page_token,
            ).execute()
            items.extend(resp.get("announcements", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return items

    # ── Course materials (documents / resources posted by teachers) ──

    @staticmethod
    def _extract_attachments(materials: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        """Normalise Google Classroom 'materials' array into a flat list of attachments."""
        if not materials:
            return []
        attachments: list[dict[str, Any]] = []
        for mat in materials:
            if "driveFile" in mat:
                df = mat["driveFile"].get("driveFile", {})
                attachments.append({
                    "type": "drive",
                    "title": df.get("title", "Untitled"),
                    "url": df.get("alternateLink", ""),
                    "thumbnail": df.get("thumbnailUrl", ""),
                })
            elif "youtubeVideo" in mat:
                yt = mat["youtubeVideo"]
                attachments.append({
                    "type": "youtube",
                    "title": yt.get("title", "YouTube Video"),
                    "url": yt.get("alternateLink", ""),
                    "thumbnail": yt.get("thumbnailUrl", ""),
                })
            elif "link" in mat:
                lk = mat["link"]
                attachments.append({
                    "type": "link",
                    "title": lk.get("title", lk.get("url", "Link")),
                    "url": lk.get("url", ""),
                    "thumbnail": lk.get("thumbnailUrl", ""),
                })
            elif "form" in mat:
                fm = mat["form"]
                attachments.append({
                    "type": "form",
                    "title": fm.get("title", "Google Form"),
                    "url": fm.get("formUrl", ""),
                    "thumbnail": fm.get("thumbnailUrl", ""),
                })
        return attachments

    def get_course_materials(self, course_id: str) -> list[dict[str, Any]]:
        """Fetch courseWorkMaterials (teacher-posted documents/resources)."""
        items: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            try:
                resp = self.service.courses().courseWorkMaterials().list(
                    courseId=course_id,
                    pageSize=100,
                    pageToken=page_token,
                ).execute()
            except Exception:
                # courseWorkMaterials may not be available on older API versions
                break
            items.extend(resp.get("courseWorkMaterial", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        result: list[dict[str, Any]] = []
        for mat in items:
            result.append({
                "id": mat.get("id"),
                "title": mat.get("title", "Untitled Material"),
                "description": mat.get("description", ""),
                "state": mat.get("state", ""),
                "alternate_link": mat.get("alternateLink", ""),
                "creation_time": mat.get("creationTime"),
                "update_time": mat.get("updateTime"),
                "attachments": self._extract_attachments(mat.get("materials")),
            })
        return result

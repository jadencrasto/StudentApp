# SAIS — Smart Academic Intelligence System: Complete Project Report

> **Generated**: 2026-10-12  
> **Purpose**: Full-context handoff document for another AI or developer to understand this codebase from scratch.

---

## 1. OVERVIEW

### What It Does
SAIS (Smart Academic Intelligence System) is an AI-powered academic management platform for **college students**. It centralises assignment tracking, attendance monitoring, timetable management, document AI extraction, college event scraping, an AI chatbot, and Google Classroom integration into a single web application.

### Who Uses It
- **College students** — the sole user role. There is no admin/teacher role; every user is a student who manages their own data.
- A hardcoded **demo user** (`demo@sais.edu` / `password123`) is auto-seeded on startup for development.

### User Roles
- **Single role**: authenticated student. No RBAC, no admin panel, no multi-tenancy. Every database query is scoped by `user_id` so each student only sees their own data.

### Origin
Built as a **hackathon project** ("Automata_26_ApexCode" team). Designed for rapid feature demonstration, not production scale.

---

## 2. TECH STACK

| Layer | Technology | Version / Notes |
|---|---|---|
| **Frontend framework** | React | 18.3.1 |
| **Frontend build** | Vite | 5.2.13 |
| **Frontend styling** | TailwindCSS | 3.4.4 |
| **Routing** | react-router-dom | 6.23.1 |
| **HTTP client** | Axios | 1.7.2 |
| **Animations** | Framer Motion | 12.34.3 |
| **Charts** | Recharts | 2.12.7 |
| **Toasts** | react-hot-toast | 2.4.1 |
| **State management** | Zustand (authStore) + React Context (useAuth) | — |
| **Backend framework** | FastAPI (Python) | ≥0.111.0 |
| **Python version** | 3.11+ | — |
| **ORM** | SQLAlchemy (async) | ≥2.0.30 |
| **Database (dev)** | SQLite + aiosqlite | File: `backend/sais.db` |
| **Database (prod/Docker)** | PostgreSQL 16 (docker-compose) | via asyncpg |
| **Auth** | JWT (python-jose) + PBKDF2-SHA256 (passlib) | HS256 |
| **AI — Gemini** | Google Gemini via `google-genai` SDK | Model: `gemini-2.0-flash` (configurable) |
| **AI — Local LLM** | Ollama (qwen2.5:7b text, llava:7b vision) | via HTTP API on :11434 |
| **NLP** | spaCy (optional, en_core_web_sm) | Falls back to regex if unavailable |
| **OCR** | Tesseract (pytesseract) + PyMuPDF | — |
| **Web scraping** | BeautifulSoup4 + requests | — |
| **Google Classroom** | google-api-python-client + OAuth2 | — |
| **Scheduling** | APScheduler (AsyncIOScheduler) | ≥3.10.4 |
| **Token encryption** | Fernet (cryptography) | For Google OAuth tokens at rest |
| **Containerisation** | Docker + docker-compose 3.9 | Backend only; no frontend container |

---

## 3. FOLDER STRUCTURE

```
Automata_26_ApexCode/
├── ARCHITECTURE.md              # High-level architecture diagram
├── CHANGES.md                   # Changelog of bug fixes
├── README.md                    # Setup instructions, API reference
├── ROADMAP.md                   # Phase guide, API tables, demo checklist
├── TESTING_SUMMARY.md           # Ollama migration testing log
├── docker-compose.yml           # PostgreSQL + backend containers
├── data.db / sais.db            # Root-level DB copies (stale/unused)
│
├── backend/
│   ├── .env / .env.example      # Environment configuration
│   ├── Dockerfile               # Python 3.11-slim + Tesseract
│   ├── requirements.txt         # All Python dependencies
│   ├── schema.sql               # PostgreSQL DDL (tables, views, triggers)
│   ├── sais.db                  # Active SQLite database (dev)
│   ├── populate_assignments.py  # Script to seed sample data
│   ├── test_*.py                # Ad-hoc test scripts (not pytest suite)
│   │
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, router mounts
│   │   ├── config.py            # pydantic-settings (Settings class)
│   │   ├── database.py          # SQLAlchemy engine, session, migrations
│   │   ├── scheduler.py         # APScheduler cron jobs
│   │   │
│   │   ├── models/              # SQLAlchemy ORM models
│   │   │   ├── user.py          # User
│   │   │   ├── assignment.py    # Assignment + enums
│   │   │   ├── attendance.py    # Subject, AttendanceRecord
│   │   │   ├── activity.py      # Activity (with recurrence)
│   │   │   ├── document_alert.py# Document, Alert + enums
│   │   │   ├── timetable.py     # TimetableEntry, TimetableDocument
│   │   │   ├── integrations.py  # GoogleToken, CollegeEvent
│   │   │   └── chat.py          # ChatConversation, ChatMessage
│   │   │
│   │   ├── schemas/
│   │   │   └── schemas.py       # ALL Pydantic request/response schemas
│   │   │
│   │   ├── api/                 # Thin route handlers (controllers)
│   │   │   ├── auth.py          # /auth/* (register, login, me)
│   │   │   ├── assignments.py   # /assignments/* (CRUD + estimate)
│   │   │   ├── attendance.py    # /attendance/* (subjects, mark, summary)
│   │   │   ├── activities.py    # /activities/* (CRUD + conflicts)
│   │   │   ├── documents.py     # /documents/* (upload + extraction)
│   │   │   ├── alerts.py        # /alerts/* (list, refresh, read)
│   │   │   ├── timetable.py     # /timetable/* (upload, entries, reminders)
│   │   │   ├── college_events.py# /colleges, /events, /college-events
│   │   │   ├── classroom.py     # /classroom/* + /auth/google/*
│   │   │   ├── chat.py          # /chat/* (conversations, messages, viva)
│   │   │   ├── dashboard.py     # /dashboard (aggregated stats)
│   │   │   └── extract.py       # /extract (universal file extraction)
│   │   │
│   │   ├── services/            # Business logic layer
│   │   │   ├── auth_service.py
│   │   │   ├── assignment_service.py
│   │   │   ├── attendance_service.py
│   │   │   ├── activity_service.py
│   │   │   ├── alert_service.py
│   │   │   ├── chat_service.py
│   │   │   ├── timetable_service.py
│   │   │   ├── time_estimator.py       # Ollama + heuristic fallback
│   │   │   ├── ollama_client.py        # HTTP wrapper for Ollama API
│   │   │   ├── ollama_timetable_extractor.py  # Vision extraction (large, ~75KB)
│   │   │   ├── gemini_timetable_extractor.py  # Gemini Vision extraction
│   │   │   ├── gemini_event_extractor.py      # Gemini text→events
│   │   │   ├── recurrence_service.py   # Activity recurrence generator
│   │   │   └── scheduler.py           # Service-level scheduler helpers
│   │   │
│   │   ├── core/                # Cross-cutting concerns
│   │   │   ├── security.py      # Password hashing, JWT create/decode
│   │   │   └── dependencies.py  # get_current_user FastAPI dependency
│   │   │
│   │   ├── ai/                  # AI extraction layer
│   │   │   ├── extractor.py     # spaCy + regex NLP extraction
│   │   │   └── ocr.py           # Tesseract OCR dispatcher
│   │   │
│   │   ├── classroom/           # Google Classroom integration
│   │   │   ├── oauth.py         # OAuth2 flow, token exchange/refresh
│   │   │   ├── client.py        # Classroom API wrapper (courses, events)
│   │   │   ├── service.py       # High-level sync/fetch operations
│   │   │   └── security.py      # Fernet encrypt/decrypt for tokens
│   │   │
│   │   └── college_events/      # College website scraping
│   │       ├── colleges.json    # Pre-configured college list (FrCRCE)
│   │       ├── college_loader.py# Load college configs
│   │       ├── sitemap_parser.py# robots.txt / sitemap.xml parser
│   │       ├── content_extractor.py # BS4 HTML/PDF text extraction
│   │       ├── event_parser.py  # Rule-based event parsing
│   │       ├── url_filter.py    # Keyword URL filtering
│   │       ├── database.py      # CollegeEvent DB operations
│   │       └── main.py          # Orchestrator: scrape → parse → store
│   │
│   └── extractor/               # Standalone document extraction module
│       ├── main.py              # Orchestrator (detect → extract → parse)
│       ├── file_detector.py     # File type detection
│       ├── pdf_extractor.py     # pdfplumber-based PDF extraction
│       ├── image_extractor.py   # OCR wrapper
│       ├── docx_extractor.py    # python-docx extraction
│       ├── ocr_engine.py        # Tesseract engine
│       ├── parser.py            # Structured data parser
│       └── cleaner.py           # Text cleaning utilities
│
└── frontend/
    ├── package.json             # Dependencies & scripts
    ├── vite.config.js           # Dev server proxy + aliases
    ├── tailwind.config.js       # Tailwind theme configuration
    ├── index.html               # HTML entry point
    │
    └── src/
        ├── main.jsx             # ReactDOM render + providers
        ├── App.jsx              # Routes, lazy loading, error boundary
        ├── index.css            # Global styles
        │
        ├── api/                 # Axios API client modules
        │   ├── client.js        # Base axios instance (JWT interceptor)
        │   ├── auth.js          # register, login, getMe
        │   ├── assignments.js   # Assignment CRUD
        │   ├── attendance.js    # Attendance API calls
        │   ├── activities.js    # Activities API calls
        │   ├── documents.js     # Document upload/list
        │   ├── timetable.js     # Timetable API calls
        │   ├── alerts.js        # Alert API calls
        │   └── chat.js          # Chat/viva API calls
        │
        ├── lib/
        │   ├── api.js           # DUPLICATE axios instance + all API wrappers
        │   └── utils.js         # Utility helpers
        │
        ├── hooks/
        │   ├── useAuth.jsx      # AuthProvider context + useAuth hook
        │   └── useClassNotifications.js  # Browser notification hook
        │
        ├── store/
        │   └── authStore.js     # Zustand store (PARTIALLY USED alongside useAuth)
        │
        ├── services/
        │   └── notificationService.js  # Browser Notification API wrapper
        │
        ├── pages/
        │   ├── LandingPage.jsx          # Marketing/hero page
        │   ├── LoginPage.jsx            # Login form
        │   ├── RegisterPage.jsx         # Registration form
        │   ├── DashboardPage.jsx        # Main dashboard with stats
        │   ├── AssignmentsPage.jsx       # Assignment CRUD table
        │   ├── AttendancePage.jsx        # Per-subject attendance cards
        │   ├── ActivitiesPage.jsx        # Activity grid with conflicts
        │   ├── TimetableSetupPage.jsx    # Timetable upload + edit
        │   ├── UploadPage.jsx           # Document upload + extraction view
        │   ├── DocumentsPage.jsx        # Document listing (alt page)
        │   ├── ChatBotPage.jsx          # AI chatbot / viva interface
        │   ├── classroom/
        │   │   ├── ClassroomDashboardPage.jsx  # Google Classroom sync
        │   │   └── CourseMaterialsPage.jsx     # Course materials viewer
        │   └── events/
        │       └── CollegeEventsPage.jsx       # College events calendar
        │
        ├── components/
        │   ├── layout/
        │   │   ├── Layout.jsx           # Sidebar + main content shell
        │   │   └── ProtectedRoute.jsx   # Auth guard wrapper
        │   ├── assignments/             # Assignment sub-components
        │   ├── attendance/              # Attendance sub-components
        │   ├── dashboard/               # Dashboard widgets
        │   ├── timetable/               # Timetable sub-components
        │   ├── reminders/               # Notification reminder components
        │   └── ui/                      # Generic UI components
        │
        └── styles/
            └── index.css               # Additional CSS imports
```

---

## 4. FEATURES

### 4.1 User Authentication
**Status: ✅ Complete**  
Register/login with email+password. JWT tokens (HS256, 24h expiry) stored in `localStorage`. Demo user auto-seeded.  
**Files**: `backend/app/api/auth.py`, `backend/app/services/auth_service.py`, `backend/app/core/security.py`, `backend/app/core/dependencies.py`, `frontend/src/hooks/useAuth.jsx`, `frontend/src/pages/LoginPage.jsx`, `frontend/src/pages/RegisterPage.jsx`

### 4.2 Assignment Management (CRUD)
**Status: ✅ Complete**  
Create, list (with status/subject filters), update (status, deadline, priority), and delete assignments. Supports filtering by status and subject.  
**Files**: `backend/app/api/assignments.py`, `backend/app/services/assignment_service.py`, `backend/app/models/assignment.py`, `frontend/src/pages/AssignmentsPage.jsx`

### 4.3 AI Time Estimation
**Status: ⚠️ Partial**  
Estimates completion time for assignments using Ollama LLM (qwen2.5:7b) with heuristic fallback. Standalone estimation works; `ai_metadata` is not always populated on assignment creation via normal CRUD flow.  
**Files**: `backend/app/services/time_estimator.py`, `backend/app/services/ollama_client.py`, `backend/app/api/assignments.py` (endpoints: `/estimate-time`, `/estimate-all`, `/{id}/estimate`)

### 4.4 Attendance Tracking
**Status: ✅ Complete**  
Add subjects, mark attendance (present/absent/late/excused) per class per day per slot, view summary with 75% threshold warnings, project future attendance, recovery plan calculation, attendance history.  
**Files**: `backend/app/api/attendance.py`, `backend/app/services/attendance_service.py`, `backend/app/models/attendance.py`, `frontend/src/pages/AttendancePage.jsx`

### 4.5 Activities & Conflict Detection
**Status: ✅ Complete**  
Create extracurricular activities with optional recurrence (daily, weekly, biweekly, custom). Automatic conflict detection against assignment deadlines. Supports update/delete of entire recurring series.  
**Files**: `backend/app/api/activities.py`, `backend/app/services/activity_service.py`, `backend/app/services/recurrence_service.py`, `backend/app/models/activity.py`, `frontend/src/pages/ActivitiesPage.jsx`

### 4.6 Document Upload & AI Extraction
**Status: ✅ Complete**  
Upload PDF, image (PNG/JPEG), DOCX, or TXT files. Background task performs OCR (Tesseract) → NLP extraction (spaCy/regex) → AI time estimation (Ollama). Automatically creates assignment from extracted data when confidence > 0.2. Supports re-processing and manual "Save as Assignment".  
**Files**: `backend/app/api/documents.py`, `backend/app/ai/extractor.py`, `backend/app/ai/ocr.py`, `backend/extractor/` (standalone module), `frontend/src/pages/UploadPage.jsx`

### 4.7 Smart Timetable (Gemini Vision)
**Status: ✅ Complete**  
Upload timetable image (PNG/JPEG/PDF). Gemini Vision API extracts class schedule. Auto-creates subjects if they don't exist. Supports bulk save of entries. Provides "today's classes" view, morning check-in, unmarked class reminders, and end-of-day summary. Falls back to Tesseract OCR when Gemini quota is exceeded.  
**Files**: `backend/app/api/timetable.py`, `backend/app/services/timetable_service.py`, `backend/app/services/gemini_timetable_extractor.py`, `backend/app/models/timetable.py`, `frontend/src/pages/TimetableSetupPage.jsx`

### 4.8 AI Alerts & Predictions
**Status: ✅ Complete**  
Four rule-based alerts: (1) Overload — ≥3 deadlines in 7 days, (2) Low attendance — < 75%, (3) Deadline soon — due tomorrow, (4) Activity-assignment conflict. Alerts are deduplicated and stored in DB. Generated on-demand via `POST /alerts/refresh` and automatically by daily cron at 8 AM.  
**Files**: `backend/app/api/alerts.py`, `backend/app/services/alert_service.py`, `backend/app/models/document_alert.py` (Alert model), `backend/app/scheduler.py`

### 4.9 College Event Scraping
**Status: ✅ Complete**  
Scrapes college websites via BS4 (up to 20 pages + 5 PDFs), sends combined text to Gemini for structured event extraction. In-memory caching (10 min URL cache, 1 hour Gemini cache). Google Custom Search API fallback. Pre-configured for FrCRCE. Supports dynamic scraping of any URL via `/college-events`.  
**Files**: `backend/app/api/college_events.py`, `backend/app/services/gemini_event_extractor.py`, `backend/app/college_events/` (entire module), `frontend/src/pages/events/CollegeEventsPage.jsx`

### 4.10 Google Classroom Integration
**Status: ⚠️ Partial**  
OAuth2 flow implemented (connect, callback, token refresh, disconnect). Fetches courses, assignments/announcements, and course materials. Auto-syncs classroom assignments into the assignments table with deduplication via `classroom_id`. Credentials updated but **not fully end-to-end tested** (requires Google Cloud Console test user setup).  
**Files**: `backend/app/api/classroom.py`, `backend/app/classroom/oauth.py`, `backend/app/classroom/client.py`, `backend/app/classroom/service.py`, `backend/app/classroom/security.py`, `frontend/src/pages/classroom/ClassroomDashboardPage.jsx`, `frontend/src/pages/classroom/CourseMaterialsPage.jsx`

### 4.11 AI Chatbot (General + Viva)
**Status: ✅ Complete**  
Two modes: (1) **General** — AI study assistant answers academic questions, (2) **Viva** — generates viva-voce questions from an uploaded document and evaluates student answers. Powered by Ollama (qwen2.5:7b). Conversation history persisted in DB (last 20 messages used for context).  
**Files**: `backend/app/api/chat.py`, `backend/app/services/chat_service.py`, `backend/app/models/chat.py`, `frontend/src/pages/ChatBotPage.jsx`, `frontend/src/api/chat.js`

### 4.12 Dashboard
**Status: ✅ Complete**  
Aggregated view showing: pending assignment count, average attendance %, upcoming activity count, unread alert count, next 5 deadlines, and latest 5 unread alerts.  
**Files**: `backend/app/api/dashboard.py`, `frontend/src/pages/DashboardPage.jsx`

### 4.13 Background Scheduler
**Status: ✅ Complete**  
Three APScheduler cron jobs: (1) Daily 8 AM — generate alerts for all users, (2) Midnight — mark overdue assignments, (3) Hourly — sync configured college events.  
**Files**: `backend/app/scheduler.py`

### 4.14 Universal Document Extraction Endpoint
**Status: ✅ Complete**  
Standalone `POST /extract` endpoint (outside `/api/v1`) for ad-hoc file extraction using the `extractor/` module. Accepts any supported file, returns structured data.  
**Files**: `backend/app/api/extract.py`, `backend/extractor/main.py`

---

## 5. DATABASE

The application uses SQLAlchemy ORM models. In development, SQLite (`backend/sais.db`). In Docker, PostgreSQL.  
Schema is also defined in `backend/schema.sql` for PostgreSQL.

### Tables

#### `users`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | auto uuid4 |
| email | VARCHAR(255) | UNIQUE, NOT NULL |
| username | VARCHAR(100) | UNIQUE, NOT NULL |
| full_name | VARCHAR(255) | nullable |
| hashed_password | TEXT | NOT NULL, PBKDF2 |
| is_active | BOOLEAN | default True |
| created_at | DATETIME(tz) | |
| updated_at | DATETIME(tz) | |

#### `assignments`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| title | VARCHAR(500) | NOT NULL |
| subject | VARCHAR(255) | nullable |
| task_type | VARCHAR(50) | enum: assignment/exam/quiz/project/announcement/other |
| description | TEXT | nullable |
| deadline | DATE | nullable, indexed |
| priority | VARCHAR(50) | low/medium/high |
| status | VARCHAR(50) | pending/in_progress/completed/overdue |
| ai_metadata | JSON | nullable (time estimates, etc.) |
| source_document_id | UUID (FK → documents) | SET NULL |
| classroom_id | VARCHAR(255) | Google Classroom dedup key |
| created_at / updated_at | DATETIME(tz) | |

#### `subjects`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| name | VARCHAR(255) | NOT NULL |
| code | VARCHAR(50) | nullable |
| total_classes | INT | default 0 |
| created_at | DATETIME(tz) | |

#### `attendance_records`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| subject_id | UUID (FK → subjects) | CASCADE |
| class_date | DATE | NOT NULL |
| status | ENUM | present/absent/late/excused |
| class_start_time | VARCHAR(10) | "HH:MM" slot identifier |
| marked_at | DATETIME(tz) | client-side timestamp |
| notes | VARCHAR(500) | |
| notification_sent | BOOLEAN | default False |
| notification_sent_at | DATETIME(tz) | |
| created_at | DATETIME(tz) | |
| **Unique** | | (user_id, subject_id, class_date, class_start_time) |

#### `activities`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| title | VARCHAR(500) | NOT NULL |
| category | VARCHAR(100) | |
| activity_date | DATE | nullable |
| start_time / end_time | TIME | |
| location | VARCHAR(255) | |
| description | TEXT | |
| has_conflict | BOOLEAN | set by conflict checker |
| conflict_detail | TEXT | |
| recurrence_type | VARCHAR(50) | none/daily/weekly/biweekly/monthly/custom |
| recurrence_start_date / recurrence_end_date | DATE | |
| custom_interval | INT | |
| custom_interval_unit | VARCHAR(20) | days/weeks/months |
| parent_activity_id | UUID (FK → activities, self-ref) | CASCADE |
| is_recurring_instance | BOOLEAN | |
| created_at / updated_at | DATETIME(tz) | |

#### `documents`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| original_filename | VARCHAR(500) | |
| file_type | VARCHAR(50) | pdf/image/txt/doc |
| file_path | TEXT | disk path |
| raw_text | TEXT | full extracted text |
| extracted_data | JSON | {title, subject, task_type, deadline, confidence, time_estimate} |
| extraction_status | ENUM | pending/processing/done/failed |
| extraction_error | TEXT | |
| created_at | DATETIME(tz) | |

#### `alerts`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| alert_type | ENUM | overload/attendance_low/activity_conflict/deadline_soon/custom |
| severity | ENUM | info/warning/critical |
| title | VARCHAR(500) | |
| message | TEXT | |
| is_read | BOOLEAN | default False |
| expires_at | DATE | |
| related_assignment_id | UUID (FK → assignments) | SET NULL |
| related_activity_id | UUID (FK → activities) | SET NULL |
| related_subject_id | UUID (FK → subjects) | SET NULL |
| created_at | DATETIME(tz) | |

#### `timetable_entries`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| subject_id | UUID (FK → subjects) | CASCADE |
| day_of_week | INT | 0=Mon … 6=Sun |
| start_time / end_time | TIME | |
| room | VARCHAR(120) | |
| notes | TEXT | |
| is_active | BOOLEAN | |
| created_at | DATETIME(tz) | |
| **Unique** | | (user_id, subject_id, day_of_week, start_time) |

#### `timetable_documents`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| file_name / file_path / file_type | VARCHAR | |
| extraction_status | VARCHAR(30) | pending/processing/success/failed |
| extracted_data | JSON | |
| error_message | TEXT | |
| uploaded_at | DATETIME(tz) | |

#### `google_tokens`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | UNIQUE, CASCADE |
| access_token | TEXT | Fernet-encrypted |
| refresh_token | TEXT | Fernet-encrypted, nullable |
| expiry | DATETIME(tz) | |
| scope | TEXT | |
| created_at / updated_at | DATETIME(tz) | |

#### `college_events`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| college | VARCHAR(255) | indexed |
| event_name | VARCHAR(500) | indexed |
| event_type | VARCHAR(120) | indexed |
| event_date | VARCHAR(120) | indexed (string, not Date) |
| semester | VARCHAR(120) | |
| department | VARCHAR(255) | |
| source_url | TEXT | |
| created_at | DATETIME(tz) | |

#### `chat_conversations`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID (FK → users) | CASCADE |
| title | VARCHAR(500) | default "New Chat" |
| mode | VARCHAR(50) | "general" or "viva" |
| document_id | UUID (FK → documents) | SET NULL, for viva mode |
| is_active | BOOLEAN | |
| created_at / updated_at | DATETIME(tz) | |

#### `chat_messages`
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| conversation_id | UUID (FK → chat_conversations) | CASCADE |
| role | VARCHAR(20) | "user" or "assistant" |
| content | TEXT | |
| created_at | DATETIME(tz) | |

### Relationships
- `users` → 1:N → assignments, subjects, activities, documents, alerts, timetable_entries, timetable_documents, chat_conversations
- `users` → 1:1 → google_tokens
- `subjects` → 1:N → attendance_records, timetable_entries
- `activities` → self-referential 1:N → recurring_instances (via parent_activity_id)
- `documents` → 1:N → chat_conversations (for viva mode)
- `chat_conversations` → 1:N → chat_messages

---

## 6. BACKEND API

All endpoints under `/api/v1` unless noted. Auth = requires `Authorization: Bearer <JWT>`.

### Authentication
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/auth/register` | ✗ | Create user account |
| POST | `/api/v1/auth/signup` | ✗ | Alias for register |
| POST | `/api/v1/auth/login` | ✗ | Login → JWT token |
| GET | `/api/v1/auth/me` | ✓ | Current user profile |

### Assignments
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/assignments` | ✓ | Create assignment |
| GET | `/api/v1/assignments` | ✓ | List (filter: ?status=, ?subject=) |
| GET | `/api/v1/assignments/upcoming` | ✓ | Due in next N days (?days=7) |
| GET | `/api/v1/assignments/{id}` | ✓ | Get single |
| PATCH | `/api/v1/assignments/{id}` | ✓ | Partial update |
| DELETE | `/api/v1/assignments/{id}` | ✓ | Delete (204) |
| POST | `/api/v1/assignments/estimate-time` | ✓ | AI time estimation from text |
| POST | `/api/v1/assignments/estimate-all` | ✓ | Backfill estimates for all |
| POST | `/api/v1/assignments/{id}/estimate` | ✓ | Re-estimate single assignment |

### Attendance
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/attendance/subjects` | ✓ | Add subject |
| GET | `/api/v1/attendance/subjects` | ✓ | List subjects |
| PATCH | `/api/v1/attendance/subjects/{id}` | ✓ | Edit subject |
| DELETE | `/api/v1/attendance/subjects/{id}` | ✓ | Delete subject + records |
| POST | `/api/v1/attendance/mark` | ✓ | Mark attendance (upsert) |
| GET | `/api/v1/attendance/summary` | ✓ | Per-subject percentages |
| GET | `/api/v1/attendance/project/{subject_id}` | ✓ | Project future attendance |
| GET | `/api/v1/attendance/history/{subject_id}` | ✓ | Full attendance log |
| GET | `/api/v1/attendance/alerts` | ✓ | Smart attendance alerts |
| GET | `/api/v1/attendance/recovery-plan/{subject_id}` | ✓ | Recovery plan (75%/80%/85%) |

### Activities
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/activities` | ✓ | Create (auto conflict-check, recurrence) |
| GET | `/api/v1/activities` | ✓ | List all (incl. recurring instances) |
| PUT | `/api/v1/activities/{id}` | ✓ | Update (?update_series=true) |
| DELETE | `/api/v1/activities/{id}` | ✓ | Delete (?delete_series=true) |
| POST | `/api/v1/activities/refresh-conflicts` | ✓ | Re-run conflict detection |

### Documents
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/documents/upload` | ✓ | Upload file → background extraction (202) |
| GET | `/api/v1/documents` | ✓ | List uploaded documents |
| GET | `/api/v1/documents/{id}` | ✓ | Get single document |
| POST | `/api/v1/documents/{id}/re-process` | ✓ | Re-trigger extraction |
| POST | `/api/v1/documents/{id}/save-as-assignment` | ✓ | Convert to assignment |

### Alerts
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/alerts` | ✓ | List (?unread_only=true) |
| POST | `/api/v1/alerts/refresh` | ✓ | Run prediction engine |
| PATCH | `/api/v1/alerts/{id}/read` | ✓ | Mark as read |

### Timetable
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/timetable/upload` | ✓ | Upload image → Gemini extraction |
| POST | `/api/v1/timetable/entries/bulk` | ✓ | Bulk save entries |
| GET | `/api/v1/timetable/entries` | ✓ | Get all entries |
| GET | `/api/v1/timetable/today` | ✓ | Today's classes w/ attendance status |
| DELETE | `/api/v1/timetable/entries/{id}` | ✓ | Delete entry |
| GET | `/api/v1/timetable/reminders/morning-checkin` | ✓ | Morning check-in data |
| GET | `/api/v1/timetable/reminders/unmarked` | ✓ | Unmarked past classes |
| GET | `/api/v1/timetable/reminders/end-of-day` | ✓ | End-of-day summary |

### Dashboard
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/dashboard` | ✓ | Aggregated stats + deadlines + alerts |

### Chat / Chatbot
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/api/v1/chat/conversations` | ✓ | Create conversation |
| GET | `/api/v1/chat/conversations` | ✓ | List conversations |
| GET | `/api/v1/chat/conversations/{id}` | ✓ | Get with messages |
| DELETE | `/api/v1/chat/conversations/{id}` | ✓ | Delete |
| POST | `/api/v1/chat/conversations/{id}/messages` | ✓ | Send message → AI reply |
| POST | `/api/v1/chat/viva` | ✓ | Start viva session on document |

### College Events (no auth required for listing)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/colleges` | ✗ | List configured colleges |
| GET | `/api/v1/events` | ✗ | Get events (?college=) |
| GET | `/api/v1/college-events` | ✗ | Dynamic scrape (?college_url=&college_name=) |

### Google Classroom OAuth (root-level, outside /api/v1)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/auth/google/debug-config` | ✗ | Debug OAuth config |
| GET | `/auth/google/connect?token=<JWT>` | via query | Initiate OAuth redirect |
| GET | `/auth/google/callback` | ✗ | OAuth callback (auto) |

### Google Classroom API (under /api/v1)
| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/api/v1/classroom/courses` | ✓ | List courses |
| GET | `/api/v1/classroom/events` | ✓ | Get assignments + announcements |
| GET | `/api/v1/classroom/materials` | ✓ | Get course materials |
| GET | `/api/v1/classroom/sync` | ✓ | Full sync (courses + events + auto-import) |
| GET | `/api/v1/classroom/status` | ✓ | Check connection status |
| DELETE | `/api/v1/classroom/disconnect` | ✓ | Remove stored credentials |

### Other
| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/extract` | ✗ | Universal file extraction (root-level) |
| GET | `/health` | ✗ | Health check |

---

## 7. FRONTEND

### Routes (from `App.jsx`)

| Route | Component | Access |
|---|---|---|
| `/` | `LandingPage` | Public |
| `/login` | `LoginPage` (lazy) | Public |
| `/register` | `RegisterPage` (lazy) | Public |
| `/dashboard` | `DashboardPage` | Protected (inside `Layout`) |
| `/dashboard/assignments` | `AssignmentsPage` | Protected |
| `/dashboard/attendance` | `AttendancePage` | Protected |
| `/dashboard/activities` | `ActivitiesPage` | Protected |
| `/dashboard/timetable` | `TimetableSetupPage` | Protected |
| `/dashboard/events` | `CollegeEventsPage` (lazy) | Protected |
| `/dashboard/classroom` | `ClassroomDashboardPage` (lazy) | Protected |
| `/dashboard/classroom/materials` | `CourseMaterialsPage` (lazy) | Protected |
| `/dashboard/documents` | `UploadPage` (lazy) | Protected |
| `/dashboard/upload` | `UploadPage` (lazy) | Protected (duplicate route) |
| `/dashboard/chat` | `ChatBotPage` (lazy) | Protected |

### Main Components
- **`Layout`** (`components/layout/Layout.jsx`) — Sidebar navigation + main content area. ~7.4KB.
- **`ProtectedRoute`** (`components/layout/ProtectedRoute.jsx`) — Checks `useAuth().isAuthenticated`, shows loading spinner or redirects to `/login`.
- **`ErrorBoundary`** (inline in `App.jsx`) — Catches render errors, resets on route change.

### State Management
- **`useAuth` context** (`hooks/useAuth.jsx`): Primary auth mechanism. React Context wrapping `AuthProvider`. Stores `user` object in state, reads JWT from `localStorage` key `sais_token`, calls `GET /auth/me` on mount.
- **`authStore` (Zustand)** (`store/authStore.js`): Secondary/duplicate auth store. Used by some components but not the main auth flow. Creates duplication with `useAuth`.
- **No global state for domain data** — each page fetches its own data via API calls on mount.

### API Communication
- **Two separate axios instances exist** (duplication):
  1. `api/client.js` — base URL `http://127.0.0.1:8000/api/v1`, used by `api/*.js` modules
  2. `lib/api.js` — base URL from `VITE_API_URL` env var or same default, used by `authStore` and some pages
- Both inject JWT via `Authorization: Bearer` header from `localStorage`
- Both redirect to `/login` on 401 (except for `/classroom/` routes)
- Vite dev server proxies `/api`, `/auth/google`, `/events`, `/colleges`, `/extract`, `/health` to `:8000`

---

## 8. AUTH & SECURITY

### How Login Works
1. User submits email + password to `POST /api/v1/auth/login`
2. Backend verifies password hash (PBKDF2-SHA256) → generates JWT
3. JWT payload: `{"sub": "<user_uuid>", "exp": <timestamp>, "iat": <timestamp>}`
4. Signed with `SECRET_KEY` using HS256
5. Frontend stores token in `localStorage` under key `sais_token`
6. Every request adds `Authorization: Bearer <token>` via axios interceptor
7. Backend `get_current_user` dependency decodes token → fetches user from DB

### User Roles
- **Single role** — no RBAC. Every authenticated user is a "student."
- `is_active` boolean on User model can disable accounts, but no admin UI to toggle it.

### Token Storage
- JWT stored in **`localStorage`** (not httpOnly cookies) — vulnerable to XSS
- Google OAuth tokens stored in DB, **Fernet-encrypted** at rest using `TOKEN_ENCRYPTION_KEY` (falls back to SHA256 of `SECRET_KEY`)

### Security Issues

| Issue | Severity | Detail |
|---|---|---|
| **JWT in localStorage** | Medium | Vulnerable to XSS. Should use httpOnly cookies. |
| **No CSRF protection** | Low | Not needed with Bearer tokens, but would be needed if switching to cookies. |
| **Hardcoded demo user** | Low | `demo@sais.edu` / `password123` seeded on every startup. Fine for dev, dangerous in prod. |
| **No password strength validation** | Low | Only `min_length=8` on Pydantic schema. No complexity requirements. |
| **No rate limiting** | High | No rate limits on login, register, or any endpoint. Brute-force attacks possible. |
| **No input sanitization for XSS** | Medium | User-provided text (titles, descriptions, chat messages) rendered in frontend without sanitization. React's JSX auto-escapes, but `dangerouslySetInnerHTML` or Markdown rendering could be exploited. |
| **CORS allows all methods/headers** | Medium | `allow_methods=["*"]`, `allow_headers=["*"]`. Should be restricted in production. |
| **Hardcoded backend URL in frontend** | Low | `http://127.0.0.1:8000` is hardcoded in `api/client.js`. `lib/api.js` uses env var but with the same hardcoded fallback. |
| **No file upload size validation in backend** | Medium | `MAX_UPLOAD_SIZE_MB` is configured but never actually enforced in the upload endpoints. |
| **`/extract` endpoint has no auth** | Medium | Anyone can extract documents without authentication. |
| **College events endpoints have no auth** | Low | By design (public data), but could be abused for scraping other sites. |
| **`/auth/google/connect` uses JWT in query string** | Low | Token passed as `?token=<jwt>` in URL, which could be logged in server access logs. |

---

## 9. AI / GEMINI USAGE

### Where Gemini Is Called

| Use Case | File | Model | Prompt Location |
|---|---|---|---|
| **Timetable extraction from images** | `services/gemini_timetable_extractor.py` | `settings.GEMINI_MODEL` (default: `gemini-2.0-flash`) | `EXTRACTION_PROMPT` constant in same file (~60 lines, asks for JSON with subject, day, times, room) |
| **College event extraction from scraped text** | `services/gemini_event_extractor.py` | Same model | `EXTRACTION_PROMPT` constant (~40 lines, asks for JSON array of events with title, type, date, source_url) |

### Where Ollama Is Called

| Use Case | File | Model | Prompt |
|---|---|---|---|
| **Assignment time estimation** | `services/time_estimator.py` → `services/ollama_client.py` | `qwen2.5:7b` (configurable) | Inline prompt asking for JSON with estimated_minutes, complexity, etc. |
| **Chatbot (general Q&A)** | `services/chat_service.py` → `services/ollama_client.py` | `qwen2.5:7b` | System prompt: "You are SAIS — a friendly AI study assistant..." + conversation history |
| **Chatbot (viva mode)** | `services/chat_service.py` → `services/ollama_client.py` | `qwen2.5:7b` | Viva system prompt + document content + generated questions |

### Error / Quota Handling

- **Gemini timetable extractor**: Detects 429/quota errors via string matching. Extracts `retry_delay` from error message. Retries once after delay. Falls back to Tesseract OCR + regex parsing if retry fails.
- **Gemini event extractor**: Catches all exceptions, returns `[]` so college events endpoint can fall back to Google Custom Search API.
- **Ollama client**: 5-second connect timeout, 120-second read timeout. Returns empty string on any error. Heuristic estimator is always available as fallback.
- **No structured error reporting to the user** when AI services are down — the system silently degrades.

---

## 10. EXTERNAL INTEGRATIONS

### Google Classroom
- **OAuth 2.0** with offline access (refresh tokens)
- **Scopes**: courses.readonly, coursework.me.readonly, student-submissions.me.readonly, announcements.readonly, courseworkmaterials.readonly
- **Setup**: Requires `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, redirect URI registered in Google Cloud Console
- **Token storage**: Fernet-encrypted in `google_tokens` table
- **Auto-refresh**: Expired tokens are refreshed using `google.auth.transport.requests.Request`
- **Files**: `backend/app/classroom/` directory

### Google Gemini AI
- **SDK**: `google-genai` (new client library)
- **Setup**: Requires `GEMINI_API_KEY` from Google AI Studio
- **Used for**: Timetable image extraction (Vision), college event text parsing
- **Files**: `backend/app/services/gemini_timetable_extractor.py`, `backend/app/services/gemini_event_extractor.py`

### Ollama (Local LLM)
- **Protocol**: HTTP REST API at `OLLAMA_BASE_URL` (default: `http://localhost:11434`)
- **Models**: `qwen2.5:7b` (text), `llava:7b` (vision, referenced but not actively used in current code paths)
- **Setup**: Install Ollama, pull models: `ollama pull qwen2.5:7b`
- **Files**: `backend/app/services/ollama_client.py`

### Google Custom Search API
- **Fallback** for college event scraping when BS4 + Gemini yields no results
- **Setup**: Requires `GOOGLE_SEARCH_API_KEY` + `GOOGLE_SEARCH_CX` (free 100 queries/day)
- **Files**: `backend/app/api/college_events.py` (`_google_search_fallback` function)

### Tesseract OCR
- **System dependency** — must be installed on the OS
- **Setup**: Set `TESSERACT_CMD` in `.env` to the binary path
- **Files**: `backend/app/ai/ocr.py`, used as fallback in timetable extraction

---

## 11. CONFIG & DEPLOYMENT

### Environment Variables (names only)

**Required:**
| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLAlchemy connection string |
| `SECRET_KEY` | JWT signing key (≥32 chars) |

**Optional:**
| Variable | Purpose |
|---|---|
| `ALGORITHM` | JWT algorithm (default: HS256) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry (default: 1440 = 24h) |
| `APP_NAME` | Application name (default: SAIS) |
| `DEBUG` | Debug mode (default: True) |
| `ALLOWED_ORIGINS` | CORS origins, comma-separated |
| `TESSERACT_CMD` | Path to Tesseract binary |
| `GEMINI_API_KEY` | Google Gemini API key |
| `GEMINI_MODEL` | Gemini model name |
| `GOOGLE_APPLICATION_CREDENTIALS` | Google service account (unused) |
| `GOOGLE_SEARCH_API_KEY` | Custom Search API key |
| `GOOGLE_SEARCH_CX` | Custom Search Engine ID |
| `OLLAMA_BASE_URL` | Ollama API URL |
| `OLLAMA_MODEL` | Ollama model name |
| `GOOGLE_CLIENT_ID` | OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REDIRECT_URI` | OAuth callback URL |
| `TOKEN_ENCRYPTION_KEY` | Fernet key for token encryption |
| `UPLOAD_DIR` | File upload directory |
| `MAX_UPLOAD_SIZE_MB` | Max upload size |

### How to Run Locally

**Backend:**
```bash
cd backend
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
cp .env.example .env           # Edit with your values
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

**Required external services:**
- Tesseract OCR installed
- Ollama running with `qwen2.5:7b` pulled (for chatbot/time estimation)
- Gemini API key (for timetable vision + college events)

### Docker
- `docker-compose.yml` defines PostgreSQL 16 + backend container
- **No frontend container** — must be run separately with `npm run dev`
- Docker compose references `backend/Dockerfile` which installs Tesseract and spaCy model
- **PostgreSQL credentials are hardcoded** in docker-compose.yml (`postgres:password`)

---

## 12. CODE QUALITY

### Tests
- **No pytest test suite** in a standard location
- Multiple ad-hoc test scripts in `backend/`: `test_accuracy.py`, `test_batch_extraction.py`, `test_comprehensive.py`, `test_debug_ocr.py`, `test_direct_extract.py`, `test_image.py`, `test_ollama_e2e.py`, `test_ollama_time_estimation.py`, `test_real_timetable.py`, `test_specific_image.py`
- These are standalone scripts, not part of a test framework
- `backend/tests/` directory exists but only contains a `samples/` subdirectory (test data)
- **No frontend tests** at all — no test runner configured
- **Test coverage**: Effectively 0% automated coverage

### Error Handling
- Backend services generally catch exceptions and return appropriate HTTP status codes
- Document extraction background task has try/except with error status saved to DB
- Ollama client silently returns empty string on failure — no error propagation
- Gemini extractors have quota detection and fallback chains
- Several bare `except Exception: pass` blocks that silently swallow errors (e.g., database migration helpers)

### Logging
- Python `logging` module used in several services (timetable, college events, scheduler, chat, Ollama)
- Many services use `print()` instead of `logging` (e.g., `main.py` demo user seed, document extraction failures)
- No structured logging format configured
- No log aggregation or rotation

### Duplicated Code
- **Two separate axios instances**: `frontend/src/api/client.js` and `frontend/src/lib/api.js` — identical functionality, both used by different parts of the codebase
- **Two auth systems**: `useAuth` context provider AND `authStore` Zustand store — both manage the same state
- **Two timetable extractors**: `gemini_timetable_extractor.py` (~494 lines) and `ollama_timetable_extractor.py` (~75KB!) — the Ollama version is enormous and appears to be a superset
- **Two document extraction paths**: `app/ai/extractor.py` + `app/ai/ocr.py` AND `extractor/` standalone module — overlapping functionality

### TODO/FIXME Comments
- Only one found: a hardcoded path in `test_ollama_time_estimation.py` referencing `D:\HACKATHON\JACE FAMILY\sais-complete10\...` — developer-specific path leaked into code

### Unused / Debug Files
- `backend/debug_bbox.py`, `debug_ocr_raw.py` — debug scripts
- `backend/debug_light_clean.png`, `debug_light_cv2.png` — debug images
- `backend/debug_output.txt`, `debug_output_all.txt`, `diagnostic_out.txt`, `diagnostic_results.json` — debug output files
- `backend/test_result.txt`, `test_result_v2.txt`, `test_result_v3.txt` — test output files
- `backend/test_timetable_grid.png` — test image
- Root-level `data.db` and `sais.db` — stale database copies outside backend directory
- `frontend/err.log` — error log committed to repo
- `frontend/dist/` — built output committed to repo
- `backend/populate_assignments.py` — 27KB data seeding script

---

## 13. KNOWN PROBLEMS

### Bugs
1. **Assignment `ai_metadata` not populated on normal creation** — When creating assignments via `POST /assignments`, the time estimator is never called. Only the `/estimate-time` and `/estimate-all` endpoints trigger it. The `TESTING_SUMMARY.md` explicitly notes this as a known issue.

2. **Duplicate auth systems** — `useAuth` context and `authStore` Zustand store both manage authentication state independently. Components that use one don't update the other, potentially causing inconsistent state.

3. **Duplicate axios clients** — `api/client.js` and `lib/api.js` are separate axios instances. If one is updated (e.g., base URL change), the other won't reflect it.

4. **`/extract` endpoint is unauthenticated** — Anyone can upload files for extraction without login.

5. **Hardcoded developer path** — `test_ollama_time_estimation.py` contains a hardcoded path `D:\HACKATHON\JACE FAMILY\sais-complete10\...`.

6. **`MAX_UPLOAD_SIZE_MB` not enforced** — The config value exists but no middleware or endpoint logic checks file size before accepting uploads.

7. **`ollama_timetable_extractor.py` is 75KB** — Extremely large single file (likely contains duplicated/generated code). Not currently used in main code paths (Gemini extractor is used instead via `timetable_service.py`).

8. **Activity date nullable but `ActivityOut` requires it** — The model has `activity_date: Mapped[date | None]` but the Pydantic `ActivityOut` schema has `activity_date: date` (non-optional), which would fail serialisation for recurring activities created without an explicit date.

### Hacks / Shortcuts
1. **SQLite schema migrations via try/except** — `database.py` has multiple `ensure_*_column()` functions that ALTER TABLE and silently catch exceptions. This works but is fragile and doesn't handle column type changes.

2. **Demo user seeded on every startup** — The `_seed_demo_user()` function runs on every boot. Not harmful but not a proper seed/migration.

3. **In-memory caching in college events** — Using global dicts (`_url_cache`, `_gemini_cache`) with TTL. No cache invalidation mechanism, not thread-safe in multi-worker deployments.

4. **Blocking sync scraping in async endpoint** — `_scrape_url_sync()` is a synchronous function run via `asyncio.to_thread()` with a 300-second timeout. This works but ties up a thread pool thread.

---

## 14. PRODUCTION GAPS

### Critical (Must Fix)

1. **No rate limiting** — Login, registration, and all API endpoints have zero rate limiting. Easy brute-force target.

2. **No HTTPS** — Everything runs on HTTP. JWT tokens transmitted in plaintext over the wire.

3. **JWT in localStorage** — Vulnerable to XSS. Should switch to httpOnly secure cookies.

4. **No input validation on file upload size** — Could exhaust disk space or memory.

5. **No database migrations** — Uses `create_all()` in debug mode and manual `ALTER TABLE` with try/except. No Alembic migration chain configured (despite being in requirements.txt).

6. **Hardcoded demo credentials** — `demo@sais.edu` / `password123` exists in every deployment.

7. **Hardcoded Docker secrets** — `docker-compose.yml` has plaintext `POSTGRES_PASSWORD: password` and `SECRET_KEY: change-me-in-production-super-secret-key-32chars`.

8. **No automated tests** — Zero CI/CD-compatible test coverage. No unit tests, no integration tests, no E2E tests.

### High Priority

9. **No email verification** — Users can register with any email without verification.

10. **No password reset flow** — No forgot-password / reset-password functionality.

11. **No monitoring / health checks** — Only a basic `/health` endpoint. No metrics, no alerting, no APM.

12. **No structured logging** — Mix of `print()` and `logging` with no format/level configuration.

13. **SQLite in production** — The default `DATABASE_URL` uses SQLite which doesn't support concurrent writes well. The `StaticPool` workaround limits to a single connection.

14. **Frontend has no error reporting** — No Sentry, no error tracking. Errors silently fail in the UI.

15. **No frontend build for production** — `dist/` is committed but there's no deployment pipeline. No CDN, no static file serving config.

16. **No Dockerfile for frontend** — Only backend has a Dockerfile. Frontend must be built and served separately.

### Medium Priority

17. **No pagination** — All list endpoints return all records. Will not scale.

18. **No data export** — Users cannot export their data.

19. **No account deletion** — No GDPR compliance / right-to-be-forgotten.

20. **No multi-factor authentication** — Single-factor password only.

21. **No content security policy headers** — No CSP, HSTS, X-Frame-Options headers.

22. **No backup strategy** — SQLite file in the working directory with no backup mechanism.

23. **Google Classroom requires test-mode manual setup** — OAuth app is in "Testing" mode requiring manual test user addition in Google Cloud Console. Full deployment requires Google verification.

24. **Ollama requires local GPU** — Chat and time estimation depend on Ollama running locally. No cloud fallback if Ollama is unavailable (returns empty responses silently).

25. **No WebSocket for chat** — Chat uses request-response pattern. No streaming, no typing indicators, no real-time updates.

26. **No internationalisation** — English only, no i18n framework.

27. **No accessibility** — No ARIA labels, no keyboard navigation testing, no screen reader support verified.

28. **Stale/debug files committed** — Multiple debug outputs, test results, and database copies in the repo.

---

*End of Report*

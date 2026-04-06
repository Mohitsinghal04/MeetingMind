# MeetingMind 🧠

**AI-Powered Meeting Assistant with Multi-Agent Architecture**

MeetingMind is an intelligent productivity assistant that processes meeting transcripts to extract action items, schedule events, and manage tasks. Built with Google Agent Development Kit (ADK) and Model Context Protocol (MCP) integration.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Google ADK](https://img.shields.io/badge/Google%20ADK-1.14.0-green.svg)](https://cloud.google.com/ai/agent-developer-kit)
[![Tests](https://img.shields.io/badge/Tests-15%20Passed-brightgreen.svg)](tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)


## ✨ Features

- **📝 Smart Meeting Processing** - Extract action items, priorities, and deadlines from transcripts
- **📅 Intelligent Scheduling** - Create calendar events with natural language date parsing (IST timezone)
- **🔍 Fuzzy Search** - Find tasks and meetings with partial keyword matching
- **💾 Duplicate Prevention** - Automatically detects and skips duplicate tasks
- **🤖 9 Specialized Agents** - Root orchestrator + 8 sub-agents for complex workflows
- **🔌 MCP Integration** - 3 MCP servers with 10 tools (Tasks, Calendar, Notes)
- **🗄️ PostgreSQL Backend** - Connection pooling, indexed queries, full CRUD operations
- **🧪 Test Coverage** - 15 automated unit tests with pytest


## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- Google Cloud account with billing enabled
- PostgreSQL database
- gcloud CLI installed

### Option A: Automated Setup (Recommended)

For a complete automated setup from scratch, use the fresh start script:

```bash
bash fresh_start.sh
```

This will:
1. Clean up any existing GCP resources
2. Set up GCP infrastructure (Cloud SQL, Service Account, etc.)
3. Initialize database schema
4. Deploy to Cloud Run

**Total time:** ~15-20 minutes (mostly Cloud SQL creation)

---

### Option B: Manual Setup

### 1. Clone Repository

```bash
git clone https://github.com/yourusername/meetingmind.git
cd meetingmind
```

### 2. Set Up Google Cloud

**IMPORTANT:** Before running the setup script, edit `setup_gcp.sh` and change the default password on line 14:

```bash
export DB_PASSWORD="temp-pwd"    # ← CHANGE THIS to a secure password
```

Then run the setup:

```bash
# Run GCP setup script
bash setup_gcp.sh

# Enable required APIs (Calendar, Cloud Run, etc.)
bash enable_calendar_api.sh
```

### 3. Configure Environment

Create a `.env` file with your configuration:

```bash
# Google Cloud
PROJECT_ID=your-gcp-project-id
REGION=us-central1

# Database
DB_HOST=your-postgresql-host
DB_NAME=meetingmind
DB_USER=meetingmind_user
DB_PASSWORD=your-secure-password
DB_PORT=5432

# Calendar
CALENDAR_ID=your-email@gmail.com

# Settings
TIMEZONE=Asia/Kolkata
MODEL=gemini-2.5-flash
```

### 4. Initialize Database

```bash
# Install dependencies
pip install -r requirements.txt

# Create database schema
python init_db.py
```

### 5. Test Locally (Optional)

```bash
# Run unit tests
pytest tests/ -v

# Test database connection
bash test_db_connection.sh
```

### 6. Deploy to Cloud Run

```bash
bash deploy.sh
```

The deployment script will:
- Build Docker image
- Push to Google Artifact Registry
- Deploy to Cloud Run
- Display the service URL


## 📖 Usage

### Process a Meeting Transcript

Paste any meeting transcript (500+ characters):

```
User: [Pastes Q3 Planning Meeting transcript]

MeetingMind:
✅ Meeting Processed Successfully

📋 Summary: Q3 Planning Discussion covering mobile app launch...
💼 Action Items: 5 tasks extracted (2 duplicates skipped)
📅 Calendar Events: 2 meetings scheduled
```

### Query Tasks

```
User: "list all meetings"
MeetingMind: Shows 12 meetings with dates

User: "show tasks from Q3 Product meeting"
MeetingMind: [5 tasks with priorities and owners]

User: "what high priority tasks are pending?"
MeetingMind: [Filtered task list]
```

### Schedule Meetings

```
User: "schedule demo on Tuesday at 2pm with sarah@example.com"

MeetingMind:
📅 Calendar Event Ready

Demo - Tuesday, April 7, 2026 at 2:00 PM IST
Attendees: sarah@example.com

[📅 Click here to add to Google Calendar](url) _(Ctrl+Click to open in new tab)_
```

Supports natural language dates:
- "tomorrow", "next Monday"
- "April 10th", "Tuesday"
- Smart IST timezone conversion

### Execute Commands

```
User: "mark API implementation as done"
MeetingMind: ✅ Task marked as Done

User: "set deployment task to in progress"
MeetingMind: ✅ Status updated to In Progress


## 🏗️ Architecture

### Multi-Agent System (9 Agents)

```
User Input → Root Agent (Intent Router)
    ↓
┌─────────────────────────────────────────────────┐
│  TRANSCRIPT Pipeline (Sequential + Parallel)    │
│                                                  │
│  Sequential:                                    │
│  1. Summary Agent     → Extract meeting summary │
│  2. Meeting Save      → Save to PostgreSQL      │
│  3. Action Items      → Identify tasks          │
│  4. Scheduler         → Create calendar events  │
│  5. Duplicate Check   → Save tasks (skip dupes) │
│  6. Briefing          → Format final output     │
│                                                  │
│  Parallel (Background):                         │
│  • Notes Agent        → Save searchable notes   │
│  • Memory Agent       → Store key decisions     │
└─────────────────────────────────────────────────┘
    ↓
Query Agent / Execution Agent (Follow-up commands)
```

**Performance:** ~8-10 seconds per transcript

### MCP Integration

| MCP Server | Tools | Purpose |
|------------|-------|---------|
| **Tasks MCP** | `save_tasks`, `update_task`, `check_duplicates` | Task management |
| **Calendar MCP** | `create_event`, `list_slots` | Google Calendar integration |
| **Notes MCP** | `save_notes`, `search_notes` | Knowledge base |

### Database Schema

```sql
meetings (id, transcript, summary, session_id, created_at)
tasks (id, meeting_id, task_name, owner, deadline, priority, status)
notes (id, meeting_id, title, content, tags, created_at)
memory (id, key, value, context, created_at)
```

**Features:**
- Connection pooling (1-10 connections)
- 6 indexes for optimized queries
- Duplicate detection with fuzzy matching
- Transaction safety


## 🧪 Testing

### Run All Tests

```bash
pytest tests/ -v --cov=tools
```

### Test Coverage

- `save_tasks()` - Duplicate prevention
- `check_duplicate_tasks()` - Fuzzy matching
- `save_meeting()` - Meeting ID generation
- `list_my_tasks()` - Task filtering
- `find_meeting_by_title()` - Meeting search
- `parse_relative_date()` - Date calculation

**Result:** 15 tests passed in 0.02s


## 📁 Project Structure

```
meetingmind/
├── agent.py                    # Main agent orchestration (9 agents)
├── tools/
│   ├── db_tools.py            # PostgreSQL operations
│   ├── task_tools.py          # Task management
│   ├── calendar_tools.py      # Google Calendar integration
│   ├── notes_tools.py         # Notes management
│   ├── date_helpers.py        # Date parsing utilities
│   ├── state_tools.py         # Session state
│   ├── metrics.py             # Performance tracking
│   ├── mcp_wrapper.py         # MCP abstraction layer
│   └── mcp_servers/           # MCP server implementations
├── tests/
│   ├── conftest.py            # Pytest fixtures
│   ├── test_db_tools.py       # Database tests
│   └── test_task_tools.py     # Task management tests
├── init_db.py                 # Database initialization
├── clear_tasks.py             # Clear database for testing
├── mcp_config.json            # MCP configuration
├── requirements.txt           # Python dependencies
├── fresh_start.sh             # Automated complete setup (recommended)
├── deploy.sh                  # Cloud Run deployment
├── setup_gcp.sh               # GCP project setup (CHANGE PASSWORD!)
├── enable_calendar_api.sh     # Enable Calendar API
├── test_db_connection.sh      # Test database connection
├── .env                       # Environment variables
├── README.md                  # This file
├── CLAUDE.md                  # Quick start guide
└── SAMPLE_TRANSCRIPT.md       # Demo transcripts
```


## 🔧 Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `PROJECT_ID` | GCP project ID | `my-project-123` |
| `DB_HOST` | PostgreSQL host | `10.1.2.3` |
| `DB_NAME` | Database name | `meetingmind` |
| `DB_USER` | Database user | `meetingmind_user` |
| `DB_PASSWORD` | Database password | `secure-password` |
| `CALENDAR_ID` | Google Calendar email | `user@gmail.com` |
| `TIMEZONE` | Default timezone | `Asia/Kolkata` |
| `MODEL` | Gemini model | `gemini-2.5-flash` |

### MCP Servers

Configured in `mcp_config.json`:

```json
{
  "tasks_mcp": {
    "command": "python",
    "args": ["tools/mcp_servers/tasks_mcp_server.py"]
  },
  "calendar_mcp": {
    "command": "python",
    "args": ["tools/mcp_servers/calendar_mcp_server.py"]
  },
  "notes_mcp": {
    "command": "python",
    "args": ["tools/mcp_servers/notes_mcp_server.py"]
  }
}
```


## 🚢 Deployment

### Cloud Run Deployment

```bash
# Deploy with default settings
bash deploy.sh

# Check deployment status
gcloud run services describe meetingmind --region=us-central1

# View logs
gcloud logging read "resource.type=cloud_run_revision" --limit=50
```

### Environment Configuration

The deployment script automatically:
- Sets environment variables from `.env`
- Configures memory (2GB) and CPU (2 vCPU)
- Sets max instances (10) and concurrency (80)
- Tags service for billing tracking


## 📊 Performance

| Operation | Average Time |
|-----------|-------------|
| Meeting save | 0.14s |
| Task save (batch) | 0.09s |
| Duplicate check | 0.02s |
| Calendar event | 0.32s |
| **Full transcript** | **8.5s** |

Tested with: 1,247 character transcript, 5 tasks, 2 events


## 🗄️ Database Management

### Clear Database for Testing

If you need to clean up your database (remove all tasks and meetings):

```bash
python clear_tasks.py
```

This script will:
- Delete all tasks from the database
- Delete all meetings from the database
- Preserve the database schema (tables remain)

**Use cases:**
- Testing with fresh data
- Removing test entries before production
- Clearing duplicate data after multiple test runs

**Warning:** This action cannot be undone. All meeting transcripts and tasks will be permanently deleted.

### Database Backup (Recommended)

Before clearing the database, create a backup:

```bash
# Backup all data
pg_dump -h $DB_HOST -U $DB_USER -d $DB_NAME > backup_$(date +%Y%m%d).sql

# Restore from backup if needed
psql -h $DB_HOST -U $DB_USER -d $DB_NAME < backup_20260406.sql
```


## 🐛 Troubleshooting

### Common Issues

**1. Database connection fails**
```bash
# Test connection
bash test_db_connection.sh

# Check if Cloud SQL proxy is running
ps aux | grep cloud_sql_proxy
```

**2. Calendar API not enabled**
```bash
bash enable_calendar_api.sh
```

**3. Deployment fails**
```bash
# Check gcloud authentication
gcloud auth list

# Verify project ID
gcloud config get-value project
```

**4. Missing dependencies**
```bash
pip install -r requirements.txt
```


## 🤝 Contributing

This project was built for the Gen AI Academy APAC - Multi-Agent Systems with MCP Hackathon 2026.

To contribute:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request


Built for **Gen AI Academy APAC — Multi-Agent Systems with MCP Hackathon 2026**


## 🙏 Acknowledgments

- Google Agent Development Kit (ADK) team
- Anthropic's Model Context Protocol (MCP)
- Gen AI Academy APAC Hackathon organizers
- PostgreSQL and Google Cloud teams


## 📚 Additional Documentation

- **[SAMPLE_TRANSCRIPT.md](SAMPLE_TRANSCRIPT.md)** - Demo meeting transcripts for testing


**Built with ❤️ using Google ADK, MCP, PostgreSQL, and pytz**

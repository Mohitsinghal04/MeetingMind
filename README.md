# ⚡ Catalyst
### *Raw meetings. Structured action.*

> **Google Gen AI Academy APAC — Multi-Agent Systems with MCP Competition**  
> Built by Mohit Singhal and Neha Lohia (Cold Start team) · Deployed on Google Cloud Run

## What It Does

Catalyst turns any meeting transcript into structured action in under 20 seconds.

Paste a transcript → **8 specialized AI agents** extract tasks, assign priorities, schedule calendar events, save searchable notes, publish a Google Doc, and grade their own output — all automatically.

**Live demo:** https://meetingmind-1046074361007.us-central1.run.app

## Architecture — Why It's Different

Most LLM apps call one model once. Catalyst runs a **coordinated multi-agent pipeline** where each agent owns exactly one responsibility.

```
User Input
    │
    ▼
Root Agent (Intent Router)
    │
    ├─► TRANSCRIPT ──► SequentialAgent: transcript_pipeline
    │                       │
    │                  Stage 1: analysis_agent
    │                       │  Gemini 2.5 Flash · summarise + extract tasks + save meeting
    │                       ▼
    │                  Stage 2: save_and_schedule_agent
    │                       │  Gemini 2.5 Flash · write tasks to DB + Google Calendar event
    │                       ▼
    │                  Stage 3: ParallelAgent (two models, separate quota pools)
    │                       ├── notes_agent          [gemini-2.5-flash]
    │                       │   save note → assemble briefing (~3s)
    │                       └── evaluation_agent     [gemini-2.5-flash-lite]
    │                           LLM-as-Judge: grade quality on 4 dimensions (~5s)
    │
    ├─► QUESTION ────► query_agent
    │                  pgvector semantic search · analytics · knowledge base
    │
    ├─► COMMAND ─────► execution_agent
    │                  mark done · update status · schedule meetings (memory-aware)
    │
    └─► REMEMBER ────► store_memory_direct (inline, no sub-agent)
                       Global persistence across all browser sessions
```

## Technical Highlights

### 8 Agents — Clear Separation of Concerns
| Agent | Responsibility | Model |
|---|---|---|
| `root_agent` | Intent router — classifies input, delegates | gemini-2.5-flash |
| `analysis_agent` | Summarise transcript, extract tasks, save meeting to DB | gemini-2.5-flash |
| `save_and_schedule_agent` | Persist tasks to PostgreSQL, create Calendar events | gemini-2.5-flash |
| `notes_agent` | Save meeting note, assemble final briefing (Python tools, no extra LLM) | gemini-2.5-flash |
| `evaluation_agent` | LLM-as-Judge: grade quality on 4 dimensions, save score | **gemini-2.5-flash-lite** |
| `query_agent` | Semantic search, analytics, overdue tracking | gemini-2.5-flash |
| `execution_agent` | Mark done, update status, schedule with memory preferences | gemini-2.5-flash |
| `transcript_pipeline` | SequentialAgent + ParallelAgent orchestrator | — |

### 4 MCP Servers
| MCP Server | Tools | External Integration |
|---|---|---|
| **Tasks MCP** | `save_tasks`, `update_task`, `check_duplicates` | PostgreSQL + pgvector |
| **Calendar MCP** | `create_calendar_event`, `get_available_slots` | Google Calendar API |
| **Notes MCP** | `save_note`, `search_notes`, `save_meeting_note` | PostgreSQL full-text |
| **Workspace MCP** | `create_meeting_doc`, `search_gdrive`, `send_email` | Google Docs/Drive/Gmail API |

### RAG — Semantic Search via pgvector + Vertex AI
- Every task, note, and meeting is embedded using **Vertex AI `text-embedding-004`**
- Stored in PostgreSQL with **pgvector** extension and IVFFlat indexes
- Semantic deduplication: cosine similarity threshold 0.85 before saving any task
- Query: `"find tasks similar to deploy authentication"` → returns semantically related tasks, not just keyword matches

### LLM-as-Judge (Self-Evaluating AI)
After every transcript, `evaluation_agent` grades its own pipeline output:
- **Summary Quality** — did it capture all decisions and outcomes?
- **Task Extraction Completeness** — were all action items found?
- **Priority Accuracy** — are High/Medium/Low correctly assigned?
- **Owner Attribution** — are tasks assigned to the right people?

Score saved to `quality_scores` table. Viewable as a scorecard in the UI after every run.

### Parallel Execution on Separate Quota Pools
`notes_agent` (gemini-2.5-flash) and `evaluation_agent` (gemini-2.5-flash-lite) run simultaneously via `ParallelAgent`. Different model versions = separate Vertex AI quota buckets = no rate-limit collision.

### Global Memory Persistence
User preferences stored in a fixed `global_user_preferences` session — not tied to a browser tab or UUID. Memory survives browser refresh, new sessions, and different devices.

Pre-injected into execution_agent's prompt at request time → zero runtime tool calls for scheduling preferences.

```
"Remember our team prefers morning meetings"
→ Next: "Schedule demo with Sarah on Friday sarah@example.com"
→ Agent reads injected memory, schedules at 9:00 AM automatically. No clarifying question.
```

### 33% Fewer LLM Calls
Initial design: 6 LLM calls per transcript.  
Current: 5 LLM calls per transcript.  
Eliminated: `briefing_agent` (replaced with deterministic Python assembly) and `memory_store_agent` (replaced with inline Python tool call).

## Database Schema

```sql
meetings     (id UUID, transcript TEXT, summary TEXT, embedding vector(768), doc_url TEXT, created_at)
tasks        (id UUID, meeting_id UUID, task_name TEXT, owner TEXT, deadline TEXT,
              priority TEXT, status TEXT, embedding vector(768), created_at)
notes        (id UUID, meeting_id UUID, title TEXT, content TEXT, embedding vector(768))
memory       (id UUID, session_id TEXT, key TEXT, value TEXT, embedding vector(768))
quality_scores (id UUID, meeting_id UUID, summary_quality INT, task_extraction_completeness INT,
                priority_accuracy INT, owner_attribution INT, overall_score FLOAT,
                flags JSONB, recommendations JSONB, created_at)
```

**Indexes:** IVFFlat on all 4 embedding columns · B-tree on `status`, `owner`, `priority`, `meeting_id`

## React Dashboard

Single Cloud Run URL serves both the FastAPI backend and React frontend — no CORS, no separate deployments.

**4 tabs, all live data from the agent pipeline:**

| Tab | What It Shows |
|---|---|
| **Tasks** | All extracted tasks · filter by status/owner/priority · inline status edit · deadline picker · bulk actions · CSV export |
| **Meetings** | Timeline of processed meetings · expandable task list per meeting · progress bar · copy summary |
| **Analytics** | Task ownership chart · weekly completion trend · overdue list with inline Mark Done · time saved estimate |
| **Docs** | Every processed meeting auto-publishes a Google Doc · click to open |

**Additional UI features:** Live pipeline visualizer (4-stage progress bar) · Quality scorecard popup after each transcript · Semantic search suggested queries · Voice input (Web Speech API) · Global memory across sessions · Real-time tab badge with overdue count

## Deployment

Single container on **Google Cloud Run** — auto-scales to zero, wakes on request.

```
Cloud Run (port 8080)
  └─ FastAPI (server.py)
       ├─ POST /api/chat       → ADK Runner (8-agent pipeline)
       ├─ PATCH /api/tasks/:id → Direct DB update (no LLM)
       ├─ GET  /api/tasks      → DB read with filters
       ├─ GET  /api/meetings   → DB read
       ├─ GET  /api/analytics  → Aggregated DB queries
       ├─ GET  /api/quality    → quality_scores table
       ├─ GET  /api/docs       → meetings with doc_url
       └─ /*                   → React build (static files)
```

**Stack:** Python 3.11 · FastAPI · Google ADK · PostgreSQL + pgvector · Vertex AI · React + Vite + Tailwind · Docker (multi-stage build)

## Quick Start

```bash
# 1. Clone and configure
git clone <repo>
cp .env.example .env
# Edit .env with your GCP project, DB credentials, Calendar ID

# 2. Initialize database
pip install -r requirements.txt
python init_db.py

# 3. Deploy to Cloud Run
bash deploy.sh
```

### Environment Variables

| Variable | Description |
|---|---|
| `PROJECT_ID` | GCP project ID |
| `DB_HOST` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` | PostgreSQL connection |
| `CALENDAR_ID` | Google Calendar email for event creation |
| `MODEL` | Primary model (default: `gemini-2.5-flash`) |
| `EVAL_MODEL` | Evaluation agent model (default: `gemini-2.5-flash-lite`) |

## Project Structure

```
catalyst/
├── agent.py                    # 8 agents — root, pipeline, query, execution, evaluation
├── server.py                   # FastAPI — /api/* routes + React static serving
├── tools/
│   ├── db_tools.py            # PostgreSQL + pgvector CRUD + semantic search
│   ├── embeddings.py          # Vertex AI text-embedding-004 wrapper
│   ├── analytics_tools.py     # Ownership, trends, velocity, overdue analytics
│   ├── workspace_tools.py     # Google Docs/Drive/Gmail tools
│   ├── calendar_tools.py      # Google Calendar event creation
│   ├── notes_tools.py         # Meeting notes + briefing assembly
│   ├── mcp_wrapper.py         # MCP abstraction layer
│   └── mcp_servers/           # 4 MCP server implementations
├── frontend/src/App.jsx        # React dashboard — all UI components
├── schema.sql                  # PostgreSQL schema with pgvector
├── Dockerfile                  # Multi-stage: Node build → Python serve
├── DEMO_SCRIPT.md              # 5-minute demo script
└── SAMPLE_TRANSCRIPT.md        # 4 realistic test transcripts
```

## Tests

```bash
pytest tests/ -v
```

15 unit tests covering: task deduplication · semantic search · date parsing · meeting save/load · task filtering · analytics queries

**Built for Google Gen AI Academy APAC — Multi-Agent Systems with MCP Competition 2026**  
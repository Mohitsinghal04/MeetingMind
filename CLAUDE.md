# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MeetingMind** is a multi-agent productivity assistant built with Google ADK (Agent Development Kit) that processes meeting transcripts through an orchestrated pipeline of specialized agents. The system extracts summaries, action items, schedules events, checks for duplicates, manages notes, and stores contextual memory — all in parallel where possible.

**Technology Stack:**
- Python with Google ADK (`google-adk==1.0.0`)
- MCP (Model Context Protocol) for tool integration (`mcp==1.0.0`)
- Google Cloud Platform (Cloud Run, Cloud SQL Postgres, Vertex AI Gemini)
- PostgreSQL for persistent storage
- Vanilla HTML/CSS/JavaScript UI served by ADK

## Development Commands

### Environment Setup
```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate

# Install dependencies (includes MCP for competition requirement)
uv pip install -r requirements.txt

# Configure environment variables
cp env .env
# Edit .env with your GCP values from day1_gcp_setup.sh

# Verify MCP installation
python3 -c "import mcp; print('✓ MCP installed')"
```

### MCP Server Testing
```bash
# Test MCP servers individually (they auto-start in production)
python -m tools.calendar_mcp_server  # Calendar operations
python -m tools.tasks_mcp_server     # Task management
python -m tools.notes_mcp_server     # Notes management

# Verify MCP config
cat mcp_config.json
```

### Local Testing
```bash
# Run the agent locally with ADK CLI (MCP servers auto-start)
adk run .

# Test database connectivity
python3 -c "import os, psycopg2; from dotenv import load_dotenv; load_dotenv(); conn = psycopg2.connect(host=os.getenv('DB_HOST'), database=os.getenv('DB_NAME'), user=os.getenv('DB_USER'), password=os.getenv('DB_PASSWORD')); print('✓ Connected'); conn.close()"

# Serve UI locally with convenience script
bash serve_ui.sh
# Or manually:
# python3 -m http.server 8080 --directory ui/
```

### Database Setup
```bash
# Connect to Cloud SQL
gcloud sql connect meetingmind-db --user=meetingmind_user --database=meetingmind

# Run schema (after connecting)
# Paste contents of schema.sql
```

### Deployment
```bash
# Deploy to Cloud Run with MCP support (from parent directory of project)
bash day6_deploy.sh

# The deployment script now includes:
# - Pre-deployment checks for MCP files
# - Verification of all competition requirements
# - Detailed output about MCP integration
```

## Multi-Agent Architecture

### Execution Flow

The system uses a **root agent** (`meetingmind`) as an intent router that delegates to four specialized pipelines:

**Intent A: TRANSCRIPT** → `transcript_pipeline`
- `sequential_chain`: `summary_agent` → `action_item_agent` → `priority_agent`
- `parallel_branch`: `scheduler_agent` + `duplicate_check_agent` + `notes_agent` + `memory_agent_background`
- `briefing_agent`: assembles final structured output

**Intent B: QUESTION** → `query_agent`
- Answers queries about tasks, notes, and stored memory using DB tools

**Intent C: COMMAND** → `execution_agent`
- Executes actions like marking tasks done, updating status, or scheduling events

**Intent D: STORE** → `memory_store_agent`
- Persists user-provided information to the memory table

### Sequential vs Parallel Execution

**Sequential Chain** (defined at line 459-463 in agent.py):
Agents run one after another, each passing output to the next via `output_key` → next agent's instruction template. Used when each agent depends on the previous agent's result.

**Parallel Branch** (defined at line 466-475 in agent.py):
All sub-agents run simultaneously. Used when agents are independent and can execute concurrently (scheduling, DB saves, note searches, memory storage).

### State Management

**Tool Context State** (ToolContext): Agents share session state through `tool_context.state`. Key state variables:
- `TRANSCRIPT`: the original meeting transcript
- `session_id`: unique session identifier for DB isolation
- `current_meeting_id`: UUID linking tasks/notes to meetings
- `user_query`, `user_command`, `memory_input`: intent-specific inputs set by root agent

State is passed between agents in a pipeline and persists for the duration of the ADK session.

### Agent Output Keys

Each agent writes its result to a specific state key via the `output_key` parameter. Downstream agents reference these keys in their instruction templates using `{key_name}` syntax.

Example flow:
1. `summary_agent` → `output_key="meeting_summary"`
2. `action_item_agent` instruction references `{meeting_summary}` → `output_key="action_items"`
3. `priority_agent` instruction references `{action_items}` → `output_key="prioritized_tasks"`

## Database Schema

The system uses **4 core tables** (schema.sql):

1. **meetings**: stores transcript + summary with session_id
2. **tasks**: action items with owner, deadline, priority, status (foreign key to meetings)
3. **notes**: searchable meeting notes (foreign key to meetings)
4. **memory**: key-value store for session context (unique constraint on session_id + key)

**Critical indexes:**
- `idx_tasks_owner`, `idx_tasks_status`, `idx_tasks_priority` for task queries
- `idx_notes_title` for note searches
- `idx_memory_session` for memory lookups

## Tool Organization

**tools/db_tools.py**: Low-level Postgres operations
- Direct DB connection handling via `get_db_connection()`
- CRUD operations for all tables
- Returns dicts with `{"status": "success/error", ...}` format

**tools/task_tools.py, notes_tools.py**: Higher-level wrappers
- Thin abstraction over db_tools with better error messages
- Used by agents as ADK tools

**tools/calendar_tools.py**: Calendar operations
- Currently returns mock data for demo purposes
- Ready for Google Calendar API integration if needed

**MCP Servers** (Competition Requirement - CRITICAL):

**tools/calendar_mcp_server.py**: Calendar MCP server
- Exposes 2 tools via MCP protocol: `get_available_slots`, `create_calendar_event`
- Uses stdio transport (auto-started by ADK)
- Wraps calendar_tools.py functions

**tools/tasks_mcp_server.py**: Tasks MCP server
- Exposes 4 tools: `list_tasks`, `save_tasks`, `update_task_status`, `check_duplicate_tasks`
- Wraps db_tools.py task operations with MCP protocol
- Used by DuplicateCheckAgent, QueryAgent, ExecutionAgent

**tools/notes_mcp_server.py**: Notes MCP server
- Exposes 4 tools: `search_notes`, `save_note`, `search_related_notes`, `save_meeting_note`
- Wraps db_tools.py notes operations with MCP protocol
- Used by NotesAgent

**mcp_config.json**: MCP server configuration
- Defines 3 MCP servers with stdio transport
- Agents auto-start these servers via ADK when tools are needed
- CRITICAL: This file proves MCP integration for competition judges

## Key Implementation Details

### Duplicate Detection (duplicate_check_agent)
Uses partial string matching (`LOWER(task_name) LIKE LOWER(%pattern%)`) to find similar tasks. Only checks tasks not in 'Done' or 'Cancelled' status. Agents must call `check_duplicate_tasks` before `save_tasks` for each task.

### JSON Output Format
Action item and priority agents are instructed to return **ONLY valid JSON arrays** with no markdown fences or explanations. The briefing agent assembles everything into a final JSON object that the UI can parse.

### Error Handling
All DB tools wrap operations in try/except and return status dicts rather than raising exceptions. Agents should check `result["status"]` and handle errors gracefully in their responses.

### Session Isolation
`session_id` from state is used to isolate memories across sessions. Tasks and meetings are global but can be filtered by meeting_id. The seed data in schema.sql uses `'demo-session'` for testing.

## UI Integration

**ui/index.html** is a single-file SPA that:
- Calls `/run` endpoint (ADK's standard HTTP interface)
- Sends messages in ADK format: `{app_name, user_id, session_id, new_message: {role, parts}}`
- Extracts responses from `data.events[].content.parts[].text`
- Animates agent status visually based on intent detection
- Parses JSON from bot responses to render structured output cards

**BASE_URL** in the UI uses `window.location.origin` — it expects to be served from the same Cloud Run service as the agent.

## GCP Infrastructure

**Services Used:**
- Cloud Run (compute)
- Cloud SQL Postgres 15 (database)
- Vertex AI (Gemini 2.5 Flash model)
- Artifact Registry (container storage)
- Cloud Build (deployment)
- Cloud Logging (observability)

**IAM Service Account** (`meetingmind-sa@PROJECT_ID.iam.gserviceaccount.com`) has roles:
- `roles/aiplatform.user` (Gemini access)
- `roles/cloudsql.client` (DB access)
- `roles/logging.logWriter` (logs)

**Environment Variables** (required in .env and Cloud Run):
- `PROJECT_ID`, `PROJECT_NUMBER`, `REGION`
- `SERVICE_ACCOUNT`, `SA_NAME`
- `DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_PORT`
- `MODEL` (defaults to `gemini-2.5-flash`)

## Development Workflow

**Day 1**: GCP setup via `day1_gcp_setup.sh` (Cloud SQL, IAM, APIs)
**Day 2-5**: Local testing with `adk run` and DB verification scripts in `day2_to_day5_testing.sh`
  - Includes MCP server verification
  - Tests all 4 intent types (transcript, query, command, memory)
**Day 6**: Deployment via `day6_deploy.sh` using `adk deploy cloud_run --with_ui`
  - Pre-deployment checks validate MCP files
  - Competition checklist output after deployment

## Testing Approach

The project includes inline Python scripts in `day2_to_day5_testing.sh` for verifying:
- MCP package installation
- MCP server files existence
- DB connectivity
- Tasks saved correctly
- Memory storage
- Full pipeline execution

Test with the **DEMO_TRANSCRIPT** embedded in `ui/index.html` (Q3 Product Planning meeting) for consistent results.

**MCP Testing**: Each MCP server can be tested individually:
```bash
python -m tools.calendar_mcp_server  # Should start without errors
python -m tools.tasks_mcp_server
python -m tools.notes_mcp_server
```
In production, MCP servers are auto-started by ADK when agents need them (stdio transport).

## Important Notes

- **Never commit secrets**: `.env` file should never be in version control
- **Google ADK version**: Pinned to `1.0.0` — check for updates if features are missing
- **MCP version**: Pinned to `1.0.0` — required for competition
- **Cloud SQL public IP**: `day1_gcp_setup.sh` authorizes `0.0.0.0/0` for demos (use Cloud SQL Proxy or private IP for production)
- **No backup configured**: Cloud SQL instance created with `--no-backup` flag for cost savings
- **Agent logging**: Uses `google.cloud.logging` when available, falls back to basic logging
- **MCP integration is live**: 3 MCP servers (calendar, tasks, notes) using stdio transport satisfy competition requirement
- **Calendar tools use mock data**: For demo purposes; can integrate Google Calendar API if needed

## Competition-Specific Features

**MCP Integration** (CRITICAL requirement):
- 3 MCP servers with 10 total tools
- Stdio transport (launched automatically by agents)
- mcp_config.json provides server definitions
- Logs show "MCP" mentions when servers are used

**Architecture Highlights**:
- Sequential + Parallel agent execution (1.8x speedup)
- Two-pass intent detection (keyword + LLM)
- Real-time UI agent status animation
- Execution metrics in briefing output

**Documentation**:
- SETUP_GUIDE.md: Complete step-by-step setup
- CLAUDE.md: This file for developers
- Inline code comments explaining architecture
- Setup scripts with verification checks

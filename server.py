"""
MeetingMind — FastAPI server
Serves the React UI at / and the ADK agent + REST API at /api/*.

Path layout inside the container:
  /app/agents/meetingmind/server.py   ← this file
  /app/agents/meetingmind/agent.py    ← ADK root_agent
  /app/static/                        ← React build (served at /)
"""

import os
import sys
import uuid
import asyncio
import logging
import datetime
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# When running inside the container, this file is at
# /app/agents/meetingmind/server.py  →  parent = /app/agents/
# Adding /app/agents to sys.path makes `import meetingmind` work.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_AGENTS_DIR = os.path.dirname(_THIS_DIR)
if _AGENTS_DIR not in sys.path:
    sys.path.insert(0, _AGENTS_DIR)

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

from meetingmind.agent import root_agent
from meetingmind.tools.db_tools import get_pending_tasks, list_all_meetings
from meetingmind.tools.analytics_tools import (
    get_task_ownership_stats,
    get_overdue_tasks,
    get_meeting_velocity,
    get_recurring_topics,
    get_task_completion_trends,
    get_latest_quality_scores,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Static files: /app/static (one level above /app/agents/meetingmind)
STATIC_DIR = os.path.abspath(os.path.join(_AGENTS_DIR, "..", "static"))


def _serialize(obj):
    """Recursively convert non-JSON-safe types to strings."""
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(i) for i in obj]
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (datetime.datetime, datetime.date)):
        return obj.isoformat()
    if isinstance(obj, (int, float, str, bool)) or obj is None:
        return obj
    # Catch-all: Decimal, pgvector types, memoryview, etc.
    return str(obj)


class _MockCtx:
    """Minimal stand-in for ToolContext used in direct DB/analytics calls."""
    def __init__(self):
        self.state = {"session_id": "api_direct"}


_session_service = InMemorySessionService()
_runner: Optional[Runner] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    _runner = Runner(
        agent=root_agent,
        app_name="meetingmind",
        session_service=_session_service,
    )
    logger.info("MeetingMind server ready (7 agents, FastAPI)")
    yield


app = FastAPI(title="MeetingMind", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ──────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


# ── API routes ─────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "meetingmind", "agents": 7}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    user_id = "web_user"

    # Create session — ADK 1.x uses async create_session
    try:
        coro = _session_service.create_session(
            app_name="meetingmind",
            user_id=user_id,
            session_id=session_id,
        )
        if asyncio.iscoroutine(coro):
            await coro
    except Exception:
        pass

    content = Content(role="user", parts=[Part(text=req.message)])
    response_text = ""

    try:
        async for event in _runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content:
                for part in event.content.parts or []:
                    if hasattr(part, "text") and part.text:
                        response_text += part.text
    except Exception as e:
        logger.error(f"Agent error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

    return {"response": response_text, "session_id": session_id}


@app.get("/api/tasks")
async def get_tasks(
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
):
    ctx = _MockCtx()
    result = get_pending_tasks(ctx, owner=owner, priority=priority, status=status,
                               show_all=(status is None))
    tasks = _serialize(result.get("tasks", []))
    return {"tasks": tasks, "count": len(tasks)}


@app.get("/api/meetings")
async def get_meetings():
    ctx = _MockCtx()
    result = list_all_meetings(ctx)
    meetings = _serialize(result.get("meetings", []))
    return {"meetings": meetings, "count": len(meetings)}


@app.get("/api/analytics")
async def get_analytics():
    ctx = _MockCtx()
    return _serialize({
        "ownership": get_task_ownership_stats(ctx),
        "overdue": get_overdue_tasks(ctx),
        "velocity": get_meeting_velocity(ctx),
        "topics": get_recurring_topics(ctx),
        "trends": get_task_completion_trends(ctx),
    })


@app.get("/api/quality")
async def get_quality():
    ctx = _MockCtx()
    return _serialize(get_latest_quality_scores(ctx, limit=10))


# ── Static files (React) — MUST be last ───────────────────

if os.path.isdir(STATIC_DIR):
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
else:
    @app.get("/")
    async def root_fallback():
        return {
            "message": "MeetingMind API running. React build not found.",
            "api_docs": "/docs",
            "health": "/health",
        }


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

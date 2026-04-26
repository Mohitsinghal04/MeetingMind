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

import json
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
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
    logger.info("MeetingMind server ready (8 agents, 1 parallel stage, 4 MCP servers, FastAPI)")
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
    return {"status": "ok", "service": "meetingmind", "agents": 8, "mcp_servers": 4}


import re as _re

def _clean_response(text: str) -> str:
    """Strip tool-result JSON and intermediate agent chatter from pipeline briefing output."""
    if not text:
        return "⚠️ No response from agents."

    # 1. If the briefing marker exists anywhere, extract from that point
    for marker in ("✅ **Meeting Processed", "📋 **Summary", "✅ **"):
        idx = text.find(marker)
        if idx >= 0:
            text = text[idx:]
            break

    # 2. Strip all fenced code blocks (```json ... ```) anywhere in the text
    text = _re.sub(r"```[\w]*\n.*?```", "", text, flags=_re.DOTALL)

    # 3. Strip multi-line JSON objects/arrays anywhere in the text
    text = _re.sub(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", "", text, flags=_re.DOTALL)

    # 4. Strip leftover lines that are pure JSON fragments or the bare word "json"
    lines = text.splitlines()
    clean = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("json", ""):
            continue
        # Strip bare JSON array fragments but NOT markdown links like [text](url)
        if stripped.startswith("]"):
            continue
        if stripped.startswith("[") and not _re.match(r'^\[.+\]\(', stripped):
            continue
        if stripped.startswith(('"related', '"note', '"search')):
            continue
        clean.append(line)

    result = "\n".join(clean).strip() or text.strip()

    # 5. Remove all Google Doc lines — doc link lives in the Docs tab only
    result = _re.sub(r"📄[^\n]*\n?", "", result)
    result = _re.sub(r"[^\n]*Google Doc[^\n]*\n?", "", result)

    # 6. Collapse runs of 3+ blank lines into 2
    result = _re.sub(r"\n{3,}", "\n\n", result)

    return result


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    user_id = "web_user"

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

    # Emit pipeline stage events for transcript messages (long input = likely a transcript)
    is_transcript = len(req.message) > 400
    PIPELINE_STAGES = [
        (0,  0,  "Summarising transcript…"),
        (1, 25,  "Saving to database & scheduling…"),
        (2, 50,  "Taking notes…"),
        (3, 75,  "Generating briefing…"),
    ]

    async def event_stream():
        response_text = ""
        error_holder:  list = []

        async def run_agent():
            try:
                async for event in _runner.run_async(
                    user_id=user_id,
                    session_id=session_id,
                    new_message=content,
                ):
                    if event.is_final_response() and event.content:
                        for part in event.content.parts or []:
                            if hasattr(part, "text") and part.text:
                                response_text_ref[0] += part.text
            except Exception as exc:
                error_holder.append(str(exc))

        response_text_ref = [""]
        agent_task = asyncio.create_task(run_agent())

        # Heartbeat every 3 s; also emit pipeline stage events for transcripts
        elapsed = 0
        stage_idx = 0
        while not agent_task.done():
            # Emit next stage event when its trigger time is reached
            if is_transcript and stage_idx < len(PIPELINE_STAGES):
                idx, trigger_at, label = PIPELINE_STAGES[stage_idx]
                if elapsed >= trigger_at:
                    yield f"data: {json.dumps({'type': 'stage', 'index': idx, 'label': label})}\n\n"
                    stage_idx += 1
            yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
            await asyncio.sleep(3)
            elapsed += 3
            if elapsed >= 270:
                agent_task.cancel()
                error_holder.append("Request timed out after 270 seconds. The model may be rate-limited (429). Please try again in a moment.")
                break

        if not agent_task.cancelled():
            await agent_task

        if error_holder:
            logger.error(f"Agent error: {error_holder[0]}")
            payload = {"type": "error", "detail": error_holder[0]}
        else:
            raw = response_text_ref[0]
            logger.info(f"Raw agent response (first 300 chars): {raw[:300]!r}")

            # Create Google Doc directly (no LLM involved) after a transcript pipeline run
            if is_transcript:
                try:
                    import psycopg2 as _pg
                    from meetingmind.tools.workspace_tools import create_meeting_doc as _create_doc
                    with _pg.connect(
                        host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
                        user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
                        port=int(os.getenv("DB_PORT", 5432)),
                    ) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT id, summary FROM meetings ORDER BY created_at DESC LIMIT 1"
                        )
                        row = cur.fetchone()
                        if row and row[1]:
                            meeting_id, summary = row
                            cur.execute(
                                "SELECT task_name, priority, owner, deadline FROM tasks "
                                "WHERE meeting_id = %s ORDER BY created_at",
                                (str(meeting_id),),
                            )
                            tasks = cur.fetchall()
                            cur.close()
                            tasks_md = "\n".join(
                                f"- [{t[1]}] {t[0]} — {t[2]} — due: {t[3]}" for t in tasks
                            )
                            ctx = _MockCtx()
                            ctx.state["current_meeting_id"] = str(meeting_id)
                            title = (summary[:60] + "…") if len(summary) > 60 else summary
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                None, _create_doc, ctx, title, summary, tasks_md
                            )
                            logger.info(f"Doc created for meeting {meeting_id}")
                except Exception as doc_err:
                    logger.warning(f"Post-pipeline doc creation failed (non-fatal): {doc_err}")

            payload = {
                "type":       "response",
                "response":   _clean_response(raw),
                "session_id": session_id,
            }

        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )


class TaskUpdate(BaseModel):
    status:   Optional[str] = None   # Pending | In Progress | Done | Cancelled
    deadline: Optional[str] = None   # YYYY-MM-DD, or "" to clear

@app.patch("/api/tasks/{task_id}")
async def patch_task(task_id: str, body: TaskUpdate):
    valid_statuses = {"Pending", "In Progress", "Done", "Cancelled"}
    if body.status is not None and body.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {sorted(valid_statuses)}")
    if body.status is None and body.deadline is None:
        raise HTTPException(status_code=400, detail="Provide at least one of: status, deadline")
    try:
        with __import__("psycopg2").connect(
            host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
            port=int(os.getenv("DB_PORT", 5432)),
        ) as conn:
            cur = conn.cursor()
            # Build SET clause dynamically — only update provided fields
            sets, params = [], []
            if body.status is not None:
                sets.append("status = %s"); params.append(body.status)
            if body.deadline is not None:
                # Empty string → store as NULL (unset deadline)
                dl = body.deadline.strip() or None
                sets.append("deadline = %s"); params.append(dl)
            params.append(task_id)
            cur.execute(
                f"UPDATE tasks SET {', '.join(sets)} WHERE id = %s RETURNING id, task_name, status, deadline",
                params,
            )
            row = cur.fetchone()
            conn.commit()
            cur.close()
        if not row:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"id": str(row[0]), "task_name": row[1], "status": row[2], "deadline": row[3]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"patch_task failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@app.get("/api/docs")
async def get_docs():
    """Return all meetings that have a published GCS doc."""
    try:
        with __import__("psycopg2").connect(
            host=os.getenv("DB_HOST"), dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"), password=os.getenv("DB_PASSWORD"),
            port=int(os.getenv("DB_PORT", 5432)),
        ) as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, summary, doc_url, created_at
                FROM meetings
                WHERE doc_url IS NOT NULL
                ORDER BY created_at DESC
            """)
            rows = cur.fetchall()
            cur.close()
        docs = _serialize([
            {
                "id":         str(r[0]),
                "summary":    r[1] or "",
                "doc_url":    r[2],
                "created_at": r[3],
            }
            for r in rows
        ])
        return {"docs": docs, "count": len(docs)}
    except Exception as e:
        logger.error(f"get_docs failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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

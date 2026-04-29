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

from meetingmind.agent import root_agent, _STATE_DEFAULTS
from meetingmind.tools.db_tools import (
    get_pending_tasks,
    list_all_meetings,
    find_recurring_topics_for_transcript,
    check_meeting_duplicate,
    increment_meeting_duplicates_blocked,
)
from meetingmind.tools.analytics_tools import (
    get_task_ownership_stats,
    get_overdue_tasks,
    get_meeting_velocity,
    get_recurring_topics,
    get_task_completion_trends,
    get_latest_quality_scores,
    get_meeting_debt,
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

# ── Model fallback ─────────────────────────────────────────
# On 429 (quota exhausted) the Vertex AI SDK raises immediately.
# We cycle through models until one succeeds.
_PRIMARY_MODEL = os.getenv("MODEL", "gemini-2.5-flash")
_EVAL_MODEL    = os.getenv("EVAL_MODEL", "gemini-2.5-flash-lite")
_FALLBACK_MODELS = [
    _PRIMARY_MODEL,
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
]
# Remove duplicates while preserving order
_FALLBACK_MODELS = list(dict.fromkeys(_FALLBACK_MODELS))

# Lock: prevent two concurrent requests from patching agents simultaneously
_model_lock = asyncio.Lock()


def _collect_llm_agents(agent, _seen: set | None = None) -> list:
    """Return every LLM Agent node in the hierarchy (skips Sequential/Parallel wrappers)."""
    if _seen is None:
        _seen = set()
    if id(agent) in _seen:
        return []
    _seen.add(id(agent))
    result = [agent] if hasattr(agent, "model") else []
    for sub in getattr(agent, "sub_agents", []) or []:
        result.extend(_collect_llm_agents(sub, _seen))
    return result


_429_KEYWORDS = (
    "429",
    "resource_exhausted",
    "quota",
    "rateerror",
    "too many requests",
    "too_many_requests",
    "rate limit",
    "rate_limit",
    "ratelimit",
)


def _is_429_str(text: str) -> bool:
    """Check a plain string for 429/rate-limit signals."""
    s = text.lower()
    return any(k in s for k in _429_KEYWORDS)


def _is_429(exc: Exception) -> bool:
    """Check an exception and its full cause chain for 429/rate-limit signals.

    Walks __cause__ and __context__ so wrapped exceptions
    (e.g. httpx.HTTPStatusError inside a google.api_core exception)
    are caught correctly.
    """
    seen: set = set()
    current: Exception | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if _is_429_str(str(current)):
            return True
        current = getattr(current, "__cause__", None) or getattr(current, "__context__", None)
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _runner
    _runner = Runner(
        agent=root_agent,
        app_name="meetingmind",
        session_service=_session_service,
    )
    logger.info("Catalyst server ready (8 agents, 1 parallel stage, 4 MCP servers, FastAPI)")
    yield


app = FastAPI(title="Catalyst", version="2.0", lifespan=lifespan)

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
    return {"status": "ok", "service": "catalyst", "agents": 8, "mcp_servers": 4}


import re as _re


def _clean_response(text: str) -> str:
    """Strip tool-result JSON and intermediate agent chatter from pipeline briefing output."""
    if not text:
        return "⚠️ No response from agents."

    # 1. Only extract from a pipeline-briefing marker — never from generic ✅ lines
    for marker in ("✅ Meeting Processed Successfully", "✅ **Meeting Processed"):
        idx = text.find(marker)
        if idx >= 0:
            text = text[idx:]
            break

    # 2. Strip all fenced code blocks (```json ... ```) anywhere in the text
    text = _re.sub(r"```[\w]*\n.*?```", "", text, flags=_re.DOTALL)

    # 3. Strip raw JSON objects that appear on their OWN line (agent internal chatter).
    # Only match lines where the ENTIRE line is a JSON object — never strip inline braces
    # that are part of markdown text like "Tasks saved {3}" or calendar event details.
    text = _re.sub(r"^\s*\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}\s*$", "", text, flags=_re.MULTILINE)

    # 4. Strip leftover lines that are pure JSON fragments, bare "json", or stray tool-call text
    lines = text.splitlines()
    clean = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("json", ""):
            continue
        # Strip bare JSON array fragments but NOT markdown links like [text](url)
        if stripped.startswith("]"):
            continue
        if stripped.startswith("[") and not _re.match(r"^\[.+\]\(", stripped):
            continue
        if stripped.startswith(('"related', '"note', '"search')):
            continue
        # Strip stray Python-style tool-call lines that flash-lite sometimes emits
        if _re.match(r"^print\s*\(", stripped):
            continue
        if _re.match(r"^save_quality_score\s*\(", stripped):
            continue
        if _re.match(r"^save_tasks\s*\(", stripped):
            continue
        if stripped == "Quality evaluation saved.":
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
            state={**_STATE_DEFAULTS},  # pre-init so {final_briefing} etc never throw
        )
        if asyncio.iscoroutine(coro):
            await coro
    except Exception:
        pass

    content = Content(role="user", parts=[Part(text=req.message)])

    # Emit pipeline stage events for transcript messages (long input = likely a transcript)
    is_transcript = len(req.message) > 400
    PIPELINE_STAGES = [
        (0, 0, "Summarising transcript…"),
        (1, 25, "Saving to database & scheduling…"),
        (2, 50, "Taking notes…"),
        (3, 75, "Generating briefing…"),
    ]

    async def event_stream():
        response_text = ""
        error_holder: list = []

        async def run_agent():
            """Run the agent with automatic model fallback on 429.

            Three-layer 429 detection:
            1. Exception raised from run_async (most common).
            2. Exception chain — walks __cause__ / __context__ for wrapped errors.
            3. Response text — ADK sometimes swallows the 429 and puts it in the
               content rather than raising; we detect that and force a retry.

            On each retry a fresh session is created so the fallback model gets
            a clean conversation state (no duplicate user messages from the
            failed first attempt).
            """
            llm_agents = _collect_llm_agents(root_agent)

            async with _model_lock:
                tried = []
                # Use a per-attempt session id so retries start clean.
                attempt_session_id = session_id

                for model in _FALLBACK_MODELS:
                    tried.append(model)

                    # Patch every LLM agent except the eval agent (keeps its own quota pool)
                    for a in llm_agents:
                        if getattr(a, "model", None) != _EVAL_MODEL:
                            a.model = model

                    if model != _PRIMARY_MODEL:
                        logger.warning(
                            f"⚡ 429 quota hit — retrying with fallback model: {model} "
                            f"(session {attempt_session_id})"
                        )

                    try:
                        async for event in _runner.run_async(
                            user_id=user_id,
                            session_id=attempt_session_id,
                            new_message=content,
                        ):
                            if event.is_final_response() and event.content:
                                for part in event.content.parts or []:
                                    if hasattr(part, "text") and part.text:
                                        response_text_ref[0] += part.text

                        # Bug 1 fix: ADK can swallow a 429 and return it as
                        # response text instead of raising. Detect and retry.
                        if _is_429_str(response_text_ref[0]):
                            logger.warning(
                                f"⚡ 429 detected in response content "
                                f"(model={model}) — retrying with fallback"
                            )
                            response_text_ref[0] = ""
                            raise RuntimeError("429 in response content")

                        final_session_id_ref[0] = attempt_session_id
                        return  # genuine success — stop trying further models

                    except Exception as exc:
                        if _is_429(exc):
                            # Bug 2 fix: create a fresh session for the next
                            # attempt so the fallback model doesn't see the
                            # partial/duplicate conversation from this attempt.
                            attempt_session_id = str(uuid.uuid4())
                            try:
                                coro = _session_service.create_session(
                                    app_name="meetingmind",
                                    user_id=user_id,
                                    session_id=attempt_session_id,
                                )
                                if asyncio.iscoroutine(coro):
                                    await coro
                            except Exception:
                                pass  # session creation failure is non-fatal
                            continue  # try next fallback model immediately

                        # Non-429 error — surface it directly
                        error_holder.append(str(exc))
                        return

                # All models exhausted
                error_holder.append(
                    f"⚠️ All models rate-limited (tried: {', '.join(tried)}). "
                    "Please wait ~1 minute and try again."
                )

            # Always restore primary model for the next request
            for a in llm_agents:
                if getattr(a, "model", None) != _EVAL_MODEL:
                    a.model = _PRIMARY_MODEL

        # ── Pre-pipeline duplicate gate ────────────────────────────
        # Compare raw transcript text (md5 hash + first-300-chars fallback).
        # No embedding needed — meetings.embedding stores SUMMARY embeddings,
        # comparing those against raw transcript would give false low similarity.
        # Fails open on any error so pipeline always runs if check breaks.
        if is_transcript:
            try:
                duplicate = check_meeting_duplicate(req.message)
                if duplicate:
                    increment_meeting_duplicates_blocked(duplicate["meeting_id"])
                    logger.info(
                        f"Duplicate transcript blocked — "
                        f"{duplicate['similarity']}% match to meeting "
                        f"{duplicate['meeting_id']}"
                    )
                    payload = {
                        "type": "duplicate",
                        "similarity": duplicate["similarity"],
                        "original_date": duplicate["created_at"],
                        "original_snippet": duplicate["summary_snippet"],
                        "session_id": session_id,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    return  # stop — no pipeline, no meeting save, no doc
            except Exception as dup_err:
                logger.warning(f"Pre-pipeline duplicate check failed (non-fatal): {dup_err}")
                # fail open — continue with full pipeline

        response_text_ref = [""]
        # Tracks which session the pipeline actually ran in (may differ on 429 fallback)
        final_session_id_ref = [session_id]
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
                error_holder.append(
                    "Request timed out after 270 seconds. The model may be rate-limited (429). Please try again in a moment."
                )
                break

        if not agent_task.cancelled():
            await agent_task

        if error_holder:
            logger.error(f"Agent error: {error_holder[0]}")
            payload = {"type": "error", "detail": error_holder[0]}
        else:
            raw = response_text_ref[0]
            logger.info(f"Raw agent response (first 300 chars): {raw[:300]!r}")

            # ── For transcripts: always use final_briefing from session state ──
            # notes_agent writes the briefing to state via assemble_briefing_from_state().
            # This is more reliable than root_agent relaying it, because the
            # ParallelAgent race condition can cause root_agent to relay
            # evaluation_agent's "Quality evaluation saved." instead.
            if is_transcript:
                try:
                    sess = _session_service.get_session(
                        app_name="meetingmind",
                        user_id=user_id,
                        session_id=final_session_id_ref[0],
                    )
                    if asyncio.iscoroutine(sess):
                        sess = await sess
                    st = getattr(sess, "state", None) or {}
                    state_briefing = st.get("final_briefing", "")

                    # Only use state briefing if summary section has actual content
                    import re as _bre
                    _summary_match = _bre.search(r'📋 Summary:\n(.+)', state_briefing or '')
                    _has_content = bool(_summary_match and _summary_match.group(1).strip())
                    if state_briefing and "✅" in state_briefing and _has_content:
                        raw = state_briefing
                        logger.info("Briefing read from session state (authoritative source)")
                    elif state_briefing and "✅" not in state_briefing and state_briefing.strip():
                        raw = state_briefing
                        logger.info("Briefing read from session state (no ✅ marker)")
                    else:
                        # Last resort: build briefing from state variables,
                        # falling back to DB if state is empty.
                        summary = (st.get("meeting_summary") or "").strip()
                        tasks = (st.get("prioritized_tasks") or "").strip()
                        save_result = (st.get("save_schedule_result") or "").strip()

                        # If state is empty (analysis_agent didn't write), pull from DB
                        if not summary or not tasks:
                            try:
                                import psycopg2 as _pg_lr
                                with _pg_lr.connect(
                                    host=os.getenv("DB_HOST"),
                                    dbname=os.getenv("DB_NAME"),
                                    user=os.getenv("DB_USER"),
                                    password=os.getenv("DB_PASSWORD"),
                                    port=int(os.getenv("DB_PORT", 5432)),
                                ) as _conn_lr:
                                    _cur = _conn_lr.cursor()
                                    # Skip meetings with empty summary — they came from failed runs
                                    _cur.execute(
                                        "SELECT id, summary FROM meetings "
                                        "WHERE summary IS NOT NULL AND summary != '' "
                                        "ORDER BY created_at DESC LIMIT 1"
                                    )
                                    _row = _cur.fetchone()
                                    if _row and _row[1]:
                                        summary = summary or _row[1]
                                        _mid = str(_row[0])
                                        logger.info(f"DB fallback: found meeting {_mid} with {len(summary)} char summary")
                                        if not tasks:
                                            _cur.execute(
                                                "SELECT task_name, priority, owner, deadline "
                                                "FROM tasks WHERE meeting_id = %s ORDER BY created_at",
                                                (_mid,),
                                            )
                                            _trows = _cur.fetchall()
                                            if _trows:
                                                tasks = "\n".join(
                                                    f"• {t[1]} — {t[0]} — Owner: {t[2] or 'Unassigned'} — Due: {t[3] or 'TBD'}"
                                                    for t in _trows
                                                )
                                                logger.info(f"DB fallback: loaded {len(_trows)} tasks")
                                    else:
                                        logger.warning("DB fallback: no meeting with non-empty summary found")
                                    _cur.close()
                            except Exception as _db_lr_err:
                                logger.warning(f"DB fallback for briefing failed: {_db_lr_err}")

                        if summary:
                            raw = (
                                "✅ Meeting Processed Successfully\n\n"
                                "📋 Summary:\n" + summary + "\n\n"
                                "✅ Action Items:\n" + tasks + "\n\n"
                                "💾 System Actions:\n" + save_result + "\n"
                                "📝 Notes saved to knowledge base\n\n"
                                "📊 Pipeline: 4 stages · Tasks + Calendar + Notes + Quality Eval\n\n"
                                '✨ Try: "What tasks are pending?" · "Mark [task] as done"'
                            )
                            logger.info("Briefing built from last-resort recovery")
                        else:
                            logger.warning(
                                f"All briefing recovery methods failed "
                                f"(session={final_session_id_ref[0]}, raw={raw[:120]!r})"
                            )
                except Exception as sb_err:
                    logger.warning(
                        f"State briefing read failed (non-fatal): {sb_err}"
                    )

            # Create Google Doc directly (no LLM involved) after a transcript pipeline run
            if is_transcript:
                try:
                    import psycopg2 as _pg
                    from meetingmind.tools.workspace_tools import create_meeting_doc as _create_doc

                    with _pg.connect(
                        host=os.getenv("DB_HOST"),
                        dbname=os.getenv("DB_NAME"),
                        user=os.getenv("DB_USER"),
                        password=os.getenv("DB_PASSWORD"),
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

            # ── Cross-meeting RAG: find recurring topics ──────────────
            # Runs entirely outside the LLM pipeline — pure pgvector SQL.
            # find_recurring_topics_for_transcript() fetches the embedding
            # internally via the pool (pgvector adapter registered) so there
            # are no text[] → vector cast issues.
            recurring_topics = []
            if is_transcript:
                try:
                    import psycopg2 as _pg2

                    with _pg2.connect(
                        host=os.getenv("DB_HOST"),
                        dbname=os.getenv("DB_NAME"),
                        user=os.getenv("DB_USER"),
                        password=os.getenv("DB_PASSWORD"),
                        port=int(os.getenv("DB_PORT", 5432)),
                    ) as conn:
                        cur = conn.cursor()
                        cur.execute(
                            "SELECT id FROM meetings ORDER BY created_at DESC LIMIT 1"
                        )
                        row = cur.fetchone()
                        cur.close()

                    if row:
                        meeting_id_for_rag = str(row[0])
                        recurring_topics = find_recurring_topics_for_transcript(
                            new_meeting_id=meeting_id_for_rag,
                        )
                        if recurring_topics:
                            logger.info(
                                f"Cross-meeting RAG: {len(recurring_topics)} recurring "
                                f"topic(s) found for meeting {meeting_id_for_rag}"
                            )
                except Exception as rag_err:
                    logger.warning(f"Cross-meeting RAG failed (non-fatal): {rag_err}")

            payload = {
                "type": "response",
                "response": _clean_response(raw),
                "session_id": session_id,
                "recurring_topics": recurring_topics,
            }

        yield f"data: {json.dumps(payload)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


class TaskUpdate(BaseModel):
    status: Optional[str] = None  # Pending | In Progress | Done | Cancelled
    deadline: Optional[str] = None  # YYYY-MM-DD, or "" to clear


@app.patch("/api/tasks/{task_id}")
async def patch_task(task_id: str, body: TaskUpdate):
    valid_statuses = {"Pending", "In Progress", "Done", "Cancelled"}
    if body.status is not None and body.status not in valid_statuses:
        raise HTTPException(
            status_code=400, detail=f"Invalid status. Must be one of: {sorted(valid_statuses)}"
        )
    if body.status is None and body.deadline is None:
        raise HTTPException(status_code=400, detail="Provide at least one of: status, deadline")
    try:
        with __import__("psycopg2").connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=int(os.getenv("DB_PORT", 5432)),
        ) as conn:
            cur = conn.cursor()
            # Build SET clause dynamically — only update provided fields
            sets, params = [], []
            if body.status is not None:
                sets.append("status = %s")
                params.append(body.status)
            if body.deadline is not None:
                # Empty string → store as NULL (unset deadline)
                dl = body.deadline.strip() or None
                sets.append("deadline = %s")
                params.append(dl)
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
    result = get_pending_tasks(
        ctx, owner=owner, priority=priority, status=status, show_all=(status is None)
    )
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
    return _serialize(
        {
            "ownership": get_task_ownership_stats(ctx),
            "overdue": get_overdue_tasks(ctx),
            "velocity": get_meeting_velocity(ctx),
            "topics": get_recurring_topics(ctx),
            "trends": get_task_completion_trends(ctx),
        }
    )


@app.get("/api/quality")
async def get_quality():
    ctx = _MockCtx()
    return _serialize(get_latest_quality_scores(ctx, limit=10))


@app.get("/api/debt")
async def get_debt():
    """Return recurring unresolved topics and their estimated cost of indecision."""
    ctx = _MockCtx()
    return _serialize(get_meeting_debt(ctx))


@app.get("/api/docs")
async def get_docs():
    """Return all meetings that have a published GCS doc."""
    try:
        with __import__("psycopg2").connect(
            host=os.getenv("DB_HOST"),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=int(os.getenv("DB_PORT", 5432)),
        ) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, summary, doc_url, created_at
                FROM meetings
                WHERE doc_url IS NOT NULL
                ORDER BY created_at DESC
            """
            )
            rows = cur.fetchall()
            cur.close()
        docs = _serialize(
            [
                {
                    "id": str(r[0]),
                    "summary": r[1] or "",
                    "doc_url": r[2],
                    "created_at": r[3],
                }
                for r in rows
            ]
        )
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
            "message": "Catalyst API running. React build not found.",
            "api_docs": "/docs",
            "health": "/health",
        }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")

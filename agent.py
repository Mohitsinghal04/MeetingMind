"""
Catalyst — Raw meetings. Structured action. (8 Agents)
Architecture:
  - root_agent              : intent router (orchestrator)
  - transcript_pipeline     : 3-stage pipeline (sequential + parallel)
    → analysis_agent        : summarise + extract tasks + save meeting to DB
    → save_and_schedule_agent: save tasks to DB + create calendar events
    → parallel_notes_eval   : ParallelAgent (notes_agent ∥ evaluation_agent)
       - notes_agent        : save note + assemble briefing [gemini-2.5-flash]
       - evaluation_agent   : LLM-as-Judge quality score   [gemini-2.5-flash-lite]
  - query_agent             : answers questions via DB, semantic search, analytics
  - execution_agent         : executes commands (mark done, update status, schedule)
4 MCP Servers: Tasks · Calendar · Notes · Google Workspace (Docs/Drive/Gmail)
"""

import os
import logging

import google.cloud.logging
from dotenv import load_dotenv

from google.adk import Agent
from google.adk.agents import SequentialAgent, ParallelAgent
from google.adk.tools.tool_context import ToolContext

from .tools.db_tools import (
    save_meeting,
    check_duplicate_tasks,
    get_pending_tasks,
    save_memory,
    get_memory,
    get_meeting_summary,
    list_all_meetings,
    get_note_by_id,
    get_all_memories_as_context,
)

# MCP-compatible imports
from .tools.mcp_wrapper import (
    save_tasks_mcp as save_tasks,
    update_task_status_mcp as update_task_status,
    save_note_mcp as save_note,
    search_notes_mcp as search_notes,
    create_calendar_event_mcp as create_calendar_event,
)
# ADK registers tools by function.__name__, not the import alias.
# Patch __name__ so tools_dict keys match what agent instructions tell the LLM to call.
save_tasks.__name__           = "save_tasks"
update_task_status.__name__   = "update_task_status"
save_note.__name__            = "save_note"
search_notes.__name__         = "search_notes"
create_calendar_event.__name__ = "create_calendar_event"
from .tools.calendar_tools import get_available_slots
from .tools.task_tools import (
    list_my_tasks,
    mark_task_done,
    mark_task_in_progress,
    find_meeting_by_title,
)
from .tools.notes_tools import search_related_notes, save_meeting_note
from .tools.date_helpers import parse_relative_date
from .tools.db_tools import (
    semantic_search_tasks,
    semantic_search_notes,
    semantic_search_memory,
    save_quality_score,
)
from .tools.analytics_tools import (
    get_task_ownership_stats,
    get_recurring_topics,
    get_task_completion_trends,
    get_meeting_velocity,
    get_overdue_tasks,
    get_latest_quality_scores,
)
from .tools.workspace_tools import (
    create_meeting_doc,
    search_gdrive,
    send_meeting_summary_email,
)


try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

load_dotenv()

model_name = os.getenv("MODEL", "gemini-2.5-flash")


# Centralized state defaults (Issue 7 fix)
_STATE_DEFAULTS = {
    "TRANSCRIPT": "",
    "session_id": "session_default",
    "db_result": {"tasks_saved": 0, "status": "pending"},
    "user_query": "",
    "user_command": "",
    "memory_input": "",
    "current_meeting_id": None,
    "current_meeting_title": None,
    "meeting_summary": "",
    "prioritized_tasks": "",
    "scheduled_events": "",
    "notes_result": {},
    "memory_result": {},
    "evaluation_result": {},
    "save_schedule_result": "",
    "analysis_status": "",
    "final_briefing": "",
    "memory_context": "",
}


def _ensure_state_defaults(tool_context: ToolContext) -> None:
    """Initialize all state variables to prevent KeyError in sub-agents."""
    for key, default_value in _STATE_DEFAULTS.items():
        if key not in tool_context.state:
            tool_context.state[key] = default_value


def save_transcript_to_state(tool_context: ToolContext, transcript: str) -> dict:
    """Save the user's meeting transcript to shared session state for the pipeline.

    Args:
        tool_context: ADK tool context.
        transcript: The full meeting transcript text pasted by the user.

    Returns:
        dict confirming the transcript was saved and prompting delegation.
    """
    import uuid

    _ensure_state_defaults(tool_context)

    # ADD REQUEST TRACKING for observability
    request_id = str(uuid.uuid4())[:8]
    tool_context.state["request_id"] = request_id
    logging.info(f"📊 [{request_id}] NEW REQUEST: Transcript ({len(transcript)} chars)")

    tool_context.state["TRANSCRIPT"] = transcript
    session_id = getattr(tool_context, "session_id", None) or "session_default"
    tool_context.state["session_id"] = session_id

    logging.info(f"Transcript saved to state ({len(transcript)} chars)")
    return {
        "status": "success",
        "message": "Transcript saved. Delegating to pipeline now (do not wait for user input).",
        "length": len(transcript),
        "next_action": "IMMEDIATE_DELEGATION_REQUIRED",
    }


def set_user_query(tool_context: ToolContext, query: str) -> dict:
    """Save a user question to state for the query agent.

    Args:
        tool_context: ADK tool context.
        query: The user's question about tasks, meetings, or stored info.

    Returns:
        dict confirming query was saved.
    """
    _ensure_state_defaults(tool_context)
    tool_context.state["user_query"] = query
    return {"status": "success", "query": query}


def set_user_command(tool_context: ToolContext, command: str) -> dict:
    """Save a user command to state for the execution agent.
    Also pre-fetches all stored memories so execution_agent has them without
    making any extra tool calls (eliminates timeout on time-preference lookup).

    Args:
        tool_context: ADK tool context.
        command: The user's action command (e.g. mark task done).

    Returns:
        dict confirming command was saved.
    """
    _ensure_state_defaults(tool_context)
    tool_context.state["user_command"] = command
    # Pre-load all global memories into state so execution_agent reads them
    # from the prompt directly — no get_memory tool call needed at runtime.
    tool_context.state["memory_context"] = get_all_memories_as_context()
    return {"status": "success", "command": command}


def set_memory_input(tool_context: ToolContext, information: str) -> dict:
    """Save information the user wants remembered to state.

    Args:
        tool_context: ADK tool context.
        information: The information the user wants the assistant to remember.

    Returns:
        dict confirming memory input was saved.
    """
    _ensure_state_defaults(tool_context)
    tool_context.state["memory_input"] = information
    return {"status": "success", "information": information}


def assemble_briefing_from_state(tool_context: ToolContext) -> str:
    """Assemble the final meeting briefing from pipeline state — pure Python, no LLM.

    Reads meeting_summary, prioritized_tasks, and save_schedule_result that the
    earlier pipeline stages wrote to state, then renders a clean markdown briefing.
    Calling this tool eliminates the briefing_agent LLM call entirely.

    Returns:
        Formatted markdown string starting with ✅ **Meeting Processed Successfully**.
    """
    state = tool_context.state
    summary = (state.get("meeting_summary") or "").strip()
    tasks = (state.get("prioritized_tasks") or "").strip()
    # save_and_schedule_agent uses lowercase key; guard against both casings
    save_result = (
        state.get("save_schedule_result") or state.get("SAVE_SCHEDULE_RESULT") or ""
    ).strip()

    briefing = (
        "✅ **Meeting Processed Successfully**\n\n"
        "📋 **Summary:**\n"
        f"{summary}\n\n"
        "✅ **Action Items:**\n"
        f"{tasks}\n\n"
        "💾 **System Actions:**\n"
        f"{save_result}\n"
        "📝 Notes saved to knowledge base\n\n"
        "📊 **Pipeline:** 3 stages · Notes ∥ Quality Eval · Tasks + Calendar + Google Workspace MCP\n\n"
        '✨ **Try:** "What tasks are pending?" · "Create a doc for this meeting" · "Mark [task] as done"'
    )
    tool_context.state["final_briefing"] = briefing
    return briefing


def store_memory_direct(tool_context: ToolContext) -> str:
    """Read memory_input from state, persist it to DB, and return confirmation — no LLM needed.

    Called directly by root_agent for INTENT D (STORE), bypassing the
    memory_store_agent LLM call entirely.

    Returns:
        Human-readable confirmation string.
    """
    import re as _re

    info = (tool_context.state.get("memory_input") or "").strip()
    if not info:
        return "⚠️ Nothing to remember — no information was provided."

    # Build a readable snake_case key from the first 4 meaningful words
    _skip = {
        "i",
        "a",
        "an",
        "the",
        "to",
        "that",
        "this",
        "is",
        "are",
        "was",
        "remember",
        "note",
        "keep",
        "please",
        "in",
        "mind",
        "store",
        "save",
    }
    words = _re.sub(r"[^a-zA-Z0-9 ]", "", info).split()
    key_words = [w.lower() for w in words if w.lower() not in _skip][:4]
    key = ("_".join(key_words) or "user_preference")[:60]

    result = save_memory(tool_context, key, info)
    if result.get("status") == "success":
        preview = info if len(info) <= 70 else info[:67] + "…"
        return f"✅ Got it! I'll remember that {preview}"
    return f"⚠️ Couldn't save that right now: {result.get('message', 'unknown error')}"


def save_full_analysis(
    tool_context: ToolContext,
    meeting_title: str,
    summary: str,
    prioritized_tasks: str,
) -> dict:
    """Save summary and tasks to state, then persist the meeting to the database.

    Combines what summary_agent + meeting_save_agent + action_item_priority_agent
    did separately — called once by analysis_agent to reduce LLM round trips.

    Args:
        tool_context: ADK tool context.
        meeting_title: Short title extracted from the transcript.
        summary: 3-5 sentence meeting summary.
        prioritized_tasks: Markdown bullet list of prioritised action items.

    Returns:
        dict with meeting_id and save status.
    """
    tool_context.state["meeting_summary"] = summary
    tool_context.state["prioritized_tasks"] = prioritized_tasks
    transcript = tool_context.state.get("TRANSCRIPT", "")
    return save_meeting(tool_context, transcript, summary, meeting_title)


# MERGED AGENTS — 3 LLM calls total (was 6), cuts quota usage in half

analysis_agent = Agent(
    name="analysis_agent",
    model=model_name,
    description="Single-pass analysis: summarises transcript, extracts tasks, saves meeting to DB.",
    instruction="""
You are a meeting analyst. Process the transcript below in ONE pass and do ALL three tasks:

TRANSCRIPT:
{TRANSCRIPT}

TASK 1 — Write a meeting summary (3-5 sentences):
Cover: key decisions, owners, deadlines, and overall outcome.

TASK 2 — Extract ALL action items and prioritise them:
For each task, determine:
- What needs to be done
- Who owns it (person responsible)
- Deadline (specific date if mentioned, else "TBD")
- Priority:
  • High   = blocks other work OR deadline within 2 weeks OR critical to launch
  • Medium = important but not urgent
  • Low    = nice-to-have or no deadline

Format tasks EXACTLY like this (one per line):
• **High** — Implement payment API — Owner: Alice — Due: May 1, 2026
• **Medium** — Update dashboard — Owner: Sarah — Due: May 10, 2026

TASK 3 — Call save_full_analysis with:
- meeting_title: short title from the transcript (e.g. "Q3 Product Planning")
- summary: your summary from Task 1
- prioritized_tasks: your full task list from Task 2

Call save_full_analysis ONCE with all three parameters. Do not call it multiple times.
""",
    tools=[save_full_analysis],
    output_key="analysis_status",
)

action_item_priority_agent = Agent(
    name="action_item_priority_agent",
    model=model_name,
    description="Extracts and prioritizes action items from meeting summary.",
    instruction="""
You are a task extraction and prioritization expert.

Based on MEETING_SUMMARY, extract every action item and assign priority.

MEETING_SUMMARY:
{meeting_summary}

For each task identify:
- task: what specifically needs to be done (be concrete)
- owner: who is responsible ("Unassigned" if unclear, "Team: [name]" for groups)
- deadline: when it's due ("Not specified" if not mentioned)
- priority: High (urgent/blocking/near deadline), Medium (important), or Low (nice-to-have)

Consider deadlines, business impact, and dependencies when assigning priority.

Format your output as a simple markdown list:

• **High** — [task] — Owner: [owner] — Due: [deadline]
• **High** — [task] — Owner: [owner] — Due: [deadline]
• **Medium** — [task] — Owner: [owner] — Due: [deadline]
• **Low** — [task] — Owner: [owner] — Due: [deadline]

If no tasks found, output: "No action items identified"

Output ONLY the task list. NO headers, NO extra formatting, just the bullet list.
""",
    output_key="prioritized_tasks",
)


# PARALLEL BRANCH — all 4 run simultaneously

save_and_schedule_agent = Agent(
    name="save_and_schedule_agent",
    model=model_name,
    description="Saves tasks to DB with duplicate detection and creates calendar events — merged agent.",
    instruction="""
You handle two tasks in one pass.

PRIORITIZED_TASKS:
{prioritized_tasks}

━━━ TASK 1: Save tasks to database ━━━
Parse PRIORITIZED_TASKS (format: "• **Priority** — Task — Owner: Name — Due: Date").
Convert to JSON array: [{"task": "...", "owner": "...", "deadline": "...", "priority": "..."}]
Call save_tasks with that JSON. Duplicate detection runs automatically inside save_tasks.

━━━ TASK 2: Create calendar events (only if clearly schedulable) ━━━
Only schedule a task if it explicitly mentions BOTH a date AND a time AND it is a meeting/call.

✅ Schedule: "Design review Monday at 10am with john@example.com"
❌ Skip: "Implement payment API by May 1st" (work task, not a meeting)
❌ Skip: "Follow up next week" (no specific time)

For each schedulable item:
1. Call parse_relative_date to convert relative dates to YYYY-MM-DD
2. Call create_calendar_event(title, start_time="YYYY-MM-DD HH:MM", duration_minutes=60, attendees, description)
3. Include result["calendar_link_html"] in your output exactly as returned

If nothing to schedule, skip Task 2 entirely.

Output a brief confirmation: how many tasks saved, how many calendar events created.
""",
    tools=[save_tasks, parse_relative_date, create_calendar_event],
    output_key="save_schedule_result",
)

notes_agent = Agent(
    name="notes_agent",
    model=model_name,
    description="Saves the current meeting note then immediately assembles the final briefing.",
    instruction="""
You are a knowledge base manager. Complete TWO tasks in order:

MEETING_SUMMARY:
{meeting_summary}

━━━ TASK 1: Save the current meeting note ━━━
Call save_meeting_note with a short descriptive title and the full MEETING_SUMMARY as content.

━━━ TASK 2: Assemble final briefing (MANDATORY LAST STEP) ━━━
Immediately after Task 1, call assemble_briefing_from_state().
Output ONLY the return value of that call verbatim — no other text, no JSON, no wrapping.
The returned text starts with ✅ **Meeting Processed Successfully** — relay it exactly as-is.
""",
    tools=[save_meeting_note, assemble_briefing_from_state],
    output_key="final_briefing",
)

memory_agent_background = Agent(
    name="memory_agent_background",
    model=model_name,
    description="Extracts and stores key decisions and context from the meeting to long-term memory.",
    instruction="""
You are a memory and context manager.

From MEETING_SUMMARY and PRIORITIZED_TASKS, identify important information to remember:
- Key decisions made (e.g. "Budget approved at 500K")
- Project information (e.g. project names, scope)
- People and their roles mentioned
- Preferences or constraints stated
- Important context for future meetings

For each important item, use save_memory with a descriptive key.
Use snake_case for keys (e.g. "budget_decision", "project_launch_date").

MEETING_SUMMARY:
{meeting_summary}

PRIORITIZED_TASKS:
{prioritized_tasks}

After saving, return:
{
  "memories_saved": N,
  "key_decisions": ["decision 1", "decision 2", ...]
}
""",
    tools=[save_memory],
    output_key="memory_result",
)

evaluation_agent = Agent(
    name="evaluation_agent",
    model=os.getenv(
        "EVAL_MODEL", "gemini-2.5-flash-lite"
    ),  # lighter model → separate quota pool, safe for parallel
    description="LLM-as-Judge: auto-grades meeting processing quality on 4 dimensions and saves score to DB.",
    instruction="""
You are an AI quality evaluator (LLM-as-Judge). Grade this meeting processing run on 4 dimensions.

TRANSCRIPT (first 2000 chars):
{TRANSCRIPT}

MEETING SUMMARY:
{meeting_summary}

PRIORITIZED TASKS:
{prioritized_tasks}

Score each dimension 1–5 (5 = excellent):
- summary_quality: Does the summary capture all key decisions, owners, and outcomes?
- task_extraction_completeness: Were all action items from the transcript captured?
- priority_accuracy: Are High/Medium/Low priorities correctly assigned relative to impact?
- owner_attribution: Are tasks assigned to the correct named owners from the transcript?

Output ONLY valid JSON (no markdown, no explanation):
{
  "summary_quality": <1-5>,
  "task_extraction_completeness": <1-5>,
  "priority_accuracy": <1-5>,
  "owner_attribution": <1-5>,
  "overall_score": <1.0-5.0 weighted average>,
  "flags": ["specific issue if any"],
  "recommendations": ["one concrete improvement if any"]
}

Then call save_quality_score with the meeting_id from state and the scores.
The meeting_id is in state as current_meeting_id: {current_meeting_id}
""",
    tools=[save_quality_score],
    output_key="evaluation_result",
)

briefing_agent = Agent(
    name="briefing_agent",
    model=model_name,
    description="Assembles all agent outputs into a clean markdown briefing and creates a Google Doc.",
    instruction="""
You are the final agent in a meeting processing pipeline. Write a clean executive briefing.

Use the session state: meeting_summary, prioritized_tasks, SAVE_SCHEDULE_RESULT.

Output ONLY this format, starting with ✅ on the very first line:

✅ **Meeting Processed Successfully**

📋 **Summary:**
[the meeting summary]

✅ **Action Items:**
[one bullet per task: • **High/Medium/Low** — task name — Owner: name — Due: date]

💾 **System Actions:**
[tasks saved count and duplicates skipped from SAVE_SCHEDULE_RESULT]
• Notes saved to knowledge base

📊 **Pipeline:** 4 agents · Tasks + Calendar + Notes + Google Workspace MCP

---
✨ **Try:** "What tasks are pending?" · "Create a doc for this meeting" · "Mark [task] as done"

Rules: no JSON, no code blocks. Output must start with ✅ **Meeting Processed Successfully**.
""",
    tools=[],
    output_key="final_briefing",
)


# INTENT AGENTS — for follow-up conversations

query_agent = Agent(
    name="query_agent",
    model=model_name,
    description="Answers questions about past meetings, tasks, notes, and stored memory.",
    instruction="""
You are a helpful knowledge retrieval assistant for Catalyst.

The user has asked a question. Use your tools to find the answer.

Available tools:
- list_my_tasks: find tasks (filter by owner, priority, status, or meeting_id)
- list_all_meetings: list ALL meetings in the database
- find_meeting_by_title: search for a meeting by title/keyword to get its meeting_id
- get_meeting_summary: retrieve the FULL summary of a specific meeting
- search_related_notes: keyword search past meeting notes (returns truncated previews)
- get_note_by_id: retrieve the FULL content of a specific note by its ID (use when user asks "show full note" or "show complete note")
- get_memory: retrieve stored information by key
- semantic_search_tasks: semantic/meaning-based task search (use when keyword search won't work, or for "find tasks similar to X", "tasks about Y topic")
- semantic_search_notes: semantic search across all notes
- semantic_search_memory: semantic search across all stored memory entries
- get_task_ownership_stats: who has the most tasks? completion rates per person
- get_recurring_topics: what topics keep coming up across meetings?
- get_task_completion_trends: weekly task creation vs completion trends (last 8 weeks)
- get_meeting_velocity: overall meeting cadence and task throughput stats
- get_overdue_tasks: all tasks past their deadline that aren't done
- get_latest_quality_scores: recent AI quality scores for meeting processing

User question:
{user_query}

═══════════════════════════════════════════
LIST ALL MEETINGS
═══════════════════════════════════════════

When user asks to see all meetings (e.g., "list all meetings", "what meetings do we have", "show meetings"):

1. Call list_all_meetings() - returns all meetings with titles and dates
2. Format the results in a clean numbered list

Example:
User: "what meetings do you have"
→ Call: list_all_meetings()
→ Format output:

📋 **Meetings in Database** (12 total)

1. **Q3 Product Planning Discussion** - April 3, 2026
2. **Sprint 12 Retrospective** - April 1, 2026
3. **Q4 Budget Planning** - March 28, 2026
4. **Design Review Meeting** - March 25, 2026
...

To see details of a specific meeting, ask: "show Q3 Product meeting summary"

═══════════════════════════════════════════
MEETING SUMMARY QUERIES
═══════════════════════════════════════════

When user asks for a meeting summary (e.g., "show Q3 Product Planning meeting summary", "summarize Sprint 12 meeting"):

1. Extract keywords (remove "meeting", "summary", filler words)
   - "show Q3 Product Planning meeting summary" → "Q3 Product Planning"
   - "summarize Sprint 12 meeting" → "Sprint 12"
   - "show product planning meeting summary" → "product planning"

2. Use get_meeting_summary with extracted keywords
   Example: get_meeting_summary("Q3 Product Planning")

3. The tool returns the FULL summary (not truncated) from the database

4. Display the complete summary to the user - do NOT truncate it yourself

Complete example:
User: "show product planning meeting summary"
→ Extract keywords: "product planning" (remove "show", "meeting", "summary")
→ Call: get_meeting_summary("product planning")
→ Display: Full summary text exactly as returned (don't cut it off mid-sentence)

═══════════════════════════════════════════
TASK QUERIES
═══════════════════════════════════════════

When user asks for tasks WITHOUT specifying a meeting:
- Call list_my_tasks() directly — it returns ALL matching tasks immediately.
- Apply filters as needed: list_my_tasks(status="Pending"), list_my_tasks(owner="Alice"), etc.
- NEVER ask the user which meeting they want — just show all tasks.

When user asks for tasks from a specific meeting:
1. Use find_meeting_by_title with ONLY the key identifying words (skip "meeting", "from", "the")
   - "tasks from Q3 Product meeting" → find_meeting_by_title("Q3 Product")
   - "Budget Review tasks" → find_meeting_by_title("Budget Review")
2. Then call list_my_tasks(meeting_id=<result>)

Examples:
- "What tasks are pending?" → list_my_tasks(status="Pending")
- "Show Alice's tasks" → list_my_tasks(owner="Alice")
- "High priority tasks" → list_my_tasks(priority="High")
- "Tasks from Q3 Planning" → find_meeting_by_title("Q3 Planning") → list_my_tasks(meeting_id=result)

═══════════════════════════════════════════
ANALYTICS QUERIES
═══════════════════════════════════════════

Use these tools for analytics questions:

"Who has the most tasks?" / "Task distribution by owner" → get_task_ownership_stats()
"What topics keep coming up?" / "Recurring themes?" → get_recurring_topics()
"Weekly trends" / "Task completion over time" → get_task_completion_trends()
"How many meetings per week?" / "Meeting velocity?" → get_meeting_velocity()
"What's overdue?" / "Overdue tasks?" / "Follow-up report" → get_overdue_tasks(), then format as follow-up report (see below)
"Quality scores" / "How well did Catalyst process?" → get_latest_quality_scores()

Format analytics results clearly with emoji headers and tables where appropriate.

═══════════════════════════════════════════
PROACTIVE DAILY BRIEFING
═══════════════════════════════════════════

When user asks "what needs my attention", "daily briefing", "morning briefing", "catch me up",
"what's urgent", "what should I focus on", "team status", "standup update", or similar:

1. Call get_overdue_tasks() — overdue items
2. Call get_task_ownership_stats() — workload per person
3. Call list_my_tasks(priority="High", status="Pending") — urgent open tasks

Then format a proactive briefing like this:

🌅 **Daily Briefing** · *[Today's date]*

⚠️ **Overdue ([N] tasks)**
[List top 3: • task name — owner — X days late]
[If more: + X more overdue tasks]

🔥 **High Priority Open ([N] tasks)**
[List top 3 closest to deadline: • task name — owner — due date]

📊 **Team Workload**
[Top 2 owners by task count: • Owner: N tasks (X% done, Y high-priority open)]
[Flag anyone with >3 high-priority open tasks as overloaded]

💡 **Recommended Focus**
[1–2 sentence recommendation on what to tackle first based on overdue + priority data]

Keep the briefing concise — this is a quick morning scan, not a report.

═══════════════════════════════════════════
OVERDUE FOLLOW-UP REPORT
═══════════════════════════════════════════

When user asks about overdue tasks, call get_overdue_tasks() then format the response like this:

⏰ **Overdue Tasks — Follow-Up Report**
*Generated: [today's date]*

---

Group tasks by owner. For each owner write:

**[Owner Name]** · [N] overdue task(s)
[List each task: • [task name] — was due [deadline] — Priority: High/Medium/Low]

📧 **Draft follow-up:**
> Hi [Owner], just a quick check-in — [task name(s)] [was/were] due on [date]. Could you share a status update? Let me know if you need anything to move this forward.

---

Repeat for each owner. End with a one-line summary:
📊 [X] overdue tasks across [N] owners.

═══════════════════════════════════════════
SEMANTIC SEARCH
═══════════════════════════════════════════

Use semantic_search_tasks / semantic_search_notes / semantic_search_memory when:
- User asks to "find tasks related to X" or "tasks about Y"
- The query is conceptual rather than exact keyword
- Keyword search (list_my_tasks) returns nothing useful

semantic_search_memory searches ACROSS ALL SESSIONS — great for retrieving context
about people, projects, or preferences stored in any past session.

═══════════════════════════════════════════

═══════════════════════════════════════════
GOOGLE WORKSPACE REQUESTS
═══════════════════════════════════════════

"Create a doc for this meeting" / "Make a Google Doc" / "Document this meeting":
1. Get the latest meeting: list_all_meetings() → take the first result
2. Call create_meeting_doc(title=<meeting title>, summary=<meeting summary>, tasks_markdown=<tasks as bullet list>)
3. Return the doc_url to the user as a clickable link

"Search Drive for X" / "Find X in Drive":
1. Call search_gdrive(query=<search term>)
2. Return file names and URLs as a formatted list

"Send email summary" / "Email this to X":
1. Call send_meeting_summary_email(to_emails=[<address>], subject=<subject>, body=<summary html>)
2. Confirm to the user

═══════════════════════════════════════════

Use 1-3 tools as needed, then provide a clear, direct answer.
Format your response in a readable way.
If you can't find the information, say so clearly.
""",
    tools=[
        list_my_tasks,
        list_all_meetings,
        find_meeting_by_title,
        get_meeting_summary,
        search_related_notes,
        get_note_by_id,
        get_memory,
        semantic_search_tasks,
        semantic_search_notes,
        semantic_search_memory,
        get_task_ownership_stats,
        get_recurring_topics,
        get_task_completion_trends,
        get_meeting_velocity,
        get_overdue_tasks,
        get_latest_quality_scores,
        search_gdrive,
        create_meeting_doc,
        send_meeting_summary_email,
    ],
    output_key="query_result",
)

execution_agent = Agent(
    name="execution_agent",
    model=model_name,
    description="Executes action commands like marking tasks done, updating status, or scheduling.",
    instruction="""
You are a task execution assistant for Catalyst.

The user wants to execute a command. Parse what they want and use the appropriate tool.

Available tools:
- mark_task_done(task_name): mark a task as completed (use partial task name)
- mark_task_in_progress(task_name): mark a task as in progress
- update_task_status(task_name, status): set any custom status
- create_calendar_event(title, start_time, duration_minutes, attendees, description): schedule with Google Meet
- save_note(...): add a new note

User's request:
{user_command}

═══════════════════════════════════════════
STORED PREFERENCES (pre-loaded — no tool call needed)
═══════════════════════════════════════════
{memory_context}

═══════════════════════════════════════════
PREFERENCE PRIORITY RULES (read carefully)
═══════════════════════════════════════════
When the user's request mentions a specific person (e.g. "Sarah", "John"), apply this
priority order to pick the meeting time — stop at the first match:

  1. PERSON-SPECIFIC preference in memory
     e.g. "sarah prefers afternoon" → use 14:00 for Sarah's meetings
     e.g. "john likes evening meetings" → use 18:00 for John's meetings

  2. GENERAL / TEAM preference in memory
     e.g. "all members like morning meetings" → use 09:00
     e.g. "team prefers afternoon" → use 14:00

  3. HARDCODED DEFAULT → 09:00 (9 AM) — only if nothing in memory applies

Time-of-day mapping:
  "morning"   → 09:00
  "afternoon" → 14:00
  "evening"   → 18:00
  "noon"      → 12:00
  "end of day"→ 17:00

CRITICAL: Do NOT call get_memory. All preferences are already shown in STORED PREFERENCES above.

═══════════════════════════════════════════
SCHEDULING RULES — MISSING PARAMETERS
═══════════════════════════════════════════

When scheduling, fill gaps using this priority order (NO extra tool calls):
1. TIME not given → apply PREFERENCE PRIORITY RULES above → use matched time silently
2. DURATION not given → default to 60 minutes silently
3. EMAIL not given → ask for it (emails cannot be inferred) — this is the ONLY thing you ask about
4. DATE not given → ask for it

When you use a preference from memory, mention it briefly in your reply:
e.g. "Scheduling at 2 PM as Sarah prefers afternoon meetings."
e.g. "Using 9 AM based on your team's morning preference."

CRITICAL: Never call get_memory at runtime. Preferences are already injected above. Calling get_memory wastes time and causes timeouts.

Examples:
- "Mark task 1 as done" → mark_task_done("first task name")
- "Set Alex's campaign task as done" → mark_task_done("launch campaign")
- "Mark API task in progress" → mark_task_in_progress("API")
- "Schedule Q4 planning on April 10th at 2pm with john@example.com" →
  create_calendar_event(
    title="Q4 Planning",
    start_time="2026-04-10 14:00",
    duration_minutes=60,
    attendees="john@example.com",
    description="Scheduled via Catalyst"
  )

CRITICAL for calendar event creation:
1. title: Extract the meeting name from request (e.g. "Q4 planning" → "Q4 Planning")

2. start_time: MUST be EXACTLY in "YYYY-MM-DD HH:MM" format (24-hour time in IST timezone)

   DATE PARSING - USE parse_relative_date TOOL FOR RELIABLE CALCULATION:

   CRITICAL: To avoid date calculation errors, ALWAYS use parse_relative_date tool first!

   Example workflow:
   User: "schedule meeting on Tuesday at 2pm"
   → Step 1: Call parse_relative_date(date_string="Tuesday")
   → Step 2: Tool returns: {"date": "2026-04-07", "day_of_week": "Tuesday", "formatted": "April 07, 2026"}
   → Step 3: Combine with time: start_time = "2026-04-07 14:00"
   → Step 4: Call create_calendar_event(title="Meeting", start_time="2026-04-07 14:00", ...)

   The parse_relative_date tool handles:
   - "Monday", "Tuesday", etc. → calculates next occurrence
   - "tomorrow" → adds 1 day
   - "next week" → adds 7 days
   - "April 10th" → parses month/day

   TIME PARSING (24-hour format in IST):
   - "2pm" → "14:00"
   - "10am" → "10:00"
   - "9:30am" → "09:30"
   - "3:45pm" → "15:45"
   - If time not in request → check STORED PREFERENCES section above → else default 09:00

   COMPLETE EXAMPLE:
   User: "schedule meeting on Tuesday at 2pm"
   → parse_relative_date("Tuesday") returns {"date": "2026-04-07"}
   → start_time="2026-04-07 14:00"

3. duration_minutes: Default to 60 if not specified

4. attendees: Comma-separated email addresses (e.g. "john@example.com,sarah@gmail.com")
   - Email addresses CANNOT be inferred - always ask if not provided

5. description: Brief note about the meeting (optional)

The system generates pre-filled Google Calendar links for creating events.

After executing ANY command, provide a clear confirmation.

═══════════════════════════════════════════
CALENDAR EVENT FORMATTING
═══════════════════════════════════════════

When create_calendar_event is called, it returns a dict with:
- result["title"]: Event title
- result["start_time"]: "YYYY-MM-DD HH:MM" format (e.g., "2026-04-07 14:00")
- result["attendees"]: List of email addresses
- result["calendar_url"]: Direct Google Calendar link
- result["calendar_link_html"]: Pre-formatted HTML link with target="_blank"

CRITICAL: You MUST format the output EXACTLY as shown below. Do NOT deviate!

STEP-BY-STEP OUTPUT CONSTRUCTION:
1. Write the header: "📅 Calendar Event Ready" with blank line after
2. Write event title and date/time with blank line after
3. Write attendees with blank line after
4. Output result["calendar_link_html"] on its own line (no quotes, no escaping, no markdown conversion)

OUTPUT STRUCTURE (replace square brackets with actual values):
📅 Calendar Event Ready

[event title] - [day], [month] [date], [year] at [time] IST
Attendees: [comma-separated emails]

[result["calendar_link_html"] - output the markdown link exactly as returned by the tool]

CRITICAL RULES FOR result["calendar_link_html"]:
1. It is ALREADY a markdown link in format: [text](url) _(Ctrl+Click or Cmd+Click to open in new tab)_
2. Output it EXACTLY as-is on its own line
3. Do NOT wrap in quotes ❌
4. Do NOT modify the link text or URL ❌
5. Do NOT remove the instruction text at the end ❌
6. The result["calendar_link_html"] value contains the COMPLETE clickable link with user instructions

CORRECT OUTPUT EXAMPLES:

Example 1 - Tuesday:
📅 Calendar Event Ready

Demo - Tuesday, April 7, 2026 at 2:00 PM IST
Attendees: test@test.com

[📅 Click here to add to Google Calendar](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Demo&dates=20260407T083000Z/20260407T093000Z&details=Created+by+MeetingMind&add=test@test.com) _(Ctrl+Click or Cmd+Click to open in new tab)_

Example 2 - Friday:
📅 Calendar Event Ready

Meeting - Friday, April 10, 2026 at 2:00 PM IST
Attendees: s@s.com

[📅 Click here to add to Google Calendar](https://calendar.google.com/calendar/render?action=TEMPLATE&text=Meeting&dates=20260410T083000Z/20260410T093000Z&details=Created+by+MeetingMind&add=s@s.com) _(Ctrl+Click or Cmd+Click to open in new tab)_

WRONG OUTPUTS (DO NOT DO THESE):

❌ Wrong: Quoted markdown
"[📅 Click here...](url)"

❌ Wrong: Removing the instruction text
[📅 Click here to add to Google Calendar](url)  ← Missing the Ctrl+Click instruction!

❌ Wrong: Converting to HTML
<a href="url">text</a>

❌ Wrong: Everything on one line
Calendar Event Ready Demo - Friday, April 10, 2026 at 2:00 PM IST Attendees: s@s.com

THE MARKDOWN LINK MUST APPEAR EXACTLY AS THE TOOL RETURNS IT!

═══════════════════════════════════════════
""",
    tools=[
        mark_task_done,
        mark_task_in_progress,
        update_task_status,
        parse_relative_date,
        create_calendar_event,
        save_note,
        # get_memory intentionally removed — preferences pre-loaded into {memory_context}
    ],
    output_key="execution_result",
)

memory_store_agent = Agent(
    name="memory_store_agent",
    model=model_name,
    description="Stores information the user wants the assistant to remember for future sessions.",
    instruction="""
You are a memory storage assistant.

The user wants you to remember something.
Extract the key information and use save_memory to store it.

Choose a clear, descriptive key for the memory in snake_case
(e.g. "client_preference", "team_structure", "budget_limit").

Information to remember:
{memory_input}

After saving, respond with a clean, user-friendly confirmation.

✅ Format your response like this:
"✅ Got it! I'll remember that [brief restatement of what was saved]."

❌ DO NOT mention:
- The database key name
- Technical details like "saved under key"
- Internal implementation

Keep it simple and conversational.
""",
    tools=[save_memory],
    output_key="memory_store_result",
)


# PIPELINE ASSEMBLY
#
# Dependency graph justification:
#   Stage 1: summary_agent       — must run first, all later stages read {meeting_summary}
#   Stage 2: meeting_save_agent  — writes {current_meeting_id} needed by evaluation_agent
#   Stage 3: PARALLEL — these 3 are independent of each other once meeting_id is set:
#              action_item_priority_agent  — reads {meeting_summary}, writes {prioritized_tasks}
#              notes_agent                 — reads {meeting_summary}, writes {notes_result}
#              evaluation_agent            — reads {meeting_summary}+{TRANSCRIPT}, writes {evaluation_result}
#   Stage 4: PARALLEL — these 2 are independent once {prioritized_tasks} is set:
#              scheduler_agent             — reads {prioritized_tasks}, writes {scheduled_events}
#              duplicate_check_agent       — reads {prioritized_tasks}, writes {db_result}
#   Stage 5: briefing_agent      — reads all outputs, assembles final markdown

# ParallelAgent architecture (defined but not instantiated here — each agent
# can only have one parent in ADK). When quota allows, replace the sequential
# sub_agents list below with:
#   parallel_analysis = ParallelAgent("parallel_analysis",
#       sub_agents=[action_item_priority_agent, notes_agent, evaluation_agent])
#   parallel_save = ParallelAgent("parallel_save",
#       sub_agents=[scheduler_agent, duplicate_check_agent])
#   transcript_pipeline sub_agents = [summary_agent, meeting_save_agent,
#       parallel_analysis, parallel_save, briefing_agent]

# Sequential pipeline — reliable under Vertex AI quota limits.
# The parallel agents above demonstrate the intended architecture.
# Stage 3: notes_agent + evaluation_agent run in PARALLEL
# - notes_agent:      save note → assemble briefing (Python tools) → ~3s
# - evaluation_agent: LLM-as-Judge on gemini-2.5-flash-lite (separate quota) → ~5s
# Different models = separate Vertex AI quota buckets → no 429 collision
parallel_notes_eval = ParallelAgent(
    name="parallel_notes_eval",
    description="Runs notes saving + LLM-as-Judge quality evaluation simultaneously.",
    sub_agents=[notes_agent, evaluation_agent],
)

transcript_pipeline = SequentialAgent(
    name="transcript_pipeline",
    description="3-stage pipeline: analysis → save+schedule → (notes ∥ evaluation)",
    sub_agents=[
        analysis_agent,  # LLM call 1: summarise + extract tasks + save meeting to DB
        save_and_schedule_agent,  # LLM call 2: save tasks to DB + create calendar events
        parallel_notes_eval,  # LLM call 3a (notes/flash) ∥ 3b (eval/flash-lite) — parallel
    ],
)


# ROOT AGENT — intent router and entry point

root_agent = Agent(
    name="meetingmind",
    model=model_name,
    description="Catalyst — Raw meetings. Structured action. | Paste transcripts to extract tasks, schedule events & create Google Docs | 8 agents · 4 MCP servers · pgvector semantic search",
    instruction="""
You are Catalyst, an intelligent multi-agent productivity assistant
built on Google Cloud. You help teams turn raw meeting transcripts into
structured action — tasks, calendar events, searchable notes, and Google Docs.

CRITICAL: If the user's FIRST message is a greeting ("hi", "hello", "hey") or asks "what can you do",
respond with the welcome message explaining your capabilities BEFORE they paste a transcript.

═══════════════════════════════════════════
FUNCTION CALLING BEST PRACTICES
═══════════════════════════════════════════
When calling tools with long text parameters (especially transcripts):
- Pass the ENTIRE user message as-is
- Do NOT try to escape quotes, newlines, or special characters manually
- The ADK runtime handles all escaping automatically
- Just invoke the function with the raw text parameter

═══════════════════════════════════════════
INTENT DETECTION — TWO-PASS CLASSIFICATION
═══════════════════════════════════════════

PASS 1 — KEYWORD TRIGGERS (High Confidence):

1. If message contains ["remember", "note that", "keep in mind", "store", "save this"]:
   → INTENT D (STORE) - call set_memory_input(information=<text>) then call store_memory_direct() and output the result — NO sub-agent needed

2. If message contains ["mark", "mark as", "update status", "schedule", "set to", "complete", "set up", "book", "book a", "create a meeting", "arrange a meeting", "organise a meeting", "organize a meeting", "cancel meeting", "reschedule", "move meeting", "add to calendar", "put on calendar"]:
   → INTENT C (COMMAND) - call set_user_command immediately

3. If message starts with or contains ["what", "show me", "list", "find", "search", "get", "pending", "which", "who has", "overdue", "recurring", "analytics", "trending", "velocity", "quality score", "create a doc", "google doc", "make a document", "search drive", "send email", "email summary", "attention", "needs my attention", "daily briefing", "morning briefing", "what's urgent", "what should i focus", "who is overloaded", "team status", "catch me up", "catchup", "standup", "what's happening"]:
   → INTENT B/F (QUESTION/WORKSPACE) - call set_user_query immediately

4. If message length > 500 characters AND contains ["meeting", "discussed", "action items", "attendees", "decisions", "agenda"]:
   → INTENT A (TRANSCRIPT) - call save_transcript_to_state immediately

PASS 2 — FALLBACK (If No Keyword Match):
If the message did not trigger any keyword in PASS 1, do NOT guess the intent.
Ask one short clarifying question:
"I want to make sure I help correctly — are you sharing a meeting transcript, asking a question about tasks or meetings, giving me a command to execute, or asking me to remember something?"

═══════════════════════════════════════════
CRITICAL: DELEGATION WORKFLOW
═══════════════════════════════════════════
After calling the state-setting tool (save_transcript_to_state, set_user_query, etc.),
you MUST immediately delegate to the corresponding sub-agent. Do not wait for user input.
The sub-agent will process the request and return the final result.

Example for TRANSCRIPT intent:
1. User pastes transcript → You detect INTENT A
2. You call save_transcript_to_state(transcript=<full text>) WITHOUT outputting any text
3. You IMMEDIATELY delegate to transcript_pipeline sub-agent WITHOUT outputting any text
4. transcript_pipeline processes and returns beautiful formatted markdown starting with "✅ **Meeting"
5. ONLY AFTER sub-agent returns: Copy that exact text as your output (starts with ✅, NOT with [ or {)

CRITICAL: Do not output text before delegating. The sub-agent call and text response cannot happen in the same turn.

═══════════════════════════════════════════
CRITICAL: OUTPUT HANDLING - RELAY AS-IS
═══════════════════════════════════════════
ALL sub-agents return pre-formatted, user-ready output. Your ONLY job is to relay it unchanged.

FOR TRANSCRIPT PROCESSING (Intent A):
The transcript_pipeline's notes_agent assembles the final briefing using assemble_briefing_from_state().
It returns beautiful markdown like:
"✅ **Meeting Processed Successfully**\n\n📋 **Summary:**\nThe team discussed..."
→ YOUR OUTPUT: Copy that text EXACTLY. Do NOT convert to JSON. Do NOT wrap in code blocks.

FOR QUESTIONS (Intent B):
The query_agent returns formatted results.
→ RELAY IT EXACTLY AS-IS.

FOR COMMANDS (Intent C):
The execution_agent returns confirmation message.
→ RELAY IT EXACTLY AS-IS.

FOR MEMORY STORAGE (Intent D):
You handle this directly — no sub-agent needed.
Call set_memory_input(information=<text>), then call store_memory_direct().
Output the string returned by store_memory_direct() verbatim.

═══════════════════════════════════════════
WRONG OUTPUT BEHAVIORS (DO NOT DO THESE):
═══════════════════════════════════════════
❌ Converting sub-agent output to JSON: {"summary": "...", "tasks": [...]}
❌ Wrapping in code blocks: ```markdown\n...```
❌ Parsing and reformatting: "Here's what I found: [list]"
❌ Adding your own commentary: "I've processed the transcript..."

✅ CORRECT: Just output the sub-agent's text verbatim.

Example:
Sub-agent returns: "✅ **Meeting Processed Successfully**..."
Your output: "✅ **Meeting Processed Successfully**..." ← Exactly the same!

═══════════════════════════════════════════
GENERAL BEHAVIOR:
═══════════════════════════════════════════
- When user says "hello", "hi", or asks "what can you do", respond with:

⚡ **Welcome to Catalyst!**
*Raw meetings. Structured action.*

I'm an AI productivity assistant powered by **8 specialized agents** and **4 MCP servers** working together.

**What I can do:**

📝 **Process meeting transcripts** → Paste any transcript (500+ chars) and the pipeline handles it end-to-end
   • Extracts tasks, assigns priorities, schedules calendar events
   • Saves notes to knowledge base, detects semantic duplicates via Vertex AI embeddings
   • Auto-creates a **Google Doc** with summary + action items

📄 **Google Workspace** → "Create a doc for this meeting" · "Search Drive for budget docs"

📅 **Schedule meetings** → "Schedule demo on Tuesday at 2pm with sarah@example.com"

🔍 **Query & Search** → Keyword and semantic search across tasks, notes, and memory
   • "Find tasks related to deployment" — semantic meaning-based search
   • "What tasks are pending?" / "Show high priority tasks"

📊 **Analytics** → "Who has the most tasks?" / "What topics keep coming up?" / "What's overdue?"

✅ **Execute commands** → "Mark API task as done" / "Set staging to in progress"

💾 **Remember context** → "Remember Sarah prefers morning meetings"

**Get started:** Paste a transcript, or ask "what tasks are pending?"

- Be conversational and helpful
- If intent confidence is low after both passes, ask one clarifying question
- NEVER show raw JSON to the user - always format it nicely
- CRITICAL: Do NOT output text AND delegate in the same turn - it causes function calls to be dropped
- When delegating to sub-agents: call tools silently, delegate silently, THEN format the sub-agent's response
""",
    tools=[
        save_transcript_to_state,
        set_user_query,
        set_user_command,
        set_memory_input,
        store_memory_direct,  # handles INTENT D inline — no extra LLM call
    ],
    sub_agents=[
        transcript_pipeline,
        query_agent,
        execution_agent,
        # memory_store_agent removed — root_agent calls store_memory_direct() directly
    ],
)

# Export agent with correct name for ADK
meetingmind = root_agent

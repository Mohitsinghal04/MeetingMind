"""
MeetingMind — Multi-Agent Productivity Assistant
Complete agent architecture:
  - root_agent       : intent router (orchestrator)
  - sequential_chain : SummaryAgent → ActionItemAgent → PriorityAgent
  - parallel_branch  : SchedulerAgent + DuplicateCheckAgent + NotesAgent + MemoryAgent
  - briefing_agent   : final assembly
  - query_agent      : answers questions from DB
  - execution_agent  : executes commands (mark done, update status)
  - memory_store_agent: stores user information
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
    save_tasks,
    check_duplicate_tasks,
    get_pending_tasks,
    update_task_status,
    save_note,
    search_notes,
    save_memory,
    get_memory,
)
from .tools.calendar_tools import create_calendar_event, get_available_slots
from .tools.task_tools import list_my_tasks, mark_task_done, mark_task_in_progress
from .tools.notes_tools import search_related_notes, save_meeting_note

# ── SETUP ─────────────────────────────────────────────────────

try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

load_dotenv()

model_name = os.getenv("MODEL", "gemini-2.5-flash")


# ── STATE TOOL ────────────────────────────────────────────────

def save_transcript_to_state(tool_context: ToolContext, transcript: str) -> dict:
    """Save the user's meeting transcript to shared session state for the pipeline.

    Args:
        tool_context: ADK tool context.
        transcript: The full meeting transcript text pasted by the user.

    Returns:
        dict confirming the transcript was saved.
    """
    tool_context.state["TRANSCRIPT"] = transcript
    session_id = getattr(tool_context, "session_id", None) or "session_default"
    tool_context.state["session_id"] = session_id
    logging.info(f"Transcript saved to state ({len(transcript)} chars)")
    return {
        "status": "success",
        "message": "Transcript received. Processing pipeline started.",
        "length": len(transcript)
    }


def set_user_query(tool_context: ToolContext, query: str) -> dict:
    """Save a user question to state for the query agent.

    Args:
        tool_context: ADK tool context.
        query: The user's question about tasks, meetings, or stored info.

    Returns:
        dict confirming query was saved.
    """
    tool_context.state["user_query"] = query
    return {"status": "success", "query": query}


def set_user_command(tool_context: ToolContext, command: str) -> dict:
    """Save a user command to state for the execution agent.

    Args:
        tool_context: ADK tool context.
        command: The user's action command (e.g. mark task done).

    Returns:
        dict confirming command was saved.
    """
    tool_context.state["user_command"] = command
    return {"status": "success", "command": command}


def set_memory_input(tool_context: ToolContext, information: str) -> dict:
    """Save information the user wants remembered to state.

    Args:
        tool_context: ADK tool context.
        information: The information the user wants the assistant to remember.

    Returns:
        dict confirming memory input was saved.
    """
    tool_context.state["memory_input"] = information
    return {"status": "success", "information": information}


# ══════════════════════════════════════════════════════════════
# SEQUENTIAL CHAIN — runs in order, each feeds the next
# ══════════════════════════════════════════════════════════════

summary_agent = Agent(
    name="summary_agent",
    model=model_name,
    description="Reads the meeting transcript and produces a concise summary.",
    instruction="""
You are a professional meeting summarizer.

Read the meeting transcript from TRANSCRIPT and create a clear, concise summary.

Your summary must:
- Be 3-5 sentences maximum
- Cover the main topics discussed
- Highlight key decisions made
- Identify who was involved
- Note any deadlines or important dates mentioned

TRANSCRIPT:
{TRANSCRIPT}

Return only the summary text. No preamble, no labels, just the summary.
""",
    output_key="meeting_summary"
)

action_item_agent = Agent(
    name="action_item_agent",
    model=model_name,
    description="Extracts specific action items and tasks from the meeting summary.",
    instruction="""
You are an action item extraction specialist.

Based on MEETING_SUMMARY, extract every action item or task mentioned.

For each action item identify:
- task: what specifically needs to be done (be concrete)
- owner: who is responsible (use "Unassigned" if not clear, or "Team: [name]" for groups)
- deadline: when it's due (use "Not specified" if not mentioned)
- confidence: how certain you are this is an actionable task (High/Medium/Low)

EDGE CASE HANDLING:
1. If owner is a team/group ("Design Team", "Everyone"), mark as "Team: [name]"
2. If deadline is relative ("next week", "end of month"), include both relative and absolute if context allows: "2026-04-30 (end of month)"
3. If task is vague or conditional ("we should look at...", "maybe consider..."), mark confidence as "Low"
4. If task appears multiple times, list only once with note: "Finalize budget (mentioned 3 times)"

MEETING_SUMMARY:
{meeting_summary}

Return ONLY a valid JSON array. No markdown, no explanation, just JSON:
[
  {"task": "...", "owner": "...", "deadline": "...", "confidence": "High/Medium/Low"},
  {"task": "...", "owner": "...", "deadline": "...", "confidence": "High/Medium/Low"}
]

If no action items found, return: []
""",
    output_key="action_items"
)

priority_agent = Agent(
    name="priority_agent",
    model=model_name,
    description="Scores and prioritizes extracted action items by urgency and impact.",
    instruction="""
You are a task prioritization expert.

Review ACTION_ITEMS and assign a priority to each task:
- High: urgent, blocks others, near deadline, or business-critical
- Medium: important but not immediately blocking
- Low: nice to have, no immediate pressure

Consider deadlines, business impact, and dependencies when prioritizing.

ACTION_ITEMS:
{action_items}

Return ONLY a valid JSON array with priority added. No markdown, no explanation:
[
  {"task": "...", "owner": "...", "deadline": "...", "priority": "High"},
  {"task": "...", "owner": "...", "deadline": "...", "priority": "Medium"}
]
""",
    output_key="prioritized_tasks"
)


# ══════════════════════════════════════════════════════════════
# PARALLEL BRANCH — all 4 run simultaneously
# ══════════════════════════════════════════════════════════════

scheduler_agent = Agent(
    name="scheduler_agent",
    model=model_name,
    description="Schedules calendar events for high-priority tasks that need meetings.",
    instruction="""
You are a calendar scheduling assistant.

Review PRIORITIZED_TASKS and identify tasks that need a calendar event
(e.g. reviews, meetings, deadlines with a specific date).

For each High priority task that needs scheduling:
1. Use get_available_slots to find a free time slot
2. Use create_calendar_event to create the event

Focus on tasks with specific deadlines or that require team coordination.

PRIORITIZED_TASKS:
{prioritized_tasks}

After scheduling, return a JSON array of created events:
[{"title": "...", "time": "...", "attendees": [...], "status": "Created"}]

If nothing needed scheduling, return: []
""",
    tools=[get_available_slots, create_calendar_event],
    output_key="scheduled_events"
)

duplicate_check_agent = Agent(
    name="duplicate_check_agent",
    model=model_name,
    description="Checks for duplicate tasks in DB and saves new unique tasks.",
    instruction="""
You are a database task manager.

For each task in PRIORITIZED_TASKS:
1. Use check_duplicate_tasks to check if a similar task already exists in the DB
2. If NOT a duplicate: use save_tasks to save the new task
3. If IS a duplicate: skip it and note it was skipped

Process all tasks and track results.

PRIORITIZED_TASKS:
{prioritized_tasks}

After processing all tasks, return a JSON summary:
{
  "tasks_saved": N,
  "duplicates_skipped": N,
  "saved_task_names": [...],
  "skipped_task_names": [...]
}
""",
    tools=[check_duplicate_tasks, save_tasks],
    output_key="db_result"
)

notes_agent = Agent(
    name="notes_agent",
    model=model_name,
    description="Searches for related past notes and saves the current meeting as a new note.",
    instruction="""
You are a knowledge base manager.

Do both of these tasks:

1. Search for related past notes:
   - Extract 2-3 key topics from MEETING_SUMMARY
   - Use search_related_notes for each topic
   - Collect any relevant past notes found

2. Save the current meeting:
   - Use save_meeting_note with a descriptive title and the full MEETING_SUMMARY as content

MEETING_SUMMARY:
{meeting_summary}

Return a JSON object:
{
  "related_notes": [{"title": "...", "relevance": "...", "date": "..."}],
  "note_saved": true,
  "note_title": "...",
  "search_topics": [...]
}
""",
    tools=[search_related_notes, save_meeting_note],
    output_key="notes_result"
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
    output_key="memory_result"
)

briefing_agent = Agent(
    name="briefing_agent",
    model=model_name,
    description="Assembles all agent outputs into a clean, structured executive briefing.",
    instruction="""
You are an executive briefing writer.

Compile all results from the pipeline into a complete, professional JSON response.

Inputs:
MEETING_SUMMARY: {meeting_summary}
PRIORITIZED_TASKS: {prioritized_tasks}
SCHEDULED_EVENTS: {scheduled_events}
DB_RESULT: {db_result}
NOTES_RESULT: {notes_result}
MEMORY_RESULT: {memory_result}

Return ONLY a valid JSON object (no markdown fences):
{
  "meeting_summary": "the meeting summary text",
  "action_items": [
    {"task": "...", "owner": "...", "deadline": "...", "priority": "High/Medium/Low"}
  ],
  "scheduled_events": [
    {"title": "...", "time": "...", "attendees": [...], "status": "Created"}
  ],
  "related_notes": [
    {"title": "...", "relevance": "...", "date": "..."}
  ],
  "execution_confirmations": [
    "X tasks saved to database",
    "Y duplicates skipped",
    "Z calendar events created",
    "Meeting note saved",
    "N memories stored"
  ],
  "metrics": {
    "agents_executed": <count of agents that ran>,
    "sequential_time_estimate": "<estimated time for sequential execution in seconds>",
    "parallel_time_estimate": "<estimated time for parallel execution in seconds>",
    "speedup_ratio": "<parallel speedup ratio>",
    "message": "Parallel execution saved X seconds compared to sequential processing"
  },
  "briefing": "2-3 sentence executive summary of what was processed and what needs attention"
}

Be accurate — only include items that were actually processed.
Calculate metrics based on typical agent execution times:
- Sequential chain (3 agents): ~6 seconds total
- Parallel branch (4 agents): ~3 seconds (runs simultaneously)
- Briefing agent: ~2 seconds
Without parallelism: 6 + (4 * 3) + 2 = 20 seconds
With parallelism: 6 + 3 + 2 = 11 seconds
Speedup: 20/11 = 1.8x
""",
    output_key="final_briefing"
)


# ══════════════════════════════════════════════════════════════
# INTENT AGENTS — for follow-up conversations
# ══════════════════════════════════════════════════════════════

query_agent = Agent(
    name="query_agent",
    model=model_name,
    description="Answers questions about past meetings, tasks, notes, and stored memory.",
    instruction="""
You are a helpful knowledge retrieval assistant for MeetingMind.

The user has asked a question. Use your tools to find the answer.

Available tools:
- list_my_tasks: find tasks (filter by owner, priority)
- search_related_notes: search past meeting notes
- get_memory: retrieve stored information

User question:
{user_query}

Use 1-2 tools as needed, then provide a clear, direct answer.
Format your response in a readable way.
If you can't find the information, say so clearly.
""",
    tools=[list_my_tasks, search_related_notes, get_memory],
    output_key="query_result"
)

execution_agent = Agent(
    name="execution_agent",
    model=model_name,
    description="Executes action commands like marking tasks done, updating status, or scheduling.",
    instruction="""
You are a task execution assistant for MeetingMind.

The user has given you a command to execute. Use your tools to carry it out.

Available tools:
- mark_task_done: mark a task as completed
- mark_task_in_progress: mark a task as in progress
- update_task_status: set any status on a task
- create_calendar_event: schedule a new meeting or event
- save_note: add a new note

User command:
{user_command}

Execute the command using the appropriate tool(s).
Confirm exactly what was done in your response.
""",
    tools=[
        mark_task_done,
        mark_task_in_progress,
        update_task_status,
        create_calendar_event,
        save_note
    ],
    output_key="execution_result"
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

Save it and confirm what you stored.
""",
    tools=[save_memory],
    output_key="memory_store_result"
)


# ══════════════════════════════════════════════════════════════
# PIPELINE ASSEMBLY
# ══════════════════════════════════════════════════════════════

# Step 1: Sequential chain — summary then actions then priority
sequential_chain = SequentialAgent(
    name="sequential_chain",
    description="Processes transcript sequentially: summarize → extract actions → prioritize.",
    sub_agents=[summary_agent, action_item_agent, priority_agent]
)

# Step 2: Parallel branch — schedule, save to DB, search notes, store memory simultaneously
parallel_branch = ParallelAgent(
    name="parallel_branch",
    description="Simultaneously schedules events, saves tasks to DB, searches notes, and stores memory.",
    sub_agents=[
        scheduler_agent,
        duplicate_check_agent,
        notes_agent,
        memory_agent_background
    ]
)

# Full transcript pipeline: sequential → parallel → briefing
transcript_pipeline = SequentialAgent(
    name="transcript_pipeline",
    description="End-to-end meeting transcript processing pipeline.",
    sub_agents=[sequential_chain, parallel_branch, briefing_agent]
)


# ══════════════════════════════════════════════════════════════
# ROOT AGENT — intent router and entry point
# ══════════════════════════════════════════════════════════════

root_agent = Agent(
    name="meetingmind",
    model=model_name,
    description="MeetingMind — Multi-Agent Productivity Assistant",
    instruction="""
You are MeetingMind, an intelligent multi-agent productivity assistant
built on Google Cloud. You help teams manage meetings, tasks, schedules,
and information through natural conversation.

═══════════════════════════════════════════
INTENT DETECTION — TWO-PASS CLASSIFICATION
═══════════════════════════════════════════

PASS 1 — KEYWORD TRIGGERS (High Confidence):

1. If message contains ["remember", "note that", "keep in mind", "store", "save this"]:
   → INTENT D (STORE) - call set_memory_input immediately

2. If message contains ["mark", "mark as", "update status", "schedule", "set to", "complete"]:
   → INTENT C (COMMAND) - call set_user_command immediately

3. If message starts with ["what", "show me", "list", "find", "search", "get", "pending", "which"]:
   → INTENT B (QUESTION) - call set_user_query immediately

4. If message length > 500 characters AND contains ["meeting", "discussed", "action items", "attendees", "decisions", "agenda"]:
   → INTENT A (TRANSCRIPT) - call save_transcript_to_state immediately

PASS 2 — LLM CLASSIFICATION (If No Keyword Match):
Read the message carefully and determine the most likely intent:

INTENT A — TRANSCRIPT
Long text with discussion, decisions, names, action items.
→ Call save_transcript_to_state → transfer to transcript_pipeline

INTENT B — QUESTION
Asking about stored data, tasks, notes, or memory.
→ Call set_user_query → transfer to query_agent

INTENT C — COMMAND
Wants to take an action (mark done, schedule, update).
→ Call set_user_command → transfer to execution_agent

INTENT D — STORE
Wants you to remember something for future sessions.
→ Call set_memory_input → transfer to memory_store_agent

═══════════════════════════════════════════
GENERAL BEHAVIOR:
═══════════════════════════════════════════
- For new conversations, greet the user as MeetingMind
- Be conversational and helpful
- If intent confidence is low after both passes, ask one clarifying question
- Always confirm what was done after executing any action
- For transcripts, let the user know processing has started
""",
    tools=[
        save_transcript_to_state,
        set_user_query,
        set_user_command,
        set_memory_input
    ],
    sub_agents=[
        transcript_pipeline,
        query_agent,
        execution_agent,
        memory_store_agent
    ]
)

# Export agent with correct name for ADK
meetingmind = root_agent

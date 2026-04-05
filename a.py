"""
MeetingMind — Multi-Agent Productivity Assistant (8 Agents)
Complete agent architecture:
  - root_agent                : intent router (orchestrator)
  - transcript_pipeline       : 4 agents in sequence
    → summary_agent           : summarizes meeting transcript
    → action_item_priority    : extracts & prioritizes tasks
    → scheduler_agent         : creates calendar events with Meet links
    → duplicate_check_agent   : saves tasks to database
  - query_agent               : answers questions from DB
  - execution_agent           : executes commands (mark done, schedule, update)
  - memory_store_agent        : stores user preferences & context
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
)
# MCP-compatible imports (HACKATHON DEMO - routes through MCP wrapper layer)
from .tools.mcp_wrapper import (
    save_tasks_mcp as save_tasks,
    update_task_status_mcp as update_task_status,
    save_note_mcp as save_note,
    search_notes_mcp as search_notes,
    create_calendar_event_mcp as create_calendar_event,
)
from .tools.calendar_tools import get_available_slots
from .tools.task_tools import list_my_tasks, mark_task_done, mark_task_in_progress, find_meeting_by_title
from .tools.notes_tools import search_related_notes, save_meeting_note

# ── SETUP ─────────────────────────────────────────────────────

try:
    cloud_logging_client = google.cloud.logging.Client()
    cloud_logging_client.setup_logging()
except Exception:
    logging.basicConfig(level=logging.INFO)

load_dotenv()

model_name = os.getenv("MODEL", "gemini-2.5-flash")


# ── STATE MANAGEMENT ──────────────────────────────────────────

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
    "final_briefing": ""
}


def _ensure_state_defaults(tool_context: ToolContext) -> None:
    """Initialize all state variables to prevent KeyError in sub-agents."""
    for key, default_value in _STATE_DEFAULTS.items():
        if key not in tool_context.state:
            tool_context.state[key] = default_value


# ── STATE TOOL ────────────────────────────────────────────────

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
        "next_action": "IMMEDIATE_DELEGATION_REQUIRED"
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

    Args:
        tool_context: ADK tool context.
        command: The user's action command (e.g. mark task done).

    Returns:
        dict confirming command was saved.
    """
    _ensure_state_defaults(tool_context)
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
    _ensure_state_defaults(tool_context)
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

meeting_save_agent = Agent(
    name="meeting_save_agent",
    model=model_name,
    description="Saves the meeting transcript and summary to database (sets meeting_id for tasks).",
    instruction="""
You are a database persistence agent.

Your job: Save the meeting to the database so tasks can be linked to it.

Use save_meeting tool with:
- transcript: {TRANSCRIPT}
- summary: {meeting_summary}

The function will return a meeting_id which gets stored in state for other agents.

After saving, return empty string: ""

CRITICAL: This must run BEFORE tasks are saved so they can be linked to this meeting.
""",
    tools=[save_meeting],
    output_key="meeting_saved"
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
    output_key="prioritized_tasks"
)


# ══════════════════════════════════════════════════════════════
# PARALLEL BRANCH — all 4 run simultaneously
# ══════════════════════════════════════════════════════════════

scheduler_agent = Agent(
    name="scheduler_agent",
    model=model_name,
    description="Creates Google Calendar events (API with calendar link fallback).",
    instruction="""
You are a calendar scheduling assistant with HYBRID event creation capabilities.

PRIORITIZED_TASKS (markdown format):
{prioritized_tasks}

Your job: Look for tasks that mention scheduling a meeting with a specific date/time.

✅ Examples that SHOULD be scheduled:
- "Schedule design review on June 15th at 10 AM with john@example.com"
- "Book Q4 planning meeting April 10th 2pm with team"
- "Set up client call tomorrow at 3pm with sarah@company.com"

❌ Examples that should NOT be scheduled:
- "Complete API implementation" (no meeting mentioned)
- "Follow up next week" (no specific date/time)
- "Schedule TBD" (date not specified)

If you find a task that needs scheduling:
1. Extract: title, date, time, attendees (email addresses)

2. Convert relative dates to absolute YYYY-MM-DD format:
   CONTEXT: Today is 2026-04-05 (Saturday)
   - "Monday" → Calculate next Monday → 2026-04-07
   - "next Monday" → 2026-04-07 (one week from today is April 12, but "next Monday" means the upcoming Monday)
   - "this Monday" → 2026-04-07 (the upcoming Monday)
   - "tomorrow" → 2026-04-06
   - "April 10th" → 2026-04-10
   - "next week" → Add 7 days → 2026-04-12

3. Call create_calendar_event with:
   - title: "Design Review Meeting"
   - start_time: "2026-04-07 10:00" (MUST be YYYY-MM-DD HH:MM format)
   - duration_minutes: 60 (default) or parse from task
   - attendees: "john@example.com,sarah@company.com" (comma-separated emails)
   - description: "Scheduled from meeting transcript"

3. The function returns a pre-filled calendar link. Format your output:

   📅 [Event title] - Ready to schedule
   (Display result["markdown_link"] value here - it's a complete HTML link with target="_blank")

   The link opens Google Calendar in a new tab with all details pre-filled (including attendees). Save the event and send invitations.

If NO tasks need scheduling, return empty string: ""

IMPORTANT:
- Only schedule if date AND time are clearly specified
- Attendees should be email addresses (use @example.com if only names given)
- If uncertain about date/time, don't schedule
- If nothing to schedule, return empty string
- Display the markdown_link value directly without quotes or modification

Return empty string if no events scheduled, otherwise return formatted confirmation.
""",
    tools=[create_calendar_event],
    output_key="scheduled_events"
)

duplicate_check_agent = Agent(
    name="duplicate_check_agent",
    model=model_name,
    description="Saves tasks to database with automatic duplicate detection - outputs nothing.",
    instruction="""
You are a smart database task manager with duplicate prevention.

Your job:
1. Extract task data from the markdown in PRIORITIZED_TASKS
2. Parse each task line like: "• **High** — Task description — Owner: Name — Due: Date"
3. Convert to JSON format: [{"task": "...", "owner": "...", "deadline": "...", "priority": "..."}]
4. Call save_tasks tool with the JSON

PRIORITIZED_TASKS:
{prioritized_tasks}

IMPORTANT: The save_tasks function automatically checks for duplicates!
- It compares each task name with existing pending tasks in the database
- If a similar task already exists (case-insensitive partial match), it skips saving
- This prevents duplicate tasks when processing the same transcript multiple times

After saving, return an empty string: ""

Do NOT output JSON. Do NOT output confirmation. Just save silently.
The duplicate checking happens automatically inside save_tasks.
""",
    tools=[save_tasks],
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
    description="Assembles all agent outputs into a beautiful, user-friendly markdown summary.",
    instruction="""
You are an executive briefing writer who creates beautiful, readable summaries.

Inputs available:
MEETING_SUMMARY: {meeting_summary}
PRIORITIZED_TASKS: {prioritized_tasks}
SCHEDULED_EVENTS: {scheduled_events}
DB_RESULT: {db_result}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL OUTPUT CONSTRAINT (ABSOLUTE REQUIREMENT):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Your FIRST character of output MUST be: ✅

If your output starts with any of these, you FAILED:
- Starting with "[" → WRONG (that's JSON array)
- Starting with "{" → WRONG (that's JSON object)
- Starting with "`" → WRONG (that's code block)

CORRECT first 10 characters of your output: "✅ **Meet"

Now generate the full markdown summary in this format:

✅ **Meeting Processed Successfully**

📋 **Summary:**
{meeting_summary}

✅ **Action Items:**
[For each task in PRIORITIZED_TASKS, format as:]
• **[priority]** — [task] — Owner: [owner] — Due: [deadline]

[If PRIORITIZED_TASKS is empty, write: "No action items identified"]

[If SCHEDULED_EVENTS is not empty, add a section:]
📅 **Scheduled Events:**
[Copy the SCHEDULED_EVENTS content directly - it's already formatted]

💾 **System Actions:**
• [tasks_saved] tasks saved to database
[If DB_RESULT contains tasks_skipped > 0, add:]
• [tasks_skipped] duplicate tasks skipped (already exist in database)
• All tasks stored for future queries

📊 **Performance:**
Processed by 6 agents sequentially with duplicate prevention (~8-10 seconds, optimized for reliability)

---
✨ **What's next? Try these commands:**
- "What tasks are pending?"
- "Show me high priority tasks"
- "Mark task [number] as done"

---

CRITICAL OUTPUT RULES:
1. Return ONLY formatted markdown text (NOT JSON, NOT code blocks)
2. Start immediately with "✅ **Meeting Processed Successfully**"
3. Do NOT wrap in ```markdown blocks
4. Do NOT output as JSON object
5. Output as plain text with markdown formatting

CORRECT OUTPUT EXAMPLE:
✅ **Meeting Processed Successfully**

📋 **Summary:**
The team discussed Q3 mobile app launch...

WRONG OUTPUT EXAMPLES:
❌ {"status": "success", "summary": "..."}  ← NO JSON!
❌ ```markdown\n✅ Meeting...```  ← NO code blocks!
❌ [{"task": "..."}]  ← NO arrays!
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
- list_my_tasks: find tasks (filter by owner, priority, status, or meeting_id)
- find_meeting_by_title: search for a meeting by title/keyword to get its meeting_id
- get_meeting_summary: retrieve the FULL summary of a specific meeting (use for "summarize X meeting" queries)
- search_related_notes: search past meeting notes
- get_memory: retrieve stored information

User question:
{user_query}

═══════════════════════════════════════════
MEETING SUMMARY QUERIES
═══════════════════════════════════════════

When user asks for a meeting summary (e.g., "show Q3 Product Planning meeting summary", "summarize Sprint 12 meeting"):

1. Use get_meeting_summary with keywords from the meeting title
   Example: "summarize Q3 Product Planning Meeting" → get_meeting_summary("Q3 Product Planning")

2. The tool returns the FULL summary (not truncated) from the database

3. Display the complete summary to the user - do NOT truncate it yourself

Example:
User: "show product planning meeting summary"
→ Call: get_meeting_summary("product planning")
→ Display: Full summary text exactly as returned (don't cut it off mid-sentence)

═══════════════════════════════════════════
INTELLIGENT MEETING-AWARE QUERIES
═══════════════════════════════════════════

CRITICAL: force_show_all parameter is ONLY for clarification responses!
- Do NOT use force_show_all=True on the initial query
- Only use it when user explicitly wants "all" AFTER seeing the clarification menu
- Example wrong: User says "show all pending tasks" → DO NOT use force_show_all=True (first query)
- Example correct: User says "show all tasks" AFTER clarification menu → use force_show_all=True

When user asks for tasks and mentions a specific meeting:
1. Use find_meeting_by_title to get the meeting_id (supports fuzzy/partial matching)
2. Then call list_my_tasks with that meeting_id

IMPORTANT: find_meeting_by_title uses fuzzy matching! Extract keywords from user's query:
- "Q3 Product meeting" → find_meeting_by_title("Q3 Product")
- "Sprint 12" → find_meeting_by_title("Sprint 12")
- "Budget Review meeting" → find_meeting_by_title("Budget Review")

Examples:
- "Show pending tasks from Q3 Planning" → find_meeting_by_title("Q3 Planning") → list_my_tasks(meeting_id=result)
- "List John's tasks from Budget Review" → find_meeting_by_title("Budget Review") → list_my_tasks(owner="John", meeting_id=result)
- "Show all tasks from Q3 Product meeting" → find_meeting_by_title("Q3 Product") → list_my_tasks(meeting_id=result)

When user asks for tasks WITHOUT specifying a meeting:
- FIRST QUERY: Call list_my_tasks normally WITHOUT force_show_all parameter
  Example: list_my_tasks() or list_my_tasks(status="Pending")
  CRITICAL: Do NOT use force_show_all=True on the first query!

- The tool will automatically offer clarification if tasks span multiple meetings (>10 tasks)
- If result["status"] == "clarification_needed", the result contains:
  - total_tasks: total count
  - meeting_options: list of meetings with task_count and title

Format the clarification nicely:

**I found tasks from N meetings:**

1. **All tasks** (X total)
2. **Meeting Title 1** (Y tasks)
3. **Meeting Title 2** (Z tasks)

Which would you like to see?

HANDLING USER'S CLARIFICATION RESPONSE (SECOND QUERY):
When user responds to the clarification menu you just showed, check what they want:

- If they say "all", "all tasks", "both", "both meetings", "everything", "show all", "option 1", or "1":
  → They want ALL tasks from ALL meetings
  → NOW call list_my_tasks(force_show_all=True)
  → The force_show_all parameter bypasses clarification and shows everything
  → Example: list_my_tasks(force_show_all=True) or list_my_tasks(status="Pending", force_show_all=True)

- If they mention a specific meeting name (e.g. "Q3 Planning", "Sprint 12", "Q3 Product meeting"):
  → Use find_meeting_by_title with fuzzy matching to get meeting_id
  → Then call list_my_tasks(meeting_id=result)
  → The tool will match partial keywords like "Q3 Product" → "Q3 Product Planning Discussion"

- If they say "option 2", "option 3", or refer to a numbered choice:
  → Look at the meeting_options from the clarification result
  → Option 1 = all tasks (use force_show_all=True)
  → Option 2+ = specific meeting (use that meeting_id)

CRITICAL: When user wants "all tasks", you MUST use force_show_all=True parameter.
This tells the function to skip the clarification menu and return all tasks immediately.

═══════════════════════════════════════════

Use 1-3 tools as needed, then provide a clear, direct answer.
Format your response in a readable way.
If you can't find the information, say so clearly.
""",
    tools=[list_my_tasks, find_meeting_by_title, get_meeting_summary, search_related_notes, get_memory],
    output_key="query_result"
)

execution_agent = Agent(
    name="execution_agent",
    model=model_name,
    description="Executes action commands like marking tasks done, updating status, or scheduling.",
    instruction="""
You are a task execution assistant for MeetingMind.

The user wants to execute a command. Parse what they want and use the appropriate tool.

Available tools:
- mark_task_done(task_name): mark a task as completed (use partial task name)
- mark_task_in_progress(task_name): mark a task as in progress
- update_task_status(task_name, status): set any custom status
- create_calendar_event(title, start_time, duration_minutes, attendees, description): schedule with Google Meet
- get_memory(key): retrieve stored user preferences and context
- save_note(...): add a new note

User's request:
{user_command}

═══════════════════════════════════════════
INTELLIGENCE ENHANCEMENT: CONTEXT-AWARE SCHEDULING
═══════════════════════════════════════════

BEFORE asking user for missing details when scheduling a meeting:
1. Check if a person's name is mentioned (e.g. "Alex", "John", "Sarah")
2. Use get_memory to search for preferences about that person
3. Look for: meeting time preferences, timezone, availability patterns
4. If found, USE that information to fill in missing details intelligently

Example workflow:
User: "Schedule a meeting with Alex for demo review on April 5th"
→ Step 1: Use get_memory("alex") or get_memory("meeting_preference") to check stored info
→ Step 2: If memory returns "Alex likes morning meetings" → infer time as 9:00 AM or 10:00 AM
→ Step 3: If email not provided, ask for it (you can't infer emails)
→ Step 4: Create event with inferred time: "2026-04-05 09:00"

This makes you MUCH smarter and reduces back-and-forth with users!

═══════════════════════════════════════════

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
    description="Scheduled via MeetingMind"
  )

CRITICAL for calendar event creation:
1. title: Extract the meeting name from request (e.g. "Q4 planning" → "Q4 Planning")

2. start_time: MUST be EXACTLY in "YYYY-MM-DD HH:MM" format (24-hour time in IST timezone)

   DATE PARSING (Context: Today is 2026-04-05, Saturday):
   - "Monday" → Calculate next Monday → 2026-04-07 (upcoming Monday)
   - "next Monday" → 2026-04-07 (same as "Monday" - the upcoming one)
   - "this Monday" → 2026-04-07
   - "tomorrow" → 2026-04-06 (Sunday)
   - "April 10th" or "April 10" → 2026-04-10
   - "next week" → Add 7 days → 2026-04-12

   TIME PARSING (24-hour format in IST):
   - "2pm" → "14:00"
   - "10am" → "10:00"
   - "9:30am" → "09:30"
   - "3:45pm" → "15:45"
   - If time not specified: CHECK MEMORY for person's preference BEFORE asking user

   EXAMPLE: "schedule meeting on Monday at 2pm" → start_time="2026-04-07 14:00"

3. duration_minutes: Default to 60 if not specified

4. attendees: Comma-separated email addresses (e.g. "john@example.com,sarah@gmail.com")
   - Email addresses CANNOT be inferred - always ask if not provided

5. description: Brief note about the meeting (optional)

The system generates pre-filled Google Calendar links for creating events.

After executing ANY command, provide a clear confirmation.

═══════════════════════════════════════════
CALENDAR EVENT FORMATTING
═══════════════════════════════════════════

When create_calendar_event is called, it returns a pre-filled calendar link.
The result will have method="calendar_link" and a "markdown_link" field.

Format your output:

**📅 Calendar Event Ready**
**[title]** - [date] at [time]
Attendees: [attendee_list]

(Display result["markdown_link"] here - it's already a complete HTML link with target="_blank")

This link opens Google Calendar in a new tab with all details pre-filled (including attendees in the guest list).
When you save the event, Google will prompt you to send email invitations to all attendees.

IMPORTANT:
- Display the markdown_link field value directly from the result
- Don't add quotes or modify it - output the HTML as-is
- The link already has target="_blank" to open in new tab

═══════════════════════════════════════════
""",
    tools=[
        mark_task_done,
        mark_task_in_progress,
        update_task_status,
        create_calendar_event,
        get_memory,  # ← ADDED: Now execution_agent can check stored preferences!
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
    output_key="memory_store_result"
)


# ══════════════════════════════════════════════════════════════
# PIPELINE ASSEMBLY
# ══════════════════════════════════════════════════════════════

# 4-agent pipeline with REAL calendar integration!
# action_item_priority_agent outputs markdown, scheduler creates REAL Google Calendar events
transcript_pipeline = SequentialAgent(
    name="transcript_pipeline",
    description="Transcript processing with real calendar event creation (6 agents).",
    sub_agents=[
        summary_agent,                # 1. Summarize transcript
        meeting_save_agent,           # 2. Save meeting to DB (sets meeting_id in state)
        action_item_priority_agent,   # 3. Extract + Prioritize tasks
        scheduler_agent,              # 4. Create calendar events with links
        duplicate_check_agent,        # 5. Save tasks to DB (links to meeting_id)
        briefing_agent,               # 6. Assemble all outputs into final markdown
    ]
)


# ══════════════════════════════════════════════════════════════
# ROOT AGENT — intent router and entry point
# ══════════════════════════════════════════════════════════════

root_agent = Agent(
    name="meetingmind",
    model=model_name,
    description="MeetingMind — AI Meeting Assistant | Paste transcripts to extract tasks & schedule events | Powered by 8 specialized agents",
    instruction="""
You are MeetingMind, an intelligent multi-agent productivity assistant
built on Google Cloud. You help teams manage meetings, tasks, schedules,
and information through natural conversation.

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
→ Step 1: Call save_transcript_to_state tool with the ENTIRE user message as the transcript parameter
  CRITICAL: Pass the full multi-line text exactly as provided. The function handles escaping.
→ Step 2: Immediately delegate to the transcript_pipeline sub-agent to process it - DO NOT output text yet
→ Step 3: Wait for sub-agent to return results
→ Step 4: Relay the sub-agent's formatted output directly to user (NO parsing, NO modification)

INTENT B — QUESTION
Asking about stored data, tasks, notes, or memory.
→ Step 1: Call set_user_query(query=<the question>) - DO NOT output text yet
→ Step 2: Immediately delegate to the query_agent sub-agent to answer - DO NOT output text yet
→ Step 3: Relay query_agent's response directly to user (NO modification)

INTENT C — COMMAND
Wants to take an action (mark done, schedule, update).
→ Step 1: Call set_user_command(command=<the action>) - DO NOT output text yet
→ Step 2: Immediately delegate to the execution_agent sub-agent to execute - DO NOT output text yet
→ Step 3: Relay execution_agent's confirmation directly to user (NO modification)

INTENT D — STORE
Wants you to remember something for future sessions.
→ Step 1: Call set_memory_input(information=<what to remember>) - DO NOT output text yet
→ Step 2: Immediately delegate to the memory_store_agent sub-agent to store - DO NOT output text yet
→ Step 3: Relay memory_store_agent's confirmation directly to user (NO modification)

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
The transcript_pipeline's briefing_agent returns beautiful markdown like:
"✅ **Meeting Processed Successfully**\n\n📋 **Summary:**\nThe team discussed..."
→ YOUR OUTPUT: Copy that text EXACTLY. Do NOT convert to JSON. Do NOT wrap in code blocks.

FOR QUESTIONS (Intent B):
The query_agent returns formatted results.
→ RELAY IT EXACTLY AS-IS.

FOR COMMANDS (Intent C):
The execution_agent returns confirmation message.
→ RELAY IT EXACTLY AS-IS.

FOR MEMORY STORAGE (Intent D):
The memory_store_agent returns confirmation.
→ RELAY IT EXACTLY AS-IS.

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

👋 **Welcome to MeetingMind!**

I'm an AI assistant powered by 8 specialized agents that help you manage meetings and tasks.

**What I can do:**

📝 **Process transcripts** → Extract tasks, schedule events, store insights
   • Paste any meeting transcript and I'll analyze it automatically

📅 **Setup meetings** → Create calendar events with Google Meet links
   • "Schedule Q4 planning on April 10th at 2pm with john@example.com"

🔍 **Query tasks** → Filter by status, owner, or priority
   • "What tasks are pending?"
   • "Show me completed tasks"
   • "List John's high priority tasks"

✅ **Execute commands** → Update task status or schedule meetings
   • "Mark task 'API implementation' as done"
   • "Set staging task to in progress"

💾 **Remember context** → Store preferences and information
   • "Remember Alex prefers morning meetings"
   • "Note that client deadline is June 30th"

**Get started:** Paste a meeting transcript (500+ characters) and I'll process it in ~10 seconds!

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

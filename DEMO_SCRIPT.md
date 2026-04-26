# MeetingMind — Demo Script
**Google Gen AI Academy APAC | Target: 5 minutes**

---

## Before You Start (Setup Checklist)

- [ ] App open at Cloud Run URL — Tasks tab visible, chat on left
- [ ] Sample 1 transcript copied to clipboard (Q3 Product Planning — in SAMPLE_TRANSCRIPT.md)
- [ ] Sample 4 transcript copied second (Budget Planning — shows second processing)
- [ ] Browser mic permission granted
- [ ] Incognito tab open for a clean session if needed
- [ ] Know your Cloud Run URL to show judges

---

## Minute 1 — Hook + Architecture (60s)

**Say:**
> "MeetingMind turns any meeting transcript into structured action — in real time.
> Under the hood it runs **8 specialized AI agents** on Google ADK, with **4 MCP servers**
> connecting to Google Calendar, Docs, Drive, and a PostgreSQL vector database.
> Let me show you."

**Point at the UI:**
> "This is a single Cloud Run URL — React dashboard on the right, AI agent chat on the left.
> Everything in one deployment, no CORS, no separate services."

**Point at the tab bar:**
> "Tasks, Meetings, Analytics, Docs — all live data from the agent pipeline."

---

## Minute 2 — Core Pipeline (90s) ← Most Important

**Action:** Paste the Q3 Product Planning transcript into the chat and hit Send.

**While pipeline is running, narrate each stage:**
> "Watch the pipeline visualizer — Stage 1: the **Analysis Agent** reads the transcript,
> extracts summary and all action items with owners and deadlines using Gemini 2.5 Flash."

> "Stage 2: **Save & Schedule Agent** writes each task to PostgreSQL and creates a
> Google Calendar event for the design review meeting — that's our Calendar MCP server."

> "Stage 3 is where it gets interesting — two agents run **in parallel**:
> the **Notes Agent** saves the meeting to our knowledge base and assembles the briefing,
> while the **Evaluation Agent** — our LLM-as-Judge — grades the processing quality
> on 4 dimensions simultaneously. Zero extra latency."

**When briefing appears:**
> "Done. Summary, action items, system actions — all in under 15 seconds."

**Point at quality scorecard when it appears:**
> "And there's the quality score — our LLM-as-Judge rated its own output: summary quality,
> task extraction completeness, priority accuracy, owner attribution. Self-evaluating AI."

---

## Minute 3 — Dashboard (60s)

**Action:** Click Tasks tab.

**Say:**
> "14 tasks extracted, prioritized, and saved — High, Medium, Low.
> Owner avatars, editable deadlines, inline status updates."

**Action:** Click a status pill, change one task to Done.

> "Status updates hit the database instantly via PATCH API. Watch the row flash green —
> that's optimistic UI with DB verification."

**Action:** Select 3 tasks with checkboxes → click Mark Done.

> "Bulk actions — 3 parallel PATCH calls, all verified."

**Action:** Click Analytics tab.

> "Real analytics from the DB — task ownership distribution, completion trends,
> overdue count. All computed server-side, no LLM involved."

**Action:** Click Meetings tab, expand the meeting, click "+9 more".

> "Full task list per meeting, inline. Progress bar shows 3 of 14 done."

---

## Minute 4 — Intelligence Features (60s)

**Action:** In chat, type:
```
remember our team prefers morning meetings
```

**Say:**
> "Memory stored globally — persists across browser sessions. Watch what happens next."

**Action:** Type:
```
set up a meeting with Sarah for demo review on Friday sarah@example.com
```

**Say:**
> "No time specified — the agent reads stored preferences, sees 'morning meetings',
> schedules at 9 AM automatically. No clarifying question, no timeout."

**When calendar link appears:**
> "That's a real Google Calendar link — click it and the event is pre-filled.
> Our Calendar MCP server built it."

**Action:** Type:
```
find tasks similar to set up environment
```

**Say:**
> "Semantic search — pgvector on Vertex AI embeddings. Finds related tasks by
> meaning, not just keywords. RAG in production."

---

## Minute 5 — Architecture Summary + Close (30s)

**Action:** Click Docs tab.

> "Every processed meeting automatically gets a Google Doc published via our
> Workspace MCP server. Judges can click the link right now."

**Say:**
> "To summarise the architecture judges care about:
> - **8 agents** coordinated by Google ADK SequentialAgent + ParallelAgent
> - **4 MCP servers**: Tasks, Calendar, Notes, Google Workspace
> - **pgvector + Vertex AI** embeddings for semantic search and deduplication
> - **LLM-as-Judge** evaluation running in parallel — not a claim, actually firing
> - **33% fewer LLM calls** than initial design — we profiled and eliminated redundant calls
> - Single Cloud Run URL, React frontend, FastAPI backend, PostgreSQL
>
> MeetingMind doesn't just process meetings — it learns from them."

---

## Backup Queries (If Judges Ask to See More)

| Judge asks | You type |
|---|---|
| "Show me the AI evaluating quality" | Ask: `"What quality score did the last meeting get?"` |
| "Can it handle follow-ups?" | Ask: `"What tasks are overdue?"` |
| "Show analytics" | Ask: `"Who has the most tasks?"` |
| "What about duplicate detection?" | Process Sample 1 again — agent catches duplicates |
| "Show memory working" | Ask: `"Schedule a meeting with John tomorrow john@j.com"` — uses morning preference |
| "Multi-meeting context?" | Process Sample 4 (Budget), then ask: `"What budget decisions were made?"` |

---

## Key Numbers to Mention

| Metric | Value |
|---|---|
| Agents | 8 (1 parallel stage) |
| MCP Servers | 4 |
| Pipeline time | ~12–15 seconds |
| LLM calls per transcript | 5 (down from 6 original) |
| Vector search | pgvector + Vertex AI textembedding-gecko@003 |
| Deployment | Google Cloud Run (single URL) |
| DB | PostgreSQL + pgvector |
| Frontend | React + Vite + Tailwind (no UI framework) |

---

## If Something Goes Wrong

| Problem | Recovery |
|---|---|
| Pipeline times out | "Cloud Run cold start — let me try again" → paste again |
| Calendar link missing | "Calendar MCP handles this — the link appears in the Docs tab" |
| Quality scorecard doesn't appear | "Evaluation runs async — let me query it" → type `"quality score"` |
| Analytics shows 0 | "Need 2+ meetings processed — let me paste the second transcript" |
| Mic doesn't work | Skip mic demo, say "Web Speech API available on Chrome" |

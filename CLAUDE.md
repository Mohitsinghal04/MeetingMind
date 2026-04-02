# MeetingMind — Quick Start Guide

## What is MeetingMind?

A multi-agent AI system that processes meeting transcripts to extract tasks, schedule events, and provide actionable insights.

## How to Use

### 1. Process a Meeting Transcript
Paste any meeting transcript (500+ characters) and MeetingMind will:
- Extract action items with owners and deadlines
- Prioritize tasks (High/Medium/Low)
- Schedule follow-up meetings
- Save searchable notes
- Store key decisions

**Example:** Paste the Q3 Product Planning transcript from `SAMPLE_TRANSCRIPT.md`

### 2. Query Tasks
- "What tasks are pending?"
- "Show me high priority tasks"
- "List tasks assigned to John"

### 3. Execute Commands
- "Mark task 1 as done"
- "Update task 3 status to in progress"

### 4. Store Information
- "Remember that client prefers morning meetings"

## Demo Transcripts

See `SAMPLE_TRANSCRIPT.md` for 4 realistic meeting transcripts you can test with.

## Architecture

**9 Specialized Agents:**
- Root Agent → Intent router
- Summary Agent → Extracts meeting summary
- Action Item Agent → Identifies tasks
- Priority Agent → Assigns High/Medium/Low
- Scheduler Agent → Creates calendar events
- Duplicate Check Agent → Prevents duplicate tasks
- Notes Agent → Saves searchable notes
- Memory Agent → Stores context
- Briefing Agent → Assembles final output

**Pipeline:** Sequential chain (3 agents) → Parallel branch (4 agents) → Assembly (1 agent)

**Performance:** ~10 seconds per transcript, 1.8x faster than sequential execution

## Competition Context

Built for Google Gen AI Academy APAC — Multi-Agent Systems with MCP Competition

**Requirements Met:**
✅ Multi-agent coordination (9 agents)
✅ Structured data storage (PostgreSQL)
✅ MCP integration (3 MCP servers)
✅ Multi-step workflows (4 intent pipelines)
✅ API deployment (Cloud Run + Vertex AI)

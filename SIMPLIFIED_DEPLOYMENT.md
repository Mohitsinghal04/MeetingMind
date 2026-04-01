# Simplified Deployment (ADK UI Only)

## What Changed

**Removed:**
- Custom UI (ui/ directory)
- CORS proxy (cors_proxy.py, requirements_proxy.txt, Dockerfile.proxy)
- UI deployment script (deploy_ui.sh)
- CORS proxy deployment script (deploy_cors_proxy.sh)

**Result:** Simple, clean deployment using ADK's built-in UI. No CORS issues, no extra services.

---

## Deployment Steps

### Option 1: Quick Start (Automated)

```bash
bash fresh_start.sh
```

This will:
1. Clean up existing resources
2. Run GCP infrastructure setup
3. Prompt you to load database schema
4. Deploy with ADK built-in UI

### Option 2: Manual Steps

```bash
# 1. Infrastructure setup (10-15 min)
bash day1_gcp_setup.sh

# 2. Update .env with values from step 1
nano .env

# 3. Load database schema
gcloud sql connect meetingmind-db --user=meetingmind_user --database=meetingmind
# Paste contents of schema.sql
# Exit with \q

# 4. Deploy backend with ADK UI
bash day6_deploy.sh
```

---

## Access Your Application

After deployment completes, you'll see:

```
🎉 VERIFIED SERVICE URL (use this one):
  https://meetingmind-xxxxx.run.app
```

**Open that URL in your browser** to access the ADK chat interface.

---

## Test the Application

In the ADK UI, try:

1. **Query intent:**
   ```
   What tasks are pending?
   ```

2. **Command intent:**
   ```
   Mark task 1 as done
   ```

3. **Memory intent:**
   ```
   Remember that client prefers morning meetings
   ```

4. **Transcript intent:**
   Paste a long meeting transcript (500+ characters with meeting keywords)

---

## Architecture (Simplified)

```
Browser
   ↓
ADK Built-in UI (Cloud Run)
   ↓
MeetingMind Agent
   ↓
Cloud SQL Database
```

**Services Used:**
- 1 Cloud Run service (meetingmind)
- 1 Cloud SQL instance (meetingmind-db)
- Vertex AI (Gemini)

**No CORS issues. No proxy. Just ADK.**

---

## Cleanup

To delete everything:

```bash
bash cleanup_gcp.sh
```

---

## Files You Need

**Core:**
- agent.py
- requirements.txt
- schema.sql
- mcp_config.json
- .env

**Tools:**
- tools/*.py (all tool files)

**Scripts:**
- day1_gcp_setup.sh
- day6_deploy.sh
- fresh_start.sh
- cleanup_gcp.sh

**Documentation:**
- CLAUDE.md
- DEPLOYMENT_GUIDE.md (still valid, just ignore UI/CORS sections)
- SIMPLIFIED_DEPLOYMENT.md (this file)

---

## Cost Estimate

~$7-10/month with minimal usage:
- Cloud Run with min-instances=0: ~$0-2
- Cloud SQL db-f1-micro: ~$7-10
- Vertex AI (Gemini): pay per use

---

## Competition Requirements ✓

- ✓ Multi-agent orchestration (Sequential + Parallel)
- ✓ MCP integration (3 servers: calendar, tasks, notes)
- ✓ Cloud deployment (GCP Cloud Run + Cloud SQL + Vertex AI)
- ✓ Database persistence (4 tables)
- ✓ Intent detection (4 intents)
- ✓ Working UI (ADK built-in)

**Everything works. Nothing extra.**

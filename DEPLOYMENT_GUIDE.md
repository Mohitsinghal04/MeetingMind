# MeetingMind - Complete Deployment Guide

## 📋 Overview

This guide walks you through deploying MeetingMind from scratch in a new GCP project or Cloud Shell environment.

**Time Required:** 20-30 minutes
**Cost:** ~$5-10/month (with minimal usage)

---

## 🚀 Quick Start (Single Command)

If all files are already in Cloud Shell:

```bash
cd ~/Hackathon
bash fresh_start.sh
```

Then follow the prompts. **Skip to Step 7** if this works.

---

## 📝 Step-by-Step Manual Deployment

### Step 1: Upload Files to Cloud Shell

Upload the entire `Hackathon` folder to Cloud Shell:

1. Open [Cloud Shell](https://shell.cloud.google.com)
2. Click **⋮** (More) → **Upload**
3. Upload the `Hackathon` folder (or zip it first)

Or use `gcloud` from your local machine:

```bash
# From your local machine
gcloud cloud-shell scp --recurse ./Hackathon cloudshell:~/
```

### Step 2: Set Up Environment

```bash
cd ~/Hackathon

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify ADK installation
adk --version  # Should show: adk, version 1.14.0
```

### Step 3: Configure GCP Project

Edit `.env` file or set variables:

```bash
# Option A: Use current project
export PROJECT_ID=$(gcloud config get-value project)

# Option B: Set specific project
export PROJECT_ID="your-project-id"
gcloud config set project $PROJECT_ID
```

### Step 4: Run Infrastructure Setup

```bash
# This creates Cloud SQL, IAM, enables APIs (~10-15 min)
bash day1_gcp_setup.sh
```

**What it creates:**
- Cloud SQL Postgres instance: `meetingmind-db`
- Service account: `meetingmind-sa`
- Enables: Cloud Run, Cloud SQL, Vertex AI, Cloud Build APIs

**Output:** Copy the environment variables printed at the end.

### Step 5: Update `.env` File

Update `.env` with values from Step 4:

```bash
nano .env
```

Or use the auto-generated values:

```bash
cat > .env << EOF
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")
SA_NAME=meetingmind-sa
SERVICE_ACCOUNT=meetingmind-sa@$(gcloud config get-value project).iam.gserviceaccount.com
REGION=asia-south1
MODEL=gemini-2.5-flash
DB_HOST=$(gcloud sql instances describe meetingmind-db --format="value(ipAddresses[0].ipAddress)")
DB_NAME=meetingmind
DB_USER=meetingmind_user
DB_PASSWORD=MeetingMind@2026!
DB_PORT=5432
EOF

source .env
```

### Step 6: Load Database Schema

```bash
# Connect to Cloud SQL
gcloud sql connect meetingmind-db --user=meetingmind_user --database=meetingmind
# Password: MeetingMind@2026!
```

Inside psql, paste the contents of `schema.sql`:

```bash
# In another terminal, show the schema
cat schema.sql
```

Copy and paste into psql, then exit:

```sql
\q
```

### Step 7: Deploy Backend to Cloud Run

```bash
# Deploy the main agent service
bash day6_deploy.sh
```

**What it deploys:**
- MeetingMind agent as Cloud Run service
- Environment variables for DB and Gemini
- IAM permissions for public access

**Expected output:**
```
✅ DEPLOYMENT COMPLETE!
🎉 VERIFIED SERVICE URL (use this one):
  https://meetingmind-xxxxx.run.app
```

**Save this URL** - you'll need it for the CORS proxy!

### Step 8: Deploy CORS Proxy

The backend doesn't have CORS enabled, so we need a proxy:

```bash
# This creates a separate Cloud Run service that adds CORS headers
bash deploy_cors_proxy.sh
```

**What it deploys:**
- CORS proxy as Cloud Run service: `meetingmind-cors-proxy`
- Forwards requests to backend with CORS headers

**Expected output:**
```
✅ CORS Proxy Deployed!
Proxy URL: https://meetingmind-cors-proxy-xxxxx.run.app
```

**Save this proxy URL** - the UI will use this!

### Step 9: Update UI Configuration

The UI needs to point to the **CORS proxy URL** (not the backend):

```bash
# Get the proxy URL
source .env
PROXY_URL=$(gcloud run services describe meetingmind-cors-proxy --project=$PROJECT_ID --region=$REGION --format="value(status.url)")

echo "Proxy URL: $PROXY_URL"

# Update ui/index.html with the proxy URL
sed -i "s|const BASE_URL = .*|const BASE_URL = '$PROXY_URL';|" ui/index.html

# Verify
grep "const BASE_URL" ui/index.html
```

**Should show:**
```javascript
const BASE_URL = 'https://meetingmind-cors-proxy-xxxxx.run.app';
```

### Step 10: Deploy Custom UI

```bash
# This creates a Cloud Storage bucket and uploads the UI
bash deploy_ui.sh
```

**What it deploys:**
- Cloud Storage bucket: `{PROJECT_ID}-meetingmind-ui`
- Static website hosting enabled
- Public read access

**Expected output:**
```
✅ Custom UI deployed!
Your custom UI is available at:
https://storage.googleapis.com/{PROJECT_ID}-meetingmind-ui/index.html
```

### Step 11: Test the Deployment

```bash
source .env

# Test 1: Backend directly
BACKEND_URL=$(gcloud run services describe meetingmind --project=$PROJECT_ID --region=$REGION --format="value(status.url)")

# Create a session
SESSION_RESPONSE=$(curl -s -X POST "$BACKEND_URL/apps/meetingmind/users/test/sessions" \
  -H "Content-Type: application/json" \
  -d '{}')

SESSION_ID=$(echo $SESSION_RESPONSE | grep -o '"id":"[^"]*"' | cut -d'"' -f4)

echo "Session ID: $SESSION_ID"

# Test the agent
curl -X POST "$BACKEND_URL/run" \
  -H "Content-Type: application/json" \
  -d "{
    \"app_name\": \"meetingmind\",
    \"user_id\": \"test\",
    \"session_id\": \"$SESSION_ID\",
    \"new_message\": {
      \"role\": \"user\",
      \"parts\": [{\"text\": \"Hello\"}]
    }
  }"
```

**Expected:** Should return a JSON response with agent greeting.

```bash
# Test 2: CORS Proxy
PROXY_URL=$(gcloud run services describe meetingmind-cors-proxy --project=$PROJECT_ID --region=$REGION --format="value(status.url)")

curl -i -X OPTIONS "$PROXY_URL/run" \
  -H "Origin: https://storage.googleapis.com" \
  -H "Access-Control-Request-Method: POST"
```

**Expected:** Should see `access-control-allow-origin: *` in headers.

```bash
# Test 3: Custom UI
BUCKET_NAME="${PROJECT_ID}-meetingmind-ui"
echo "Open in browser:"
echo "https://storage.googleapis.com/$BUCKET_NAME/index.html"
```

Open in browser and test:
- Click "Pending tasks" button
- Paste demo transcript
- Try commands like "What tasks are pending?"

---

## 🔧 Troubleshooting

### Issue: "Session not found" error in UI

**Cause:** UI isn't creating sessions first
**Fix:** Make sure `ui/index.html` has the `ensureSession()` function and calls it before `/run`

```bash
# Check if ensureSession exists
grep -n "ensureSession" ui/index.html
```

### Issue: CORS errors in browser

**Cause:** UI is calling backend directly instead of proxy
**Fix:** Update BASE_URL in `ui/index.html`:

```bash
PROXY_URL=$(gcloud run services describe meetingmind-cors-proxy --region=$REGION --format="value(status.url)")
sed -i "s|const BASE_URL = .*|const BASE_URL = '$PROXY_URL';|" ui/index.html

# Redeploy UI
bash deploy_ui.sh
```

### Issue: Backend returns 404

**Cause:** Agent export missing
**Fix:** Check `agent.py` has this at the end:

```bash
tail -3 agent.py
```

Should show:
```python
# Export agent with correct name for ADK
meetingmind = root_agent
```

If missing, add it:

```bash
echo "" >> agent.py
echo "# Export agent with correct name for ADK" >> agent.py
echo "meetingmind = root_agent" >> agent.py
```

Then redeploy:

```bash
bash day6_deploy.sh
```

### Issue: Database connection errors

**Cause:** DB_HOST or credentials incorrect
**Fix:** Verify environment variables:

```bash
source .env
echo "DB_HOST: $DB_HOST"
echo "DB_NAME: $DB_NAME"

# Test connection
gcloud sql connect meetingmind-db --user=$DB_USER --database=$DB_NAME
# Password: MeetingMind@2026!
```

### Issue: Cloud Build fails

**Cause:** APIs not enabled or permissions missing
**Fix:**

```bash
# Enable required APIs
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

# Check service account permissions
gcloud projects get-iam-policy $PROJECT_ID \
  --flatten="bindings[].members" \
  --filter="bindings.members:serviceAccount:meetingmind-sa@*"
```

---

## 📁 Required Files Checklist

Before deploying, ensure these files exist:

### Core Files
- [ ] `agent.py` - Main agent code (with `meetingmind = root_agent` at end)
- [ ] `requirements.txt` - Python dependencies
- [ ] `schema.sql` - Database schema
- [ ] `.env` - Environment variables (will be generated)
- [ ] `__init__.py` - Package marker

### Tool Files
- [ ] `tools/db_tools.py`
- [ ] `tools/calendar_tools.py`
- [ ] `tools/task_tools.py`
- [ ] `tools/notes_tools.py`
- [ ] `tools/calendar_mcp_server.py`
- [ ] `tools/tasks_mcp_server.py`
- [ ] `tools/notes_mcp_server.py`

### MCP Configuration
- [ ] `mcp_config.json`

### UI Files
- [ ] `ui/index.html` (with proxy URL and session management)

### Deployment Scripts
- [ ] `day1_gcp_setup.sh` - Infrastructure setup
- [ ] `day6_deploy.sh` - Backend deployment
- [ ] `deploy_cors_proxy.sh` - CORS proxy deployment
- [ ] `deploy_ui.sh` - UI deployment
- [ ] `fresh_start.sh` - Full automated deployment
- [ ] `cleanup_gcp.sh` - Cleanup script

### CORS Proxy Files
- [ ] `cors_proxy.py` - Proxy server code
- [ ] `requirements_proxy.txt` - Proxy dependencies
- [ ] `Dockerfile.proxy` - Proxy container

### Documentation
- [ ] `CLAUDE.md` - Project documentation
- [ ] `SETUP_GUIDE.md` - Setup instructions
- [ ] `DEPLOYMENT_GUIDE.md` - This file

---

## 🗑️ Cleanup (Delete Everything)

To remove all resources and start fresh:

```bash
bash cleanup_gcp.sh
```

This deletes:
- Cloud Run services (meetingmind, meetingmind-cors-proxy)
- Cloud Storage bucket
- Cloud SQL instance
- Service account
- Container images

**Warning:** This is destructive and cannot be undone!

---

## 💰 Cost Estimate

**Monthly costs with minimal usage:**

| Service | Cost |
|---------|------|
| Cloud Run (2 services, min instances=0) | $0-5 |
| Cloud SQL (db-f1-micro, 10GB) | $7-10 |
| Cloud Storage (1 bucket, <1GB) | $0.02 |
| Vertex AI (Gemini API calls) | Pay per use |
| **Total** | **~$7-15/month** |

**To minimize costs:**
- Use `--min-instances=0` for Cloud Run (cold starts OK for demo)
- Use `db-f1-micro` for Cloud SQL (smallest tier)
- Delete resources after competition: `bash cleanup_gcp.sh`

---

## 🎯 Competition Demo Checklist

Before presenting:

- [ ] Backend deployed and responding
- [ ] CORS proxy working (no CORS errors in browser)
- [ ] Custom UI accessible via Cloud Storage URL
- [ ] Database schema loaded with seed data
- [ ] Test all 4 intents work:
  - [ ] Transcript processing
  - [ ] Query (pending tasks)
  - [ ] Command (mark done)
  - [ ] Memory (remember info)
- [ ] Agent status animation works
- [ ] Structured output displays correctly
- [ ] No errors in browser console

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                   USER BROWSER                          │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ HTTPS (Cloud Storage)
                  ▼
┌─────────────────────────────────────────────────────────┐
│          CUSTOM UI (index.html)                         │
│   https://storage.googleapis.com/.../index.html         │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ POST /apps/.../sessions (create session)
                  │ POST /run (send messages)
                  ▼
┌─────────────────────────────────────────────────────────┐
│     CORS PROXY (Cloud Run)                              │
│   https://meetingmind-cors-proxy-xxxxx.run.app          │
│   • Adds CORS headers                                   │
│   • Forwards to backend                                 │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ Proxied requests
                  ▼
┌─────────────────────────────────────────────────────────┐
│     MEETINGMIND BACKEND (Cloud Run)                     │
│   https://meetingmind-xxxxx.run.app                     │
│   • ADK FastAPI app                                     │
│   • Multi-agent orchestration                           │
│   • Session management                                  │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ SQL queries
                  ▼
┌─────────────────────────────────────────────────────────┐
│     CLOUD SQL POSTGRES                                  │
│   • 4 tables: meetings, tasks, notes, memory           │
│   • Seed data for testing                              │
└─────────────────────────────────────────────────────────┘
```

---

## 🔗 Useful Commands

```bash
# Get all service URLs
source .env
echo "Backend: $(gcloud run services describe meetingmind --region=$REGION --format='value(status.url)')"
echo "Proxy: $(gcloud run services describe meetingmind-cors-proxy --region=$REGION --format='value(status.url)')"
echo "UI: https://storage.googleapis.com/${PROJECT_ID}-meetingmind-ui/index.html"

# View logs
gcloud run services logs read meetingmind --limit=50
gcloud run services logs read meetingmind-cors-proxy --limit=50

# Check service status
gcloud run services list --project=$PROJECT_ID

# Check Cloud SQL status
gcloud sql instances describe meetingmind-db

# List Cloud Storage buckets
gsutil ls

# Delete a specific service
gcloud run services delete meetingmind --region=$REGION --quiet
```

---

## 📞 Support

If you encounter issues:

1. Check the **Troubleshooting** section above
2. Review Cloud Run logs: `gcloud run services logs read meetingmind`
3. Verify all files from **Required Files Checklist** exist
4. Try `bash fresh_start.sh` for a clean redeployment

---

## ✅ Success Criteria

Your deployment is successful when:

1. ✅ Custom UI loads without errors
2. ✅ Can create sessions and send messages
3. ✅ Agent responds to all 4 intent types
4. ✅ No CORS errors in browser console
5. ✅ Database persists tasks and notes
6. ✅ Agent status animation displays
7. ✅ Structured output renders correctly

**Total deployment time: 20-30 minutes**
**You're ready for the competition! 🏆**

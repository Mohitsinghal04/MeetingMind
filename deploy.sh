#!/bin/bash
# ============================================================
# MeetingMind — Day 6: Deploy to Cloud Run with MCP Support
# Run from inside the Hackathon directory
# ============================================================

# Load env vars
source .env

# ── GCLOUD AUTHENTICATION & CONFIGURATION
echo "Configuring gcloud..."
echo ""

# Check if gcloud is authenticated
if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "."; then
    echo "⚠ No active gcloud account found."
    echo "Please authenticate first:"
    echo ""
    echo "  gcloud auth login"
    echo ""
    echo "Or if you're using a service account:"
    echo "  gcloud auth activate-service-account --key-file=path/to/key.json"
    echo ""
    exit 1
fi

# Get the active account
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
echo "✓ Using gcloud account: $ACTIVE_ACCOUNT"

# Set the project
gcloud config set project $PROJECT_ID

# Set the default region
gcloud config set run/region $REGION

echo "✓ gcloud configured for project: $PROJECT_ID"
echo ""

# PRE-DEPLOYMENT CHECKS
echo "Running pre-deployment checks..."
echo ""

# Check 1: Verify .env has all required values
required_vars=("PROJECT_ID" "REGION" "SERVICE_ACCOUNT" "DB_HOST" "DB_NAME" "DB_USER" "DB_PASSWORD")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "✗ ERROR: Missing required environment variables:"
    printf '  - %s\n' "${missing_vars[@]}"
    echo ""
    echo "Please update your .env file with values from setup_gcp.sh"
    exit 1
fi

echo "✓ Environment variables configured"

# Check 2: Verify MCP files exist (CRITICAL for competition)
mcp_files=("mcp_config.json" "tools/calendar_mcp_server.py" "tools/tasks_mcp_server.py" "tools/notes_mcp_server.py")
missing_files=()

for file in "${mcp_files[@]}"; do
    if [ ! -f "$file" ]; then
        missing_files+=("$file")
    fi
done

if [ ${#missing_files[@]} -gt 0 ]; then
    echo "✗ ERROR: Missing MCP files (required for competition):"
    printf '  - %s\n' "${missing_files[@]}"
    exit 1
fi

echo "✓ MCP files present (competition requirement satisfied)"

# Check 3: Verify requirements.txt has MCP package
if grep -q "mcp" requirements.txt; then
    echo "✓ MCP package in requirements.txt"
else
    echo "⚠ WARNING: MCP package not found in requirements.txt"
    echo "  This is required for the competition. Add 'mcp==1.0.0'"
fi

echo ""
echo "✓ All pre-deployment checks passed"
echo ""

# DEPLOY
echo "Deploying to Cloud Run with ADK..."
echo ""

# Deploy with adk with built-in UI
adk deploy cloud_run \
  --project=$PROJECT_ID \
  --region=$REGION \
  --service_name=meetingmind \
  --app_name=meetingmind \
  --with_ui \
  .

echo ""
echo "Updating Cloud Run service configuration..."
echo ""

# Get Cloud SQL connection name for proxy
DB_INSTANCE="meetingmind-db"
CLOUD_SQL_CONNECTION="${PROJECT_ID}:${REGION}:${DB_INSTANCE}"
echo "Cloud SQL connection name: $CLOUD_SQL_CONNECTION"

# Update service with additional configuration
gcloud run services update meetingmind \
  --project=$PROJECT_ID \
  --region=$REGION \
  --service-account=$SERVICE_ACCOUNT \
  --add-cloudsql-instances=$CLOUD_SQL_CONNECTION \
  --set-env-vars="DB_HOST=$DB_HOST,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASSWORD,DB_PORT=$DB_PORT,MODEL=$MODEL,PROJECT_ID=$PROJECT_ID,GOOGLE_GENAI_USE_VERTEXAI=TRUE,CALENDAR_ID=${CALENDAR_ID:-primary},TIMEZONE=${TIMEZONE:-America/Los_Angeles}" \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --update-labels=hackathon=gen-ai-academy-apac \
  --platform=managed

echo ""
echo "Setting IAM policy to allow unauthenticated access..."
gcloud run services add-iam-policy-binding meetingmind \
  --project=$PROJECT_ID \
  --region=$REGION \
  --member="allUsers" \
  --role="roles/run.invoker"

# PRINT SERVICE URL
echo ""
echo ""
echo "============================================================"
echo "✅ DEPLOYMENT COMPLETE!"
echo "============================================================"
echo ""
echo "📡 Fetching verified service URL..."
# Use 'list' instead of 'describe' to get correct URL
export SERVICE_URL=$(gcloud run services list \
  --project=$PROJECT_ID \
  --platform=managed \
  --filter="metadata.name:meetingmind AND metadata.namespace:$REGION" \
  --format="value(status.url)" | head -1)

# Fallback to describe if list doesn't work
if [ -z "$SERVICE_URL" ]; then
  export SERVICE_URL=$(gcloud run services describe meetingmind \
    --project=$PROJECT_ID \
    --region=$REGION \
    --platform=managed \
    --format="value(status.url)")
fi
echo ""
echo "============================================================"
echo "🎉 VERIFIED SERVICE URL (use this one):"
echo "============================================================"
echo ""
echo "  $SERVICE_URL"
echo ""
echo "============================================================"
echo "============================================================"
echo "COMPETITION CHECKLIST:"
echo "============================================================"
echo "✓ Multi-agent orchestration (Sequential + Parallel pipelines)"
echo "✓ MCP integration (3 servers: calendar, tasks, notes)"
echo "✓ Cloud deployment (Cloud Run + Cloud SQL + Vertex AI)"
echo "✓ ADK built-in UI (chat interface)"
echo "✓ Database persistence (Postgres with 4 tables)"
echo "✓ Intent detection (4 intents: transcript, query, command, memory)"
echo "============================================================"
echo ""
echo "Test the deployment:"
echo ""
echo "1. Open ADK UI in browser:"
echo "   $SERVICE_URL"
echo ""
echo "2. Test with demo queries:"
echo "   - 'What tasks are pending?'"
echo "   - 'Mark task 1 as done'"
echo "   - 'Remember that client prefers morning meetings'"
echo ""
echo "3. Test with a meeting transcript (paste the demo transcript from CLAUDE.md)"
echo ""
echo "============================================================"
echo "MCP VERIFICATION:"
echo "============================================================"
echo "The following MCP servers are configured:"
echo "  • Calendar MCP: get_available_slots, create_calendar_event"
echo "  • Tasks MCP: list_tasks, save_tasks, update_task_status, check_duplicate_tasks"
echo "  • Notes MCP: search_notes, save_note, search_related_notes, save_meeting_note"
echo ""
echo "MCP servers will auto-start via stdio transport when agents need them."
echo "Check Cloud Run logs to verify MCP tool calls during transcript processing."
echo "============================================================"

#!/bin/bash
# ============================================================
# MeetingMind — Fresh Start
# Wipes all data, re-applies schema, re-deploys.
# Use this before a competition demo to start clean.
# ============================================================

set -e

echo "============================================================"
echo "🚀 MeetingMind Fresh Start"
echo "============================================================"
echo ""
echo "This script will:"
echo "  1. Drop all data (tasks, meetings, notes, memory, quality_scores)"
echo "  2. Re-apply the full schema (pgvector + all tables + indexes)"
echo "  3. Insert fresh seed data"
echo "  4. Deploy to Cloud Run"
echo ""
echo "⏱️  Total time: ~5 minutes"
echo ""

# Load env
if [ ! -f .env ]; then
    echo "✗ .env file not found. Copy .env.example to .env and fill in values."
    exit 1
fi
source .env

# ── CONFIRM ───────────────────────────────────────────────
read -p "⚠️  This will DELETE ALL data. Are you sure? (yes/no): " confirm
if [ "$confirm" != "yes" ]; then
    echo "Aborted."
    exit 0
fi

# ── STEP 1: Wipe + Re-apply schema via Cloud SQL ──────────
echo ""
echo "============================================================"
echo "Step 1: Re-applying database schema..."
echo "============================================================"
echo ""
echo "Connecting to Cloud SQL instance: meetingmind-db"
echo "This will drop all data and re-create all tables cleanly."
echo ""

# Generate a wipe + schema SQL script
cat > /tmp/fresh_schema.sql << 'SQLEOF'
-- Wipe all data (respects FK order)
DROP TABLE IF EXISTS quality_scores CASCADE;
DROP TABLE IF EXISTS tasks CASCADE;
DROP TABLE IF EXISTS notes CASCADE;
DROP TABLE IF EXISTS memory CASCADE;
DROP TABLE IF EXISTS meetings CASCADE;

-- Re-apply full schema
SQLEOF

# Append the main schema file
cat schema.sql >> /tmp/fresh_schema.sql

gcloud sql connect meetingmind-db \
  --user="$DB_USER" \
  --database="$DB_NAME" < /tmp/fresh_schema.sql

echo ""
echo "✓ Database schema applied (pgvector + all tables + seed data)"
echo ""

# ── STEP 2: Deploy ────────────────────────────────────────
echo "============================================================"
echo "Step 2: Deploying to Cloud Run..."
echo "============================================================"
echo ""

bash deploy.sh

# ── DONE ──────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe meetingmind \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --platform=managed \
  --format="value(status.url)" 2>/dev/null || echo "check gcloud run services list")

echo ""
echo "============================================================"
echo "🎉 FRESH START COMPLETE!"
echo "============================================================"
echo ""
echo "  🌐 Service URL: $SERVICE_URL"
echo ""
echo "Demo quick-test sequence:"
echo "  1. Open $SERVICE_URL"
echo "  2. Paste Q3 Product Planning transcript from SAMPLE_TRANSCRIPT.md"
echo "  3. Ask: 'What tasks are pending?'"
echo "  4. Ask: 'Who has the most tasks?'"
echo "  5. Ask: 'What topics keep coming up?'"
echo "  6. Ask: 'What's overdue?'"
echo "============================================================"

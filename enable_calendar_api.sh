#!/bin/bash
# ============================================================
# MeetingMind — Quick Calendar API Enable
# ============================================================

source .env

echo "Enabling Google Calendar API for project: $PROJECT_ID"

gcloud services enable calendar-json.googleapis.com \
  --project=$PROJECT_ID

if [ $? -eq 0 ]; then
    echo "✅ Google Calendar API enabled successfully"
    echo ""
    echo "Your service account ($SERVICE_ACCOUNT) can now:"
    echo "  • Create calendar events in its own calendar"
    echo "  • Generate Google Meet links automatically"
    echo "  • Send email invitations to attendees"
    echo ""
    echo "Next: Deploy with 'bash day6_deploy.sh'"
else
    echo "❌ Failed to enable Calendar API"
    exit 1
fi

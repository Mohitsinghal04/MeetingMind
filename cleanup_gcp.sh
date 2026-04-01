#!/bin/bash
# ============================================================
# MeetingMind — Complete GCP Cleanup Script
# This deletes ALL resources and starts fresh
# ============================================================

set -e  # Exit on error

# Load environment variables
if [ ! -f .env ]; then
    echo "❌ ERROR: .env file not found"
    echo "Please create .env file with your PROJECT_ID at minimum"
    exit 1
fi

source .env

# Verify critical variables
if [ -z "$PROJECT_ID" ] || [ "$PROJECT_ID" = "your-project-id" ]; then
    echo "❌ ERROR: PROJECT_ID not set in .env"
    echo "Please update .env with your actual GCP project ID"
    exit 1
fi

# Set defaults if not provided
REGION=${REGION:-asia-south1}
SA_NAME=${SA_NAME:-meetingmind-sa}
DB_INSTANCE=${DB_INSTANCE:-meetingmind-db}

echo "============================================================"
echo "⚠️  GCP CLEANUP - ALL RESOURCES WILL BE DELETED"
echo "============================================================"
echo ""
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo ""
echo "This will delete:"
echo "  • Cloud Run service: meetingmind"
echo "  • Cloud SQL instance: $DB_INSTANCE (⚠️ takes 5-10 min)"
echo "  • Container images in Artifact Registry"
echo "  • Service account: $SA_NAME"
echo ""
read -p "Are you sure? Type 'yes' to continue: " confirmation

if [ "$confirmation" != "yes" ]; then
    echo "Cleanup cancelled."
    exit 0
fi

echo ""
echo "============================================================"
echo "Starting cleanup..."
echo "============================================================"
echo ""

# ── 1. DELETE CLOUD RUN SERVICE ───────────────────────────────
echo "🗑️  Deleting Cloud Run service..."
if gcloud run services describe meetingmind --project=$PROJECT_ID --region=$REGION --platform=managed &>/dev/null; then
    gcloud run services delete meetingmind \
      --project=$PROJECT_ID \
      --region=$REGION \
      --platform=managed \
      --quiet
    echo "✓ Cloud Run service deleted"
else
    echo "  (Cloud Run service not found - skipping)"
fi

# ── 2. DELETE ARTIFACT REGISTRY IMAGES ─────────────────────────
echo ""
echo "🗑️  Cleaning up Artifact Registry..."
# List and delete all meetingmind images
if gcloud artifacts repositories describe cloud-run-source-deploy --location=$REGION --project=$PROJECT_ID &>/dev/null; then
    echo "  Deleting meetingmind images..."
    gcloud artifacts docker images delete \
      $REGION-docker.pkg.dev/$PROJECT_ID/cloud-run-source-deploy/meetingmind \
      --project=$PROJECT_ID \
      --delete-tags \
      --quiet 2>/dev/null || echo "  (No images found)"
    echo "✓ Artifact Registry cleaned"
else
    echo "  (Artifact Registry repository not found - skipping)"
fi

# ── 3. DELETE CLOUD SQL INSTANCE (SLOW) ───────────────────────
echo ""
echo "🗑️  Deleting Cloud SQL instance..."
echo "  ⚠️  This takes 5-10 minutes - please wait..."
if gcloud sql instances describe $DB_INSTANCE --project=$PROJECT_ID &>/dev/null; then
    gcloud sql instances delete $DB_INSTANCE \
      --project=$PROJECT_ID \
      --quiet
    echo "✓ Cloud SQL instance deleted"
else
    echo "  (Cloud SQL instance not found - skipping)"
fi

# ── 4. DELETE SERVICE ACCOUNT ──────────────────────────────────
echo ""
echo "🗑️  Deleting service account..."
SERVICE_ACCOUNT="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
if gcloud iam service-accounts describe $SERVICE_ACCOUNT --project=$PROJECT_ID &>/dev/null; then
    # Remove IAM policy bindings first
    echo "  Removing IAM roles..."
    gcloud projects remove-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$SERVICE_ACCOUNT" \
      --role="roles/aiplatform.user" \
      --quiet 2>/dev/null || true

    gcloud projects remove-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$SERVICE_ACCOUNT" \
      --role="roles/cloudsql.client" \
      --quiet 2>/dev/null || true

    gcloud projects remove-iam-policy-binding $PROJECT_ID \
      --member="serviceAccount:$SERVICE_ACCOUNT" \
      --role="roles/logging.logWriter" \
      --quiet 2>/dev/null || true

    # Delete the service account
    gcloud iam service-accounts delete $SERVICE_ACCOUNT \
      --project=$PROJECT_ID \
      --quiet
    echo "✓ Service account deleted"
else
    echo "  (Service account not found - skipping)"
fi

# ── 5. RESET .env FILE ─────────────────────────────────────────
echo ""
echo "🗑️  Resetting .env file to template..."
cat > .env << 'EOF'
# ============================================================
# MeetingMind — Environment Variables
# Fill in your values from day1_gcp_setup.sh output
# ============================================================

# GCP Project Configuration
# Get this from: gcloud config get-value project
PROJECT_ID=your-project-id

# Get this from: gcloud projects describe $PROJECT_ID --format="value(projectNumber)"
PROJECT_NUMBER=your-project-number

# Service Account Configuration
SA_NAME=meetingmind-sa
SERVICE_ACCOUNT=meetingmind-sa@your-project-id.iam.gserviceaccount.com

# GCP Region
REGION=asia-south1

# Gemini Model
MODEL=gemini-2.5-flash

# Cloud SQL Postgres Configuration
# Get DB_HOST from: gcloud sql instances describe meetingmind-db --format="value(ipAddresses[0].ipAddress)"
DB_HOST=your-cloud-sql-public-ip
DB_NAME=meetingmind
DB_USER=meetingmind_user
DB_PASSWORD=MeetingMind@2026!
DB_PORT=5432

# ============================================================
# INSTRUCTIONS:
# ============================================================
#
# 1. If you haven't run day1_gcp_setup.sh yet, run it first:
#    bash day1_gcp_setup.sh
#
# 2. The script will output all values at the end. Copy them here.
#
# 3. Replace the placeholder values above with your actual values:
#    - PROJECT_ID: your actual GCP project ID
#    - PROJECT_NUMBER: your project number (numeric)
#    - SERVICE_ACCOUNT: replace 'your-project-id' with your actual project ID
#    - DB_HOST: the public IP address of your Cloud SQL instance
#    - DB_PASSWORD: use the password from day1_gcp_setup.sh (or change both places)
#
# 4. Quick validation after filling values:
#    python3 -c "import os; from dotenv import load_dotenv; load_dotenv(); print(f'Project: {os.getenv(\"PROJECT_ID\")}'); print(f'DB Host: {os.getenv(\"DB_HOST\")}')"
#
EOF
echo "✓ .env reset to template"

# ── COMPLETION ─────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "✅ CLEANUP COMPLETE!"
echo "============================================================"
echo ""
echo "All MeetingMind resources have been deleted from GCP."
echo ""
echo "Next steps to redeploy from scratch:"
echo ""
echo "1. Edit day1_gcp_setup.sh and set your PROJECT_ID:"
echo "   export PROJECT_ID=\"your-actual-project-id\""
echo ""
echo "2. Run day1_gcp_setup.sh to recreate infrastructure:"
echo "   bash day1_gcp_setup.sh"
echo "   (This takes 10-15 minutes - Cloud SQL creation is slow)"
echo ""
echo "3. Copy the output values to .env file"
echo ""
echo "4. Load the database schema:"
echo "   gcloud sql connect meetingmind-db --user=meetingmind_user --database=meetingmind"
echo "   (Then paste the contents of schema.sql)"
echo ""
echo "5. Deploy to Cloud Run:"
echo "   bash day6_deploy.sh"
echo ""
echo "============================================================"

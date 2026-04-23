#!/bin/bash
# ============================================================
# MeetingMind — GCP Setup
# Run this line by line in Cloud Shell
# ============================================================

# STEP 1: Set your project
export PROJECT_ID="genai-hackathon-2026-491904"
export REGION="us-central1"          # ← verify this matches your .env
export SA_NAME="meetingmind-sa"
export DB_INSTANCE="meetingmind-db"
export DB_NAME="meetingmind"
export DB_USER="meetingmind_user"
export DB_PASSWORD="temp-pwd"        # ← CHANGE THIS to a strong password

gcloud config set project $PROJECT_ID
echo "Project set to: $PROJECT_ID"

# STEP 2: Enable all required APIs
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  compute.googleapis.com \
  sqladmin.googleapis.com \
  sql-component.googleapis.com \
  cloudresourcemanager.googleapis.com \
  logging.googleapis.com \
  gmail.googleapis.com \
  docs.googleapis.com \
  drive.googleapis.com

echo "✓ APIs enabled (core + Google Workspace)"

# STEP 3: Create Cloud SQL Postgres instance
# NOTE: This takes 5-10 minutes
gcloud sql instances create $DB_INSTANCE \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --storage-type=SSD \
  --storage-size=10GB \
  --authorized-networks=0.0.0.0/0 \
  --no-backup

echo "✓ Cloud SQL instance created"

# STEP 4: Set the postgres root password
gcloud sql users set-password postgres \
  --instance=$DB_INSTANCE \
  --password=$DB_PASSWORD

# STEP 5: Create the application database user
gcloud sql users create $DB_USER \
  --instance=$DB_INSTANCE \
  --password=$DB_PASSWORD

echo "✓ DB user created"

# STEP 6: Create the database
gcloud sql databases create $DB_NAME \
  --instance=$DB_INSTANCE

echo "✓ Database created"

# STEP 7: Get the DB public IP
export DB_HOST=$(gcloud sql instances describe $DB_INSTANCE \
  --format="value(ipAddresses[0].ipAddress)")
echo "DB_HOST = $DB_HOST"

# STEP 8: Create IAM service account
gcloud iam service-accounts create $SA_NAME \
  --display-name="MeetingMind Service Account"

export SERVICE_ACCOUNT="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
echo "✓ Service account: $SERVICE_ACCOUNT"

# STEP 9: Grant all required IAM roles
# Vertex AI (Gemini + Text Embeddings)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/aiplatform.user"

# Cloud SQL
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/cloudsql.client"

# Cloud Logging
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/logging.logWriter"

# Artifact Registry (for Cloud Build pushing Docker images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/artifactregistry.writer"

# Google Workspace (Gmail send, Docs create, Drive read)
# NOTE: Domain-Wide Delegation must be configured separately in Google Workspace Admin
# for service accounts to act on behalf of users. For the hackathon demo, the service
# account can only access resources it owns (e.g. its own Drive).
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/iam.serviceAccountTokenCreator"

echo "✓ IAM roles granted"

# STEP 10: Get project number
export PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID \
  --format="value(projectNumber)")

# STEP 11: Print .env values
echo ""
echo "============================================================"
echo "COPY THESE VALUES INTO YOUR .env FILE:"
echo "============================================================"
echo "PROJECT_ID=$PROJECT_ID"
echo "PROJECT_NUMBER=$PROJECT_NUMBER"
echo "SA_NAME=$SA_NAME"
echo "SERVICE_ACCOUNT=$SERVICE_ACCOUNT"
echo "MODEL=gemini-2.5-flash"
echo "DB_HOST=$DB_HOST"
echo "DB_NAME=$DB_NAME"
echo "DB_USER=$DB_USER"
echo "DB_PASSWORD=$DB_PASSWORD"
echo "DB_PORT=5432"
echo "REGION=$REGION"
echo "============================================================"
echo ""
echo "NEXT STEPS:"
echo "1. Copy these values to your .env file"
echo "2. Connect to Cloud SQL and run schema.sql:"
echo "   gcloud sql connect $DB_INSTANCE --user=$DB_USER --database=$DB_NAME"
echo "   Then paste the full contents of schema.sql (includes pgvector + all tables)"
echo "3. Deploy the application:"
echo "   bash deploy.sh"
echo "============================================================"
echo ""
echo "NOTE: pgvector is pre-installed in Cloud SQL Postgres 15+"
echo "      The schema.sql already includes: CREATE EXTENSION IF NOT EXISTS vector;"
echo "============================================================"

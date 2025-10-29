#!/bin/bash

# Deployment Script for DV360 YouTube Channel Analyzer Cloud Function
# This script deploys the function to Google Cloud Platform

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}DV360 YouTube Channel Analyzer${NC}"
echo -e "${GREEN}Cloud Function Deployment Script${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Load environment variables
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo "Please create .env file from .env.example and configure it."
    exit 1
fi

source .env

# Verify required environment variables
if [ -z "$GCP_PROJECT_ID" ]; then
    echo -e "${RED}ERROR: GCP_PROJECT_ID not set in .env${NC}"
    exit 1
fi

if [ -z "$GCP_BUCKET_NAME" ]; then
    echo -e "${RED}ERROR: GCP_BUCKET_NAME not set in .env${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Project ID: $GCP_PROJECT_ID"
echo "  Bucket: $GCP_BUCKET_NAME"
echo "  Region: us-central1"
echo

# Set the GCP project
echo -e "${YELLOW}Setting GCP project...${NC}"
gcloud config set project $GCP_PROJECT_ID

# Create deployment package (exclude unnecessary files)
echo -e "${YELLOW}Preparing deployment package...${NC}"

# Create .gcloudignore if it doesn't exist
cat > .gcloudignore << EOF
.git/
.gitignore
__pycache__/
*.pyc
.env
.env.example
*.md
deploy.sh
test_*.py
.DS_Store
.vscode/
.idea/
EOF

echo -e "${GREEN}✓ Deployment package prepared${NC}"

# Deploy the Cloud Function
echo -e "${YELLOW}Deploying Cloud Function...${NC}"
echo

gcloud functions deploy dv360-channel-analyzer \
    --gen2 \
    --runtime=python311 \
    --region=us-central1 \
    --source=. \
    --entry-point=process_dv360_report \
    --trigger-http \
    --no-allow-unauthenticated \
    --timeout=3600s \
    --memory=1GB \
    --max-instances=1 \
    --set-env-vars="GCP_PROJECT_ID=$GCP_PROJECT_ID,GCP_BUCKET_NAME=$GCP_BUCKET_NAME,FIRESTORE_COLLECTION=$FIRESTORE_COLLECTION,GMAIL_SUBJECT_FILTER=$GMAIL_SUBJECT_FILTER,RECIPIENT_EMAIL=$RECIPIENT_EMAIL,OPENAI_MODEL=$OPENAI_MODEL,BATCH_SIZE=$BATCH_SIZE,MAX_WORKERS=$MAX_WORKERS,RATE_LIMIT_DELAY=$RATE_LIMIT_DELAY" \
    --set-secrets="YOUTUBE_API_KEY=youtube-api-key:latest,OPENAI_API_KEY=openai-api-key:latest,GMAIL_CREDENTIALS=gmail-credentials:latest,GMAIL_TOKEN=gmail-token:latest"

echo
echo -e "${GREEN}✓ Cloud Function deployed successfully!${NC}"
echo

# Get the function URL
FUNCTION_URL=$(gcloud functions describe dv360-channel-analyzer --region=us-central1 --format="value(serviceConfig.uri)" --gen2)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "Function URL: $FUNCTION_URL"
echo
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Set up Cloud Scheduler to trigger this function weekly"
echo "2. Upload secrets to Secret Manager:"
echo "   - youtube-api-key"
echo "   - openai-api-key"
echo "   - gmail-credentials"
echo "   - gmail-token"
echo
echo -e "${YELLOW}Create Cloud Scheduler job:${NC}"
echo "gcloud scheduler jobs create http dv360-analyzer-weekly \\"
echo "  --location=us-central1 \\"
echo "  --schedule=\"0 9 * * 1\" \\"
echo "  --uri=\"$FUNCTION_URL\" \\"
echo "  --http-method=POST \\"
echo "  --oidc-service-account-email=<YOUR-SERVICE-ACCOUNT>@$GCP_PROJECT_ID.iam.gserviceaccount.com \\"
echo "  --time-zone=\"America/New_York\""
echo
echo -e "${GREEN}Done!${NC}"

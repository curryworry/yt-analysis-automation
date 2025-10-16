#!/bin/bash

# Setup Script for Google Cloud Secret Manager
# This script helps upload credentials to Secret Manager

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}GCP Secret Manager Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo

# Load .env
if [ ! -f .env ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    exit 1
fi

source .env

# Set project
echo -e "${YELLOW}Setting GCP project to: $GCP_PROJECT_ID${NC}"
gcloud config set project $GCP_PROJECT_ID

# Create secrets
echo -e "${YELLOW}Creating secrets in Secret Manager...${NC}"
echo

# YouTube API Key
echo -e "${YELLOW}1. Creating youtube-api-key secret...${NC}"
if [ -z "$YOUTUBE_API_KEY" ]; then
    echo -e "${RED}ERROR: YOUTUBE_API_KEY not set in .env${NC}"
    exit 1
fi
echo -n "$YOUTUBE_API_KEY" | gcloud secrets create youtube-api-key --data-file=- 2>/dev/null || \
    echo -n "$YOUTUBE_API_KEY" | gcloud secrets versions add youtube-api-key --data-file=-
echo -e "${GREEN}✓ youtube-api-key created/updated${NC}"

# OpenAI API Key
echo -e "${YELLOW}2. Creating openai-api-key secret...${NC}"
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${RED}ERROR: OPENAI_API_KEY not set in .env${NC}"
    exit 1
fi
echo -n "$OPENAI_API_KEY" | gcloud secrets create openai-api-key --data-file=- 2>/dev/null || \
    echo -n "$OPENAI_API_KEY" | gcloud secrets versions add openai-api-key --data-file=-
echo -e "${GREEN}✓ openai-api-key created/updated${NC}"

# Gmail credentials
echo -e "${YELLOW}3. Creating gmail-credentials secret...${NC}"
if [ ! -f "credentials.json" ]; then
    echo -e "${RED}ERROR: credentials.json not found${NC}"
    exit 1
fi
gcloud secrets create gmail-credentials --data-file=credentials.json 2>/dev/null || \
    gcloud secrets versions add gmail-credentials --data-file=credentials.json
echo -e "${GREEN}✓ gmail-credentials created/updated${NC}"

# Gmail token
echo -e "${YELLOW}4. Creating gmail-token secret...${NC}"
if [ ! -f "gmail_token.json" ]; then
    echo -e "${RED}ERROR: gmail_token.json not found${NC}"
    exit 1
fi
gcloud secrets create gmail-token --data-file=gmail_token.json 2>/dev/null || \
    gcloud secrets versions add gmail-token --data-file=gmail_token.json
echo -e "${GREEN}✓ gmail-token created/updated${NC}"

echo
echo -e "${YELLOW}Setting IAM permissions for service account...${NC}"

SERVICE_ACCOUNT="$GCP_PROJECT_ID@appspot.gserviceaccount.com"

# Grant access to each secret
for SECRET in youtube-api-key openai-api-key gmail-credentials gmail-token; do
    gcloud secrets add-iam-policy-binding $SECRET \
        --member="serviceAccount:$SERVICE_ACCOUNT" \
        --role="roles/secretmanager.secretAccessor" \
        --quiet
done

echo -e "${GREEN}✓ IAM permissions granted${NC}"
echo
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Secret Manager Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo
echo "All secrets have been created and permissions granted."
echo "You can now deploy the Cloud Function with: ./deploy.sh"
echo

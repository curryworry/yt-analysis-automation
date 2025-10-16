# DV360 YouTube Channel Categorization System

Automated system to analyze DV360 YouTube placement reports and identify children's content channels using AI.

## Features

- **Automated Email Processing**: Monitors Gmail for DV360 reports and downloads attachments
- **Smart Pre-filtering**: Uses keyword matching to reduce API costs
- **Intelligent Caching**: Stores results in Firestore to avoid re-analyzing channels
- **AI-Powered Analysis**: Uses OpenAI GPT-4o-mini for accurate content categorization
- **Scalable Architecture**: Handles 125K+ rows efficiently with batch processing
- **Weekly Automation**: Runs automatically via Cloud Scheduler

## Architecture

```
Gmail → Cloud Function → CSV Parser → Firestore Cache Check
                              ↓
                         YouTube API (metadata)
                              ↓
                         OpenAI GPT-4o-mini (categorization)
                              ↓
                         Firestore (save results)
                              ↓
                         Gmail (send results)
```

## Project Structure

```
yt-automation/
├── main.py                      # Main Cloud Function handler
├── config.yaml                  # Configuration (keywords, prompts)
├── requirements.txt             # Python dependencies
├── deploy.sh                    # Deployment script
├── .env.example                 # Environment variables template
├── services/
│   ├── gmail_service.py         # Gmail API integration
│   ├── youtube_service.py       # YouTube Data API integration
│   ├── firestore_service.py     # Firestore caching
│   └── openai_service.py        # OpenAI categorization
└── utils/
    └── csv_processor.py         # CSV parsing and filtering
```

## Setup Instructions

### 1. Local Setup

```bash
# Clone or navigate to the project directory
cd yt-automation

# Create .env file from template
cp .env.example .env

# Edit .env with your actual credentials
nano .env
```

### 2. Configure Environment Variables

Edit `.env` file with your actual values:

```bash
# GCP Configuration
GCP_PROJECT_ID=yt-channel-analysis-475221
GCP_BUCKET_NAME=yt-channel-analysis-temp-files
GCP_SERVICE_ACCOUNT_KEY_PATH=./yt-channel-analysis-475221-xxxxx.json

# API Keys
YOUTUBE_API_KEY=your_actual_youtube_api_key
OPENAI_API_KEY=your_actual_openai_api_key

# Gmail Configuration
GMAIL_CREDENTIALS_PATH=./credentials.json
GMAIL_TOKEN_PATH=./gmail_token.json
RECIPIENT_EMAIL=ashwinacquireonline@gmail.com
```

### 3. Install Dependencies (for local testing)

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 4. Test Locally

```bash
# Test the function locally
python main.py
```

### 5. Set Up Google Cloud Secrets

Store sensitive credentials in Secret Manager (more secure than environment variables):

```bash
# Set your project
gcloud config set project yt-channel-analysis-475221

# Create secrets
echo -n "YOUR_YOUTUBE_API_KEY" | gcloud secrets create youtube-api-key --data-file=-
echo -n "YOUR_OPENAI_API_KEY" | gcloud secrets create openai-api-key --data-file=-

# Upload credential files
gcloud secrets create gmail-credentials --data-file=credentials.json
gcloud secrets create gmail-token --data-file=gmail_token.json

# Grant Cloud Function access to secrets
gcloud secrets add-iam-policy-binding youtube-api-key \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding openai-api-key \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-credentials \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding gmail-token \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"
```

### 6. Deploy to Google Cloud Functions

```bash
# Run the deployment script
./deploy.sh
```

The script will:
- Deploy the Cloud Function to GCP
- Configure environment variables
- Link secrets from Secret Manager
- Provide the function URL

### 7. Set Up Cloud Scheduler (Weekly Trigger)

```bash
# Create a Cloud Scheduler job to run every Monday at 9 AM
gcloud scheduler jobs create http dv360-analyzer-weekly \
  --location=us-central1 \
  --schedule="0 9 * * 1" \
  --uri="https://us-central1-yt-channel-analysis-475221.cloudfunctions.net/dv360-channel-analyzer" \
  --http-method=POST \
  --oidc-service-account-email=yt-channel-analysis-475221@appspot.gserviceaccount.com \
  --time-zone="America/New_York"
```

### 8. Test the Deployed Function

```bash
# Manually trigger the function
gcloud scheduler jobs run dv360-analyzer-weekly --location=us-central1

# View logs
gcloud functions logs read dv360-channel-analyzer --region=us-central1 --limit=50
```

## Configuration

### Keyword Filters

Edit [config.yaml](config.yaml) to modify the keyword list:

```yaml
keywords:
  - baby
  - nursery
  - rhyme
  - kid
  - kids
  - children
  - toddler
  - preschool
```

### OpenAI Prompts

Customize the AI categorization prompts in [config.yaml](config.yaml):

```yaml
openai:
  system_prompt: |
    You are an expert at analyzing YouTube channels...

  user_prompt_template: |
    Analyze this YouTube channel...
```

## How It Works

### Workflow Steps

1. **Email Monitoring**: Searches Gmail for latest DV360 report (subject: "YouTube Placement Check - DV360")
2. **Download & Extract**: Downloads zip attachment and extracts CSV file
3. **Pre-filtering**: Filters channels using keyword matching (reduces API costs by ~90%)
4. **Cache Check**: Queries Firestore for previously analyzed channels
5. **YouTube Metadata**: Fetches channel details using YouTube Data API
6. **AI Categorization**: Uses OpenAI GPT-4o-mini to determine if content targets children
7. **Cache Results**: Saves categorization to Firestore for future lookups
8. **Generate Report**: Creates CSV with flagged channels
9. **Email Results**: Sends report back to recipient email

### Cost Optimization

- **Keyword Pre-filtering**: Reduces channels to analyze by ~80-90%
- **Firestore Caching**: Avoids re-analyzing known channels (saves ~$0.15 per 1000 channels)
- **Batch Processing**: Efficiently handles large datasets
- **Rate Limiting**: Respects API quotas

### Expected Costs (per run)

- YouTube Data API: ~$0.05 (assuming 500 new channels)
- OpenAI API: ~$0.10 (500 channels × $0.0002)
- Firestore: ~$0.01 (reads/writes)
- Cloud Functions: ~$0.02 (compute time)
- **Total: ~$0.18 per weekly run** (~$9/year)

## Monitoring & Debugging

### View Logs

```bash
# Real-time logs
gcloud functions logs read dv360-channel-analyzer --region=us-central1 --limit=100 --follow

# Filter for errors
gcloud functions logs read dv360-channel-analyzer --region=us-central1 --limit=50 | grep ERROR
```

### Query Firestore Cache

```python
from google.cloud import firestore

db = firestore.Client(project='yt-channel-analysis-475221')
collection = db.collection('channel_categories')

# Get all children's content channels
for doc in collection.where('is_children_content', '==', True).stream():
    print(doc.to_dict())
```

### Check API Usage

- **YouTube API**: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas
- **OpenAI API**: https://platform.openai.com/usage
- **Cloud Functions**: https://console.cloud.google.com/functions/list

## Troubleshooting

### Function Times Out

Increase timeout in [deploy.sh](deploy.sh):
```bash
--timeout=540s  # Increase to 900s if needed
```

### YouTube API Quota Exceeded

- Default quota: 10,000 units/day
- Each channel lookup: ~5 units
- Request quota increase: https://support.google.com/youtube/contact/yt_api_form

### Gmail Authentication Fails

Regenerate Gmail token:
```bash
python get_gmail_token.py
```

Then update the secret:
```bash
gcloud secrets versions add gmail-token --data-file=gmail_token.json
```

### Firestore Permission Issues

Grant Firestore access to service account:
```bash
gcloud projects add-iam-policy-binding yt-channel-analysis-475221 \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/datastore.user"
```

## Maintenance

### Update Keywords

```bash
# Edit config.yaml locally
nano config.yaml

# Redeploy
./deploy.sh
```

### Clear Firestore Cache (Force Re-analysis)

```python
from google.cloud import firestore

db = firestore.Client(project='yt-channel-analysis-475221')
collection = db.collection('channel_categories')

# Delete all documents
docs = collection.stream()
for doc in docs:
    doc.reference.delete()
```

### Update Dependencies

```bash
# Update requirements.txt
pip install --upgrade google-cloud-firestore openai google-api-python-client

# Freeze versions
pip freeze > requirements.txt

# Redeploy
./deploy.sh
```

## Security Best Practices

- ✅ Credentials stored in Secret Manager (not in code)
- ✅ `.gitignore` excludes sensitive files
- ✅ Cloud Function requires authentication
- ✅ Service account has minimal required permissions
- ✅ HTTPS-only communication

## Support

For issues or questions:
1. Check logs: `gcloud functions logs read dv360-channel-analyzer --region=us-central1`
2. Review Firestore data
3. Verify API quotas
4. Test locally with `python main.py`

## License

Internal use only - Acquire Online

---

**Last Updated**: 2025-10-16
**Version**: 1.0.0

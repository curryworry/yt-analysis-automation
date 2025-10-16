# Quick Start Guide - DV360 Channel Analyzer

Follow these steps to deploy the system to Google Cloud Functions.

## Prerequisites Checklist

- ✅ GCP Project: `yt-channel-analysis-475221`
- ✅ Storage Bucket: `yt-channel-analysis-temp-files`
- ✅ Firestore: Enabled (nam5)
- ✅ Gmail account: `ashwinacquireonline@gmail.com`
- ✅ Service account key: `yt-channel-analysis-475221-xxxxx.json`
- ✅ OAuth credentials: `credentials.json`
- ✅ Gmail token: `gmail_token.json`
- ⚠️ YouTube API key (add to .env)
- ⚠️ OpenAI API key (add to .env)

## Setup Steps (5 minutes)

### 1. Create .env File

```bash
cp .env.example .env
nano .env  # or use your preferred editor
```

Add your API keys:
```bash
YOUTUBE_API_KEY=AIzaSy...your_actual_key
OPENAI_API_KEY=sk-...your_actual_key
```

### 2. Install gcloud CLI (if not installed)

```bash
# macOS
brew install google-cloud-sdk

# Verify
gcloud --version
```

### 3. Authenticate with GCP

```bash
gcloud auth login
gcloud config set project yt-channel-analysis-475221
```

### 4. Upload Secrets to Secret Manager

```bash
./setup_secrets.sh
```

This script will:
- Create secrets for API keys and credentials
- Set IAM permissions
- Verify everything is configured

### 5. Deploy Cloud Function

```bash
./deploy.sh
```

This will:
- Deploy the function to `us-central1`
- Configure environment variables
- Link secrets
- Output the function URL

### 6. Set Up Weekly Scheduler

```bash
# Create Cloud Scheduler job (runs every Monday at 9 AM)
gcloud scheduler jobs create http dv360-analyzer-weekly \
  --location=us-central1 \
  --schedule="0 9 * * 1" \
  --uri="FUNCTION_URL_FROM_DEPLOY" \
  --http-method=POST \
  --oidc-service-account-email=yt-channel-analysis-475221@appspot.gserviceaccount.com \
  --time-zone="America/New_York"
```

Replace `FUNCTION_URL_FROM_DEPLOY` with the actual URL from step 5.

### 7. Test the Function

```bash
# Manually trigger
gcloud scheduler jobs run dv360-analyzer-weekly --location=us-central1

# Watch logs
gcloud functions logs read dv360-channel-analyzer --region=us-central1 --limit=50 --follow
```

## Verification

After deployment, verify:

1. **Cloud Function**: https://console.cloud.google.com/functions/list
2. **Cloud Scheduler**: https://console.cloud.google.com/cloudscheduler
3. **Secret Manager**: https://console.cloud.google.com/security/secret-manager
4. **Firestore**: https://console.cloud.google.com/firestore

## Expected Results

When the function runs successfully, you'll receive an email with:
- CSV attachment containing flagged children's content channels
- Summary statistics (cache hits, API calls, processing time)

## Troubleshooting

### "Permission denied" errors
```bash
# Grant necessary permissions
gcloud projects add-iam-policy-binding yt-channel-analysis-475221 \
    --member="serviceAccount:yt-channel-analysis-475221@appspot.gserviceaccount.com" \
    --role="roles/datastore.user"
```

### Function times out
Edit [deploy.sh](deploy.sh) and increase `--timeout=540s` to `--timeout=900s`

### No email found
Check:
1. Gmail has DV360 report from `noreply@google.com`
2. Subject contains "YouTube Placement Check - DV360"
3. Email received within last 7 days

### View detailed logs
```bash
gcloud functions logs read dv360-channel-analyzer \
  --region=us-central1 \
  --limit=100 \
  --format="table(time, log)"
```

## Cost Monitoring

Monitor costs at:
- **Cloud Functions**: https://console.cloud.google.com/billing
- **YouTube API**: https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas
- **OpenAI**: https://platform.openai.com/usage

Expected: ~$0.18 per weekly run (~$9/year)

## Next Steps

1. Test the function manually to ensure everything works
2. Monitor the first scheduled run on Monday
3. Review results email and adjust keywords if needed
4. Check Firestore cache growth
5. Monitor API usage and costs

## Support

For issues:
1. Check [README.md](README.md) for detailed troubleshooting
2. Review logs: `gcloud functions logs read dv360-channel-analyzer --region=us-central1`
3. Verify all secrets are set correctly
4. Test locally: `python main.py`

---

**Ready to deploy?** Run `./setup_secrets.sh` followed by `./deploy.sh`

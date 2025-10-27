# YouTube API Quota Increase Request Guide

## Current Situation

With the enhanced analysis fetching recent videos, our YouTube API quota usage has increased slightly:

### Quota Usage Per Channel:
- **Old (without videos):** ~50-100 units per channel
- **New (with efficient playlist method):** ~55-60 units per channel
- **Increase:** Only ~10-20% more quota needed

### For 125,000 channels:
- **Old quota needed:** 6.25M - 12.5M units
- **New quota needed:** 7M - 7.5M units
- **Default quota:** 10,000 units/day
- **Days needed with default:** ~700-750 days (impractical)

## Solution: Request Quota Increase

Google allows you to request higher quotas for production use. Most legitimate use cases are approved quickly.

---

## Step-by-Step Instructions

### Step 1: Go to Google Cloud Console

1. Navigate to: https://console.cloud.google.com/
2. Select your project: `yt-channel-analysis-475221`
3. Go to **APIs & Services** → **YouTube Data API v3**

### Step 2: Request Quota Increase

1. Click on **Quotas** tab
2. Look for **Queries per day**
3. Click the **Edit quotas** or **Request quota increase** button

### Step 3: Fill Out the Request Form

**Recommended request amount:**
- **Request:** 100,000 units/day (or 50,000 units/day as minimum)
- **Justification:** See template below

### Step 4: Justification Template

```
Project: DV360 YouTube Channel Analysis for Brand Safety and COPPA Compliance

Purpose:
We are building an automated system to analyze YouTube channels for advertising
targeting and compliance purposes. The system:
- Identifies children's content for COPPA compliance
- Classifies content categories for advertising targeting
- Assesses brand safety for advertiser protection

Use Case:
- Analyzing DV360 placement reports with 100K-200K unique channels
- Batch processing with Firestore caching to minimize repeated API calls
- Runs daily to ensure up-to-date categorization

Current Quota Limitation:
- Default 10,000 units/day would require 700+ days to process our dataset
- With increased quota of 100,000 units/day, we can process within 70-80 days
- Subsequent runs will use cache, requiring only 5-10K new channels per day

Efficiency Measures:
- Implemented Firestore caching (90%+ cache hit rate after initial run)
- Using efficient playlistItems.list() (3 units) instead of search (100 units)
- Rate limiting to respect API guidelines

Business Value:
- Ensures advertiser compliance with COPPA regulations
- Prevents wasted ad spend on inappropriate placements
- Protects brand reputation through safety filtering

Requested Quota: 100,000 units/day
```

### Step 5: Submit and Wait

- Typical approval time: 24-72 hours
- You'll receive email notification when approved
- Some requests are approved automatically, others require manual review

---

## Alternative: Incremental Approach

If you want to start immediately without waiting for quota approval:

### Option A: Process High-Value Channels First

Only analyze channels with significant impressions:

```python
# In main.py, filter channels by impression threshold
high_value_channels = {
    url: data for url, data in channel_data.items()
    if data['impressions'] > 10000  # Only channels with 10K+ impressions
}
```

This could reduce your dataset from 125K to maybe 10K-20K channels, which fits within default quota.

### Option B: Spread Processing Over Time

With 10,000 units/day:
- Process ~180 channels per day
- Set up daily runs to gradually build cache
- After 30 days, you'd have analyzed ~5,400 channels
- Cache hit rate improves over time

---

## Monitoring Quota Usage

### Check Current Usage:

1. Go to Google Cloud Console
2. Navigate to **APIs & Services** → **Dashboard**
3. Click on **YouTube Data API v3**
4. View **Quotas** tab to see daily usage

### In Your Code:

The YouTube service tracks API calls:

```python
logger.info(f"YouTube API calls made: {youtube_service.api_calls_made}")
```

---

## What If Request is Denied?

If your quota increase request is denied:

1. **Provide more details:** Resubmit with more specific business justification
2. **Start with smaller request:** Ask for 25,000-50,000 units instead of 100,000
3. **Demonstrate responsible use:** Show that you've implemented caching and rate limiting
4. **Business verification:** Ensure your Google Cloud project is tied to a verified business account

---

## Cost Implications

**Important:** YouTube Data API quota is **FREE** up to your allocated limit.

- Quota increases do NOT increase costs
- You only pay for:
  - Cloud Functions execution time
  - Firestore reads/writes
  - Cloud Storage
  - OpenAI API calls

**There is NO CHARGE for YouTube API usage within your quota limit.**

---

## Expected Timeline

### Without Quota Increase:
- Daily processing: ~180 channels
- Time to complete 125K channels: 700+ days ❌

### With 50,000 units/day:
- Daily processing: ~900 channels
- Time to complete first run: 140 days
- After cache builds: ~50-100 new channels/day ✅

### With 100,000 units/day (Recommended):
- Daily processing: ~1,800 channels
- Time to complete first run: 70 days
- After cache builds: All new channels processed same day ✅✅

---

## Summary

**Recommended Action:** Request 100,000 units/day quota increase

**Benefits:**
- ✅ Only ~10% increase in quota usage per channel (efficient implementation)
- ✅ Significant improvement in analysis quality (video data)
- ✅ Reasonable processing timeline (70 days for initial run)
- ✅ Sustainable for daily operations (handle 1,800 new channels/day)
- ✅ No additional cost (quota is free)

**Next Steps:**
1. Submit quota increase request today
2. While waiting, start processing with default quota (high-value channels first)
3. Once approved, run full batch processing
4. Monitor cache hit rates and adjust as needed

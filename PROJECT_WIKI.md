# Project Wiki: DV360 YouTube Channel Analyzer

## 1. Project Overview
This project automates the analysis of YouTube channels from DV360 placement reports. It identifies "children's content" to ensure COPPA compliance and brand safety for advertisers.

**Key Workflow:**
1.  **Trigger**: Cloud Function triggered via HTTP (scheduled).
2.  **Input**: Downloads latest DV360 report (ZIP/CSV) from Gmail.
3.  **Processing**: Extracts channel URLs from the CSV.
4.  **Analysis**:
    *   **Keyword Matching**: Pre-filters obvious children's content (e.g., "nursery rhymes").
    *   **YouTube API**: Fetches channel metadata (subscribers, video count, recent video titles).
    *   **OpenAI GPT-4o-mini**: Analyzes metadata to categorize content (Safe vs. Children's Content).
5.  **Storage**:
    *   **Firestore**: Caches analysis results to reduce API costs.
    *   **Cloud Storage (GCS)**: Stores generated Inclusion/Exclusion CSV lists.
6.  **Output**: Emails the user with summary statistics and download links for the CSV lists.

## 2. System Architecture

```mermaid
graph TD
    Scheduler[Cloud Scheduler] -->|Trigger| Main[main.py (Cloud Function)]
    Main -->|1. Get Report| Gmail[Gmail Service]
    Main -->|2. Parse CSV| CSV[CSV Processor]
    Main -->|3. Check Cache| Firestore[Firestore Service]
    Main -->|4. Fetch Metadata| YT[YouTube Service]
    Main -->|5. Analyze Content| OpenAI[OpenAI Service]
    Main -->|6. Save Results| Firestore
    Main -->|7. Upload Lists| GCS[GCS Service]
    Main -->|8. Send Email| Gmail
```

## 3. Core Application

### `main.py`
**Purpose**: The entry point for the Google Cloud Function. Orchestrates the entire workflow.

#### Functions:
*   **`process_dv360_report(request=None)`**
    *   **Type**: Main Entry Point.
    *   **Operations**:
        1.  Initializes all services.
        2.  Orchestrates the 11-step workflow (Email -> CSV -> Analysis -> Storage -> Email).
        3.  Handles batch processing with time management (stops before timeout).
        4.  Generates cumulative Inclusion/Exclusion lists from Firestore.
    *   **Dependencies**: All service modules.

*   **`process_channel_batch_combined(batch_urls, ...)`**
    *   **Purpose**: Helper to process a small batch of channels.
    *   **Operations**: Fetches YouTube metadata -> Calls OpenAI -> Saves to Firestore immediately.

*   **`load_config()`**
    *   **Purpose**: Loads settings from `config.yaml`.

## 4. Services (`services/`)

### `services/youtube_service.py`
**Purpose**: Interacts with the YouTube Data API v3.

#### Class: `YouTubeService`
*   **`__init__(api_key, rate_limit_delay)`**: Sets up the API client.
*   **`get_channel_metadata(channel_url)`**:
    *   **Input**: Channel URL (ID, username, or handle).
    *   **Operations**: Resolves channel ID, fetches details (snippet, statistics), and fetches recent video titles via the "uploads" playlist (quota optimization).
    *   **Returns**: Dict with channel details + recent video list.
*   **`get_recent_videos_from_playlist(...)`**: Fetches video titles from the uploads playlist (costs 3 quota units vs 100 for search).
*   **`extract_channel_id_from_url(url)`**: Parses various YouTube URL formats.

### `services/openai_service.py`
**Purpose**: Uses OpenAI's GPT-4o-mini to analyze channel content.

#### Class: `OpenAIService`
*   **`categorize_channel(channel_metadata)`**:
    *   **Input**: Metadata from YouTube Service.
    *   **Operations**: Constructs a prompt with channel info + recent videos. Calls GPT-4o-mini to classify as "Children's Content" or "Safe".
    *   **Returns**: JSON object with compliance, content type, brand safety, and targeting info.
*   **`batch_categorize_channels(...)`**: Handles concurrent categorization of multiple channels.

### `services/firestore_service.py`
**Purpose**: Manages the persistent cache in Google Cloud Firestore.

#### Class: `FirestoreService`
*   **`get_cached_category(channel_url)`**: Checks if a channel has already been analyzed.
*   **`save_category(...)`**: Saves analysis results.
*   **`batch_get_cached_categories(channel_urls)`**: Efficiently retrieves multiple documents.
*   **`get_all_channels()`**: Retrieves *all* cached channels to generate the cumulative Inclusion/Exclusion lists.

### `services/gmail_service.py`
**Purpose**: Handles email operations via Gmail API.

#### Class: `GmailService`
*   **`find_latest_dv360_email(subject_filter)`**: Searches for the most recent report email.
*   **`download_zip_attachment(...)`**: Downloads the ZIP file from the email.
*   **`extract_csv_from_zip(...)`**: Unzips the report.
*   **`send_results_email(...)`**: Sends the final summary email to the user.

### `services/gcs_service.py`
**Purpose**: Interacts with Google Cloud Storage.

#### Class: `GCSService`
*   **`upload_and_get_url(...)`**: Uploads a file and generates a signed URL (valid for 7 days) for downloading.
*   **`get_signed_url(...)`**: Generates the signed URL using IAM impersonation (secure, no key file needed).

## 5. Utilities (`utils/`)

### `utils/csv_processor.py`
**Purpose**: Handles CSV parsing and generation.

#### Class: `CSVProcessor`
*   **`read_dv360_csv(csv_path)`**: Reads the raw DV360 report, handling encoding/header issues.
*   **`extract_youtube_channels(rows)`**: Parses rows to find YouTube URLs and aggregates impressions/spend.
*   **`filter_channels_by_keywords(...)`**: Checks placement names against `config.yaml` keywords (e.g., "nursery rhymes").
*   **`create_inclusion_list(...)`**: Generates the "Safe" CSV list.
*   **`create_exclusion_list(...)`**: Generates the "Block" CSV list.

## 6. Configuration Files

*   **`config.yaml`**:
    *   **keywords**: List of terms to auto-flag as children's content.
    *   **openai**: System prompts and user prompt templates.
    *   **email**: Templates for the results email.
*   **`env-vars.yaml`**: Environment variables for Cloud Function deployment (Project ID, Bucket Name, etc.).
*   **`.env`**: Local environment variables (API Keys, Credentials path) - *Never committed*.

## 7. Deployment & Scripts

*   **`deploy.sh`**: Bash script to deploy the Cloud Function using `gcloud`. Sets up environment variables and secrets.
*   **`setup_secrets.sh`**: Helper script to upload API keys and `credentials.json` to Google Secret Manager.
*   **`requirements.txt`**: Python dependencies (`google-cloud-firestore`, `openai`, `google-api-python-client`, etc.).

## 8. Test Scripts

*   **`test_local.py`**: Runs the full workflow locally using a sample CSV (`test_data.csv`).
*   **`test_simple.py`**: Tests just the YouTube -> OpenAI connection (no Firestore/Gmail).
*   **`test_enhanced_analysis.py`**: specific test for the detailed GPT-4o analysis logic.

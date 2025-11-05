"""
Main Cloud Function Handler
Orchestrates the entire DV360 YouTube channel categorization workflow
"""

import os
import logging
import tempfile
import yaml
from datetime import datetime
from dotenv import load_dotenv

# Import service modules
from services.gmail_service import GmailService
from services.youtube_service import YouTubeService
from services.firestore_service import FirestoreService
from services.openai_service import OpenAIService
from services.gcs_service import GCSService
from utils.csv_processor import CSVProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_channel_batch_combined(batch_urls, youtube_service, openai_service, firestore_service):
    """
    Process a batch of channels: Fetch YouTube metadata AND do OpenAI categorization
    Write results immediately to Firestore for natural checkpointing

    Args:
        batch_urls: List of YouTube channel URLs to process
        youtube_service: YouTubeService instance
        openai_service: OpenAIService instance
        firestore_service: FirestoreService instance

    Returns:
        list: Categorization results for this batch
    """
    results = []

    for channel_url in batch_urls:
        try:
            # 1. Fetch YouTube metadata
            metadata = youtube_service.get_channel_metadata(channel_url)

            if not metadata:
                logger.warning(f"Could not fetch metadata for: {channel_url}")
                continue

            # 2. Categorize with OpenAI
            categorization = openai_service.categorize_channel(metadata)

            # Add channel URL to result
            categorization['channel_url'] = channel_url
            categorization['channel_name'] = metadata.get('channel_name')

            results.append(categorization)

            # 3. Save immediately to Firestore (natural checkpoint)
            firestore_service.batch_save_categories([categorization])

            logger.info(f"Processed {channel_url}: {categorization.get('is_children_content')}")

        except Exception as error:
            logger.error(f"Error processing {channel_url}: {error}")
            # Continue with next channel
            continue

    return results


def load_config():
    """Load configuration from config.yaml"""
    try:
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        logger.info("Configuration loaded successfully")
        return config
    except Exception as error:
        logger.error(f"Error loading config: {error}")
        raise


def process_dv360_report(request=None):
    """
    Main Cloud Function entry point
    Processes DV360 YouTube placement reports and categorizes children's content

    Args:
        request: HTTP request object (for Cloud Functions)

    Returns:
        dict: Processing summary
    """
    start_time = datetime.now()
    logger.info("=" * 80)
    logger.info("Starting DV360 YouTube Channel Analysis")
    logger.info("=" * 80)

    try:
        # Load environment variables
        load_dotenv()

        # Load configuration
        config = load_config()
        keywords = config.get('keywords', [])

        # Initialize services
        logger.info("Initializing services...")

        gmail_service = GmailService(
            credentials_path=os.getenv('GMAIL_CREDENTIALS_PATH'),
            token_path=os.getenv('GMAIL_TOKEN_PATH')
        )
        gmail_service.authenticate()

        youtube_service = YouTubeService(
            api_key=os.getenv('YOUTUBE_API_KEY'),
            rate_limit_delay=float(os.getenv('RATE_LIMIT_DELAY', 0.1))
        )

        firestore_service = FirestoreService(
            project_id=os.getenv('GCP_PROJECT_ID'),
            collection_name=os.getenv('FIRESTORE_COLLECTION', 'channel_categories')
        )

        openai_service = OpenAIService(
            api_key=os.getenv('OPENAI_API_KEY'),
            model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
            system_prompt=config.get('openai', {}).get('system_prompt'),
            user_prompt_template=config.get('openai', {}).get('user_prompt_template')
        )

        gcs_service = GCSService(
            bucket_name=os.getenv('GCP_BUCKET_NAME')
        )

        csv_processor = CSVProcessor(keywords=keywords)

        # Step 1: Find and download latest DV360 email
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Finding latest DV360 report email")
        logger.info("=" * 80)

        message_id = gmail_service.find_latest_dv360_email(
            subject_filter=os.getenv('GMAIL_SUBJECT_FILTER'),
            days_back=7
        )

        if not message_id:
            logger.error("No DV360 report email found")
            return {'error': 'No report email found'}

        # Step 2: Download zip attachment
        logger.info("\n" + "=" * 80)
        logger.info("STEP 2: Downloading zip attachment")
        logger.info("=" * 80)

        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = gmail_service.download_zip_attachment(message_id, temp_dir)

            if not zip_path:
                logger.error("Failed to download zip attachment")
                return {'error': 'Failed to download attachment'}

            # Step 3: Extract CSV
            logger.info("\n" + "=" * 80)
            logger.info("STEP 3: Extracting CSV from zip")
            logger.info("=" * 80)

            csv_path = gmail_service.extract_csv_from_zip(zip_path, temp_dir)

            if not csv_path:
                logger.error("Failed to extract CSV")
                return {'error': 'Failed to extract CSV'}

            # Step 4: Read and process CSV
            logger.info("\n" + "=" * 80)
            logger.info("STEP 4: Reading and processing CSV data")
            logger.info("=" * 80)

            rows = csv_processor.read_dv360_csv(csv_path)
            channel_data = csv_processor.extract_youtube_channels(rows)

            # Step 5: Separate channels by keyword matching
            logger.info("\n" + "=" * 80)
            logger.info("STEP 5: Categorizing channels by keyword matching")
            logger.info("=" * 80)

            keyword_matched = {}  # Obvious children's content
            needs_analysis = {}   # Needs OpenAI analysis

            for channel_url, data in channel_data.items():
                placement_name = data.get('placement_name', '').lower()

                # Check if any keyword is in the placement name
                if any(keyword.lower() in placement_name for keyword in keywords):
                    keyword_matched[channel_url] = data
                    logger.info(f"Keyword match: {placement_name[:60]}... → Auto-flagged as children's content")
                else:
                    needs_analysis[channel_url] = data

            logger.info(f"Keyword-matched (obvious children's content): {len(keyword_matched)}")
            logger.info(f"Needs OpenAI analysis: {len(needs_analysis)}")

            # Step 6: Check Firestore cache for all channels
            logger.info("\n" + "=" * 80)
            logger.info("STEP 6: Checking Firestore cache")
            logger.info("=" * 80)

            all_channel_urls = list(channel_data.keys())
            cached_results = firestore_service.batch_get_cached_categories(all_channel_urls)

            # Process keyword-matched channels
            final_results = []
            auto_flagged_new = []

            for channel_url, data in keyword_matched.items():
                if channel_url in cached_results:
                    # Use cached result
                    cached = cached_results[channel_url]
                    final_results.append({
                        'channel_url': channel_url,
                        'channel_name': cached['channel_name'],
                        'is_children_content': cached['is_children_content'],
                        'confidence': cached['confidence'],
                        'reasoning': cached['reasoning'],
                        'impressions': data['impressions'],
                        'advertisers': data['advertisers'],
                        'insertion_orders': data['insertion_orders'],
                        'cached': True
                    })
                else:
                    # Auto-flag as children's content (keyword match)
                    auto_flagged_new.append({
                        'channel_url': channel_url,
                        'placement_name': data['placement_name'],
                        'impressions': data['impressions'],
                        'advertisers': data['advertisers'],
                        'insertion_orders': data['insertion_orders']
                    })

            # Separate channels that need OpenAI analysis
            channels_to_analyze = []
            for channel_url in needs_analysis.keys():
                if channel_url not in cached_results:
                    channels_to_analyze.append(channel_url)
                else:
                    # Use cached result
                    cached = cached_results[channel_url]
                    data = needs_analysis[channel_url]
                    final_results.append({
                        'channel_url': channel_url,
                        'channel_name': cached['channel_name'],
                        'is_children_content': cached['is_children_content'],
                        'confidence': cached['confidence'],
                        'reasoning': cached['reasoning'],
                        'impressions': data['impressions'],
                        'advertisers': data['advertisers'],
                        'insertion_orders': data['insertion_orders'],
                        'cached': True
                    })

            logger.info(f"Cache hits: {len(cached_results)}")
            logger.info(f"Auto-flagged (new keyword matches): {len(auto_flagged_new)}")
            logger.info(f"New channels needing OpenAI analysis: {len(channels_to_analyze)}")

            # Step 7: Process uncategorized channels in batches (YouTube + OpenAI combined)
            # Time-aware processing: stop at 45 minutes
            MAX_RUNTIME = 45 * 60  # 45 minutes in seconds
            BATCH_SIZE = 100
            quota_exceeded = False

            if channels_to_analyze:
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 7: Processing {len(channels_to_analyze)} uncategorized channels in batches")
                logger.info(f"Batch size: {BATCH_SIZE}, Max runtime: {MAX_RUNTIME/60} minutes")
                logger.info("=" * 80)

                # Split into batches
                batches = [channels_to_analyze[i:i+BATCH_SIZE]
                           for i in range(0, len(channels_to_analyze), BATCH_SIZE)]

                processed_results = []

                # Process batches with time awareness
                for batch_num, batch in enumerate(batches, 1):
                    # Check if we're approaching timeout
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed > MAX_RUNTIME:
                        logger.warning(f"Approaching timeout at batch {batch_num}/{len(batches)}")
                        logger.warning(f"Stopping after {elapsed/60:.1f} minutes")
                        break

                    logger.info(f"Processing batch {batch_num}/{len(batches)} ({len(batch)} channels)")

                    try:
                        batch_results = process_channel_batch_combined(
                            batch, youtube_service, openai_service, firestore_service
                        )
                        processed_results.extend(batch_results)

                    except Exception as e:
                        if 'quota' in str(e).lower():
                            logger.error(f"Quota exceeded at batch {batch_num}")
                            quota_exceeded = True
                            break
                        else:
                            logger.error(f"Error in batch {batch_num}: {e}")
                            continue

                # Add impression data and combine with final results
                for result in processed_results:
                    channel_url = result['channel_url']
                    if channel_url in needs_analysis:
                        result['impressions'] = needs_analysis[channel_url]['impressions']
                        result['advertisers'] = needs_analysis[channel_url]['advertisers']
                        result['insertion_orders'] = needs_analysis[channel_url]['insertion_orders']
                    result['cached'] = False
                    final_results.append(result)

                logger.info(f"Processed {len(processed_results)} new channels")
                logger.info(f"Total results: {len(final_results)} (cached + new)")

            # Step 8: Process auto-flagged keyword-matched channels
            # Check if we have enough time remaining (need at least 10 minutes for CSV/email)
            elapsed = (datetime.now() - start_time).total_seconds()
            time_remaining = (MAX_RUNTIME - elapsed) / 60

            if auto_flagged_new and elapsed < (MAX_RUNTIME - 5 * 60):  # Skip if less than 5 min remaining
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 8: Processing {len(auto_flagged_new)} auto-flagged channels")
                logger.info(f"Time remaining: {time_remaining:.1f} minutes")
                logger.info("=" * 80)

                firestore_auto_flagged = []
                processed_count = 0

                for auto_flag in auto_flagged_new:
                    # Check time limit every 100 channels
                    if processed_count > 0 and processed_count % 100 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        if elapsed > (MAX_RUNTIME - 5 * 60):  # Stop if less than 5 min remaining
                            logger.warning(f"Stopping auto-flagged processing after {processed_count}/{len(auto_flagged_new)} channels")
                            logger.warning(f"Time limit approaching: {elapsed/60:.1f} minutes elapsed")
                            break

                    processed_count += 1
                    channel_url = auto_flag['channel_url']

                    # Fetch basic channel name from YouTube (with quota protection)
                    try:
                        metadata = youtube_service.get_channel_metadata(channel_url)
                        channel_name = metadata['channel_name'] if metadata else auto_flag['placement_name']
                    except Exception as e:
                        if 'quota' in str(e).lower():
                            logger.warning(f"YouTube API quota exceeded while processing auto-flagged channels")
                            quota_exceeded = True
                            # Use placement name as fallback
                            channel_name = auto_flag['placement_name']
                        else:
                            logger.error(f"Error fetching metadata for auto-flagged channel: {e}")
                            channel_name = auto_flag['placement_name']

                    # Add to final results
                    final_results.append({
                        'channel_url': channel_url,
                        'channel_name': channel_name,
                        'is_children_content': True,
                        'confidence': 'high',
                        'reasoning': f"Auto-flagged based on keyword match in placement name: '{auto_flag['placement_name']}'",
                        'impressions': auto_flag['impressions'],
                        'advertisers': auto_flag['advertisers'],
                        'insertion_orders': auto_flag['insertion_orders'],
                        'cached': False
                    })

                    # Save to Firestore
                    firestore_auto_flagged.append({
                        'channel_url': channel_url,
                        'channel_name': channel_name,
                        'is_children_content': True,
                        'confidence': 'high',
                        'reasoning': f"Auto-flagged based on keyword match in placement name: '{auto_flag['placement_name']}'"
                    })

                if firestore_auto_flagged:
                    firestore_service.batch_save_categories(firestore_auto_flagged)
                    logger.info(f"✓ Saved {len(firestore_auto_flagged)} auto-flagged channels to Firestore")

            elif auto_flagged_new and elapsed >= (MAX_RUNTIME - 5 * 60):
                logger.warning(f"⚠️ Skipping Step 8 (auto-flagged channels) - insufficient time remaining")
                logger.warning(f"Elapsed: {elapsed/60:.1f} minutes, {len(auto_flagged_new)} channels will be processed in next run")

            # Step 9: Generate CSV lists (Inclusion & Exclusion)
            # IMPORTANT: Use ALL channels from Firestore (cumulative) for DV360 targeting
            logger.info("\n" + "=" * 80)
            logger.info("STEP 9: Generating CSV lists (cumulative from ALL Firestore data)")
            logger.info("=" * 80)

            date_str = datetime.now().strftime("%Y%m%d")

            # Fetch ALL channels from Firestore for cumulative lists
            all_firestore_channels = firestore_service.get_all_channels()

            # Merge current run impressions into Firestore data for channels in this CSV
            # This ensures current run's impression data is included
            for result in final_results:
                channel_url = result.get('channel_url')
                # Find matching Firestore channel and update impressions if present
                for fs_channel in all_firestore_channels:
                    if fs_channel.get('channel_url') == channel_url:
                        if 'impressions' in result:
                            fs_channel['impressions'] = result['impressions']
                        if 'advertisers' in result:
                            fs_channel['advertisers'] = result['advertisers']
                        if 'insertion_orders' in result:
                            fs_channel['insertion_orders'] = result['insertion_orders']
                        break

            # Generate inclusion list (SAFE channels - INCLUDE in campaigns)
            inclusion_list_path = os.path.join(temp_dir, f'inclusion_list_safe_channels_{date_str}.csv')
            safe_count = csv_processor.create_inclusion_list(all_firestore_channels, inclusion_list_path)

            # Generate exclusion list (children's content - EXCLUDE from campaigns)
            exclusion_list_path = os.path.join(temp_dir, f'exclusion_list_children_channels_{date_str}.csv')
            flagged_count = csv_processor.create_exclusion_list(all_firestore_channels, exclusion_list_path)

            logger.info(f"✓ Inclusion list (SAFE/INCLUDE): {safe_count} channels (cumulative)")
            logger.info(f"✓ Exclusion list (BLOCK/EXCLUDE): {flagged_count} channels (cumulative)")
            logger.info(f"✓ Current run contributed: {len(final_results)} channels")
            logger.info(f"✓ Total unique channels in Firestore: {len(all_firestore_channels)}")

            # Step 10: Upload CSVs to Cloud Storage
            logger.info("\n" + "=" * 80)
            logger.info("STEP 10: Uploading CSVs to Cloud Storage")
            logger.info("=" * 80)

            # Upload inclusion list to both dated archive and latest location
            # Archive copy with date
            inclusion_archive_blob = f'dv360-reports/archive/{date_str}/inclusion_list_safe_channels_{date_str}.csv'
            gcs_service.upload_file(inclusion_list_path, inclusion_archive_blob)
            logger.info(f"✓ Archived inclusion list to: gs://{gcs_service.bucket_name}/{inclusion_archive_blob}")

            # Latest copy with fixed name and signed URL (max 7 days)
            inclusion_blob_name = 'dv360-reports/latest/inclusion_list_safe_channels.csv'
            inclusion_gcs_uri, inclusion_url = gcs_service.upload_and_get_url(
                inclusion_list_path,
                inclusion_blob_name,
                expiration_hours=168  # 7 days (GCS maximum)
            )
            logger.info(f"✓ Uploaded inclusion list to: {inclusion_gcs_uri}")

            # Upload exclusion list to both dated archive and latest location
            # Archive copy with date
            exclusion_archive_blob = f'dv360-reports/archive/{date_str}/exclusion_list_children_channels_{date_str}.csv'
            gcs_service.upload_file(exclusion_list_path, exclusion_archive_blob)
            logger.info(f"✓ Archived exclusion list to: gs://{gcs_service.bucket_name}/{exclusion_archive_blob}")

            # Latest copy with fixed name and signed URL (max 7 days)
            exclusion_blob_name = 'dv360-reports/latest/exclusion_list_children_channels.csv'
            exclusion_gcs_uri, exclusion_url = gcs_service.upload_and_get_url(
                exclusion_list_path,
                exclusion_blob_name,
                expiration_hours=168  # 7 days (GCS maximum)
            )
            logger.info(f"✓ Uploaded exclusion list to: {exclusion_gcs_uri}")

            # Step 11: Send results email with download links
            logger.info("\n" + "=" * 80)
            logger.info("STEP 11: Sending results email with download links")
            logger.info("=" * 80)

            processing_time = (datetime.now() - start_time).total_seconds()

            # Add partial results warning if quota was exceeded
            partial_warning = ""
            if quota_exceeded:
                unprocessed_count = len(channels_to_analyze) - len([r for r in final_results if not r.get('cached')])
                partial_warning = f"<div style='background-color: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin: 15px 0;'><strong>⚠️ Partial Results:</strong> API quota exceeded (YouTube or OpenAI). {unprocessed_count} channels were not processed and will be analyzed in the next run. Only successfully analyzed channels are included in the lists below.</div>"

            email_subject_template = config.get('email', {}).get('subject', 'DV360 Children\'s Channel Analysis Results')
            if quota_exceeded:
                email_subject_template += " [PARTIAL]"

            email_subject = email_subject_template.format(
                date=datetime.now().strftime('%Y-%m-%d')
            )

            email_body = config.get('email', {}).get('body_template', '').format(
                total_channels=len(channel_data),
                flagged_count=flagged_count,
                safe_count=safe_count,
                cache_hits=len(cached_results),
                api_calls=len(channels_to_analyze) + len(auto_flagged_new),
                processing_time=f"{processing_time:.2f} seconds",
                date=date_str,
                inclusion_url=inclusion_url,
                exclusion_url=exclusion_url,
                partial_warning=partial_warning
            )

            # Send email with graceful degradation (data already saved to Firestore & GCS)
            try:
                gmail_service.send_results_email(
                    recipient_email=os.getenv('RECIPIENT_EMAIL'),
                    subject=email_subject,
                    body=email_body
                )
            except Exception as email_error:
                logger.error(f"Failed to send results email: {email_error}")
                logger.warning("Email delivery failed, but all results are saved to Firestore and Cloud Storage")
                logger.warning(f"Inclusion list: {inclusion_url}")
                logger.warning(f"Exclusion list: {exclusion_url}")

            # Final summary
            logger.info("\n" + "=" * 80)
            logger.info("PROCESSING COMPLETE - SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total rows processed: {csv_processor.total_rows}")
            logger.info(f"Unique channels found: {len(channel_data)}")
            logger.info(f"Keyword-matched (auto-flagged): {len(keyword_matched)}")
            logger.info(f"Needed OpenAI analysis: {len(needs_analysis)}")
            logger.info(f"Cache hits: {len(cached_results)}")
            logger.info(f"New OpenAI analyses: {len(channels_to_analyze)}")
            logger.info(f"New auto-flagged: {len(auto_flagged_new)}")
            logger.info(f"Channels flagged as children's content: {flagged_count}")
            logger.info(f"YouTube API calls: {youtube_service.api_calls_made}")
            logger.info(f"OpenAI API calls: {openai_service.api_calls_made}")
            logger.info(f"Processing time: {processing_time:.2f} seconds")
            logger.info("=" * 80)

            summary = {
                'status': 'success',
                'total_rows': csv_processor.total_rows,
                'unique_channels': len(channel_data),
                'keyword_matched': len(keyword_matched),
                'needs_analysis': len(needs_analysis),
                'cache_hits': len(cached_results),
                'new_openai_analyses': len(channels_to_analyze),
                'new_auto_flagged': len(auto_flagged_new),
                'flagged_count': flagged_count,
                'youtube_api_calls': youtube_service.api_calls_made,
                'openai_api_calls': openai_service.api_calls_made,
                'processing_time_seconds': round(processing_time, 2)
            }

            return summary

    except Exception as error:
        logger.error(f"Critical error in main workflow: {error}", exc_info=True)
        return {
            'status': 'error',
            'error': str(error)
        }


# For local testing
if __name__ == '__main__':
    result = process_dv360_report()
    print("\nFinal Result:")
    print(result)

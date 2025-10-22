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

            # Step 7: Fetch YouTube metadata for new channels
            quota_exceeded = False
            if channels_to_analyze:
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 7: Fetching YouTube metadata for {len(channels_to_analyze)} new channels")
                logger.info("=" * 80)

                channels_metadata = []

                for i, channel_url in enumerate(channels_to_analyze):
                    logger.info(f"Fetching metadata {i + 1}/{len(channels_to_analyze)}: {channel_url}")

                    try:
                        metadata = youtube_service.get_channel_metadata(channel_url)

                        if metadata:
                            channels_metadata.append(metadata)
                        else:
                            logger.warning(f"Could not fetch metadata for: {channel_url}")
                    except Exception as e:
                        # Check if it's a quota error
                        if 'quota' in str(e).lower():
                            logger.warning(f"YouTube API quota exceeded after processing {i} channels")
                            logger.info(f"Successfully fetched metadata for {len(channels_metadata)} channels before quota limit")
                            quota_exceeded = True
                            break
                        else:
                            logger.error(f"Error fetching metadata for {channel_url}: {e}")
                            continue

                # Step 8: Categorize channels with OpenAI
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 8: Categorizing {len(channels_metadata)} channels with OpenAI")
                logger.info("=" * 80)

                try:
                    categorization_results = openai_service.batch_categorize_channels(channels_metadata)
                except Exception as e:
                    # Check if it's a quota error
                    if 'quota' in str(e).lower() or 'billing' in str(e).lower():
                        logger.warning(f"OpenAI quota exceeded during categorization")
                        logger.info(f"Successfully categorized {len([r for r in final_results if not r.get('cached')])} channels before quota limit")
                        quota_exceeded = True
                        categorization_results = []  # Empty results, won't save bad data
                    else:
                        raise

                # Step 9: Save results to Firestore
                logger.info("\n" + "=" * 80)
                logger.info("STEP 9: Saving categorization results to Firestore")
                logger.info("=" * 80)

                firestore_save_data = []

                for result in categorization_results:
                    channel_url = result['channel_url']

                    # Add impression data
                    if channel_url in needs_analysis:
                        result['impressions'] = needs_analysis[channel_url]['impressions']
                        result['advertisers'] = needs_analysis[channel_url]['advertisers']
                        result['insertion_orders'] = needs_analysis[channel_url]['insertion_orders']

                    result['cached'] = False
                    final_results.append(result)

                    # Prepare for Firestore batch save
                    firestore_save_data.append({
                        'channel_url': result['channel_url'],
                        'channel_name': result['channel_name'],
                        'is_children_content': result['is_children_content'],
                        'confidence': result['confidence'],
                        'reasoning': result['reasoning']
                    })

                if firestore_save_data:
                    firestore_service.batch_save_categories(firestore_save_data)

            # Step 9.5: Process auto-flagged keyword-matched channels
            if auto_flagged_new:
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 9.5: Processing {len(auto_flagged_new)} auto-flagged channels")
                logger.info("=" * 80)

                firestore_auto_flagged = []

                for auto_flag in auto_flagged_new:
                    channel_url = auto_flag['channel_url']

                    # Fetch basic channel name from YouTube
                    metadata = youtube_service.get_channel_metadata(channel_url)

                    channel_name = metadata['channel_name'] if metadata else auto_flag['placement_name']

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

            # Step 10: Generate CSV lists (Inclusion & Exclusion)
            logger.info("\n" + "=" * 80)
            logger.info("STEP 10: Generating CSV lists")
            logger.info("=" * 80)

            date_str = datetime.now().strftime("%Y%m%d")

            # Generate inclusion list (SAFE channels - INCLUDE in campaigns)
            inclusion_list_path = os.path.join(temp_dir, f'inclusion_list_safe_channels_{date_str}.csv')
            safe_count = csv_processor.create_inclusion_list(final_results, inclusion_list_path)

            # Generate exclusion list (children's content - EXCLUDE from campaigns)
            exclusion_list_path = os.path.join(temp_dir, f'exclusion_list_children_channels_{date_str}.csv')
            flagged_count = csv_processor.create_exclusion_list(final_results, exclusion_list_path)

            logger.info(f"✓ Inclusion list (SAFE/INCLUDE): {safe_count} channels")
            logger.info(f"✓ Exclusion list (BLOCK/EXCLUDE): {flagged_count} channels")

            # Step 11: Upload CSVs to Cloud Storage
            logger.info("\n" + "=" * 80)
            logger.info("STEP 11: Uploading CSVs to Cloud Storage")
            logger.info("=" * 80)

            # Upload inclusion list to both dated archive and latest location
            # Archive copy with date
            inclusion_archive_blob = f'dv360-reports/archive/{date_str}/inclusion_list_safe_channels_{date_str}.csv'
            gcs_service.upload_file(inclusion_list_path, inclusion_archive_blob)
            logger.info(f"✓ Archived inclusion list to: gs://{gcs_service.bucket_name}/{inclusion_archive_blob}")

            # Latest copy with fixed name and long-lived signed URL
            inclusion_blob_name = 'dv360-reports/latest/inclusion_list_safe_channels.csv'
            inclusion_gcs_uri, inclusion_url = gcs_service.upload_and_get_url(
                inclusion_list_path,
                inclusion_blob_name,
                expiration_hours=720  # 30 days
            )
            logger.info(f"✓ Uploaded inclusion list to: {inclusion_gcs_uri}")

            # Upload exclusion list to both dated archive and latest location
            # Archive copy with date
            exclusion_archive_blob = f'dv360-reports/archive/{date_str}/exclusion_list_children_channels_{date_str}.csv'
            gcs_service.upload_file(exclusion_list_path, exclusion_archive_blob)
            logger.info(f"✓ Archived exclusion list to: gs://{gcs_service.bucket_name}/{exclusion_archive_blob}")

            # Latest copy with fixed name and long-lived signed URL
            exclusion_blob_name = 'dv360-reports/latest/exclusion_list_children_channels.csv'
            exclusion_gcs_uri, exclusion_url = gcs_service.upload_and_get_url(
                exclusion_list_path,
                exclusion_blob_name,
                expiration_hours=720  # 30 days
            )
            logger.info(f"✓ Uploaded exclusion list to: {exclusion_gcs_uri}")

            # Step 12: Send results email with download links
            logger.info("\n" + "=" * 80)
            logger.info("STEP 12: Sending results email with download links")
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

            gmail_service.send_results_email(
                recipient_email=os.getenv('RECIPIENT_EMAIL'),
                subject=email_subject,
                body=email_body
            )

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

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

        csv_processor = CSVProcessor(keywords=keywords)

        # Step 1: Find and download latest DV360 email
        logger.info("\n" + "=" * 80)
        logger.info("STEP 1: Finding latest DV360 report email")
        logger.info("=" * 80)

        message_id = gmail_service.find_latest_dv360_email(
            sender_email=os.getenv('GMAIL_SENDER_EMAIL'),
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

            # Step 5: Pre-filter channels by keywords
            logger.info("\n" + "=" * 80)
            logger.info("STEP 5: Pre-filtering channels by keywords")
            logger.info("=" * 80)

            filtered_channels = csv_processor.filter_channels_by_keywords(channel_data)

            if not filtered_channels:
                logger.warning("No channels matched keyword filters")
                return {'warning': 'No channels matched filters'}

            # Step 6: Check Firestore cache
            logger.info("\n" + "=" * 80)
            logger.info("STEP 6: Checking Firestore cache for known channels")
            logger.info("=" * 80)

            channel_urls = list(filtered_channels.keys())
            cached_results = firestore_service.batch_get_cached_categories(channel_urls)

            # Separate cached vs new channels
            channels_to_analyze = []
            final_results = []

            for channel_url, data in filtered_channels.items():
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
                    channels_to_analyze.append(channel_url)

            logger.info(f"Cache hits: {len(cached_results)}, New channels to analyze: {len(channels_to_analyze)}")

            # Step 7: Fetch YouTube metadata for new channels
            if channels_to_analyze:
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 7: Fetching YouTube metadata for {len(channels_to_analyze)} new channels")
                logger.info("=" * 80)

                channels_metadata = []

                for i, channel_url in enumerate(channels_to_analyze):
                    logger.info(f"Fetching metadata {i + 1}/{len(channels_to_analyze)}: {channel_url}")

                    metadata = youtube_service.get_channel_metadata(channel_url)

                    if metadata:
                        channels_metadata.append(metadata)
                    else:
                        logger.warning(f"Could not fetch metadata for: {channel_url}")

                # Step 8: Categorize channels with OpenAI
                logger.info("\n" + "=" * 80)
                logger.info(f"STEP 8: Categorizing {len(channels_metadata)} channels with OpenAI")
                logger.info("=" * 80)

                categorization_results = openai_service.batch_categorize_channels(channels_metadata)

                # Step 9: Save results to Firestore
                logger.info("\n" + "=" * 80)
                logger.info("STEP 9: Saving categorization results to Firestore")
                logger.info("=" * 80)

                firestore_save_data = []

                for result in categorization_results:
                    channel_url = result['channel_url']

                    # Add impression data
                    if channel_url in filtered_channels:
                        result['impressions'] = filtered_channels[channel_url]['impressions']
                        result['advertisers'] = filtered_channels[channel_url]['advertisers']
                        result['insertion_orders'] = filtered_channels[channel_url]['insertion_orders']

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

            # Step 10: Generate results CSV
            logger.info("\n" + "=" * 80)
            logger.info("STEP 10: Generating results CSV")
            logger.info("=" * 80)

            results_csv_path = os.path.join(temp_dir, f'children_channels_{datetime.now().strftime("%Y%m%d")}.csv')
            csv_processor.create_results_csv(final_results, results_csv_path)

            flagged_count = sum(1 for r in final_results if r.get('is_children_content'))

            # Step 11: Send results email
            logger.info("\n" + "=" * 80)
            logger.info("STEP 11: Sending results email")
            logger.info("=" * 80)

            processing_time = (datetime.now() - start_time).total_seconds()

            email_subject = config.get('email', {}).get('subject', 'DV360 Children\'s Channel Analysis Results').format(
                date=datetime.now().strftime('%Y-%m-%d')
            )

            email_body = config.get('email', {}).get('body_template', '').format(
                total_channels=len(filtered_channels),
                flagged_count=flagged_count,
                cache_hits=len(cached_results),
                api_calls=len(channels_to_analyze),
                processing_time=f"{processing_time:.2f} seconds"
            )

            gmail_service.send_results_email(
                recipient_email=os.getenv('RECIPIENT_EMAIL'),
                subject=email_subject,
                body=email_body,
                attachment_path=results_csv_path
            )

            # Final summary
            logger.info("\n" + "=" * 80)
            logger.info("PROCESSING COMPLETE - SUMMARY")
            logger.info("=" * 80)
            logger.info(f"Total rows processed: {csv_processor.total_rows}")
            logger.info(f"Unique channels found: {len(channel_data)}")
            logger.info(f"Channels after keyword filter: {len(filtered_channels)}")
            logger.info(f"Cache hits: {len(cached_results)}")
            logger.info(f"New channels analyzed: {len(channels_to_analyze)}")
            logger.info(f"Channels flagged as children's content: {flagged_count}")
            logger.info(f"YouTube API calls: {youtube_service.api_calls_made}")
            logger.info(f"OpenAI API calls: {openai_service.api_calls_made}")
            logger.info(f"Processing time: {processing_time:.2f} seconds")
            logger.info("=" * 80)

            summary = {
                'status': 'success',
                'total_rows': csv_processor.total_rows,
                'unique_channels': len(channel_data),
                'filtered_channels': len(filtered_channels),
                'cache_hits': len(cached_results),
                'new_channels_analyzed': len(channels_to_analyze),
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

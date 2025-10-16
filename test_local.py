"""
Local test script for DV360 YouTube Channel Analyzer
Tests with 2 sample rows
"""

import os
import logging
from dotenv import load_dotenv

# Import service modules
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

def test_local():
    """Test the system locally with test CSV"""

    logger.info("=" * 80)
    logger.info("LOCAL TEST - DV360 YouTube Channel Analyzer")
    logger.info("=" * 80)

    # Load environment variables
    load_dotenv()

    # Load keywords
    import yaml
    with open('config.yaml', 'r') as f:
        config = yaml.safe_load(f)
    keywords = config.get('keywords', [])

    logger.info(f"\nKeywords for pre-filtering: {keywords}")

    # Initialize services
    logger.info("\n" + "=" * 80)
    logger.info("STEP 1: Initializing services...")
    logger.info("=" * 80)

    youtube_service = YouTubeService(
        api_key=os.getenv('YOUTUBE_API_KEY'),
        rate_limit_delay=0.1
    )

    firestore_service = FirestoreService(
        project_id=os.getenv('GCP_PROJECT_ID'),
        collection_name=os.getenv('FIRESTORE_COLLECTION', 'channel_categories')
    )

    openai_service = OpenAIService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    )

    csv_processor = CSVProcessor(keywords=keywords)

    # Read test CSV
    logger.info("\n" + "=" * 80)
    logger.info("STEP 2: Reading test CSV...")
    logger.info("=" * 80)

    rows = csv_processor.read_dv360_csv('test_data.csv')
    logger.info(f"Read {len(rows)} test rows")

    # Extract channels
    logger.info("\n" + "=" * 80)
    logger.info("STEP 3: Extracting YouTube channels...")
    logger.info("=" * 80)

    channel_data = csv_processor.extract_youtube_channels(rows)
    logger.info(f"Found {len(channel_data)} unique channels")

    for url, data in channel_data.items():
        logger.info(f"  - {url}")
        logger.info(f"    Placement: {data['placement_name']}")
        logger.info(f"    Impressions: {data['impressions']:,}")

    # Pre-filter by keywords
    logger.info("\n" + "=" * 80)
    logger.info("STEP 4: Pre-filtering by keywords...")
    logger.info("=" * 80)

    filtered_channels = csv_processor.filter_channels_by_keywords(channel_data)
    logger.info(f"After keyword filter: {len(filtered_channels)} channels")

    # Check Firestore cache
    logger.info("\n" + "=" * 80)
    logger.info("STEP 5: Checking Firestore cache...")
    logger.info("=" * 80)

    channel_urls = list(filtered_channels.keys())
    cached_results = firestore_service.batch_get_cached_categories(channel_urls)
    logger.info(f"Cache hits: {len(cached_results)}, Cache misses: {len(channel_urls) - len(cached_results)}")

    # Identify new channels
    channels_to_analyze = [url for url in channel_urls if url not in cached_results]
    logger.info(f"New channels to analyze: {len(channels_to_analyze)}")

    final_results = []

    # Add cached results
    for channel_url, cached in cached_results.items():
        final_results.append({
            'channel_url': channel_url,
            'channel_name': cached['channel_name'],
            'is_children_content': cached['is_children_content'],
            'confidence': cached['confidence'],
            'reasoning': cached['reasoning'],
            'impressions': filtered_channels[channel_url]['impressions'],
            'cached': True
        })

    # Analyze new channels
    if channels_to_analyze:
        logger.info("\n" + "=" * 80)
        logger.info(f"STEP 6: Fetching YouTube metadata for {len(channels_to_analyze)} channels...")
        logger.info("=" * 80)

        channels_metadata = []
        for i, channel_url in enumerate(channels_to_analyze):
            logger.info(f"\nFetching metadata {i + 1}/{len(channels_to_analyze)}: {channel_url}")
            metadata = youtube_service.get_channel_metadata(channel_url)

            if metadata:
                logger.info(f"  ✓ Channel: {metadata['channel_name']}")
                logger.info(f"    Subscribers: {metadata['subscriber_count']}")
                logger.info(f"    Videos: {metadata['video_count']}")
                logger.info(f"    Description: {metadata['description'][:100]}...")
                channels_metadata.append(metadata)
            else:
                logger.warning(f"  ✗ Could not fetch metadata")

        # Categorize with OpenAI
        logger.info("\n" + "=" * 80)
        logger.info(f"STEP 7: Categorizing {len(channels_metadata)} channels with OpenAI...")
        logger.info("=" * 80)

        categorization_results = openai_service.batch_categorize_channels(channels_metadata, rate_limit_delay=1.0)

        # Save to Firestore
        logger.info("\n" + "=" * 80)
        logger.info("STEP 8: Saving results to Firestore...")
        logger.info("=" * 80)

        firestore_save_data = []
        for result in categorization_results:
            channel_url = result['channel_url']

            # Add to final results
            if channel_url in filtered_channels:
                result['impressions'] = filtered_channels[channel_url]['impressions']
                result['cached'] = False
                final_results.append(result)

            # Prepare for Firestore
            firestore_save_data.append({
                'channel_url': result['channel_url'],
                'channel_name': result['channel_name'],
                'is_children_content': result['is_children_content'],
                'confidence': result['confidence'],
                'reasoning': result['reasoning']
            })

        if firestore_save_data:
            firestore_service.batch_save_categories(firestore_save_data)
            logger.info(f"✓ Saved {len(firestore_save_data)} results to Firestore")

    # Display final results
    logger.info("\n" + "=" * 80)
    logger.info("FINAL RESULTS")
    logger.info("=" * 80)

    for i, result in enumerate(final_results, 1):
        logger.info(f"\n{i}. {result['channel_name']}")
        logger.info(f"   URL: {result['channel_url']}")
        logger.info(f"   Children's Content: {result['is_children_content']}")
        logger.info(f"   Confidence: {result['confidence']}")
        logger.info(f"   Reasoning: {result['reasoning']}")
        logger.info(f"   Impressions: {result['impressions']:,}")
        logger.info(f"   Source: {'Cache' if result.get('cached') else 'New Analysis'}")

    # Statistics
    logger.info("\n" + "=" * 80)
    logger.info("STATISTICS")
    logger.info("=" * 80)
    logger.info(f"Total channels analyzed: {len(final_results)}")
    logger.info(f"Flagged as children's content: {sum(1 for r in final_results if r['is_children_content'])}")
    logger.info(f"Cache hits: {len(cached_results)}")
    logger.info(f"New API calls: {len(channels_to_analyze)}")
    logger.info(f"YouTube API calls: {youtube_service.api_calls_made}")
    logger.info(f"OpenAI API calls: {openai_service.api_calls_made}")

    logger.info("\n" + "=" * 80)
    logger.info("TEST COMPLETE!")
    logger.info("=" * 80)


if __name__ == '__main__':
    test_local()

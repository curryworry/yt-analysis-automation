"""
Simple local test - YouTube + OpenAI only (no Firestore)
Tests with 2 sample channels
"""

import os
import logging
from dotenv import load_dotenv

# Import service modules
from services.youtube_service import YouTubeService
from services.openai_service import OpenAIService
from utils.csv_processor import CSVProcessor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_simple():
    """Test YouTube + OpenAI integration"""

    logger.info("=" * 80)
    logger.info("SIMPLE LOCAL TEST - YouTube + OpenAI")
    logger.info("=" * 80)

    # Load environment variables
    load_dotenv()

    # Initialize services (no Firestore for local test)
    logger.info("\nInitializing services...")

    youtube_service = YouTubeService(
        api_key=os.getenv('YOUTUBE_API_KEY'),
        rate_limit_delay=0.1
    )

    openai_service = OpenAIService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model='gpt-4o-mini'
    )

    csv_processor = CSVProcessor(keywords=['baby', 'nursery', 'kids'])

    # Read test CSV
    logger.info("\n" + "=" * 80)
    logger.info("Reading test CSV...")
    logger.info("=" * 80)

    rows = csv_processor.read_dv360_csv('test_data.csv')
    logger.info(f"✓ Read {len(rows)} test rows")

    # Extract channels
    logger.info("\n" + "=" * 80)
    logger.info("Extracting YouTube channels...")
    logger.info("=" * 80)

    channel_data = csv_processor.extract_youtube_channels(rows)
    logger.info(f"✓ Found {len(channel_data)} unique channels\n")

    for url, data in channel_data.items():
        logger.info(f"  Channel: {url}")
        logger.info(f"  Placement: {data['placement_name']}")
        logger.info(f"  Impressions: {data['impressions']:,}\n")

    # Pre-filter by keywords
    filtered_channels = csv_processor.filter_channels_by_keywords(channel_data)
    logger.info(f"✓ After keyword filter: {len(filtered_channels)} channels")

    # Fetch YouTube metadata
    logger.info("\n" + "=" * 80)
    logger.info("Fetching YouTube metadata...")
    logger.info("=" * 80)

    channels_metadata = []
    for i, channel_url in enumerate(filtered_channels.keys(), 1):
        logger.info(f"\n[{i}/{len(filtered_channels)}] Fetching: {channel_url}")
        metadata = youtube_service.get_channel_metadata(channel_url)

        if metadata:
            logger.info(f"  ✓ Channel: {metadata['channel_name']}")
            logger.info(f"    Subscribers: {int(metadata['subscriber_count']):,}")
            logger.info(f"    Videos: {metadata['video_count']}")
            logger.info(f"    Description: {metadata['description'][:80]}...")
            channels_metadata.append(metadata)
        else:
            logger.warning(f"  ✗ Could not fetch metadata")

    # Categorize with OpenAI (REST API)
    logger.info("\n" + "=" * 80)
    logger.info("Categorizing with OpenAI (REST API)...")
    logger.info("=" * 80)

    results = []
    for i, metadata in enumerate(channels_metadata, 1):
        logger.info(f"\n[{i}/{len(channels_metadata)}] Analyzing: {metadata['channel_name']}")

        result = openai_service.categorize_channel(metadata)

        results.append({
            'channel_url': metadata['channel_url'],
            'channel_name': metadata['channel_name'],
            **result
        })

        logger.info(f"  ✓ Children's Content: {result['is_children_content']}")
        logger.info(f"    Confidence: {result['confidence']}")
        logger.info(f"    Reasoning: {result['reasoning']}")

    # Final summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST RESULTS")
    logger.info("=" * 80)

    for i, result in enumerate(results, 1):
        logger.info(f"\n{i}. {result['channel_name']}")
        logger.info(f"   URL: {result['channel_url']}")
        logger.info(f"   Children's Content: {'YES' if result['is_children_content'] else 'NO'}")
        logger.info(f"   Confidence: {result['confidence'].upper()}")
        logger.info(f"   Reasoning: {result['reasoning']}")

    # Statistics
    logger.info("\n" + "=" * 80)
    logger.info("STATISTICS")
    logger.info("=" * 80)
    logger.info(f"Total channels analyzed: {len(results)}")
    logger.info(f"Flagged as children's content: {sum(1 for r in results if r['is_children_content'])}")
    logger.info(f"YouTube API calls: {youtube_service.api_calls_made}")
    logger.info(f"OpenAI API calls: {openai_service.api_calls_made}")

    logger.info("\n" + "=" * 80)
    logger.info("✓ TEST COMPLETE - REST API WORKING!")
    logger.info("=" * 80)

    return results


if __name__ == '__main__':
    test_simple()

"""
Test script for enhanced channel analysis with video data
Tests the new features:
- Efficient video fetching using playlistItems
- Enhanced OpenAI analysis (content vertical, brand safety, etc.)
- Quota usage tracking
"""

import os
import logging
import yaml
from dotenv import load_dotenv

from services.youtube_service import YouTubeService
from services.openai_service import OpenAIService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_config():
    """Load configuration from config.yaml"""
    with open('config.yaml', 'r') as f:
        return yaml.safe_load(f)

def test_channel_analysis(channel_url):
    """
    Test enhanced analysis on a single channel

    Args:
        channel_url: YouTube channel URL to test
    """
    # Load environment variables
    load_dotenv()

    # Load configuration
    config = load_config()

    logger.info("=" * 80)
    logger.info(f"Testing Enhanced Analysis on: {channel_url}")
    logger.info("=" * 80)

    # Initialize services
    youtube_service = YouTubeService(
        api_key=os.getenv('YOUTUBE_API_KEY'),
        rate_limit_delay=0.1
    )

    openai_service = OpenAIService(
        api_key=os.getenv('OPENAI_API_KEY'),
        model=os.getenv('OPENAI_MODEL', 'gpt-4o-mini'),
        system_prompt=config.get('openai', {}).get('system_prompt'),
        user_prompt_template=config.get('openai', {}).get('user_prompt_template')
    )

    # Step 1: Fetch YouTube metadata with recent videos
    logger.info("\nStep 1: Fetching YouTube metadata...")
    metadata = youtube_service.get_channel_metadata(channel_url)

    if not metadata:
        logger.error("Failed to fetch channel metadata")
        return

    logger.info(f"✓ Channel: {metadata['channel_name']}")
    logger.info(f"✓ Subscribers: {metadata['subscriber_count']}")
    logger.info(f"✓ Videos: {metadata['video_count']}")
    logger.info(f"✓ Country: {metadata.get('country', 'N/A')}")

    # Display recent videos
    recent_videos = metadata.get('recent_videos', [])
    logger.info(f"\n✓ Fetched {len(recent_videos)} recent videos:")
    for i, video in enumerate(recent_videos[:3], 1):
        logger.info(f"  {i}. {video['title'][:60]}...")

    # Step 2: Analyze with OpenAI
    logger.info("\nStep 2: Analyzing with OpenAI...")
    result = openai_service.categorize_channel(metadata)

    # Step 3: Display results
    logger.info("\n" + "=" * 80)
    logger.info("ANALYSIS RESULTS")
    logger.info("=" * 80)

    logger.info(f"\n📋 COMPLIANCE:")
    logger.info(f"  Children's Content: {result['is_children_content']}")
    logger.info(f"  Confidence: {result['confidence']}")
    logger.info(f"  Reasoning: {result['reasoning']}")

    logger.info(f"\n📊 CONTENT CLASSIFICATION:")
    logger.info(f"  Primary Vertical: {result.get('content_vertical', 'N/A')}")
    logger.info(f"  Sub-Niche: {result.get('content_niche', 'N/A')}")
    logger.info(f"  Format: {result.get('content_format', 'N/A')}")
    logger.info(f"  Confidence: {result.get('content_confidence', 'N/A')}")

    logger.info(f"\n🛡️  BRAND SAFETY:")
    logger.info(f"  Overall Score: {result.get('brand_safety_score', 'N/A')}")
    logger.info(f"  Controversial Topics: {result.get('controversial_topics', 'N/A')}")
    logger.info(f"  Premium Suitable: {result.get('premium_suitable', 'N/A')}")
    flags = result.get('safety_flags', [])
    if flags:
        logger.info(f"  Flags: {', '.join(flags)}")
    else:
        logger.info(f"  Flags: None")

    logger.info(f"\n🎯 TARGETING SIGNALS:")
    logger.info(f"  Geographic Focus: {result.get('geographic_focus', 'N/A')}")
    logger.info(f"  Primary Language: {result.get('primary_language', 'N/A')}")
    logger.info(f"  Purchase Intent: {result.get('purchase_intent', 'N/A')}")

    logger.info(f"\n📝 SUMMARY:")
    logger.info(f"  {result.get('summary', 'N/A')}")

    # Step 4: Display quota usage
    logger.info("\n" + "=" * 80)
    logger.info("QUOTA USAGE")
    logger.info("=" * 80)
    logger.info(f"YouTube API calls: {youtube_service.api_calls_made}")
    logger.info(f"OpenAI API calls: {openai_service.api_calls_made}")
    logger.info(f"Estimated OpenAI cost: ${openai_service.api_calls_made * 0.0003:.4f}")

    return result

if __name__ == '__main__':
    # Test channels
    test_channels = [
        # Tech review channel (should be safe, high purchase intent)
        "https://www.youtube.com/channel/UCBJycsmduvYEL83R_U4JriQ",  # MKBHD

        # Kids channel (should be flagged as children's content)
        # "https://www.youtube.com/channel/UCbCmjCuTUZos6Inko4u57UQ",  # Cocomelon
    ]

    for channel_url in test_channels:
        try:
            test_channel_analysis(channel_url)
            print("\n" + "=" * 80 + "\n")
        except Exception as e:
            logger.error(f"Error testing channel {channel_url}: {e}", exc_info=True)

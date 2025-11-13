#!/usr/bin/env python3
"""
Test script to verify CSV processing optimizations:
1. Channels are sorted by impressions (descending)
2. "Unknown" placement names are skipped
"""

import sys
from utils.csv_processor import CSVProcessor

def test_sorting_and_unknown_filtering():
    """Test that channels are sorted and Unknown channels are filtered"""

    # Create test CSV data
    test_rows = [
        {
            'Placement (All YouTube Channels)': 'https://www.youtube.com/channel/UCtest1',
            'Placement Name (All YouTube Channels)': 'Test Channel 1',
            'Impressions': '1000',
            'Advertiser': 'Test Advertiser',
            'Insertion Order': 'Test IO'
        },
        {
            'Placement (All YouTube Channels)': 'https://www.youtube.com/channel/UCtest2',
            'Placement Name (All YouTube Channels)': 'Unknown',  # Should be filtered out
            'Impressions': '5000',
            'Advertiser': 'Test Advertiser',
            'Insertion Order': 'Test IO'
        },
        {
            'Placement (All YouTube Channels)': 'https://www.youtube.com/channel/UCtest3',
            'Placement Name (All YouTube Channels)': 'Test Channel 3',
            'Impressions': '10000',  # Highest impressions - should be first
            'Advertiser': 'Test Advertiser',
            'Insertion Order': 'Test IO'
        },
        {
            'Placement (All YouTube Channels)': 'https://www.youtube.com/channel/UCtest4',
            'Placement Name (All YouTube Channels)': 'Test Channel 4',
            'Impressions': '500',  # Lowest impressions - should be last
            'Advertiser': 'Test Advertiser',
            'Insertion Order': 'Test IO'
        },
        {
            'Placement (All YouTube Channels)': 'https://www.youtube.com/channel/UCtest5',
            'Placement Name (All YouTube Channels)': 'unknown',  # Should be filtered out (lowercase)
            'Impressions': '3000',
            'Advertiser': 'Test Advertiser',
            'Insertion Order': 'Test IO'
        }
    ]

    # Process the test data
    processor = CSVProcessor(keywords=['test'])
    channel_data = processor.extract_youtube_channels(test_rows)

    print("\n" + "="*80)
    print("TEST RESULTS")
    print("="*80)

    # Check that Unknown channels were filtered out
    channel_urls = list(channel_data.keys())
    print(f"\n✓ Total channels extracted: {len(channel_urls)}")
    print(f"  Expected: 3 (filtered out 2 'Unknown' channels)")

    if len(channel_urls) != 3:
        print(f"  ❌ FAILED: Expected 3 channels, got {len(channel_urls)}")
        return False

    # Check that channels are sorted by impressions (descending)
    impressions_list = [channel_data[url]['impressions'] for url in channel_urls]
    print(f"\n✓ Impression order: {impressions_list}")
    print(f"  Expected: [10000, 1000, 500] (descending)")

    if impressions_list != [10000, 1000, 500]:
        print(f"  ❌ FAILED: Channels not sorted correctly")
        return False

    # Verify specific channels
    first_channel_url = channel_urls[0]
    last_channel_url = channel_urls[2]

    print(f"\n✓ First channel (highest impressions):")
    print(f"  URL: {first_channel_url}")
    print(f"  Name: {channel_data[first_channel_url]['placement_name']}")
    print(f"  Impressions: {channel_data[first_channel_url]['impressions']:,}")

    if 'UCtest3' not in first_channel_url:
        print(f"  ❌ FAILED: First channel should be UCtest3")
        return False

    print(f"\n✓ Last channel (lowest impressions):")
    print(f"  URL: {last_channel_url}")
    print(f"  Name: {channel_data[last_channel_url]['placement_name']}")
    print(f"  Impressions: {channel_data[last_channel_url]['impressions']:,}")

    if 'UCtest4' not in last_channel_url:
        print(f"  ❌ FAILED: Last channel should be UCtest4")
        return False

    # Verify Unknown channels were skipped
    for url in channel_urls:
        if 'UCtest2' in url or 'UCtest5' in url:
            print(f"  ❌ FAILED: Unknown channel {url} should have been filtered out")
            return False

    print(f"\n✓ Unknown channels correctly filtered out")

    print("\n" + "="*80)
    print("✅ ALL TESTS PASSED!")
    print("="*80)
    print("\nOptimizations working correctly:")
    print("  ✓ Channels sorted by impressions (descending)")
    print("  ✓ 'Unknown' placement names filtered out")
    print("\n")

    return True

if __name__ == '__main__':
    success = test_sorting_and_unknown_filtering()
    sys.exit(0 if success else 1)

"""
YouTube Service Module
Handles YouTube Data API interactions to fetch channel metadata
"""

import time
import logging
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class YouTubeService:
    def __init__(self, api_key, rate_limit_delay=0.1):
        """
        Initialize YouTube Data API service

        Args:
            api_key: YouTube Data API key
            rate_limit_delay: Delay between API calls (seconds)
        """
        self.api_key = api_key
        self.rate_limit_delay = rate_limit_delay
        self.service = build('youtube', 'v3', developerKey=api_key)
        self.api_calls_made = 0

    def extract_channel_id_from_url(self, url):
        """
        Extract channel ID or username from YouTube URL

        Args:
            url: YouTube channel URL

        Returns:
            tuple: (channel_type, channel_identifier)
                   channel_type can be 'id', 'username', 'custom', or 'handle'
        """
        url = url.strip()

        # Handle different URL formats
        if 'youtube.com/channel/' in url:
            # Direct channel ID: https://www.youtube.com/channel/UCxxxxx
            channel_id = url.split('youtube.com/channel/')[-1].split('/')[0].split('?')[0]
            return ('id', channel_id)

        elif 'youtube.com/c/' in url or 'youtube.com/user/' in url:
            # Custom URL or username
            identifier = url.split('youtube.com/')[-1].split('/')[1]
            return ('custom', identifier)

        elif 'youtube.com/@' in url:
            # Handle format: https://www.youtube.com/@username
            handle = url.split('youtube.com/@')[-1].split('/')[0].split('?')[0]
            return ('handle', handle)

        elif 'youtube.com/' in url:
            # Generic format
            parts = url.split('youtube.com/')[-1].split('/')[0]
            return ('custom', parts)

        else:
            logger.warning(f"Unknown URL format: {url}")
            return ('unknown', url)

    def get_channel_id_from_handle(self, handle):
        """
        Convert YouTube handle (@username) to channel ID using search

        Args:
            handle: YouTube handle (with or without @)

        Returns:
            Channel ID or None
        """
        try:
            # Remove @ if present
            handle = handle.lstrip('@')

            # Search for the channel
            request = self.service.search().list(
                part='snippet',
                q=handle,
                type='channel',
                maxResults=1
            )
            response = request.execute()

            self.api_calls_made += 1
            time.sleep(self.rate_limit_delay)

            if response.get('items'):
                return response['items'][0]['snippet']['channelId']

            logger.warning(f"No channel found for handle: @{handle}")
            return None

        except HttpError as error:
            logger.error(f"Error resolving handle {handle}: {error}")
            return None

    def get_channel_metadata(self, channel_url, max_retries=3):
        """
        Fetch channel metadata from YouTube Data API

        Args:
            channel_url: YouTube channel URL
            max_retries: Maximum number of retry attempts

        Returns:
            dict: Channel metadata or None if not found
        """
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Extract channel identifier
                channel_type, identifier = self.extract_channel_id_from_url(channel_url)

                # Get channel ID if needed
                if channel_type == 'handle':
                    channel_id = self.get_channel_id_from_handle(identifier)
                    if not channel_id:
                        return None
                elif channel_type == 'custom':
                    # Try to resolve custom URL using search
                    channel_id = self.get_channel_id_from_handle(identifier)
                    if not channel_id:
                        return None
                elif channel_type == 'id':
                    channel_id = identifier
                else:
                    logger.error(f"Unknown channel type for URL: {channel_url}")
                    return None

                # Fetch channel details
                request = self.service.channels().list(
                    part='snippet,statistics,brandingSettings',
                    id=channel_id
                )
                response = request.execute()

                self.api_calls_made += 1
                time.sleep(self.rate_limit_delay)

                if not response.get('items'):
                    logger.warning(f"No channel data found for: {channel_url}")
                    return None

                channel_data = response['items'][0]

                # Skip fetching recent video titles to save quota (costs 100 units per call)
                # Channel name and description are usually sufficient for analysis
                recent_titles = []

                # Extract relevant metadata
                metadata = {
                    'channel_id': channel_id,
                    'channel_name': channel_data['snippet']['title'],
                    'description': channel_data['snippet'].get('description', ''),
                    'custom_url': channel_data['snippet'].get('customUrl', ''),
                    'subscriber_count': channel_data['statistics'].get('subscriberCount', '0'),
                    'video_count': channel_data['statistics'].get('videoCount', '0'),
                    'view_count': channel_data['statistics'].get('viewCount', '0'),
                    'published_at': channel_data['snippet'].get('publishedAt', ''),
                    'country': channel_data['snippet'].get('country', ''),
                    'keywords': channel_data.get('brandingSettings', {}).get('channel', {}).get('keywords', ''),
                    'recent_video_titles': recent_titles,
                    'channel_url': f"https://www.youtube.com/channel/{channel_id}"
                }

                logger.info(f"Retrieved metadata for channel: {metadata['channel_name']}")
                return metadata

            except HttpError as error:
                if error.resp.status == 403:
                    logger.error(f"API quota exceeded: {error}")
                    raise
                elif error.resp.status == 404:
                    logger.warning(f"Channel not found: {channel_url}")
                    return None
                else:
                    retry_count += 1
                    logger.warning(f"API error (attempt {retry_count}/{max_retries}): {error}")
                    time.sleep(2 ** retry_count)  # Exponential backoff

            except Exception as error:
                retry_count += 1
                logger.error(f"Error fetching channel metadata (attempt {retry_count}/{max_retries}): {error}")
                time.sleep(2 ** retry_count)

        return None

    def get_recent_video_titles(self, channel_id, max_results=5):
        """
        Get titles of recent videos for better content analysis

        Args:
            channel_id: YouTube channel ID
            max_results: Number of recent videos to fetch

        Returns:
            list: List of recent video titles
        """
        try:
            request = self.service.search().list(
                part='snippet',
                channelId=channel_id,
                type='video',
                order='date',
                maxResults=max_results
            )
            response = request.execute()

            self.api_calls_made += 1
            time.sleep(self.rate_limit_delay)

            titles = [item['snippet']['title'] for item in response.get('items', [])]
            return titles

        except HttpError as error:
            logger.warning(f"Error fetching recent videos: {error}")
            return []

    def batch_get_channels_metadata(self, channel_urls, batch_size=50):
        """
        Fetch metadata for multiple channels efficiently

        Args:
            channel_urls: List of channel URLs
            batch_size: Maximum channels per API call

        Returns:
            dict: Mapping of channel URL to metadata
        """
        results = {}

        for i, channel_url in enumerate(channel_urls):
            logger.info(f"Processing channel {i+1}/{len(channel_urls)}")

            metadata = self.get_channel_metadata(channel_url)
            if metadata:
                results[channel_url] = metadata

        logger.info(f"Total YouTube API calls made: {self.api_calls_made}")
        return results

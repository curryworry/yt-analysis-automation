"""
OpenAI Service Module
Handles AI-powered channel categorization using GPT-4o-mini
Uses REST API directly to avoid Cloud Functions proxy issues
"""

import json
import logging
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self, api_key, model='gpt-4o-mini', system_prompt=None, user_prompt_template=None):
        """
        Initialize OpenAI service using REST API

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4o-mini)
            system_prompt: System prompt for the model
            user_prompt_template: Template for user prompt
        """
        self.api_key = api_key
        self.model = model
        self.api_calls_made = 0
        self.api_url = "https://api.openai.com/v1/chat/completions"

        # Create persistent session with retry strategy to handle SSL issues
        self.session = requests.Session()

        # Configure retry strategy for transient SSL/network errors
        retry_strategy = Retry(
            total=3,
            backoff_factor=2,  # 2, 4, 8 seconds
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST"],
            raise_on_status=False  # Let us handle HTTP errors
        )

        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=10,
            pool_maxsize=10
        )

        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.system_prompt = system_prompt or """You are an expert at analyzing YouTube channels to determine if they primarily target children.
Consider factors like: content themes, language complexity, visual style, and target audience."""

        self.user_prompt_template = user_prompt_template or """Analyze this YouTube channel and determine if it primarily targets children (under 13):

Channel Name: {channel_name}
Description: {description}
Custom URL: {custom_url}
Subscriber Count: {subscriber_count}
Video Count: {video_count}
Recent Video Titles: {recent_titles}

Respond with a JSON object containing:
- "is_children_content": true/false
- "confidence": "high"/"medium"/"low"
- "reasoning": brief explanation (1-2 sentences)

Example response:
{{"is_children_content": true, "confidence": "high", "reasoning": "Channel features nursery rhymes and animations clearly targeting toddlers and preschoolers."}}"""

    def format_recent_videos(self, recent_videos):
        """
        Format recent videos data for the prompt

        Args:
            recent_videos: List of video dicts with title, description, published_at

        Returns:
            str: Formatted string of recent videos
        """
        if not recent_videos:
            return "No recent videos available"

        formatted = []
        for i, video in enumerate(recent_videos[:5], 1):
            title = video.get('title', 'No title')
            description = video.get('description', '')[:200]  # Limit description length
            formatted.append(f"{i}. Title: {title}\n   Description: {description}")

        return '\n'.join(formatted)

    def categorize_channel(self, channel_metadata, max_retries=3):
        """
        Categorize a YouTube channel using OpenAI REST API

        Args:
            channel_metadata: Dict containing channel metadata
            max_retries: Maximum number of retry attempts

        Returns:
            dict: Categorization result with enhanced targeting data
        """
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Format recent videos
                recent_videos_formatted = self.format_recent_videos(
                    channel_metadata.get('recent_videos', [])
                )

                # Prepare prompt with channel data
                user_prompt = self.user_prompt_template.format(
                    channel_name=channel_metadata.get('channel_name', 'Unknown'),
                    description=channel_metadata.get('description', 'No description')[:1000],  # Increased limit
                    keywords=channel_metadata.get('keywords', 'None'),
                    country=channel_metadata.get('country', 'Unknown'),
                    subscriber_count=channel_metadata.get('subscriber_count', '0'),
                    video_count=channel_metadata.get('video_count', '0'),
                    view_count=channel_metadata.get('view_count', '0'),
                    published_at=channel_metadata.get('published_at', 'Unknown'),
                    recent_videos=recent_videos_formatted
                )

                # Prepare request payload
                payload = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}
                }

                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }

                # Call OpenAI REST API using persistent session
                response = self.session.post(
                    self.api_url,
                    headers=headers,
                    json=payload,
                    timeout=60  # Increased timeout from 30 to 60 seconds
                )

                response.raise_for_status()
                self.api_calls_made += 1

                # Parse response
                response_data = response.json()
                result_text = response_data['choices'][0]['message']['content']
                result = json.loads(result_text)

                # Validate result format (new enhanced format)
                required_sections = ['compliance', 'content', 'brand_safety', 'targeting', 'summary']
                if not all(k in result for k in required_sections):
                    logger.warning(f"Invalid response format, missing sections: {result_text[:200]}")
                    retry_count += 1
                    continue

                # Extract key values for backward compatibility
                compliance = result.get('compliance', {})
                content = result.get('content', {})
                brand_safety = result.get('brand_safety', {})

                # Create flattened result for easier use
                flattened_result = {
                    # Compliance (backward compatible)
                    'is_children_content': compliance.get('is_children_content', False),
                    'confidence': compliance.get('confidence', 'low'),
                    'reasoning': compliance.get('reasoning', ''),

                    # Enhanced targeting data
                    'content_vertical': content.get('primary_vertical', 'Other'),
                    'content_niche': content.get('sub_niche', ''),
                    'content_format': content.get('format', ''),
                    'content_confidence': content.get('confidence', 'low'),

                    'brand_safety_score': brand_safety.get('overall_score', 'moderate'),
                    'controversial_topics': brand_safety.get('controversial_topics', False),
                    'premium_suitable': brand_safety.get('premium_suitable', True),
                    'safety_flags': brand_safety.get('flags', []),

                    'geographic_focus': result.get('targeting', {}).get('geographic_focus', 'unknown'),
                    'primary_language': result.get('targeting', {}).get('primary_language', 'unknown'),
                    'purchase_intent': result.get('targeting', {}).get('purchase_intent', 'unknown'),

                    'summary': result.get('summary', ''),

                    # Keep full result for reference
                    'full_analysis': result
                }

                logger.info(f"Categorized channel: {channel_metadata.get('channel_name')} - "
                          f"Children's content: {flattened_result['is_children_content']}, "
                          f"Vertical: {flattened_result['content_vertical']}, "
                          f"Safety: {flattened_result['brand_safety_score']}")

                return flattened_result

            except json.JSONDecodeError as error:
                logger.error(f"Error parsing OpenAI response: {error}")
                retry_count += 1
                time.sleep(2 ** retry_count)

            except requests.exceptions.RequestException as error:
                error_msg = str(error).lower()

                # Check for quota/billing errors
                if 'quota' in error_msg or 'insufficient_quota' in error_msg or 'billing' in error_msg or 'rate_limit' in error_msg:
                    logger.error(f"OpenAI quota/billing error: {error}")
                    raise Exception(f"OpenAI quota exceeded: {error}")

                logger.error(f"Error calling OpenAI API (attempt {retry_count + 1}/{max_retries}): {error}")
                retry_count += 1

                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Exponential backoff

            except Exception as error:
                logger.error(f"Unexpected error (attempt {retry_count + 1}/{max_retries}): {error}")
                retry_count += 1

                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)

        # Return default result if all retries fail
        logger.error(f"Failed to categorize channel after {max_retries} attempts: "
                    f"{channel_metadata.get('channel_name')}")

        return {
            'is_children_content': False,
            'confidence': 'low',
            'reasoning': 'Failed to analyze due to API errors'
        }

    def batch_categorize_channels(self, channels_metadata, rate_limit_delay=0.5):
        """
        Categorize multiple channels with rate limiting

        Args:
            channels_metadata: List of channel metadata dicts
            rate_limit_delay: Delay between API calls (seconds)

        Returns:
            list: List of categorization results
        """
        results = []

        for i, metadata in enumerate(channels_metadata):
            logger.info(f"Categorizing channel {i + 1}/{len(channels_metadata)}: "
                       f"{metadata.get('channel_name')}")

            result = self.categorize_channel(metadata)
            results.append({
                'channel_url': metadata.get('channel_url'),
                'channel_name': metadata.get('channel_name'),
                **result
            })

            # Rate limiting
            if i < len(channels_metadata) - 1:
                time.sleep(rate_limit_delay)

        logger.info(f"Total OpenAI API calls made: {self.api_calls_made}")
        return results

    def categorize_with_keyword_prefilter(self, channel_metadata, keywords):
        """
        Quick categorization using keyword matching before calling OpenAI
        This can help reduce API costs for obvious cases

        Args:
            channel_metadata: Dict containing channel metadata
            keywords: List of keywords to check for

        Returns:
            dict: Categorization result or None if keywords not found
        """
        # Check channel name and description for keywords
        text_to_check = (
            channel_metadata.get('channel_name', '').lower() + ' ' +
            channel_metadata.get('description', '').lower() + ' ' +
            ' '.join(channel_metadata.get('recent_video_titles', [])).lower()
        )

        # Check if any keyword is present
        matched_keywords = [kw for kw in keywords if kw.lower() in text_to_check]

        if matched_keywords:
            logger.info(f"Pre-filter matched keywords {matched_keywords} for "
                       f"{channel_metadata.get('channel_name')}")

            # Still use OpenAI for confirmation, but this could be skipped for cost optimization
            return self.categorize_channel(channel_metadata)

        return None

    def get_stats(self):
        """
        Get API usage statistics

        Returns:
            dict: API call statistics
        """
        return {
            'api_calls_made': self.api_calls_made,
            'estimated_cost_usd': self.api_calls_made * 0.00015  # Rough estimate for gpt-4o-mini
        }

"""
OpenAI Service Module
Handles AI-powered channel categorization using GPT-4o-mini
"""

import json
import logging
import time
from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAIService:
    def __init__(self, api_key, model='gpt-4o-mini', system_prompt=None, user_prompt_template=None):
        """
        Initialize OpenAI service

        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4o-mini)
            system_prompt: System prompt for the model
            user_prompt_template: Template for user prompt
        """
        # Initialize OpenAI client without proxy settings for Cloud Functions compatibility
        import os
        # Remove any proxy environment variables that cause issues in Cloud Functions
        for proxy_var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']:
            os.environ.pop(proxy_var, None)

        # Initialize client with explicit no-proxy configuration
        try:
            self.client = OpenAI(api_key=api_key, http_client=None)
        except TypeError:
            # Fallback for older OpenAI versions
            self.client = OpenAI(api_key=api_key)
        self.model = model
        self.api_calls_made = 0

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

    def categorize_channel(self, channel_metadata, max_retries=3):
        """
        Categorize a YouTube channel using OpenAI

        Args:
            channel_metadata: Dict containing channel metadata
            max_retries: Maximum number of retry attempts

        Returns:
            dict: Categorization result with is_children_content, confidence, reasoning
        """
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Prepare prompt with channel data
                user_prompt = self.user_prompt_template.format(
                    channel_name=channel_metadata.get('channel_name', 'Unknown'),
                    description=channel_metadata.get('description', 'No description')[:500],  # Limit length
                    custom_url=channel_metadata.get('custom_url', 'N/A'),
                    subscriber_count=channel_metadata.get('subscriber_count', '0'),
                    video_count=channel_metadata.get('video_count', '0'),
                    recent_titles=', '.join(channel_metadata.get('recent_video_titles', [])[:5])
                )

                # Call OpenAI API
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": self.system_prompt},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.3,  # Lower temperature for more consistent results
                    response_format={"type": "json_object"}
                )

                self.api_calls_made += 1

                # Parse response
                result_text = response.choices[0].message.content
                result = json.loads(result_text)

                # Validate result format
                if not all(k in result for k in ['is_children_content', 'confidence', 'reasoning']):
                    logger.warning(f"Invalid response format: {result_text}")
                    retry_count += 1
                    continue

                logger.info(f"Categorized channel: {channel_metadata.get('channel_name')} - "
                          f"Children's content: {result['is_children_content']}, "
                          f"Confidence: {result['confidence']}")

                return result

            except json.JSONDecodeError as error:
                logger.error(f"Error parsing OpenAI response: {error}")
                retry_count += 1
                time.sleep(2 ** retry_count)

            except Exception as error:
                logger.error(f"Error calling OpenAI API (attempt {retry_count + 1}/{max_retries}): {error}")
                retry_count += 1

                if retry_count < max_retries:
                    time.sleep(2 ** retry_count)  # Exponential backoff

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

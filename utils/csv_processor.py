"""
CSV Processor Module
Handles CSV reading, channel extraction, filtering, and batch processing
"""

import csv
import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class CSVProcessor:
    def __init__(self, keywords=None):
        """
        Initialize CSV processor

        Args:
            keywords: List of keywords for pre-filtering channels
        """
        self.keywords = keywords or []
        self.total_rows = 0
        self.filtered_rows = 0
        self.unique_channels = set()

    def read_dv360_csv(self, csv_path):
        """
        Read DV360 placement report CSV

        Args:
            csv_path: Path to CSV file

        Returns:
            list: List of row dicts
        """
        rows = []

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as f:
                # Try to detect dialect
                sample = f.read(4096)
                f.seek(0)

                sniffer = csv.Sniffer()
                try:
                    dialect = sniffer.sniff(sample)
                except csv.Error:
                    dialect = csv.excel

                reader = csv.DictReader(f, dialect=dialect)

                # Log column names for debugging
                first_row = True
                for row in reader:
                    if first_row:
                        logger.info(f"CSV column names: {list(row.keys())}")
                        first_row = False
                    rows.append(row)
                    self.total_rows += 1

                logger.info(f"Read {self.total_rows} rows from CSV")

        except Exception as error:
            logger.error(f"Error reading CSV: {error}")
            raise

        return rows

    def extract_youtube_channels(self, rows):
        """
        Extract unique YouTube channel URLs from placement data

        Args:
            rows: List of row dicts from CSV

        Returns:
            dict: Mapping of channel URL to aggregated data
        """
        channel_data = defaultdict(lambda: {
            'placement_name': '',
            'impressions': 0,
            'advertisers': set(),
            'insertion_orders': set()
        })

        unknown_count = 0

        try:
            for row in rows:
                # Handle both old and new DV360 CSV column formats
                placement = (row.get('Placement (All YouTube Channels)') or row.get('Placement') or '').strip()

                # Check if this is a YouTube channel placement
                if not placement or 'youtube.com' not in placement.lower():
                    continue

                # Extract channel URL
                channel_url = self._extract_channel_url(placement)
                if not channel_url:
                    continue

                # Aggregate data for this channel
                impressions = self._parse_impressions(row.get('Impressions', '0'))
                placement_name = row.get('Placement Name (All YouTube Channels)', row.get('Placement Name', ''))

                # Skip channels with "Unknown" placement name (removed by YouTube)
                if placement_name.strip().lower() == 'unknown':
                    unknown_count += 1
                    logger.debug(f"Skipping channel with 'Unknown' placement name: {channel_url}")
                    continue

                channel_data[channel_url]['placement_name'] = placement_name
                channel_data[channel_url]['impressions'] += impressions
                channel_data[channel_url]['advertisers'].add(row.get('Advertiser', 'Unknown'))
                channel_data[channel_url]['insertion_orders'].add(row.get('Insertion Order', 'Unknown'))

                self.unique_channels.add(channel_url)

            # Convert sets to lists for JSON serialization
            for channel_url in channel_data:
                channel_data[channel_url]['advertisers'] = list(channel_data[channel_url]['advertisers'])
                channel_data[channel_url]['insertion_orders'] = list(channel_data[channel_url]['insertion_orders'])

            # Sort channels by impressions (descending) - focus on high-traffic channels first
            sorted_channels = dict(sorted(
                channel_data.items(),
                key=lambda item: item[1]['impressions'],
                reverse=True
            ))

            logger.info(f"Extracted {len(sorted_channels)} unique YouTube channels (sorted by impressions)")
            if unknown_count > 0:
                logger.info(f"Skipped {unknown_count} channels with 'Unknown' placement name (removed by YouTube)")
            if sorted_channels:
                top_channel = next(iter(sorted_channels.items()))
                logger.info(f"Top channel has {top_channel[1]['impressions']:,} impressions")

        except Exception as error:
            logger.error(f"Error extracting channels: {error}")
            raise

        return sorted_channels

    def filter_channels_by_keywords(self, channel_data):
        """
        Pre-filter channels based on keywords in placement names

        Args:
            channel_data: Dict mapping channel URL to data

        Returns:
            dict: Filtered channel data
        """
        if not self.keywords:
            logger.info("No keywords configured, skipping pre-filter")
            return channel_data

        filtered = {}

        for channel_url, data in channel_data.items():
            placement_name = data.get('placement_name', '').lower()

            # Check if any keyword is in the placement name
            if any(keyword.lower() in placement_name for keyword in self.keywords):
                filtered[channel_url] = data
                self.filtered_rows += 1

        logger.info(f"Pre-filtered to {len(filtered)} channels matching keywords: {self.keywords}")

        return filtered

    def _extract_channel_url(self, placement_text):
        """
        Extract clean YouTube channel URL from placement text

        Args:
            placement_text: Placement text containing URL

        Returns:
            str: Clean channel URL or None
        """
        try:
            # Find youtube.com URL in text
            if 'youtube.com/channel/' in placement_text:
                # Extract channel ID format
                start_idx = placement_text.find('youtube.com/channel/')
                url_part = placement_text[start_idx:]

                # Clean up URL (remove trailing characters)
                channel_id = url_part.split('/')[-1].split()[0].strip(',;()')

                return f"https://www.youtube.com/channel/{channel_id}"

            elif 'youtube.com/@' in placement_text:
                # Handle @ format
                start_idx = placement_text.find('youtube.com/@')
                url_part = placement_text[start_idx:]

                handle = url_part.split('/')[-1].split()[0].strip(',;()')

                return f"https://www.youtube.com/@{handle}"

            elif 'youtube.com/c/' in placement_text:
                # Custom URL format
                start_idx = placement_text.find('youtube.com/c/')
                url_part = placement_text[start_idx:]

                custom_name = url_part.split('/')[-1].split()[0].strip(',;()')

                return f"https://www.youtube.com/c/{custom_name}"

            elif 'youtube.com/user/' in placement_text:
                # Legacy username format
                start_idx = placement_text.find('youtube.com/user/')
                url_part = placement_text[start_idx:]

                username = url_part.split('/')[-1].split()[0].strip(',;()')

                return f"https://www.youtube.com/user/{username}"

            else:
                # Generic youtube.com URL
                if 'youtube.com/' in placement_text:
                    start_idx = placement_text.find('youtube.com/')
                    url_part = placement_text[start_idx:]

                    # Extract channel identifier
                    parts = url_part.split('/')
                    if len(parts) >= 2:
                        identifier = parts[1].split()[0].strip(',;()')
                        return f"https://www.youtube.com/{identifier}"

        except Exception as error:
            logger.warning(f"Error extracting channel URL from: {placement_text[:100]}")

        return None

    def _parse_impressions(self, impressions_str):
        """
        Parse impressions string to integer

        Args:
            impressions_str: String representation of impressions

        Returns:
            int: Impressions count
        """
        try:
            # Remove commas and convert to int
            return int(impressions_str.replace(',', '').strip())
        except (ValueError, AttributeError):
            return 0

    def create_results_csv(self, results, output_path):
        """
        Create CSV file with categorization results

        Args:
            results: List of categorization result dicts
            output_path: Path to save CSV file
        """
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'channel_name',
                    'channel_url',
                    'is_children_content',
                    'confidence',
                    'reasoning',
                    'impressions',
                    'advertisers',
                    'insertion_orders'
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in results:
                    # Only include channels flagged as children's content
                    if result.get('is_children_content'):
                        writer.writerow({
                            'channel_name': result.get('channel_name', 'Unknown'),
                            'channel_url': result.get('channel_url', ''),
                            'is_children_content': result.get('is_children_content', False),
                            'confidence': result.get('confidence', 'unknown'),
                            'reasoning': result.get('reasoning', ''),
                            'impressions': result.get('impressions', 0),
                            'advertisers': ', '.join(result.get('advertisers', [])),
                            'insertion_orders': ', '.join(result.get('insertion_orders', []))
                        })

            logger.info(f"Created results CSV at: {output_path}")

        except Exception as error:
            logger.error(f"Error creating results CSV: {error}")
            raise

    def create_inclusion_list(self, results, output_path):
        """
        Create CSV inclusion list (SAFE channels to INCLUDE in campaigns)

        Args:
            results: List of categorization result dicts
            output_path: Path to save CSV file

        Returns:
            int: Number of channels in inclusion list
        """
        try:
            safe_channels = [r for r in results if not r.get('is_children_content')]

            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'channel_name',
                    'channel_url',
                    'channel_id',
                    'impressions',
                    # Top-level Firestore fields
                    'is_children_content',
                    'confidence',
                    'reasoning',
                    'content_vertical',
                    'content_niche',
                    'content_format',
                    'brand_safety_score',
                    'premium_suitable',
                    'geographic_focus',
                    'primary_language',
                    'purchase_intent',
                    'summary',
                    # full_analysis.compliance fields
                    'compliance_confidence',
                    'compliance_is_children_content',
                    'compliance_reasoning',
                    # full_analysis.content fields
                    'content_confidence',
                    'content_format_detail',
                    'content_primary_vertical',
                    'content_sub_niche',
                    # full_analysis.brand_safety fields
                    'brand_safety_controversial_topics',
                    'brand_safety_first_flag',
                    'brand_safety_overall_score',
                    'brand_safety_premium_suitable',
                    # full_analysis.summary
                    'full_analysis_summary'
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in safe_channels:
                    # Extract channel ID from URL
                    channel_url = result.get('channel_url', '')
                    channel_id = channel_url.split('/')[-1] if '/channel/' in channel_url else ''

                    # Extract nested fields safely with "No data" defaults
                    full_analysis = result.get('full_analysis', {})
                    compliance = full_analysis.get('compliance', {}) if isinstance(full_analysis, dict) else {}
                    content = full_analysis.get('content', {}) if isinstance(full_analysis, dict) else {}
                    brand_safety = full_analysis.get('brand_safety', {}) if isinstance(full_analysis, dict) else {}

                    # Get first flag from brand_safety.flags array if exists, otherwise "No data"
                    flags = brand_safety.get('flags', []) if isinstance(brand_safety, dict) else []
                    first_flag = flags[0] if (flags and len(flags) > 0) else 'No data'

                    writer.writerow({
                        'channel_name': result.get('channel_name', 'No data'),
                        'channel_url': channel_url,
                        'channel_id': channel_id,
                        'impressions': result.get('impressions', 0),
                        # Top-level Firestore fields
                        'is_children_content': result.get('is_children_content', 'No data'),
                        'confidence': result.get('confidence', 'No data'),
                        'reasoning': result.get('reasoning', 'No data'),
                        'content_vertical': result.get('content_vertical', 'No data'),
                        'content_niche': result.get('content_niche', 'No data'),
                        'content_format': result.get('content_format', 'No data'),
                        'brand_safety_score': result.get('brand_safety_score', 'No data'),
                        'premium_suitable': result.get('premium_suitable', 'No data'),
                        'geographic_focus': result.get('geographic_focus', 'No data'),
                        'primary_language': result.get('primary_language', 'No data'),
                        'purchase_intent': result.get('purchase_intent', 'No data'),
                        'summary': result.get('summary', 'No data'),
                        # full_analysis.compliance fields
                        'compliance_confidence': compliance.get('confidence', 'No data') if isinstance(compliance, dict) else 'No data',
                        'compliance_is_children_content': compliance.get('is_children_content', 'No data') if isinstance(compliance, dict) else 'No data',
                        'compliance_reasoning': compliance.get('reasoning', 'No data') if isinstance(compliance, dict) else 'No data',
                        # full_analysis.content fields
                        'content_confidence': content.get('confidence', 'No data') if isinstance(content, dict) else 'No data',
                        'content_format_detail': content.get('format', 'No data') if isinstance(content, dict) else 'No data',
                        'content_primary_vertical': content.get('primary_vertical', 'No data') if isinstance(content, dict) else 'No data',
                        'content_sub_niche': content.get('sub_niche', 'No data') if isinstance(content, dict) else 'No data',
                        # full_analysis.brand_safety fields
                        'brand_safety_controversial_topics': brand_safety.get('controversial_topics', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        'brand_safety_first_flag': first_flag,
                        'brand_safety_overall_score': brand_safety.get('overall_score', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        'brand_safety_premium_suitable': brand_safety.get('premium_suitable', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        # full_analysis.summary
                        'full_analysis_summary': full_analysis.get('summary', 'No data') if isinstance(full_analysis, dict) else 'No data'
                    })

            logger.info(f"Created inclusion list (SAFE/INCLUDE) with {len(safe_channels)} channels at: {output_path}")
            return len(safe_channels)

        except Exception as error:
            logger.error(f"Error creating inclusion list: {error}")
            raise

    def create_exclusion_list(self, results, output_path):
        """
        Create CSV exclusion list (children's content channels to EXCLUDE/BLOCK from campaigns)

        Args:
            results: List of categorization result dicts
            output_path: Path to save CSV file

        Returns:
            int: Number of channels in exclusion list
        """
        try:
            children_channels = [r for r in results if r.get('is_children_content')]

            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = [
                    'channel_name',
                    'channel_url',
                    'channel_id',
                    'impressions',
                    'advertisers',
                    'insertion_orders',
                    # Top-level Firestore fields
                    'is_children_content',
                    'confidence',
                    'reasoning',
                    'content_vertical',
                    'content_niche',
                    'content_format',
                    'brand_safety_score',
                    'premium_suitable',
                    'geographic_focus',
                    'primary_language',
                    'purchase_intent',
                    'summary',
                    # full_analysis.compliance fields
                    'compliance_confidence',
                    'compliance_is_children_content',
                    'compliance_reasoning',
                    # full_analysis.content fields
                    'content_confidence',
                    'content_format_detail',
                    'content_primary_vertical',
                    'content_sub_niche',
                    # full_analysis.brand_safety fields
                    'brand_safety_controversial_topics',
                    'brand_safety_first_flag',
                    'brand_safety_overall_score',
                    'brand_safety_premium_suitable',
                    # full_analysis.summary
                    'full_analysis_summary'
                ]

                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in children_channels:
                    # Extract channel ID from URL
                    channel_url = result.get('channel_url', '')
                    channel_id = channel_url.split('/')[-1] if '/channel/' in channel_url else ''

                    # Extract nested fields safely with "No data" defaults
                    full_analysis = result.get('full_analysis', {})
                    compliance = full_analysis.get('compliance', {}) if isinstance(full_analysis, dict) else {}
                    content = full_analysis.get('content', {}) if isinstance(full_analysis, dict) else {}
                    brand_safety = full_analysis.get('brand_safety', {}) if isinstance(full_analysis, dict) else {}

                    # Get first flag from brand_safety.flags array if exists, otherwise "No data"
                    flags = brand_safety.get('flags', []) if isinstance(brand_safety, dict) else []
                    first_flag = flags[0] if (flags and len(flags) > 0) else 'No data'

                    writer.writerow({
                        'channel_name': result.get('channel_name', 'No data'),
                        'channel_url': channel_url,
                        'channel_id': channel_id,
                        'impressions': result.get('impressions', 0),
                        'advertisers': ', '.join(result.get('advertisers', [])) if result.get('advertisers') else 'No data',
                        'insertion_orders': ', '.join(result.get('insertion_orders', [])) if result.get('insertion_orders') else 'No data',
                        # Top-level Firestore fields
                        'is_children_content': result.get('is_children_content', 'No data'),
                        'confidence': result.get('confidence', 'No data'),
                        'reasoning': result.get('reasoning', 'No data'),
                        'content_vertical': result.get('content_vertical', 'No data'),
                        'content_niche': result.get('content_niche', 'No data'),
                        'content_format': result.get('content_format', 'No data'),
                        'brand_safety_score': result.get('brand_safety_score', 'No data'),
                        'premium_suitable': result.get('premium_suitable', 'No data'),
                        'geographic_focus': result.get('geographic_focus', 'No data'),
                        'primary_language': result.get('primary_language', 'No data'),
                        'purchase_intent': result.get('purchase_intent', 'No data'),
                        'summary': result.get('summary', 'No data'),
                        # full_analysis.compliance fields
                        'compliance_confidence': compliance.get('confidence', 'No data') if isinstance(compliance, dict) else 'No data',
                        'compliance_is_children_content': compliance.get('is_children_content', 'No data') if isinstance(compliance, dict) else 'No data',
                        'compliance_reasoning': compliance.get('reasoning', 'No data') if isinstance(compliance, dict) else 'No data',
                        # full_analysis.content fields
                        'content_confidence': content.get('confidence', 'No data') if isinstance(content, dict) else 'No data',
                        'content_format_detail': content.get('format', 'No data') if isinstance(content, dict) else 'No data',
                        'content_primary_vertical': content.get('primary_vertical', 'No data') if isinstance(content, dict) else 'No data',
                        'content_sub_niche': content.get('sub_niche', 'No data') if isinstance(content, dict) else 'No data',
                        # full_analysis.brand_safety fields
                        'brand_safety_controversial_topics': brand_safety.get('controversial_topics', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        'brand_safety_first_flag': first_flag,
                        'brand_safety_overall_score': brand_safety.get('overall_score', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        'brand_safety_premium_suitable': brand_safety.get('premium_suitable', 'No data') if isinstance(brand_safety, dict) else 'No data',
                        # full_analysis.summary
                        'full_analysis_summary': full_analysis.get('summary', 'No data') if isinstance(full_analysis, dict) else 'No data'
                    })

            logger.info(f"Created exclusion list (BLOCK/EXCLUDE) with {len(children_channels)} channels at: {output_path}")
            return len(children_channels)

        except Exception as error:
            logger.error(f"Error creating exclusion list: {error}")
            raise

    def get_stats(self):
        """
        Get processing statistics

        Returns:
            dict: Processing stats
        """
        return {
            'total_rows': self.total_rows,
            'unique_channels': len(self.unique_channels),
            'filtered_channels': self.filtered_rows
        }

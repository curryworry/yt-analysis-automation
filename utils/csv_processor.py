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

                for row in reader:
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

        try:
            for row in rows:
                placement = row.get('Placement', '').strip()

                # Check if this is a YouTube channel placement
                if not placement or 'youtube.com' not in placement.lower():
                    continue

                # Extract channel URL
                channel_url = self._extract_channel_url(placement)
                if not channel_url:
                    continue

                # Aggregate data for this channel
                impressions = self._parse_impressions(row.get('Impressions', '0'))

                channel_data[channel_url]['placement_name'] = row.get('Placement Name', '')
                channel_data[channel_url]['impressions'] += impressions
                channel_data[channel_url]['advertisers'].add(row.get('Advertiser', 'Unknown'))
                channel_data[channel_url]['insertion_orders'].add(row.get('Insertion Order', 'Unknown'))

                self.unique_channels.add(channel_url)

            # Convert sets to lists for JSON serialization
            for channel_url in channel_data:
                channel_data[channel_url]['advertisers'] = list(channel_data[channel_url]['advertisers'])
                channel_data[channel_url]['insertion_orders'] = list(channel_data[channel_url]['insertion_orders'])

            logger.info(f"Extracted {len(channel_data)} unique YouTube channels")

        except Exception as error:
            logger.error(f"Error extracting channels: {error}")
            raise

        return dict(channel_data)

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

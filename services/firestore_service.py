"""
Firestore Service Module
Handles caching and retrieval of channel categorization results
"""

import logging
from datetime import datetime
from google.cloud import firestore

logger = logging.getLogger(__name__)


class FirestoreService:
    def __init__(self, project_id, collection_name='channel_categories'):
        """
        Initialize Firestore client

        Args:
            project_id: GCP project ID
            collection_name: Name of Firestore collection for caching
        """
        self.project_id = project_id
        self.collection_name = collection_name
        self.db = firestore.Client(project=project_id)
        self.collection = self.db.collection(collection_name)
        self.cache_hits = 0
        self.cache_misses = 0

    def get_cached_category(self, channel_url):
        """
        Retrieve cached categorization result for a channel

        Args:
            channel_url: YouTube channel URL

        Returns:
            dict: Cached categorization data or None if not found
        """
        try:
            # Use channel URL as document ID (sanitized)
            doc_id = self._sanitize_doc_id(channel_url)

            doc = self.collection.document(doc_id).get()

            if doc.exists:
                self.cache_hits += 1
                cached_data = doc.to_dict()
                logger.info(f"Cache HIT for channel: {channel_url}")
                return cached_data
            else:
                self.cache_misses += 1
                logger.info(f"Cache MISS for channel: {channel_url}")
                return None

        except Exception as error:
            logger.error(f"Error retrieving from cache: {error}")
            return None

    def save_category(self, channel_url, channel_name, is_children_content,
                     confidence, reasoning, metadata=None):
        """
        Save categorization result to Firestore

        Args:
            channel_url: YouTube channel URL
            channel_name: Channel name
            is_children_content: Boolean indicating if channel targets children
            confidence: Confidence level (high/medium/low)
            reasoning: Explanation for categorization
            metadata: Optional additional metadata dict
        """
        try:
            doc_id = self._sanitize_doc_id(channel_url)

            data = {
                'channel_url': channel_url,
                'channel_name': channel_name,
                'is_children_content': is_children_content,
                'confidence': confidence,
                'reasoning': reasoning,
                'created_at': firestore.SERVER_TIMESTAMP,
                'updated_at': firestore.SERVER_TIMESTAMP,
                'version': '1.0'
            }

            # Add optional metadata
            if metadata:
                data['metadata'] = metadata

            self.collection.document(doc_id).set(data)
            logger.info(f"Saved category for channel: {channel_name}")

        except Exception as error:
            logger.error(f"Error saving to Firestore: {error}")
            raise

    def batch_get_cached_categories(self, channel_urls):
        """
        Retrieve cached results for multiple channels efficiently

        Args:
            channel_urls: List of channel URLs

        Returns:
            dict: Mapping of channel URL to cached data
        """
        results = {}

        try:
            # Firestore supports batch reads up to 500 documents
            batch_size = 500

            for i in range(0, len(channel_urls), batch_size):
                batch_urls = channel_urls[i:i + batch_size]

                # Get documents
                doc_ids = [self._sanitize_doc_id(url) for url in batch_urls]
                docs = [self.collection.document(doc_id).get() for doc_id in doc_ids]

                # Process results
                for url, doc in zip(batch_urls, docs):
                    if doc.exists:
                        results[url] = doc.to_dict()
                        self.cache_hits += 1
                    else:
                        self.cache_misses += 1

            logger.info(f"Batch cache check: {self.cache_hits} hits, {self.cache_misses} misses")

        except Exception as error:
            logger.error(f"Error in batch cache retrieval: {error}")

        return results

    def batch_save_categories(self, categories_data):
        """
        Save multiple categorization results efficiently using batch writes

        Args:
            categories_data: List of dicts with categorization data
        """
        try:
            # Firestore batch writes support up to 500 operations
            batch_size = 500
            total_saved = 0

            for i in range(0, len(categories_data), batch_size):
                batch_data = categories_data[i:i + batch_size]
                batch = self.db.batch()

                for data in batch_data:
                    doc_id = self._sanitize_doc_id(data['channel_url'])
                    doc_ref = self.collection.document(doc_id)

                    save_data = {
                        'channel_url': data['channel_url'],
                        'channel_name': data['channel_name'],
                        # Compliance (backward compatible)
                        'is_children_content': data.get('is_children_content', False),
                        'confidence': data.get('confidence', 'low'),
                        'reasoning': data.get('reasoning', ''),
                        # Enhanced targeting data (optional, won't break if missing)
                        'content_vertical': data.get('content_vertical', ''),
                        'content_niche': data.get('content_niche', ''),
                        'content_format': data.get('content_format', ''),
                        'brand_safety_score': data.get('brand_safety_score', ''),
                        'premium_suitable': data.get('premium_suitable', True),
                        'geographic_focus': data.get('geographic_focus', ''),
                        'primary_language': data.get('primary_language', ''),
                        'purchase_intent': data.get('purchase_intent', ''),
                        'summary': data.get('summary', ''),
                        'created_at': firestore.SERVER_TIMESTAMP,
                        'updated_at': firestore.SERVER_TIMESTAMP,
                        'version': '2.0'  # Updated version for enhanced data
                    }

                    if 'metadata' in data:
                        save_data['metadata'] = data['metadata']

                    # Store full analysis if available
                    if 'full_analysis' in data:
                        save_data['full_analysis'] = data['full_analysis']

                    batch.set(doc_ref, save_data)

                batch.commit()
                total_saved += len(batch_data)

            logger.info(f"Batch saved {total_saved} categorization results")

        except Exception as error:
            logger.error(f"Error in batch save: {error}")
            raise

    def update_category(self, channel_url, updates):
        """
        Update existing category data

        Args:
            channel_url: YouTube channel URL
            updates: Dict of fields to update
        """
        try:
            doc_id = self._sanitize_doc_id(channel_url)
            updates['updated_at'] = firestore.SERVER_TIMESTAMP

            self.collection.document(doc_id).update(updates)
            logger.info(f"Updated category for channel: {channel_url}")

        except Exception as error:
            logger.error(f"Error updating category: {error}")
            raise

    def delete_category(self, channel_url):
        """
        Delete a cached category (useful for re-analysis)

        Args:
            channel_url: YouTube channel URL
        """
        try:
            doc_id = self._sanitize_doc_id(channel_url)
            self.collection.document(doc_id).delete()
            logger.info(f"Deleted category for channel: {channel_url}")

        except Exception as error:
            logger.error(f"Error deleting category: {error}")
            raise

    def get_stats(self):
        """
        Get cache performance statistics

        Returns:
            dict: Cache hit/miss statistics
        """
        total = self.cache_hits + self.cache_misses
        hit_rate = (self.cache_hits / total * 100) if total > 0 else 0

        return {
            'cache_hits': self.cache_hits,
            'cache_misses': self.cache_misses,
            'total_queries': total,
            'hit_rate_percent': round(hit_rate, 2)
        }

    def _sanitize_doc_id(self, channel_url):
        """
        Convert channel URL to valid Firestore document ID

        Args:
            channel_url: YouTube channel URL

        Returns:
            str: Sanitized document ID
        """
        # Remove invalid characters and limit length
        doc_id = channel_url.replace('/', '_').replace(':', '_').replace('?', '_')
        doc_id = doc_id.replace('&', '_').replace('#', '_').replace('.', '_')

        # Firestore doc IDs have a max length of 1500 bytes
        if len(doc_id) > 1000:
            # Use hash for very long URLs
            import hashlib
            doc_id = hashlib.sha256(channel_url.encode()).hexdigest()

        return doc_id

    def query_children_channels(self, limit=1000):
        """
        Query all channels flagged as children's content

        Args:
            limit: Maximum number of results

        Returns:
            list: List of channel documents
        """
        try:
            docs = self.collection.where(
                'is_children_content', '==', True
            ).limit(limit).stream()

            results = [doc.to_dict() for doc in docs]
            logger.info(f"Found {len(results)} children's content channels")
            return results

        except Exception as error:
            logger.error(f"Error querying children's channels: {error}")
            return []

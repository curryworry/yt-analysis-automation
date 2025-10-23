#!/usr/bin/env python3
"""
Clear Firestore cache to remove bad categorization data
Run this after a failed categorization to reset the cache
"""

import os
from google.cloud import firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def clear_firestore_cache():
    """Delete all documents from the channel_categories collection"""

    project_id = os.getenv('GCP_PROJECT_ID', 'yt-channel-analysis-475221')
    collection_name = os.getenv('FIRESTORE_COLLECTION', 'channel_categories')

    print(f"Connecting to Firestore project: {project_id}")
    print(f"Collection: {collection_name}")

    db = firestore.Client(project=project_id)
    collection_ref = db.collection(collection_name)

    # Get all documents
    docs = collection_ref.stream()

    deleted_count = 0
    batch = db.batch()
    batch_count = 0

    print("\nDeleting documents...")

    for doc in docs:
        batch.delete(doc.reference)
        batch_count += 1
        deleted_count += 1

        # Firestore batch limit is 500
        if batch_count >= 500:
            batch.commit()
            print(f"  Deleted {deleted_count} documents so far...")
            batch = db.batch()
            batch_count = 0

    # Commit remaining
    if batch_count > 0:
        batch.commit()

    print(f"\n✓ Successfully deleted {deleted_count} documents from Firestore")
    print("Cache cleared! Next run will re-analyze all channels.")

if __name__ == '__main__':
    response = input("⚠️  This will delete ALL cached channel categorizations. Continue? (yes/no): ")

    if response.lower() == 'yes':
        clear_firestore_cache()
    else:
        print("Cancelled.")

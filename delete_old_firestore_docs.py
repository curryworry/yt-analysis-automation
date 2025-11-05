#!/usr/bin/env python3
"""
Delete Firestore documents with created_at before October 28th, 2025
"""

import os
from datetime import datetime, timezone
from google.cloud import firestore
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def delete_old_documents():
    """Delete documents with created_at before October 28th, 2025"""

    project_id = os.getenv('GCP_PROJECT_ID', 'yt-channel-analysis-475221')
    collection_name = os.getenv('FIRESTORE_COLLECTION', 'channel_categories')

    # October 28, 2025 at 00:00:00 UTC (timezone-aware)
    cutoff_date = datetime(2025, 10, 28, 0, 0, 0, tzinfo=timezone.utc)

    print(f"Connecting to Firestore project: {project_id}")
    print(f"Collection: {collection_name}")
    print(f"Cutoff date: {cutoff_date.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"Will delete documents with created_at < {cutoff_date.isoformat()}\n")

    db = firestore.Client(project=project_id)
    collection_ref = db.collection(collection_name)

    # Query for documents with created_at before October 28th
    query = collection_ref.where('created_at', '<', cutoff_date)
    docs = query.stream()

    deleted_count = 0
    skipped_count = 0
    batch = db.batch()
    batch_count = 0

    print("Processing documents...")

    for doc in docs:
        doc_data = doc.to_dict()
        created_at = doc_data.get('created_at')

        # Double-check the date (safety check)
        if created_at and created_at < cutoff_date:
            batch.delete(doc.reference)
            batch_count += 1
            deleted_count += 1

            # Show sample of what's being deleted
            if deleted_count <= 5:
                channel_name = doc_data.get('channel_name', 'Unknown')
                print(f"  Deleting: {channel_name} (created: {created_at.strftime('%Y-%m-%d %H:%M:%S')})")

            # Firestore batch limit is 500
            if batch_count >= 500:
                batch.commit()
                print(f"  Deleted {deleted_count} documents so far...")
                batch = db.batch()
                batch_count = 0
        else:
            skipped_count += 1

    # Commit remaining
    if batch_count > 0:
        batch.commit()

    print(f"\n✓ Successfully deleted {deleted_count} documents")
    print(f"  Kept {skipped_count} documents (created_at >= October 28th)")

    # Show count of remaining documents
    remaining_docs = collection_ref.stream()
    remaining_count = sum(1 for _ in remaining_docs)
    print(f"  Total documents remaining in collection: {remaining_count}")

if __name__ == '__main__':
    print("⚠️  This will delete all documents with created_at before October 28th, 2025")
    response = input("Continue? (yes/no): ")

    if response.lower() == 'yes':
        delete_old_documents()
    else:
        print("Cancelled.")

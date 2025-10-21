import os
import logging
from google.cloud import storage
from datetime import timedelta

logger = logging.getLogger(__name__)

class GCSService:
    """Service for interacting with Google Cloud Storage."""

    def __init__(self, bucket_name):
        """
        Initialize GCS service.

        Args:
            bucket_name: Name of the GCS bucket
        """
        self.bucket_name = bucket_name
        self.client = storage.Client()
        self.bucket = self.client.bucket(bucket_name)
        logger.info(f"Initialized GCS service for bucket: {bucket_name}")

    def upload_file(self, local_file_path, destination_blob_name):
        """
        Upload a file to GCS.

        Args:
            local_file_path: Path to the local file
            destination_blob_name: Name of the blob in GCS (path in bucket)

        Returns:
            str: GCS URI (gs://bucket/path)
        """
        try:
            blob = self.bucket.blob(destination_blob_name)
            blob.upload_from_filename(local_file_path)

            gcs_uri = f"gs://{self.bucket_name}/{destination_blob_name}"
            logger.info(f"Uploaded {local_file_path} to {gcs_uri}")
            return gcs_uri

        except Exception as e:
            logger.error(f"Failed to upload {local_file_path}: {str(e)}")
            raise

    def get_signed_url(self, blob_name, expiration_hours=168):
        """
        Generate a signed URL for downloading a blob.

        Args:
            blob_name: Name of the blob in GCS
            expiration_hours: How long the URL should be valid (default: 168 hours = 7 days)

        Returns:
            str: Signed URL for downloading the file
        """
        try:
            blob = self.bucket.blob(blob_name)

            # Generate signed URL that expires in specified hours
            url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=expiration_hours),
                method="GET"
            )

            logger.info(f"Generated signed URL for {blob_name} (expires in {expiration_hours} hours)")
            return url

        except Exception as e:
            logger.error(f"Failed to generate signed URL for {blob_name}: {str(e)}")
            raise

    def upload_and_get_url(self, local_file_path, destination_blob_name, expiration_hours=168):
        """
        Upload a file and return a signed download URL.

        Args:
            local_file_path: Path to the local file
            destination_blob_name: Name of the blob in GCS (path in bucket)
            expiration_hours: How long the URL should be valid (default: 168 hours = 7 days)

        Returns:
            tuple: (gcs_uri, signed_url)
        """
        gcs_uri = self.upload_file(local_file_path, destination_blob_name)
        signed_url = self.get_signed_url(destination_blob_name, expiration_hours)
        return gcs_uri, signed_url

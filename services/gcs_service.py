import os
import logging
from google.cloud import storage
from datetime import timedelta
import datetime as dt

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
        Generate a signed URL for downloading the blob.
        Uses IAM-based signing for Cloud Functions (no private key needed).

        Args:
            blob_name: Name of the blob in GCS
            expiration_hours: How many hours the URL should be valid (default: 168 = 7 days)

        Returns:
            str: Signed URL for downloading the file
        """
        try:
            import google.auth
            from google.auth.transport import requests as google_requests
            from google.auth import impersonated_credentials
            import google.auth.credentials

            blob = self.bucket.blob(blob_name)

            # Get default credentials
            credentials, project = google.auth.default()

            # Get service account email from metadata
            import requests
            try:
                response = requests.get(
                    'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email',
                    headers={'Metadata-Flavor': 'Google'},
                    timeout=5
                )
                service_account_email = response.text.strip()
                logger.info(f"Using service account for signing: {service_account_email}")
            except Exception as e:
                logger.error(f"Could not get service account email: {e}")
                raise

            # Create impersonated credentials that use IAM signBlob
            # This allows signing without having the private key
            signing_credentials = impersonated_credentials.Credentials(
                source_credentials=credentials,
                target_principal=service_account_email,
                target_scopes=['https://www.googleapis.com/auth/cloud-platform'],
                delegates=[],
                lifetime=3600  # Token lifetime
            )

            # Generate signed URL with impersonated credentials
            signed_url = blob.generate_signed_url(
                version="v4",
                expiration=timedelta(hours=expiration_hours),
                method="GET",
                credentials=signing_credentials
            )

            logger.info(f"Generated signed URL for {blob_name} (expires in {expiration_hours} hours)")
            return signed_url

        except Exception as e:
            logger.error(f"Failed to generate signed URL: {str(e)}")
            logger.error("Make sure the service account has 'roles/iam.serviceAccountTokenCreator' role on itself")
            raise

    def upload_and_get_url(self, local_file_path, destination_blob_name, expiration_hours=168):
        """
        Upload a file and return a signed download URL.

        Args:
            local_file_path: Path to the local file
            destination_blob_name: Name of the blob in GCS (path in bucket)
            expiration_hours: How many hours the URL should be valid (default: 168 = 7 days)

        Returns:
            tuple: (gcs_uri, signed_url)
        """
        gcs_uri = self.upload_file(local_file_path, destination_blob_name)
        signed_url = self.get_signed_url(destination_blob_name, expiration_hours)
        return gcs_uri, signed_url

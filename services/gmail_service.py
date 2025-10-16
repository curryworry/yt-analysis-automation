"""
Gmail Service Module
Handles email retrieval and attachment downloads
"""

import os
import base64
import zipfile
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import logging

logger = logging.getLogger(__name__)


class GmailService:
    def __init__(self, credentials_path, token_path):
        """
        Initialize Gmail service with OAuth credentials

        Args:
            credentials_path: Path to OAuth credentials.json
            token_path: Path to gmail_token.json
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.service = None

    def authenticate(self):
        """Authenticate and create Gmail API service"""
        try:
            import json

            # Handle both file paths and JSON strings (from secrets)
            if self.token_path and os.path.exists(self.token_path):
                # Local file path
                creds = Credentials.from_authorized_user_file(
                    self.token_path,
                    ['https://www.googleapis.com/auth/gmail.readonly',
                     'https://www.googleapis.com/auth/gmail.send']
                )
            else:
                # Environment variable with JSON string
                token_json = os.getenv('GMAIL_TOKEN')
                if token_json:
                    token_info = json.loads(token_json)
                    creds = Credentials.from_authorized_user_info(
                        token_info,
                        ['https://www.googleapis.com/auth/gmail.readonly',
                         'https://www.googleapis.com/auth/gmail.send']
                    )
                else:
                    raise ValueError("No Gmail token found in file or environment")

            self.service = build('gmail', 'v1', credentials=creds)
            logger.info("Gmail authentication successful")
            return True

        except Exception as e:
            logger.error(f"Gmail authentication failed: {str(e)}")
            raise

    def find_latest_dv360_email(self, sender_email, subject_filter, days_back=7):
        """
        Find the most recent DV360 report email

        Args:
            sender_email: Email address to filter by sender
            subject_filter: Subject line filter text
            days_back: Number of days to search back

        Returns:
            Message ID of the latest matching email, or None
        """
        try:
            # Calculate date for search query
            date_filter = (datetime.now() - timedelta(days=days_back)).strftime('%Y/%m/%d')

            # Build search query
            query = f'from:{sender_email} subject:"{subject_filter}" after:{date_filter} has:attachment'

            logger.info(f"Searching for emails with query: {query}")

            # Search for messages
            results = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=1
            ).execute()

            messages = results.get('messages', [])

            if not messages:
                logger.warning("No matching emails found")
                return None

            message_id = messages[0]['id']
            logger.info(f"Found email with ID: {message_id}")
            return message_id

        except HttpError as error:
            logger.error(f"Error searching for emails: {error}")
            raise

    def download_zip_attachment(self, message_id, download_path):
        """
        Download zip attachment from email

        Args:
            message_id: Gmail message ID
            download_path: Path to save the zip file

        Returns:
            Path to downloaded zip file, or None
        """
        try:
            # Get message details
            message = self.service.users().messages().get(
                userId='me',
                id=message_id
            ).execute()

            # Find zip attachment
            zip_attachment = None
            attachment_id = None
            filename = None

            # Check message parts for attachments
            parts = message.get('payload', {}).get('parts', [])

            for part in parts:
                if part.get('filename', '').endswith('.zip'):
                    attachment_id = part['body'].get('attachmentId')
                    filename = part['filename']
                    break

            # Also check nested parts (for multipart messages)
            if not attachment_id:
                for part in parts:
                    if 'parts' in part:
                        for subpart in part['parts']:
                            if subpart.get('filename', '').endswith('.zip'):
                                attachment_id = subpart['body'].get('attachmentId')
                                filename = subpart['filename']
                                break

            if not attachment_id:
                logger.error("No zip attachment found in email")
                return None

            logger.info(f"Found zip attachment: {filename}")

            # Download attachment
            attachment = self.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()

            # Decode and save
            file_data = base64.urlsafe_b64decode(attachment['data'].encode('UTF-8'))

            zip_path = os.path.join(download_path, filename)
            with open(zip_path, 'wb') as f:
                f.write(file_data)

            logger.info(f"Downloaded zip file to: {zip_path}")
            return zip_path

        except HttpError as error:
            logger.error(f"Error downloading attachment: {error}")
            raise

    def extract_csv_from_zip(self, zip_path, extract_path):
        """
        Extract CSV file from zip archive

        Args:
            zip_path: Path to zip file
            extract_path: Directory to extract to

        Returns:
            Path to extracted CSV file, or None
        """
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                # Find CSV file in zip
                csv_files = [f for f in zip_ref.namelist() if f.endswith('.csv')]

                if not csv_files:
                    logger.error("No CSV file found in zip archive")
                    return None

                # Extract the first CSV file
                csv_filename = csv_files[0]
                zip_ref.extract(csv_filename, extract_path)

                csv_path = os.path.join(extract_path, csv_filename)
                logger.info(f"Extracted CSV file to: {csv_path}")

                return csv_path

        except zipfile.BadZipFile as error:
            logger.error(f"Invalid zip file: {error}")
            raise
        except Exception as error:
            logger.error(f"Error extracting CSV: {error}")
            raise

    def send_results_email(self, recipient_email, subject, body, attachment_path):
        """
        Send results email with CSV attachment

        Args:
            recipient_email: Email address to send to
            subject: Email subject
            body: Email body text
            attachment_path: Path to CSV file to attach
        """
        try:
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            from email.mime.base import MIMEBase
            from email import encoders

            # Create message
            message = MIMEMultipart()
            message['To'] = recipient_email
            message['Subject'] = subject

            # Add body
            message.attach(MIMEText(body, 'plain'))

            # Add attachment
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(f.read())

            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename={os.path.basename(attachment_path)}'
            )
            message.attach(part)

            # Send message
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode('utf-8')
            send_message = {'raw': raw_message}

            self.service.users().messages().send(
                userId='me',
                body=send_message
            ).execute()

            logger.info(f"Results email sent to {recipient_email}")

        except Exception as error:
            logger.error(f"Error sending email: {error}")
            raise

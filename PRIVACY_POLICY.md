# Privacy Policy for DV360 YouTube Channel Analyzer

**Last Updated**: November 13, 2025
**Effective Date**: November 13, 2025

## Overview

DV360 YouTube Channel Analyzer is an internal automation tool developed and operated by Acquire Online (acquirenz.com) for the sole purpose of analyzing YouTube channel placements from DV360 advertising reports.

## Application Purpose

This application is designed exclusively for internal business use to:
- Process DV360 placement reports received via email
- Analyze YouTube channel content for brand safety compliance
- Generate categorized channel lists for advertising campaign management
- Automate weekly reporting workflows

## Data Collection and Usage

### Gmail API Access
**What We Access:**
- Emails sent to ashwinacquireonlineemail@gmail.com with the subject "YouTube Placement Check - DV360"
- ZIP file attachments containing DV360 placement reports

**How We Use It:**
- Download and extract CSV reports from email attachments
- Send automated result emails with categorized channel lists

**Data Retention:**
- Email attachments are temporarily stored in Google Cloud Storage during processing
- Temporary files are deleted after analysis is complete
- No email content is permanently stored

### YouTube Data API Access
**What We Access:**
- Public channel metadata (channel name, description, video titles)
- Publicly available channel information only

**How We Use It:**
- Retrieve channel details for content categorization
- Analyze publicly available information to assess brand safety

**Data Retention:**
- Channel metadata is cached in Google Cloud Firestore to avoid redundant API calls
- Only channel URL, name, and categorization results are stored
- No private or personal user data is collected

### OpenAI API Usage
**What We Share:**
- YouTube channel names and descriptions (publicly available data only)
- Channel video titles (publicly available data only)

**How We Use It:**
- Automated content categorization using GPT-4o-mini
- Brand safety assessment based on publicly available content

**Data Retention:**
- OpenAI processes data according to their API data usage policies
- No personal information is shared with OpenAI

## Data Storage

### Google Cloud Firestore
**What We Store:**
- YouTube channel URLs
- Channel names
- Content categorization results (children's content vs. general audience)
- Analysis timestamps
- Impression data from DV360 reports

**Purpose:**
- Cache analysis results to reduce API costs
- Maintain historical records of analyzed channels
- Generate cumulative targeting lists for advertising campaigns

**Security:**
- Data is stored in Google Cloud Platform with enterprise-grade security
- Access is restricted to authorized service accounts only
- All data transmission uses HTTPS encryption

## Third-Party Services

This application integrates with the following services:

1. **Gmail API** (Google)
   - Purpose: Email retrieval and sending
   - Privacy Policy: https://policies.google.com/privacy

2. **YouTube Data API** (Google)
   - Purpose: Retrieving public channel metadata
   - Privacy Policy: https://policies.google.com/privacy

3. **OpenAI API**
   - Purpose: Content categorization
   - Privacy Policy: https://openai.com/policies/privacy-policy

4. **Google Cloud Platform** (Storage, Firestore, Cloud Functions)
   - Purpose: Application hosting and data storage
   - Privacy Policy: https://policies.google.com/privacy

## Data Sharing

- **No data is sold or shared with third parties** for marketing purposes
- Data is only shared with service providers necessary for application functionality (Google Cloud, OpenAI)
- All channel data analyzed is publicly available information
- No personal user data is collected or processed

## User Rights

This application is for internal business use only and does not collect personal information from external users. The application owner (Acquire Online) has the right to:
- Request deletion of all stored data
- Export stored data
- Revoke application access at any time

## Data Retention Policy

- **Email Data**: Temporary files deleted immediately after processing
- **Firestore Cache**: Retained indefinitely for cost optimization (can be cleared on request)
- **Cloud Function Logs**: Retained for 30 days (Google Cloud default)
- **CSV Reports**: Stored in Google Cloud Storage for 90 days

## Security Measures

- API credentials stored in Google Cloud Secret Manager
- Service accounts use principle of least privilege
- HTTPS-only communication
- Regular security updates to dependencies
- OAuth 2.0 authentication for Gmail access

## Compliance

This application:
- Only accesses publicly available YouTube channel information
- Does not collect personal data from end users
- Complies with YouTube API Terms of Service
- Complies with Google API Services User Data Policy
- Uses Gmail API solely for authorized business email automation

## Changes to Privacy Policy

We reserve the right to update this privacy policy. The "Last Updated" date will reflect when changes were made. Continued use of the application constitutes acceptance of any updates.

## Contact Information

For questions, concerns, or requests regarding this privacy policy or data handling:

**Organization**: Acquire Online
**Email**: ashwin@acquirenz.com
**Website**: https://github.com/curryworry/yt-analysis-automation

## Scope of Application

This application is used exclusively by:
- ashwinacquireonlineemail@gmail.com
- ashwin@acquirenz.com
- wtp@acquirenz.com

The application is not available to the general public and does not interact with external users.

## YouTube API Disclosure

This application uses YouTube API Services. By using this application, you are also agreeing to be bound by the YouTube Terms of Service: https://www.youtube.com/t/terms

## Google API Services User Data Policy Compliance

This application's use of information received from Google APIs adheres to [Google API Services User Data Policy](https://developers.google.com/terms/api-services-user-data-policy), including the Limited Use requirements.

---

**Version**: 1.0.0
**Internal Use Only - Acquire Online**

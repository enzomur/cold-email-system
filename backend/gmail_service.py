"""Gmail API service for sending emails and tracking opens."""

import os
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from backend.database import update_email, log_send, get_today_send_count, get_setting

logger = logging.getLogger(__name__)

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
]

TOKEN_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'gmail_token.json')
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'credentials.json')


def get_gmail_service():
    """Get authenticated Gmail API service."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_PATH}. "
                    "Run setup_wizard.py first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8090)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())

    return build('gmail', 'v1', credentials=creds)


def is_gmail_connected() -> bool:
    """Check if Gmail is authenticated."""
    try:
        if not os.path.exists(TOKEN_PATH):
            return False
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token)
    except Exception:
        return False


def send_email(to_email: str, subject: str, body: str,
               email_id: int = None) -> dict:
    """Send an email via Gmail API.

    Args:
        to_email: recipient address
        subject: email subject
        body: plain text body
        email_id: database email ID for tracking

    Returns:
        dict with 'success', 'message_id', 'error'
    """
    # Check daily limit
    daily_limit = int(get_setting('daily_send_limit', '30'))
    today_count = get_today_send_count()
    if today_count >= daily_limit:
        error = f"Daily send limit reached ({daily_limit}). Try again tomorrow."
        if email_id:
            log_send(email_id, gmail_message_id='')
        return {'success': False, 'message_id': '', 'error': error}

    from_email = get_setting('send_from_email', os.getenv('SEND_FROM_EMAIL', ''))

    try:
        service = get_gmail_service()

        message = MIMEMultipart('alternative')
        message['to'] = to_email
        message['from'] = from_email
        message['subject'] = subject

        # Plain text
        message.attach(MIMEText(body, 'plain'))

        # HTML version with basic formatting
        html_body = body.replace('\n', '<br>')
        message.attach(MIMEText(f"<html><body><p>{html_body}</p></body></html>", 'html'))

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        result = service.users().messages().send(
            userId='me', body={'raw': raw}
        ).execute()

        message_id = result.get('id', '')

        # Update database
        if email_id:
            update_email(email_id, {
                'status': 'sent',
                'sent_date': datetime.now().isoformat(),
            })
            log_send(email_id, gmail_message_id=message_id)

        logger.info(f"Email sent to {to_email}: {message_id}")
        return {'success': True, 'message_id': message_id, 'error': ''}

    except FileNotFoundError as e:
        error = str(e)
        logger.error(error)
        return {'success': False, 'message_id': '', 'error': error}
    except Exception as e:
        error = f"Failed to send email: {e}"
        logger.error(error)
        if email_id:
            log_send(email_id, gmail_message_id='')
        return {'success': False, 'message_id': '', 'error': error}


def send_batch(email_records: list[dict]) -> dict:
    """Send a batch of emails with rate limiting.

    Args:
        email_records: list of dicts with 'id', 'lead_email', 'subject', 'body'

    Returns:
        dict with 'sent', 'failed', 'errors'
    """
    import time
    results = {'sent': 0, 'failed': 0, 'errors': []}

    for record in email_records:
        result = send_email(
            to_email=record['lead_email'],
            subject=record['subject'],
            body=record['body'],
            email_id=record['id']
        )

        if result['success']:
            results['sent'] += 1
        else:
            results['failed'] += 1
            results['errors'].append({
                'email_id': record['id'],
                'error': result['error']
            })

            # Stop if daily limit hit
            if 'Daily send limit' in result['error']:
                break

        # Small delay between sends to avoid rate limiting
        time.sleep(1.5)

    return results

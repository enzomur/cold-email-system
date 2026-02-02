"""Google Sheets bidirectional sync for leads."""

import os
import logging
from datetime import datetime

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from backend.database import (
    get_db, insert_lead, get_all_leads_for_export, get_setting, set_setting
)

logger = logging.getLogger(__name__)

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

TOKEN_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'sheets_token.json')
CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'credentials.json')

HEADER_ROW = [
    'ID', 'Business Name', 'Contact Name', 'Email', 'Phone',
    'Address', 'City', 'State', 'Zip', 'Website', 'Trade',
    'Source', 'Rating', 'Reviews', 'License #', 'Status', 'Notes',
    'Website Quality', 'Lead Score', 'Lead Tier'
]


def get_sheets_service():
    """Get authenticated Sheets API service."""
    creds = None

    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_PATH):
                raise FileNotFoundError(
                    f"Credentials not found at {CREDENTIALS_PATH}. "
                    "Run setup_wizard.py first."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=8091)

        os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
        with open(TOKEN_PATH, 'w') as f:
            f.write(creds.to_json())

    return build('sheets', 'v4', credentials=creds)


def is_sheets_connected() -> bool:
    """Check if Sheets is authenticated."""
    try:
        if not os.path.exists(TOKEN_PATH):
            return False
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        return creds.valid or (creds.expired and creds.refresh_token)
    except Exception:
        return False


def _get_or_create_spreadsheet() -> str:
    """Get existing spreadsheet ID or create a new one."""
    sheet_id = get_setting('sheet_id', '')
    if sheet_id:
        return sheet_id

    service = get_sheets_service()
    sheet_name = get_setting('sheet_name', os.getenv('SHEET_NAME', 'Cold Email Outreach'))

    spreadsheet = service.spreadsheets().create(body={
        'properties': {'title': sheet_name},
        'sheets': [{'properties': {'title': 'Leads'}}]
    }).execute()

    sheet_id = spreadsheet['spreadsheetId']
    set_setting('sheet_id', sheet_id)

    # Write header row
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range='Leads!A1',
        valueInputOption='RAW',
        body={'values': [HEADER_ROW]}
    ).execute()

    logger.info(f"Created new spreadsheet: {sheet_id}")
    return sheet_id


def export_leads_to_sheet() -> dict:
    """Export all leads from SQLite to Google Sheets.

    Returns dict with 'success', 'count', 'sheet_url', 'error'.
    """
    try:
        service = get_sheets_service()
        sheet_id = _get_or_create_spreadsheet()
        leads = get_all_leads_for_export()

        rows = [HEADER_ROW]
        for lead in leads:
            rows.append([
                lead.get('id', ''),
                lead.get('business_name', ''),
                lead.get('contact_name', ''),
                lead.get('email', ''),
                lead.get('phone', ''),
                lead.get('address', ''),
                lead.get('city', ''),
                lead.get('state', ''),
                lead.get('zip_code', ''),
                lead.get('website', ''),
                lead.get('trade', ''),
                lead.get('source', ''),
                lead.get('rating', ''),
                lead.get('review_count', ''),
                lead.get('license_number', ''),
                lead.get('status', ''),
                lead.get('notes', ''),
                lead.get('website_quality', ''),
                lead.get('lead_score', ''),
                lead.get('lead_tier', ''),
            ])

        # Clear existing data and write new
        service.spreadsheets().values().clear(
            spreadsheetId=sheet_id, range='Leads!A:T'
        ).execute()

        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range='Leads!A1',
            valueInputOption='RAW',
            body={'values': rows}
        ).execute()

        sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        set_setting('last_sheet_sync', datetime.now().isoformat())

        return {
            'success': True,
            'count': len(leads),
            'sheet_url': sheet_url,
            'error': ''
        }

    except Exception as e:
        logger.error(f"Sheet export failed: {e}")
        return {'success': False, 'count': 0, 'sheet_url': '', 'error': str(e)}


def import_leads_from_sheet() -> dict:
    """Import leads from Google Sheets into SQLite.

    Returns dict with 'success', 'imported', 'error'.
    """
    try:
        service = get_sheets_service()
        sheet_id = get_setting('sheet_id', '')
        if not sheet_id:
            return {'success': False, 'imported': 0, 'error': 'No spreadsheet configured.'}

        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range='Leads!A2:T'
        ).execute()

        rows = result.get('values', [])
        imported = 0

        for row in rows:
            if len(row) < 2:
                continue
            # Pad row to expected length
            row += [''] * (20 - len(row))

            lead = {
                'business_name': row[1],
                'contact_name': row[2],
                'email': row[3],
                'phone': row[4],
                'address': row[5],
                'city': row[6],
                'state': row[7],
                'zip_code': row[8],
                'website': row[9],
                'trade': row[10],
                'source': row[11] or 'Google Sheets',
                'rating': float(row[12]) if row[12] else None,
                'review_count': int(row[13]) if row[13] else None,
                'license_number': row[14],
                'license_type': '',
                'scraped_date': datetime.now().isoformat(),
                'status': row[15] or 'new',
                'notes': row[16],
                'website_quality': row[17] or 'none',
                'lead_score': int(row[18]) if row[18] else 0,
                'lead_tier': row[19] or 'cool',
            }

            if lead['business_name'] and insert_lead(lead) is not None:
                imported += 1

        set_setting('last_sheet_sync', datetime.now().isoformat())
        return {'success': True, 'imported': imported, 'error': ''}

    except Exception as e:
        logger.error(f"Sheet import failed: {e}")
        return {'success': False, 'imported': 0, 'error': str(e)}

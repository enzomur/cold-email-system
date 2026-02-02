"""Email finder: extracts emails from business websites and Hunter.io API."""

import re
import os
import time
import random
import logging
import requests
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)
ua = UserAgent()

MIN_DELAY = 1.5
MAX_DELAY = 3.0

IGNORE_DOMAINS = [
    'example.com', 'sentry.io', 'wixpress.com', 'googleapis.com',
    'w3.org', 'schema.org', 'facebook.com', 'twitter.com',
    'instagram.com', 'youtube.com', 'google.com', 'yelp.com',
    'wordpress.org', 'gravatar.com', 'jquery.com',
]

EMAIL_RE = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def _get_headers():
    return {
        'User-Agent': ua.random,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    }


def _delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def _is_valid_email(email: str) -> bool:
    """Filter out obviously invalid or non-business emails."""
    email = email.lower()
    if any(d in email for d in IGNORE_DOMAINS):
        return False
    if email.endswith(('.png', '.jpg', '.gif', '.svg', '.css', '.js')):
        return False
    if len(email) > 80:
        return False
    return True


def extract_emails_from_website(url: str) -> list[str]:
    """Scrape a website for email addresses."""
    if not url:
        return []

    # Ensure URL has scheme
    if not url.startswith('http'):
        url = 'https://' + url

    emails = set()
    pages_to_check = [url]

    # Also check common contact pages
    base = url.rstrip('/')
    for path in ['/contact', '/contact-us', '/about', '/about-us']:
        pages_to_check.append(base + path)

    for page_url in pages_to_check:
        try:
            resp = requests.get(page_url, headers=_get_headers(), timeout=10,
                                allow_redirects=True)
            if resp.status_code == 200:
                found = EMAIL_RE.findall(resp.text)
                for e in found:
                    if _is_valid_email(e):
                        emails.add(e.lower())
            _delay()
        except Exception:
            continue

    return list(emails)


def hunter_find_email(domain: str, api_key: str = None) -> dict:
    """Use Hunter.io API to find emails for a domain.

    Returns dict with 'emails' list and 'webmail' bool.
    """
    if not api_key:
        api_key = os.getenv('HUNTER_API_KEY', '')
    if not api_key or api_key == 'your_hunter_api_key_here':
        return {'emails': [], 'webmail': False}

    try:
        resp = requests.get(
            'https://api.hunter.io/v2/domain-search',
            params={'domain': domain, 'api_key': api_key},
            timeout=10
        )
        if resp.status_code == 200:
            data = resp.json().get('data', {})
            emails = []
            for e in data.get('emails', []):
                emails.append({
                    'email': e.get('value', ''),
                    'type': e.get('type', ''),
                    'confidence': e.get('confidence', 0),
                    'first_name': e.get('first_name', ''),
                    'last_name': e.get('last_name', ''),
                })
            return {
                'emails': emails,
                'webmail': data.get('webmail', False),
            }
        elif resp.status_code == 429:
            logger.warning("Hunter.io rate limit reached")
        else:
            logger.warning(f"Hunter.io returned {resp.status_code}")
    except Exception as e:
        logger.error(f"Hunter.io request failed: {e}")

    return {'emails': [], 'webmail': False}


def find_email_for_lead(lead: dict, hunter_api_key: str = None) -> str:
    """Try to find an email for a lead. Returns best email or empty string."""
    # First try website scraping
    if lead.get('website'):
        emails = extract_emails_from_website(lead['website'])
        if emails:
            return emails[0]

        # Try Hunter.io if we have a real domain
        domain = lead['website'].replace('https://', '').replace('http://', '').split('/')[0]
        if '.' in domain and not domain.endswith('.yelp.com'):
            result = hunter_find_email(domain, hunter_api_key)
            if result['emails']:
                # Prefer generic emails (info@, contact@) for cold outreach
                generic = [e for e in result['emails'] if e['type'] == 'generic']
                if generic:
                    return generic[0]['email']
                return result['emails'][0]['email']

    return ''


def enrich_leads_with_emails(leads: list[dict], hunter_api_key: str = None,
                             progress_callback=None) -> int:
    """Find emails for leads that don't have one. Returns count of emails found."""
    found = 0
    to_process = [l for l in leads if not l.get('email') and l.get('website')]

    for i, lead in enumerate(to_process):
        if progress_callback:
            progress_callback(i, len(to_process),
                              f"Finding email for {lead.get('business_name', '?')}...")

        email = find_email_for_lead(lead, hunter_api_key)
        if email:
            lead['email'] = email
            found += 1

        _delay()

    if progress_callback:
        progress_callback(len(to_process), len(to_process),
                          f"Done. Found {found} emails.")
    return found

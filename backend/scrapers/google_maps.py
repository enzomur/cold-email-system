"""Google Maps scraper for tradesperson leads.

Uses requests + BeautifulSoup to scrape Google Maps search results.
Includes rate limiting and user-agent rotation.
"""

import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote_plus
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)
ua = UserAgent()

# Rate limiting config
MIN_DELAY = 2.0
MAX_DELAY = 4.0


def _get_headers():
    return {
        'User-Agent': ua.random,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Referer': 'https://www.google.com/',
    }


def _delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def _extract_email_from_website(url: str) -> str:
    """Try to find an email address on a business website."""
    if not url:
        return ''
    try:
        resp = requests.get(url, headers=_get_headers(), timeout=10)
        emails = re.findall(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', resp.text)
        # Filter out common non-business emails
        ignore = ['example.com', 'sentry.io', 'wixpress.com', 'googleapis.com']
        emails = [e for e in emails if not any(d in e for d in ignore)]
        return emails[0] if emails else ''
    except Exception:
        return ''


def scrape_google_maps(trade: str, location: str, max_results: int = 20,
                       progress_callback=None) -> list[dict]:
    """
    Scrape Google Maps search results for a trade in a location.

    NOTE: Google Maps is heavily JS-rendered. This scraper uses Google search
    with the 'maps' site filter as a fallback approach. For production use,
    consider using Selenium with the actual Maps interface.

    Args:
        trade: e.g. "electrician", "plumber"
        location: e.g. "Austin, TX" or "90210"
        max_results: maximum leads to return
        progress_callback: optional function(current, total, message)

    Returns:
        List of lead dicts
    """
    leads = []
    query = f"{trade} in {location}"
    search_url = f"https://www.google.com/search?q={quote_plus(query)}&num=20&tbm=lcl"

    if progress_callback:
        progress_callback(0, max_results, f"Searching Google for '{query}'...")

    try:
        resp = requests.get(search_url, headers=_get_headers(), timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # Parse local results (div class patterns vary, try multiple selectors)
        result_blocks = soup.select('div.VkpGBb') or soup.select('div.rllt__details')

        for i, block in enumerate(result_blocks[:max_results]):
            try:
                name_el = block.select_one('div.dbg0pd, span.OSrXXb, div.BNeawe')
                name = name_el.get_text(strip=True) if name_el else ''
                if not name:
                    name = block.get_text(strip=True)[:80]

                # Extract rating
                rating_el = block.select_one('span.BTtC6e, span.yi40Hd')
                rating = None
                if rating_el:
                    try:
                        rating = float(rating_el.get_text(strip=True))
                    except ValueError:
                        pass

                # Extract review count
                review_count = None
                review_el = block.select_one('span.RDApEe, span.dv1nJ')
                if review_el:
                    nums = re.findall(r'[\d,]+', review_el.get_text())
                    if nums:
                        review_count = int(nums[0].replace(',', ''))

                # Extract address text
                addr_el = block.select_one('div.rllt__wrapped, span.rllt__details')
                address_text = addr_el.get_text(' ', strip=True) if addr_el else ''

                # Extract phone from text
                full_text = block.get_text(' ')
                phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', full_text)
                phone = phone_match.group() if phone_match else ''

                # Try to get website link
                website = ''
                link_el = block.find_parent('div').select_one('a[href*="http"]') if block.find_parent('div') else None
                if link_el:
                    href = link_el.get('href', '')
                    if 'google' not in href:
                        website = href

                lead = {
                    'business_name': name.split('·')[0].strip() if name else '',
                    'contact_name': '',
                    'email': '',
                    'phone': phone,
                    'address': address_text,
                    'city': location.split(',')[0].strip() if ',' in location else location,
                    'state': location.split(',')[1].strip() if ',' in location else '',
                    'zip_code': location if location.isdigit() else '',
                    'website': website,
                    'trade': trade,
                    'source': 'Google Maps',
                    'rating': rating,
                    'review_count': review_count,
                    'license_number': '',
                    'license_type': '',
                    'scraped_date': '',
                    'status': 'new',
                    'notes': '',
                }

                if lead['business_name']:
                    leads.append(lead)
                    if progress_callback:
                        progress_callback(len(leads), max_results,
                                          f"Found: {lead['business_name']}")

            except Exception as e:
                logger.warning(f"Error parsing Google Maps result: {e}")
                continue

            _delay()

    except requests.RequestException as e:
        logger.error(f"Google Maps request failed: {e}")

    # Try to find emails from websites
    for lead in leads:
        if not lead['email'] and lead['website']:
            lead['email'] = _extract_email_from_website(lead['website'])
            _delay()

    if progress_callback:
        progress_callback(len(leads), len(leads), f"Done. Found {len(leads)} leads.")

    return leads

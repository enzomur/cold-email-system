"""Yelp scraper for tradesperson leads.

Uses requests + BeautifulSoup to scrape Yelp search results.
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

MIN_DELAY = 2.0
MAX_DELAY = 4.0

TRADE_TO_YELP_CATEGORY = {
    'electrician': 'electricians',
    'plumber': 'plumbing',
    'hvac': 'hvac',
    'hvac contractor': 'hvac',
    'handyman': 'handyman',
    'roofer': 'roofing',
    'general contractor': 'contractors',
}


def _get_headers():
    return {
        'User-Agent': ua.random,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    }


def _delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


def scrape_yelp(trade: str, location: str, max_results: int = 20,
                progress_callback=None) -> list[dict]:
    """
    Scrape Yelp search results for a trade in a location.

    Args:
        trade: e.g. "electrician", "plumber"
        location: e.g. "Austin, TX"
        max_results: maximum leads to return
        progress_callback: optional function(current, total, message)

    Returns:
        List of lead dicts
    """
    leads = []
    category = TRADE_TO_YELP_CATEGORY.get(trade.lower(), trade.lower())
    base_url = "https://www.yelp.com/search"

    pages_needed = (max_results + 9) // 10  # Yelp shows ~10 per page

    if progress_callback:
        progress_callback(0, max_results, f"Searching Yelp for '{trade}' in {location}...")

    for page in range(pages_needed):
        if len(leads) >= max_results:
            break

        params = {
            'find_desc': category,
            'find_loc': location,
            'start': page * 10,
        }

        try:
            resp = requests.get(base_url, params=params, headers=_get_headers(), timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'lxml')

            # Yelp result containers
            results = soup.select('[data-testid="serp-ia-card"]') or \
                      soup.select('div.container__09f24__FeTO6') or \
                      soup.select('li.border-color--default__09f24__NPAKY')

            # Fallback: look for business name links
            if not results:
                results = soup.select('a[href*="/biz/"]')
                results = list({r.get('href', '').split('?')[0]: r for r in results
                               if '/biz/' in r.get('href', '') and r.get_text(strip=True)}.values())

            for item in results:
                if len(leads) >= max_results:
                    break

                try:
                    # Business name
                    name_el = item.select_one('a[href*="/biz/"] span, a[href*="/biz/"]')
                    name = name_el.get_text(strip=True) if name_el else ''
                    # Clean numbered prefix like "1. " from name
                    name = re.sub(r'^\d+\.\s*', '', name)

                    if not name or len(name) < 2:
                        continue

                    # Biz page URL for more details
                    biz_link = item.select_one('a[href*="/biz/"]')
                    biz_url = ''
                    if biz_link:
                        href = biz_link.get('href', '')
                        if href.startswith('/'):
                            biz_url = f"https://www.yelp.com{href.split('?')[0]}"

                    # Rating
                    rating = None
                    rating_el = item.select_one('[aria-label*="star"]')
                    if rating_el:
                        match = re.search(r'([\d.]+)\s*star', rating_el.get('aria-label', ''))
                        if match:
                            rating = float(match.group(1))

                    # Review count
                    review_count = None
                    review_el = item.select_one('span.reviewCount__09f24__yzIwM')
                    if not review_el:
                        text = item.get_text()
                        rev_match = re.search(r'(\d+)\s*reviews?', text)
                        if rev_match:
                            review_count = int(rev_match.group(1))

                    # Phone
                    full_text = item.get_text(' ')
                    phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', full_text)
                    phone = phone_match.group() if phone_match else ''

                    # Location text
                    loc_parts = location.split(',')
                    city = loc_parts[0].strip() if loc_parts else ''
                    state = loc_parts[1].strip() if len(loc_parts) > 1 else ''

                    lead = {
                        'business_name': name,
                        'contact_name': '',
                        'email': '',
                        'phone': phone,
                        'address': '',
                        'city': city,
                        'state': state,
                        'zip_code': '',
                        'website': biz_url,
                        'trade': trade,
                        'source': 'Yelp',
                        'rating': rating,
                        'review_count': review_count,
                        'license_number': '',
                        'license_type': '',
                        'scraped_date': '',
                        'status': 'new',
                        'notes': '',
                    }

                    # Dedup by name
                    if not any(l['business_name'] == name for l in leads):
                        leads.append(lead)
                        if progress_callback:
                            progress_callback(len(leads), max_results,
                                              f"Found: {name}")

                except Exception as e:
                    logger.warning(f"Error parsing Yelp result: {e}")
                    continue

        except requests.RequestException as e:
            logger.error(f"Yelp request failed (page {page}): {e}")
            break

        _delay()

    if progress_callback:
        progress_callback(len(leads), len(leads), f"Done. Found {len(leads)} leads from Yelp.")

    return leads

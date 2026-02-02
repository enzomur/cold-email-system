"""State contractor license database scrapers.

Scrapes publicly available contractor license databases for:
- California (CSLB)
- Texas (TDLR)
- Florida (DBPR)

Includes rate limiting and user-agent rotation.
"""

import re
import time
import random
import logging
import requests
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)
ua = UserAgent()

MIN_DELAY = 2.5
MAX_DELAY = 4.5

TRADE_KEYWORDS = {
    'electrician': ['electric', 'electrical', 'C-10'],
    'plumber': ['plumb', 'plumbing', 'C-36'],
    'hvac': ['hvac', 'heating', 'air conditioning', 'C-20'],
    'hvac contractor': ['hvac', 'heating', 'air conditioning', 'C-20'],
    'handyman': ['handyman', 'general', 'maintenance'],
    'roofer': ['roof', 'roofing', 'C-39'],
    'general contractor': ['general', 'building', 'B-General'],
}


def _get_headers():
    return {
        'User-Agent': ua.random,
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept': 'text/html,application/xhtml+xml',
    }


def _delay():
    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))


# --- California CSLB ---

def scrape_california_cslb(trade: str, city: str = '', max_results: int = 20,
                           progress_callback=None) -> list[dict]:
    """
    Scrape California Contractors State License Board.
    https://www.cslb.ca.gov/onlineservices/checklicenseII/checklicense.aspx

    This uses the CSLB public search which requires specific form submissions.
    As a fallback, we scrape the public license lookup results.
    """
    leads = []
    keywords = TRADE_KEYWORDS.get(trade.lower(), [trade])

    if progress_callback:
        progress_callback(0, max_results, f"Searching CA CSLB for {trade}...")

    # CSLB uses ASP.NET form posts — we use their search API endpoint
    search_url = "https://www.cslb.ca.gov/OnlineServices/CheckLicenseII/CheckLicense.aspx"

    try:
        session = requests.Session()
        session.headers.update(_get_headers())

        # Get the page to extract form tokens
        resp = session.get(search_url, timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')

        # Extract ASP.NET form fields
        viewstate = soup.select_one('#__VIEWSTATE')
        if not viewstate:
            logger.warning("Could not find CSLB form tokens. Site may have changed.")
            if progress_callback:
                progress_callback(0, 0, "CSLB scrape unavailable — site structure changed.")
            return leads

        form_data = {
            '__VIEWSTATE': viewstate.get('value', ''),
            '__VIEWSTATEGENERATOR': (soup.select_one('#__VIEWSTATEGENERATOR') or {}).get('value', ''),
            '__EVENTVALIDATION': (soup.select_one('#__EVENTVALIDATION') or {}).get('value', ''),
            'ctl00$MainContent$txtLicenseNumber': '',
            'ctl00$MainContent$txtBusinessName': keywords[0] if keywords else trade,
            'ctl00$MainContent$txtCity': city,
            'ctl00$MainContent$btnSearch': 'Search',
        }

        _delay()
        resp = session.post(search_url, data=form_data, timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')

        # Parse results table
        rows = soup.select('table.datagrid tr, #MainContent_gvSearchResults tr')
        for row in rows[1:max_results + 1]:  # Skip header row
            cells = row.select('td')
            if len(cells) < 4:
                continue

            try:
                license_num = cells[0].get_text(strip=True)
                biz_name = cells[1].get_text(strip=True)
                lic_type = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                address_text = cells[3].get_text(strip=True) if len(cells) > 3 else ''

                # Parse city from address
                parsed_city = city
                if ',' in address_text:
                    parts = address_text.rsplit(',', 1)
                    parsed_city = parts[0].strip().split('\n')[-1].strip()

                lead = {
                    'business_name': biz_name,
                    'contact_name': '',
                    'email': '',
                    'phone': '',
                    'address': address_text,
                    'city': parsed_city or city,
                    'state': 'CA',
                    'zip_code': '',
                    'website': '',
                    'trade': trade,
                    'source': 'CA CSLB',
                    'rating': None,
                    'review_count': None,
                    'license_number': license_num,
                    'license_type': lic_type,
                    'scraped_date': '',
                    'status': 'new',
                    'notes': '',
                }

                if biz_name and not any(l['business_name'] == biz_name for l in leads):
                    leads.append(lead)
                    if progress_callback:
                        progress_callback(len(leads), max_results, f"Found: {biz_name}")

            except Exception as e:
                logger.warning(f"Error parsing CSLB row: {e}")
                continue

    except requests.RequestException as e:
        logger.error(f"CSLB request failed: {e}")

    if progress_callback:
        progress_callback(len(leads), len(leads),
                          f"Done. Found {len(leads)} CA CSLB leads.")
    return leads


# --- Texas TDLR ---

def scrape_texas_tdlr(trade: str, city: str = '', max_results: int = 20,
                      progress_callback=None) -> list[dict]:
    """
    Scrape Texas Department of Licensing and Regulation.
    https://www.tdlr.texas.gov/LicenseSearch/
    """
    leads = []
    if progress_callback:
        progress_callback(0, max_results, f"Searching TX TDLR for {trade}...")

    search_url = "https://www.tdlr.texas.gov/LicenseSearch/SearchResults.aspx"
    keywords = TRADE_KEYWORDS.get(trade.lower(), [trade])

    try:
        session = requests.Session()
        session.headers.update(_get_headers())

        resp = session.get("https://www.tdlr.texas.gov/LicenseSearch/", timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')

        viewstate = soup.select_one('#__VIEWSTATE')
        if not viewstate:
            logger.warning("Could not find TDLR form tokens.")
            if progress_callback:
                progress_callback(0, 0, "TX TDLR scrape unavailable.")
            return leads

        form_data = {
            '__VIEWSTATE': viewstate.get('value', ''),
            'ctl00$MainContent$txtName': keywords[0],
            'ctl00$MainContent$txtCity': city,
            'ctl00$MainContent$btnSearch': 'Search',
        }

        _delay()
        resp = session.post(search_url, data=form_data, timeout=15)
        soup = BeautifulSoup(resp.text, 'lxml')

        rows = soup.select('table tr.gridRow, table tr.gridAltRow')
        for row in rows[:max_results]:
            cells = row.select('td')
            if len(cells) < 3:
                continue

            try:
                name = cells[0].get_text(strip=True)
                lic_num = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                lic_type = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                loc = cells[3].get_text(strip=True) if len(cells) > 3 else city

                lead = {
                    'business_name': name,
                    'contact_name': name,
                    'email': '',
                    'phone': '',
                    'address': '',
                    'city': loc or city,
                    'state': 'TX',
                    'zip_code': '',
                    'website': '',
                    'trade': trade,
                    'source': 'TX TDLR',
                    'rating': None,
                    'review_count': None,
                    'license_number': lic_num,
                    'license_type': lic_type,
                    'scraped_date': '',
                    'status': 'new',
                    'notes': '',
                }

                if name and not any(l['business_name'] == name for l in leads):
                    leads.append(lead)
                    if progress_callback:
                        progress_callback(len(leads), max_results, f"Found: {name}")

            except Exception as e:
                logger.warning(f"Error parsing TDLR row: {e}")
                continue

    except requests.RequestException as e:
        logger.error(f"TDLR request failed: {e}")

    if progress_callback:
        progress_callback(len(leads), len(leads),
                          f"Done. Found {len(leads)} TX TDLR leads.")
    return leads


# --- Florida DBPR ---

def scrape_florida_dbpr(trade: str, city: str = '', max_results: int = 20,
                        progress_callback=None) -> list[dict]:
    """
    Scrape Florida Department of Business and Professional Regulation.
    https://www.myfloridalicense.com/wl11.asp
    """
    leads = []
    if progress_callback:
        progress_callback(0, max_results, f"Searching FL DBPR for {trade}...")

    keywords = TRADE_KEYWORDS.get(trade.lower(), [trade])

    try:
        session = requests.Session()
        session.headers.update(_get_headers())

        search_url = "https://www.myfloridalicense.com/wl11.asp"
        resp = session.get(search_url, timeout=15)

        form_data = {
            'SID': '',
            'hession': '',
            'bession': '',
            'Board': 'Construction',
            'LastName': keywords[0],
            'City': city,
            'State': 'FL',
            'Submit': 'Search',
        }

        _delay()
        resp = session.post(
            "https://www.myfloridalicense.com/wl11.asp",
            data=form_data, timeout=15
        )
        soup = BeautifulSoup(resp.text, 'lxml')

        rows = soup.select('table tr')[1:]  # Skip header
        for row in rows[:max_results]:
            cells = row.select('td')
            if len(cells) < 3:
                continue

            try:
                name = cells[0].get_text(strip=True)
                lic_num = cells[1].get_text(strip=True) if len(cells) > 1 else ''
                lic_type = cells[2].get_text(strip=True) if len(cells) > 2 else ''
                loc = cells[3].get_text(strip=True) if len(cells) > 3 else city

                lead = {
                    'business_name': name,
                    'contact_name': name,
                    'email': '',
                    'phone': '',
                    'address': '',
                    'city': loc or city,
                    'state': 'FL',
                    'zip_code': '',
                    'website': '',
                    'trade': trade,
                    'source': 'FL DBPR',
                    'rating': None,
                    'review_count': None,
                    'license_number': lic_num,
                    'license_type': lic_type,
                    'scraped_date': '',
                    'status': 'new',
                    'notes': '',
                }

                if name and not any(l['business_name'] == name for l in leads):
                    leads.append(lead)
                    if progress_callback:
                        progress_callback(len(leads), max_results, f"Found: {name}")

            except Exception as e:
                logger.warning(f"Error parsing DBPR row: {e}")
                continue

    except requests.RequestException as e:
        logger.error(f"FL DBPR request failed: {e}")

    if progress_callback:
        progress_callback(len(leads), len(leads),
                          f"Done. Found {len(leads)} FL DBPR leads.")
    return leads


def scrape_license_dbs(trade: str, location: str, states: list[str] | None = None,
                       max_results: int = 20, progress_callback=None) -> list[dict]:
    """
    Dispatch to the correct state scraper(s).

    Args:
        trade: trade category
        location: city name or "city, ST"
        states: list of state abbreviations, or None for all supported
        max_results: per-state max
        progress_callback: optional progress function
    """
    all_leads = []
    city = location.split(',')[0].strip() if ',' in location else location

    supported = {
        'CA': scrape_california_cslb,
        'TX': scrape_texas_tdlr,
        'FL': scrape_florida_dbpr,
    }

    if states is None:
        # Try to detect state from location
        if ',' in location:
            st = location.split(',')[1].strip().upper()[:2]
            states = [st] if st in supported else list(supported.keys())
        else:
            states = list(supported.keys())

    for st in states:
        scraper = supported.get(st.upper())
        if scraper:
            leads = scraper(trade, city, max_results, progress_callback)
            all_leads.extend(leads)

    return all_leads

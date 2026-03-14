"""Lead scoring engine — prioritizes solo operators and micro-businesses."""

import re
import logging
import requests
from datetime import datetime
from fake_useragent import UserAgent

logger = logging.getLogger(__name__)
ua = UserAgent()

SCHEDULING_DOMAINS = [
    'calendly.com', 'acuityscheduling.com', 'squareup.com/appointments',
    'booksy.com', 'setmore.com', 'housecallpro.com', 'jobber.com',
    'servicetitan.com', 'kickserv.com',
]

GATEKEEPER_PHRASES = [
    'contact our office', 'speak with a representative', 'our team will',
    'leave a message', 'front desk', 'receptionist', 'call our main',
    'scheduling department',
]

# Phrases that indicate owner-operated / solo businesses (positive signals)
OWNER_OPERATED_PHRASES = [
    'owner operated', 'owner-operated', 'owner/operator', 'owner and operator',
    'personally', 'i personally', 'i handle', 'i will', 'i am', "i'm the owner",
    'one man', 'one-man', 'solo', 'just me', 'my name is',
]

FAMILY_BUSINESS_PHRASES = [
    'family owned', 'family-owned', 'family business', 'family run',
    'family-run', 'father and son', 'family operated', 'family-operated',
    'husband and wife', 'mom and pop', 'brothers',
]

# Expensive software they might be paying for (good targets to save money)
EXPENSIVE_SOFTWARE = [
    'servicetitan', 'service titan', 'jobber', 'housecall pro', 'housecallpro',
    'fieldedge', 'field edge', 'servicefusion', 'service fusion',
    'successware', 'workiz',
]

# Pain point indicators (manual/chaotic processes)
PAIN_POINT_PHRASES = [
    'call for quote', 'call us for', 'contact us for pricing',
    'estimates available', 'free estimates', 'call to schedule',
]


def check_website_quality(url: str) -> dict:
    """Check website quality indicators. Returns dict with quality info.

    Lightweight check: HTTPS, meta viewport, copyright year.
    Also detects expensive software and owner-operated signals.
    """
    result = {
        'website_quality': 'none',
        'has_booking_system': False,
        'uses_expensive_software': False,
        'is_owner_operated': False,
        'is_family_business': False,
    }

    if not url:
        return result

    if not url.startswith('http'):
        url = 'https://' + url

    try:
        resp = requests.get(url, headers={'User-Agent': ua.random}, timeout=10,
                            allow_redirects=True)
        if resp.status_code != 200:
            result['website_quality'] = 'basic'
            return result

        html = resp.text.lower()
        has_https = resp.url.startswith('https')
        has_viewport = 'name="viewport"' in html or "name='viewport'" in html

        # Check copyright year
        current_year = datetime.now().year
        copyright_match = re.search(r'(?:©|copyright)\s*(\d{4})', html)
        recent_copyright = False
        if copyright_match:
            year = int(copyright_match.group(1))
            recent_copyright = year >= current_year - 1

        # Check for scheduling/booking links
        for domain in SCHEDULING_DOMAINS:
            if domain in html:
                result['has_booking_system'] = True
                break

        # Also check for generic booking indicators
        if not result['has_booking_system']:
            booking_patterns = [
                'book online', 'book now', 'schedule online', 'online booking',
                'book an appointment', 'schedule a service',
            ]
            for pattern in booking_patterns:
                if pattern in html:
                    result['has_booking_system'] = True
                    break

        # Check for expensive software mentions (prime targets for cost savings)
        for software in EXPENSIVE_SOFTWARE:
            if software in html:
                result['uses_expensive_software'] = True
                break

        # Check for owner-operated signals
        for phrase in OWNER_OPERATED_PHRASES:
            if phrase in html:
                result['is_owner_operated'] = True
                break

        # Check for family business signals
        for phrase in FAMILY_BUSINESS_PHRASES:
            if phrase in html:
                result['is_family_business'] = True
                break

        # Determine quality
        modern_signals = sum([has_https, has_viewport, recent_copyright])
        if modern_signals >= 2:
            result['website_quality'] = 'modern'
        else:
            result['website_quality'] = 'basic'

    except Exception as e:
        logger.debug(f"Website check failed for {url}: {e}")
        result['website_quality'] = 'basic'

    return result


def detect_gatekeeper_language(text: str) -> bool:
    """Check if text contains gatekeeper/office manager language."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in GATEKEEPER_PHRASES)


def detect_owner_operated(text: str) -> bool:
    """Check if text contains owner-operated signals."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in OWNER_OPERATED_PHRASES)


def detect_family_business(text: str) -> bool:
    """Check if text contains family business signals."""
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in FAMILY_BUSINESS_PHRASES)


def score_lead(lead: dict) -> dict:
    """Calculate lead score and tier. Mutates and returns the lead dict.

    Adds: website_quality, has_booking_system, lead_score, lead_tier, location_count,
          uses_expensive_software, is_owner_operated, is_family_business
    """
    score = 0

    # --- Website quality ---
    website_quality = lead.get('website_quality', '')
    if not website_quality:
        website_info = check_website_quality(lead.get('website', ''))
        lead['website_quality'] = website_info['website_quality']
        lead['has_booking_system'] = website_info['has_booking_system']
        lead['uses_expensive_software'] = website_info.get('uses_expensive_software', False)
        lead['is_owner_operated'] = website_info.get('is_owner_operated', False)
        lead['is_family_business'] = website_info.get('is_family_business', False)
    else:
        # Already set (e.g. manual override)
        pass

    wq = lead.get('website_quality', 'none')
    if wq == 'none':
        score += 20
    elif wq == 'basic':
        score += 0  # neutral — they have one but it's not polished
    elif wq == 'modern':
        score -= 10

    # --- Review count ---
    rc = lead.get('review_count') or 0
    if 10 <= rc <= 100:
        score += 15
    elif 1 <= rc <= 9:
        score += 10
    elif 100 < rc <= 300:
        score += 5
    elif rc > 300:
        score -= 15

    # --- Location count (default 1 = single location) ---
    lc = lead.get('location_count', 1) or 1
    if lc == 1:
        score += 10
    elif lc > 1:
        score -= 20

    # --- Owner name visible ---
    owner_visible = bool(lead.get('contact_name') or lead.get('owner_name_visible'))
    lead['owner_name_visible'] = 1 if owner_visible else 0
    if owner_visible:
        score += 15

    # --- Email type ---
    email = (lead.get('email') or '').lower()
    if email:
        local = email.split('@')[0]
        if local in ('info', 'contact', 'hello', 'service', 'office'):
            score += 10
        # owner-firstname style (short local part, no dots with numbers)
        elif len(local) <= 12 and not re.search(r'\d', local):
            score += 10

    # --- Gatekeeper language ---
    notes = lead.get('notes') or ''
    full_text = f"{lead.get('address', '')} {notes} {lead.get('description', '')}"
    if detect_gatekeeper_language(full_text):
        score -= 15

    # --- Booking system ---
    if lead.get('has_booking_system'):
        score -= 10
    else:
        # No booking system visible — solo operator signal
        if lead.get('website') and wq != 'none':
            score += 10

    # --- NEW: Expensive software detection (prime targets!) ---
    # They're already paying $150+/month, perfect for cost-savings pitch
    if lead.get('uses_expensive_software'):
        score += 20

    # --- NEW: Owner-operated detection ---
    # Check website detection or notes/description
    if lead.get('is_owner_operated') or detect_owner_operated(full_text):
        lead['is_owner_operated'] = True
        score += 15

    # --- NEW: Family business detection ---
    if lead.get('is_family_business') or detect_family_business(full_text):
        lead['is_family_business'] = True
        score += 10

    # --- NEW: Review text mentions owner by name (indicates personal service) ---
    review_text = lead.get('review_text', '') or lead.get('reviews_sample', '') or ''
    contact_name = lead.get('contact_name', '')
    if contact_name and review_text:
        first_name = contact_name.split()[0].lower()
        if len(first_name) > 2 and first_name in review_text.lower():
            score += 10

    # --- NEW: No employees listed (solo operator signal) ---
    employee_count = lead.get('employee_count')
    if employee_count is not None:
        if employee_count == 0 or employee_count == 1:
            score += 10
        elif employee_count > 10:
            score -= 10

    lead['lead_score'] = score
    lead['lead_tier'] = _tier_from_score(score)
    lead.setdefault('location_count', 1)

    return lead


def _tier_from_score(score: int) -> str:
    if score >= 50:
        return 'hot'
    elif score >= 25:
        return 'warm'
    elif score >= 0:
        return 'cool'
    else:
        return 'skip'


def score_leads_batch(leads: list[dict], progress_callback=None) -> dict:
    """Score a list of leads. Returns summary counts by tier."""
    counts = {'hot': 0, 'warm': 0, 'cool': 0, 'skip': 0}

    for i, lead in enumerate(leads):
        if progress_callback:
            progress_callback(i, len(leads),
                              f"Scoring: {lead.get('business_name', '?')}...")
        score_lead(lead)
        counts[lead['lead_tier']] += 1

    if progress_callback:
        progress_callback(len(leads), len(leads),
                          f"Scored {len(leads)} leads: "
                          f"{counts['hot']} Hot, {counts['warm']} Warm, "
                          f"{counts['cool']} Cool, {counts['skip']} Skip")

    return counts


def rescore_lead_from_db(lead: dict) -> dict:
    """Re-score a lead that already has website_quality set (skip HTTP check)."""
    score = 0

    wq = lead.get('website_quality', 'none') or 'none'
    if wq == 'none':
        score += 20
    elif wq == 'modern':
        score -= 10

    rc = lead.get('review_count') or 0
    if 10 <= rc <= 100:
        score += 15
    elif 1 <= rc <= 9:
        score += 10
    elif 100 < rc <= 300:
        score += 5
    elif rc > 300:
        score -= 15

    lc = lead.get('location_count', 1) or 1
    if lc == 1:
        score += 10
    elif lc > 1:
        score -= 20

    if lead.get('owner_name_visible') or lead.get('contact_name'):
        score += 15

    email = (lead.get('email') or '').lower()
    if email:
        local = email.split('@')[0]
        if local in ('info', 'contact', 'hello', 'service', 'office'):
            score += 10
        elif len(local) <= 12 and not re.search(r'\d', local):
            score += 10

    notes = lead.get('notes') or ''
    full_text = f"{lead.get('address', '')} {notes} {lead.get('description', '')}"
    if detect_gatekeeper_language(full_text):
        score -= 15

    has_booking = lead.get('has_booking_system')
    if has_booking:
        score -= 10
    elif lead.get('website') and wq != 'none':
        score += 10

    # Expensive software detection
    if lead.get('uses_expensive_software'):
        score += 20

    # Owner-operated detection
    if lead.get('is_owner_operated') or detect_owner_operated(full_text):
        lead['is_owner_operated'] = True
        score += 15

    # Family business detection
    if lead.get('is_family_business') or detect_family_business(full_text):
        lead['is_family_business'] = True
        score += 10

    # Review text mentions owner by name
    review_text = lead.get('review_text', '') or lead.get('reviews_sample', '') or ''
    contact_name = lead.get('contact_name', '')
    if contact_name and review_text:
        first_name = contact_name.split()[0].lower()
        if len(first_name) > 2 and first_name in review_text.lower():
            score += 10

    # Employee count
    employee_count = lead.get('employee_count')
    if employee_count is not None:
        if employee_count == 0 or employee_count == 1:
            score += 10
        elif employee_count > 10:
            score -= 10

    lead['lead_score'] = score
    lead['lead_tier'] = _tier_from_score(score)
    return lead

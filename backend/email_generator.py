"""3-email drip sequence template engine for cold outreach."""

from datetime import datetime, timedelta
from backend.database import insert_email, get_emails_for_lead, get_setting

# Default delays between emails (days)
DEFAULT_DELAY_1_TO_2 = 3
DEFAULT_DELAY_2_TO_3 = 5

# --- Email Templates ---
# Each template is a function that takes a lead dict and returns (subject, body)

TEMPLATES = {
    'intro': {
        1: {
            'subject': "Quick question for {business_name}",
            'body': """Hi {first_name},

I came across {business_name} while researching top {trade} companies in {city}, and I was impressed by your work.

I help tradespeople like you get more high-quality leads and jobs through targeted digital marketing — without the hassle of managing it yourself.

Would you be open to a quick 10-minute call this week to see if it's a fit?

Best,
{sender_name}
{sender_title}"""
        },
        2: {
            'subject': "Following up — {business_name}",
            'body': """Hi {first_name},

Just following up on my last email. I know you're busy running {business_name}, so I'll keep this brief.

I've helped several {trade} businesses in {state} increase their booked jobs by 30-50% using a simple outreach system. Happy to share how it works — no strings attached.

Would a quick call work this week?

Best,
{sender_name}"""
        },
        3: {
            'subject': "Last note from me — {business_name}",
            'body': """Hi {first_name},

I don't want to be a pest, so this will be my last email.

If getting more {trade} jobs in {city} is a priority for you, I'd love to help. Just reply "interested" and I'll send over some details.

Either way, wishing you and {business_name} continued success.

Cheers,
{sender_name}"""
        }
    },
    'referral': {
        1: {
            'subject': "Referral partner opportunity — {trade} in {city}",
            'body': """Hi {first_name},

I work with homeowners in {city} who regularly need {trade} services, and I'm looking for a reliable partner to refer them to.

I found {business_name} online and your reviews caught my eye. Would you be interested in receiving qualified referrals?

Let me know and I can explain how it works.

Best,
{sender_name}
{sender_title}"""
        },
        2: {
            'subject': "Re: Referral partner opportunity",
            'body': """Hi {first_name},

Quick follow-up — I have homeowners reaching out for {trade} work in the {city} area and wanted to make sure {business_name} had first dibs on these referrals.

No cost to you — just looking for a quality partner. Worth a quick chat?

Best,
{sender_name}"""
        },
        3: {
            'subject': "Closing the loop — {business_name}",
            'body': """Hi {first_name},

Haven't heard back so I'll assume the timing isn't right. No worries at all.

If you ever want to discuss a referral partnership for {trade} jobs in {city}, feel free to reach out anytime.

All the best,
{sender_name}"""
        }
    },
    'value_first': {
        1: {
            'subject': "Free tip to get more {trade} jobs in {city}",
            'body': """Hi {first_name},

I've been researching the {trade} market in {city} and noticed that many businesses are missing out on a simple trick to rank higher in local Google searches.

Here's a quick win: make sure your Google Business Profile has at least 5 recent photos and responds to every review (even the good ones). Businesses that do this see 35% more calls on average.

I help {trade} businesses implement these kinds of strategies. Would you be open to a quick chat about what else {business_name} could do to stand out?

Best,
{sender_name}
{sender_title}"""
        },
        2: {
            'subject': "Another quick tip for {business_name}",
            'body': """Hi {first_name},

One more thing I noticed — having a simple "Request a Quote" form on your website can increase leads by 25%. Most homeowners prefer to submit a form over calling.

I help businesses like {business_name} set these up and optimize them. Want me to put together a quick action plan for you? No charge.

Best,
{sender_name}"""
        },
        3: {
            'subject': "Last idea for {business_name}",
            'body': """Hi {first_name},

Last email from me — I wanted to leave you with one final suggestion. Asking happy customers to leave Google reviews (and making it easy with a direct link) is the #1 thing {trade} businesses can do to get more calls.

If you ever want help putting a system in place for {business_name}, just reply to this email.

Wishing you the best,
{sender_name}"""
        }
    }
}


def _get_first_name(lead: dict) -> str:
    """Extract first name from contact_name or business_name."""
    name = lead.get('contact_name', '') or ''
    if name:
        return name.split()[0]
    # Fallback to generic
    return 'there'


def _fill_template(template: dict, lead: dict, sender_name: str = '',
                   sender_title: str = '') -> tuple[str, str]:
    """Fill in a template with lead data."""
    sender_name = sender_name or get_setting('sender_name', 'Your Name')
    sender_title = sender_title or get_setting('sender_title', '')

    replacements = {
        '{business_name}': lead.get('business_name', 'your company'),
        '{first_name}': _get_first_name(lead),
        '{trade}': lead.get('trade', 'contracting'),
        '{city}': lead.get('city', 'your area'),
        '{state}': lead.get('state', ''),
        '{sender_name}': sender_name,
        '{sender_title}': sender_title,
    }

    subject = template['subject']
    body = template['body']

    for key, val in replacements.items():
        subject = subject.replace(key, val)
        body = body.replace(key, val)

    # Clean up empty sender_title line
    if not sender_title:
        body = body.replace('\n\n', '\n').replace('\n\n', '\n')

    return subject, body


def generate_email_sequence(lead: dict, template_name: str = 'intro',
                            sender_name: str = '', sender_title: str = '') -> list[dict]:
    """Generate a 3-email sequence for a lead.

    Returns list of dicts with keys: sequence_num, subject, body, scheduled_date
    """
    template_set = TEMPLATES.get(template_name, TEMPLATES['intro'])
    delay_1 = int(get_setting('delay_email_2', str(DEFAULT_DELAY_1_TO_2)))
    delay_2 = int(get_setting('delay_email_3', str(DEFAULT_DELAY_2_TO_3)))

    # Check what emails already exist for this lead
    existing = get_emails_for_lead(lead['id']) if lead.get('id') else []
    existing_nums = {e['sequence_num'] for e in existing}

    emails = []
    base_date = datetime.now()

    for seq_num in (1, 2, 3):
        if seq_num in existing_nums:
            continue

        template = template_set.get(seq_num)
        if not template:
            continue

        subject, body = _fill_template(template, lead, sender_name, sender_title)

        if seq_num == 1:
            scheduled = base_date
        elif seq_num == 2:
            scheduled = base_date + timedelta(days=delay_1)
        else:
            scheduled = base_date + timedelta(days=delay_1 + delay_2)

        emails.append({
            'sequence_num': seq_num,
            'subject': subject,
            'body': body,
            'scheduled_date': scheduled.isoformat(),
        })

    return emails


def generate_and_save_emails(lead_ids: list[int], template_name: str = 'intro',
                             sender_name: str = '', sender_title: str = '') -> int:
    """Generate emails for multiple leads and save to database.

    Returns count of emails created.
    """
    from backend.database import get_lead
    count = 0
    for lead_id in lead_ids:
        lead = get_lead(lead_id)
        if not lead or not lead.get('email'):
            continue

        emails = generate_email_sequence(lead, template_name, sender_name, sender_title)
        for email_data in emails:
            insert_email({
                'lead_id': lead_id,
                'sequence_num': email_data['sequence_num'],
                'subject': email_data['subject'],
                'body': email_data['body'],
                'status': 'pending_review',
            })
            count += 1

    return count


def get_template_names() -> list[str]:
    """Return available template names."""
    return list(TEMPLATES.keys())


def preview_template(template_name: str, sequence_num: int = 1) -> dict:
    """Preview a template with sample data."""
    sample_lead = {
        'business_name': 'ABC Plumbing',
        'contact_name': 'John Smith',
        'trade': 'plumber',
        'city': 'Austin',
        'state': 'TX',
    }
    template_set = TEMPLATES.get(template_name, TEMPLATES['intro'])
    template = template_set.get(sequence_num, template_set[1])
    subject, body = _fill_template(template, sample_lead, 'Your Name', 'Marketing Consultant')
    return {'subject': subject, 'body': body}

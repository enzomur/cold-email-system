"""3-email drip sequence template engine for cold outreach."""

from datetime import datetime, timedelta
from backend.database import insert_email, get_emails_for_lead, get_setting

# Default delays between emails (days)
DEFAULT_DELAY_1_TO_2 = 3
DEFAULT_DELAY_2_TO_3 = 5

# --- Email Templates ---
# Each template is a function that takes a lead dict and returns (subject, body)

TEMPLATES = {
    # --- All templates sell TradeTrackTemplate.com ---

    'pain_point': {
        1: {
            'subject': "Quick question about invoicing at {business_name}",
            'body': """Hi {first_name},

Honest question — how many jobs has {business_name} completed in the last year where the invoice never got sent?

I ask because I talk to {trade} owners in {city} all the time, and the answer is almost always "more than I'd like to admit."

I built a simple spreadsheet system that makes it impossible to forget. Takes 3 minutes to set up, costs $97 once, and you own it forever.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "That invoice you forgot to send",
            'body': """Hi {first_name},

Following up — most {trade} businesses lose $1,200-$5,000 a year just from jobs they completed but forgot to bill for.

TradeTrackTemplate is a dead-simple Google Sheets tracker that:
- Shows overdue invoices at a glance
- Tracks every job from quote to paid
- Works on your phone between jobs

One-time $97. No subscription, no software login.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "Last note — {business_name}",
            'body': """Hi {first_name},

Final email from me. If tracking jobs, invoices, and payments is a headache for {business_name}, check out TradeTrackTemplate.com.

It's what I wish existed when I was helping {trade} pros get organized — simple, cheap, and you own it forever.

Either way, best of luck with the business.

{sender_name}"""
        }
    },

    'cost_savings': {
        1: {
            'subject': "Paying $149/month for job tracking?",
            'body': """Hi {first_name},

Quick question — is {business_name} currently paying for software like Jobber, ServiceTitan, or Housecall Pro?

If so, you're probably spending $1,500-$2,000+ per year on features you barely use.

I built TradeTrackTemplate for {trade} pros who just need the basics: track jobs, send invoices, get paid. It's a one-time $97 purchase — no monthly fees, no contracts.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "Re: Monthly software costs",
            'body': """Hi {first_name},

Just following up. Here's the math for {business_name}:

Jobber/ServiceTitan: ~$149/month = $1,788/year
TradeTrackTemplate: $97 one-time

That's $1,691 saved in year one alone.

It's a simple Google Sheets system — you can see every job, invoice status, and payment in one place. Works on your phone too.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "One last thing — {business_name}",
            'body': """Hi {first_name},

Last email. If you ever get frustrated paying monthly fees for software that's more complicated than you need, check out TradeTrackTemplate.com.

$97 once, yours forever. Built specifically for {trade} businesses like {business_name}.

Wishing you continued success,
{sender_name}"""
        }
    },

    'social_proof': {
        1: {
            'subject': "How {trade} pros in {state} are staying organized",
            'body': """Hi {first_name},

I've been working with {trade} owners across {state} who were drowning in sticky notes, texts, and forgotten invoices.

The common thread? They didn't need fancy software — they needed something simple that actually worked.

TradeTrackTemplate is a Google Sheets job tracker I built after watching too many good contractors lose money to admin chaos. One-time $97, takes 3 minutes to set up.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "What other {trade} owners are saying",
            'body': """Hi {first_name},

Quick follow-up. The most common feedback I get from {trade} pros using TradeTrackTemplate:

"I can finally see which invoices are overdue without digging through emails."

"Setup took less time than making coffee."

"Wish I had this years ago."

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "Final note for {business_name}",
            'body': """Hi {first_name},

Last email from me. If staying organized and not losing money to forgotten invoices sounds good, take a look at TradeTrackTemplate.com.

It's what I wish existed for every {trade} business I've worked with — simple, affordable, and actually gets used.

All the best,
{sender_name}"""
        }
    },

    'direct': {
        1: {
            'subject': "Built this for {trade} pros like you",
            'body': """Hi {first_name},

I found {business_name} while looking for {trade} businesses in {city} and wanted to reach out directly.

I built TradeTrackTemplate — a simple Google Sheets system that helps contractors track jobs, invoices, and payments without paying $150+/month for bloated software.

It's $97 one-time. No subscriptions, no logins, works on your phone.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "Re: Job tracking for {business_name}",
            'body': """Hi {first_name},

Quick follow-up on my last email.

TradeTrackTemplate helps you:
- Never forget to send an invoice
- See which customers still owe you money
- Track every job from quote to paid

Most {trade} pros set it up in under 5 minutes. $97 once, yours forever.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "Last one from me",
            'body': """Hi {first_name},

Last email, I promise.

If you're tired of sticky notes, scattered texts, and forgetting to bill customers — TradeTrackTemplate.com might help.

$97 one-time, built specifically for {trade} pros who want something simple.

Either way, wishing {business_name} continued success.

{sender_name}"""
        }
    },

    'admin_chaos': {
        1: {
            'subject': "Sticky notes and scattered texts?",
            'body': """Hi {first_name},

Running a {trade} business means you're juggling a lot — jobs, quotes, invoices, customer calls.

If you're like most contractors I talk to, that info is scattered across sticky notes, text threads, and your head.

I built TradeTrackTemplate to fix that. It's a simple Google Sheets tracker where you can see everything in one place. $97 once, no monthly fees.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "One place for everything",
            'body': """Hi {first_name},

Following up — imagine opening one spreadsheet and seeing:
- Every active job and its status
- Which invoices are overdue
- How much money is coming in this month

That's TradeTrackTemplate. Works on your phone between jobs, takes 3 minutes to set up.

Most {trade} businesses lose $1,200+ a year to forgotten invoices alone. This fixes that.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "Final note — {business_name}",
            'body': """Hi {first_name},

Last email from me. If admin chaos is costing {business_name} time and money, check out TradeTrackTemplate.com.

Simple job tracking for {trade} pros. $97 once, yours forever.

Best of luck either way.

{sender_name}"""
        }
    },

    'time_savings': {
        1: {
            'subject': "5 hours a week on admin?",
            'body': """Hi {first_name},

Quick question — how much time does {business_name} spend each week tracking jobs, chasing invoices, and managing paperwork?

Most {trade} owners I talk to say 5-10 hours. That's time you could be on a job site making money.

I built TradeTrackTemplate to cut that down to minutes. It's a simple Google Sheets system that keeps everything organized. $97 one-time, no subscriptions.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        2: {
            'subject': "Time = money",
            'body': """Hi {first_name},

Following up. If you're spending 5 hours a week on admin at $50/hour, that's $13,000 a year in lost billable time.

TradeTrackTemplate helps you:
- Log jobs in 30 seconds
- See overdue invoices at a glance
- Track payments without digging through emails

One-time $97. Pays for itself in the first week.

Check it out at TradeTrackTemplate.com — or use our ROI calculator to see how much you're losing to admin chaos.

{sender_name}"""
        },
        3: {
            'subject': "Last note for {business_name}",
            'body': """Hi {first_name},

Final email. If you want to spend less time on paperwork and more time on jobs, take a look at TradeTrackTemplate.com.

Built for {trade} pros who want something simple. $97 once, no monthly fees.

Wishing you the best.

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


def _get_template_set(template_name: str) -> dict:
    """Get template set by name, checking custom templates first."""
    from backend.database import get_custom_template_by_name
    # Check for custom template (override or custom)
    custom = get_custom_template_by_name(template_name)
    if custom and custom.get('sequences'):
        # Convert custom format to TEMPLATES format
        result = {}
        for seq in custom['sequences']:
            result[seq['sequence_num']] = {
                'subject': seq['subject'],
                'body': seq['body']
            }
        return result
    # Fall back to system template
    return TEMPLATES.get(template_name, TEMPLATES['pain_point'])


def generate_email_sequence(lead: dict, template_name: str = 'pain_point',
                            sender_name: str = '', sender_title: str = '') -> list[dict]:
    """Generate a 3-email sequence for a lead.

    Returns list of dicts with keys: sequence_num, subject, body, scheduled_date
    """
    template_set = _get_template_set(template_name)
    delay_1 = int(get_setting('delay_email_2', str(DEFAULT_DELAY_1_TO_2)))
    delay_2 = int(get_setting('delay_email_3', str(DEFAULT_DELAY_2_TO_3)))

    # Check what emails already exist for this lead (exclude rejected so they can be regenerated)
    existing = get_emails_for_lead(lead['id'], exclude_rejected=True) if lead.get('id') else []
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


def generate_and_save_emails(lead_ids: list[int], template_name: str = 'pain_point',
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
    """Return available template names (system + custom)."""
    from backend.database import get_custom_templates
    names = list(TEMPLATES.keys())
    # Add custom template names that aren't overrides
    try:
        custom = get_custom_templates()
        for t in custom:
            if not t.get('is_override') and t['name'] not in names:
                names.append(t['name'])
    except Exception:
        pass  # Database might not be initialized yet
    return names


def preview_template(template_name: str, sequence_num: int = 1) -> dict:
    """Preview a template with sample data."""
    sample_lead = {
        'business_name': 'ABC Plumbing',
        'contact_name': 'John Smith',
        'trade': 'plumber',
        'city': 'Austin',
        'state': 'TX',
    }
    template_set = _get_template_set(template_name)
    template = template_set.get(sequence_num, template_set.get(1, {'subject': '', 'body': ''}))
    subject, body = _fill_template(template, sample_lead, 'Your Name', '')
    return {'subject': subject, 'body': body}

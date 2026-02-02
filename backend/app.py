"""Flask application — all API routes and page rendering."""

import os
import sys
import json
import logging
import threading
from datetime import datetime

from flask import (
    Flask, render_template, request, jsonify, Response, redirect, url_for
)
from flask_cors import CORS
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.database import (
    init_db, get_leads, get_lead, insert_lead, update_lead, delete_leads,
    insert_leads_bulk, get_email_queue, get_sent_emails, update_email,
    get_stats, get_setting, set_setting, get_emails_for_lead,
    get_today_send_count, get_all_leads_for_export, get_followup_candidates,
)
from backend.email_generator import (
    generate_and_save_emails, get_template_names, preview_template,
)
from backend.gmail_service import send_email, send_batch, is_gmail_connected
from backend.sheets_service import (
    export_leads_to_sheet, import_leads_from_sheet, is_sheets_connected,
)
from backend.scrapers.google_maps import scrape_google_maps
from backend.scrapers.yelp import scrape_yelp
from backend.scrapers.license_dbs import scrape_license_dbs
from backend.scrapers.email_finder import enrich_leads_with_emails
from backend.lead_scorer import score_leads_batch, rescore_lead_from_db

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend', 'templates'),
    static_folder=os.path.join(os.path.dirname(__file__), '..', 'frontend', 'static'),
)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'dev-secret-key')
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory scrape job tracking
scrape_jobs = {}


# --- Page Routes ---

@app.route('/')
def dashboard():
    stats = get_stats()
    return render_template('dashboard.html', stats=stats)


@app.route('/scrape')
def scrape_page():
    return render_template('scrape.html')


@app.route('/leads')
def leads_page():
    page = request.args.get('page', 1, type=int)
    filters = {
        'trade': request.args.get('trade', ''),
        'state': request.args.get('state', ''),
        'status': request.args.get('status', ''),
        'has_email': request.args.get('has_email', ''),
        'search': request.args.get('search', ''),
        'tier': request.args.get('tier', ''),
    }
    # Remove empty filters
    filters = {k: v for k, v in filters.items() if v}
    result = get_leads(filters=filters, page=page)
    return render_template('leads.html', **result, filters=request.args)


@app.route('/queue')
def queue_page():
    status = request.args.get('status', 'pending_review')
    include_cool = request.args.get('include_cool', '')
    exclude_tiers = ['skip']
    if not include_cool:
        exclude_tiers.append('cool')
    emails = get_email_queue(status=status, exclude_tiers=exclude_tiers)
    return render_template('queue.html', emails=emails, current_status=status,
                           include_cool=include_cool)


@app.route('/sent')
def sent_page():
    emails = get_sent_emails()
    return render_template('sent.html', emails=emails)


@app.route('/settings')
def settings_page():
    gmail_connected = is_gmail_connected()
    sheets_connected = is_sheets_connected()
    return render_template('settings.html',
                           gmail_connected=gmail_connected,
                           sheets_connected=sheets_connected)


# --- API: Scraping ---

@app.route('/api/scrape/start', methods=['POST'])
def api_start_scrape():
    data = request.json
    trade = data.get('trade', '')
    location = data.get('location', '')
    sources = data.get('sources', ['google_maps'])
    max_results = data.get('max_results', 20)

    if not trade or not location:
        return jsonify({'error': 'Trade and location are required'}), 400

    job_id = f"scrape_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    scrape_jobs[job_id] = {
        'status': 'running',
        'progress': 0,
        'total': 0,
        'message': 'Starting...',
        'results': [],
        'leads_found': 0,
    }

    def run_scrape():
        all_leads = []

        def progress_cb(current, total, message):
            scrape_jobs[job_id]['progress'] = current
            scrape_jobs[job_id]['total'] = total
            scrape_jobs[job_id]['message'] = message

        try:
            if 'google_maps' in sources:
                leads = scrape_google_maps(trade, location, max_results, progress_cb)
                all_leads.extend(leads)

            if 'yelp' in sources:
                leads = scrape_yelp(trade, location, max_results, progress_cb)
                all_leads.extend(leads)

            if 'license_dbs' in sources:
                leads = scrape_license_dbs(trade, location, max_results=max_results,
                                           progress_callback=progress_cb)
                all_leads.extend(leads)

            # Find emails for leads that don't have one
            if data.get('find_emails', True):
                progress_cb(0, len(all_leads), "Finding email addresses...")
                hunter_key = os.getenv('HUNTER_API_KEY', '')
                enrich_leads_with_emails(all_leads, hunter_key, progress_cb)

            # Score leads
            progress_cb(0, len(all_leads), "Scoring leads...")
            tier_counts = score_leads_batch(all_leads, progress_cb)

            # Save to database
            inserted = insert_leads_bulk(all_leads)

            scrape_jobs[job_id]['status'] = 'done'
            scrape_jobs[job_id]['leads_found'] = inserted
            scrape_jobs[job_id]['tier_counts'] = tier_counts
            scrape_jobs[job_id]['message'] = (
                f"Done! {inserted} new leads saved. "
                f"{tier_counts['hot']} Hot, {tier_counts['warm']} Warm, "
                f"{tier_counts['cool']} Cool, {tier_counts['skip']} Skip"
            )

        except Exception as e:
            logger.error(f"Scrape job {job_id} failed: {e}")
            scrape_jobs[job_id]['status'] = 'error'
            scrape_jobs[job_id]['message'] = f"Error: {e}"

    thread = threading.Thread(target=run_scrape, daemon=True)
    thread.start()

    return jsonify({'job_id': job_id})


@app.route('/api/scrape/status/<job_id>')
def api_scrape_status(job_id):
    job = scrape_jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@app.route('/api/scrape/stream/<job_id>')
def api_scrape_stream(job_id):
    """SSE endpoint for real-time scrape progress."""
    def generate():
        import time
        while True:
            job = scrape_jobs.get(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                break
            yield f"data: {json.dumps(job)}\n\n"
            if job['status'] in ('done', 'error'):
                break
            time.sleep(1)

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


# --- API: Leads ---

@app.route('/api/leads', methods=['GET'])
def api_get_leads():
    page = request.args.get('page', 1, type=int)
    filters = {k: v for k, v in request.args.items() if k != 'page' and v}
    result = get_leads(filters=filters, page=page)
    return jsonify(result)


@app.route('/api/leads/<int:lead_id>', methods=['GET'])
def api_get_lead(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    lead['emails'] = get_emails_for_lead(lead_id)
    return jsonify(lead)


@app.route('/api/leads/<int:lead_id>', methods=['PUT'])
def api_update_lead(lead_id):
    data = request.json
    update_lead(lead_id, data)
    return jsonify({'success': True})


@app.route('/api/leads/<int:lead_id>/rescore', methods=['POST'])
def api_rescore_lead(lead_id):
    lead = get_lead(lead_id)
    if not lead:
        return jsonify({'error': 'Lead not found'}), 404
    data = request.json or {}
    # Allow manual score override
    if 'lead_score' in data:
        score = int(data['lead_score'])
        from backend.lead_scorer import _tier_from_score
        tier = _tier_from_score(score)
        update_lead(lead_id, {'lead_score': score, 'lead_tier': tier})
        return jsonify({'success': True, 'lead_score': score, 'lead_tier': tier})
    # Otherwise recalculate from signals
    rescored = rescore_lead_from_db(lead)
    update_lead(lead_id, {
        'lead_score': rescored['lead_score'],
        'lead_tier': rescored['lead_tier'],
    })
    return jsonify({'success': True, 'lead_score': rescored['lead_score'],
                    'lead_tier': rescored['lead_tier']})


@app.route('/api/leads/delete', methods=['POST'])
def api_delete_leads():
    ids = request.json.get('ids', [])
    if ids:
        delete_leads(ids)
    return jsonify({'success': True, 'deleted': len(ids)})


# --- API: Emails ---

@app.route('/api/emails/generate', methods=['POST'])
def api_generate_emails():
    data = request.json
    lead_ids = data.get('lead_ids', [])
    template = data.get('template', 'intro')
    sender_name = data.get('sender_name', '')
    sender_title = data.get('sender_title', '')

    if not lead_ids:
        return jsonify({'error': 'No leads selected'}), 400

    count = generate_and_save_emails(lead_ids, template, sender_name, sender_title)
    return jsonify({'success': True, 'emails_created': count})


@app.route('/api/emails/queue', methods=['GET'])
def api_get_queue():
    status = request.args.get('status', 'pending_review')
    emails = get_email_queue(status=status)
    return jsonify({'emails': emails})


@app.route('/api/emails/<int:email_id>', methods=['PUT'])
def api_update_email(email_id):
    data = request.json
    update_email(email_id, data)
    return jsonify({'success': True})


@app.route('/api/emails/<int:email_id>/approve', methods=['POST'])
def api_approve_email(email_id):
    update_email(email_id, {'status': 'approved', 'approved_date': datetime.now().isoformat()})
    return jsonify({'success': True})


@app.route('/api/emails/<int:email_id>/reject', methods=['POST'])
def api_reject_email(email_id):
    update_email(email_id, {'status': 'rejected'})
    return jsonify({'success': True})


@app.route('/api/emails/approve-all', methods=['POST'])
def api_approve_all():
    emails = get_email_queue(status='pending_review')
    for e in emails:
        update_email(e['id'], {'status': 'approved', 'approved_date': datetime.now().isoformat()})
    return jsonify({'success': True, 'count': len(emails)})


@app.route('/api/emails/send', methods=['POST'])
def api_send_emails():
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        # Send all approved emails
        emails = get_email_queue(status='approved')
    else:
        emails = [e for e in get_email_queue(status='approved') if e['id'] in email_ids]

    if not emails:
        return jsonify({'error': 'No approved emails to send'}), 400

    result = send_batch(emails)
    return jsonify(result)


@app.route('/api/emails/sent', methods=['GET'])
def api_get_sent():
    emails = get_sent_emails()
    return jsonify({'emails': emails})


@app.route('/api/emails/templates', methods=['GET'])
def api_get_templates():
    names = get_template_names()
    return jsonify({'templates': names})


@app.route('/api/emails/preview', methods=['GET'])
def api_preview_template():
    name = request.args.get('template', 'intro')
    seq = request.args.get('sequence', 1, type=int)
    preview = preview_template(name, seq)
    return jsonify(preview)


# --- API: Sheets ---

@app.route('/api/sheets/export', methods=['POST'])
def api_export_sheets():
    result = export_leads_to_sheet()
    return jsonify(result)


@app.route('/api/sheets/import', methods=['POST'])
def api_import_sheets():
    result = import_leads_from_sheet()
    return jsonify(result)


# --- API: Settings ---

@app.route('/api/settings', methods=['GET'])
def api_get_settings():
    from backend.database import get_db
    conn = get_db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    settings = {r['key']: r['value'] for r in rows}
    settings['gmail_connected'] = is_gmail_connected()
    settings['sheets_connected'] = is_sheets_connected()
    settings['sends_today'] = get_today_send_count()
    return jsonify(settings)


@app.route('/api/settings', methods=['POST'])
def api_save_settings():
    data = request.json
    for key, value in data.items():
        set_setting(key, str(value))
    return jsonify({'success': True})


# --- API: Stats ---

@app.route('/api/stats', methods=['GET'])
def api_get_stats():
    return jsonify(get_stats())


# --- Init ---

if __name__ == '__main__':
    init_db()
    print("Starting Cold Email Outreach System...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000, threaded=True)

"""SQLite database layer for lead storage and email tracking."""

import sqlite3
import os
from datetime import datetime, date

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'leads.db')


def get_db():
    """Get a database connection with row factory."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist."""
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            business_name TEXT NOT NULL,
            contact_name TEXT,
            email TEXT,
            phone TEXT,
            address TEXT,
            city TEXT,
            state TEXT,
            zip_code TEXT,
            website TEXT,
            trade TEXT,
            source TEXT,
            rating REAL,
            review_count INTEGER,
            license_number TEXT,
            license_type TEXT,
            scraped_date TEXT NOT NULL,
            status TEXT DEFAULT 'new',
            notes TEXT,
            website_quality TEXT DEFAULT 'none',
            location_count INTEGER DEFAULT 1,
            owner_name_visible INTEGER DEFAULT 0,
            has_booking_system INTEGER DEFAULT 0,
            lead_score INTEGER DEFAULT 0,
            lead_tier TEXT DEFAULT 'cool',
            UNIQUE(business_name, city, state, source)
        );

        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            sequence_num INTEGER NOT NULL DEFAULT 1,
            subject TEXT NOT NULL,
            body TEXT NOT NULL,
            status TEXT DEFAULT 'pending_review',
            created_date TEXT NOT NULL,
            approved_date TEXT,
            sent_date TEXT,
            opened_date TEXT,
            replied_date TEXT,
            FOREIGN KEY (lead_id) REFERENCES leads(id)
        );

        CREATE TABLE IF NOT EXISTS send_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            sent_at TEXT NOT NULL,
            gmail_message_id TEXT,
            FOREIGN KEY (email_id) REFERENCES emails(id)
        );

        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
        CREATE INDEX IF NOT EXISTS idx_leads_source ON leads(source);
        CREATE INDEX IF NOT EXISTS idx_leads_state ON leads(state);
        CREATE INDEX IF NOT EXISTS idx_leads_trade ON leads(trade);
        CREATE INDEX IF NOT EXISTS idx_emails_status ON emails(status);
        CREATE INDEX IF NOT EXISTS idx_emails_lead ON emails(lead_id);
    """)
    # Migrate existing tables — add new columns if missing
    _migrate_leads_table(conn)
    # Create indexes on scoring columns (after migration ensures columns exist)
    conn.executescript("""
        CREATE INDEX IF NOT EXISTS idx_leads_score ON leads(lead_score);
        CREATE INDEX IF NOT EXISTS idx_leads_tier ON leads(lead_tier);
    """)
    conn.commit()
    conn.close()


def _migrate_leads_table(conn):
    """Add scoring columns to existing leads table if they don't exist."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(leads)").fetchall()}
    migrations = [
        ('website_quality', "TEXT DEFAULT 'none'"),
        ('location_count', 'INTEGER DEFAULT 1'),
        ('owner_name_visible', 'INTEGER DEFAULT 0'),
        ('has_booking_system', 'INTEGER DEFAULT 0'),
        ('lead_score', 'INTEGER DEFAULT 0'),
        ('lead_tier', "TEXT DEFAULT 'cool'"),
    ]
    for col_name, col_def in migrations:
        if col_name not in existing:
            conn.execute(f"ALTER TABLE leads ADD COLUMN {col_name} {col_def}")


# --- Lead CRUD ---

def insert_lead(lead: dict) -> int | None:
    """Insert a lead, return its id. Returns None if duplicate."""
    conn = get_db()
    try:
        cur = conn.execute("""
            INSERT INTO leads (business_name, contact_name, email, phone, address,
                city, state, zip_code, website, trade, source, rating, review_count,
                license_number, license_type, scraped_date, status, notes,
                website_quality, location_count, owner_name_visible,
                has_booking_system, lead_score, lead_tier)
            VALUES (:business_name, :contact_name, :email, :phone, :address,
                :city, :state, :zip_code, :website, :trade, :source, :rating,
                :review_count, :license_number, :license_type, :scraped_date, :status, :notes,
                :website_quality, :location_count, :owner_name_visible,
                :has_booking_system, :lead_score, :lead_tier)
        """, {
            'business_name': lead.get('business_name', ''),
            'contact_name': lead.get('contact_name', ''),
            'email': lead.get('email', ''),
            'phone': lead.get('phone', ''),
            'address': lead.get('address', ''),
            'city': lead.get('city', ''),
            'state': lead.get('state', ''),
            'zip_code': lead.get('zip_code', ''),
            'website': lead.get('website', ''),
            'trade': lead.get('trade', ''),
            'source': lead.get('source', ''),
            'rating': lead.get('rating'),
            'review_count': lead.get('review_count'),
            'license_number': lead.get('license_number', ''),
            'license_type': lead.get('license_type', ''),
            'scraped_date': lead.get('scraped_date', datetime.now().isoformat()),
            'status': lead.get('status', 'new'),
            'notes': lead.get('notes', ''),
            'website_quality': lead.get('website_quality', 'none'),
            'location_count': lead.get('location_count', 1),
            'owner_name_visible': 1 if lead.get('owner_name_visible') else 0,
            'has_booking_system': 1 if lead.get('has_booking_system') else 0,
            'lead_score': lead.get('lead_score', 0),
            'lead_tier': lead.get('lead_tier', 'cool'),
        })
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def insert_leads_bulk(leads: list[dict]) -> int:
    """Insert multiple leads. Returns count of successfully inserted."""
    count = 0
    for lead in leads:
        if insert_lead(lead) is not None:
            count += 1
    return count


def get_leads(filters: dict | None = None, page: int = 1, per_page: int = 50) -> dict:
    """Get paginated, filtered leads."""
    conn = get_db()
    where_clauses = []
    params = []

    if filters:
        if filters.get('status'):
            where_clauses.append("status = ?")
            params.append(filters['status'])
        if filters.get('source'):
            where_clauses.append("source = ?")
            params.append(filters['source'])
        if filters.get('state'):
            where_clauses.append("state = ?")
            params.append(filters['state'])
        if filters.get('trade'):
            where_clauses.append("trade = ?")
            params.append(filters['trade'])
        if filters.get('tier'):
            where_clauses.append("lead_tier = ?")
            params.append(filters['tier'])
        if filters.get('search'):
            where_clauses.append("(business_name LIKE ? OR email LIKE ? OR contact_name LIKE ?)")
            s = f"%{filters['search']}%"
            params.extend([s, s, s])
        if filters.get('has_email'):
            where_clauses.append("email != '' AND email IS NOT NULL")

    where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    # Count
    total = conn.execute(f"SELECT COUNT(*) FROM leads{where_sql}", params).fetchone()[0]

    # Paginated results — default sort by score descending
    offset = (page - 1) * per_page
    rows = conn.execute(
        f"SELECT * FROM leads{where_sql} ORDER BY lead_score DESC, id DESC LIMIT ? OFFSET ?",
        params + [per_page, offset]
    ).fetchall()
    conn.close()

    return {
        'leads': [dict(r) for r in rows],
        'total': total,
        'page': page,
        'per_page': per_page,
        'pages': (total + per_page - 1) // per_page
    }


def get_lead(lead_id: int) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_lead(lead_id: int, data: dict):
    conn = get_db()
    sets = ", ".join(f"{k} = ?" for k in data)
    conn.execute(f"UPDATE leads SET {sets} WHERE id = ?", list(data.values()) + [lead_id])
    conn.commit()
    conn.close()


def delete_leads(lead_ids: list[int]):
    conn = get_db()
    placeholders = ",".join("?" * len(lead_ids))
    conn.execute(f"DELETE FROM leads WHERE id IN ({placeholders})", lead_ids)
    conn.commit()
    conn.close()


def get_all_leads_for_export() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM leads ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Email CRUD ---

def insert_email(email: dict) -> int:
    conn = get_db()
    cur = conn.execute("""
        INSERT INTO emails (lead_id, sequence_num, subject, body, status, created_date)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        email['lead_id'], email.get('sequence_num', 1),
        email['subject'], email['body'],
        email.get('status', 'pending_review'),
        datetime.now().isoformat()
    ))
    conn.commit()
    eid = cur.lastrowid
    conn.close()
    return eid


def get_email_queue(status: str = 'pending_review',
                    exclude_tiers: list[str] | None = None) -> list[dict]:
    conn = get_db()
    tier_filter = ""
    params = [status]
    if exclude_tiers:
        placeholders = ",".join("?" * len(exclude_tiers))
        tier_filter = f" AND l.lead_tier NOT IN ({placeholders})"
        params.extend(exclude_tiers)
    rows = conn.execute(f"""
        SELECT e.*, l.business_name, l.contact_name, l.email as lead_email,
               l.city, l.state, l.source, l.trade, l.lead_score, l.lead_tier
        FROM emails e JOIN leads l ON e.lead_id = l.id
        WHERE e.status = ?{tier_filter}
        ORDER BY l.lead_score DESC, e.created_date DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_sent_emails() -> list[dict]:
    conn = get_db()
    rows = conn.execute("""
        SELECT e.*, l.business_name, l.contact_name, l.email as lead_email,
               l.city, l.state
        FROM emails e JOIN leads l ON e.lead_id = l.id
        WHERE e.status IN ('sent', 'opened', 'replied')
        ORDER BY e.sent_date DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_email(email_id: int, data: dict):
    conn = get_db()
    sets = ", ".join(f"{k} = ?" for k in data)
    conn.execute(f"UPDATE emails SET {sets} WHERE id = ?", list(data.values()) + [email_id])
    conn.commit()
    conn.close()


def get_today_send_count() -> int:
    conn = get_db()
    today = date.today().isoformat()
    count = conn.execute(
        "SELECT COUNT(*) FROM send_log WHERE sent_at LIKE ?", (f"{today}%",)
    ).fetchone()[0]
    conn.close()
    return count


def log_send(email_id: int, gmail_message_id: str = ''):
    conn = get_db()
    conn.execute(
        "INSERT INTO send_log (email_id, sent_at, gmail_message_id) VALUES (?, ?, ?)",
        (email_id, datetime.now().isoformat(), gmail_message_id)
    )
    conn.commit()
    conn.close()


def get_emails_for_lead(lead_id: int) -> list[dict]:
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM emails WHERE lead_id = ? ORDER BY sequence_num", (lead_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_followup_candidates() -> list[dict]:
    """Find leads that need follow-up emails queued."""
    conn = get_db()
    # Leads with email 1 sent 3+ days ago but no email 2
    rows = conn.execute("""
        SELECT e.lead_id, e.sent_date, e.sequence_num, l.business_name,
               l.contact_name, l.email, l.city, l.state, l.source, l.trade
        FROM emails e
        JOIN leads l ON e.lead_id = l.id
        WHERE e.status = 'sent'
          AND l.status NOT IN ('replied', 'converted')
          AND e.lead_id NOT IN (
              SELECT lead_id FROM emails WHERE sequence_num > e.sequence_num
          )
        ORDER BY e.sent_date ASC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Stats ---

def get_stats() -> dict:
    conn = get_db()
    today = date.today().isoformat()
    stats = {
        'total_leads': conn.execute("SELECT COUNT(*) FROM leads").fetchone()[0],
        'leads_with_email': conn.execute(
            "SELECT COUNT(*) FROM leads WHERE email != '' AND email IS NOT NULL"
        ).fetchone()[0],
        'emails_in_queue': conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status = 'pending_review'"
        ).fetchone()[0],
        'emails_approved': conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status = 'approved'"
        ).fetchone()[0],
        'emails_sent_today': conn.execute(
            "SELECT COUNT(*) FROM send_log WHERE sent_at LIKE ?", (f"{today}%",)
        ).fetchone()[0],
        'emails_sent_total': conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status IN ('sent','opened','replied')"
        ).fetchone()[0],
        'replies': conn.execute(
            "SELECT COUNT(*) FROM emails WHERE status = 'replied'"
        ).fetchone()[0],
        'conversions': conn.execute(
            "SELECT COUNT(*) FROM leads WHERE status = 'converted'"
        ).fetchone()[0],
    }
    sent_total = stats['emails_sent_total']
    stats['reply_rate'] = round(stats['replies'] / sent_total * 100, 1) if sent_total else 0

    # Tier counts
    for tier in ('hot', 'warm', 'cool', 'skip'):
        stats[f'leads_{tier}'] = conn.execute(
            "SELECT COUNT(*) FROM leads WHERE lead_tier = ?", (tier,)
        ).fetchone()[0]

    conn.close()
    return stats


# --- Settings ---

def get_setting(key: str, default: str = '') -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
    )
    conn.commit()
    conn.close()

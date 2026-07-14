"""
WorkTrack Pro — MPPL Office Tasks & Compliances
Single-file, stdlib-only Python web app (no Flask, no pip installs needed).
Run:  python app.py    →    http://127.0.0.1:5000
Demo: admin@office.local / admin123  (also savitha/rabiya/deepak/murali/radha @office.local)
"""

from __future__ import annotations
import csv, hashlib, html, io, os, secrets, sqlite3, sys, time, zipfile
from datetime import date, datetime, timedelta, time as dtime
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from xml.etree import ElementTree as ET

# ──────────────────────────────────────────────────────────────────────────────
# Configuration & constants
# ──────────────────────────────────────────────────────────────────────────────
BASE = Path(__file__).resolve().parent
DB = BASE / 'worktrack.db'
UPLOADS = BASE / 'uploads'; UPLOADS.mkdir(exist_ok=True)
SESSIONS: dict[str, int] = {}

STATUSES   = ['Assigned', 'Accepted', 'In Progress', 'Waiting', 'Submitted for Review',
              'Rework Required', 'Completed', 'Overdue', 'Deferred', 'Cancelled']
UPDATES    = ['Not Started', 'In Progress', 'Waiting for Documents', 'Waiting for Approval',
              'Waiting from Client/Vendor', 'Submitted for Review', 'Rework Required',
              'Completed', 'Delayed', 'Deferred']
PRIORITIES = ['Low', 'Medium', 'High', 'Critical']
DELAY      = ['', 'Employee delay', 'Management approval pending', 'Client/vendor pending',
              'Document pending', 'System issue', 'External consultant pending',
              'Regulatory dependency', 'Bank dependency', 'Auditor dependency']
WORK       = ['Office', 'WFH', 'Client Visit', 'Leave', 'Half Day']
COMP       = ['Agreement Renewal', 'DSC Renewal', 'LEI Renewal', 'Board Meeting', 'ROC Filing',
              'DPT-3', 'Form 3', 'Form 8', 'Form 11', 'GST Return', 'TDS Return', 'Advance Tax',
              'Professional Tax', 'PF', 'ESI', 'Shops & Establishment', 'Insurance Renewal',
              'AMC Renewal', 'Bank KYC Update', 'License Renewal', 'Audit Due Date', 'Custom']
ROLE_OPTIONS = ['System Admin', 'Management', 'Assignor', 'Reviewer', 'Assignee']
ENTITY_MASTER = [
    ('MPPL', 'Company'),
    ('MSiR', 'Company'),
    ('MP', 'Individual'),
    ('Matterhorn LLP', 'LLP'),
    ('Ozymandiaz', 'Company'),
    ('Recinloop', 'Company'),
    ('Tarraki', 'Company'),
    ('Redhill', 'Company'),
    ('Samaroha', 'LLP'),
]

# Default daily time slots (label, start, end) — pre-seeded per user per day on demand
DEFAULT_SLOTS = [
    ('Priority Block 1', '09:30', '11:30'),
    ('Priority Block 2', '11:30', '13:30'),
    ('Lunch Break',      '13:30', '14:30'),
    ('Execution Block',  '14:30', '16:00'),
    ('Closure Block',    '16:00', '17:30'),
]
OFFICE_SLOT_LABELS = [x[0] for x in DEFAULT_SLOTS]

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────
def h(x): return html.escape(str(x if x is not None else ''))
def pw(p): return hashlib.sha256(p.encode()).hexdigest()
def db():
    con = sqlite3.connect(DB); con.row_factory = sqlite3.Row; return con
def q(sql, args=(), one=False):
    con = db(); cur = con.execute(sql, args); rows = cur.fetchall(); con.close()
    return (rows[0] if rows else None) if one else rows
def ex(sql, args=()):
    con = db(); cur = con.execute(sql, args); con.commit(); lid = cur.lastrowid; con.close()
    return lid

def now_in_slot(start: str, end: str) -> bool:
    """True if current local time falls inside the slot window."""
    try:
        s = datetime.strptime(start, '%H:%M').time()
        e = datetime.strptime(end, '%H:%M').time()
        n = datetime.now().time()
        return s <= n < e
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────────────
# Database
# ──────────────────────────────────────────────────────────────────────────────
def init_db():
    fresh = not DB.exists()
    con = db(); c = con.cursor()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
        password_hash TEXT, role TEXT, department TEXT, designation TEXT,
        reporting_manager_id INTEGER, skill_area TEXT, status TEXT DEFAULT 'Active',
        must_change_password INTEGER DEFAULT 0, password_changed_at TEXT);

    CREATE TABLE IF NOT EXISTS entities(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, entity_type TEXT,
        pan TEXT, gstin TEXT, cin_llpin TEXT, responsible_user_id INTEGER,
        status TEXT DEFAULT 'Active');

    CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_code TEXT, title TEXT, description TEXT,
        category TEXT, entity_id INTEGER, assigned_by INTEGER, assigned_to INTEGER,
        reviewer_id INTEGER, priority TEXT, start_date TEXT, target_date TEXT,
        expected_hours REAL DEFAULT 0, actual_hours REAL DEFAULT 0,
        status TEXT DEFAULT 'Assigned', recurring_flag TEXT DEFAULT 'No',
        recurrence_frequency TEXT, attachment_required TEXT DEFAULT 'No',
        external_dependency TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT);

    CREATE TABLE IF NOT EXISTS task_updates(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, user_id INTEGER,
        update_date TEXT, status TEXT, hours_spent REAL, remarks TEXT,
        issue_description TEXT, delay_reason TEXT, support_required_from TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);

    CREATE TABLE IF NOT EXISTS compliance_reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id INTEGER, compliance_type TEXT,
        financial_year TEXT, due_date TEXT, frequency TEXT, responsible_user_id INTEGER,
        reviewer_id INTEGER, priority TEXT, reminder_days TEXT DEFAULT '30,15,7,3,1',
        escalation_user_id INTEGER, status TEXT DEFAULT 'Upcoming', filing_date TEXT,
        acknowledgement_number TEXT, remarks TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);

    CREATE TABLE IF NOT EXISTS reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, reviewer_id INTEGER,
        review_status TEXT, quality_rating INTEGER, comments TEXT,
        reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP);

    CREATE TABLE IF NOT EXISTS daily_reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, report_date TEXT,
        work_mode TEXT, total_hours REAL, summary TEXT, submitted_at TEXT,
        emailed_to_manager TEXT, manager_id INTEGER);

    CREATE TABLE IF NOT EXISTS daily_sheet_entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, entry_date TEXT,
        task_id INTEGER, task_text TEXT, from_time TEXT, to_time TEXT,
        work_status TEXT, remarks TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);

    -- NEW: daily time-slot planner (one row per slot per user per day)
    CREATE TABLE IF NOT EXISTS daily_slots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, slot_date TEXT,
        slot_label TEXT, start_time TEXT, end_time TEXT, task_id INTEGER,
        status TEXT DEFAULT 'Planned', notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, slot_date, slot_label));
    ''')
    con.commit()

    if fresh:
        users = [
            ('Admin',       'admin@office.local',      'System Admin',  'Admin',              'Administrator',          None, 'Admin'),
            ('Management',  'management@office.local', 'Management',    'Management',         'Management',             None, 'Strategy'),
            ('Savitha',     'savitha@office.local',    'Assignor',     'Finance & Accounts', 'Finance Lead',           2,    'Finance, Taxation, Compliance, HR'),
            ('Rabiya',      'rabiya@office.local',     'Reviewer',      'Accounts',           'Senior Accounts Exec',   3,    'Ledger scrutiny, GST/TDS, Audit'),
            ('Deepak',      'deepak@office.local',     'Assignee',   'Accounts',           'Accounts Executive',     3,    'Accounting, invoices, bank reconciliation'),
            ('Mohanmurali', 'murali@office.local',     'Assignee',   'Accounts',           'Accounts Executive',     3,    'Accounting, GST/TDS, vendor bills'),
            ('Radha',       'radha@office.local',      'Assignee',   'Admin',              'Admin Coordinator',      3,    'Admin, coordination, personal accounts'),
        ]
        for u in users:
            c.execute('INSERT INTO users(name,email,password_hash,role,department,designation,reporting_manager_id,skill_area) VALUES (?,?,?,?,?,?,?,?)',
                      (u[0], u[1], pw('admin123'), u[2], u[3], u[4], u[5], u[6]))

        # Entity master is kept in the sequence requested by office management.
        for name, entity_type in ENTITY_MASTER:
            c.execute('INSERT INTO entities(name,entity_type,status) VALUES (?,?,"Active")', (name, entity_type))

        today = date.today()
        tasks = [
            ('Bank Reconciliation - MPPL',    'Complete current month BRS and upload statement', 'Bank Reconciliation', 5, 3, 5, 4, 'High',     4,  'In Progress'),
            ('GST Working - Matterhorn',      'Prepare GSTR-1 and GSTR-3B working',              'GST',                 1, 3, 6, 4, 'Critical', 6,  'Assigned'),
            ('Ledger Scrutiny - All Entities','Review sundry creditors and debtors',             'Ledger Scrutiny',     None, 3, 4, 3, 'High', 10, 'In Progress'),
            ('Vendor Bill Processing',        'Check and process pending vendor bills',          'Vendor Payment',      3, 3, 6, 4, 'Medium',   3,  'Assigned'),
        ]
        for i, t in enumerate(tasks, 1):
            c.execute('INSERT INTO tasks(task_code,title,description,category,entity_id,assigned_by,assigned_to,reviewer_id,priority,start_date,target_date,expected_hours,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (f'TASK-{i:04d}', t[0], t[1], t[2], t[3], t[4], t[5], t[6], t[7],
                       today.isoformat(), (today + timedelta(days=t[8])).isoformat(), t[8], t[9]))

        rem = [
            (5, 'GST Return',  '2026-27', (today + timedelta(days=8)).isoformat(),  'Monthly', 5, 4, 'Critical', 2, 'Upcoming'),
            (6, 'Form 11',     '2026-27', (today + timedelta(days=15)).isoformat(), 'Annual',  5, 4, 'High',     2, 'Upcoming'),
            (1, 'DSC Renewal', '2026-27', (today + timedelta(days=25)).isoformat(), 'Annual',  3, 4, 'High',     2, 'Upcoming'),
        ]
        c.executemany('INSERT INTO compliance_reminders(entity_id,compliance_type,financial_year,due_date,frequency,responsible_user_id,reviewer_id,priority,escalation_user_id,status) VALUES (?,?,?,?,?,?,?,?,?,?)', rem)

    con.commit(); con.close()
    ensure_user_columns()
    sync_master_data()


def ensure_user_columns():
    """Add password-change tracking columns to an older worktrack.db that predates them."""
    con = db(); c = con.cursor()
    cols = {r['name'] for r in c.execute('PRAGMA table_info(users)').fetchall()}
    if 'must_change_password' not in cols:
        c.execute('ALTER TABLE users ADD COLUMN must_change_password INTEGER DEFAULT 0')
    if 'password_changed_at' not in cols:
        c.execute('ALTER TABLE users ADD COLUMN password_changed_at TEXT')
    con.commit(); con.close()


def ensure_slots(user_id: int, slot_date: str):
    """Create office-day slots and auto-place priority work."""
    # Remove older MVP slot labels for this day so the page stays clean.
    placeholders = ','.join(['?'] * len(OFFICE_SLOT_LABELS))
    ex(f'DELETE FROM daily_slots WHERE user_id=? AND slot_date=? AND slot_label NOT IN ({placeholders})',
       tuple([user_id, slot_date] + OFFICE_SLOT_LABELS))

    existing = q('SELECT slot_label FROM daily_slots WHERE user_id=? AND slot_date=?', (user_id, slot_date))
    existing_labels = {r['slot_label'] for r in existing}
    for label, s_time, e_time in DEFAULT_SLOTS:
        if label not in existing_labels:
            default_status = 'Break' if label == 'Lunch Break' else 'Planned'
            ex('INSERT OR IGNORE INTO daily_slots(user_id,slot_date,slot_label,start_time,end_time,status) VALUES (?,?,?,?,?,?)',
               (user_id, slot_date, label, s_time, e_time, default_status))

    # Auto-plan only empty work slots. Lunch remains unassigned.
    slots = q('''SELECT * FROM daily_slots
                 WHERE user_id=? AND slot_date=? AND slot_label!='Lunch Break'
                 ORDER BY start_time''', (user_id, slot_date))
    already = {r['task_id'] for r in slots if r['task_id']}
    tasks = q('''SELECT id,priority FROM tasks
                 WHERE assigned_to=? AND status NOT IN ('Completed','Cancelled')
                 ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                                        WHEN 'Medium' THEN 3 ELSE 4 END,
                          target_date, id''', (user_id,))
    candidates = [t for t in tasks if t['id'] not in already]
    high_priority = [t for t in candidates if t['priority'] in ('Critical', 'High')]

    first_half = [s for s in slots if s['slot_label'] in ('Priority Block 1', 'Priority Block 2') and not s['task_id']]
    afternoon = [s for s in slots if s['slot_label'] in ('Execution Block', 'Closure Block') and not s['task_id']]

    used = set()
    for slot in first_half:
        pick = next((t for t in high_priority if t['id'] not in used), None)
        if pick:
            ex('UPDATE daily_slots SET task_id=?,status=? WHERE id=?', (pick['id'], 'Planned', slot['id']))
            used.add(pick['id'])

    remaining = [t for t in candidates if t['id'] not in used]
    for slot in afternoon:
        pick = remaining.pop(0) if remaining else None
        if pick:
            ex('UPDATE daily_slots SET task_id=?,status=? WHERE id=?', (pick['id'], 'Planned', slot['id']))


def sync_master_data():
    """Keep entity and role naming current even if an old worktrack.db already exists."""
    con = db(); c = con.cursor()
    for idx, (name, entity_type) in enumerate(ENTITY_MASTER, start=1):
        row = c.execute('SELECT id FROM entities WHERE id=?', (idx,)).fetchone()
        if row:
            c.execute('UPDATE entities SET name=?, entity_type=?, status="Active" WHERE id=?', (name, entity_type, idx))
        else:
            c.execute('INSERT INTO entities(id,name,entity_type,status) VALUES (?,?,?,"Active")', (idx, name, entity_type))
    c.execute('UPDATE users SET role="Assignor" WHERE role IN ("Team Lead", "Task Owner")')
    c.execute('UPDATE users SET role="Assignee" WHERE role IN ("Team Member", "Executor")')
    con.commit(); con.close()


# ──────────────────────────────────────────────────────────────────────────────
# Brand assets (inline SVG so the app stays offline-capable)
# ──────────────────────────────────────────────────────────────────────────────
LOGO_SVG = '''<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" width="40" height="40" aria-hidden="true">
  <rect width="48" height="48" rx="11" fill="#1e3a8a"/>
  <rect x="19" y="9" width="10" height="3.5" rx="1.5" fill="#cbd5e1"/>
  <rect x="11" y="11" width="26" height="29" rx="2.5" fill="#ffffff"/>
  <path d="M15.5 19 L18 21.5 L23 16.5" stroke="#10b981" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="26" y1="19.5" x2="33" y2="19.5" stroke="#cbd5e1" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M15.5 26 L18 28.5 L23 23.5" stroke="#10b981" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="26" y1="26.5" x2="33" y2="26.5" stroke="#cbd5e1" stroke-width="1.6" stroke-linecap="round"/>
  <path d="M15.5 33 L18 35.5 L23 30.5" stroke="#10b981" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <line x1="26" y1="33.5" x2="33" y2="33.5" stroke="#cbd5e1" stroke-width="1.6" stroke-linecap="round"/>
  <circle cx="35" cy="36" r="6.2" fill="#10b981" stroke="#0a1628" stroke-width="1.6"/>
  <path d="M32 36 L34.2 38.2 L38 33.8" stroke="#ffffff" stroke-width="1.9" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

def nav_icon(name: str) -> str:
    icons = {
        'dashboard':  '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/></svg>',
        'myday':      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 14"/></svg>',
        'tasks':      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 11 12 14 22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>',
        'daily':      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>',
        'compliance': '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>',
        'reports':    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>',
        'masters':    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="8" r="4"/><path d="M4 21v-2a4 4 0 0 1 4-4h8a4 4 0 0 1 4 4v2"/></svg>',
        'logout':     '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>',
    }
    return icons.get(name, '')

# ──────────────────────────────────────────────────────────────────────────────
# CSS — brand-aligned design system
# ──────────────────────────────────────────────────────────────────────────────
CSS = '''<style>
:root{
  --bg:#f1f5f9; --surface:#ffffff;
  --navy:#0a1628; --navy-2:#0f1f3d; --navy-3:#1e293b;
  --emerald:#10b981; --emerald-2:#059669; --emerald-soft:#ecfdf5;
  --text:#0f172a; --muted:#64748b; --muted-2:#94a3b8;
  --border:#e2e8f0; --border-2:#f1f5f9;
  --warn:#f59e0b; --warn-soft:#fef3c7;
  --danger:#dc2626; --danger-soft:#fee2e2;
  --info:#0ea5e9; --info-soft:#e0f2fe;
  --shadow-sm:0 1px 2px rgba(15,23,42,.06);
  --shadow:0 4px 16px rgba(15,23,42,.06), 0 1px 2px rgba(15,23,42,.04);
  --shadow-lg:0 10px 25px rgba(15,23,42,.08);
  --radius:14px; --radius-lg:18px;
}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:'Inter','Segoe UI',system-ui,-apple-system,Arial,sans-serif;
  background:var(--bg);color:var(--text);font-size:14.5px;line-height:1.5;-webkit-font-smoothing:antialiased}
a{text-decoration:none;color:inherit}

/* ─── Login ─── */
.login{min-height:100vh;display:grid;place-items:center;
  background:radial-gradient(circle at 20% 20%,#1e3a8a 0%,#0a1628 55%,#020617 100%)}
.login form{width:min(440px,92vw);background:#fff;border-radius:24px;padding:38px 36px;
  box-shadow:0 30px 70px rgba(0,0,0,.4)}
.login .brandrow{display:flex;align-items:center;gap:14px;margin-bottom:6px}
.login .brandrow .name{font-size:26px;font-weight:800;letter-spacing:-.5px}
.login .brandrow .name .accent{color:var(--emerald)}
.login .subtitle{color:var(--muted);font-size:13.5px;margin-bottom:22px}

/* ─── App shell ─── */
.app{display:flex;min-height:100vh}
.side{width:260px;background:var(--navy);color:#e2e8f0;padding:22px 14px;
  display:flex;flex-direction:column;gap:6px;position:sticky;top:0;height:100vh}
.brand{display:flex;align-items:center;gap:12px;padding:6px 8px 4px}
.brand .name{font-size:22px;font-weight:800;letter-spacing:-.5px;line-height:1}
.brand .name .accent{color:var(--emerald)}
.brand .tagline{font-size:11px;color:#94a3b8;margin-top:4px;letter-spacing:.3px;text-transform:uppercase}
.divider{height:1px;background:rgba(255,255,255,.08);margin:14px 4px}
.usercard{padding:10px 12px;border-radius:12px;background:rgba(255,255,255,.04);margin:0 4px 8px}
.usercard .who{font-weight:700;font-size:14px;color:#fff}
.usercard .role{font-size:11.5px;color:#94a3b8;text-transform:uppercase;letter-spacing:.4px;margin-top:2px}
.nav{display:flex;flex-direction:column;gap:3px;padding:0 4px;flex:1;overflow-y:auto}
.nav a{display:flex;align-items:center;gap:11px;padding:10px 12px;border-radius:11px;
  color:#cbd5e1;font-size:14px;font-weight:500;transition:all .15s}
.nav a:hover{background:rgba(255,255,255,.06);color:#fff}
.nav a.active{background:rgba(16,185,129,.12);color:#fff;border-left:3px solid var(--emerald);padding-left:9px}
.nav svg{flex-shrink:0;opacity:.85}
.foot{padding:10px 4px 4px;font-size:11px;color:#64748b;text-align:center}

.main{flex:1;padding:28px 32px;min-width:0}
.top{display:flex;justify-content:space-between;align-items:center;gap:14px;margin-bottom:22px;flex-wrap:wrap}
.top h1{margin:0;font-size:24px;font-weight:800;letter-spacing:-.4px}
.top .sub{color:var(--muted);font-size:13.5px;margin-top:3px}
.top .actions{display:flex;gap:8px;flex-wrap:wrap}

/* ─── Cards & grids ─── */
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius-lg);
  padding:20px;box-shadow:var(--shadow);margin-bottom:16px}
.card h2{margin:0 0 14px;font-size:16px;font-weight:700;letter-spacing:-.2px}
.card h3{margin:0 0 10px;font-size:14px;font-weight:700;color:var(--muted-2);text-transform:uppercase;letter-spacing:.5px}
.grid{display:grid;gap:16px}
.kpis{grid-template-columns:repeat(4,1fr)}
.split{grid-template-columns:2fr 1fr}
.split-3{grid-template-columns:repeat(3,1fr)}

.kpi{position:relative;overflow:hidden}
.kpi .label{color:var(--muted);font-size:12.5px;font-weight:600;text-transform:uppercase;letter-spacing:.4px}
.kpi .num{font-size:34px;font-weight:800;letter-spacing:-1px;margin-top:6px;line-height:1}
.kpi .delta{font-size:12px;color:var(--muted);margin-top:6px}
.kpi.k-blue::before, .kpi.k-amber::before, .kpi.k-green::before, .kpi.k-red::before{
  content:'';position:absolute;top:0;left:0;right:0;height:4px}
.kpi.k-blue::before{background:#0ea5e9}
.kpi.k-amber::before{background:#f59e0b}
.kpi.k-green::before{background:#10b981}
.kpi.k-red::before{background:#dc2626}

/* ─── Buttons & forms ─── */
.btn{border:0;border-radius:10px;padding:9px 14px;font-weight:700;font-size:13.5px;
  background:#eef2ff;color:#1e40af;cursor:pointer;display:inline-flex;align-items:center;gap:6px;
  transition:transform .05s, box-shadow .15s}
.btn:hover{box-shadow:var(--shadow-sm)}
.btn:active{transform:translateY(1px)}
.btn.primary{background:var(--navy);color:#fff}
.btn.primary:hover{background:var(--navy-2)}
.btn.success{background:var(--emerald);color:#fff}
.btn.success:hover{background:var(--emerald-2)}
.btn.ghost{background:transparent;color:var(--muted);border:1px solid var(--border)}
.btn.ghost:hover{background:var(--border-2);color:var(--text)}
.btn.danger{background:var(--danger-soft);color:var(--danger)}
.btn.sm{padding:6px 10px;font-size:12.5px}

input,select,textarea{width:100%;border:1px solid var(--border);border-radius:10px;
  padding:10px 12px;font:inherit;background:#fff;color:var(--text);transition:border-color .15s,box-shadow .15s}
input:focus,select:focus,textarea:focus{outline:0;border-color:var(--emerald);box-shadow:0 0 0 3px rgba(16,185,129,.15)}
textarea{min-height:80px;resize:vertical}
label{font-size:12.5px;font-weight:700;color:var(--muted);margin:10px 0 5px;display:block;
  text-transform:uppercase;letter-spacing:.3px}
.form{display:grid;grid-template-columns:repeat(2,1fr);gap:14px 16px}
.full{grid-column:1/-1}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.row>*{flex:1;min-width:140px}

/* ─── Tables ─── */
.tablewrap{overflow-x:auto;margin:0 -4px}
.table{width:100%;border-collapse:collapse}
.table th,.table td{padding:12px 14px;border-bottom:1px solid var(--border-2);text-align:left;vertical-align:top;font-size:13.5px}
.table th{font-size:11.5px;text-transform:uppercase;color:var(--muted);font-weight:700;letter-spacing:.4px;
  background:#f8fafc;border-bottom:1px solid var(--border)}
.table tbody tr:hover{background:#f8fafc}
.table .strong{font-weight:700}

/* ─── Badges (status / priority pill colours) ─── */
.badge{display:inline-block;border-radius:999px;padding:3px 10px;font-size:11.5px;font-weight:700;
  background:var(--border-2);color:var(--muted);letter-spacing:.2px;white-space:nowrap}
.badge.Completed{background:var(--emerald-soft);color:var(--emerald-2)}
.badge.Critical,.badge.Overdue,.badge.Delayed{background:var(--danger-soft);color:var(--danger)}
.badge.High,.badge.Waiting,.badge\\ for\\ Documents{background:var(--warn-soft);color:#92400e}
.badge.Medium,.badge.InProgress,.badge.In\\ Progress{background:var(--info-soft);color:#0369a1}
.badge.Low{background:var(--border-2);color:var(--muted)}
.badge.Assigned{background:#ede9fe;color:#6d28d9}

/* ─── My Day slot cards ─── */
.slot{border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;
  margin-bottom:10px;background:#fff;transition:border-color .15s, box-shadow .15s}
.slot:hover{border-color:#cbd5e1}
.slot.now{border:2px solid var(--emerald);background:var(--emerald-soft);box-shadow:0 0 0 3px rgba(16,185,129,.1)}
.slot.done{background:#f8fafc;opacity:.85}
.slot .shead{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.slot .stime{font-size:13px;color:var(--muted);font-weight:700;letter-spacing:.3px}
.slot .stitle{font-size:15px;font-weight:700;color:var(--text)}
.slot .pill-now{background:var(--emerald);color:#fff;padding:2px 9px;border-radius:999px;font-size:10.5px;
  font-weight:800;letter-spacing:.5px;text-transform:uppercase;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.65}}
.slot .sbody{display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;align-items:end}

.day-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.day-summary .pill{background:#fff;border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px}
.day-summary .pill .l{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px;font-weight:700}
.day-summary .pill .v{font-size:22px;font-weight:800;margin-top:3px;letter-spacing:-.5px}

/* ─── Daily & misc ─── */
.daily{border:1px solid var(--border);border-radius:var(--radius);padding:14px;margin:10px 0;background:#fbfdff}
.flash{padding:12px 16px;border-radius:var(--radius);background:var(--emerald-soft);color:var(--emerald-2);
  margin-bottom:14px;font-weight:600}
pre{background:#f8fafc;border-radius:8px;padding:8px;font-size:12px;white-space:pre-wrap;margin:0}

/* ─── Simplified My Day planning ─── */
.office-day-note{background:linear-gradient(135deg,#ecfdf5,#eef2ff);border:1px solid var(--border);border-radius:var(--radius-lg);padding:16px 18px;margin-bottom:16px;color:var(--navy)}
.office-day-note b{color:var(--emerald-2)}
.myday-layout{display:grid;grid-template-columns:1.7fr .9fr;gap:16px;align-items:start}
.slot-compact{display:grid;grid-template-columns:120px 1.4fr 1fr 1.1fr auto;gap:10px;align-items:end;border:1px solid var(--border);border-radius:16px;padding:14px;margin-bottom:10px;background:#fff}
.slot-compact.firsthalf{border-left:5px solid var(--emerald);background:#fbfffd}
.slot-compact.lunch{background:#fffbeb;border-left:5px solid var(--warn)}
.slot-compact.afternoon{border-left:5px solid #0ea5e9}
.slot-compact.now{box-shadow:0 0 0 3px rgba(16,185,129,.14);border-color:var(--emerald)}
.slot-time{font-weight:800;color:var(--navy);font-size:13px}
.slot-label{font-size:12px;color:var(--muted);text-transform:uppercase;font-weight:800;letter-spacing:.4px;margin-top:4px}
.priority-card{border:1px solid var(--border);border-radius:14px;padding:12px 14px;margin-bottom:10px;background:#fff}
.priority-card .ptitle{font-weight:800;color:var(--text)}
.priority-card .pmeta{font-size:12.5px;color:var(--muted);margin-top:3px}
@media(max-width:960px){.myday-layout{grid-template-columns:1fr}.slot-compact{grid-template-columns:1fr}.slot-compact .btn{width:100%;justify-content:center}}

/* ─── Mobile ─── */
@media(max-width:960px){
  .app{display:block}
  .side{width:auto;position:relative;height:auto;flex-direction:row;align-items:center;
    flex-wrap:wrap;padding:14px;gap:10px}
  .brand{flex:1}
  .divider,.usercard,.foot{display:none}
  .nav{flex-direction:row;flex-wrap:wrap;gap:4px;padding:0;flex:1 0 100%}
  .nav a{padding:8px 10px;font-size:12px}
  .nav a span:not(.tagline){display:none}
  .main{padding:18px}
  .kpis,.split,.split-3,.form,.day-summary{grid-template-columns:1fr 1fr}
  .slot .sbody{grid-template-columns:1fr}
  .table th:nth-child(4),.table td:nth-child(4),.table th:nth-child(8),.table td:nth-child(8){display:none}
}
</style>'''


# ──────────────────────────────────────────────────────────────────────────────
# Layout
# ──────────────────────────────────────────────────────────────────────────────
def layout(user, title, body, actions='', subtitle='', active=''):
    nav_items = [
        ('/',          'Dashboard',     'dashboard'),
        ('/tasks',     'Tasks',         'tasks'),
        ('/daily',     'Daily Update',  'daily'),
        ('/compliance','Compliance',    'compliance'),
        ('/reports',   'Reports',       'reports'),
        ('/masters',   'Masters',       'masters'),
        ('/logout',    'Logout',        'logout'),
    ]
    nav = ''.join(
        f'<a href="{p}" class="{"active" if active==key else ""}">{nav_icon(key)}<span>{n}</span></a>'
        for p, n, key in nav_items
    )
    sub_html = f'<div class="sub">{h(subtitle)}</div>' if subtitle else ''
    return f'''<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)} · WorkTrack</title>{CSS}</head>
<body><div class="app">
  <aside class="side">
    <div class="brand">
      {LOGO_SVG}
      <div>
        <div class="name">Work<span class="accent">Track</span></div>
        <div class="tagline">MPPL Office · Tasks &amp; Compliances</div>
      </div>
    </div>
    <div class="divider"></div>
    <div class="usercard">
      <div class="who">{h(user["name"])}</div>
      <div class="role">{h(user["role"])} · {h(user["department"])}</div>
    </div>
    <nav class="nav">{nav}</nav>
    <div class="foot">Copyrights reserved with MPPL</div>
  </aside>
  <main class="main">
    <div class="top">
      <div>
        <h1>{h(title)}</h1>
        {sub_html}
      </div>
      <div class="actions">{actions}</div>
    </div>
    {body}
  </main>
</div></body></html>'''


def opts(vals, selected=''):
    return ''.join(f'<option {"selected" if str(v)==str(selected) else ""}>{h(v)}</option>' for v in vals)

def optrows(rows, selected='', show_role=True):
    out = []
    for r in rows:
        keys = r.keys()
        suffix = f" — {h(r['role'])}" if show_role and 'role' in keys else ''
        sel = 'selected' if str(r['id']) == str(selected) else ''
        out.append(f'<option value="{r["id"]}" {sel}>{h(r["name"])}{suffix}</option>')
    return ''.join(out)


# ──────────────────────────────────────────────────────────────────────────────
# HTTP Handler
# ──────────────────────────────────────────────────────────────────────────────
class App(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s - %s' % (self.address_string(), fmt % args))

    def send(self, htmlstr, status=200, ctype='text/html', extra=None):
        b = htmlstr.encode('utf-8') if isinstance(htmlstr, str) else htmlstr
        self.send_response(status)
        self.send_header('Content-Type', ctype + '; charset=utf-8')
        self.send_header('Content-Length', str(len(b)))
        if extra:
            for k, v in extra.items(): self.send_header(k, v)
        self.end_headers(); self.wfile.write(b)

    def redirect(self, path, cookie=None):
        self.send_response(302); self.send_header('Location', path)
        if cookie: self.send_header('Set-Cookie', cookie)
        self.end_headers()

    def body(self):
        n = int(self.headers.get('Content-Length', 0))
        raw = self.rfile.read(n).decode('utf-8')
        return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}

    def user(self):
        c = cookies.SimpleCookie(self.headers.get('Cookie'))
        sid = c.get('sid'); uid = SESSIONS.get(sid.value) if sid else None
        return q('SELECT * FROM users WHERE id=?', (uid,), True) if uid else None

    def require(self):
        u = self.user()
        if not u:
            self.redirect('/login'); return None
        return u

    # ── Routing ────────────────────────────────────────────────────────────
    def do_GET(self):
        init_db()
        path = urlparse(self.path).path
        if path == '/login': return self.login()
        if path == '/logout':
            return self.redirect('/login', 'sid=; Max-Age=0; Path=/')
        u = self.require()
        if not u: return
        if path == '/change-password':
            return self.change_password_page(u)
        if u['must_change_password']:
            return self.redirect('/change-password')
        routes = {
            '/':            self.dashboard,
            '/myday':       self.myday,
            '/tasks':       self.tasks,
            '/tasks/new':   self.new_task,
            '/daily':       self.daily,
            '/compliance':  self.compliance,
            '/reports':     self.reports,
            '/reports/tasks.csv': self.csv,
            '/reports/daily.csv': self.daily_csv,
            '/employees/template.csv': self.employee_template_csv,
            '/masters':     self.masters,
        }
        if path.startswith('/employee-progress/') and path.split('/')[-1].isdigit():
            return self.employee_progress(u, int(path.split('/')[-1]))
        if path.startswith('/tasks/') and path.split('/')[-1].isdigit():
            return self.task_detail(u, int(path.split('/')[-1]))
        return routes.get(path, self.notfound)(u) if path in routes else self.notfound(u)

    def do_POST(self):
        init_db()
        path = urlparse(self.path).path
        if path == '/login': return self.post_login()
        u = self.require()
        if not u: return
        if path == '/change-password': return self.post_change_password(u)
        if u['must_change_password']:
            return self.redirect('/change-password')
        if path == '/tasks/new':      return self.post_task(u)
        if path.startswith('/tasks/') and path.endswith('/update'): return self.post_update(u, int(path.split('/')[2]))
        if path.startswith('/tasks/') and path.endswith('/review'): return self.post_review(u, int(path.split('/')[2]))
        if path == '/daily':          return self.post_daily(u)
        if path == '/employees/new':  return self.post_employee(u)
        if path == '/employees/import': return self.post_employee_import(u)
        if path.startswith('/employees/') and path.endswith('/update'):
            return self.post_employee_update(u, int(path.split('/')[2]))
        if path.startswith('/employees/') and path.endswith('/delete'):
            return self.post_employee_delete(u, int(path.split('/')[2]))
        if path == '/entities/new':    return self.post_entity(u)
        if path == '/compliance':     return self.post_compliance(u)
        if path.startswith('/compliance/') and path.endswith('/complete'):
            return self.post_comp_done(u, int(path.split('/')[2]))
        if path == '/myday':          return self.post_myday(u)
        if path.startswith('/myday/quick/') and path.endswith('/done'):
            return self.post_slot_done(u, int(path.split('/')[3]))
        return self.notfound(u)

    # ── Login ──────────────────────────────────────────────────────────────
    def login(self):
        return self.send(f'''<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Sign in · WorkTrack</title>{CSS}</head>
<body class="login"><form method="post">
  <div class="brandrow">{LOGO_SVG}<div class="name">Work<span class="accent">Track</span></div></div>
  <div class="subtitle">MPPL Office · Tasks &amp; Compliances</div>
  <label>Email</label>
  <input name="email" autofocus>
  <label>Password</label>
  <input name="password" type="password">
  <br><br>
  <button class="btn primary" style="width:100%;justify-content:center;padding:12px">Sign in</button>

  <p style="margin-top:18px;text-align:center">
    <a href="#" onclick="alert('For password reset or any technical assistance,\\n\\nPlease contact Sapan Pati (System Administrator).'); return false;"
       style="color:#2563eb;font-size:13px;text-decoration:underline;font-weight:600;">
       Forgot Password?
    </a>
  </p>

  <p style="color:#64748b;font-size:12px;text-align:center;margin-top:8px">
    Please contact <b>Sapan Pati (System Administrator)</b><br>
    for any technical support.
  </p>
</form></body></html>''')

    def post_login(self):
        f = self.body()
        user = q('SELECT * FROM users WHERE email=? AND status="Active"',
                 (f.get('email', '').lower().strip(),), True)
        if user and user['password_hash'] == pw(f.get('password', '')):
            sid = secrets.token_urlsafe(24); SESSIONS[sid] = user['id']
            cookie = f'sid={sid}; Path=/; HttpOnly; SameSite=Lax'
            if user['must_change_password']:
                return self.redirect('/change-password', cookie)
            return self.redirect('/', cookie)
        return self.redirect('/login')

    # ── Change Password (first-login enforcement) ────────────────────────────
    def change_password_page(self, u, error=''):
        err_html = f'<p style="color:#dc2626;font-size:13px;margin-top:14px">{h(error)}</p>' if error else ''
        return self.send(f'''<!doctype html><html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Change Password · WorkTrack</title>{CSS}</head>
<body class="login"><form method="post" action="/change-password">
  <div class="brandrow">{LOGO_SVG}<div class="name">Work<span class="accent">Track</span></div></div>
  <div class="subtitle">For security, please set a new password before continuing.</div>
  <label>Current Password</label>
  <input name="current_password" type="password" autofocus>
  <label>New Password</label>
  <input name="new_password" type="password">
  <label>Confirm New Password</label>
  <input name="confirm_password" type="password">
  {err_html}
  <br><br>
  <button class="btn primary" style="width:100%;justify-content:center;padding:12px">Change Password</button>
</form></body></html>''')

    def post_change_password(self, u):
        f = self.body()
        current = f.get('current_password', '')
        new = f.get('new_password', '')
        confirm = f.get('confirm_password', '')
        if pw(current) != u['password_hash']:
            return self.change_password_page(u, 'Current password is incorrect.')
        if new != confirm:
            return self.change_password_page(u, 'New passwords do not match.')
        if len(new) < 8:
            return self.change_password_page(u, 'New password must be at least 8 characters long.')
        if pw(new) == u['password_hash']:
            return self.change_password_page(u, 'New password cannot be the same as the current password.')
        ex('UPDATE users SET password_hash=?, must_change_password=0, password_changed_at=? WHERE id=?',
           (pw(new), datetime.now().isoformat(timespec='seconds'), u['id']))
        return self.redirect('/')

    # ── Dashboard ──────────────────────────────────────────────────────────
    def dashboard(self, u):
        scope = 'WHERE assigned_to=?' if u['role'] in ('Assignee','Team Member') else ''
        args = (u['id'],) if scope else ()
        total = q(f'SELECT COUNT(*) c FROM tasks {scope}', args, True)['c']
        pending = q(f"SELECT COUNT(*) c FROM tasks {scope + (' AND' if scope else 'WHERE')} status NOT IN ('Completed','Cancelled')", args, True)['c']
        completed = q(f"SELECT COUNT(*) c FROM tasks {scope + (' AND' if scope else 'WHERE')} status='Completed'", args, True)['c']
        overdue = q(f"SELECT COUNT(*) c FROM tasks {scope + (' AND' if scope else 'WHERE')} status!='Completed' AND target_date < ?",
                    args + (date.today().isoformat(),), True)['c']

        tasks = q('''SELECT t.*,e.name entity,u.name owner FROM tasks t
                     LEFT JOIN entities e ON e.id=t.entity_id LEFT JOIN users u ON u.id=t.assigned_to
                     WHERE (?='All' OR t.assigned_to=?)
                     ORDER BY CASE t.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                                              WHEN 'Medium' THEN 3 ELSE 4 END, target_date LIMIT 10''',
                  ('All' if u['role'] not in ('Assignee','Team Member') else 'Mine', u['id']))
        rem = q('''SELECT c.*,e.name entity,u.name owner FROM compliance_reminders c
                   LEFT JOIN entities e ON e.id=c.entity_id LEFT JOIN users u ON u.id=c.responsible_user_id
                   WHERE c.status!='Completed' ORDER BY due_date LIMIT 6''')

        k_data = [('Total Tasks', total, 'k-blue'), ('Pending', pending, 'k-amber'),
                  ('Completed', completed, 'k-green'), ('Overdue', overdue, 'k-red')]
        k = ''.join(
            f'<div class="card kpi {cls}"><div class="label">{n}</div>'
            f'<div class="num">{v}</div></div>'
            for n, v, cls in k_data)

        rows = ''.join(
            f'<tr><td><a href="/tasks/{t["id"]}" class="strong">{h(t["task_code"])}</a>'
            f'<br><span style="color:var(--muted);font-size:12.5px">{h(t["title"])}</span></td>'
            f'<td>{h(t["entity"])}</td><td>{h(t["owner"])}</td>'
            f'<td><span class="badge {h(t["priority"])}">{h(t["priority"])}</span></td>'
            f'<td><span class="badge {h(t["status"])}">{h(t["status"])}</span></td>'
            f'<td>{h(t["target_date"])}</td></tr>'
            for t in tasks)

        rr = ''.join(
            f'<div style="padding:10px 0;border-bottom:1px solid var(--border-2)">'
            f'<div class="strong">{h(r["compliance_type"])}</div>'
            f'<div style="color:var(--muted);font-size:12.5px;margin-top:2px">'
            f'{h(r["entity"])} · Due {h(r["due_date"])} · {h(r["owner"])}</div></div>'
            for r in rem)

        employee_panel = ''
        if u['role'] not in ('Assignee','Team Member'):
            emp_rows = q('''SELECT u.id,u.name,u.role,u.department,
                            COUNT(t.id) total,
                            SUM(CASE WHEN t.status='Assigned' THEN 1 ELSE 0 END) assigned,
                            SUM(CASE WHEN t.status IN ('In Progress','Waiting','Submitted for Review','Rework Required','Delayed') THEN 1 ELSE 0 END) active,
                            SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) completed,
                            SUM(CASE WHEN t.status!='Completed' AND t.target_date<date('now') THEN 1 ELSE 0 END) overdue,
                            COALESCE((SELECT COUNT(*) FROM daily_sheet_entries ds WHERE ds.user_id=u.id AND ds.entry_date=date('now')),0) today_updates
                            FROM users u
                            LEFT JOIN tasks t ON t.assigned_to=u.id
                            WHERE u.status='Active' AND u.role IN ('Assignee','Team Member','Reviewer','Assignor')
                            GROUP BY u.id
                            ORDER BY overdue DESC, active DESC, u.name''')
            emp_html = ''.join(
                f'<tr><td class="strong">{h(e["name"])}<br><span style="color:var(--muted);font-size:12px">{h(e["role"])} · {h(e["department"])}</span></td>'
                f'<td>{h(e["total"] or 0)}</td>'
                f'<td><span class="badge Assigned">{h(e["assigned"] or 0)}</span></td>'
                f'<td><span class="badge In\\ Progress">{h(e["active"] or 0)}</span></td>'
                f'<td><span class="badge Completed">{h(e["completed"] or 0)}</span></td>'
                f'<td><span class="badge Overdue">{h(e["overdue"] or 0)}</span></td>'
                f'<td>{h(e["today_updates"] or 0)} update(s)</td>'
                f'<td><a class="btn sm primary" href="/employee-progress/{e["id"]}">View</a> '
                f'<a class="btn sm ghost" href="/daily?user_id={e["id"]}">View Daily</a></td></tr>'
                for e in emp_rows)
            employee_panel = f'''
            <div class="card tablewrap" style="margin-top:18px">
              <h2>Employee-wise Work Control Panel</h2>
              <p style="color:var(--muted);font-size:13.5px;margin-top:-6px">Live assignee-wise control for Admin, Management, Assignor and Reviewer.</p>
              <table class="table">
                <tr><th>Employee</th><th>Total</th><th>Assigned</th><th>Active</th><th>Completed</th><th>Overdue</th><th>Today</th><th>Control</th></tr>
                {emp_html or '<tr><td colspan="8" style="color:var(--muted);text-align:center;padding:24px">No active employees found.</td></tr>'}
              </table>
            </div>'''

        body = f'''
        <section class="grid kpis">{k}</section>
        {employee_panel}
        <section class="grid split" style="margin-top:18px">
          <div class="card">
            <h2>Priority Work Queue</h2>
            <div class="tablewrap"><table class="table">
              <tr><th>Task</th><th>Entity</th><th>Owner</th><th>Priority</th><th>Status</th><th>Due</th></tr>
              {rows or '<tr><td colspan="6" style="color:var(--muted);text-align:center;padding:30px">No active tasks.</td></tr>'}
            </table></div>
          </div>
          <div>
            <div class="card">
              <h2>Daily Update</h2>
              <p style="color:var(--muted);font-size:13.5px">Open sheet format: Task, From Time, To Time, Status and Remarks. Export the daily report for management.</p>
              <div style="margin-top:10px"><a href="/daily" class="btn success sm">Update Daily Sheet →</a></div>
            </div>
            <div class="card">
              <h2>Compliance Due Soon</h2>
              {rr or '<p style="color:var(--muted)">No open reminders.</p>'}
            </div>
          </div>
        </section>
        '''
        actions = '<a class="btn primary" href="/tasks/new">+ Add Task</a> <a class="btn success" href="/daily">Update Today</a>'
        return self.send(layout(u, 'Dashboard', body, actions,
                                subtitle=f'Good {("morning" if datetime.now().hour < 12 else "afternoon" if datetime.now().hour < 17 else "evening")}, {u["name"]}',
                                active='dashboard'))

    def employee_progress(self, u, emp_id):
        """Detailed employee/assignee progress view for control users."""
        if u['role'] in ('Assignee','Team Member') and u['id'] != emp_id:
            return self.redirect('/')
        emp = q('SELECT * FROM users WHERE id=?', (emp_id,), True)
        if not emp:
            return self.notfound(u)
        totals = q('''SELECT COUNT(*) total,
                    SUM(CASE WHEN status='Assigned' THEN 1 ELSE 0 END) assigned,
                    SUM(CASE WHEN status IN ('In Progress','Waiting','Submitted for Review','Rework Required','Delayed') THEN 1 ELSE 0 END) active,
                    SUM(CASE WHEN status='Completed' THEN 1 ELSE 0 END) completed,
                    SUM(CASE WHEN status!='Completed' AND target_date<date('now') THEN 1 ELSE 0 END) overdue
                    FROM tasks WHERE assigned_to=?''', (emp_id,), True)
        task_rows = q('''SELECT t.*,e.name entity,r.name reviewer FROM tasks t
                         LEFT JOIN entities e ON e.id=t.entity_id
                         LEFT JOIN users r ON r.id=t.reviewer_id
                         WHERE t.assigned_to=?
                         ORDER BY CASE t.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END,
                                  t.target_date''', (emp_id,))
        daily_rows = q('''SELECT d.*,t.task_code,t.title assigned_title FROM daily_sheet_entries d
                          LEFT JOIN tasks t ON t.id=d.task_id
                          WHERE d.user_id=? AND d.entry_date>=date('now','-7 day')
                          ORDER BY d.entry_date DESC,d.from_time,d.id''', (emp_id,))
        k_data = [('Total', totals['total'] or 0, 'k-blue'), ('Assigned', totals['assigned'] or 0, 'k-amber'),
                  ('Active', totals['active'] or 0, 'k-blue'), ('Completed', totals['completed'] or 0, 'k-green'),
                  ('Overdue', totals['overdue'] or 0, 'k-red')]
        kpis = ''.join(f'<div class="card kpi {cls}"><div class="label">{h(n)}</div><div class="num">{h(v)}</div></div>' for n,v,cls in k_data)
        task_html = ''.join(
            f'<tr><td><a class="strong" href="/tasks/{t["id"]}">{h(t["task_code"])}</a><br><span style="color:var(--muted);font-size:12px">{h(t["title"])}</span></td>'
            f'<td>{h(t["entity"])}</td><td><span class="badge {h(t["priority"])}">{h(t["priority"])}</span></td>'
            f'<td><span class="badge {h(t["status"])}">{h(t["status"])}</span></td><td>{h(t["target_date"])}</td><td>{h(t["reviewer"])}</td></tr>'
            for t in task_rows)
        daily_html = ''.join(
            f'<tr><td>{h(d["entry_date"])}</td><td>{h(d["from_time"])} - {h(d["to_time"])}</td>'
            f'<td>{h(d["task_text"] or ((d["task_code"] or "") + " · " + (d["assigned_title"] or "")))}</td>'
            f'<td><span class="badge {h(d["work_status"])}">{h(d["work_status"])}</span></td><td>{h(d["remarks"])}</td></tr>'
            for d in daily_rows)
        body = f'''
        <section class="grid kpis" style="grid-template-columns:repeat(5,1fr)">{kpis}</section>
        <div class="card" style="margin-top:18px">
          <h2>{h(emp['name'])} · Work Progress</h2>
          <p style="color:var(--muted);margin-top:-6px">{h(emp['role'])} · {h(emp['department'])} · {h(emp['designation'])}</p>
          <div class="row" style="max-width:560px">
            <a class="btn success" href="/daily?user_id={emp_id}">View Daily Sheet</a>
            <a class="btn ghost" href="/reports/daily.csv">Export Daily Report</a>
            <a class="btn ghost" href="/">Back to Dashboard</a>
          </div>
        </div>
        <section class="grid split" style="margin-top:18px">
          <div class="card tablewrap">
            <h2>Assigned Task Status</h2>
            <table class="table">
              <tr><th>Task</th><th>Entity</th><th>Priority</th><th>Status</th><th>Due</th><th>Reviewer</th></tr>
              {task_html or '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:24px">No tasks assigned.</td></tr>'}
            </table>
          </div>
          <div class="card tablewrap">
            <h2>Daily Work Updates · Last 7 Days</h2>
            <table class="table">
              <tr><th>Date</th><th>Time</th><th>Task</th><th>Status</th><th>Remarks</th></tr>
              {daily_html or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:24px">No daily updates found.</td></tr>'}
            </table>
          </div>
        </section>'''
        return self.send(layout(u, f'{emp["name"]} Progress', body,
                                subtitle='Employee-wise task control and daily work visibility', active='dashboard'))

    # ── My Day (the new daily-slot planner) ────────────────────────────────
    def myday(self, u):
        qs = parse_qs(urlparse(self.path).query)
        slot_date = qs.get('date', [date.today().isoformat()])[0]
        ensure_slots(u['id'], slot_date)

        open_tasks = q('''SELECT id,task_code,title,priority,target_date,category FROM tasks
                          WHERE assigned_to=? AND status NOT IN ("Completed","Cancelled")
                          ORDER BY CASE priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2
                                                 WHEN 'Medium' THEN 3 ELSE 4 END,
                                   target_date, id''', (u['id'],))
        slots = q('''SELECT s.*,t.title task_title,t.task_code,t.priority,t.target_date FROM daily_slots s
                     LEFT JOIN tasks t ON t.id=s.task_id
                     WHERE s.user_id=? AND s.slot_date=?
                     ORDER BY s.start_time''', (u['id'], slot_date))

        work_slots = [s for s in slots if s['slot_label'] != 'Lunch Break']
        planned = sum(1 for s in work_slots if s['task_id'])
        done = sum(1 for s in work_slots if s['status'] == 'Completed')

        def hrs(s_time, e_time):
            try:
                a = datetime.strptime(s_time, '%H:%M'); b = datetime.strptime(e_time, '%H:%M')
                return (b - a).total_seconds() / 3600
            except Exception:
                return 0
        total_hrs = sum(hrs(s['start_time'], s['end_time']) for s in work_slots if s['task_id'])
        first_half_count = sum(1 for s in slots if s['slot_label'] in ('Priority Block 1','Priority Block 2') and s['task_id'])

        summary = f'''
        <div class="office-day-note">
          <b>Office timing:</b> 09:30 AM to 01:30 PM · Lunch 01:30 PM to 02:30 PM · 02:30 PM to 05:30 PM.<br>
          Critical and High priority assigned work is automatically placed before lunch. Assignee can change the task or status in one click.
        </div>
        <div class="day-summary">
          <div class="pill"><div class="l">Date</div><div class="v">{h(slot_date)}</div></div>
          <div class="pill"><div class="l">Priority before lunch</div><div class="v">{first_half_count}</div></div>
          <div class="pill"><div class="l">Hours allocated</div><div class="v">{total_hrs:.1f}</div></div>
          <div class="pill"><div class="l">Completed</div><div class="v">{done}</div></div>
        </div>'''

        task_options_base = '<option value="">— no task —</option>' + ''.join(
            f'<option value="{t["id"]}">{h(t["task_code"])} · {h(t["title"])} ({h(t["priority"])})</option>' for t in open_tasks)

        slot_cards = []
        for s in slots:
            is_lunch = s['slot_label'] == 'Lunch Break'
            part = 'lunch' if is_lunch else ('firsthalf' if s['slot_label'] in ('Priority Block 1','Priority Block 2') else 'afternoon')
            now_cls = ' now' if now_in_slot(s['start_time'], s['end_time']) else ''
            now_pill = '<span class="pill-now">NOW</span>' if now_cls else ''
            opts_html = task_options_base
            if s['task_id']:
                opts_html = opts_html.replace(f'value="{s["task_id"]}"', f'value="{s["task_id"]}" selected')
            task_control = '<input value="Lunch Break" disabled>' if is_lunch else f'<select name="slot_{s["id"]}_task">{opts_html}</select>'
            status_opts = opts(['Break'] if is_lunch else ['Planned','In Progress','Completed','Blocked','Skipped'], s['status'])
            done_btn = '' if is_lunch else f'<button class="btn success sm" formaction="/myday/quick/{s["id"]}/done" formmethod="post" type="submit">✓ Done</button>'
            slot_cards.append(f'''
            <div class="slot-compact {part}{now_cls}">
              <div>
                <div class="slot-time">{h(s["start_time"])} – {h(s["end_time"])}</div>
                <div class="slot-label">{h(s["slot_label"])} {now_pill}</div>
              </div>
              <div><label>Task</label>{task_control}</div>
              <div><label>Status</label><select name="slot_{s["id"]}_status">{status_opts}</select></div>
              <div><label>Note</label><input name="slot_{s["id"]}_notes" value="{h(s["notes"])}" placeholder="Optional"></div>
              <div>{done_btn}</div>
            </div>''')

        priority_queue = []
        for t in open_tasks[:8]:
            priority_queue.append(f'''
              <div class="priority-card">
                <div class="ptitle">{h(t['task_code'])} · {h(t['title'])}</div>
                <div class="pmeta"><span class="badge {h(t['priority'])}">{h(t['priority'])}</span> · Due {h(t['target_date'])} · {h(t['category'])}</div>
              </div>''')

        body = f'''
        {summary}
        <form method="post">
          <input type="hidden" name="slot_date" value="{h(slot_date)}">
          <div class="myday-layout">
            <div class="card">
              <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:14px;flex-wrap:wrap">
                <div>
                  <h2 style="margin:0">Today Plan</h2>
                  <div style="color:var(--muted);font-size:13px;margin-top:4px">Priority work first, lunch protected, closure block at day end.</div>
                </div>
                <div style="max-width:190px"><label>View Date</label>
                  <input type="date" name="goto_date" value="{h(slot_date)}" onchange="window.location='/myday?date='+this.value">
                </div>
              </div>
              {''.join(slot_cards)}
              <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
                <button class="btn primary">Save Plan</button>
                <a class="btn ghost" href="/myday">Refresh</a>
              </div>
            </div>
            <div class="card">
              <h2>Assigned Priority Queue</h2>
              <p style="color:var(--muted);font-size:13px;margin-top:-4px">System uses this order for auto-planning. You can still override the slot selection.</p>
              {''.join(priority_queue) or '<p style="color:var(--muted)">No active assigned tasks.</p>'}
            </div>
          </div>
        </form>
        '''
        return self.send(layout(u, 'My Day', body,
                                subtitle='Simple daily planner based on MPPL office timing',
                                active='myday'))

    def post_myday(self, u):
        f = self.body()
        slot_date = f.get('slot_date', date.today().isoformat())
        slots = q('SELECT id FROM daily_slots WHERE user_id=? AND slot_date=?', (u['id'], slot_date))
        for s in slots:
            sid = s['id']
            task_id = f.get(f'slot_{sid}_task') or None
            status = f.get(f'slot_{sid}_status', 'Planned')
            notes = f.get(f'slot_{sid}_notes', '')
            ex('UPDATE daily_slots SET task_id=?,status=?,notes=? WHERE id=? AND user_id=?',
               (task_id if task_id else None, status, notes, sid, u['id']))
        return self.redirect(f'/myday?date={slot_date}')

    def post_slot_done(self, u, slot_id):
        s = q('SELECT * FROM daily_slots WHERE id=? AND user_id=?', (slot_id, u['id']), True)
        if s:
            ex('UPDATE daily_slots SET status="Completed" WHERE id=?', (slot_id,))
            # If a task is linked and not already completed, log a quick update.
            if s['task_id']:
                ex('INSERT INTO task_updates(task_id,user_id,update_date,status,hours_spent,remarks) VALUES (?,?,?,?,?,?)',
                   (s['task_id'], u['id'], s['slot_date'], 'In Progress', 0,
                    f'Slot done: {s["slot_label"]} ({s["start_time"]}-{s["end_time"]})'))
        return self.redirect(f'/myday?date={s["slot_date"] if s else date.today().isoformat()}')

    # ── Tasks list ─────────────────────────────────────────────────────────
    def tasks(self, u):
        qs = parse_qs(urlparse(self.path).query)
        st = qs.get('status', [''])[0]; search = qs.get('q', [''])[0]
        sql = '''SELECT t.*,e.name entity,u.name owner,r.name reviewer FROM tasks t
                 LEFT JOIN entities e ON e.id=t.entity_id
                 LEFT JOIN users u ON u.id=t.assigned_to
                 LEFT JOIN users r ON r.id=t.reviewer_id WHERE 1=1'''
        args = []
        if u['role'] in ('Assignee','Team Member'):
            sql += ' AND t.assigned_to=?'; args.append(u['id'])
        if st:     sql += ' AND t.status=?'; args.append(st)
        if search: sql += ' AND (t.title LIKE ? OR t.category LIKE ? OR e.name LIKE ?)'; args += [f'%{search}%'] * 3
        rows = q(sql + ' ORDER BY target_date', tuple(args))

        filt = f'''<div class="card"><form class="row">
          <div><label>Search</label><input name="q" value="{h(search)}" placeholder="title, category, entity"></div>
          <div><label>Status</label><select name="status"><option value="">All</option>{opts(STATUSES, st)}</select></div>
          <div style="max-width:130px"><button class="btn primary" style="width:100%;justify-content:center">Filter</button></div>
        </form></div>'''

        tr = ''.join(
            f'<tr><td><a href="/tasks/{r["id"]}" class="strong">{h(r["task_code"])}</a>'
            f'<br><span style="color:var(--muted);font-size:12.5px">{h(r["title"])}</span></td>'
            f'<td>{h(r["entity"])}</td><td>{h(r["owner"])}</td><td>{h(r["reviewer"])}</td>'
            f'<td><span class="badge {h(r["priority"])}">{h(r["priority"])}</span></td>'
            f'<td><span class="badge {h(r["status"])}">{h(r["status"])}</span></td>'
            f'<td>{h(r["target_date"])}</td><td>{h(r["actual_hours"] or 0)}/{h(r["expected_hours"] or 0)}</td></tr>'
            for r in rows)

        body = f'''{filt}
          <div class="card tablewrap"><table class="table">
            <tr><th>Task</th><th>Entity</th><th>Assigned</th><th>Reviewer</th>
                <th>Priority</th><th>Status</th><th>Due</th><th>Hours</th></tr>
            {tr or '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:30px">No tasks match your filter.</td></tr>'}
          </table></div>'''
        return self.send(layout(u, 'Tasks', body,
                                actions='<a class="btn primary" href="/tasks/new">+ Add Task</a>',
                                subtitle=f'{len(rows)} task(s) shown',
                                active='tasks'))

    def new_task(self, u):
        users = q('SELECT * FROM users WHERE status="Active" ORDER BY name')
        ents = q('SELECT * FROM entities ORDER BY name')
        body = f'''<form method="post" class="card"><div class="form">
          <div class="full"><label>Task Title</label><input name="title" required></div>
          <div class="full"><label>Description</label><textarea name="description"></textarea></div>
          <div><label>Category</label><input name="category" list="cats">
            <datalist id="cats">
              <option>Accounting</option><option>Bank Reconciliation</option><option>GST</option>
              <option>TDS</option><option>ROC Filing</option><option>Payroll</option>
              <option>Audit Support</option><option>Vendor Payment</option><option>Admin</option>
            </datalist></div>
          <div><label>Entity</label><select name="entity_id">
            <option value="">General</option>{optrows(ents, show_role=False)}</select></div>
          <div><label>Assign To</label><select name="assigned_to">{optrows(users)}</select></div>
          <div><label>Reviewer</label><select name="reviewer_id">{optrows(users)}</select></div>
          <div><label>Priority</label><select name="priority">{opts(PRIORITIES)}</select></div>
          <div><label>Start Date</label><input type="date" name="start_date" value="{date.today().isoformat()}"></div>
          <div><label>Target Date</label><input type="date" name="target_date" required></div>
          <div><label>Expected Hours</label><input type="number" step="0.25" name="expected_hours" value="1"></div>
          <div><label>Recurring</label><select name="recurring_flag"><option>No</option><option>Yes</option></select></div>
          <div><label>Frequency</label><select name="recurrence_frequency">
            <option></option><option>Daily</option><option>Weekly</option><option>Monthly</option>
            <option>Quarterly</option><option>Annual</option></select></div>
          <div><label>Attachment Required</label><select name="attachment_required"><option>No</option><option>Yes</option></select></div>
          <div><label>External Dependency</label><input name="external_dependency"></div>
        </div><br>
        <button class="btn primary">Create Task</button>
        <a class="btn ghost" href="/tasks">Cancel</a></form>'''
        return self.send(layout(u, 'Create Task', body, active='tasks'))

    def post_task(self, u):
        f = self.body()
        tid = ex('''INSERT INTO tasks(task_code,title,description,category,entity_id,assigned_by,assigned_to,
                    reviewer_id,priority,start_date,target_date,expected_hours,recurring_flag,
                    recurrence_frequency,attachment_required,external_dependency,status)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                 ('TEMP', f.get('title'), f.get('description'), f.get('category'),
                  f.get('entity_id') or None, u['id'], f.get('assigned_to'), f.get('reviewer_id'),
                  f.get('priority'), f.get('start_date'), f.get('target_date'),
                  f.get('expected_hours') or 0, f.get('recurring_flag'), f.get('recurrence_frequency'),
                  f.get('attachment_required'), f.get('external_dependency'), 'Assigned'))
        ex('UPDATE tasks SET task_code=? WHERE id=?', (f'TASK-{tid:04d}', tid))
        return self.redirect(f'/tasks/{tid}')

    def task_detail(self, u, tid):
        t = q('''SELECT t.*,e.name entity,a.name assigner,u.name owner,r.name reviewer FROM tasks t
                 LEFT JOIN entities e ON e.id=t.entity_id LEFT JOIN users a ON a.id=t.assigned_by
                 LEFT JOIN users u ON u.id=t.assigned_to LEFT JOIN users r ON r.id=t.reviewer_id
                 WHERE t.id=?''', (tid,), True)
        if not t: return self.notfound(u)
        updates = q('''SELECT tu.*,u.name uname FROM task_updates tu
                       LEFT JOIN users u ON u.id=tu.user_id
                       WHERE task_id=? ORDER BY update_date DESC,id DESC''', (tid,))
        reviews = q('''SELECT r.*,u.name reviewer_name FROM reviews r
                       LEFT JOIN users u ON u.id=r.reviewer_id
                       WHERE task_id=? ORDER BY reviewed_at DESC''', (tid,))
        uh = ''.join(
            f'<tr><td>{h(x["update_date"])}</td><td>{h(x["uname"])}</td>'
            f'<td><span class="badge {h(x["status"])}">{h(x["status"])}</span></td>'
            f'<td>{h(x["hours_spent"])}</td><td>{h(x["remarks"])}</td><td>{h(x["delay_reason"])}</td></tr>'
            for x in updates)
        rh = ''.join(
            f'<div style="padding:10px 0;border-bottom:1px solid var(--border-2)">'
            f'<div class="strong">{h(r["review_status"])} · ★ {h(r["quality_rating"])}</div>'
            f'<div style="color:var(--muted);font-size:12px">{h(r["reviewer_name"])} · {h(r["reviewed_at"])}</div>'
            f'<div style="margin-top:5px">{h(r["comments"])}</div></div>' for r in reviews)

        body = f'''
        <div class="card">
          <h2 style="margin-bottom:8px">{h(t['title'])}</h2>
          <p style="color:var(--muted);margin:0 0 12px">{h(t['description'])}</p>
          <div style="margin-bottom:10px">
            <span class="badge {h(t['priority'])}">{h(t['priority'])}</span>
            <span class="badge {h(t['status'])}">{h(t['status'])}</span>
          </div>
          <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;font-size:13px">
            <div><span style="color:var(--muted)">Entity</span><br><b>{h(t['entity'])}</b></div>
            <div><span style="color:var(--muted)">Owner</span><br><b>{h(t['owner'])}</b></div>
            <div><span style="color:var(--muted)">Reviewer</span><br><b>{h(t['reviewer'])}</b></div>
            <div><span style="color:var(--muted)">Target Date</span><br><b>{h(t['target_date'])}</b></div>
            <div><span style="color:var(--muted)">Hours</span><br><b>{h(t['actual_hours'] or 0)} / {h(t['expected_hours'] or 0)}</b></div>
            <div><span style="color:var(--muted)">Assigned By</span><br><b>{h(t['assigner'])}</b></div>
          </div>
        </div>
        <section class="grid split">
          <form method="post" action="/tasks/{tid}/update" class="card">
            <h2>Update Work</h2>
            <div class="form">
              <div><label>Date</label><input type="date" name="update_date" value="{date.today().isoformat()}"></div>
              <div><label>Status</label><select name="status">{opts(UPDATES)}</select></div>
              <div><label>Hours</label><input name="hours_spent" type="number" step="0.25" value="1"></div>
              <div><label>Delay Reason</label><select name="delay_reason">{opts(DELAY)}</select></div>
              <div class="full"><label>Remarks</label><textarea name="remarks"></textarea></div>
              <div class="full"><label>Issue / Blocker</label><textarea name="issue_description"></textarea></div>
              <div><label>Support Required From</label><input name="support_required_from"></div>
            </div><br>
            <button class="btn primary">Submit Update</button>
          </form>
          <form method="post" action="/tasks/{tid}/review" class="card">
            <h2>Review</h2>
            <label>Review Status</label>
            <select name="review_status"><option>Completed</option><option>Rework Required</option><option>Under Review</option></select>
            <label>Quality Rating</label>
            <select name="quality_rating"><option>5</option><option>4</option><option>3</option><option>2</option><option>1</option></select>
            <label>Comments</label><textarea name="comments"></textarea><br>
            <button class="btn success">Save Review</button>
          </form>
        </section>
        <div class="card tablewrap">
          <h2>Update History</h2>
          <table class="table">
            <tr><th>Date</th><th>User</th><th>Status</th><th>Hours</th><th>Remarks</th><th>Delay</th></tr>
            {uh or '<tr><td colspan="6" style="text-align:center;color:var(--muted);padding:20px">No updates yet.</td></tr>'}
          </table>
          <h2 style="margin-top:18px">Review History</h2>
          {rh or '<p style="color:var(--muted)">No reviews yet.</p>'}
        </div>'''
        return self.send(layout(u, t['task_code'], body,
                                actions='<a class="btn ghost" href="/tasks">← Back to Tasks</a>',
                                subtitle=t['title'], active='tasks'))

    def post_update(self, u, tid):
        f = self.body(); hrs = float(f.get('hours_spent') or 0); st = f.get('status')
        ex('''INSERT INTO task_updates(task_id,user_id,update_date,status,hours_spent,remarks,
              issue_description,delay_reason,support_required_from)
              VALUES (?,?,?,?,?,?,?,?,?)''',
           (tid, u['id'], f.get('update_date'), st, hrs, f.get('remarks'),
            f.get('issue_description'), f.get('delay_reason'), f.get('support_required_from')))
        ex('''UPDATE tasks SET status=?,actual_hours=COALESCE(actual_hours,0)+?,
              completed_at=CASE WHEN ?="Completed" THEN ? ELSE completed_at END WHERE id=?''',
           (st, hrs, st, datetime.now().isoformat(timespec='seconds'), tid))
        return self.redirect(f'/tasks/{tid}')

    def post_review(self, u, tid):
        f = self.body(); st = f.get('review_status')
        ex('INSERT INTO reviews(task_id,reviewer_id,review_status,quality_rating,comments) VALUES (?,?,?,?,?)',
           (tid, u['id'], st, f.get('quality_rating'), f.get('comments')))
        ex('UPDATE tasks SET status=?,completed_at=CASE WHEN ?="Completed" THEN ? ELSE completed_at END WHERE id=?',
           (st, st, datetime.now().isoformat(timespec='seconds'), tid))
        return self.redirect(f'/tasks/{tid}')

    # ── Daily Report ───────────────────────────────────────────────────────
    def daily(self, u):
        """Open-sheet style daily update: assigned tasks are prefilled, with extra rows for unassigned work."""
        qs = parse_qs(urlparse(self.path).query)
        work_date = qs.get('date', [date.today().isoformat()])[0]
        scope_all = u['role'] not in ('Assignee','Team Member')
        users = q('SELECT id,name,role FROM users WHERE status="Active" ORDER BY name')
        selected_user = int(qs.get('user_id', [u['id']])[0] or u['id']) if scope_all else u['id']
        selected_user_row = q('SELECT * FROM users WHERE id=?', (selected_user,), True) or u
        read_only = selected_user != u['id']
        row_lock = 'disabled' if read_only else ''

        assigned = q("""SELECT t.*,e.name entity FROM tasks t
                        LEFT JOIN entities e ON e.id=t.entity_id
                        WHERE t.assigned_to=? AND t.status NOT IN ("Completed","Cancelled")
                        ORDER BY CASE t.priority WHEN 'Critical' THEN 1 WHEN 'High' THEN 2 WHEN 'Medium' THEN 3 ELSE 4 END, t.target_date""",
                     (selected_user,))
        entries = q("""SELECT d.*,t.task_code,t.title assigned_title,u.name employee FROM daily_sheet_entries d
                       LEFT JOIN tasks t ON t.id=d.task_id
                       LEFT JOIN users u ON u.id=d.user_id
                       WHERE d.user_id=? AND d.entry_date=? ORDER BY d.from_time,d.id""", (selected_user, work_date))
        entries_by_task = {str(e['task_id']): e for e in entries if e['task_id']}
        unassigned_entries = [e for e in entries if not e['task_id']]

        def task_row(idx, task=None, entry=None):
            tid = task['id'] if task else ''
            default_task = f"{task['task_code']} · {task['title']}" if task else ''
            if task and task['entity']:
                default_task += f" ({task['entity']})"
            if task:
                task_cell = (f'<input type="hidden" name="row_{idx}_task_id" value="{h(tid)}">'
                             f'<input name="row_{idx}_task_text" value="{h(entry["task_text"] if entry and entry["task_text"] else default_task)}" readonly {row_lock}>')
            else:
                task_cell = (f'<input type="hidden" name="row_{idx}_task_id" value="">'
                             f'<input name="row_{idx}_task_text" value="{h(entry["task_text"] if entry else "")}" placeholder="Unassigned / ad-hoc work done" {row_lock}>')
            from_val = h(entry['from_time'] if entry else '')
            to_val = h(entry['to_time'] if entry else '')
            status_val = entry['work_status'] if entry else ('Assigned' if task else 'Completed')
            remarks_val = h(entry['remarks'] if entry else '')
            return f'''<tr>
                <td>{task_cell}</td>
                <td><input type="time" name="row_{idx}_from" value="{from_val}" {row_lock}></td>
                <td><input type="time" name="row_{idx}_to" value="{to_val}" {row_lock}></td>
                <td><select name="row_{idx}_status" {row_lock}>{opts(UPDATES, status_val)}</select></td>
                <td><input name="row_{idx}_remarks" value="{remarks_val}" placeholder="Remarks / issues / completion note" {row_lock}></td>
              </tr>'''

        rows=[]; idx=0
        for t in assigned:
            idx += 1
            rows.append(task_row(idx, task=t, entry=entries_by_task.get(str(t['id']))))
        for e in unassigned_entries:
            idx += 1
            rows.append(task_row(idx, entry=e))
        for _ in range(5):
            idx += 1
            rows.append(task_row(idx))

        recent = q("""SELECT d.*,u.name employee,t.task_code,t.title assigned_title FROM daily_sheet_entries d
                      LEFT JOIN users u ON u.id=d.user_id
                      LEFT JOIN tasks t ON t.id=d.task_id
                      WHERE d.entry_date=? AND (?=1 OR d.user_id=?)
                      ORDER BY u.name,d.from_time,d.id""", (work_date, 1 if scope_all else 0, u['id']))
        recent_rows=''.join(f'''<tr><td>{h(r['employee'])}</td><td>{h(r['from_time'])} - {h(r['to_time'])}</td>
            <td>{h(r['task_text'] or ((r['task_code'] or '') + ' · ' + (r['assigned_title'] or '')))}</td>
            <td><span class="badge {h(r['work_status'])}">{h(r['work_status'])}</span></td><td>{h(r['remarks'])}</td></tr>''' for r in recent)

        user_filter = ''
        if scope_all:
            user_opts=''.join(f'<option value="{x["id"]}" {"selected" if x["id"]==selected_user else ""}>{h(x["name"])} — {h(x["role"])}</option>' for x in users)
            user_filter = f'<div><label>Employee</label><select name="user_id" onchange="window.location=\'/daily?date={work_date}&user_id=\'+this.value">{user_opts}</select></div>'

        view_note = ''
        if read_only:
            view_note = '<div class="flash" style="background:#eff6ff;color:#1e40af">View-only mode: only the concerned employee can fill or edit this daily sheet.</div>'
        action_buttons = '<button class="btn primary" style="margin-top:14px">Save Daily Sheet</button>' if not read_only else '<span class="badge">View Only</span>'

        body=f'''<form method="post" class="card">
          {view_note}
          <input type="hidden" name="row_count" value="{idx}">
          <input type="hidden" name="entry_date" value="{h(work_date)}">
          <input type="hidden" name="selected_user" value="{h(selected_user)}">
          <div class="row">
            <div><label>Date</label><input type="date" name="view_date" value="{h(work_date)}" onchange="window.location='/daily?date='+this.value{'&user_id='+str(selected_user) if scope_all else ''}"></div>
            <div><label>Work Mode</label><select name="work_mode" {"disabled" if read_only else ""}>{opts(WORK)}</select></div>
            {user_filter}
          </div>
          <h2 style="margin-top:18px">Daily Task Completion Sheet - {h(selected_user_row['name'])}</h2>
          <p style="color:var(--muted);margin-top:-6px">Assigned tasks are prefilled. Use blank rows for unassigned/ad-hoc office work.</p>
          <div class="tablewrap"><table class="table">
            <tr><th style="width:38%">Task</th><th>From Time</th><th>To Time</th><th>Work Status</th><th>Remarks</th></tr>
            {''.join(rows)}
          </table></div>
          {action_buttons}
          <a class="btn success" href="/reports/daily.csv?date={h(work_date)}">Export Daily Report</a>
        </form>
        <div class="card tablewrap">
          <h2>Today’s Submitted Work</h2>
          <table class="table"><tr><th>Employee</th><th>Time</th><th>Task</th><th>Status</th><th>Remarks</th></tr>
          {recent_rows or '<tr><td colspan="5" style="text-align:center;color:var(--muted);padding:20px">No daily updates submitted for this date.</td></tr>'}
          </table>
        </div>'''
        return self.send(layout(u, 'Daily Update', body,
                                actions=f'<a class="btn primary" href="/reports/daily.csv?date={h(work_date)}">↓ Export Daily Report</a>',
                                subtitle='Open sheet for daily task completion and management reporting', active='daily'))

    def post_daily(self, u):
        f = self.body()
        entry_date = f.get('entry_date') or date.today().isoformat()
        requested_user = int(f.get('selected_user') or u['id'])
        if requested_user != u['id']:
            return self.redirect(f'/daily?date={entry_date}&user_id={requested_user}')
        target_user = u['id']
        ex('DELETE FROM daily_sheet_entries WHERE user_id=? AND entry_date=?', (target_user, entry_date))
        row_count = int(f.get('row_count') or 0)
        lines=[]; total=0.0
        for i in range(1, row_count+1):
            task_id = f.get(f'row_{i}_task_id') or None
            task_text = (f.get(f'row_{i}_task_text') or '').strip()
            from_time = f.get(f'row_{i}_from') or ''
            to_time = f.get(f'row_{i}_to') or ''
            status = f.get(f'row_{i}_status') or ''
            remarks = f.get(f'row_{i}_remarks') or ''
            if not task_text and not task_id:
                continue
            ex("""INSERT INTO daily_sheet_entries(user_id,entry_date,task_id,task_text,from_time,to_time,work_status,remarks)
                  VALUES (?,?,?,?,?,?,?,?)""", (target_user, entry_date, task_id, task_text, from_time, to_time, status, remarks))
            try:
                if from_time and to_time:
                    a=datetime.strptime(from_time,'%H:%M'); b=datetime.strptime(to_time,'%H:%M')
                    total += max(0,(b-a).total_seconds()/3600)
            except Exception:
                pass
            if task_id:
                ex('INSERT INTO task_updates(task_id,user_id,update_date,status,hours_spent,remarks) VALUES (?,?,?,?,?,?)',
                   (task_id, target_user, entry_date, status, 0, remarks))
                ex("""UPDATE tasks SET status=?, completed_at=CASE WHEN ?='Completed' THEN ? ELSE completed_at END WHERE id=?""",
                   (status, status, datetime.now().isoformat(timespec='seconds'), task_id))
            lines.append(f'{from_time}-{to_time} | {task_text} | {status} | {remarks}')
        ex('DELETE FROM daily_reports WHERE user_id=? AND report_date=?', (target_user, entry_date))
        ex("""INSERT INTO daily_reports(user_id,report_date,work_mode,total_hours,summary,submitted_at,emailed_to_manager,manager_id)
              VALUES (?,?,?,?,?,?,?,?)""",
           (target_user, entry_date, f.get('work_mode'), round(total,2), '\n'.join(lines), datetime.now().isoformat(timespec='seconds'), 'Ready for Export', u['reporting_manager_id']))
        redirect = f'/daily?date={entry_date}'
        return self.redirect(redirect)

    # ── Compliance ─────────────────────────────────────────────────────────
    def compliance(self, u):
        users = q('SELECT * FROM users ORDER BY name')
        ents = q('SELECT * FROM entities ORDER BY name')
        rem = q('''SELECT c.*,e.name entity,u.name owner,r.name reviewer FROM compliance_reminders c
                   LEFT JOIN entities e ON e.id=c.entity_id
                   LEFT JOIN users u ON u.id=c.responsible_user_id
                   LEFT JOIN users r ON r.id=c.reviewer_id ORDER BY due_date''')
        form = f'''<form method="post" class="card"><h2>Add Reminder</h2>
          <div class="form">
            <div><label>Entity</label><select name="entity_id">{optrows(ents, show_role=False)}</select></div>
            <div><label>Compliance Type</label><select name="compliance_type">{opts(COMP)}</select></div>
            <div><label>FY</label><input name="financial_year" value="2026-27"></div>
            <div><label>Due Date</label><input type="date" name="due_date" required></div>
            <div><label>Frequency</label><select name="frequency">{opts(["One-time","Monthly","Quarterly","Half-yearly","Annual"])}</select></div>
            <div><label>Responsible</label><select name="responsible_user_id">{optrows(users)}</select></div>
            <div><label>Reviewer</label><select name="reviewer_id">{optrows(users)}</select></div>
            <div><label>Priority</label><select name="priority">{opts(PRIORITIES)}</select></div>
            <div><label>Reminder Days</label><input name="reminder_days" value="30,15,7,3,1"></div>
            <div><label>Escalation User</label><select name="escalation_user_id">{optrows(users)}</select></div>
            <div class="full"><label>Remarks</label><textarea name="remarks"></textarea></div>
          </div>
          <button class="btn primary">Add Reminder</button></form>'''
        rows = ''.join(
            f'<tr><td class="strong">{h(c["compliance_type"])}</td><td>{h(c["entity"])}</td>'
            f'<td>{h(c["due_date"])}</td><td>{h(c["owner"])}</td><td>{h(c["reviewer"])}</td>'
            f'<td><span class="badge {h(c["priority"])}">{h(c["priority"])}</span></td>'
            f'<td><span class="badge {h(c["status"])}">{h(c["status"])}</span></td>'
            f'<td>{"" if c["status"]=="Completed" else f"""<form method=post action=/compliance/{c["id"]}/complete style="display:flex;gap:6px"><input name=acknowledgement_number placeholder=SRN/Ack style="max-width:140px"><button class=\"btn success sm\">Close</button></form>"""}</td></tr>'
            for c in rem)
        body = f'''
        <section class="grid split">
          {form}
          <div class="card">
            <h2>Reminder Strategy</h2>
            <p style="color:var(--muted);font-size:13.5px;line-height:1.6">
              Alerts will fire at <b>30, 15, 7, 3 and 1 day</b> before the due date.
              Overdue critical items escalate to management.
            </p>
            <p style="color:var(--muted-2);font-size:12.5px;margin-top:14px">
              SMTP / WhatsApp integration can be added in Phase 2.
            </p>
          </div>
        </section>
        <div class="card tablewrap">
          <h2>Open Compliance Calendar</h2>
          <table class="table">
            <tr><th>Compliance</th><th>Entity</th><th>Due</th><th>Owner</th>
                <th>Reviewer</th><th>Priority</th><th>Status</th><th>Close</th></tr>
            {rows or '<tr><td colspan="8" style="text-align:center;color:var(--muted);padding:20px">No reminders yet.</td></tr>'}
          </table>
        </div>'''
        return self.send(layout(u, 'Compliance & Renewal Tracker', body,
                                subtitle='Statutory dates, escalations and acknowledgements',
                                active='compliance'))

    def post_compliance(self, u):
        f = self.body()
        ex('''INSERT INTO compliance_reminders(entity_id,compliance_type,financial_year,due_date,
              frequency,responsible_user_id,reviewer_id,priority,reminder_days,escalation_user_id,
              status,remarks) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
           (f.get('entity_id'), f.get('compliance_type'), f.get('financial_year'),
            f.get('due_date'), f.get('frequency'), f.get('responsible_user_id'),
            f.get('reviewer_id'), f.get('priority'), f.get('reminder_days'),
            f.get('escalation_user_id'), 'Upcoming', f.get('remarks')))
        return self.redirect('/compliance')

    def post_comp_done(self, u, cid):
        f = self.body()
        ex('UPDATE compliance_reminders SET status="Completed",filing_date=?,acknowledgement_number=? WHERE id=?',
           (date.today().isoformat(), f.get('acknowledgement_number'), cid))
        return self.redirect('/compliance')

    # ── Reports & masters ──────────────────────────────────────────────────
    def reports(self, u):
        emp = q('''SELECT u.name,COUNT(t.id) total,
                   SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) completed,
                   SUM(CASE WHEN t.status!='Completed' AND t.target_date<date('now') THEN 1 ELSE 0 END) overdue,
                   ROUND(COALESCE(SUM(t.actual_hours),0),2) hours FROM users u
                   LEFT JOIN tasks t ON t.assigned_to=u.id
                   WHERE u.role IN ('Assignee','Reviewer','Assignor','Team Member','Team Lead') GROUP BY u.id ORDER BY u.name''')
        ent = q('''SELECT e.name,COUNT(t.id) total,
                   SUM(CASE WHEN t.status='Completed' THEN 1 ELSE 0 END) completed,
                   SUM(CASE WHEN t.status!='Completed' AND t.target_date<date('now') THEN 1 ELSE 0 END) overdue
                   FROM entities e LEFT JOIN tasks t ON t.entity_id=e.id GROUP BY e.id ORDER BY e.name''')
        er = ''.join(
            f'<tr><td class="strong">{h(r["name"])}</td><td>{h(r["total"] or 0)}</td>'
            f'<td>{h(r["completed"] or 0)}</td><td>{h(r["overdue"] or 0)}</td>'
            f'<td>{h(r["hours"] or 0)}</td>'
            f'<td>{round((r["completed"] or 0)*100/(r["total"] or 1), 1) if r["total"] else "-"}%</td></tr>'
            for r in emp)
        et = ''.join(
            f'<tr><td class="strong">{h(r["name"])}</td><td>{h(r["total"] or 0)}</td>'
            f'<td>{h(r["completed"] or 0)}</td><td>{h(r["overdue"] or 0)}</td></tr>' for r in ent)
        body = f'''<section class="grid split">
          <div class="card tablewrap">
            <h2>Employee Performance Snapshot</h2>
            <table class="table">
              <tr><th>Employee</th><th>Total</th><th>Done</th><th>Overdue</th><th>Hours</th><th>%</th></tr>
              {er}
            </table>
          </div>
          <div class="card tablewrap">
            <h2>Entity Workload</h2>
            <table class="table">
              <tr><th>Entity</th><th>Total</th><th>Done</th><th>Overdue</th></tr>
              {et}
            </table>
          </div>
        </section>'''
        return self.send(layout(u, 'Reports', body,
                                actions='<a class="btn primary" href="/reports/tasks.csv">↓ Export Tasks CSV</a> <a class="btn success" href="/reports/daily.csv">↓ Export Daily Report</a>',
                                subtitle='Performance, workload and exports',
                                active='reports'))

    def csv(self, u):
        rows = q('''SELECT t.task_code,t.title,t.category,e.name entity,u.name assigned_to,t.priority,
                    t.status,t.target_date,t.expected_hours,t.actual_hours FROM tasks t
                    LEFT JOIN entities e ON e.id=t.entity_id LEFT JOIN users u ON u.id=t.assigned_to
                    ORDER BY target_date''')
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(['Task Code', 'Title', 'Category', 'Entity', 'Assigned To',
                    'Priority', 'Status', 'Target Date', 'Expected Hours', 'Actual Hours'])
        for r in rows: w.writerow(list(r))
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv')
        self.send_header('Content-Disposition', 'attachment; filename=tasks_report.csv')
        data = out.getvalue().encode()
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def post_employee(self, u):
        if u['role'] not in ('System Admin','Management','Assignor','Team Lead'):
            return self.redirect('/masters')
        f = self.body()
        email = (f.get('email') or '').lower().strip()
        if not email:
            return self.redirect('/masters')
        password = f.get('password') or 'welcome123'
        try:
            ex('''INSERT INTO users(name,email,password_hash,role,department,designation,reporting_manager_id,skill_area,status,must_change_password)
                  VALUES (?,?,?,?,?,?,?,?,?,1)''',
               (f.get('name'), email, pw(password), f.get('role') or 'Assignee',
                f.get('department'), f.get('designation'), f.get('reporting_manager_id') or None,
                f.get('skill_area'), 'Active'))
        except sqlite3.IntegrityError:
            pass
        return self.redirect('/masters')

    def post_employee_update(self, u, emp_id):
        if u['role'] not in ('System Admin','Management','Assignor','Team Lead'):
            return self.redirect('/masters')
        f = self.body()
        email = (f.get('email') or '').lower().strip()
        if not email or not f.get('name'):
            return self.redirect('/masters')
        existing = q('SELECT id FROM users WHERE email=? AND id!=?', (email, emp_id), True)
        if existing:
            return self.redirect('/masters')
        ex("""UPDATE users SET name=?, email=?, role=?, department=?, designation=?,
              reporting_manager_id=?, skill_area=?, status=? WHERE id=?""",
           (f.get('name'), email, f.get('role') or 'Assignee', f.get('department'),
            f.get('designation'), f.get('reporting_manager_id') or None,
            f.get('skill_area'), f.get('status') or 'Active', emp_id))
        if f.get('password'):
            ex('UPDATE users SET password_hash=? WHERE id=?', (pw(f.get('password')), emp_id))
        return self.redirect('/masters')

    def post_employee_delete(self, u, emp_id):
        # Only senior roles can delete/deactivate employees.
        if u['role'] not in ('System Admin','Management','Assignor','Team Lead'):
            return self.redirect('/masters')
        # Safety: never allow the logged-in user to delete his/her own login.
        if emp_id == u['id']:
            return self.redirect('/masters')

        emp = q('SELECT * FROM users WHERE id=?', (emp_id,), True)
        if not emp:
            return self.redirect('/masters')

        refs = 0
        ref_checks = [
            ('tasks', 'assigned_by'), ('tasks', 'assigned_to'), ('tasks', 'reviewer_id'),
            ('task_updates', 'user_id'), ('reviews', 'reviewer_id'),
            ('daily_reports', 'user_id'), ('daily_reports', 'manager_id'),
            ('compliance_reminders', 'responsible_user_id'), ('compliance_reminders', 'reviewer_id'),
            ('compliance_reminders', 'escalation_user_id'), ('entities', 'responsible_user_id'),
            ('daily_slots', 'user_id'), ('users', 'reporting_manager_id')
        ]
        for table, col in ref_checks:
            try:
                refs += q(f'SELECT COUNT(*) c FROM {table} WHERE {col}=?', (emp_id,), True)['c']
            except Exception:
                pass

        # If the employee is already used in tasks/reports/compliances, hard delete would break history.
        # So we deactivate and hide from the active employee list. Login is blocked because login only permits Active users.
        if refs:
            ex('UPDATE users SET status="Inactive" WHERE id=?', (emp_id,))
        else:
            ex('UPDATE users SET reporting_manager_id=NULL WHERE reporting_manager_id=?', (emp_id,))
            ex('DELETE FROM users WHERE id=?', (emp_id,))
        return self.redirect('/masters')


    def employee_template_csv(self, u):
        """Download an Excel-openable CSV template for bulk employee import."""
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(['name','email','password','role','department','designation','reporting_manager_email','skill_area','status'])
        w.writerow(['Example Employee','example@office.local','welcome123','Assignee','Accounts','Accounts Executive','savitha@office.local','GST, TDS, Banking','Active'])
        data = out.getvalue().encode('utf-8-sig')
        self.send_response(200)
        self.send_header('Content-Type', 'text/csv; charset=utf-8')
        self.send_header('Content-Disposition', 'attachment; filename=employee_import_template.csv')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def _read_multipart_file(self, field_name='employee_file'):
        """Tiny multipart/form-data parser for one uploaded file; avoids external packages."""
        content_type = self.headers.get('Content-Type','')
        if 'boundary=' not in content_type:
            return '', b''
        boundary = content_type.split('boundary=', 1)[1].strip().strip('"')
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        marker = ('--' + boundary).encode()
        for part in raw.split(marker):
            if b'Content-Disposition' not in part or field_name.encode() not in part:
                continue
            head, sep, body = part.partition(b'\r\n\r\n')
            if not sep:
                continue
            header_text = head.decode('utf-8', errors='ignore')
            filename = ''
            for token in header_text.split(';'):
                token = token.strip()
                if token.startswith('filename='):
                    filename = token.split('=', 1)[1].strip().strip('"')
            body = body.rstrip(b'\r\n')
            if body.endswith(b'--'):
                body = body[:-2].rstrip(b'\r\n')
            return filename, body
        return '', b''

    def _xlsx_rows(self, data):
        """Small XLSX reader using only Python standard library; reads first worksheet values."""
        z = zipfile.ZipFile(io.BytesIO(data))
        ns = {'a':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        shared = []
        if 'xl/sharedStrings.xml' in z.namelist():
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            for si in root.findall('a:si', ns):
                txt = ''.join(t.text or '' for t in si.findall('.//a:t', ns))
                shared.append(txt)
        sheet_name = 'xl/worksheets/sheet1.xml'
        if sheet_name not in z.namelist():
            sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet') and n.endswith('.xml')]
            if not sheets: return []
            sheet_name = sheets[0]
        root = ET.fromstring(z.read(sheet_name))
        rows = []
        for row in root.findall('.//a:row', ns):
            vals = []
            last_col = 0
            for c in row.findall('a:c', ns):
                ref = c.attrib.get('r','A1')
                col_letters = ''.join(ch for ch in ref if ch.isalpha())
                col = 0
                for ch in col_letters:
                    col = col*26 + (ord(ch.upper())-64)
                while last_col < col-1:
                    vals.append(''); last_col += 1
                v = c.find('a:v', ns)
                value = '' if v is None else v.text or ''
                if c.attrib.get('t') == 's' and value.isdigit():
                    value = shared[int(value)] if int(value) < len(shared) else ''
                vals.append(value); last_col = col
            rows.append(vals)
        return rows

    def _employee_import_rows(self, filename, data):
        name = (filename or '').lower()
        if name.endswith('.xlsx'):
            rows = self._xlsx_rows(data)
            if not rows: return []
            headers = [str(x).strip().lower().replace(' ','_') for x in rows[0]]
            output = []
            for row in rows[1:]:
                if not any(str(v).strip() for v in row):
                    continue
                padded = [str(v).strip() for v in row] + [''] * max(0, len(headers)-len(row))
                output.append(dict(zip(headers, padded)))
            return output
        text = data.decode('utf-8-sig', errors='replace')
        return list(csv.DictReader(io.StringIO(text)))

    def post_employee_import(self, u):
        if u['role'] not in ('System Admin','Management','Assignor','Team Lead'):
            return self.redirect('/masters')
        try:
            filename, data = self._read_multipart_file('employee_file')
            rows = self._employee_import_rows(filename, data)
            imported = updated = skipped = 0
            allowed = set(ROLE_OPTIONS)
            for r in rows:
                clean = {str(k).strip().lower().replace(' ','_'): (v or '').strip() for k, v in r.items()}
                name = clean.get('name') or clean.get('employee_name')
                email = (clean.get('email') or clean.get('login_id') or clean.get('email_login_id') or '').lower().strip()
                if not name or not email:
                    skipped += 1; continue
                role = clean.get('role') or clean.get('role_category') or 'Assignee'
                if role not in allowed: role = 'Assignee'
                status = clean.get('status') or 'Active'
                if status not in ('Active','Inactive'): status = 'Active'
                mgr_email = (clean.get('reporting_manager_email') or clean.get('manager_email') or '').lower().strip()
                mgr = q('SELECT id FROM users WHERE email=?', (mgr_email,), True) if mgr_email else None
                existing = q('SELECT id FROM users WHERE email=?', (email,), True)
                password = clean.get('password') or 'welcome123'
                common = (name, email, role, clean.get('department'), clean.get('designation'), mgr['id'] if mgr else None, clean.get('skill_area'), status)
                if existing:
                    ex("""UPDATE users SET name=?, email=?, role=?, department=?, designation=?, reporting_manager_id=?, skill_area=?, status=? WHERE id=?""", common + (existing['id'],))
                    if clean.get('password'):
                        ex('UPDATE users SET password_hash=? WHERE id=?', (pw(password), existing['id']))
                    updated += 1
                else:
                    ex("""INSERT INTO users(name,email,password_hash,role,department,designation,reporting_manager_id,skill_area,status,must_change_password) VALUES (?,?,?,?,?,?,?,?,?,1)""", (name, email, pw(password), role, clean.get('department'), clean.get('designation'), mgr['id'] if mgr else None, clean.get('skill_area'), status))
                    imported += 1
            return self.redirect(f'/masters?imported={imported}&updated={updated}&skipped={skipped}')
        except Exception as e:
            return self.send(layout(u, 'Employee Import Error', f'<div class="card"><h2>Import failed</h2><p>{h(e)}</p><a class="btn ghost" href="/masters">Back to Masters</a></div>', active='masters'), 500)

    def post_entity(self, u):
        if u['role'] not in ('System Admin','Management','Assignor','Team Lead'):
            return self.redirect('/masters')
        f = self.body()
        if f.get('name'):
            ex('INSERT INTO entities(name,entity_type,responsible_user_id,status) VALUES (?,?,?,"Active")',
               (f.get('name'), f.get('entity_type') or 'Company', None))
        return self.redirect('/masters')

    def daily_csv(self, u):
        qs = parse_qs(urlparse(self.path).query)
        report_date = qs.get('date', [date.today().isoformat()])[0]
        rows = q("""SELECT d.entry_date,u.name employee,d.from_time,d.to_time,
                    COALESCE(t.task_code,'') task_code,
                    COALESCE(d.task_text,t.title,'') task,
                    d.work_status,d.remarks
                    FROM daily_sheet_entries d
                    LEFT JOIN users u ON u.id=d.user_id
                    LEFT JOIN tasks t ON t.id=d.task_id
                    WHERE d.entry_date=?
                    ORDER BY u.name,d.from_time,d.id""", (report_date,))
        out = io.StringIO(); w = csv.writer(out)
        w.writerow(['Date','Employee','From Time','To Time','Task Code','Task','Work Status','Remarks'])
        for r in rows:
            w.writerow([r['entry_date'],r['employee'],r['from_time'],r['to_time'],r['task_code'],r['task'],r['work_status'],r['remarks']])
        data = out.getvalue().encode()
        self.send_response(200)
        self.send_header('Content-Type','text/csv')
        self.send_header('Content-Disposition',f'attachment; filename=daily_task_report_{report_date}.csv')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def masters(self, u):
        users = q('SELECT * FROM users WHERE status="Active" ORDER BY name')
        all_users_for_managers = q('SELECT * FROM users ORDER BY name')
        inactive_users = q('SELECT * FROM users WHERE status="Inactive" ORDER BY name')
        ents = q('SELECT * FROM entities ORDER BY e.id, e.name'.replace('e.id','id').replace('e.name','name'))
        can_edit = u['role'] in ('System Admin','Management','Assignor','Team Lead')
        def employee_row(x):
            if not can_edit:
                return (f'<tr><td class="strong">{h(x["name"])}</td><td>{h(x["email"])}</td>'
                        f'<td>{h(x["role"])}</td><td>{h(x["department"])}</td>'
                        f'<td>{h(x["designation"])}</td><td>{h(x["skill_area"])}</td>'
                        f'<td><span class="badge {h(x["status"])}">{h(x["status"])}</span></td></tr>')
            rid = x['id']
            mgr_opts = '<option value="">None</option>' + optrows(users, x['reporting_manager_id'])
            return f'''
            <tr>
              <td><input form="emp_{rid}" name="name" value="{h(x['name'])}" required></td>
              <td><input form="emp_{rid}" name="email" type="email" value="{h(x['email'])}" required></td>
              <td><select form="emp_{rid}" name="role">{opts(ROLE_OPTIONS, x['role'])}</select></td>
              <td><input form="emp_{rid}" name="department" value="{h(x['department'])}"></td>
              <td><input form="emp_{rid}" name="designation" value="{h(x['designation'])}"></td>
              <td><input form="emp_{rid}" name="skill_area" value="{h(x['skill_area'])}"></td>
              <td><select form="emp_{rid}" name="status">{opts(['Active','Inactive'], x['status'])}</select></td>
              <td style="min-width:230px">
                <form id="emp_{rid}" method="post" action="/employees/{rid}/update"></form>
                <input form="emp_{rid}" name="password" placeholder="New password optional" style="margin-bottom:6px">
                <select form="emp_{rid}" name="reporting_manager_id" style="margin-bottom:6px">{mgr_opts}</select>
                <button form="emp_{rid}" class="btn success sm">Save</button>
                <form method="post" action="/employees/{rid}/delete" style="display:inline" onsubmit="return confirm('Delete/deactivate this employee login? Existing task history will be preserved.');">
                  <button class="btn danger sm">Delete</button>
                </form>
              </td>
            </tr>'''
        ur = ''.join(employee_row(x) for x in users)
        er = ''.join(
            f'<tr><td class="strong">{h(e["name"])}</td><td>{h(e["entity_type"])}</td>'
            f'<td><span class="badge {h(e["status"])}">{h(e["status"])}</span></td></tr>'
            for e in ents)

        emp_form = ''
        ent_form = ''
        if can_edit:
            emp_form = f'''<div class="card">
              <h2>Create Employee Login</h2>
              <form method="post" action="/employees/new" class="form">
                <div><label>Employee Name</label><input name="name" required placeholder="e.g. Kiran"></div>
                <div><label>Email / Login ID</label><input name="email" autofocus></div>
                <div><label>Password</label><input name="password" value="welcome123"></div>
                <div><label>Role Category</label><select name="role">{opts(ROLE_OPTIONS, 'Assignee')}</select></div>
                <div><label>Department</label><input name="department" placeholder="Accounts / Admin / Compliance"></div>
                <div><label>Designation</label><input name="designation" placeholder="Accounts Executive"></div>
                <div><label>Reporting Manager</label><select name="reporting_manager_id"><option value="">None</option>{optrows(users)}</select></div>
                <div><label>Skill Area</label><input name="skill_area" placeholder="GST, TDS, ROC, Banking"></div>
                <div class="full"><button class="btn primary">Create Employee & Login</button></div>
              </form>
              <p style="color:var(--muted);font-size:12.5px;margin-bottom:0">New employee can login immediately using the email and password entered above.</p>
            </div>'''
            ent_form = f'''<div class="card">
              <h2>Add Entity</h2>
              <form method="post" action="/entities/new" class="form">
                <div><label>Entity Name</label><input name="name" required placeholder="Entity / Client name"></div>
                <div><label>Type</label><select name="entity_type"><option>Company</option><option>LLP</option><option>Individual</option><option>Trust</option><option>Other</option></select></div>
                <div class="full"><button class="btn success">Add Entity</button></div>
              </form>
            </div>'''

        role_note = '''<div class="card">
          <h2>Role Naming Suggested</h2>
          <p style="color:var(--muted);margin-top:0">For office use, keep only two working role categories:</p>
          <p><b>Assignor</b> = person who creates, delegates, reviews or monitors work.</p>
          <p><b>Assignee</b> = person responsible for executing and updating the work.</p>
          <p style="color:var(--muted);font-size:12.5px;margin-bottom:0">Fancy alternatives: <b>Work Owner</b> and <b>Work Executor</b>. For the current MVP I have used Assignor / Assignee because it is clear and easy for all employees.</p>
        </div>'''

        qs = parse_qs(urlparse(self.path).query)
        flash = ''
        if qs.get('imported') or qs.get('updated') or qs.get('skipped'):
            flash = f'<div class="flash">Employee import completed: {h(qs.get("imported", [0])[0])} added, {h(qs.get("updated", [0])[0])} updated, {h(qs.get("skipped", [0])[0])} skipped.</div>'
        import_form = ''
        if can_edit:
            import_form = '''<div class="card" id="bulk-import-employees">
              <h2>Bulk Import Employees from Excel</h2>
              <p style="color:var(--muted);font-size:13px;margin-top:-6px">First-time setup shortcut: download the template, fill employee details in Excel, save as CSV or XLSX, and upload here.</p>
              <form method="post" action="/employees/import" enctype="multipart/form-data" class="row">
                <div><label>Employee File</label><input type="file" name="employee_file" accept=".csv,.xlsx" required></div>
                <div style="max-width:190px"><button class="btn primary" style="width:100%;justify-content:center">Import Employees</button></div>
              </form>
              <p style="color:var(--muted-2);font-size:12px;margin-bottom:0">Columns: name, email, password, role, department, designation, reporting_manager_email, skill_area, status. Duplicate emails are updated automatically.</p>
            </div>'''

        inactive_note = ''
        if can_edit and inactive_users:
            inactive_note = f'<p style="color:var(--muted);font-size:12.5px;margin-top:10px">Inactive/deleted logins hidden from this list: <b>{len(inactive_users)}</b>. Historical task records are preserved.</p>'

        body = f'''{flash}{import_form}{emp_form}
        <div class="card tablewrap">
          <h2>Employee Master & Login Access</h2>
          <p style="color:var(--muted);font-size:12.5px;margin-top:-6px">Edit employee details directly in the table. Delete removes unused employees; employees with task history are safely deactivated and hidden.</p>
          <table class="table">
            <tr><th>Name</th><th>Email/Login</th><th>Role</th><th>Department</th><th>Designation</th><th>Skill Area</th><th>Status</th>{'<th>Edit / Delete</th>' if can_edit else ''}</tr>
            {ur}
          </table>
          {inactive_note}
        </div>
        {role_note}
        {ent_form}
        <div class="card tablewrap">
          <h2>Entity Master</h2>
          <table class="table">
            <tr><th>Entity</th><th>Type</th><th>Status</th></tr>
            {er}
          </table>
        </div>'''
        actions = '<a class="btn primary" href="/employees/template.csv">Download Employee Template</a>' if can_edit else ''
        return self.send(layout(u, 'Masters', body, actions=actions,
                                subtitle='Employees, login access, roles and entities', active='masters'))

    def notfound(self, u):
        return self.send(layout(u, 'Not Found',
                                '<div class="card">The page you requested was not found.</div>'), 404)


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", "5000"))
    host = "0.0.0.0"

    print("=" * 60)
    print("  WorkTrack Pro · MPPL Office")
    print(f"  Running at  http://{host}:{port}")
    print("  Login       admin@office.local / admin123")
    print("  Stop with   Ctrl+C")
    print("=" * 60)

    ThreadingHTTPServer((host, port), App).serve_forever()
CREATE TABLE users(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, email TEXT UNIQUE,
        password_hash TEXT, role TEXT, department TEXT, designation TEXT,
        reporting_manager_id INTEGER, skill_area TEXT, status TEXT DEFAULT 'Active', must_change_password INTEGER DEFAULT 0, password_changed_at TEXT);
CREATE TABLE sqlite_sequence(name,seq);
CREATE TABLE entities(
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, entity_type TEXT,
        pan TEXT, gstin TEXT, cin_llpin TEXT, responsible_user_id INTEGER,
        status TEXT DEFAULT 'Active');
CREATE TABLE tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_code TEXT, title TEXT, description TEXT,
        category TEXT, entity_id INTEGER, assigned_by INTEGER, assigned_to INTEGER,
        reviewer_id INTEGER, priority TEXT, start_date TEXT, target_date TEXT,
        expected_hours REAL DEFAULT 0, actual_hours REAL DEFAULT 0,
        status TEXT DEFAULT 'Assigned', recurring_flag TEXT DEFAULT 'No',
        recurrence_frequency TEXT, attachment_required TEXT DEFAULT 'No',
        external_dependency TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT);
CREATE TABLE task_updates(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, user_id INTEGER,
        update_date TEXT, status TEXT, hours_spent REAL, remarks TEXT,
        issue_description TEXT, delay_reason TEXT, support_required_from TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE compliance_reminders(
        id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id INTEGER, compliance_type TEXT,
        financial_year TEXT, due_date TEXT, frequency TEXT, responsible_user_id INTEGER,
        reviewer_id INTEGER, priority TEXT, reminder_days TEXT DEFAULT '30,15,7,3,1',
        escalation_user_id INTEGER, status TEXT DEFAULT 'Upcoming', filing_date TEXT,
        acknowledgement_number TEXT, remarks TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id INTEGER, reviewer_id INTEGER,
        review_status TEXT, quality_rating INTEGER, comments TEXT,
        reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE daily_reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, report_date TEXT,
        work_mode TEXT, total_hours REAL, summary TEXT, submitted_at TEXT,
        emailed_to_manager TEXT, manager_id INTEGER);
CREATE TABLE daily_sheet_entries(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, entry_date TEXT,
        task_id INTEGER, task_text TEXT, from_time TEXT, to_time TEXT,
        work_status TEXT, remarks TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE daily_slots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, slot_date TEXT,
        slot_label TEXT, start_time TEXT, end_time TEXT, task_id INTEGER,
        status TEXT DEFAULT 'Planned', notes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, slot_date, slot_label));

import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from config import DATABASE_URL as CONFIG_DATABASE_URL

# Load environment variables
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL") or CONFIG_DATABASE_URL


# CONNECTION
def get_connection():
    """
    Returns a PostgreSQL connection (NeonDB).
    Rows will be returned as dictionaries.
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is not set. Add it to .env or config.py.")

    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )



# READ HELPERS

def get_project(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM projects WHERE id = %s", (project_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return dict(row) if row else None


def get_project_stakeholders(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stakeholders WHERE project_id = %s", (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_open_action_items(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM action_items
        WHERE project_id = %s AND status = 'OPEN'
        ORDER BY created_at DESC
    """, (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_open_risks(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM risks
        WHERE project_id = %s AND status = 'OPEN'
        ORDER BY created_at DESC
    """, (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_open_issues(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM issues
        WHERE project_id = %s AND status = 'OPEN'
        ORDER BY created_at DESC
    """, (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_open_decisions(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM decisions
        WHERE project_id = %s AND status = 'PENDING'
        ORDER BY created_at DESC
    """, (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


def get_sops(project_id: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT * FROM sops
        WHERE project_id = %s OR project_id IS NULL
        ORDER BY created_at DESC LIMIT 10
    """, (project_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]


# WRITE HELPERS

def save_action_item(project_id, item_id, description,
                     owner=None, due_date=None,
                     flags=None, source_message=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO action_items
            (id, project_id, description, owner, due_date, flags, source_message)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id, project_id) DO UPDATE SET
            description = EXCLUDED.description,
            owner = EXCLUDED.owner,
            due_date = EXCLUDED.due_date,
            flags = EXCLUDED.flags,
            source_message = EXCLUDED.source_message
    """, (item_id, project_id, description, owner, due_date, flags, source_message))
    conn.commit()
    cur.close()
    conn.close()


def save_risk(project_id, risk_id, description,
              likelihood="MEDIUM", impact="MEDIUM", source_message=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO risks
            (id, project_id, description, likelihood, impact, source_message)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (id, project_id) DO UPDATE SET
            description = EXCLUDED.description,
            likelihood = EXCLUDED.likelihood,
            impact = EXCLUDED.impact,
            source_message = EXCLUDED.source_message
    """, (risk_id, project_id, description, likelihood, impact, source_message))
    conn.commit()
    cur.close()
    conn.close()


def save_issue(project_id, issue_id, description,
               severity="MEDIUM", source_message=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO issues
            (id, project_id, description, severity, source_message)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id, project_id) DO UPDATE SET
            description = EXCLUDED.description,
            severity = EXCLUDED.severity,
            source_message = EXCLUDED.source_message
    """, (issue_id, project_id, description, severity, source_message))
    conn.commit()
    cur.close()
    conn.close()


def save_decision(project_id, decision_id, description,
                  decision_maker=None, source_message=None):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO decisions
            (id, project_id, description, decision_maker, source_message)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (id, project_id) DO UPDATE SET
            description = EXCLUDED.description,
            decision_maker = EXCLUDED.decision_maker,
            source_message = EXCLUDED.source_message
    """, (decision_id, project_id, description, decision_maker, source_message))
    conn.commit()
    cur.close()
    conn.close()


def save_sop(project_id, title, rule_text):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO sops (project_id, title, rule_text) VALUES (%s, %s, %s)",
        (project_id, title, rule_text)
    )
    conn.commit()
    cur.close()
    conn.close()


def log_message(message: dict, intent: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO messages
            (id, project_id, sender_name, sender_role, source, content, intent)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (id) DO NOTHING
    """, (
        message.get("message_id"),
        message.get("project"),
        message.get("sender", {}).get("name"),
        message.get("sender", {}).get("role"),
        message.get("source"),
        message.get("content"),
        intent
    ))
    conn.commit()
    cur.close()
    conn.close()


def log_delivery(message_id, recipient, channel, cc=None, status="SENT"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO delivery_log (message_id, recipient, channel, cc, status)
        VALUES (%s, %s, %s, %s, %s)
    """, (message_id, recipient, channel, cc, status))
    conn.commit()
    cur.close()
    conn.close()


def next_id(prefix: str, project_id: str) -> str:
    table_map = {
        "AI": "action_items",
        "RISK": "risks",
        "ISS": "issues",
        "DEC": "decisions",
    }
    table = table_map.get(prefix, "action_items")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT COUNT(*) FROM {table} WHERE project_id = %s", (project_id,))
    count = cur.fetchone()["count"]
    cur.close()
    conn.close()

    return f"{prefix}-{(count + 1):03d}"

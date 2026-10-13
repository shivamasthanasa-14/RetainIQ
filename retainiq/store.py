import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, date
from pathlib import Path

def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS tickets (
              ticket_id TEXT PRIMARY KEY, customer TEXT NOT NULL, received_at TEXT NOT NULL,
              subject TEXT NOT NULL, message TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Unclassified',
              processing_status TEXT NOT NULL DEFAULT 'Pending AI', summary TEXT NOT NULL DEFAULT '',
              owner TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'Open',
              follow_up TEXT NOT NULL DEFAULT '', due_date TEXT NOT NULL DEFAULT '',
              resolution_notes TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL,
              resolved_at TEXT, revision INTEGER NOT NULL DEFAULT 1, ai_provider TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS history (
              id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
              action TEXT NOT NULL, actor TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS drafts (
              id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
              ticket_revision INTEGER NOT NULL, body TEXT NOT NULL, original_body TEXT NOT NULL,
              sources TEXT NOT NULL, missing TEXT NOT NULL, provider TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'Draft', created_at TEXT NOT NULL,
              approved_at TEXT, approved_by TEXT,
              UNIQUE(ticket_id, ticket_revision));
            CREATE TABLE IF NOT EXISTS dispatches (
              id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
              escalation_id INTEGER NOT NULL UNIQUE REFERENCES history(id), owner TEXT NOT NULL,
              payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Pending',
              attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
            ''')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(tickets)')}
            for name, definition in {
                'issue_group': "TEXT NOT NULL DEFAULT ''", 'attention_reason': "TEXT NOT NULL DEFAULT ''",
                'missing_information': "TEXT NOT NULL DEFAULT '[]'", 'result_origin': "TEXT NOT NULL DEFAULT ''"
            }.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE tickets ADD COLUMN {name} {definition}')
            db.executescript('''
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS lifecycle (
              id INTEGER PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(ticket_id),
              status TEXT NOT NULL, due_date TEXT NOT NULL, effective_at TEXT NOT NULL, recorded_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS lifecycle_ticket_time ON lifecycle(ticket_id,effective_at,id);
            CREATE TABLE IF NOT EXISTS response_templates (
              id INTEGER PRIMARY KEY, group_key TEXT NOT NULL, body TEXT NOT NULL, sources TEXT NOT NULL,
              reviewed_by TEXT NOT NULL, reviewed_at TEXT NOT NULL);
            ''')
            template_columns={r['name'] for r in db.execute('PRAGMA table_info(response_templates)')}
            if 'request_hash' not in template_columns:
                db.execute("ALTER TABLE response_templates ADD COLUMN request_hash TEXT NOT NULL DEFAULT ''")

    def metadata(self, key, default=None):
        rows = self.query('SELECT value FROM metadata WHERE key=?', (key,))
        return rows[0]['value'] if rows else default

    def set_metadata(self, key, value):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO metadata VALUES (?,?)', (key, str(value)))

    def reference_date(self):
        return date.fromisoformat(self.metadata('reference_date', date.today().isoformat()))

    def effective_now(self):
        ref = self.metadata('reference_date')
        return ref + 'T18:00:00+00:00' if ref else now()

    def lifecycle_event(self, db, ticket_id, status, due_date, effective_at=None):
        db.execute('INSERT INTO lifecycle(ticket_id,status,due_date,effective_at,recorded_at) VALUES (?,?,?,?,?)',
                   (ticket_id, status, due_date, effective_at or self.effective_now(), now()))

    def migrate_owners(self):
        from .constants import LEGACY_OWNERS
        if self.metadata('neutral_owner_migration'):
            return
        with self.connect() as db:
            for old, new in LEGACY_OWNERS.items():
                affected = db.execute('SELECT ticket_id FROM tickets WHERE owner=?', (old,)).fetchall()
                db.execute('UPDATE tickets SET owner=? WHERE owner=?', (new, old))
                db.execute('UPDATE drafts SET approved_by=? WHERE approved_by=?', (new, old))
                db.execute('UPDATE dispatches SET owner=? WHERE owner=?', (new, old))
                for row in affected:
                    self.event(db, row['ticket_id'], 'Owner identifier migrated', 'Support Lead', {'from':old, 'to':new})
            db.execute("INSERT OR REPLACE INTO metadata VALUES ('neutral_owner_migration','1')")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def query(self, sql, args=()):
        with self.connect() as db:
            return [dict(r) for r in db.execute(sql, args)]

    def tickets(self):
        return self.query('SELECT * FROM tickets ORDER BY received_at DESC, ticket_id')

    def ticket(self, ticket_id):
        rows = self.query('SELECT * FROM tickets WHERE ticket_id=?', (ticket_id,))
        if not rows:
            raise ValueError('Ticket not found')
        return rows[0]

    def event(self, db, ticket_id, action, actor, detail):
        if not actor.strip():
            raise ValueError('An actor is required')
        return db.execute('INSERT INTO history(ticket_id,action,actor,detail,created_at) VALUES (?,?,?,?,?)',
                          (ticket_id, action, actor, json.dumps(detail, ensure_ascii=False), now())).lastrowid

    def history(self, ticket_id):
        return self.query('SELECT * FROM history WHERE ticket_id=? ORDER BY id DESC', (ticket_id,))

    def draft(self, ticket_id):
        return self.query('SELECT * FROM drafts WHERE ticket_id=? ORDER BY id DESC LIMIT 1', (ticket_id,))

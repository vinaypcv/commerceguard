import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def utc_day():
    return datetime.now(UTC).date().isoformat()


class Store:
    def __init__(self, path="data/commerce.db"):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS ledger (
              transaction_id TEXT PRIMARY KEY, owner TEXT NOT NULL, paid_cents INTEGER NOT NULL,
              refunded_cents INTEGER NOT NULL DEFAULT 0, currency TEXT NOT NULL,
              billed_day TEXT NOT NULL, consumed INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS decisions (
              owner TEXT, idem TEXT, fingerprint TEXT NOT NULL, result TEXT NOT NULL,
              PRIMARY KEY(owner, idem));
            CREATE TABLE IF NOT EXISTS refunds (
              owner TEXT, day TEXT, amount_cents INTEGER NOT NULL, transaction_id TEXT);
            CREATE TABLE IF NOT EXISTS audit (
              seq INTEGER PRIMARY KEY, payload TEXT NOT NULL, previous TEXT NOT NULL, digest TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY, owner TEXT NOT NULL, route TEXT NOT NULL, evidence TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'OPEN');
            CREATE TABLE IF NOT EXISTS traces (
              seq INTEGER PRIMARY KEY, run_id TEXT NOT NULL, state TEXT NOT NULL, detail TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self):
        with self.connect() as db:
            for tid, owner, paid in [("tx_demo", "alice", 30000), ("tx_other", "bob", 5000)]:
                db.execute(
                    "INSERT OR IGNORE INTO ledger VALUES (?, ?, ?, 0, 'USD', ?, 0)",
                    (tid, owner, paid, utc_day()),
                )

    def ledger(self, db, tid, owner, today=None):
        row = db.execute("SELECT * FROM ledger WHERE transaction_id=? AND owner=?", (tid, owner)).fetchone()
        if not row:
            raise LookupError("Transaction unavailable for this identity")
        facts = dict(row)
        facts["age_days"] = (
            datetime.fromisoformat(today or utc_day()).date()
            - datetime.fromisoformat(facts["billed_day"]).date()
        ).days
        return facts

    def append_audit(self, db, payload):
        previous = db.execute("SELECT digest FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        previous = previous[0] if previous else "0" * 64
        body = canonical({**payload, "recorded_at": datetime.now(UTC).isoformat()})
        digest = hashlib.sha256((previous + body).encode()).hexdigest()
        db.execute("INSERT INTO audit(payload, previous, digest) VALUES (?, ?, ?)", (body, previous, digest))
        return digest

    def verify_audit(self):
        previous = "0" * 64
        count = 0
        with self.connect() as db:
            for row in db.execute("SELECT * FROM audit ORDER BY seq"):
                digest = hashlib.sha256((previous + row["payload"]).encode()).hexdigest()
                if row["previous"] != previous or row["digest"] != digest:
                    return {"valid": False, "events": count}
                previous = digest
                count += 1
        return {"valid": True, "events": count, "head": previous}

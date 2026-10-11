import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path=None):
        path = path or os.getenv("VIBE_DB", ".data/vibe.db")
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.path = str(path)
        with self.connect() as db:
            db.executescript("CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, body TEXT); CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, project_id TEXT, created_at TEXT, reason TEXT, body TEXT);")

    def connect(self):
        return sqlite3.connect(self.path, timeout=30)

    def list(self):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM projects ORDER BY rowid DESC")]

    def get(self, project_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise KeyError(project_id)
        return json.loads(row[0])

    def save(self, project, reason):
        project["updated_at"] = now()
        body = json.dumps(project, ensure_ascii=False)
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO projects VALUES(?,?)", (project["id"], body))
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?)", (uuid.uuid4().hex, project["id"], now(), reason, body))
        return project

    def versions(self, project_id):
        with self.connect() as db:
            return [{"id": row[0], "created_at": row[1], "reason": row[2]} for row in db.execute("SELECT id,created_at,reason FROM versions WHERE project_id=? ORDER BY rowid DESC", (project_id,))]

    def restore(self, project_id, version_id):
        with self.connect() as db:
            row = db.execute("SELECT body FROM versions WHERE project_id=? AND id=?", (project_id, version_id)).fetchone()
        if not row:
            raise KeyError(version_id)
        return self.save(json.loads(row[0]), "restore:" + version_id)

    def delete(self, project_id):
        with self.connect() as db:
            db.execute("DELETE FROM projects WHERE id=?", (project_id,))
            db.execute("DELETE FROM versions WHERE project_id=?", (project_id,))

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH


class Storage:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _connection(self):
        connection = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.path, check_same_thread=False)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            self._local.connection = connection
        return connection

    @contextmanager
    def transaction(self):
        connection = self._connection()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def initialize(self):
        with self.transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    received_at TEXT NOT NULL,
                    station_id TEXT NOT NULL,
                    packet_json TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    inference_ms REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS ix_reports_station_time
                    ON reports(station_id, id DESC);
                CREATE TABLE IF NOT EXISTS evaluations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    result_json TEXT NOT NULL
                );
                """
            )

    def insert_report(self, packet: dict, decision: dict, inference_ms: float):
        received_at=datetime.now(timezone.utc).isoformat()
        with self.transaction() as connection:
            cursor=connection.execute(
                "INSERT INTO reports(received_at,station_id,packet_json,decision_json,inference_ms) VALUES(?,?,?,?,?)",
                (received_at,packet["station_id"],json.dumps(packet),json.dumps(decision),float(inference_ms)),
            )
            return cursor.lastrowid

    def recent(self, station_id: str, limit: int = 120):
        connection=self._connection()
        rows=connection.execute(
            "SELECT * FROM reports WHERE station_id=? ORDER BY id DESC LIMIT ?",
            (station_id,limit),
        ).fetchall()
        return [self._decode(row) for row in reversed(rows)]

    def latest_by_station(self):
        connection=self._connection()
        rows=connection.execute(
            """SELECT r.* FROM reports r JOIN
               (SELECT station_id,MAX(id) AS max_id FROM reports GROUP BY station_id) x
               ON r.id=x.max_id ORDER BY r.id DESC"""
        ).fetchall()
        return [self._decode(row) for row in rows]

    def _decode(self,row):
        return {
            "id":row["id"],"received_at":row["received_at"],"station_id":row["station_id"],
            "packet":json.loads(row["packet_json"]),"decision":json.loads(row["decision_json"]),
            "inference_ms":row["inference_ms"],
        }

    def save_evaluation(self,result: dict):
        created=datetime.now(timezone.utc).isoformat()
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO evaluations(created_at,result_json) VALUES(?,?)",
                (created,json.dumps(result)),
            )

    def latest_evaluation(self):
        row=self._connection().execute(
            "SELECT created_at,result_json FROM evaluations ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:return None
        result=json.loads(row["result_json"]);result["created_at"]=row["created_at"]
        return result

    def reset(self):
        with self.transaction() as connection:
            connection.execute("DELETE FROM reports")
            connection.execute("DELETE FROM evaluations")


storage=Storage()

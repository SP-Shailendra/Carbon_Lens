import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .analytics.events import validate_event_name


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ReportStore:
    def __init__(self, path: str):
        self.path = path

    def initialize(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, created_at TEXT NOT NULL, payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, report_id TEXT NOT NULL,
                    name TEXT NOT NULL, created_at TEXT NOT NULL
                );
            """)

    def save(self, report: dict[str, Any]) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute(
                "INSERT INTO reports VALUES (?, ?, ?)",
                (report["id"], report["created_at"], json.dumps(report, allow_nan=False)),
            )
            self._event(connection, report["id"], "upload_validated")

    def get(self, report_id: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as connection:
            row = connection.execute(
                "SELECT payload FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as connection:
            rows = connection.execute(
                "SELECT payload FROM reports ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {
                "id": report["id"],
                "created_at": report["created_at"],
                "summary": report["summary"],
                "methodology_version": report.get("methodology_version", "1"),
            }
            for report in (json.loads(row[0]) for row in rows)
        ]

    def decide(
        self, report_id: str, recommendation_id: str, decision: str
    ) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM reports WHERE id = ?", (report_id,)
            ).fetchone()
            if row is None:
                return None
            report = json.loads(row[0])
            recommendation = next(
                (item for item in report["recommendations"] if item["id"] == recommendation_id),
                None,
            )
            if recommendation is None:
                return None
            if recommendation["decision"] != decision:
                recommendation["decision"] = decision
                recommendation["decided_at"] = utc_now()
                connection.execute(
                    "UPDATE reports SET payload = ? WHERE id = ?",
                    (json.dumps(report, allow_nan=False), report_id),
                )
                self._event(connection, report_id, f"recommendation_{decision}")
            return report

    def _event(self, connection: sqlite3.Connection, report_id: str, name: str) -> None:
        connection.execute(
            "INSERT INTO events (report_id, name, created_at) VALUES (?, ?, ?)",
            (report_id, validate_event_name(name), utc_now()),
        )

    def event(self, report_id: str, name: str) -> None:
        with closing(sqlite3.connect(self.path)) as connection, connection:
            self._event(connection, report_id, name)

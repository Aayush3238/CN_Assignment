"""Run history (SQLite) and export bundles.

SQLite is part of the Python standard library, so run history adds no external
dependency. Each run is stored twice: a summary row for fast ``runs list`` and
the full JSON payload for exact reconstruction by ``runs show``/``export``.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from netarchitect.core.models import RunResult
from netarchitect.report import render_html, render_json, render_markdown

DEFAULT_DB = Path("netarchitect.db")


def _connect(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(db_path: Path | str = DEFAULT_DB) -> None:
    """Create tables if they do not exist."""
    with closing(_connect(db_path)) as connection:
        with connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    profile TEXT NOT NULL,
                    endpoints INTEGER NOT NULL,
                    media_summary TEXT,
                    subnet_count INTEGER NOT NULL,
                    host_utilization REAL NOT NULL,
                    result_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL REFERENCES runs(id),
                    filename TEXT NOT NULL,
                    content TEXT NOT NULL
                );
                """
            )


def save_run(result: RunResult, db_path: Path | str = DEFAULT_DB) -> int:
    """Persist one run and its generated configs; return the new run id."""
    init_db(db_path)
    media_summary = ", ".join(
        f"{item.link}: {item.media}" for item in result.media
    )
    payload = result.model_dump_json()
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with closing(_connect(db_path)) as connection:
        with connection:
            cursor = connection.execute(
                """
                INSERT INTO runs (
                    created_at, profile, endpoints, media_summary,
                    subnet_count, host_utilization, result_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created_at,
                    result.scenario.profile,
                    result.scenario.endpoints,
                    media_summary,
                    len(result.subnets),
                    result.utilization.host_pct,
                    payload,
                ),
            )
            run_id = int(cursor.lastrowid)
            connection.executemany(
                "INSERT INTO artifacts (run_id, filename, content) VALUES (?, ?, ?)",
                [
                    (run_id, filename, content)
                    for filename, content in result.configs.items()
                ],
            )
    return run_id


def list_runs(db_path: Path | str = DEFAULT_DB) -> list[dict]:
    """Return lightweight run summaries, newest first."""
    init_db(db_path)
    with closing(_connect(db_path)) as connection:
        rows = connection.execute(
            """
            SELECT id, created_at, profile, endpoints, media_summary,
                   subnet_count, host_utilization
            FROM runs ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_run(run_id: int, db_path: Path | str = DEFAULT_DB) -> RunResult | None:
    """Load a full run by id, or ``None`` if it does not exist."""
    init_db(db_path)
    with closing(_connect(db_path)) as connection:
        row = connection.execute(
            "SELECT result_json FROM runs WHERE id = ?", (run_id,)
        ).fetchone()
    if row is None:
        return None
    return RunResult.model_validate_json(row["result_json"])


def write_export(result: RunResult, out_dir: Path | str) -> list[Path]:
    """Write configs, rationale Markdown, JSON, and a static HTML report."""
    directory = Path(out_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, content in result.configs.items():
        path = directory / filename
        path.write_text(content, encoding="utf-8")
        written.append(path)

    rationale_path = directory / "rationale.md"
    rationale_path.write_text(render_markdown(result), encoding="utf-8")
    written.append(rationale_path)

    json_path = directory / "run.json"
    json_path.write_text(render_json(result), encoding="utf-8")
    written.append(json_path)

    html_path = directory / "report.html"
    html_path.write_text(render_html(result), encoding="utf-8")
    written.append(html_path)

    return written

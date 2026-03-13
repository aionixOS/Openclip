"""
database.py — Async SQLite database layer for OpenClip.

Uses aiosqlite to provide non-blocking database access.  Manages the
connection to the local SQLite database and provides CRUD helpers for
the `projects` and `clips` tables.

How it works:
    Every public function opens a short-lived aiosqlite connection, runs
    its query, and closes the connection.  This keeps the API simple and
    avoids long-lived connection state.  WAL journal mode and foreign
    keys are enabled on every connection for performance and integrity.
"""

import aiosqlite  # type: ignore
import uuid
import os
import json
from typing import Optional
from dotenv import load_dotenv  # type: ignore

load_dotenv()


# ---------------------------------------------------------------------------
# Path to the SQLite database file (relative to project root)
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "data", "openclip.db"))


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------

async def _get_connection() -> aiosqlite.Connection:
    """Return an async SQLite connection with row-factory enabled."""
    conn = await aiosqlite.connect(DB_PATH)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL;")
    await conn.execute("PRAGMA foreign_keys=ON;")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

async def init_db() -> None:
    """
    Create the `projects`, `clips`, and `settings` tables if they do not
    exist.  Also runs lightweight migrations (e.g. adding columns) so
    that upgrades are seamless.

    Called once at application startup to guarantee the schema is ready
    before any request arrives.
    """
    conn = await _get_connection()
    try:
        await conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id          TEXT PRIMARY KEY,
                youtube_url TEXT NOT NULL,
                title       TEXT,
                status      TEXT NOT NULL DEFAULT 'pending',
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clips (
                id          TEXT PRIMARY KEY,
                project_id  TEXT NOT NULL,
                file_path   TEXT NOT NULL,
                start_time  REAL NOT NULL,
                end_time    REAL NOT NULL,
                duration    REAL NOT NULL,
                reframed    BOOLEAN NOT NULL DEFAULT 1,
                captioned   BOOLEAN NOT NULL DEFAULT 0,
                title       TEXT,
                reason      TEXT,
                viral_score INTEGER,
                face_count  INTEGER,
                layout_mode TEXT,
                caption_style TEXT,
                needs_user_confirm BOOLEAN NOT NULL DEFAULT 0,
                hashtags TEXT,
                tags TEXT,
                created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );
            """
        )
        await conn.commit()

        # --- Migrations: add columns if they don't exist yet -----------
        for col in ("title", "reason", "viral_score", "face_count", "layout_mode", "caption_style", "needs_user_confirm", "hashtags", "tags"):
            try:
                col_type = "BOOLEAN" if col == "needs_user_confirm" else ("INTEGER" if col in ["viral_score", "face_count"] else "TEXT")
                await conn.execute(
                    f"ALTER TABLE clips ADD COLUMN {col} {col_type}"
                )
                await conn.commit()
            except Exception:
                pass  # column already exists — safe to ignore

    except Exception as exc:
        raise RuntimeError(f"Failed to initialise database: {exc}") from exc
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Project CRUD
# ---------------------------------------------------------------------------

async def create_project(youtube_url: str) -> dict:
    """
    Insert a new project row and return its id + initial status.

    Args:
        youtube_url: The YouTube video URL to associate with this project.

    Returns:
        dict with ``project_id`` and ``status`` keys.
    """
    project_id = str(uuid.uuid4())
    conn = await _get_connection()
    try:
        await conn.execute(
            "INSERT INTO projects (id, youtube_url) VALUES (?, ?)",
            (project_id, youtube_url),
        )
        await conn.commit()
        ret = {"project_id": project_id, "status": "pending"}
    except Exception as exc:
        raise RuntimeError(f"Failed to create project: {exc}") from exc
    finally:
        await conn.close()
    return ret


async def update_project_status(project_id: str, status: str) -> None:
    """
    Update the status field of a project.

    Args:
        project_id: UUID of the project.
        status:     New status value (pending/downloading/processing/done/error).
    """
    conn = await _get_connection()
    try:
        await conn.execute(
            "UPDATE projects SET status = ? WHERE id = ?",
            (status, project_id),
        )
        await conn.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to update project status: {exc}") from exc
    finally:
        await conn.close()


async def update_project_title(project_id: str, title: str) -> None:
    """
    Update the title field of a project.

    Args:
        project_id: UUID of the project.
        title:      New title string.
    """
    conn = await _get_connection()
    try:
        await conn.execute(
            "UPDATE projects SET title = ? WHERE id = ?",
            (title, project_id),
        )
        await conn.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to update project title: {exc}") from exc
    finally:
        await conn.close()


async def get_all_projects() -> list[dict]:
    """
    Return every project, newest first, with a ``clip_count`` field.

    The clip count is computed via a LEFT JOIN on the clips table so
    that projects with zero clips are still returned.

    Returns:
        List of project dicts, each containing:
        id, title, status, created_at, clip_count.
    """
    conn = await _get_connection()
    try:
        cursor = await conn.execute(
            """
            SELECT p.id, p.title, p.youtube_url, p.status, p.created_at,
                   COUNT(c.id) AS clip_count
            FROM projects p
            LEFT JOIN clips c ON c.project_id = p.id
            GROUP BY p.id
            ORDER BY p.created_at DESC
            """
        )
        rows = await cursor.fetchall()
        ret = [
            {
                "id": row["id"],
                "title": row["title"],
                "youtube_url": row["youtube_url"],
                "status": row["status"],
                "created_at": row["created_at"],
                "clip_count": row["clip_count"],
            }
            for row in rows
        ]
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch projects: {exc}") from exc
    finally:
        await conn.close()
    return ret


async def get_project(project_id: str) -> Optional[dict]:
    """
    Return a single project by ID, including its list of clips.

    Args:
        project_id: UUID of the project to fetch.

    Returns:
        A dict with project fields plus a ``clips`` list, or *None* if
        the project does not exist.
    """
    conn = await _get_connection()
    try:
        # Fetch project row
        cursor = await conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        project = {
            "id": row["id"],
            "title": row["title"],
            "youtube_url": row["youtube_url"],
            "status": row["status"],
            "created_at": row["created_at"],
        }

        # Fetch associated clips
        cursor = await conn.execute(
            "SELECT * FROM clips WHERE project_id = ? ORDER BY start_time",
            (project_id,),
        )
        clip_rows = await cursor.fetchall()
        project["clips"] = [
            {
                "id": c["id"],
                "project_id": c["project_id"],
                "file_path": c["file_path"],
                "start_time": c["start_time"],
                "end_time": c["end_time"],
                "duration": c["duration"],
                "reframed": bool(c["reframed"]),
                "captioned": bool(c["captioned"]),
                "title": c["title"],
                "reason": c["reason"],
                "viral_score": c["viral_score"],
                "face_count": c["face_count"],
                "layout_mode": c["layout_mode"] if "layout_mode" in c.keys() else "none",
                "caption_style": c["caption_style"] if "caption_style" in c.keys() else "none",
                "needs_user_confirm": bool(c["needs_user_confirm"]) if "needs_user_confirm" in c.keys() else False,
                "hashtags": json.loads(c["hashtags"]) if "hashtags" in c.keys() and c["hashtags"] else [],
                "tags": json.loads(c["tags"]) if "tags" in c.keys() and c["tags"] else [],
                "created_at": c["created_at"],
            }
            for c in clip_rows
        ]

        return project
    except Exception as exc:
        raise RuntimeError(f"Failed to fetch project: {exc}") from exc
    finally:
        await conn.close()


async def save_clip(
    project_id: str,
    file_path: str,
    start_time: float,
    end_time: float,
    title: Optional[str] = None,
    reason: Optional[str] = None,
    viral_score: Optional[int] = None,
    face_count: Optional[int] = None,
    layout_mode: Optional[str] = None,
    caption_style: Optional[str] = None,
    needs_user_confirm: bool = False,
    reframed: bool = True,
    hashtags: Optional[list] = None,
    tags: Optional[list] = None,
) -> dict:
    """
    Insert a new clip row for a project.

    The duration is automatically computed as ``end_time - start_time``.

    Args:
        project_id: UUID of the parent project.
        file_path:  Absolute path to the clip file on disk.
        start_time: Clip start in seconds.
        end_time:   Clip end in seconds.
        title:      Optional clip title (from LLM suggestion).
        reason:     Optional reason why this clip was chosen.
        viral_score: Optional viral score out of 10.
        face_count: Optional max faces detected in the clip.
        reframed:   Whether the clip was reframed to 9:16.

    Returns:
        dict with the new clip's fields.
    """
    clip_id = str(uuid.uuid4())
    duration = end_time - start_time
    hashtags_json = json.dumps(hashtags) if hashtags else None
    tags_json = json.dumps(tags) if tags else None
    conn = await _get_connection()
    try:
        await conn.execute(
            """INSERT INTO clips
               (id, project_id, file_path, start_time, end_time, duration, title, reason, viral_score, face_count, layout_mode, caption_style, needs_user_confirm, reframed, hashtags, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (clip_id, project_id, file_path, start_time, end_time, duration, title, reason, viral_score, face_count, layout_mode, caption_style, int(needs_user_confirm), int(reframed), hashtags_json, tags_json),
        )
        await conn.commit()
        ret = {
            "id": clip_id,
            "project_id": project_id,
            "file_path": file_path,
            "start_time": start_time,
            "end_time": end_time,
            "duration": duration,
            "reframed": reframed,
            "captioned": False,
            "title": title,
            "reason": reason,
            "viral_score": viral_score,
            "face_count": face_count,
            "layout_mode": layout_mode,
            "caption_style": caption_style,
            "needs_user_confirm": needs_user_confirm,
            "hashtags": hashtags or [],
            "tags": tags or [],
        }
    except Exception as exc:
        raise RuntimeError(f"Failed to save clip: {exc}") from exc
    finally:
        await conn.close()
    return ret


async def delete_project(project_id: str) -> None:
    """
    Delete a project and all of its associated clips.

    Clips are deleted first to satisfy the foreign-key constraint,
    then the project row is removed.

    Args:
        project_id: UUID of the project to delete.
    """
    conn = await _get_connection()
    try:
        await conn.execute(
            "DELETE FROM clips WHERE project_id = ?", (project_id,)
        )
        await conn.execute(
            "DELETE FROM projects WHERE id = ?", (project_id,)
        )
        await conn.commit()
    except Exception as exc:
        raise RuntimeError(f"Failed to delete project: {exc}") from exc
    finally:
        await conn.close()

async def get_clip(clip_id: str) -> Optional[dict]:
    """Fetch a single clip by its ID."""
    conn = await _get_connection()
    try:
        cursor = await conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None
    except Exception as exc:
        raise RuntimeError(f"Failed to get clip: {exc}") from exc
    finally:
        await conn.close()

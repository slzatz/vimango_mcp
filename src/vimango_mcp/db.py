"""Database operations for vimango SQLite databases."""

import sqlite3
from pathlib import Path
from typing import Any, Optional, Tuple
import json

# Default UUIDs for "none" containers (matches vimango init.go)
DEFAULT_CONTEXT_UUID = "00000000-0000-0000-0000-000000000001"
DEFAULT_FOLDER_UUID = "00000000-0000-0000-0000-000000000002"


class VimangoDatabase:
    """Handle operations on vimango SQLite databases."""

    def __init__(self, main_db_path: str, fts_db_path: str):
        """
        Initialize database connections.

        Args:
            main_db_path: Path to vimango.db
            fts_db_path: Path to fts5_vimango.db (not used for inserts)
        """
        self.main_db_path = main_db_path
        self.fts_db_path = fts_db_path
        self.main_db: Optional[sqlite3.Connection] = None
        self.fts_db: Optional[sqlite3.Connection] = None

    def connect(self):
        """Establish database connections."""
        # Use a short busy timeout so we wait briefly for vimango's writes before failing
        self.main_db = sqlite3.connect(self.main_db_path, timeout=2.0)
        # Enable foreign keys
        self.main_db.execute("PRAGMA foreign_keys=ON")
        if self.fts_db_path:
            # Open FTS database read-only; raises if unavailable so caller can react
            self.fts_db = sqlite3.connect(
                f"file:{self.fts_db_path}?mode=ro",
                uri=True,
                timeout=2.0
            )

    def close(self):
        """Close database connections."""
        if self.main_db:
            self.main_db.close()
        if self.fts_db:
            self.fts_db.close()
            self.fts_db = None

    def insert_note(
        self,
        title: str,
        note: str,
        context_uuid: str = DEFAULT_CONTEXT_UUID,
        folder_uuid: str = DEFAULT_FOLDER_UUID,
        star: bool = False
    ) -> int:
        """
        Insert a new note into the task table.

        Args:
            title: Note title
            note: Note body (markdown)
            context_uuid: Context UUID (default = "none" context)
            folder_uuid: Folder UUID (default = "none" folder)
            star: Star/favorite flag

        Returns:
            The ID of the newly created task

        Note:
            - Leaves tid NULL so sync can assign the real server tid later
            - FTS database is NOT updated (happens during sync)
        """
        try:
            cursor = self.main_db.execute(
                """INSERT INTO task (title, note, folder_uuid, context_uuid, star, added, modified)
                   VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
                (title, note, folder_uuid, context_uuid, star)
            )
            task_id = cursor.lastrowid
            self.main_db.commit()
            return task_id
        except sqlite3.DatabaseError:
            # Ensure we release SQLite's write lock if the insert fails
            self.main_db.rollback()
            raise

    def list_contexts(self) -> list[Tuple[int, int, str, str, bool]]:
        """
        List all available contexts.

        Returns:
            List of tuples: (id, tid, title, uuid, star)
        """
        cursor = self.main_db.execute(
            "SELECT id, tid, title, uuid, star FROM context WHERE deleted=0 ORDER BY title COLLATE NOCASE"
        )
        return cursor.fetchall()

    def list_folders(self) -> list[Tuple[int, int, str, str, bool]]:
        """
        List all available folders.

        Returns:
            List of tuples: (id, tid, title, uuid, star)
        """
        cursor = self.main_db.execute(
            "SELECT id, tid, title, uuid, star FROM folder WHERE deleted=0 ORDER BY title COLLATE NOCASE"
        )
        return cursor.fetchall()

    def get_context_uuid_by_name(self, name: str) -> Optional[str]:
        """
        Get context UUID by name.

        Args:
            name: Context name

        Returns:
            Context UUID or None if not found
        """
        cursor = self.main_db.execute(
            "SELECT uuid FROM context WHERE title=? AND deleted=0",
            (name,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_folder_uuid_by_name(self, name: str) -> Optional[str]:
        """
        Get folder UUID by name.

        Args:
            name: Folder name

        Returns:
            Folder UUID or None if not found
        """
        cursor = self.main_db.execute(
            "SELECT uuid FROM folder WHERE title=? AND deleted=0",
            (name,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def find_notes(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """
        Search for notes using the FTS database and return basic metadata.

        Args:
            query: Full-text search string (minimum 3 characters)
            limit: Maximum number of rows to return (minimum 1)

        Returns:
            List of dictionaries containing rank, id, tid, title, context_title, folder_title
        """
        cleaned_query = query.strip()
        if len(cleaned_query) < 3:
            raise ValueError("Search query must be at least 3 characters long.")

        if limit <= 0:
            limit = 5

        if not self.fts_db:
            raise RuntimeError("FTS database is not connected.")

        try:
            cursor = self.fts_db.execute(
                "SELECT tid FROM fts WHERE fts MATCH ? "
                "ORDER BY bm25(fts, 2.0, 1.0, 5.0) LIMIT ?",
                (cleaned_query, limit)
            )
        except sqlite3.DatabaseError as exc:
            raise RuntimeError(f"FTS search failed: {exc}") from exc

        tids = [row[0] for row in cursor.fetchall()]
        cursor.close()

        if not tids:
            return []

        ranked_tids = list(enumerate(tids, start=1))
        values_clause = ", ".join(["(?, ?)"] * len(ranked_tids))
        params: list[Any] = []
        for rank, tid in ranked_tids:
            params.extend([rank, tid])

        sql = (
            f"WITH matches(rank, tid) AS (VALUES {values_clause}) "
            "SELECT matches.rank, task.id, task.tid, task.title, "
            "COALESCE(context.title, 'none') AS context_title, "
            "COALESCE(folder.title, 'none') AS folder_title "
            "FROM matches "
            "JOIN task ON task.tid = matches.tid "
            "LEFT JOIN context ON context.uuid = task.context_uuid "
            "LEFT JOIN folder ON folder.uuid = task.folder_uuid "
            "WHERE task.deleted = 0 AND task.archived = 0 "
            "ORDER BY matches.rank"
        )

        main_cursor = self.main_db.execute(sql, params)
        rows = main_cursor.fetchall()
        main_cursor.close()

        results: list[dict[str, Any]] = []
        for rank, task_id, tid, title, context_title, folder_title in rows:
            results.append(
                {
                    "rank": rank,
                    "id": task_id,
                    "tid": tid,
                    "title": title,
                    "context_title": context_title,
                    "folder_title": folder_title,
                }
            )

        return results

    def get_note_by_tid(self, tid: int) -> Optional[dict[str, Any]]:
        """
        Retrieve the full note content and metadata for a given task tid.

        Args:
            tid: Task TID (synchronization identifier)

        Returns:
            Dictionary with id, tid, title, note, context_title, folder_title, or None if not found.
        """
        cursor = self.main_db.execute(
            """
            SELECT task.id, task.tid, task.title, task.note,
                   COALESCE(context.title, 'none') AS context_title,
                   COALESCE(folder.title, 'none') AS folder_title
            FROM task
            LEFT JOIN context ON context.uuid = task.context_uuid
            LEFT JOIN folder ON folder.uuid = task.folder_uuid
            WHERE task.tid = ? AND task.deleted = 0 AND task.archived = 0
            """,
            (tid,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        task_id, task_tid, title, note, context_title, folder_title = row
        return {
            "id": task_id,
            "tid": task_tid,
            "title": title,
            "note": note or "",
            "context_title": context_title,
            "folder_title": folder_title,
        }


    def get_note_by_id(self, note_id: int) -> Optional[dict[str, Any]]:
        """
        Retrieve the full note content and metadata for a given local ID.

        Args:
            note_id: Local database ID

        Returns:
            Dictionary with id, tid, title, note, context_title, folder_title, or None if not found.
        """
        cursor = self.main_db.execute(
            """
            SELECT task.id, task.tid, task.title, task.note,
                   COALESCE(context.title, 'none') AS context_title,
                   COALESCE(folder.title, 'none') AS folder_title
            FROM task
            LEFT JOIN context ON context.uuid = task.context_uuid
            LEFT JOIN folder ON folder.uuid = task.folder_uuid
            WHERE task.id = ? AND task.deleted = 0 AND task.archived = 0
            """,
            (note_id,),
        )
        row = cursor.fetchone()
        cursor.close()

        if not row:
            return None

        task_id, task_tid, title, note, context_title, folder_title = row
        return {
            "id": task_id,
            "tid": task_tid,
            "title": title,
            "note": note or "",
            "context_title": context_title,
            "folder_title": folder_title,
        }

    def update_note_metadata(
        self,
        note_id: int,
        context_uuid: Optional[str] = None,
        folder_uuid: Optional[str] = None,
        title: Optional[str] = None,
        star: Optional[bool] = None
    ) -> bool:
        """
        Update metadata fields on an existing note.

        Args:
            note_id: Local database ID of the note
            context_uuid: New context UUID (optional)
            folder_uuid: New folder UUID (optional)
            title: New title (optional)
            star: New star/favorite value (optional)

        Returns:
            True if a row was updated, False otherwise
        """
        updates = []
        params = []

        if context_uuid is not None:
            updates.append("context_uuid = ?")
            params.append(context_uuid)
        if folder_uuid is not None:
            updates.append("folder_uuid = ?")
            params.append(folder_uuid)
        if title is not None:
            updates.append("title = ?")
            params.append(title)
        if star is not None:
            updates.append("star = ?")
            params.append(star)

        if not updates:
            return False

        updates.append("modified = datetime('now')")
        params.append(note_id)

        sql = f"UPDATE task SET {', '.join(updates)} WHERE id = ? AND deleted = 0"
        try:
            cursor = self.main_db.execute(sql, params)
            self.main_db.commit()
            return cursor.rowcount > 0
        except sqlite3.DatabaseError:
            self.main_db.rollback()
            raise


def load_config(config_path: str = "config.json") -> dict:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config.json

    Returns:
        Configuration dictionary
    """
    with open(config_path) as f:
        return json.load(f)

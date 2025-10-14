"""Database operations for vimango SQLite databases."""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple
import json


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

    def connect(self):
        """Establish database connections."""
        self.main_db = sqlite3.connect(self.main_db_path)
        # Enable foreign keys
        self.main_db.execute("PRAGMA foreign_keys=ON")

    def close(self):
        """Close database connections."""
        if self.main_db:
            self.main_db.close()

    def insert_note(
        self,
        title: str,
        note: str,
        context_tid: int = 1,  # Default: "none"
        folder_tid: int = 1,   # Default: "none"
        star: bool = False
    ) -> int:
        """
        Insert a new note into the task table.

        Args:
            title: Note title
            note: Note body (markdown)
            context_tid: Context TID (default 1 = "none")
            folder_tid: Folder TID (default 1 = "none")
            star: Star/favorite flag

        Returns:
            The ID of the newly created task

        Note:
            - Creates entry with tid = -1 (sentinel for "needs sync")
            - FTS database is NOT updated (happens during sync)
        """
        cursor = self.main_db.execute(
            """INSERT INTO task (tid, title, note, folder_tid, context_tid, star, added, modified)
               VALUES (-1, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (title, note, folder_tid, context_tid, star)
        )
        task_id = cursor.lastrowid
        self.main_db.commit()
        return task_id

    def list_contexts(self) -> list[Tuple[int, int, str, bool]]:
        """
        List all available contexts.

        Returns:
            List of tuples: (id, tid, title, star)
        """
        cursor = self.main_db.execute(
            "SELECT id, tid, title, star FROM context WHERE deleted=0 ORDER BY title COLLATE NOCASE"
        )
        return cursor.fetchall()

    def list_folders(self) -> list[Tuple[int, int, str, bool]]:
        """
        List all available folders.

        Returns:
            List of tuples: (id, tid, title, star)
        """
        cursor = self.main_db.execute(
            "SELECT id, tid, title, star FROM folder WHERE deleted=0 ORDER BY title COLLATE NOCASE"
        )
        return cursor.fetchall()

    def get_context_tid_by_name(self, name: str) -> Optional[int]:
        """
        Get context TID by name.

        Args:
            name: Context name

        Returns:
            Context TID or None if not found
        """
        cursor = self.main_db.execute(
            "SELECT tid FROM context WHERE title=? AND deleted=0",
            (name,)
        )
        result = cursor.fetchone()
        return result[0] if result else None

    def get_folder_tid_by_name(self, name: str) -> Optional[int]:
        """
        Get folder TID by name.

        Args:
            name: Folder name

        Returns:
            Folder TID or None if not found
        """
        cursor = self.main_db.execute(
            "SELECT tid FROM folder WHERE title=? AND deleted=0",
            (name,)
        )
        result = cursor.fetchone()
        return result[0] if result else None


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

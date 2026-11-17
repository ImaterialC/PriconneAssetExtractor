#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NewDataMiner.database - Direct SQLite reader, schema inspector, and search engine for master.db
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ColumnInfo:
    cid: int
    name: str
    type: str
    notnull: bool
    default_value: Any
    pk: bool


@dataclass
class TableInfo:
    name: str
    row_count: int
    column_count: int
    columns: List[ColumnInfo] = field(default_factory=list)


class GameDatabase:
    """
    Direct SQLite interface to Princess Connect! Re:Dive master.db.
    Supports deobfuscated databases (such as Robo Ninon) and standard game databases.
    """

    DEFAULT_DB_FILENAME = "master.db"

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is not None:
            self.db_path = Path(db_path)
        else:
            # Check default locations
            cwd_db = Path.cwd() / self.DEFAULT_DB_FILENAME
            script_dir_db = Path(__file__).resolve().parent.parent / self.DEFAULT_DB_FILENAME
            if cwd_db.is_file():
                self.db_path = cwd_db
            elif script_dir_db.is_file():
                self.db_path = script_dir_db
            else:
                self.db_path = script_dir_db

        self._conn: Optional[sqlite3.Connection] = None

    def is_available(self) -> bool:
        """Check if the database file exists and is a valid SQLite file."""
        if not self.db_path.is_file():
            return False
        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' LIMIT 1")
            conn.close()
            return True
        except Exception:
            return False

    def connect(self) -> sqlite3.Connection:
        """Open a read-only SQLite connection."""
        if self._conn is None:
            if not self.db_path.is_file():
                raise FileNotFoundError(f"Game database not found at: {self.db_path}")
            # Open in read-only URI mode to prevent any accidental write modification
            self._conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> GameDatabase:
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def list_tables(self) -> List[Dict[str, Any]]:
        """Enumerate all tables with their estimated or exact row count."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        table_names = [row["name"] for row in cursor.fetchall()]

        results = []
        for name in table_names:
            try:
                cursor.execute(f"SELECT COUNT(*) as count FROM {name}")
                row_count = cursor.fetchone()["count"]
            except Exception:
                row_count = -1
            results.append({"name": name, "row_count": row_count})
        return results

    def get_table_schema(self, table_name: str) -> List[ColumnInfo]:
        """Return the schema (columns, types, pk) for a given table."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(f"PRAGMA table_info({table_name})")
        cols = []
        for row in cursor.fetchall():
            cols.append(ColumnInfo(
                cid=row[0],
                name=row[1],
                type=row[2],
                notnull=bool(row[3]),
                default_value=row[4],
                pk=bool(row[5])
            ))
        return cols

    def has_table(self, table_name: str) -> bool:
        """Check if a table exists in the database."""
        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        return cursor.fetchone() is not None

    def has_column(self, table_name: str, column_name: str) -> bool:
        """Check if a column exists in a given table."""
        schema = self.get_table_schema(table_name)
        return any(c.name.lower() == column_name.lower() for c in schema)

    # -------------------------------------------------------------------------
    # Search APIs
    # -------------------------------------------------------------------------

    def search_units(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search playable and NPC units by unit ID, English name, Japanese name,
        kana, voice actor, or guild.
        """
        if not self.has_table("unit_data"):
            return []

        conn = self.connect()
        cursor = conn.cursor()
        q_wild = f"%{query.strip()}%"

        has_profile = self.has_table("unit_profile")
        has_unit_jp = self.has_column("unit_data", "unit_name_jp")

        # Build dynamic query to support various schemas (with/without unit_profile or unit_name_jp)
        select_fields = [
            "u.unit_id",
            "u.unit_name",
            "u.rarity" if self.has_column("unit_data", "rarity") else "0 AS rarity",
            "u.kana" if self.has_column("unit_data", "kana") else "'' AS kana",
            "u.comment" if self.has_column("unit_data", "comment") else "'' AS comment",
        ]

        if has_unit_jp:
            select_fields.append("u.unit_name_jp")
        else:
            select_fields.append("'' AS unit_name_jp")

        if has_profile:
            select_fields.extend([
                "p.voice",
                "p.guild",
                "p.age",
                "p.catch_copy" if self.has_column("unit_profile", "catch_copy") else "'' AS catch_copy",
            ])
            sql = f"""
                SELECT {', '.join(select_fields)}
                FROM unit_data u
                LEFT JOIN unit_profile p ON u.unit_id = p.unit_id
                WHERE CAST(u.unit_id AS TEXT) LIKE ?
                   OR u.unit_name LIKE ?
                   OR {'u.unit_name_jp LIKE ? OR' if has_unit_jp else ''}
                   u.kana LIKE ?
                   OR p.voice LIKE ?
                   OR p.guild LIKE ?
                ORDER BY u.unit_id ASC
                LIMIT ?
            """
            params = [q_wild, q_wild]
            if has_unit_jp:
                params.append(q_wild)
            params.extend([q_wild, q_wild, q_wild, limit])
        else:
            sql = f"""
                SELECT {', '.join(select_fields)}
                FROM unit_data u
                WHERE CAST(u.unit_id AS TEXT) LIKE ?
                   OR u.unit_name LIKE ?
                   OR {'u.unit_name_jp LIKE ? OR' if has_unit_jp else ''}
                   u.kana LIKE ?
                ORDER BY u.unit_id ASC
                LIMIT ?
            """
            params = [q_wild, q_wild]
            if has_unit_jp:
                params.append(q_wild)
            params.extend([q_wild, limit])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def search_stories(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search story episodes by story ID, title, subtitle, or story group.
        """
        if not self.has_table("story_detail"):
            return []

        conn = self.connect()
        cursor = conn.cursor()
        q_wild = f"%{query.strip()}%"

        has_sub_title = self.has_column("story_detail", "sub_title")
        has_story_data = self.has_table("story_data")

        select_fields = [
            "sd.story_id",
            "sd.story_group_id",
            "sd.title",
            "sd.sub_title" if has_sub_title else "'' AS sub_title",
        ]

        if has_story_data and self.has_column("story_data", "story_type"):
            select_fields.append("sdata.story_type")
            sql = f"""
                SELECT {', '.join(select_fields)}
                FROM story_detail sd
                LEFT JOIN story_data sdata ON sd.story_group_id = sdata.story_group_id
                WHERE CAST(sd.story_id AS TEXT) LIKE ?
                   OR sd.title LIKE ?
                   OR {'sd.sub_title LIKE ? OR' if has_sub_title else ''}
                   CAST(sd.story_group_id AS TEXT) LIKE ?
                ORDER BY sd.story_id ASC
                LIMIT ?
            """
            params = [q_wild, q_wild]
            if has_sub_title:
                params.append(q_wild)
            params.extend([q_wild, limit])
        else:
            sql = f"""
                SELECT {', '.join(select_fields)}
                FROM story_detail sd
                WHERE CAST(sd.story_id AS TEXT) LIKE ?
                   OR sd.title LIKE ?
                   OR {'sd.sub_title LIKE ? OR' if has_sub_title else ''}
                   CAST(sd.story_group_id AS TEXT) LIKE ?
                ORDER BY sd.story_id ASC
                LIMIT ?
            """
            params = [q_wild, q_wild]
            if has_sub_title:
                params.append(q_wild)
            params.extend([q_wild, limit])

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def search_skills(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search skill records by skill ID, English name, Japanese name, or description.
        """
        if not self.has_table("skill_data"):
            return []

        conn = self.connect()
        cursor = conn.cursor()
        q_wild = f"%{query.strip()}%"

        has_jp = self.has_column("skill_data", "name_jp")
        has_desc_jp = self.has_column("skill_data", "description_jp")

        where_clauses = [
            "CAST(skill_id AS TEXT) LIKE ?",
            "name LIKE ?",
            "description LIKE ?"
        ]
        params = [q_wild, q_wild, q_wild]

        if has_jp:
            where_clauses.append("name_jp LIKE ?")
            params.append(q_wild)
        if has_desc_jp:
            where_clauses.append("description_jp LIKE ?")
            params.append(q_wild)

        sql = f"""
            SELECT skill_id, name,
                   {'name_jp' if has_jp else "'' AS name_jp"},
                   description,
                   {'description_jp' if has_desc_jp else "'' AS description_jp"},
                   icon_type
            FROM skill_data
            WHERE {' OR '.join(where_clauses)}
            ORDER BY skill_id ASC
            LIMIT ?
        """
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def search_dialogues(self, query: str, limit: int = 50) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search dialogue lines across homescreen interactions (unit_comments)
        and guildhouse chirping (room_unit_comments).
        """
        conn = self.connect()
        cursor = conn.cursor()
        q_wild = f"%{query.strip()}%"

        homescreen_rows = []
        if self.has_table("unit_comments"):
            sql_hs = """
                SELECT id, unit_id, voice_id, use_type, description
                FROM unit_comments
                WHERE description LIKE ?
                   OR CAST(unit_id AS TEXT) LIKE ?
                   OR CAST(voice_id AS TEXT) LIKE ?
                ORDER BY unit_id ASC, voice_id ASC
                LIMIT ?
            """
            cursor.execute(sql_hs, (q_wild, q_wild, q_wild, limit))
            homescreen_rows = [dict(r) for r in cursor.fetchall()]

        guildhouse_rows = []
        if self.has_table("room_unit_comments"):
            sql_gh = """
                SELECT id, unit_id, voice_id, trigger, description
                FROM room_unit_comments
                WHERE description LIKE ?
                   OR CAST(unit_id AS TEXT) LIKE ?
                   OR CAST(voice_id AS TEXT) LIKE ?
                ORDER BY unit_id ASC, voice_id ASC
                LIMIT ?
            """
            cursor.execute(sql_gh, (q_wild, q_wild, q_wild, limit))
            guildhouse_rows = [dict(r) for r in cursor.fetchall()]

        return {
            "homescreen": homescreen_rows,
            "guildhouse": guildhouse_rows,
        }

    # -------------------------------------------------------------------------
    # SQL Export & Raw Query
    # -------------------------------------------------------------------------

    def export_table_sql(self, table_name: str, out_path: Path, max_rows: Optional[int] = None) -> int:
        """
        Export a specific table schema and rows to a standard .sql file.
        Returns the number of rows exported.
        """
        if not self.has_table(table_name):
            raise ValueError(f"Table '{table_name}' does not exist in database.")

        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        conn = self.connect()
        cursor = conn.cursor()

        # Get CREATE TABLE statement from sqlite_master
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        create_sql_row = cursor.fetchone()
        create_sql = create_sql_row[0] if create_sql_row and create_sql_row[0] else ""

        # Fetch rows
        limit_clause = f" LIMIT {max_rows}" if max_rows and max_rows > 0 else ""
        cursor.execute(f"SELECT * FROM {table_name}{limit_clause}")
        rows = cursor.fetchall()

        if not rows:
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(f"-- Table export: {table_name} (0 rows)\n")
                if create_sql:
                    f.write(f"{create_sql};\n")
            return 0

        col_names = [col[0] for col in cursor.description]
        col_str = ", ".join(f'"{c}"' for c in col_names)

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"-- Table export: {table_name} ({len(rows):,} rows)\n")
            f.write(f"-- Generated from: {self.db_path.name}\n\n")
            if create_sql:
                f.write(f"{create_sql};\n\n")

            f.write(f"BEGIN TRANSACTION;\n")
            for r in rows:
                val_strs = []
                for v in r:
                    if v is None:
                        val_strs.append("NULL")
                    elif isinstance(v, (int, float)):
                        val_strs.append(str(v))
                    else:
                        escaped = str(v).replace("'", "''")
                        val_strs.append(f"'{escaped}'")
                f.write(f"INSERT INTO \"{table_name}\" ({col_str}) VALUES ({', '.join(val_strs)});\n")
            f.write(f"COMMIT;\n")

        return len(rows)

    def raw_query(self, sql: str, params: Tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """Execute a read-only query and return records as dictionaries."""
        sql_clean = sql.strip().upper()
        if not (sql_clean.startswith("SELECT") or sql_clean.startswith("PRAGMA") or sql_clean.startswith("EXPLAIN")):
            raise PermissionError("Only read-only queries (SELECT, PRAGMA, EXPLAIN) are allowed.")

        conn = self.connect()
        cursor = conn.cursor()
        cursor.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

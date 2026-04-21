# local_db.py - Local database for storing and retrieving data.
import os
import sqlite3
from typing import Any

DB_PATH = os.path.join(os.path.dirname(__file__), "machine_local.db")

class LocalDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_db(self) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()

            cur.execute("""
                CREATE TABLE IF NOT EXISTS fruits (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER NOT NULL,
                    sales INTEGER NOT NULL DEFAULT 0,
                    best_seller INTEGER NOT NULL DEFAULT 0,
                    asset_name TEXT NOT NULL,
                    updated_at_local TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS addons (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    price REAL NOT NULL,
                    stock INTEGER NOT NULL,
                    sales INTEGER NOT NULL DEFAULT 0,
                    updated_at_local TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS ingredients (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    stock INTEGER NOT NULL,
                    updated_at_local TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS local_sales (
                    local_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sale_id TEXT NOT NULL UNIQUE,
                    total_price REAL NOT NULL,
                    payment_method TEXT NOT NULL,
                    selected_fruits TEXT NOT NULL,
                    selected_addons TEXT,
                    sync_status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    synced_at TEXT,
                    last_error TEXT
                )
            """)

            conn.commit()
        finally:
            conn.close()

    def replace_fruits(self, fruits: dict[str, dict[str, Any]]) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM fruits")
            for item in fruits.values():
                cur.execute("""
                    INSERT INTO fruits (id, name, price, stock, sales, best_seller, asset_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    item["id"],
                    item["name"],
                    item["price"],
                    item["stock"],
                    item["sales"],
                    1 if item.get("best_seller", False) else 0,
                    item["asset_name"],
                ))
            conn.commit()
        finally:
            conn.close()

    def replace_addons(self, addons: dict[str, dict[str, Any]]) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM addons")
            for item in addons.values():
                cur.execute("""
                    INSERT INTO addons (id, name, price, stock, sales)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    item["id"],
                    item["name"],
                    item["price"],
                    item["stock"],
                    item["sales"],
                ))
            conn.commit()
        finally:
            conn.close()

    def replace_ingredients(self, ingredients: dict[str, dict[str, Any]]) -> None:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM ingredients")
            for item in ingredients.values():
                cur.execute("""
                    INSERT INTO ingredients (id, name, stock)
                    VALUES (?, ?, ?)
                """, (
                    item["id"],
                    item["name"],
                    item["stock"],
                ))
            conn.commit()
        finally:
            conn.close()

    def load_fruits(self) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM fruits ORDER BY id ASC")
            return cur.fetchall()
        finally:
            conn.close()

    def load_addons(self) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM addons ORDER BY id ASC")
            return cur.fetchall()
        finally:
            conn.close()

    def load_ingredients(self) -> list[sqlite3.Row]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT * FROM ingredients ORDER BY id ASC")
            return cur.fetchall()
        finally:
            conn.close()

    def insert_sale(self, sale_row: dict):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO local_sales (
                    sale_id,
                    total_price,
                    payment_method,
                    selected_fruits,
                    selected_addons,
                    sync_status
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                sale_row["sale_id"],
                sale_row["total_price"],
                sale_row["payment_method"],
                ",".join(sale_row["selected_fruits"]),
                ",".join(sale_row["selected_addons"]),
                "pending"
            ))
            conn.commit()
        finally:
            conn.close()

    def get_pending_sales(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM local_sales
                WHERE sync_status = 'pending'
                ORDER BY created_at ASC
            """)
            return cur.fetchall()
        finally:
            conn.close()

    def get_pending_sales(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT * FROM local_sales
                WHERE sync_status = 'pending'
                ORDER BY created_at ASC
            """)
            return cur.fetchall()
        finally:
            conn.close()

    def mark_sale_synced(self, sale_id: str):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE local_sales
                SET sync_status = 'synced',
                    synced_at = CURRENT_TIMESTAMP,
                    last_error = NULL
                WHERE sale_id = ?
            """, (sale_id,))
            conn.commit()
        finally:
            conn.close()

    def mark_sale_error(self, sale_id: str, err: str):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                UPDATE local_sales
                SET last_error = ?
                WHERE sale_id = ?
            """, (err[:500], sale_id))
            conn.commit()
        finally:
            conn.close()

    def delete_old_synced(self, keep_latest: int = 5):
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                DELETE FROM local_sales
                WHERE local_id NOT IN (
                    SELECT local_id FROM local_sales
                    WHERE sync_status = 'synced'
                    ORDER BY synced_at DESC
                    LIMIT ?
                )
                AND sync_status = 'synced'
            """, (keep_latest,))
            conn.commit()
        finally:
            conn.close()

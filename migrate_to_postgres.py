#!/usr/bin/env python3
"""One-time migration from SQLite database.db to PostgreSQL."""
import os
import sqlite3
import sys

import psycopg2
import psycopg2.extras

SQLITE_PATH = os.getenv("SQLITE_PATH", "database.db")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def sqlite_table_exists(conn, table):
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
    return c.fetchone() is not None


def sqlite_rows(table):
    conn = sqlite3.connect(SQLITE_PATH)
    conn.row_factory = sqlite3.Row
    if not sqlite_table_exists(conn, table):
        conn.close()
        return []
    c = conn.cursor()
    c.execute(f"SELECT * FROM {table}")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def insert_rows(cur, table, rows, columns=None):
    if not rows:
        return 0
    columns = columns or list(rows[0].keys())
    placeholders = ", ".join(["%s"] * len(columns))
    col_sql = ", ".join(columns)
    count = 0
    for row in rows:
        values = [row.get(col) for col in columns]
        cur.execute(f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})", values)
        count += 1
    return count


def main():
    if not DATABASE_URL:
        print("DATABASE_URL is required", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(SQLITE_PATH):
        print(f"SQLite file not found: {SQLITE_PATH}", file=sys.stderr)
        sys.exit(1)

    import db

    db.init_db()

    pg = psycopg2.connect(DATABASE_URL)
    cur = pg.cursor()

    cur.execute(
        """
        TRUNCATE TABLE
            shop_products, shop_categories, shop_users, community_users,
            transactions, projects, banks, admins, project_settings, settings
        RESTART IDENTITY CASCADE
        """
    )

    insert_rows(cur, "settings", sqlite_rows("settings"))
    insert_rows(cur, "project_settings", sqlite_rows("project_settings"))
    insert_rows(cur, "admins", sqlite_rows("admins"))
    insert_rows(
        cur,
        "banks",
        sqlite_rows("banks"),
        ["id", "region_code", "name", "value", "is_active", "link_url", "sort_order"],
    )
    insert_rows(
        cur,
        "projects",
        sqlite_rows("projects"),
        ["id", "name", "code", "description", "media_url", "min_amount", "payment_link", "is_active", "sort_order", "category"],
    )
    insert_rows(
        cur,
        "transactions",
        sqlite_rows("transactions"),
        ["id", "tx_code", "category", "amount", "currency", "name", "comment", "file_path", "status", "created_at", "expires_at"],
    )
    insert_rows(
        cur,
        "community_users",
        sqlite_rows("community_users"),
        [
            "tg_user_id", "tg_username", "tg_first_name", "role", "title_badge", "tx_code",
            "is_anonymous", "messages_count", "activity_points", "last_active_at", "created_at", "updated_at",
        ],
    )
    insert_rows(cur, "shop_users", sqlite_rows("shop_users"))
    insert_rows(cur, "shop_categories", sqlite_rows("shop_categories"))
    insert_rows(
        cur,
        "shop_products",
        sqlite_rows("shop_products"),
        ["id", "category_id", "name_ru", "name_en", "name_lt", "desc_ru", "desc_en", "desc_lt", "price", "photo_id", "pdf_id"],
    )

    for table, col in [
        ("projects", "id"),
        ("banks", "id"),
        ("transactions", "id"),
        ("shop_categories", "id"),
        ("shop_products", "id"),
    ]:
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{col}'), COALESCE((SELECT MAX({col}) FROM {table}), 1))"
        )

    pg.commit()
    pg.close()
    print("Migration complete")


if __name__ == "__main__":
    main()

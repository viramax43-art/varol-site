import os
import re
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg2
import psycopg2.extras

PROJECT_CODE_RE = re.compile(r"[A-Z0-9]{2,12}")
RESERVED_PROJECT_CODES = {"OWN"}


def _database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return url


@contextmanager
def get_connection():
    conn = psycopg2.connect(_database_url())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(row):
    return dict(row) if row is not None else None


def normalize_project_code(code: str) -> str:
    normalized = (code or "").strip().upper()
    if not PROJECT_CODE_RE.fullmatch(normalized):
        raise ValueError("Код проекта должен содержать от 2 до 12 символов A-Z и 0-9.")
    if normalized in RESERVED_PROJECT_CODES:
        raise ValueError("Код OWN зарезервирован для пользовательских проектов.")
    return normalized


def _base36(value: int) -> str:
    alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    result = ""
    while value:
        value, remainder = divmod(value, 36)
        result = alphabet[remainder] + result
    return result or "0"


def _legacy_project_code(project_id: int, used_codes: set[str]) -> str:
    base = f"P{_base36(project_id)}"
    candidate = base
    suffix = 0
    while candidate in used_codes or candidate in RESERVED_PROJECT_CODES:
        suffix += 1
        candidate = f"{base}{_base36(suffix)}"[:12]
    return candidate


def init_db():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                id SERIAL PRIMARY KEY,
                tx_code TEXT UNIQUE,
                category TEXT,
                amount DOUBLE PRECISION,
                currency TEXT,
                name TEXT,
                comment TEXT,
                file_path TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                region_code TEXT PRIMARY KEY,
                req_title TEXT,
                req_value TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                code TEXT,
                description TEXT,
                media_url TEXT,
                min_amount DOUBLE PRECISION,
                payment_link TEXT,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                category TEXT DEFAULT 'investment',
                CHECK (code IS NULL OR (code ~ '^[A-Z0-9]{2,12}$' AND code <> 'OWN'))
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS banks (
                id SERIAL PRIMARY KEY,
                region_code TEXT,
                name TEXT,
                value TEXT,
                is_active INTEGER DEFAULT 1,
                link_url TEXT DEFAULT '',
                sort_order INTEGER DEFAULT 0
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admins (
                chat_id TEXT PRIMARY KEY,
                added_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS project_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS community_users (
                tg_user_id BIGINT PRIMARY KEY,
                tg_username TEXT,
                tg_first_name TEXT,
                role TEXT DEFAULT 'member',
                title_badge TEXT DEFAULT 'Участник',
                tx_code TEXT DEFAULT '',
                is_anonymous INTEGER DEFAULT 0,
                messages_count INTEGER DEFAULT 0,
                activity_points INTEGER DEFAULT 0,
                last_active_at TIMESTAMPTZ DEFAULT NOW(),
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_users (
                tg_id TEXT PRIMARY KEY,
                role TEXT DEFAULT 'client',
                lang TEXT DEFAULT 'ru'
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_categories (
                id SERIAL PRIMARY KEY,
                name_ru TEXT,
                name_en TEXT,
                name_lt TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS shop_products (
                id SERIAL PRIMARY KEY,
                category_id INTEGER REFERENCES shop_categories(id),
                name_ru TEXT,
                name_en TEXT,
                name_lt TEXT,
                desc_ru TEXT,
                desc_en TEXT,
                desc_lt TEXT,
                price DOUBLE PRECISION,
                photo_id TEXT,
                pdf_id TEXT
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_credentials (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                password_hash TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
            """
        )
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_sessions (
                id SERIAL PRIMARY KEY,
                token_hash TEXT UNIQUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL,
                ip_address TEXT,
                user_agent TEXT
            )
            """
        )
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_code_unique ON projects(code) WHERE code IS NOT NULL"
        )

        c.execute("SELECT COUNT(*) AS cnt FROM banks")
        if c.fetchone()["cnt"] == 0:
            c.execute("SELECT * FROM settings")
            old_settings = c.fetchall()
            if old_settings:
                for s in old_settings:
                    c.execute(
                        "INSERT INTO banks (region_code, name, value) VALUES (%s, %s, %s)",
                        (s["region_code"], s["req_title"], s["req_value"]),
                    )
            else:
                default_banks = [
                    ("PL", "BLIK / Bank Millennium", "PL89 1020 5558 1111 2222 3333 4444"),
                    ("LT", "Revolut Bank (Rimas Cicenas)", "LT85 3250 0478 6473 6227"),
                    ("KZ", "Kaspi Bank", "Данные уточняются..."),
                    ("AZ", "M10 / Золотая Корона", "Данные уточняются..."),
                ]
                c.executemany(
                    "INSERT INTO banks (region_code, name, value) VALUES (%s, %s, %s)",
                    default_banks,
                )

        c.execute("SELECT id, code FROM projects ORDER BY id")
        project_rows = c.fetchall()
        used_codes = set()
        for row in project_rows:
            raw_code = (row["code"] or "").strip().upper()
            is_valid = bool(PROJECT_CODE_RE.fullmatch(raw_code)) and raw_code not in RESERVED_PROJECT_CODES
            if not is_valid or raw_code in used_codes:
                raw_code = _legacy_project_code(row["id"], used_codes)
                c.execute("UPDATE projects SET code = %s WHERE id = %s", (raw_code, row["id"]))
            elif raw_code != row["code"]:
                c.execute("UPDATE projects SET code = %s WHERE id = %s", (raw_code, row["id"]))
            used_codes.add(raw_code)

        admin_env = os.getenv("TELEGRAM_ADMIN_ID", "DUMMY_ID")
        for aid in admin_env.split(","):
            aid = aid.strip()
            if aid and aid != "DUMMY_ID":
                c.execute(
                    "INSERT INTO admins (chat_id) VALUES (%s) ON CONFLICT (chat_id) DO NOTHING",
                    (aid,),
                )


def get_admin_password_hash():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT password_hash FROM admin_credentials WHERE id = 1")
        row = c.fetchone()
        return row["password_hash"] if row else None


def set_admin_password_hash(password_hash: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO admin_credentials (id, password_hash, updated_at)
            VALUES (1, %s, NOW())
            ON CONFLICT (id) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = NOW()
            """,
            (password_hash,),
        )


def create_admin_session(token_hash: str, expires_at: datetime, ip_address: str, user_agent: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO admin_sessions (token_hash, expires_at, ip_address, user_agent)
            VALUES (%s, %s, %s, %s)
            """,
            (token_hash, expires_at, ip_address, user_agent),
        )


def get_admin_session(token_hash: str):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "SELECT * FROM admin_sessions WHERE token_hash = %s AND expires_at > NOW()",
            (token_hash,),
        )
        return c.fetchone()


def delete_admin_session(token_hash: str):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admin_sessions WHERE token_hash = %s", (token_hash,))


def delete_all_admin_sessions():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admin_sessions")


def create_transaction(tx_code, category, amount, currency, name, comment, file_path, expires_at=None):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO transactions (tx_code, category, amount, currency, name, comment, file_path, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (tx_code, category, amount, currency, name, comment, file_path, expires_at),
        )
        return c.fetchone()[0]


def get_transaction(tx_id):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM transactions WHERE id = %s", (tx_id,))
        return c.fetchone()


def get_transaction_by_code(tx_code):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM transactions WHERE tx_code = %s", (tx_code,))
        return c.fetchone()


def get_transaction_by_id(tx_id):
    return get_transaction(tx_id)


def update_transaction_status(tx_id, status):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE transactions SET status = %s WHERE id = %s", (status, tx_id))


def get_statistics():
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            SELECT COUNT(*), COALESCE(SUM(amount), 0)
            FROM transactions
            WHERE created_at::date = CURRENT_DATE AND status = 'approved'
            """
        )
        today_approved_count, today_approved_sum = c.fetchone()
        c.execute("SELECT COUNT(*) FROM transactions WHERE status = 'pending'")
        pending_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM transactions WHERE created_at::date = CURRENT_DATE")
        today_total_count = c.fetchone()[0]
    return {
        "today_approved_count": today_approved_count or 0,
        "today_approved_sum": today_approved_sum or 0,
        "pending_count": pending_count or 0,
        "today_total_count": today_total_count or 0,
    }


def get_extended_statistics(period="today"):
    if period == "today":
        date_cond = "created_at::date = CURRENT_DATE"
    elif period == "week":
        date_cond = "created_at >= NOW() - INTERVAL '7 days'"
    elif period == "month":
        date_cond = "created_at >= NOW() - INTERVAL '30 days'"
    else:
        date_cond = "TRUE"

    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM transactions WHERE {date_cond} AND status = 'approved'"
        )
        appr_cnt, appr_sum = c.fetchone()
        c.execute(f"SELECT COUNT(*) FROM transactions WHERE {date_cond} AND status = 'rejected'")
        rej_cnt = c.fetchone()[0]
        c.execute(f"SELECT COUNT(*) FROM transactions WHERE {date_cond}")
        total_cnt = c.fetchone()[0]
    return {
        "approved_count": appr_cnt or 0,
        "approved_sum": appr_sum or 0,
        "rejected_count": rej_cnt or 0,
        "total_count": total_cnt or 0,
        "period": period,
    }


def get_all_banks():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM banks ORDER BY sort_order ASC, id ASC")
        return [dict(b) for b in c.fetchall()]


def update_bank_order(bank_ids: list):
    with get_connection() as conn:
        c = conn.cursor()
        for index, bank_id in enumerate(bank_ids):
            c.execute("UPDATE banks SET sort_order = %s WHERE id = %s", (index, bank_id))


def get_banks_by_region(region_code):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM banks WHERE region_code = %s", (region_code,))
        return [dict(b) for b in c.fetchall()]


def add_bank(region_code, name, value, link_url=""):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(sort_order) FROM banks")
        row = c.fetchone()
        next_sort_order = (row[0] + 1) if row and row[0] is not None else 0
        c.execute(
            "INSERT INTO banks (region_code, name, value, link_url, sort_order) VALUES (%s, %s, %s, %s, %s)",
            (region_code, name, value, link_url, next_sort_order),
        )


def toggle_bank_active(bank_id, is_active):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE banks SET is_active = %s WHERE id = %s", (1 if is_active else 0, bank_id))


def update_bank_value(bank_id, new_value):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE banks SET value = %s WHERE id = %s", (new_value, bank_id))


def update_bank_link(bank_id, link_url):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE banks SET link_url = %s WHERE id = %s", (link_url, bank_id))


def update_bank_full(bank_id, name, value, link_url):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "UPDATE banks SET name = %s, value = %s, link_url = %s WHERE id = %s",
            (name, value, link_url, bank_id),
        )


def delete_bank(bank_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM banks WHERE id = %s", (bank_id,))


def get_pending_transactions(offset=0, limit=20):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "SELECT * FROM transactions WHERE status = 'pending' ORDER BY id ASC LIMIT %s OFFSET %s",
            (limit, offset),
        )
        rows = c.fetchall()
        c.execute("SELECT COUNT(*) AS cnt FROM transactions WHERE status = 'pending'")
        total = c.fetchone()["cnt"]
    return [dict(r) for r in rows], total


def get_project_stats():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT category, COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total_amount
            FROM transactions
            GROUP BY category
            ORDER BY count DESC
            """
        )
        return [dict(r) for r in c.fetchall()]


def get_all_transactions():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM transactions ORDER BY id DESC")
        return [dict(r) for r in c.fetchall()]


def get_all_projects():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, name, code, description, media_url, min_amount, payment_link, is_active, sort_order, category
            FROM projects ORDER BY sort_order ASC, id ASC
            """
        )
        return [dict(row) for row in c.fetchall()]


def get_active_projects():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, name, code, description, media_url, min_amount, payment_link, is_active, sort_order, category
            FROM projects WHERE is_active = 1 ORDER BY sort_order ASC, id ASC
            """
        )
        return [dict(row) for row in c.fetchall()]


def toggle_project_active(project_id: int, is_active: int):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("UPDATE projects SET is_active = %s WHERE id = %s", (1 if is_active else 0, project_id))


def update_project_order(project_ids: list):
    with get_connection() as conn:
        c = conn.cursor()
        for index, proj_id in enumerate(project_ids):
            c.execute("UPDATE projects SET sort_order = %s WHERE id = %s", (index, proj_id))


def add_project(
    name: str,
    code: str,
    min_amount=None,
    description: str = "",
    media_url: str = "",
    payment_link: str = "",
    is_active: int = 1,
    category: str = "investment",
):
    code = normalize_project_code(code)
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT MAX(sort_order) FROM projects")
        row = c.fetchone()
        next_sort_order = (row[0] + 1) if row and row[0] is not None else 0
        c.execute(
            """
            INSERT INTO projects (name, code, min_amount, description, media_url, payment_link, is_active, sort_order, category)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (name, code, min_amount, description, media_url, payment_link, 1 if is_active else 0, next_sort_order, category),
        )
        return c.fetchone()[0]


def update_project(
    project_id: int,
    name: str,
    code: str,
    min_amount=None,
    description: str = "",
    media_url: str = "",
    payment_link: str = "",
    is_active: int = 1,
    category: str = "investment",
):
    code = normalize_project_code(code)
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            UPDATE projects
            SET name = %s, code = %s, min_amount = %s, description = %s, media_url = %s,
                payment_link = %s, is_active = %s, category = %s
            WHERE id = %s
            """,
            (name, code, min_amount, description, media_url, payment_link, 1 if is_active else 0, category, project_id),
        )
        return c.rowcount > 0


def get_project(project_id: int):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, name, code, description, media_url, min_amount, payment_link, is_active, sort_order, category
            FROM projects WHERE id = %s
            """,
            (project_id,),
        )
        row = c.fetchone()
        return dict(row) if row else None


def get_project_by_code(code: str):
    code = normalize_project_code(code)
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            """
            SELECT id, name, code, description, media_url, min_amount, payment_link, is_active, sort_order, category
            FROM projects WHERE code = %s
            """,
            (code,),
        )
        row = c.fetchone()
        return dict(row) if row else None


def delete_project(project_id: int):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM projects WHERE id = %s", (project_id,))


_SETTINGS_CACHE = {}


def get_setting(key, default=None):
    if key in _SETTINGS_CACHE:
        return _SETTINGS_CACHE[key]
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT value FROM project_settings WHERE key = %s", (key,))
        row = c.fetchone()
    val = row["value"] if row else default
    if val is not None:
        _SETTINGS_CACHE[key] = val
    return val


def set_setting(key, value):
    val_str = str(value)
    _SETTINGS_CACHE[key] = val_str
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO project_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (key, val_str),
        )


def is_admin(chat_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM admins WHERE chat_id = %s", (str(chat_id),))
        return c.fetchone() is not None


def add_admin(chat_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO admins (chat_id) VALUES (%s) ON CONFLICT (chat_id) DO NOTHING",
            (str(chat_id),),
        )


def remove_admin(chat_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM admins WHERE chat_id = %s", (str(chat_id),))


def get_all_admins():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM admins ORDER BY added_at DESC")
        return [dict(r) for r in c.fetchall()]


def get_shop_user(tg_id):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM shop_users WHERE tg_id = %s", (str(tg_id),))
        row = c.fetchone()
        return dict(row) if row else None


def create_or_update_shop_user(tg_id, role=None, lang=None):
    user = get_shop_user(tg_id)
    with get_connection() as conn:
        c = conn.cursor()
        if not user:
            c.execute(
                "INSERT INTO shop_users (tg_id, role, lang) VALUES (%s, %s, %s)",
                (str(tg_id), role or "client", lang or "ru"),
            )
        else:
            c.execute(
                "UPDATE shop_users SET role = %s, lang = %s WHERE tg_id = %s",
                (role or user["role"], lang or user["lang"], str(tg_id)),
            )


def get_shop_categories():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM shop_categories ORDER BY id")
        return [dict(r) for r in c.fetchall()]


def get_shop_category(cat_id):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM shop_categories WHERE id = %s", (cat_id,))
        row = c.fetchone()
        return dict(row) if row else None


def add_shop_category(name_ru, name_en, name_lt):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            "INSERT INTO shop_categories (name_ru, name_en, name_lt) VALUES (%s, %s, %s)",
            (name_ru, name_en, name_lt),
        )


def get_shop_products(category_id=None):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if category_id:
            c.execute("SELECT * FROM shop_products WHERE category_id = %s ORDER BY id", (category_id,))
        else:
            c.execute("SELECT * FROM shop_products ORDER BY id")
        return [dict(r) for r in c.fetchall()]


def get_shop_product(prod_id):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM shop_products WHERE id = %s", (prod_id,))
        row = c.fetchone()
        return dict(row) if row else None


def add_shop_product(category_id, name_ru, name_en, name_lt, desc_ru, desc_en, desc_lt, price, photo_id, pdf_id):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO shop_products
            (category_id, name_ru, name_en, name_lt, desc_ru, desc_en, desc_lt, price, photo_id, pdf_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (category_id, name_ru, name_en, name_lt, desc_ru, desc_en, desc_lt, price, photo_id, pdf_id),
        )


def register_community_member(tg_user_id: int, tg_username: str, tg_first_name: str, role: str, title_badge: str, tx_code: str = ""):
    clean_badge = title_badge.replace("👑 ", "").replace("💡 ", "").replace("⭐️ ", "").strip()
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO community_users
            (tg_user_id, tg_username, tg_first_name, role, title_badge, tx_code, is_anonymous, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
            ON CONFLICT (tg_user_id) DO UPDATE SET
                tg_username = EXCLUDED.tg_username,
                tg_first_name = EXCLUDED.tg_first_name,
                role = CASE WHEN EXCLUDED.role = 'investor' THEN 'investor' ELSE community_users.role END,
                title_badge = CASE WHEN EXCLUDED.role = 'investor' THEN 'Инвестор' ELSE %s END,
                tx_code = CASE WHEN EXCLUDED.tx_code <> '' THEN EXCLUDED.tx_code ELSE community_users.tx_code END,
                updated_at = NOW()
            """,
            (tg_user_id, tg_username or "", tg_first_name or "", role, clean_badge, tx_code or "", clean_badge),
        )


def get_community_member(tg_user_id: int):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM community_users WHERE tg_user_id = %s", (tg_user_id,))
        row = c.fetchone()
        return dict(row) if row else None


def check_community_access(tg_user_id: int) -> bool:
    if is_admin(tg_user_id):
        return True
    member = get_community_member(tg_user_id)
    return bool(member and member.get("role") in ["investor", "member", "donor"])


def verify_and_activate_code(tg_user_id: int, tg_username: str, tg_first_name: str, tx_code: str):
    tx_code = (tx_code or "").strip()
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM transactions WHERE tx_code = %s OR id::text = %s", (tx_code, tx_code))
        tx = c.fetchone()

        if tx:
            category = str(tx["category"] or "").lower()
            is_inv = any(k in category for k in ["инвест", "инвестор", "проект", "invest", "sphere", "dict", "radio", "008", "own"])
            role = "investor" if is_inv else "member"
            badge = "Инвестор" if role == "investor" else "Участник"
        else:
            role = "investor" if any(tx_code.upper().startswith(p) for p in ["VB-", "INV-", "TX-SPHERE", "TX-DICT", "TX-RADIO", "TX-008", "TX-OWN"]) else "member"
            badge = "Инвестор" if role == "investor" else "Участник"

        c.execute(
            """
            INSERT INTO community_users
            (tg_user_id, tg_username, tg_first_name, role, title_badge, tx_code, is_anonymous, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, 0, NOW(), NOW())
            ON CONFLICT (tg_user_id) DO UPDATE SET
                tg_username = EXCLUDED.tg_username,
                tg_first_name = EXCLUDED.tg_first_name,
                role = EXCLUDED.role,
                title_badge = EXCLUDED.title_badge,
                tx_code = EXCLUDED.tx_code,
                updated_at = NOW()
            """,
            (tg_user_id, tg_username or "", tg_first_name or "", role, badge, tx_code),
        )
        c.execute("SELECT * FROM community_users WHERE tg_user_id = %s", (tg_user_id,))
        member = dict(c.fetchone())
    return True, badge, member


def toggle_community_anonymity(tg_user_id: int):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT is_anonymous FROM community_users WHERE tg_user_id = %s", (tg_user_id,))
        row = c.fetchone()
        if row:
            new_val = 0 if row["is_anonymous"] == 1 else 1
            c.execute(
                "UPDATE community_users SET is_anonymous = %s, updated_at = NOW() WHERE tg_user_id = %s",
                (new_val, tg_user_id),
            )
            return new_val
    return 0


def get_all_community_members():
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute("SELECT * FROM community_users ORDER BY created_at DESC")
        return [dict(r) for r in c.fetchall()]


def record_user_activity(tg_user_id: int, tg_username: str = "", tg_first_name: str = "", points: int = 1):
    with get_connection() as conn:
        c = conn.cursor()
        c.execute(
            """
            INSERT INTO community_users
            (tg_user_id, tg_username, tg_first_name, role, title_badge, messages_count, activity_points, last_active_at, created_at, updated_at)
            VALUES (%s, %s, %s, 'member', 'Участник', 1, %s, NOW(), NOW(), NOW())
            ON CONFLICT (tg_user_id) DO UPDATE SET
                tg_username = CASE WHEN EXCLUDED.tg_username <> '' THEN EXCLUDED.tg_username ELSE community_users.tg_username END,
                tg_first_name = CASE WHEN EXCLUDED.tg_first_name <> '' THEN EXCLUDED.tg_first_name ELSE community_users.tg_first_name END,
                messages_count = community_users.messages_count + 1,
                activity_points = community_users.activity_points + EXCLUDED.activity_points,
                last_active_at = NOW(),
                updated_at = NOW()
            """,
            (tg_user_id, tg_username or "", tg_first_name or "", points),
        )


def get_top_active_members(limit: int = 10):
    with get_connection() as conn:
        c = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        c.execute(
            "SELECT * FROM community_users ORDER BY activity_points DESC, messages_count DESC LIMIT %s",
            (limit,),
        )
        return [dict(r) for r in c.fetchall()]


if os.getenv("DATABASE_URL"):
    init_db()

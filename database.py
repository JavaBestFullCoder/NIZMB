import aiosqlite
from config import DB_PATH

_db: aiosqlite.Connection | None = None

EXPENSE_TYPES = ("expense", "transfer_out", "director_expense", "supplier_payment")


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def init_db():
    db = await get_db()

    # Check if this is an old DB (access_codes table doesn't exist yet)
    cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='access_codes'")
    old_db = not await cursor.fetchone()

    cursor = await db.execute("PRAGMA table_info(users)")
    users_exist = bool(await cursor.fetchone())

    if old_db and users_exist:
        # Migrate old users table: drop UNIQUE on access_code
        await db.executescript("""
            CREATE TABLE users_migrated (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                telegram_username TEXT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                access_code TEXT,
                object_id INTEGER REFERENCES objects(id),
                created_at TEXT DEFAULT (datetime('now'))
            );
            INSERT OR IGNORE INTO users_migrated SELECT * FROM users;
            DROP TABLE users;
            ALTER TABLE users_migrated RENAME TO users;
        """)
    elif not users_exist:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE,
                telegram_username TEXT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                access_code TEXT,
                object_id INTEGER REFERENCES objects(id),
                created_at TEXT DEFAULT (datetime('now'))
            )
        """)

    # Create all tables (fresh or migrated)
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS access_codes (
            code TEXT PRIMARY KEY,
            role TEXT NOT NULL,
            object_id INTEGER REFERENCES objects(id),
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object_id INTEGER REFERENCES objects(id),
            user_id INTEGER REFERENCES users(id),
            type TEXT NOT NULL,
            amount REAL NOT NULL,
            reason TEXT,
            transaction_date TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS transfer_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transfer_out_id INTEGER NOT NULL REFERENCES transactions(id),
            transfer_in_id INTEGER NOT NULL REFERENCES transactions(id),
            source_object_id INTEGER REFERENCES objects(id),
            created_at TEXT DEFAULT (datetime('now'))
        );
    """)
    await db.commit()


# --- Access codes ---

async def create_access_code(code: str, role: str, object_id: int | None):
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO access_codes (code, role, object_id) VALUES (?, ?, ?)",
        (code, role, object_id),
    )
    await db.commit()


async def resolve_code(code: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM access_codes WHERE code = ?", (code,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def code_exists(code: str) -> bool:
    db = await get_db()
    cursor = await db.execute("SELECT COUNT(*) FROM access_codes WHERE code = ?", (code,))
    row = await cursor.fetchone()
    return row[0] > 0


async def delete_access_codes_for_object(object_id: int):
    db = await get_db()
    await db.execute("DELETE FROM access_codes WHERE object_id = ?", (object_id,))
    await db.commit()


async def get_all_codes_with_users() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("""
        SELECT ac.code, ac.role, ac.object_id, o.name as object_name,
               GROUP_CONCAT(u.name, ', ') as user_names
        FROM access_codes ac
        LEFT JOIN objects o ON ac.object_id = o.id
        LEFT JOIN users u ON u.access_code = ac.code
        GROUP BY ac.code
        ORDER BY ac.role, ac.code
    """)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# --- Users ---

async def login_user(telegram_id: int, telegram_username: str | None, code: str, first_name: str = "") -> dict | None:
    """Authenticate user by code. Creates/updates user record. Returns user dict or None."""
    ac = await resolve_code(code)
    if not ac:
        return None

    db = await get_db()
    existing = await get_user_by_telegram(telegram_id)

    if existing:
        await db.execute(
            "UPDATE users SET role = ?, object_id = ?, access_code = ? WHERE telegram_id = ?",
            (ac["role"], ac["object_id"], code, telegram_id),
        )
    else:
        await db.execute(
            "INSERT INTO users (telegram_id, telegram_username, name, role, access_code, object_id) VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, telegram_username, first_name, ac["role"], code, ac["object_id"]),
        )
    await db.commit()
    return await get_user_by_telegram(telegram_id)


async def update_user_name(telegram_id: int, name: str):
    db = await get_db()
    await db.execute("UPDATE users SET name = ? WHERE telegram_id = ?", (name, telegram_id))
    await db.commit()


async def get_user_by_telegram(telegram_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def get_users_by_code(code: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM users WHERE access_code = ?", (code,))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


# --- Objects ---

async def get_objects() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("""
        SELECT o.*, COUNT(u.id) as user_count
        FROM objects o
        LEFT JOIN users u ON u.object_id = o.id
        GROUP BY o.id
        ORDER BY o.name
    """)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_object(obj_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM objects WHERE id = ?", (obj_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_object(name: str) -> int:
    db = await get_db()
    cursor = await db.execute("INSERT INTO objects (name) VALUES (?)", (name,))
    await db.commit()
    return cursor.lastrowid


async def delete_object(obj_id: int):
    db = await get_db()
    await db.execute("DELETE FROM access_codes WHERE object_id = ?", (obj_id,))
    await db.execute("DELETE FROM transactions WHERE object_id = ?", (obj_id,))
    await db.execute("DELETE FROM transfer_links WHERE source_object_id = ?", (obj_id,))
    await db.execute("DELETE FROM users WHERE object_id = ?", (obj_id,))
    await db.execute("DELETE FROM objects WHERE id = ?", (obj_id,))
    await db.commit()


# --- Transactions ---

async def get_transaction_by_id(txn_id: int) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT t.*, u.name as user_name FROM transactions t LEFT JOIN users u ON t.user_id = u.id WHERE t.id = ?", (txn_id,))
    row = await cursor.fetchone()
    return dict(row) if row else None


async def delete_transaction(txn_id: int):
    db = await get_db()
    await db.execute("DELETE FROM transactions WHERE id = ?", (txn_id,))
    await db.commit()


async def get_hq_users() -> list[dict]:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM users WHERE role = 'head_office' ORDER BY name")
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def delete_user(user_id: int):
    db = await get_db()
    await db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    await db.commit()


async def get_transfer_link_by_transaction(txn_id: int) -> dict | None:
    """Find transfer_link where txn_id is either transfer_out_id or transfer_in_id."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM transfer_links WHERE transfer_out_id = ? OR transfer_in_id = ?",
        (txn_id, txn_id),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def create_transaction(object_id: int | None, user_id: int, type_: str, amount: float, date_str: str, reason: str | None = None) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO transactions (object_id, user_id, type, amount, reason, transaction_date) VALUES (?, ?, ?, ?, ?, ?)",
        (object_id, user_id, type_, amount, reason, date_str),
    )
    await db.commit()
    return cursor.lastrowid


async def link_transfers(transfer_out_id: int, transfer_in_id: int, source_object_id: int):
    db = await get_db()
    await db.execute(
        "INSERT INTO transfer_links (transfer_out_id, transfer_in_id, source_object_id) VALUES (?, ?, ?)",
        (transfer_out_id, transfer_in_id, source_object_id),
    )
    await db.commit()


async def get_object_transactions(object_id: int, start_date: str, end_date: str, type_: str | None = None) -> list[dict]:
    db = await get_db()
    query = """
        SELECT t.*, u.name as user_name
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        WHERE t.object_id = ? AND date(t.transaction_date) >= ? AND date(t.transaction_date) <= ?
    """
    params = [object_id, start_date, end_date]
    if type_:
        query += " AND t.type = ?"
        params.append(type_)
    query += " ORDER BY t.transaction_date, t.id"
    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_hq_transactions(start_date: str, end_date: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("""
        SELECT t.*, u.name as user_name,
               tl.source_object_id, o.name as source_object_name
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN transfer_links tl ON t.id = tl.transfer_in_id
        LEFT JOIN objects o ON tl.source_object_id = o.id
        WHERE t.object_id IS NULL AND date(t.transaction_date) >= ? AND date(t.transaction_date) <= ?
        ORDER BY t.transaction_date, t.id
    """, (start_date, end_date))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_hq_balance_before(date_str: str) -> float:
    db = await get_db()
    cursor = await db.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN type = 'transfer_in' THEN amount ELSE 0 END), 0) -
               COALESCE(SUM(CASE WHEN type IN {EXPENSE_TYPES} THEN amount ELSE 0 END), 0)
        FROM transactions WHERE object_id IS NULL AND date(transaction_date) < ?
    """, (date_str,))
    row = await cursor.fetchone()
    return row[0] or 0.0


async def get_all_objects_transactions(start_date: str, end_date: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("""
        SELECT t.*, u.name as user_name, o.name as object_name
        FROM transactions t
        LEFT JOIN users u ON t.user_id = u.id
        LEFT JOIN objects o ON t.object_id = o.id
        WHERE t.object_id IS NOT NULL AND date(t.transaction_date) >= ? AND date(t.transaction_date) <= ?
        ORDER BY t.transaction_date, t.object_id, t.id
    """, (start_date, end_date))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_employees(object_id: int) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM users WHERE object_id = ? AND role IN ('manager', 'employee') ORDER BY name",
        (object_id,),
    )
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def get_object_balance(object_id: int) -> float:
    db = await get_db()
    cursor = await db.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
               COALESCE(SUM(CASE WHEN type IN {EXPENSE_TYPES} THEN amount ELSE 0 END), 0)
        FROM transactions WHERE object_id = ?
    """, (object_id,))
    row = await cursor.fetchone()
    return row[0] or 0.0


async def get_hq_balance() -> float:
    db = await get_db()
    cursor = await db.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN type = 'transfer_in' THEN amount ELSE 0 END), 0) -
               COALESCE(SUM(CASE WHEN type IN {EXPENSE_TYPES} THEN amount ELSE 0 END), 0)
        FROM transactions WHERE object_id IS NULL
    """)
    row = await cursor.fetchone()
    return row[0] or 0.0


async def get_daily_summary(object_id: int, date_str: str) -> dict:
    opening = await get_object_balance_before(object_id, date_str)
    db = await get_db()
    cursor = await db.execute("""
        SELECT type, COALESCE(SUM(amount), 0) as total
        FROM transactions
        WHERE object_id = ? AND date(transaction_date) = ?
        GROUP BY type
    """, (object_id, date_str))
    rows = await cursor.fetchall()
    income = 0.0
    expense = 0.0
    transfer_out = 0.0
    for r in rows:
        if r["type"] == "income":
            income = r["total"]
        elif r["type"] in ("expense", "director_expense", "supplier_payment"):
            expense += r["total"]
        elif r["type"] == "transfer_out":
            transfer_out = r["total"]
    closing = opening + income - expense - transfer_out
    return {"opening": opening, "income": income, "expense": expense, "transfer_out": transfer_out, "closing": closing}


async def get_object_balance_before(object_id: int, date_str: str) -> float:
    db = await get_db()
    cursor = await db.execute(f"""
        SELECT COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
               COALESCE(SUM(CASE WHEN type IN {EXPENSE_TYPES} THEN amount ELSE 0 END), 0)
        FROM transactions WHERE object_id = ? AND date(transaction_date) < ?
    """, (object_id, date_str))
    row = await cursor.fetchone()
    return row[0] or 0.0


async def get_transfer_links(object_id: int, start_date: str, end_date: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute("""
        SELECT tl.*, to_t.amount, to_t.transaction_date, to_t.user_id as from_user_id,
               u_from.name as from_user_name, o.name as object_name
        FROM transfer_links tl
        JOIN transactions to_t ON tl.transfer_out_id = to_t.id
        LEFT JOIN users u_from ON to_t.user_id = u_from.id
        JOIN objects o ON tl.source_object_id = o.id
        WHERE tl.source_object_id = ? AND date(to_t.transaction_date) >= ? AND date(to_t.transaction_date) <= ?
        ORDER BY to_t.transaction_date
    """, (object_id, start_date, end_date))
    rows = await cursor.fetchall()
    return [dict(r) for r in rows]

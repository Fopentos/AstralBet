import json
import aiosqlite
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

DB_PATH = Path("data/bot.db")
DATA_JSON_PATH = Path("data.json")

async def get_db() -> aiosqlite.Connection:
    """Получить соединение с базой данных (aiosqlite)."""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db

# ================== ИНИЦИАЛИЗАЦИЯ И МИГРАЦИЯ ==================

async def init_db():
    """Создать все таблицы, если их нет, и выполнить миграцию из data.json."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await get_db()
    try:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            game_balance REAL DEFAULT 0.0,
            total_games INTEGER DEFAULT 0,
            total_wins INTEGER DEFAULT 0,
            total_deposited REAL DEFAULT 0.0,
            real_money_spent REAL DEFAULT 0.0,
            current_bet INTEGER DEFAULT 5,
            registration_date TEXT,
            last_activity TEXT,
            slots_mode TEXT DEFAULT 'normal',
            win_streak INTEGER DEFAULT 0,
            max_win_streak INTEGER DEFAULT 0,
            mega_wins_count INTEGER DEFAULT 0,
            total_mega_win_amount REAL DEFAULT 0.0,
            referral_code TEXT,
            referral_by INTEGER,
            referrals_count INTEGER DEFAULT 0,
            referral_earnings REAL DEFAULT 0.0,
            used_promo_codes TEXT DEFAULT '[]',
            muted_until TEXT,
            warnings TEXT DEFAULT '[]',
            vip_until TEXT
        );

        CREATE TABLE IF NOT EXISTS activity (
            user_id INTEGER PRIMARY KEY,
            weekly_streak_days INTEGER DEFAULT 0,
            weekly_total_bets REAL DEFAULT 0.0,
            weekly_total_games INTEGER DEFAULT 0,
            last_weekly_bonus_date TEXT,
            daily_games_count INTEGER DEFAULT 0,
            last_activity_date TEXT,
            current_week_start TEXT
        );

        CREATE TABLE IF NOT EXISTS referral_codes (
            code TEXT PRIMARY KEY,
            user_id INTEGER
        );

        CREATE TABLE IF NOT EXISTS promo_codes (
            code TEXT PRIMARY KEY,
            amount INTEGER,
            uses_left INTEGER,
            created_by INTEGER,
            created_at TEXT,
            used_by TEXT DEFAULT '[]'
        );

        CREATE TABLE IF NOT EXISTS bans (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            banned_by INTEGER,
            banned_at TEXT
        );

        CREATE TABLE IF NOT EXISTS mutes (
            user_id INTEGER PRIMARY KEY,
            muted_until TEXT,
            reason TEXT,
            muted_by INTEGER,
            muted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            reason TEXT,
            warned_by INTEGER,
            warned_at TEXT
        );

        CREATE TABLE IF NOT EXISTS vip (
            user_id INTEGER PRIMARY KEY,
            vip_until TEXT,
            given_by INTEGER,
            given_at TEXT
        );

        CREATE TABLE IF NOT EXISTS withdrawal_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            amount REAL,
            combination TEXT,
            gift_count INTEGER,
            status TEXT DEFAULT 'pending',
            created_at TEXT,
            source TEXT DEFAULT 'balance'
        );

        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER,
            action TEXT,
            target_id INTEGER,
            details TEXT,
            timestamp TEXT
        );
        """)
        await db.commit()

        if DATA_JSON_PATH.exists():
            await _migrate_from_json(db)
            DATA_JSON_PATH.rename(DATA_JSON_PATH.with_suffix('.backup'))
            print("✅ Миграция из data.json завершена")
        await db.close()
    except Exception as e:
        print(f"Ошибка инициализации БД: {e}")
        raise

async def _migrate_from_json(db: aiosqlite.Connection):
    with open(DATA_JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # users (добавлено поле username – берём None, в старой базе его нет)
    for uid_str, udata in data.get('user_data', {}).items():
        uid = int(uid_str)
        await db.execute("""
        INSERT OR REPLACE INTO users (
            user_id, username, game_balance, total_games, total_wins, total_deposited, real_money_spent,
            current_bet, registration_date, last_activity, slots_mode, win_streak, max_win_streak,
            mega_wins_count, total_mega_win_amount, referral_code, referral_by, referrals_count,
            referral_earnings, used_promo_codes, muted_until, warnings, vip_until
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uid,
            udata.get('username'),  # может быть None
            udata.get('game_balance', 0),
            udata.get('total_games', 0),
            udata.get('total_wins', 0),
            udata.get('total_deposited', 0),
            udata.get('real_money_spent', 0),
            udata.get('current_bet', 5),
            udata.get('registration_date', datetime.now().isoformat()),
            udata.get('last_activity', datetime.now().isoformat()),
            udata.get('slots_mode', 'normal'),
            udata.get('win_streak', 0),
            udata.get('max_win_streak', 0),
            udata.get('mega_wins_count', 0),
            udata.get('total_mega_win_amount', 0.0),
            udata.get('referral_code'),
            udata.get('referral_by'),
            udata.get('referrals_count', 0),
            udata.get('referral_earnings', 0.0),
            json.dumps(udata.get('used_promo_codes', [])),
            udata.get('muted_until'),
            json.dumps(udata.get('warnings', [])),
            udata.get('vip_until')
        ))

    # activity
    for uid_str, adata in data.get('user_activity', {}).items():
        uid = int(uid_str)
        await db.execute("""
        INSERT OR REPLACE INTO activity (
            user_id, weekly_streak_days, weekly_total_bets, weekly_total_games,
            last_weekly_bonus_date, daily_games_count, last_activity_date, current_week_start
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            uid,
            adata.get('weekly_streak_days', 0),
            adata.get('weekly_total_bets', 0),
            adata.get('weekly_total_games', 0),
            adata.get('last_weekly_bonus_date'),
            adata.get('daily_games_count', 0),
            adata.get('last_activity_date'),
            adata.get('current_week_start')
        ))

    # referral_codes
    for code, uid in data.get('referral_codes', {}).items():
        await db.execute("INSERT OR REPLACE INTO referral_codes (code, user_id) VALUES (?, ?)", (code, uid))

    # promo_codes
    for code, pdata in data.get('promo_codes', {}).items():
        await db.execute("""
        INSERT OR REPLACE INTO promo_codes (code, amount, uses_left, created_by, created_at, used_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (
            code,
            pdata.get('amount'),
            pdata.get('uses_left'),
            pdata.get('created_by'),
            pdata.get('created_at'),
            json.dumps(pdata.get('used_by', []))
        ))

    # bans
    for uid, bdata in data.get('banned_users', {}).items():
        await db.execute("""
        INSERT OR REPLACE INTO bans (user_id, reason, banned_by, banned_at)
        VALUES (?, ?, ?, ?)
        """, (int(uid), bdata.get('reason'), bdata.get('banned_by'), bdata.get('banned_at')))

    # mutes
    for uid, mdata in data.get('muted_users', {}).items():
        await db.execute("""
        INSERT OR REPLACE INTO mutes (user_id, muted_until, reason, muted_by, muted_at)
        VALUES (?, ?, ?, ?, ?)
        """, (
            int(uid),
            mdata.get('muted_until'),
            mdata.get('reason'),
            mdata.get('muted_by'),
            mdata.get('muted_at')
        ))

    # warnings
    for uid, wlist in data.get('user_warnings', {}).items():
        for w in wlist:
            await db.execute("""
            INSERT INTO warnings (user_id, reason, warned_by, warned_at)
            VALUES (?, ?, ?, ?)
            """, (int(uid), w.get('reason'), w.get('warned_by'), w.get('warned_at')))

    # vip
    for uid, vdata in data.get('vip_users', {}).items():
        await db.execute("""
        INSERT OR REPLACE INTO vip (user_id, vip_until, given_by, given_at)
        VALUES (?, ?, ?, ?)
        """, (int(uid), vdata.get('vip_until'), vdata.get('given_by'), vdata.get('given_at')))

    # admin_logs
    for log in data.get('admin_logs', []):
        await db.execute("""
        INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """, (
            log.get('admin_id'),
            log.get('action'),
            log.get('target_id'),
            log.get('details'),
            log.get('timestamp')
        ))

    await db.commit()

# ================== ПОЛЬЗОВАТЕЛИ ==================

async def create_user_if_not_exists(db: aiosqlite.Connection, user_id: int,
                                    username: str = None, referral_code: str = None,
                                    referral_by: int = None):
    """Создать пользователя, если его нет, и вернуть его данные."""
    now = datetime.now().isoformat()
    today = datetime.now().date().isoformat()

    user = await db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not await user.fetchone():
        await db.execute("""
        INSERT INTO users (user_id, username, registration_date, last_activity, referral_code, referral_by)
        VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, username, now, now, referral_code, referral_by))
        await db.execute("""
        INSERT INTO activity (user_id, last_activity_date, current_week_start)
        VALUES (?, ?, ?)
        """, (user_id, today, today))
        await db.commit()
    else:
        if username:
            await db.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
            await db.commit()

    user_row = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await user_row.fetchone()

async def get_user(db: aiosqlite.Connection, user_id: int):
    row = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return await row.fetchone()

async def get_user_by_username(db: aiosqlite.Connection, username: str):
    """Поиск пользователя по имени (без @)."""
    clean = username.lstrip('@')
    row = await db.execute("SELECT * FROM users WHERE username = ?", (clean,))
    return await row.fetchone()

# ================== БАЛАНС И СТАТИСТИКА ==================

async def update_user_balance(db: aiosqlite.Connection, user_id: int, delta: float):
    await db.execute("UPDATE users SET game_balance = round(game_balance + ?, 1) WHERE user_id = ?",
                     (delta, user_id))
    await db.commit()

async def set_user_balance(db: aiosqlite.Connection, user_id: int, new_balance: float):
    await db.execute("UPDATE users SET game_balance = round(?, 1) WHERE user_id = ?",
                     (new_balance, user_id))
    await db.commit()

async def update_user_stats(db: aiosqlite.Connection, user_id: int, bet: float, is_win: bool):
    if is_win:
        await db.execute("""
        UPDATE users SET total_games = total_games + 1, total_wins = total_wins + 1
        WHERE user_id = ?
        """, (user_id,))
    else:
        await db.execute("""
        UPDATE users SET total_games = total_games + 1 WHERE user_id = ?
        """, (user_id,))
    await db.commit()

async def update_user_deposit(db: aiosqlite.Connection, user_id: int, amount: float, real_amount: int):
    await db.execute("""
    UPDATE users SET total_deposited = total_deposited + ?,
                     real_money_spent = real_money_spent + ?
    WHERE user_id = ?
    """, (amount, real_amount, user_id))
    await db.commit()

# ================== РЕФЕРАЛЬНАЯ СИСТЕМА ==================

async def update_user_referral_code(db: aiosqlite.Connection, user_id: int, code: str):
    await db.execute("UPDATE users SET referral_code = ? WHERE user_id = ?", (code, user_id))
    await db.execute("INSERT OR REPLACE INTO referral_codes (code, user_id) VALUES (?, ?)", (code, user_id))
    await db.commit()

async def set_user_referrer(db: aiosqlite.Connection, user_id: int, referrer_id: int):
    await db.execute("UPDATE users SET referral_by = ? WHERE user_id = ?", (referrer_id, user_id))
    await db.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (referrer_id,))
    await db.commit()

async def add_referral_earnings(db: aiosqlite.Connection, referrer_id: int, amount: float):
    """Начисляет реферальное вознаграждение на отдельный реферальный баланс."""
    await db.execute("""
    UPDATE users SET referral_earnings = referral_earnings + ?
    WHERE user_id = ?
    """, (amount, referrer_id))
    await db.commit()

async def transfer_referral_earnings(db: aiosqlite.Connection, user_id: int, amount: float):
    """Переносит реферальный баланс на игровой."""
    await db.execute("""
    UPDATE users SET referral_earnings = referral_earnings - ?,
                     game_balance = game_balance + ?
    WHERE user_id = ? AND referral_earnings >= ?
    """, (amount, amount, user_id, amount))
    await db.commit()

async def update_referral_balance(db: aiosqlite.Connection, user_id: int, delta: float):
    """Изменяет реферальный баланс (для списания при выводе)."""
    await db.execute("""
    UPDATE users SET referral_earnings = referral_earnings + ?
    WHERE user_id = ?
    """, (delta, user_id))
    await db.commit()

# ================== НАСТРОЙКИ ПОЛЬЗОВАТЕЛЯ ==================

async def update_user_slots_mode(db: aiosqlite.Connection, user_id: int, mode: str):
    await db.execute("UPDATE users SET slots_mode = ? WHERE user_id = ?", (mode, user_id))
    await db.commit()

async def update_user_bet(db: aiosqlite.Connection, user_id: int, bet: int):
    await db.execute("UPDATE users SET current_bet = ? WHERE user_id = ?", (bet, user_id))
    await db.commit()

async def increment_mega_wins(db: aiosqlite.Connection, user_id: int, extra_amount: float):
    await db.execute("""
    UPDATE users SET mega_wins_count = mega_wins_count + 1,
                     total_mega_win_amount = total_mega_win_amount + ?
    WHERE user_id = ?
    """, (extra_amount, user_id))
    await db.commit()

async def update_win_streak(db: aiosqlite.Connection, user_id: int, streak: int):
    await db.execute("""
    UPDATE users SET win_streak = ?, max_win_streak = MAX(max_win_streak, ?)
    WHERE user_id = ?
    """, (streak, streak, user_id))
    await db.commit()

async def add_used_promo_code(db: aiosqlite.Connection, user_id: int, code: str):
    user = await get_user(db, user_id)
    used = json.loads(user['used_promo_codes']) if user else []
    used.append(code)
    await db.execute("UPDATE users SET used_promo_codes = ? WHERE user_id = ?",
                     (json.dumps(used), user_id))
    await db.commit()

# ================== АКТИВНОСТЬ ==================

async def get_user_activity(db: aiosqlite.Connection, user_id: int):
    row = await db.execute("SELECT * FROM activity WHERE user_id = ?", (user_id,))
    return await row.fetchone()

async def update_activity(db: aiosqlite.Connection, user_id: int, updates: dict):
    sets = ", ".join([f"{k} = ?" for k in updates])
    values = list(updates.values()) + [user_id]
    await db.execute(f"UPDATE activity SET {sets} WHERE user_id = ?", values)
    await db.commit()

# ================== ПРОМОКОДЫ ==================

async def create_promo_code_db(db: aiosqlite.Connection, code: str, amount: int,
                               uses: int, creator_id: int):
    await db.execute("""
    INSERT INTO promo_codes (code, amount, uses_left, created_by, created_at, used_by)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (code, amount, uses, creator_id, datetime.now().isoformat(), json.dumps([])))
    await db.commit()

async def get_promo_code(db: aiosqlite.Connection, code: str):
    row = await db.execute("SELECT * FROM promo_codes WHERE code = ?", (code,))
    return await row.fetchone()

async def use_promo_code_db(db: aiosqlite.Connection, code: str, user_id: int) -> bool:
    promo = await get_promo_code(db, code)
    if not promo or promo['uses_left'] <= 0:
        return False
    used_by = json.loads(promo['used_by'])
    if user_id in used_by:
        return False
    used_by.append(user_id)
    await db.execute("""
    UPDATE promo_codes SET uses_left = uses_left - 1, used_by = ?
    WHERE code = ?
    """, (json.dumps(used_by), code))
    await db.execute("UPDATE users SET game_balance = game_balance + ? WHERE user_id = ?",
                     (promo['amount'], user_id))
    await add_used_promo_code(db, user_id, code)
    await db.commit()
    return True

async def delete_promo_code_db(db: aiosqlite.Connection, code: str):
    await db.execute("DELETE FROM promo_codes WHERE code = ?", (code,))
    await db.commit()

async def get_all_promo_codes(db: aiosqlite.Connection):
    rows = await db.execute("SELECT * FROM promo_codes")
    return await rows.fetchall()

# ================== БАНЫ, МУТЫ, ПРЕДУПРЕЖДЕНИЯ, VIP ==================

async def add_ban(db: aiosqlite.Connection, user_id: int, reason: str, admin_id: int):
    await db.execute("""
    INSERT OR REPLACE INTO bans (user_id, reason, banned_by, banned_at)
    VALUES (?, ?, ?, ?)
    """, (user_id, reason, admin_id, datetime.now().isoformat()))
    await db.commit()

async def remove_ban(db: aiosqlite.Connection, user_id: int):
    await db.execute("DELETE FROM bans WHERE user_id = ?", (user_id,))
    await db.commit()

async def get_ban(db: aiosqlite.Connection, user_id: int):
    row = await db.execute("SELECT * FROM bans WHERE user_id = ?", (user_id,))
    return await row.fetchone()

async def get_all_bans(db: aiosqlite.Connection):
    rows = await db.execute("SELECT * FROM bans")
    return await rows.fetchall()

async def add_mute(db: aiosqlite.Connection, user_id: int, until: str, reason: str, admin_id: int):
    await db.execute("""
    INSERT OR REPLACE INTO mutes (user_id, muted_until, reason, muted_by, muted_at)
    VALUES (?, ?, ?, ?, ?)
    """, (user_id, until, reason, admin_id, datetime.now().isoformat()))
    await db.commit()

async def remove_mute(db: aiosqlite.Connection, user_id: int):
    await db.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
    await db.commit()

async def get_mute(db: aiosqlite.Connection, user_id: int):
    row = await db.execute("SELECT * FROM mutes WHERE user_id = ?", (user_id,))
    return await row.fetchone()

async def add_warning(db: aiosqlite.Connection, user_id: int, reason: str, admin_id: int):
    await db.execute("""
    INSERT INTO warnings (user_id, reason, warned_by, warned_at)
    VALUES (?, ?, ?, ?)
    """, (user_id, reason, admin_id, datetime.now().isoformat()))
    user = await get_user(db, user_id)
    warns = json.loads(user['warnings']) if user else []
    warns.append({"reason": reason, "by": admin_id, "at": datetime.now().isoformat()})
    await db.execute("UPDATE users SET warnings = ? WHERE user_id = ?",
                     (json.dumps(warns), user_id))
    await db.commit()

async def remove_last_warning(db: aiosqlite.Connection, user_id: int):
    user = await get_user(db, user_id)
    warns = json.loads(user['warnings']) if user else []
    if warns:
        warns.pop()
        await db.execute("UPDATE users SET warnings = ? WHERE user_id = ?",
                         (json.dumps(warns), user_id))
        await db.commit()
        return True
    return False

async def get_warnings(db: aiosqlite.Connection, user_id: int):
    rows = await db.execute("SELECT * FROM warnings WHERE user_id = ?", (user_id,))
    return await rows.fetchall()

async def set_vip(db: aiosqlite.Connection, user_id: int, until: str, admin_id: int):
    await db.execute("""
    INSERT OR REPLACE INTO vip (user_id, vip_until, given_by, given_at)
    VALUES (?, ?, ?, ?)
    """, (user_id, until, admin_id, datetime.now().isoformat()))
    await db.execute("UPDATE users SET vip_until = ? WHERE user_id = ?", (until, user_id))
    await db.commit()

async def remove_vip(db: aiosqlite.Connection, user_id: int):
    await db.execute("DELETE FROM vip WHERE user_id = ?", (user_id,))
    await db.execute("UPDATE users SET vip_until = NULL WHERE user_id = ?", (user_id,))
    await db.commit()

async def get_vip(db: aiosqlite.Connection, user_id: int):
    row = await db.execute("SELECT * FROM vip WHERE user_id = ?", (user_id,))
    return await row.fetchone()

# ================== ВЫВОДЫ ==================

async def create_withdrawal_request(db: aiosqlite.Connection, user_id: int,
                                    amount: float, combination: dict,
                                    gift_count: int, source: str = 'balance') -> int:
    cursor = await db.execute("""
    INSERT INTO withdrawal_requests (user_id, amount, combination, gift_count, status, created_at, source)
    VALUES (?, ?, ?, ?, 'pending', ?, ?)
    """, (user_id, amount, json.dumps(combination), gift_count, datetime.now().isoformat(), source))
    await db.commit()
    return cursor.lastrowid

async def get_pending_withdrawals(db: aiosqlite.Connection, source: str = None):
    if source:
        rows = await db.execute("""
        SELECT * FROM withdrawal_requests WHERE status = 'pending' AND source = ? ORDER BY created_at
        """, (source,))
    else:
        rows = await db.execute("""
        SELECT * FROM withdrawal_requests WHERE status = 'pending' ORDER BY created_at
        """)
    return await rows.fetchall()

async def mark_withdrawal_done(db: aiosqlite.Connection, request_id: int):
    await db.execute("""
    UPDATE withdrawal_requests SET status = 'completed' WHERE id = ?
    """, (request_id,))
    await db.commit()

# ================== ЛОГИ АДМИНОВ ==================

async def log_admin_action(db: aiosqlite.Connection, admin_id: int, action: str,
                           target_id: int = None, details: str = ""):
    await db.execute("""
    INSERT INTO admin_logs (admin_id, action, target_id, details, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (admin_id, action, target_id, details, datetime.now().isoformat()))
    await db.commit()

async def get_recent_logs(db: aiosqlite.Connection, limit: int = 20):
    rows = await db.execute("""
    SELECT * FROM admin_logs ORDER BY timestamp DESC LIMIT ?
    """, (limit,))
    return await rows.fetchall()

async def clear_logs_db(db: aiosqlite.Connection):
    await db.execute("DELETE FROM admin_logs")
    await db.commit()

# ================== СТАТИСТИКА ==================

async def get_total_users(db: aiosqlite.Connection):
    row = await db.execute("SELECT COUNT(*) as cnt FROM users")
    return (await row.fetchone())['cnt']

async def get_users_activity_today(db: aiosqlite.Connection):
    today = datetime.now().date().isoformat()
    row = await db.execute("""
    SELECT COUNT(DISTINCT user_id) as cnt FROM activity WHERE last_activity_date = ?
    """, (today,))
    return (await row.fetchone())['cnt']

async def get_total_balance(db: aiosqlite.Connection):
    row = await db.execute("SELECT SUM(game_balance) as sum_bal FROM users")
    return (await row.fetchone())['sum_bal'] or 0.0

async def get_total_deposited(db: aiosqlite.Connection):
    row = await db.execute("SELECT SUM(total_deposited) as sum_dep FROM users")
    return (await row.fetchone())['sum_dep'] or 0.0

async def get_total_games(db: aiosqlite.Connection):
    row = await db.execute("SELECT SUM(total_games) as sum_games FROM users")
    return (await row.fetchone())['sum_games'] or 0

async def get_total_wins(db: aiosqlite.Connection):
    row = await db.execute("SELECT SUM(total_wins) as sum_wins FROM users")
    return (await row.fetchone())['sum_wins'] or 0

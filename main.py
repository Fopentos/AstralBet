import os
import json
import random
import datetime
import asyncio
from dotenv import load_dotenv
from telegram import Update, LabeledPrice, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ContextTypes, filters, PreCheckoutQueryHandler, ConversationHandler
)
import aiosqlite
import db

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise EnvironmentError("BOT_TOKEN не задан в переменных окружения")
PROVIDER_TOKEN = os.getenv("PROVIDER_TOKEN", "TEST_PROVIDER_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(","))) if os.getenv("ADMIN_IDS") else []

# -------------------- КОНФИГУРАЦИЯ --------------------
MIN_BET = 1
MAX_BET = 1_000_000_000
MIN_WITHDRAWAL = 15

CUSTOM_DEPOSIT_CONFIG = {"min_amount": 1, "max_amount": 1_000_000, "step": 1}
DICE_DELAYS = {"🎰": 1.2, "🎯": 2.2, "🎲": 2.2, "🎳": 3.3, "⚽": 3.3, "🏀": 3.3}
REFUND_CONFIG = {"min_refund": 0.02, "max_refund": 0.1}
MEGA_WIN_CONFIG = {"chance": 0.006, "min_multiplier": 1.5, "max_multiplier": 5.0}
WEEKLY_BONUS_CONFIG = {
    "min_daily_games": 5, "required_days": 7,
    "base_percent": 0.01, "bonus_per_extra_game": 0.0005, "max_extra_bonus": 0.02
}
REFERRAL_CONFIG = {"reward_percent": 0.10, "min_referee_games": 3, "min_referee_deposit": 10}
PROMO_CONFIG = {"max_active_promos": 50, "default_uses": 100, "min_amount": 5, "max_amount": 1000}

PRODUCTS = {
    "pack_5": {"title": "5 ⭐", "description": "Пополнение на 5 ⭐", "price": 5, "currency": "XTR", "credits": 5},
    "pack_10": {"title": "10 ⭐", "description": "Пополнение на 10 ⭐", "price": 10, "currency": "XTR", "credits": 10},
    "pack_25": {"title": "25 ⭐", "description": "Пополнение на 25 ⭐", "price": 25, "currency": "XTR", "credits": 25},
    "pack_50": {"title": "50 ⭐", "description": "Пополнение на 50 ⭐", "price": 50, "currency": "XTR", "credits": 50},
    "pack_100": {"title": "100 ⭐", "description": "Пополнение на 100 ⭐", "price": 100, "currency": "XTR", "credits": 100},
    "pack_250": {"title": "250 ⭐", "description": "Пополнение на 250 ⭐", "price": 250, "currency": "XTR", "credits": 250},
    "pack_500": {"title": "500 ⭐", "description": "Пополнение на 500 ⭐", "price": 500, "currency": "XTR", "credits": 500},
    "pack_1000": {"title": "1000 ⭐", "description": "Пополнение на 1000 ⭐", "price": 1000, "currency": "XTR", "credits": 1000}
}

BASE_PRIZES = {
    "🎰": {"ТРИ БАРА": 5, "ТРИ ВИШНИ": 10, "ТРИ ЛИМОНЫ": 15, "ДЖЕКПОТ 777": 20},
    "🎯": {"ПОПАДАНИЕ В ЦЕЛЬ": 3},
    "🎲": {"ВЫПАЛО 6": 3},
    "🎳": {"СТРАЙК": 3},
    "⚽": {"СЛАБЫЙ УДАР": 0.0, "УДАР МИМО": 0.0, "БЛИЗКИЙ УДАР": 0.0,
          "ХОРОШИЙ ГОЛ": 2.0, "СУПЕРГОЛ": 2.0},
    "🏀": {"ПРОМАХ": 0.0, "КАСАТЕЛЬНО": 0.0, "ОТСКОК": 0.0,
          "ТРЕХОЧКОВЫЙ": 2.0, "СЛЭМ-ДАНК": 2.0}
}

GAMES_CONFIG = {}
for emoji, prizes in BASE_PRIZES.items():
    if emoji == "🎰":
        values = {}
        for i in range(1, 65):
            if i == 1:
                values[i] = {"win": True, "base_prize": prizes["ТРИ БАРА"], "message": "🎰 ТРИ БАРА! Выигрыш: {prize} ⭐"}
            elif i == 22:
                values[i] = {"win": True, "base_prize": prizes["ТРИ ВИШНИ"], "message": "🎰 ТРИ ВИШНИ! Выигрыш: {prize} ⭐"}
            elif i == 43:
                values[i] = {"win": True, "base_prize": prizes["ТРИ ЛИМОНЫ"], "message": "🎰 ТРИ ЛИМОНА! Выигрыш: {prize} ⭐"}
            elif i == 64:
                values[i] = {"win": True, "base_prize": prizes["ДЖЕКПОТ 777"], "message": "🎰 ДЖЕКПОТ 777! Выигрыш: {prize} ⭐"}
            else:
                values[i] = {"win": False, "base_prize": 0, "message": f"🎰 Комбинация #{i} - проигрыш. Возврат: {{prize}} ⭐"}
        GAMES_CONFIG["🎰"] = {"values": values}
    elif emoji in ("🎯", "🎲", "🎳"):
        win_prize = list(prizes.values())[0]
        values = {}
        for i in range(1, 7):
            if i == 6:
                values[i] = {"win": True, "base_prize": win_prize, "message": f"{emoji} - ПОБЕДА! Выигрыш: {{prize}} ⭐"}
            else:
                values[i] = {"win": False, "base_prize": 0, "message": f"{emoji} - проигрыш. Возврат: {{prize}} ⭐"}
        GAMES_CONFIG[emoji] = {"values": values}
    else:
        values = {}
        for i, (name, prize) in enumerate(prizes.items(), start=1):
            win = prize >= 1.0
            values[i] = {"win": win, "base_prize": prize,
                         "message": f"{emoji} {name}. {'Выигрыш' if win else 'Возврат'}: {{prize}} ⭐"}
        GAMES_CONFIG[emoji] = {"values": values}

WAITING_CUSTOM_AMOUNT, CONFIRM_CUSTOM_AMOUNT, WAITING_WITHDRAW_AMOUNT, CONFIRM_WITHDRAW, \
WAITING_SEARCH_USER, WAITING_PROMO_AMOUNT, WAITING_PROMO_USES, \
WAITING_REF_WITHDRAW_AMOUNT, CONFIRM_REF_WITHDRAW, WAITING_DELETE_PROMO = range(10)

class GiftCalculator:
    def __init__(self):
        self.available_gifts = [100, 50, 25, 15]

    def can_withdraw_amount(self, amount: int) -> bool:
        return self._find_combination(amount) is not None

    def find_best_combination(self, amount: int) -> dict:
        combination = self._find_combination(amount)
        if combination is None:
            for diff in range(1, 100):
                test_amount = amount + diff
                combination = self._find_combination(test_amount)
                if combination is not None:
                    return combination
        return combination or {}

    def _find_combination(self, amount: int) -> dict | None:
        if amount == 0:
            return {}
        if amount < 0:
            return None
        for gift in self.available_gifts:
            if amount >= gift:
                remaining = amount - gift
                result = self._find_combination(remaining)
                if result is not None:
                    result = result.copy()
                    result[gift] = result.get(gift, 0) + 1
                    return result
        return None

    def get_suggested_amounts(self, desired_amount: int, count: int = 3) -> list:
        suggestions = []
        for diff in range(0, 100):
            for direction in [1, -1]:
                test_amount = desired_amount + diff * direction
                if test_amount >= MIN_WITHDRAWAL and self.can_withdraw_amount(test_amount):
                    if test_amount not in suggestions:
                        suggestions.append(test_amount)
                    if len(suggestions) >= count:
                        return sorted(suggestions)
        return sorted(suggestions)

gift_calculator = GiftCalculator()

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def get_win_streak_bonus(streak: int) -> tuple:
    if streak <= 1:
        return 1.0, ""
    if streak == 2:
        return 1.1, "🔥 Серия из 2 побед! Бонус +10%"
    if streak == 3:
        return 1.25, "🔥🔥 Серия из 3 побед! Бонус +25%"
    if streak == 4:
        return 1.45, "🔥🔥🔥 Серия из 4 побед! Бонус +45%"
    if streak == 5:
        return 1.6, "🔥🔥🔥🔥 Серия из 5 побед! Бонус +60%"
    if streak == 6:
        return 1.85, "🔥🔥🔥🔥🔥 СЕРИЯ ИЗ 6 ПОБЕД! +85%"
    multiplier = 1.85 + (streak - 6) * 0.10
    return multiplier, f"🔥 СЕРИЯ ИЗ {streak} ПОБЕД! МЕГА БОНУС +{int((multiplier-1)*100)}%"

async def check_ban_mute(user_id: int, db_conn: aiosqlite.Connection) -> str | None:
    ban = await db.get_ban(db_conn, user_id)
    if ban:
        return f"🚫 Вы забанены администратором.\nПричина: {ban['reason']}"
    mute = await db.get_mute(db_conn, user_id)
    if mute and datetime.datetime.fromisoformat(mute['muted_until']) > datetime.datetime.now():
        time_left = datetime.datetime.fromisoformat(mute['muted_until']) - datetime.datetime.now()
        return f"🔇 Вы в муте. Осталось: {str(time_left).split('.')[0]}"
    return None

async def process_dice_result(user_id: int, emoji: str, value: int, bet: int,
                              message, context: ContextTypes.DEFAULT_TYPE):
    db_conn = context.bot_data['db']
    try:
        user = await db.get_user(db_conn, user_id)
        if not user:
            return
        restriction = await check_ban_mute(user_id, db_conn)
        if restriction:
            await message.reply_text(restriction)
            return
        config = GAMES_CONFIG.get(emoji)
        if not config:
            return
        result = config["values"].get(value)
        if not result:
            result = {"win": False, "base_prize": 0, "message": f"{emoji} - проигрыш. Возврат: {{prize}} ⭐"}
        base_prize = result["base_prize"]
        is_win = result["win"]
        prize = base_prize * bet
        bonus_msgs = []
        if not is_win and base_prize == 0:
            refund_pct = random.uniform(REFUND_CONFIG["min_refund"], REFUND_CONFIG["max_refund"])
            prize = round(bet * refund_pct, 1)
            bonus_msgs.append(f"🔄 Возврат {refund_pct*100:.1f}% от ставки: {prize} ⭐")
        if is_win and base_prize > 0:
            new_streak = user['win_streak'] + 1
            multiplier, streak_msg = get_win_streak_bonus(new_streak)
            if multiplier > 1.0:
                prize = round(prize * multiplier, 1)
                bonus_msgs.append(streak_msg)
            await db.update_win_streak(db_conn, user_id, new_streak)
        else:
            if user['win_streak'] > 0:
                bonus_msgs.append(f"💔 Серия побед прервана на {user['win_streak']}!")
            await db.update_win_streak(db_conn, user_id, 0)
        if is_win and base_prize > 0 and random.random() < MEGA_WIN_CONFIG["chance"]:
            mega_mult = random.uniform(MEGA_WIN_CONFIG["min_multiplier"], MEGA_WIN_CONFIG["max_multiplier"])
            extra = round(prize * mega_mult - prize, 1)
            if extra > 0:
                prize = round(prize + extra, 1)
                await db.increment_mega_wins(db_conn, user_id, extra)
                bonus_msgs.append(f"🎉 МЕГА-ВЫИГРЫШ! x{mega_mult:.1f} к выигрышу!")
        if not is_admin(user_id):
            await db.update_user_balance(db_conn, user_id, -bet)
        if prize > 0:
            await db.update_user_balance(db_conn, user_id, prize)
        await db.update_user_stats(db_conn, user_id, bet, is_win)
        updated_user = await db.get_user(db_conn, user_id)
        balance = round(updated_user['game_balance'], 1)
        result_msg = result["message"].format(prize=prize)
        full_msg = f"{result_msg}\n\n💰 Баланс: {balance} ⭐"
        if bonus_msgs:
            full_msg += "\n\n" + "\n".join(bonus_msgs)
        await message.reply_text(full_msg)
        if not is_admin(user_id) and user['referral_by']:
            referrer = await db.get_user(db_conn, user['referral_by'])
            if referrer and referrer['total_games'] >= REFERRAL_CONFIG["min_referee_games"] \
                    and referrer['total_deposited'] >= REFERRAL_CONFIG["min_referee_deposit"]:
                loss = max(0, bet - prize)
                if loss > 0:
                    ref_reward = round(loss * REFERRAL_CONFIG["reward_percent"], 1)
                    # Начисляем только на реферальный баланс, не на игровой
                    await db.add_referral_earnings(db_conn, user['referral_by'], ref_reward)
                    try:
                        await context.bot.send_message(user['referral_by'],
                                                       f"👥 Вы получили {ref_reward} ⭐ на реферальный баланс за проигрыш друга.")
                    except:
                        pass
        weekly_bonus = await update_weekly_activity(db_conn, user_id, bet)
        if weekly_bonus:
            await context.bot.send_message(user_id,
                                           f"🎁 НЕДЕЛЬНАЯ НАГРАДА!\n\n"
                                           f"Базовый бонус: {weekly_bonus['base_bonus']} ⭐\n"
                                           f"Доп. бонус: {weekly_bonus['extra_bonus']} ⭐\n"
                                           f"💰 Итого: {weekly_bonus['total_bonus']} ⭐\n\n"
                                           f"Ваш баланс: {balance + weekly_bonus['total_bonus']} ⭐")
    finally:
        if user_id in context.bot_data.setdefault('in_game', set()):
            context.bot_data['in_game'].discard(user_id)

async def update_weekly_activity(db_conn, user_id, bet):
    act = await db.get_user_activity(db_conn, user_id)
    today = datetime.datetime.now().date()
    today_iso = today.isoformat()
    if not act:
        await db_conn.execute("INSERT INTO activity (user_id) VALUES (?)", (user_id,))
        await db_conn.commit()
        return None
    week_start_str = act['current_week_start'] or today_iso
    week_start = datetime.datetime.fromisoformat(week_start_str).date()
    days_diff = (today - week_start).days
    previous_total_bets = act['weekly_total_bets']
    previous_total_games = act['weekly_total_games']
    if days_diff >= 7:
        bonus_info = None
        if act['weekly_streak_days'] >= WEEKLY_BONUS_CONFIG["required_days"]:
            base_bonus = round(previous_total_bets * WEEKLY_BONUS_CONFIG["base_percent"], 1)
            min_games = WEEKLY_BONUS_CONFIG["min_daily_games"] * WEEKLY_BONUS_CONFIG["required_days"]
            extra_games = max(0, previous_total_games - min_games)
            extra_bonus = round(previous_total_bets * extra_games * WEEKLY_BONUS_CONFIG["bonus_per_extra_game"], 1)
            extra_bonus = min(extra_bonus, round(previous_total_bets * WEEKLY_BONUS_CONFIG["max_extra_bonus"], 1))
            total_bonus = base_bonus + extra_bonus
            if total_bonus > 0:
                await db.update_user_balance(db_conn, user_id, total_bonus)
                bonus_info = {'base_bonus': base_bonus, 'extra_bonus': extra_bonus, 'total_bonus': total_bonus}
        await db.update_activity(db_conn, user_id, {
            'weekly_streak_days': 0,
            'weekly_total_bets': 0,
            'weekly_total_games': 0,
            'current_week_start': today_iso,
            'daily_games_count': 0,
            'last_activity_date': today_iso
        })
        return bonus_info
    last_date_str = act['last_activity_date']
    if last_date_str != today_iso:
        if last_date_str:
            last_date = datetime.datetime.fromisoformat(last_date_str).date()
            if (today - last_date).days == 1:
                await db.update_activity(db_conn, user_id, {'weekly_streak_days': act['weekly_streak_days'] + 1})
            else:
                await db.update_activity(db_conn, user_id, {'weekly_streak_days': 1})
        else:
            await db.update_activity(db_conn, user_id, {'weekly_streak_days': 1})
        await db.update_activity(db_conn, user_id, {'last_activity_date': today_iso, 'daily_games_count': 1})
    else:
        await db.update_activity(db_conn, user_id, {'daily_games_count': act['daily_games_count'] + 1})
    await db.update_activity(db_conn, user_id, {
        'weekly_total_games': act['weekly_total_games'] + 1,
        'weekly_total_bets': act['weekly_total_bets'] + bet
    })
    return None

# ---------- Команды ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.effective_user.username
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await update.message.reply_text(restriction)
        return
    ref_code = context.args[0] if context.args else None
    user = await db.create_user_if_not_exists(db_conn, user_id, username=username)
    if ref_code and not user['referral_by']:
        row = await db_conn.execute("SELECT user_id FROM referral_codes WHERE code = ?", (ref_code,))
        ref_row = await row.fetchone()
        if ref_row and ref_row['user_id'] != user_id:
            await db.set_user_referrer(db_conn, user_id, ref_row['user_id'])
    if not user['referral_code']:
        code = f"AST{user_id % 10000:04d}"
        await db.update_user_referral_code(db_conn, user_id, code)
    welcome = (
        "🎰 AstralBet Casino\n\n"
        "Добро пожаловать! Играйте, пополняйте баланс и выводите выигрыши.\n\n"
        "Основные команды:\n"
        "/profile - профиль\n"
        "/play - игры\n"
        "/deposit - пополнить\n"
        "/withdraw - вывести\n"
        "/promo <код> - активировать промокод\n"
        "/help - помощь"
    )
    keyboard = [
        [InlineKeyboardButton("🎮 Играть", callback_data="play_games")],
        [InlineKeyboardButton("📊 Профиль", callback_data="profile"),
         InlineKeyboardButton("💰 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("💸 Вывести", callback_data="withdraw")],
    ]
    await update.message.reply_text(welcome, reply_markup=InlineKeyboardMarkup(keyboard))

async def play_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    if not user:
        await update.message.reply_text("Сначала зарегистрируйтесь через /start")
        return
    balance = round(user['game_balance'], 1)
    bet = user['current_bet']
    slots_mode = user['slots_mode']
    text = (
        f"🎮 Игры\n\n"
        f"💰 Баланс: {balance} ⭐\n"
        f"🎯 Ставка: {bet} ⭐\n"
        f"🎰 Режим слотов: {'Обычный' if slots_mode == 'normal' else '777'}\n\n"
        f"Выберите игру или киньте эмодзи в чат:"
    )
    keyboard = [
        [InlineKeyboardButton("🎰 Слоты", callback_data="play_slots"),
         InlineKeyboardButton("🎰 777", callback_data="play_777")],
        [InlineKeyboardButton("🎯 Дартс", callback_data="play_darts"),
         InlineKeyboardButton("🎲 Кубик", callback_data="play_dice")],
        [InlineKeyboardButton("🎳 Боулинг", callback_data="play_bowling"),
         InlineKeyboardButton("⚽ Футбол", callback_data="play_football")],
        [InlineKeyboardButton("🏀 Баскетбол", callback_data="play_basket")],
        [InlineKeyboardButton("🔙 Профиль", callback_data="profile")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🎰 AstralBet Casino - Помощь\n\n"
        "🎮 Игры:\n"
        "Просто отправьте любой dice эмодзи: 🎰 🎯 🎲 🎳 ⚽ 🏀\n"
        "Или используйте кнопки меню.\n\n"
        "💰 Пополнение через Telegram Stars.\n"
        "💸 Вывод от 15 ⭐ через заявки.\n\n"
        "Команды:\n"
        "/start - начало\n"
        "/profile - ваш профиль\n"
        "/activity - недельная активность\n"
        "/promo <код> - активировать промокод\n"
        "/bet <сумма> - изменить ставку\n"
        "/deposit - пополнить\n"
        "/withdraw - вывести"
    )
    await update.message.reply_text(text)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        db_conn = context.bot_data['db']
    else:
        user_id = update.effective_user.id
        db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        if query:
            await query.edit_message_text(restriction)
        else:
            await update.message.reply_text(restriction)
        return
    user_data = await db.get_user(db_conn, user_id)
    if not user_data:
        text = "Профиль не найден. Нажмите /start"
        if query:
            await query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return
    act = await db.get_user_activity(db_conn, user_id)
    streak = act['weekly_streak_days'] if act else 0
    winrate = (user_data['total_wins'] / user_data['total_games'] * 100) if user_data['total_games'] > 0 else 0
    username = user_data['username'] or "нет"
    text = (
        f"📊 Профиль\n\n"
        f"👤 Имя: @{username}\n"
        f"🆔 ID: {user_id}\n"
        f"💰 Баланс: {round(user_data['game_balance'], 1)} ⭐\n"
        f"🎯 Ставка: {user_data['current_bet']} ⭐\n"
        f"🎮 Игр: {user_data['total_games']}\n"
        f"🏆 Побед: {user_data['total_wins']} ({winrate:.1f}%)\n"
        f"💳 Пополнено: {user_data['total_deposited']} ⭐\n"
        f"🔥 Серия побед: {user_data['win_streak']} (макс: {user_data['max_win_streak']})\n"
        f"🎉 Мега-выигрышей: {user_data['mega_wins_count']}\n"
        f"📅 Дней активности подряд: {streak}"
    )
    keyboard = [
        [InlineKeyboardButton("🎮 Играть", callback_data="play_games"),
         InlineKeyboardButton("💰 Пополнить", callback_data="deposit")],
        [InlineKeyboardButton("💸 Вывести", callback_data="withdraw"),
         InlineKeyboardButton("🎯 Ставка", callback_data="change_bet")],
        [InlineKeyboardButton("👥 Рефералы", callback_data="referral_system")]
    ]
    if is_admin(user_id):
        keyboard.append([InlineKeyboardButton("👑 Админ-панель", callback_data="admin_panel")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def activity_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await update.message.reply_text(restriction)
        return
    act = await db.get_user_activity(db_conn, user_id)
    if not act:
        await update.message.reply_text("Нет данных активности.")
        return
    text = (
        f"📊 Активность\n\n"
        f"🎮 Игр сегодня: {act['daily_games_count']}/{WEEKLY_BONUS_CONFIG['min_daily_games']}\n"
        f"📅 Дней подряд: {act['weekly_streak_days']}/{WEEKLY_BONUS_CONFIG['required_days']}\n"
        f"🎯 Всего игр за неделю: {act['weekly_total_games']}\n"
        f"💰 Сумма ставок за неделю: {round(act['weekly_total_bets'], 1)} ⭐\n"
    )
    await update.message.reply_text(text)

async def bet_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await update.message.reply_text(restriction)
        return
    if not context.args:
        user = await db.get_user(db_conn, user_id)
        if user:
            await update.message.reply_text(f"🎯 Текущая ставка: {user['current_bet']} ⭐")
        return
    try:
        new_bet = int(context.args[0])
        if new_bet < MIN_BET:
            await update.message.reply_text(f"❌ Минимальная ставка: {MIN_BET} ⭐")
            return
        if new_bet > MAX_BET:
            await update.message.reply_text(f"❌ Максимальная ставка: {MAX_BET} ⭐")
            return
        await db.update_user_bet(db_conn, user_id, new_bet)
        await update.message.reply_text(f"✅ Ставка изменена на {new_bet} ⭐")
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")

# ---------- Игры ----------
async def play_games_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await query.edit_message_text(restriction)
        return
    user = await db.get_user(db_conn, user_id)
    if not user:
        await query.edit_message_text("Профиль не найден. /start")
        return
    balance = round(user['game_balance'], 1)
    bet = user['current_bet']
    slots_mode = user['slots_mode']
    text = (
        f"🎮 Игры\n\n"
        f"💰 Баланс: {balance} ⭐\n"
        f"🎯 Ставка: {bet} ⭐\n"
        f"🎰 Режим слотов: {'Обычный' if slots_mode == 'normal' else '777'}\n\n"
        f"Выберите игру или киньте эмодзи в чат:"
    )
    keyboard = [
        [InlineKeyboardButton("🎰 Слоты", callback_data="play_slots"),
         InlineKeyboardButton("🎰 777", callback_data="play_777")],
        [InlineKeyboardButton("🎯 Дартс", callback_data="play_darts"),
         InlineKeyboardButton("🎲 Кубик", callback_data="play_dice")],
        [InlineKeyboardButton("🎳 Боулинг", callback_data="play_bowling"),
         InlineKeyboardButton("⚽ Футбол", callback_data="play_football")],
        [InlineKeyboardButton("🏀 Баскетбол", callback_data="play_basket")],
        [InlineKeyboardButton("🔙 Профиль", callback_data="profile")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def change_bet_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await query.edit_message_text(restriction)
        return
    user = await db.get_user(db_conn, user_id)
    if not user:
        return
    text = f"🎯 Изменение ставки\nТекущая: {user['current_bet']} ⭐\nВведите /bet <сумма>"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Профиль", callback_data="profile")]]))

async def handle_game_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await query.edit_message_text(restriction)
        return
    user = await db.get_user(db_conn, user_id)
    if not user:
        return
    if user_id in context.bot_data.setdefault('in_game', set()):
        await query.answer("⏳ Дождитесь завершения текущей игры!", show_alert=True)
        return

    games = {
        "play_slots": ("🎰", 'normal'),
        "play_777": ("🎰", '777'),
        "play_darts": ("🎯", None),
        "play_dice": ("🎲", None),
        "play_bowling": ("🎳", None),
        "play_football": ("⚽", None),
        "play_basket": ("🏀", None)
    }
    data = query.data
    if data not in games:
        return
    emoji, mode = games[data]
    if mode:
        await db.update_user_slots_mode(db_conn, user_id, mode)
    bet = user['current_bet']
    if not is_admin(user_id) and user['game_balance'] < bet:
        await query.edit_message_text("❌ Недостаточно средств!")
        return
    context.bot_data.setdefault('in_game', set()).add(user_id)
    dice_msg = await context.bot.send_dice(query.message.chat_id, emoji=emoji)
    await asyncio.sleep(DICE_DELAYS[emoji])
    await process_dice_result(user_id, emoji, dice_msg.dice.value, bet, dice_msg, context)

async def dice_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message.from_user.is_bot:
        return
    user_id = message.from_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        await message.reply_text(restriction)
        return
    user = await db.get_user(db_conn, user_id)
    if not user:
        return
    emoji = message.dice.emoji
    if emoji not in GAMES_CONFIG:
        return
    if user_id in context.bot_data.setdefault('in_game', set()):
        return
    bet = user['current_bet']
    if not is_admin(user_id) and user['game_balance'] < bet:
        await message.reply_text("❌ Недостаточно средств!")
        return
    context.bot_data.setdefault('in_game', set()).add(user_id)
    await asyncio.sleep(DICE_DELAYS[emoji])
    await process_dice_result(user_id, emoji, message.dice.value, bet, message, context)

# ---------- Пополнение ----------
async def deposit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
    else:
        user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    restriction = await check_ban_mute(user_id, db_conn)
    if restriction:
        if query:
            await query.edit_message_text(restriction)
        else:
            await update.message.reply_text(restriction)
        return
    user = await db.get_user(db_conn, user_id)
    if not user:
        if query:
            await query.edit_message_text("Профиль не найден.")
        else:
            await update.message.reply_text("Профиль не найден.")
        return
    balance = round(user['game_balance'], 1)
    text = f"💰 Пополнение\n\nВаш баланс: {balance} ⭐\nВыберите сумму:"
    keyboard = []
    for key, prod in PRODUCTS.items():
        keyboard.append([InlineKeyboardButton(f"{prod['title']} - {prod['price']} Stars", callback_data=f"buy_{key}")])
    keyboard.append([InlineKeyboardButton("💎 Своя сумма", callback_data="custom_deposit")])
    keyboard.append([InlineKeyboardButton("🔙 Профиль", callback_data="profile")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=reply_markup)
    else:
        await update.message.reply_text(text, reply_markup=reply_markup)

async def buy_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    product_key = query.data.replace("buy_", "")
    product = PRODUCTS.get(product_key)
    if not product:
        return
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=product["title"],
        description=product["description"],
        payload=product_key,
        provider_token=PROVIDER_TOKEN,
        currency=product["currency"],
        prices=[LabeledPrice(product["title"], product["price"])],
        start_parameter="metaslots"
    )

async def custom_deposit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = f"💎 Введите сумму пополнения (от {CUSTOM_DEPOSIT_CONFIG['min_amount']} до {CUSTOM_DEPOSIT_CONFIG['max_amount']}):"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="deposit")]
    ]))
    return WAITING_CUSTOM_AMOUNT

async def custom_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if not (CUSTOM_DEPOSIT_CONFIG['min_amount'] <= amount <= CUSTOM_DEPOSIT_CONFIG['max_amount']):
            await update.message.reply_text(f"❌ Сумма должна быть от {CUSTOM_DEPOSIT_CONFIG['min_amount']} до {CUSTOM_DEPOSIT_CONFIG['max_amount']}")
            return WAITING_CUSTOM_AMOUNT
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")
        return WAITING_CUSTOM_AMOUNT
    context.user_data['custom_amount'] = amount
    keyboard = [
        [InlineKeyboardButton("💳 Оплатить", callback_data="confirm_custom")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_custom")]
    ]
    await update.message.reply_text(f"Сумма: {amount} Stars. Подтвердите оплату.", reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_CUSTOM_AMOUNT

async def confirm_custom_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    amount = context.user_data.get('custom_amount')
    if not amount:
        await query.edit_message_text("Ошибка сессии.")
        return ConversationHandler.END
    await context.bot.send_invoice(
        chat_id=query.message.chat_id,
        title=f"{amount} ⭐",
        description=f"Пополнение на {amount} ⭐",
        payload=f"custom_{amount}",
        provider_token=PROVIDER_TOKEN,
        currency="XTR",
        prices=[LabeledPrice(f"{amount} ⭐", amount)],
        start_parameter="custom"
    )
    return ConversationHandler.END

async def cancel_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Отменено", reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 К пополнению", callback_data="deposit")]
        ]))
    else:
        await update.message.reply_text("❌ Отменено")
    return ConversationHandler.END

async def pre_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    payload = query.invoice_payload
    if payload in PRODUCTS or payload.startswith("custom_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Неверный продукт")

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    payload = payment.invoice_payload
    if payload.startswith("custom_"):
        amount = int(payload.split("_")[1])
        credits = amount
    else:
        product = PRODUCTS.get(payload)
        if not product:
            return
        amount = product["price"]
        credits = product["credits"]
    await db.update_user_balance(db_conn, user_id, credits)
    await db.update_user_deposit(db_conn, user_id, credits, amount)
    await update.message.reply_text(f"✅ Платёж успешен! Зачислено {credits} ⭐")

# ---------- Вывод ----------
async def withdraw_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id
        db_conn = context.bot_data['db']
        restriction = await check_ban_mute(user_id, db_conn)
        if restriction:
            await query.edit_message_text(restriction)
            return
        user = await db.get_user(db_conn, user_id)
        if not user:
            return
        balance = round(user['game_balance'], 1)
        if balance < MIN_WITHDRAWAL:
            await query.edit_message_text(
                f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} ⭐\nВаш баланс: {balance} ⭐",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Профиль", callback_data="profile")]])
            )
            return
        text = (
            f"💸 Вывод средств\n\n"
            f"Ваш баланс: {balance} ⭐\n"
            f"Минимум: {MIN_WITHDRAWAL} ⭐\n"
            f"Сумма должна быть кратна 5 и раскладываться на подарки 15/25/50/100.\n"
            f"Введите сумму для вывода:"
        )
        await query.edit_message_text(text)
        context.user_data['awaiting_withdraw'] = True
        return WAITING_WITHDRAW_AMOUNT
    else:
        user_id = update.effective_user.id
        db_conn = context.bot_data['db']
        restriction = await check_ban_mute(user_id, db_conn)
        if restriction:
            await update.message.reply_text(restriction)
            return
        user = await db.get_user(db_conn, user_id)
        if not user:
            return
        balance = round(user['game_balance'], 1)
        if balance < MIN_WITHDRAWAL:
            await update.message.reply_text(f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} ⭐\nВаш баланс: {balance} ⭐")
            return
        text = (
            f"💸 Вывод средств\n\n"
            f"Ваш баланс: {balance} ⭐\n"
            f"Минимум: {MIN_WITHDRAWAL} ⭐\n"
            f"Сумма должна быть кратна 5 и раскладываться на подарки 15/25/50/100.\n"
            f"Введите сумму для вывода:"
        )
        await update.message.reply_text(text)
        context.user_data['awaiting_withdraw'] = True
        return WAITING_WITHDRAW_AMOUNT

async def withdraw_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_withdraw'):
        return ConversationHandler.END
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")
        return WAITING_WITHDRAW_AMOUNT

    if amount < MIN_WITHDRAWAL:
        await update.message.reply_text(f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} ⭐")
        return WAITING_WITHDRAW_AMOUNT
    if amount > user['game_balance']:
        await update.message.reply_text("❌ Недостаточно средств.")
        return WAITING_WITHDRAW_AMOUNT
    if amount % 5 != 0:
        await update.message.reply_text("❌ Сумма должна быть кратна 5.")
        return WAITING_WITHDRAW_AMOUNT

    if not gift_calculator.can_withdraw_amount(amount):
        suggestions = gift_calculator.get_suggested_amounts(amount, 3)
        sug_text = "\n".join([f"• {s} ⭐" for s in suggestions])
        await update.message.reply_text(
            f"❌ Сумма {amount} ⭐ не может быть собрана из подарков.\n"
            f"Ближайшие доступные суммы:\n{sug_text}\n"
            f"Введите ещё раз:"
        )
        return WAITING_WITHDRAW_AMOUNT

    combination = gift_calculator.find_best_combination(amount)
    gift_count = sum(combination.values())
    context.user_data['withdraw_amount'] = amount
    context.user_data['withdraw_combo'] = combination
    combo_text = " + ".join([f"{cnt}×{val}⭐" for val, cnt in combination.items()])
    text = (
        f"📦 Заявка на вывод {amount} ⭐\n"
        f"Подарков: {gift_count} шт.\n"
        f"Комбинация: {combo_text}\n\n"
        f"Подтвердите списание средств."
    )
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_withdraw")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_withdraw")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_WITHDRAW

async def confirm_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    amount = context.user_data.get('withdraw_amount')
    combo = context.user_data.get('withdraw_combo')
    if not amount or not combo:
        await query.edit_message_text("Ошибка данных.")
        return ConversationHandler.END

    user = await db.get_user(db_conn, user_id)
    if not user or user['game_balance'] < amount:
        await query.edit_message_text("Недостаточно средств.")
        return ConversationHandler.END

    await db.update_user_balance(db_conn, user_id, -amount)
    gift_count = sum(combo.values())
    request_id = await db.create_withdrawal_request(db_conn, user_id, amount, combo, gift_count, source='balance')

    user_info = query.from_user
    username = user_info.username or f"id{user_id}"
    mention = f"@{username}" if user_info.username else f"[пользователь](tg://user?id={user_id})"
    await query.edit_message_text(
        f"✅ Заявка #{request_id} создана!\n"
        f"Сумма: {amount} ⭐ списана.\n"
        f"Ожидайте отправки {gift_count} подарков администратором."
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 Новая заявка на вывод #{request_id}\n"
                f"Пользователь: {mention}\n"
                f"Сумма: {amount} ⭐\n"
                f"Подарки: {combo}"
            )
        except:
            pass

    return ConversationHandler.END

async def cancel_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Вывод отменён.")
    return ConversationHandler.END

# ---------- Реферальная система ----------
async def referral_system_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    if not user:
        await query.edit_message_text("Профиль не найден.")
        return
    bot = context.bot
    bot_username = (await bot.get_me()).username
    referral_link = f"https://t.me/{bot_username}?start={user['referral_code']}"
    ref_balance = round(user['referral_earnings'], 1)
    text = (
        f"👥 Реферальная система\n\n"
        f"Ваш код: {user['referral_code']}\n"
        f"Приглашено: {user['referrals_count']}\n"
        f"Реферальный баланс: {ref_balance} ⭐\n"
        f"Ссылка для приглашения:\n{referral_link}\n\n"
        f"Вы получаете 10% от проигрышей приглашённых друзей."
    )
    keyboard = [
        [InlineKeyboardButton("💸 Вывести на игровой баланс", callback_data="ref_to_balance")],
        [InlineKeyboardButton("🎁 Заказать вывод подарками", callback_data="ref_withdraw_start")],
        [InlineKeyboardButton("🔙 Профиль", callback_data="profile")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def ref_to_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    if not user:
        await query.edit_message_text("Профиль не найден.")
        return
    amount = user['referral_earnings']
    if amount <= 0:
        await query.answer("Нет средств для вывода.", show_alert=True)
        return
    # Переносим на игровой баланс
    await db.transfer_referral_earnings(db_conn, user_id, amount)
    await query.edit_message_text(f"✅ {amount} ⭐ переведено на игровой баланс!")
    # Обновим информацию
    await referral_system_callback(update, context)

async def ref_withdraw_start_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    if not user:
        return
    ref_balance = round(user['referral_earnings'], 1)
    if ref_balance < MIN_WITHDRAWAL:
        await query.edit_message_text(
            f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} ⭐\nРеферальный баланс: {ref_balance} ⭐",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Рефералы", callback_data="referral_system")]])
        )
        return
    text = (
        f"💸 Вывод реферальных средств\n\n"
        f"Доступно: {ref_balance} ⭐\n"
        f"Минимум: {MIN_WITHDRAWAL} ⭐\n"
        f"Сумма должна быть кратна 5 и раскладываться на подарки 15/25/50/100.\n"
        f"Введите сумму для вывода:"
    )
    await query.edit_message_text(text)
    context.user_data['awaiting_ref_withdraw'] = True
    return WAITING_REF_WITHDRAW_AMOUNT

async def ref_withdraw_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_ref_withdraw'):
        return ConversationHandler.END
    user_id = update.effective_user.id
    db_conn = context.bot_data['db']
    user = await db.get_user(db_conn, user_id)
    try:
        amount = int(update.message.text)
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")
        return WAITING_REF_WITHDRAW_AMOUNT

    if amount < MIN_WITHDRAWAL:
        await update.message.reply_text(f"❌ Минимальная сумма вывода: {MIN_WITHDRAWAL} ⭐")
        return WAITING_REF_WITHDRAW_AMOUNT
    if amount > user['referral_earnings']:
        await update.message.reply_text("❌ Недостаточно средств на реферальном балансе.")
        return WAITING_REF_WITHDRAW_AMOUNT
    if amount % 5 != 0:
        await update.message.reply_text("❌ Сумма должна быть кратна 5.")
        return WAITING_REF_WITHDRAW_AMOUNT

    if not gift_calculator.can_withdraw_amount(amount):
        suggestions = gift_calculator.get_suggested_amounts(amount, 3)
        sug_text = "\n".join([f"• {s} ⭐" for s in suggestions])
        await update.message.reply_text(
            f"❌ Сумма {amount} ⭐ не может быть собрана из подарков.\n"
            f"Ближайшие доступные суммы:\n{sug_text}\n"
            f"Введите ещё раз:"
        )
        return WAITING_REF_WITHDRAW_AMOUNT

    combination = gift_calculator.find_best_combination(amount)
    gift_count = sum(combination.values())
    context.user_data['ref_withdraw_amount'] = amount
    context.user_data['ref_withdraw_combo'] = combination
    combo_text = " + ".join([f"{cnt}×{val}⭐" for val, cnt in combination.items()])
    text = (
        f"📦 Заявка на вывод {amount} ⭐ (реферальный баланс)\n"
        f"Подарков: {gift_count} шт.\n"
        f"Комбинация: {combo_text}\n\n"
        f"Подтвердите списание с реферального баланса."
    )
    keyboard = [
        [InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_ref_withdraw")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_ref_withdraw")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    return CONFIRM_REF_WITHDRAW

async def confirm_ref_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    db_conn = context.bot_data['db']
    amount = context.user_data.get('ref_withdraw_amount')
    combo = context.user_data.get('ref_withdraw_combo')
    if not amount or not combo:
        await query.edit_message_text("Ошибка данных.")
        return ConversationHandler.END

    user = await db.get_user(db_conn, user_id)
    if not user or user['referral_earnings'] < amount:
        await query.edit_message_text("Недостаточно средств на реферальном балансе.")
        return ConversationHandler.END

    # Списываем с referral_earnings
    await db.update_referral_balance(db_conn, user_id, -amount)
    gift_count = sum(combo.values())
    request_id = await db.create_withdrawal_request(db_conn, user_id, amount, combo, gift_count, source='referral')

    user_info = query.from_user
    username = user_info.username or f"id{user_id}"
    mention = f"@{username}" if user_info.username else f"[пользователь](tg://user?id={user_id})"
    await query.edit_message_text(
        f"✅ Заявка #{request_id} создана!\n"
        f"Сумма: {amount} ⭐ списана с реферального баланса.\n"
        f"Ожидайте отправки {gift_count} подарков администратором."
    )

    for admin_id in ADMIN_IDS:
        try:
            await context.bot.send_message(
                admin_id,
                f"🔔 Новая реферальная заявка на вывод #{request_id}\n"
                f"Пользователь: {mention}\n"
                f"Сумма: {amount} ⭐\n"
                f"Подарки: {combo}"
            )
        except:
            pass

    return ConversationHandler.END

async def cancel_ref_withdraw_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("❌ Вывод отменён.")
    return ConversationHandler.END

# ---------- Админ-панель ----------
async def admin_panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        await query.edit_message_text("⛔ Доступ запрещён.")
        return
    text = "👑 Админ-панель AstralBet"
    keyboard = [
        [InlineKeyboardButton("📊 Статистика", callback_data="admin_stats"),
         InlineKeyboardButton("👥 Пользователи", callback_data="admin_users_info")],
        [InlineKeyboardButton("🔍 Поиск пользователя", callback_data="admin_find_user"),
         InlineKeyboardButton("📋 Все пользователи", callback_data="admin_all_users")],
        [InlineKeyboardButton("💰 Выводы (игровые)", callback_data="admin_withdrawals"),
         InlineKeyboardButton("🎁 Промокоды", callback_data="admin_promo")],
        [InlineKeyboardButton("➕ Создать промокод", callback_data="admin_create_promo"),
         InlineKeyboardButton("🗑️ Удалить промокод", callback_data="admin_delete_promo")],
        [InlineKeyboardButton("👥 Реферальные выводы", callback_data="admin_ref_withdrawals")],
        [InlineKeyboardButton("📋 Логи", callback_data="admin_logs"),
         InlineKeyboardButton("🔙 Профиль", callback_data="profile")]
    ]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    total_users = await db.get_total_users(db_conn)
    total_balance = await db.get_total_balance(db_conn)
    total_deposited = await db.get_total_deposited(db_conn)
    total_games = await db.get_total_games(db_conn)
    total_wins = await db.get_total_wins(db_conn)
    text = (
        f"📊 Статистика\n\n"
        f"Пользователей: {total_users}\n"
        f"Баланс всего: {round(total_balance,1)} ⭐\n"
        f"Пополнено: {round(total_deposited,1)} ⭐\n"
        f"Игр: {total_games}\n"
        f"Побед: {total_wins}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_users_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "👥 Управление пользователями\n\n"
        "Используйте команды:\n"
        "/addbalance <user_id> <amount>\n"
        "/setbalance <user_id> <amount>\n"
        "/ban <user_id> <причина>\n"
        "/unban <user_id>\n"
        "/mute <user_id> <минуты> <причина>\n"
        "/unmute <user_id>\n"
        "/warn <user_id> <причина>\n"
        "/unwarn <user_id>\n"
        "/vip <user_id> <дни>\n"
        "/unvip <user_id>"
    )
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    requests = await db.get_pending_withdrawals(db_conn, source='balance')
    if not requests:
        text = "Нет ожидающих заявок."
    else:
        text = "📤 Заявки на вывод (игровой баланс):\n\n"
        for req in requests:
            combo = json.loads(req['combination'])
            combo_text = ", ".join([f"{cnt}x{val}⭐" for val, cnt in combo.items()])
            text += f"ID: {req['id']}\nПользователь: {req['user_id']}\nСумма: {req['amount']} ⭐\nСостав: {combo_text}\nДата: {req['created_at'][:16]}\n\n"
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_ref_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    requests = await db.get_pending_withdrawals(db_conn, source='referral')
    if not requests:
        text = "Нет ожидающих реферальных заявок."
    else:
        text = "👥 Заявки на вывод (реферальный баланс):\n\n"
        for req in requests:
            combo = json.loads(req['combination'])
            combo_text = ", ".join([f"{cnt}x{val}⭐" for val, cnt in combo.items()])
            text += f"ID: {req['id']}\nПользователь: {req['user_id']}\nСумма: {req['amount']} ⭐\nСостав: {combo_text}\nДата: {req['created_at'][:16]}\n\n"
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_promo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    promos = await db.get_all_promo_codes(db_conn)
    if not promos:
        text = "Промокодов нет."
    else:
        text = "🎁 Промокоды:\n\n"
        for p in promos[:10]:
            used = len(json.loads(p['used_by']))
            text += f"Код: {p['code']}\nСумма: {p['amount']} ⭐\nОсталось: {p['uses_left']}\nИсп.: {used}\n\n"
        if len(promos) > 10:
            text += f"... и ещё {len(promos)-10}"
    keyboard = [[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    logs = await db.get_recent_logs(db_conn, limit=10)
    if not logs:
        text = "Логи пусты."
    else:
        text = "📋 Последние логи:\n\n"
        for log in logs:
            text += f"[{log['timestamp'][:16]}] {log['action']} - admin:{log['admin_id']} target:{log['target_id']} {log['details']}\n"
    keyboard = [[InlineKeyboardButton("🗑️ Очистить", callback_data="admin_clear_logs"),
                 InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_clear_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    db_conn = context.bot_data['db']
    await db.clear_logs_db(db_conn)
    await query.edit_message_text("✅ Логи очищены.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]
    ]))

async def admin_find_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    # Сбросим другие состояния, чтобы сообщение точно попало сюда
    context.user_data.clear()
    await query.edit_message_text("🔍 Введите ID или @username пользователя:",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")]]))
    return WAITING_SEARCH_USER

async def admin_find_user_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END
    db_conn = context.bot_data['db']
    query_text = update.message.text.strip()
    target = None
    try:
        target_id = int(query_text)
        target = await db.get_user(db_conn, target_id)
    except ValueError:
        target = await db.get_user_by_username(db_conn, query_text)
    if not target:
        await update.message.reply_text("❌ Пользователь не найден.")
        return ConversationHandler.END
    username = target['username'] or "нет"
    info = (
        f"👤 Пользователь: @{username}\n"
        f"🆔 ID: {target['user_id']}\n"
        f"💰 Баланс: {round(target['game_balance'], 1)} ⭐\n"
        f"🎮 Игр: {target['total_games']} | Побед: {target['total_wins']}\n"
        f"📅 Регистрация: {target['registration_date'][:10]}\n"
        f"🔥 Серия побед: {target['win_streak']} (макс: {target['max_win_streak']})\n"
        f"🎉 Мега-выигрышей: {target['mega_wins_count']}\n"
        f"💳 Пополнено: {target['total_deposited']} ⭐\n"
        f"👥 Рефералов: {target['referrals_count']}"
    )
    await update.message.reply_text(info)
    return ConversationHandler.END

async def admin_all_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    db_conn = context.bot_data['db']
    rows = await (await db_conn.execute("SELECT user_id, username, game_balance FROM users LIMIT 50")).fetchall()
    if not rows:
        text = "Нет пользователей."
    else:
        text = "👥 Список пользователей (первые 50):\n\n"
        for row in rows:
            uname = row['username'] or f"id{row['user_id']}"
            text += f"@{uname} | ID: {row['user_id']} | Баланс: {round(row['game_balance'],1)} ⭐\n"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Админ-панель", callback_data="admin_panel")]]))

# ---------- Создание и удаление промокодов ----------
async def admin_create_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text("Введите сумму промокода:",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")]]))
    return WAITING_PROMO_AMOUNT

async def admin_create_promo_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text)
        if not (PROMO_CONFIG['min_amount'] <= amount <= PROMO_CONFIG['max_amount']):
            await update.message.reply_text(f"Сумма должна быть от {PROMO_CONFIG['min_amount']} до {PROMO_CONFIG['max_amount']}")
            return WAITING_PROMO_AMOUNT
    except ValueError:
        await update.message.reply_text("Введите целое число.")
        return WAITING_PROMO_AMOUNT
    context.user_data['promo_amount'] = amount
    await update.message.reply_text("Введите количество использований:")
    return WAITING_PROMO_USES

async def admin_create_promo_uses(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uses = int(update.message.text)
        if uses < 1:
            await update.message.reply_text("Введите положительное число.")
            return WAITING_PROMO_USES
    except ValueError:
        await update.message.reply_text("Введите целое число.")
        return WAITING_PROMO_USES
    amount = context.user_data['promo_amount']
    db_conn = context.bot_data['db']
    code = f"PROMO{random.randint(10000,99999)}"
    await db.create_promo_code_db(db_conn, code, amount, uses, update.effective_user.id)
    await db.log_admin_action(db_conn, update.effective_user.id, "promo_create", details=f"код: {code}, сумма: {amount}, исп.: {uses}")
    await update.message.reply_text(f"✅ Промокод создан: {code}\nСумма: {amount} ⭐\nИспользований: {uses}")
    return ConversationHandler.END

async def admin_delete_promo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not is_admin(query.from_user.id):
        return
    await query.edit_message_text("🗑️ Введите код промокода для удаления:",
                                  reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Отмена", callback_data="admin_panel")]]))
    return WAITING_DELETE_PROMO

async def admin_delete_promo_execute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return ConversationHandler.END
    code = update.message.text.strip().upper()
    db_conn = context.bot_data['db']
    await db.delete_promo_code_db(db_conn, code)
    await db.log_admin_action(db_conn, user_id, "promo_delete", details=f"код: {code}")
    await update.message.reply_text(f"✅ Промокод {code} удалён.")
    return ConversationHandler.END

# ---------- Админские команды ----------
async def promo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not context.args:
        await update.message.reply_text("Используйте: /promo <код>")
        return
    code = context.args[0].upper()
    db_conn = context.bot_data['db']
    success = await db.use_promo_code_db(db_conn, code, user_id)
    if success:
        promo = await db.get_promo_code(db_conn, code)
        await update.message.reply_text(f"✅ Промокод активирован! Начислено {promo['amount']} ⭐")
    else:
        await update.message.reply_text("❌ Недействительный или уже использованный промокод.")

async def add_balance_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /addbalance <user_id> <amount>")
        return
    db_conn = context.bot_data['db']
    await db.update_user_balance(db_conn, target_id, amount)
    await db.log_admin_action(db_conn, user_id, "add_balance", target_id, f"сумма: {amount}")
    await update.message.reply_text(f"✅ Баланс пользователя {target_id} пополнен на {amount} ⭐")

async def set_balance_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        amount = float(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /setbalance <user_id> <amount>")
        return
    db_conn = context.bot_data['db']
    await db.set_user_balance(db_conn, target_id, amount)
    await db.log_admin_action(db_conn, user_id, "set_balance", target_id, f"новый баланс: {amount}")
    await update.message.reply_text(f"✅ Баланс пользователя {target_id} установлен на {amount} ⭐")

async def ban_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        reason = ' '.join(context.args[1:]) or "Не указана"
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /ban <user_id> <причина>")
        return
    db_conn = context.bot_data['db']
    await db.add_ban(db_conn, target_id, reason, user_id)
    await db.log_admin_action(db_conn, user_id, "ban", target_id, reason)
    await update.message.reply_text(f"✅ Пользователь {target_id} забанен. Причина: {reason}")

async def unban_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /unban <user_id>")
        return
    db_conn = context.bot_data['db']
    await db.remove_ban(db_conn, target_id)
    await db.log_admin_action(db_conn, user_id, "unban", target_id)
    await update.message.reply_text(f"✅ Пользователь {target_id} разбанен.")

async def mute_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        minutes = int(context.args[1])
        reason = ' '.join(context.args[2:]) or "Не указана"
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /mute <user_id> <минуты> <причина>")
        return
    until = (datetime.datetime.now() + datetime.timedelta(minutes=minutes)).isoformat()
    db_conn = context.bot_data['db']
    await db.add_mute(db_conn, target_id, until, reason, user_id)
    await db.log_admin_action(db_conn, user_id, "mute", target_id, f"{minutes} мин: {reason}")
    await update.message.reply_text(f"✅ Пользователь {target_id} замучен на {minutes} мин. Причина: {reason}")

async def unmute_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /unmute <user_id>")
        return
    db_conn = context.bot_data['db']
    await db.remove_mute(db_conn, target_id)
    await db.log_admin_action(db_conn, user_id, "unmute", target_id)
    await update.message.reply_text(f"✅ Пользователь {target_id} размучен.")

async def warn_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        reason = ' '.join(context.args[1:]) or "Не указана"
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /warn <user_id> <причина>")
        return
    db_conn = context.bot_data['db']
    await db.add_warning(db_conn, target_id, reason, user_id)
    await db.log_admin_action(db_conn, user_id, "warn", target_id, reason)
    await update.message.reply_text(f"⚠️ Пользователь {target_id} получил предупреждение: {reason}")

async def unwarn_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /unwarn <user_id>")
        return
    db_conn = context.bot_data['db']
    success = await db.remove_last_warning(db_conn, target_id)
    if success:
        await db.log_admin_action(db_conn, user_id, "unwarn", target_id)
        await update.message.reply_text(f"✅ Предупреждение снято с {target_id}.")
    else:
        await update.message.reply_text("❌ Нет предупреждений.")

async def vip_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
        days = int(context.args[1])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /vip <user_id> <дни>")
        return
    until = (datetime.datetime.now() + datetime.timedelta(days=days)).isoformat()
    db_conn = context.bot_data['db']
    await db.set_vip(db_conn, target_id, until, user_id)
    await db.log_admin_action(db_conn, user_id, "vip", target_id, f"{days} дней")
    await update.message.reply_text(f"⭐ Пользователю {target_id} выдан VIP на {days} дней.")

async def unvip_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        target_id = int(context.args[0])
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /unvip <user_id>")
        return
    db_conn = context.bot_data['db']
    await db.remove_vip(db_conn, target_id)
    await db.log_admin_action(db_conn, user_id, "unvip", target_id)
    await update.message.reply_text(f"✅ VIP снят с {target_id}.")

async def promo_create_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    db_conn = context.bot_data['db']
    try:
        amount = int(context.args[0])
        uses = int(context.args[1])
        broadcast_text = ' '.join(context.args[2:]) if len(context.args) > 2 else None
    except (IndexError, ValueError):
        await update.message.reply_text("Используйте: /promo_create <amount> <uses> [текст рассылки]")
        return
    if amount < PROMO_CONFIG['min_amount'] or amount > PROMO_CONFIG['max_amount']:
        await update.message.reply_text(f"Сумма должна быть от {PROMO_CONFIG['min_amount']} до {PROMO_CONFIG['max_amount']}")
        return
    code = f"PROMO{random.randint(10000,99999)}"
    await db.create_promo_code_db(db_conn, code, amount, uses, user_id)
    await db.log_admin_action(db_conn, user_id, "promo_create", details=f"код: {code}, сумма: {amount}, исп.: {uses}")
    await update.message.reply_text(f"✅ Промокод создан: {code} (сумма {amount}, использований {uses})")
    if broadcast_text:
        rows = await (await db_conn.execute("SELECT user_id FROM users")).fetchall()
        msg = f"🚀 Новый промокод: {code}\nСумма: {amount} ⭐\n{broadcast_text}"
        for u in rows:
            try:
                await context.bot.send_message(u['user_id'], msg)
                await asyncio.sleep(0.05)
            except:
                pass

async def promo_delete_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    try:
        code = context.args[0].upper()
    except IndexError:
        await update.message.reply_text("Используйте: /promo_delete <код>")
        return
    db_conn = context.bot_data['db']
    await db.delete_promo_code_db(db_conn, code)
    await db.log_admin_action(db_conn, user_id, "promo_delete", details=f"код: {code}")
    await update.message.reply_text(f"✅ Промокод {code} удалён.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    db_conn = context.bot_data['db']
    total_users = await db.get_total_users(db_conn)
    total_balance = await db.get_total_balance(db_conn)
    total_deposited = await db.get_total_deposited(db_conn)
    total_games = await db.get_total_games(db_conn)
    total_wins = await db.get_total_wins(db_conn)
    text = (
        f"📊 Статистика\n"
        f"Пользователей: {total_users}\n"
        f"Баланс всего: {round(total_balance,1)} ⭐\n"
        f"Пополнено: {round(total_deposited,1)} ⭐\n"
        f"Игр: {total_games}\n"
        f"Побед: {total_wins}"
    )
    await update.message.reply_text(text)

async def system_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    import psutil
    process = psutil.Process()
    memory = process.memory_info()
    text = (
        "⚙️ Системная информация\n"
        f"PID: {process.pid}\n"
        f"Память: {memory.rss // 1024 // 1024} MB\n"
        f"CPU: {psutil.cpu_percent(interval=1)}%\n"
        f"Диск: {psutil.disk_usage('/').percent}%"
    )
    await update.message.reply_text(text)

async def clear_logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    db_conn = context.bot_data['db']
    await db.clear_logs_db(db_conn)
    await db.log_admin_action(db_conn, user_id, "clear_logs")
    await update.message.reply_text("✅ Логи очищены.")

async def reset_weekly_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("⛔ Доступ запрещён.")
        return
    db_conn = context.bot_data['db']
    await db_conn.execute("UPDATE activity SET weekly_streak_days=0, weekly_total_bets=0, weekly_total_games=0, daily_games_count=0")
    await db_conn.commit()
    await db.log_admin_action(db_conn, user_id, "reset_weekly")
    await update.message.reply_text("✅ Недельные данные сброшены у всех пользователей.")

# ---------- MAIN ----------
def main():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(db.init_db())
    db_conn = loop.run_until_complete(aiosqlite.connect(db.DB_PATH))
    db_conn.row_factory = aiosqlite.Row
    loop.run_until_complete(db_conn.execute("PRAGMA journal_mode=WAL"))
    loop.run_until_complete(db_conn.execute("PRAGMA foreign_keys=ON"))

    application = Application.builder().token(BOT_TOKEN).build()
    application.bot_data['db'] = db_conn
    application.bot_data['in_game'] = set()

    async def set_bot_commands(app):
        commands = [
            ("start", "Начать"),
            ("help", "Помощь"),
            ("profile", "Профиль"),
            ("play", "Игры"),
            ("deposit", "Пополнить"),
            ("withdraw", "Вывести"),
            ("promo", "Активировать промокод"),
            ("bet", "Изменить ставку"),
            ("activity", "Активность")
        ]
        await app.bot.set_my_commands(commands)
    loop.run_until_complete(set_bot_commands(application))

    # Регистрация обработчиков
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("play", play_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("profile", profile))
    application.add_handler(CommandHandler("activity", activity_command))
    application.add_handler(CommandHandler("bet", bet_command))
    application.add_handler(CommandHandler("promo", promo_command))
    application.add_handler(CommandHandler("deposit", deposit_command))

    application.add_handler(CallbackQueryHandler(profile, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(play_games_callback, pattern="^play_games$"))
    application.add_handler(CallbackQueryHandler(change_bet_callback, pattern="^change_bet$"))
    application.add_handler(CallbackQueryHandler(handle_game_selection, pattern="^play_"))
    application.add_handler(CallbackQueryHandler(deposit_command, pattern="^deposit$"))
    application.add_handler(CallbackQueryHandler(buy_callback, pattern="^buy_"))
    application.add_handler(CallbackQueryHandler(referral_system_callback, pattern="^referral_system$"))
    application.add_handler(CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$"))
    application.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    application.add_handler(CallbackQueryHandler(admin_users_info, pattern="^admin_users_info$"))
    application.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    application.add_handler(CallbackQueryHandler(admin_ref_withdrawals, pattern="^admin_ref_withdrawals$"))
    application.add_handler(CallbackQueryHandler(admin_promo, pattern="^admin_promo$"))
    application.add_handler(CallbackQueryHandler(admin_logs, pattern="^admin_logs$"))
    application.add_handler(CallbackQueryHandler(admin_clear_logs_callback, pattern="^admin_clear_logs$"))
    application.add_handler(CallbackQueryHandler(admin_find_user_start, pattern="^admin_find_user$"))
    application.add_handler(CallbackQueryHandler(admin_all_users, pattern="^admin_all_users$"))
    # Новые кнопки реферальной системы
    application.add_handler(CallbackQueryHandler(ref_to_balance_callback, pattern="^ref_to_balance$"))
    application.add_handler(CallbackQueryHandler(ref_withdraw_start_callback, pattern="^ref_withdraw_start$"))

    # ConversationHandler: кастомное пополнение
    conv_custom = ConversationHandler(
        entry_points=[CallbackQueryHandler(custom_deposit_callback, pattern="^custom_deposit$")],
        states={
            WAITING_CUSTOM_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_input)],
            CONFIRM_CUSTOM_AMOUNT: [CallbackQueryHandler(confirm_custom_payment, pattern="^confirm_custom$"),
                                    CallbackQueryHandler(cancel_custom, pattern="^cancel_custom$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_custom)],
    )
    application.add_handler(conv_custom)

    # ConversationHandler: вывод с игрового баланса
    conv_withdraw = ConversationHandler(
        entry_points=[
            CommandHandler("withdraw", withdraw_start),
            CallbackQueryHandler(withdraw_start, pattern="^withdraw$")
        ],
        states={
            WAITING_WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_input)],
            CONFIRM_WITHDRAW: [CallbackQueryHandler(confirm_withdraw_callback, pattern="^confirm_withdraw$"),
                               CallbackQueryHandler(cancel_withdraw_callback, pattern="^cancel_withdraw$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_withdraw_callback)],
    )
    application.add_handler(conv_withdraw)

    # ConversationHandler: вывод с реферального баланса
    conv_ref_withdraw = ConversationHandler(
        entry_points=[CallbackQueryHandler(ref_withdraw_start_callback, pattern="^ref_withdraw_start$")],
        states={
            WAITING_REF_WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, ref_withdraw_amount_input)],
            CONFIRM_REF_WITHDRAW: [CallbackQueryHandler(confirm_ref_withdraw_callback, pattern="^confirm_ref_withdraw$"),
                                   CallbackQueryHandler(cancel_ref_withdraw_callback, pattern="^cancel_ref_withdraw$")]
        },
        fallbacks=[CommandHandler("cancel", cancel_ref_withdraw_callback)],
    )
    application.add_handler(conv_ref_withdraw)

    # ConversationHandler: поиск пользователя
    conv_search = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_find_user_start, pattern="^admin_find_user$")],
        states={
            WAITING_SEARCH_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_find_user_execute)]
        },
        fallbacks=[CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$")],
    )
    application.add_handler(conv_search)

    # ConversationHandler: создание промокода
    conv_promo_create = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_create_promo_start, pattern="^admin_create_promo$")],
        states={
            WAITING_PROMO_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_promo_amount)],
            WAITING_PROMO_USES: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_create_promo_uses)]
        },
        fallbacks=[CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$")],
    )
    application.add_handler(conv_promo_create)

    # ConversationHandler: удаление промокода
    conv_promo_delete = ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_delete_promo_start, pattern="^admin_delete_promo$")],
        states={
            WAITING_DELETE_PROMO: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_delete_promo_execute)]
        },
        fallbacks=[CallbackQueryHandler(admin_panel_callback, pattern="^admin_panel$")],
    )
    application.add_handler(conv_promo_delete)

    application.add_handler(PreCheckoutQueryHandler(pre_checkout))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))

    application.add_handler(MessageHandler(filters.Dice.ALL, dice_message_handler))

    # Админские команды
    application.add_handler(CommandHandler("addbalance", add_balance_admin))
    application.add_handler(CommandHandler("setbalance", set_balance_admin))
    application.add_handler(CommandHandler("ban", ban_admin))
    application.add_handler(CommandHandler("unban", unban_admin))
    application.add_handler(CommandHandler("mute", mute_admin))
    application.add_handler(CommandHandler("unmute", unmute_admin))
    application.add_handler(CommandHandler("warn", warn_admin))
    application.add_handler(CommandHandler("unwarn", unwarn_admin))
    application.add_handler(CommandHandler("vip", vip_admin))
    application.add_handler(CommandHandler("unvip", unvip_admin))
    application.add_handler(CommandHandler("promo_create", promo_create_admin))
    application.add_handler(CommandHandler("promo_delete", promo_delete_admin))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("system_info", system_info_command))
    application.add_handler(CommandHandler("clear_logs", clear_logs_command))
    application.add_handler(CommandHandler("reset_weekly", reset_weekly_command))

    print("🤖 AstralBet запущен!")
    application.run_polling()

if __name__ == "__main__":
    main()

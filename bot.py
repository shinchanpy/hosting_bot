import os
import sys
import re
import time
import shutil
import signal
import psutil
import sqlite3
import logging
import zipfile
import tempfile
import threading
import subprocess
import atexit
import hashlib
import inspect
import venv
import copy
from pathlib import Path, PurePosixPath
from html import escape
from datetime import datetime, timedelta

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
os.environ["PYTHONUNBUFFERED"] = "1"

import telebot
from telebot import types
from flask import Flask

flask_app = Flask(__name__)


@flask_app.route("/")
def home():
    return "⚡ File Hosting Bot Runner Active ⚡"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)


def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    logging.info("Flask Keep-Alive server started.")


TOKEN = os.environ.get(
    "TELEGRAM_BOT_TOKEN", "9265039368:AAH0pkucxjBYAKaqGF0aQtVx4_aqCLGoxio"
).strip()
OWNER_ID = 8357719069
ADMIN_ID = 8357719069
YOUR_USERNAME = "@vishaldied"
UPDATE_CHANNEL = "t.me/vishaldied"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_BOTS_DIR = os.path.join(BASE_DIR, "upload_bots")
INF_DIR = os.path.join(BASE_DIR, "inf")
DATABASE_PATH = os.path.join(INF_DIR, "bot_data.db")
RUNTIMES_DIR = os.path.join(INF_DIR, "runtimes")
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_BATCH_BYTES = 100 * 1024 * 1024
MAX_BATCH_FILES = 1000

os.makedirs(UPLOAD_BOTS_DIR, exist_ok=True)
os.makedirs(INF_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

bot = None

callback_context = threading.local()
PAGE_SIZE = 8
MENU_ACTIONS = {
    "upload script": "btn_upload",
    "my scripts": "btn_my_scripts",
    "help": "btn_help",
    "my account": "btn_account",
    "support": "btn_support",
    "request access": "btn_support",
    "admin panel": "btn_admin_panel",
    "back to dashboard": "btn_back_main",
}
FILE_ACTION_PREFIXES = (
    "mng_",
    "manage_",
    "start_",
    "stop_",
    "ask_r_",
    "ask_restart_",
    "r_prev_",
    "do_restart_prev_",
    "r_fresh_",
    "do_restart_fresh_",
    "t_ar_",
    "toggle_ar_",
    "logs_",
    "dlog_",
    "downlog_",
    "inp_",
    "send_inp_",
    "del_",
    "confirm_del_",
    "appr_",
    "rej_",
    "dscr_",
    "adm_kill_",
    "confirm_kill_",
)

# -------------------------------------------------------------
# PREMIUM ANIMATED EMOJI MAPS & FALLBACKS
# -------------------------------------------------------------
_EMOJI_MAP: dict[str, tuple[str, str]] = {
    "check":     ("5350722806281676158", "✅"),
    "cross":     ("5834895792409677476", "❌"),
    "warn":      ("5420323339723881652", "⚠️"),
    "info":      ("5334544901428229844", "ℹ️"),
    "bolt":      ("5456140674028019486", "⚡"),
    "hourglass": ("6138579366403119002", "⏳"),
    "fire":      ("5042136067558343759", "🔥"),
    "pin":       ("5251753277879511172", "📌"),
    "phone":     ("6325330308279308485", "📱"),
    "paperclip": ("5888584382553265934", "📎"),
    "key":       ("5420094143089111506", "🔑"),
    "id":        ("5841276284155467413", "🆔"),
    "person":    ("5969740061648884524", "👤"),
    "megaphone": ("5800920921766104807", "📢"),
    "card":      ("5902056028513505203", "💳"),
    "clock":     ("5846127793313681804", "⏳"),
    "reset":     ("5017470156276761427", "🔄"),
    "gift":      ("5355193051193059834", "🎁"),
    "unlock":    ("5017470156276761427", "🔓"),
    "doc":       ("5017470156276761427", "📄"),
    "edit":      ("5332724926216428039", "✏️"),
    "users":     ("5388583647370565067", "👥"),
    "stats":     ("5231200819986047254", "📊"),
    "note":      ("5444856076954520455", "📝"),
    "back":      ("6159071084869066737", "🔙"),
}

BUTTON_CUSTOM_EMOJI_IDS: dict[str, str] = {
    "action":        "5456140674028019486",   # ⚡
    "positive":      "5350722806281676158",   # ✅
    "negative":      "5834895792409677476",   # ❌
    "warning":       "5420323339723881652",   # ⚠️
    "info":          "5334544901428229844",   # ℹ️
    "phone":         "6325330308279308485",   # 📱
    "paperclip":     "5888584382553265934",   # 📎
    "card":          "5902056028513505203",   # 💳
    "help":          "5449814015402337207",   # ❓
    "person":        "5969740061648884524",   # 👤
    "back":          "6159071084869066737",   # 🔙
    "reset":         "5017470156276761427",   # 🔄
    "join_channel":  "5951969256504562067",
    "contact_owner": "5969740061648884524",
}

FALLBACK_EMOJIS: dict[str, str] = {
    "positive": "✅",
    "negative": "❌",
    "warning":  "⚠️",
    "info":     "ℹ️",
    "action":   "⚡",
    "back":     "🔙",
    "url":      "🔗",
}

def emo(key: str) -> str:
    """Returns Telegram HTML custom emoji tag with standard emoji as fallback.
    e.g. <tg-emoji emoji-id="5350722806281676158">✅</tg-emoji>
    """
    if key in _EMOJI_MAP:
        emoji_id, fallback = _EMOJI_MAP[key]
        return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'
    return FALLBACK_EMOJIS.get(key, "🔹")


def format_size(num_bytes: int) -> str:
    """Formats raw bytes into clean human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.1f} MB"


BUTTON_FIELDS = inspect.signature(types.InlineKeyboardButton).parameters
BUTTON_THEMES = (
    (("confirm_del_", "del_", "rej_", "dscr_"), "delete", "🗑️", "danger"),
    (("confirm_kill_", "adm_kill_", "stop_"), "stop", "⏹️", "danger"),
    (("adm_revoke",), "lock", "🔒", "danger"),
    (("adm_confirm_",), "confirm", "✅", "success"),
    (("btn_upload",), "upload", "📤", "success"),
    (("start_",), "start", "▶️", "success"),
    (
        ("ask_r_", "ask_restart_", "r_prev_", "r_fresh_", "do_restart_"),
        "restart",
        "🔄",
        "success",
    ),
    (("t_ar_", "toggle_ar_"), "auto_restart", "🔁", "primary"),
    (("appr_", "adm_grant", "setdays_"), "grant", "✨", "success"),
    (("dlog_", "downlog_"), "download", "📥", "primary"),
    (("logs_",), "logs", "📜", "primary"),
    (("inp_", "send_inp_"), "input", "⌨️", "primary"),
    (("btn_back_main",), "home", "🏠", "primary"),
    (("btn_my_scripts", "scripts_", "mng_", "manage_"), "scripts", "📂", "primary"),
    (("btn_account",), "account", "👤", "primary"),
    (("btn_help",), "help", "💡", "primary"),
    (("btn_support",), "support", "💬", "primary"),
    (("btn_admin_panel",), "admin", "🛡️", "primary"),
    (("adm_live",), "processes", "📊", "primary"),
    (("adm_limit", "setlimit_"), "limit", "🎛️", "primary"),
    (("adm_user",), "search", "🔎", "primary"),
    (("adm_broadcast",), "broadcast", "📣", "primary"),
)

BUTTON_ROLE_MAP = {
    "delete": ("negative", "🗑️", "danger"),
    "stop": ("negative", "⏹️", "danger"),
    "lock": ("negative", "🔒", "danger"),
    "confirm": ("positive", "✅", "success"),
    "upload": ("action", "📤", "success"),
    "start": ("positive", "▶️", "success"),
    "restart": ("reset", "🔄", "success"),
    "auto_restart": ("reset", "🔁", "primary"),
    "grant": ("positive", "✨", "success"),
    "download": ("paperclip", "📥", "primary"),
    "logs": ("info", "📜", "primary"),
    "input": ("action", "⌨️", "primary"),
    "home": ("back", "🏠", "primary"),
    "scripts": ("action", "📂", "primary"),
    "account": ("person", "👤", "primary"),
    "help": ("help", "💡", "primary"),
    "support": ("contact_owner", "💬", "primary"),
    "admin": ("action", "🛡️", "primary"),
    "processes": ("info", "📊", "primary"),
    "limit": ("action", "🎛️", "primary"),
    "search": ("info", "🔎", "primary"),
    "broadcast": ("action", "📣", "primary"),
}


def ui_button(text, callback_data=None, url=None, style=None):
    """Generates an InlineKeyboardButton.
    When custom emoji is supported, icon_custom_emoji_id is used and text remains clean.
    Normal emoji icons are only prepended in fallback mode.
    """
    if callback_data is not None and not 1 <= len(callback_data.encode("utf-8")) <= 64:
        raise ValueError("Button callback data must be 1-64 bytes.")

    role = "action"
    icon = "🔹"
    default_style = "primary"
    emoji_key = "action"

    for prefixes, theme_role, theme_icon, theme_style in BUTTON_THEMES:
        if (callback_data or "").startswith(prefixes):
            role, icon, default_style = theme_role, theme_icon, theme_style
            if role in BUTTON_ROLE_MAP:
                emoji_key = BUTTON_ROLE_MAP[role][0]
            break

    label = re.sub(r"^[^\w]+", "", text).strip() or "Open"
    label_lower = label.lower()
    first_word = label_lower.split()[0] if label_lower else ""

    if default_style != "danger" and first_word in (
        "back",
        "cancel",
        "previous",
        "next",
        "refresh",
    ):
        role = first_word
        icon_dict = {
            "back": ("back", "↩️"),
            "cancel": ("negative", "✖️"),
            "previous": ("back", "⬅️"),
            "next": ("action", "➡️"),
            "refresh": ("reset", "🔄"),
        }
        emoji_key, icon = icon_dict[role]
        default_style = "primary"
    elif url:
        emoji_key, icon = "contact_owner", "💬"
    elif label_lower.startswith("running |"):
        emoji_key, icon, default_style = "positive", "🟢", "success"
    elif label_lower.startswith("stopped |"):
        emoji_key, icon, default_style = "negative", "⏸️", "primary"

    custom_emoji_id = BUTTON_CUSTOM_EMOJI_IDS.get(emoji_key, "")
    fallback_icon = FALLBACK_EMOJIS.get(emoji_key, icon)

    use_custom_emoji = (
        "icon_custom_emoji_id" in BUTTON_FIELDS
        and bool(re.fullmatch(r"[1-9][0-9]*", custom_emoji_id))
    )

    if use_custom_emoji:
        # Custom emoji icon is used; keep text clean without normal emoji
        display_text = label
        options = {"text": display_text, "callback_data": callback_data, "url": url}
        options["icon_custom_emoji_id"] = custom_emoji_id
    else:
        # Fallback mode: use normal emoji icon in button text
        display_text = f"{fallback_icon} {label}"
        options = {"text": display_text, "callback_data": callback_data, "url": url}

    if len(display_text) > 48:
        display_text = display_text[:47].rstrip() + "…"
        options["text"] = display_text

    if "style" in BUTTON_FIELDS:
        options["style"] = style or default_style

    return types.InlineKeyboardButton(**options)


def strip_custom_emojis_from_markup(markup):
    """Safely removes icon_custom_emoji_id and restores normal fallback emoji into button text if Telegram rejects custom emoji buttons."""
    if not markup:
        return markup
    try:
        new_markup = copy.deepcopy(markup)
        keyboard = getattr(new_markup, "keyboard", None)
        if keyboard:
            for row in keyboard:
                for btn in row:
                    cid = getattr(btn, "icon_custom_emoji_id", None)
                    if cid:
                        btn.icon_custom_emoji_id = None
                        fb = None
                        for k, eid in BUTTON_CUSTOM_EMOJI_IDS.items():
                            if eid == str(cid):
                                fb = FALLBACK_EMOJIS.get(k)
                                break
                        if not fb:
                            fb = "🔹"
                        if not btn.text.startswith(fb):
                            btn.text = f"{fb} {btn.text}"
        return new_markup
    except Exception:
        return markup


def answer_callback(callback_query_id, text=None, show_alert=False):
    if getattr(callback_context, "answered_id", None) == callback_query_id:
        return
    callback_context.answered_id = callback_query_id
    try:
        return bot.answer_callback_query(
            callback_query_id, text=text[:200] if text else None, show_alert=show_alert
        )
    except Exception:
        logger.warning("Could not acknowledge callback query.")


def safe_send_message(chat_id, text, **kwargs):
    """Send message with fallback for custom emoji buttons if rejected by Telegram API."""
    markup = kwargs.get("reply_markup")
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except telebot.apihelper.ApiTelegramException as error:
        err_msg = str(error).lower()
        if ("custom_emoji" in err_msg or "button" in err_msg) and markup:
            kwargs["reply_markup"] = strip_custom_emojis_from_markup(markup)
            return bot.send_message(chat_id, text, **kwargs)
        raise


def edit_panel(text, **kwargs):
    markup = kwargs.get("reply_markup")
    try:
        return bot.edit_message_text(text, **kwargs)
    except telebot.apihelper.ApiTelegramException as error:
        err_msg = str(error).lower()
        if "message is not modified" in err_msg:
            return None
        if ("custom_emoji" in err_msg or "button" in err_msg) and markup:
            kwargs["reply_markup"] = strip_custom_emojis_from_markup(markup)
            try:
                return bot.edit_message_text(text, **kwargs)
            except Exception:
                pass
        if (
            "message to edit not found" in err_msg
            or "message can't be edited" in err_msg
        ):
            chat_id = kwargs.get("chat_id")
            if chat_id:
                return safe_send_message(
                    chat_id, text, reply_markup=kwargs.get("reply_markup")
                )
        raise


def cancel_pending_input(chat_id):
    pending_inputs.pop(chat_id, None)
    bot.clear_step_handler_by_chat_id(chat_id)


def parse_user_id(text):
    value = int((text or "").strip())
    if not 0 < value < 2**52:
        raise ValueError("Invalid Telegram user ID.")
    return value


def confirm_admin_action(message, action, payload):
    nonce = os.urandom(8).hex()
    admin_states[message.chat.id] = {
        "nonce": nonce,
        "actor_id": message.from_user.id,
        "action": action,
        "payload": payload,
    }
    markup = types.InlineKeyboardMarkup()
    markup.row(
        ui_button(
            "Send broadcast" if action == "broadcast" else "Revoke access",
            callback_data=f"adm_confirm_{nonce}",
            style="success" if action == "broadcast" else "danger",
        ),
        ui_button("Cancel", callback_data="btn_admin_panel"),
    )
    title = f"{emo('megaphone')} Broadcast Preview" if action == "broadcast" else f"{emo('cross')} Revoke Access?"
    detail = (
        str(payload)
        if action == "broadcast"
        else f"User {payload}\nAll their running scripts will be stopped."
    )
    safe_send_message(
        message.chat.id,
        f"<b>{title}</b>\n<i>Review before confirming action</i>\n\n"
        f"<blockquote>{escape(detail)}</blockquote>",
        reply_markup=markup,
    )


def request_text_input(chat_id, actor_id, text, handler, *args, back="btn_back_main"):
    cancel_pending_input(chat_id)
    admin_states.pop(chat_id, None)
    request = {"actor_id": actor_id, "handler": handler, "args": args}
    pending_inputs[chat_id] = request
    markup = types.InlineKeyboardMarkup()
    markup.add(ui_button("Cancel", callback_data=back))
    message = safe_send_message(chat_id, text, reply_markup=markup)
    bot.register_next_step_handler(message, dispatch_text_input, request)


def dispatch_text_input(message, request):
    chat_id = message.chat.id
    if pending_inputs.get(chat_id) is not request:
        return
    if message.chat.type != "private" or message.from_user.id != request["actor_id"]:
        return
    text = message.text
    if not text:
        bot.reply_to(message, "Please send a text value, or /cancel.")
        bot.register_next_step_handler(message, dispatch_text_input, request)
        return
    if text.strip().lower() in ("/cancel", "/start", "/menu"):
        cancel_pending_input(chat_id)
        cmd_start(message)
        return
    if menu_action_from_text(text):
        handle_menu_message(message)
        return
    cancel_pending_input(chat_id)
    if request["handler"].__name__.startswith("admin_") and not is_admin(
        message.from_user.id
    ):
        bot.reply_to(message, "Admin access is required.")
        return
    request["handler"](message, *request["args"])


bot_scripts = {}
user_subscriptions = {}
user_files = {}
script_approvals = {}
active_users = set()
admin_ids = {OWNER_ID, ADMIN_ID}
pending_inputs = {}
admin_states = {}
user_workspace_locks = {}
upload_groups = {}
upload_groups_lock = threading.Lock()

file_registry = {}
file_registry_rev = {}


def get_file_id(user_id, file_name):
    key = (user_id, file_name)
    if key not in file_registry_rev:
        fid = (
            "f"
            + hashlib.blake2s(
                f"{user_id}:{file_name}".encode("utf-8"), digest_size=12
            ).hexdigest()
        )
        file_registry[fid] = key
        file_registry_rev[key] = fid
    return file_registry_rev[key]


def resolve_file_id(fid_val):
    target = file_registry.get(str(fid_val))
    if target and any(entry[0] == target[1] for entry in user_files.get(target[0], [])):
        return target
    return None


def parse_callback_target(data, prefixes):
    for pref in sorted(prefixes, key=len, reverse=True):
        if data.startswith(pref):
            rem = data[len(pref) :]
            target = resolve_file_id(rem)
            if target:
                return target
            if "_" in rem:
                parts = rem.split("_", 1)
                try:
                    uid = int(parts[0])
                    fn = parts[1]
                    if any(entry[0] == fn for entry in user_files.get(uid, [])):
                        return uid, fn
                except ValueError:
                    pass
            break
    return None, None


def init_db():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            """CREATE TABLE IF NOT EXISTS subscriptions
                     (user_id INTEGER PRIMARY KEY, expiry TEXT, script_limit INTEGER DEFAULT 1)"""
        )
        c.execute("""CREATE TABLE IF NOT EXISTS user_files
                     (user_id INTEGER, file_name TEXT, file_type TEXT,
                      auto_restart INTEGER DEFAULT 0, saved_inputs TEXT DEFAULT '',
                      is_approved INTEGER DEFAULT 1,
                      PRIMARY KEY (user_id, file_name))""")
        c.execute("""CREATE TABLE IF NOT EXISTS active_users
                     (user_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins
                     (user_id INTEGER PRIMARY KEY)""")

        c.execute("PRAGMA table_info(subscriptions)")
        cols = [col[1] for col in c.fetchall()]
        if "script_limit" not in cols:
            c.execute(
                "ALTER TABLE subscriptions ADD COLUMN script_limit INTEGER DEFAULT 1"
            )

        c.execute("PRAGMA table_info(user_files)")
        uf_cols = [col[1] for col in c.fetchall()]
        if "auto_restart" not in uf_cols:
            c.execute(
                "ALTER TABLE user_files ADD COLUMN auto_restart INTEGER DEFAULT 0"
            )
        if "saved_inputs" not in uf_cols:
            c.execute("ALTER TABLE user_files ADD COLUMN saved_inputs TEXT DEFAULT ''")
        if "is_approved" not in uf_cols:
            c.execute("ALTER TABLE user_files ADD COLUMN is_approved INTEGER DEFAULT 1")
        c.execute("UPDATE user_files SET is_approved = 1 WHERE is_approved = 0")

        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        if ADMIN_ID != OWNER_ID:
            c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (ADMIN_ID,))

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database init error: {e}", exc_info=True)


def load_data():
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()

        c.execute("SELECT user_id, expiry, script_limit FROM subscriptions")
        for user_id, expiry, limit in c.fetchall():
            try:
                user_subscriptions[user_id] = {
                    "expiry": datetime.fromisoformat(expiry),
                    "limit": limit if limit else 1,
                }
            except Exception:
                pass

        c.execute(
            "SELECT user_id, file_name, file_type, auto_restart, saved_inputs, is_approved FROM user_files"
        )
        for (
            user_id,
            file_name,
            file_type,
            auto_restart,
            saved_inputs,
            is_approved,
        ) in c.fetchall():
            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append((file_name, file_type))
            script_approvals[(user_id, file_name)] = (
                is_approved if is_approved is not None else 1
            )
            get_file_id(user_id, file_name)

        if os.path.exists(UPLOAD_BOTS_DIR):
            for entry in os.listdir(UPLOAD_BOTS_DIR):
                if entry.isdigit():
                    uid = int(entry)
                    user_dir = os.path.join(UPLOAD_BOTS_DIR, entry)
                    if os.path.isdir(user_dir):
                        for f in os.listdir(user_dir):
                            if f.endswith(".py"):
                                if uid not in user_files:
                                    user_files[uid] = []
                                if not any(
                                    existing[0] == f for existing in user_files[uid]
                                ):
                                    user_files[uid].append((f, "py"))
                                    c.execute(
                                        """INSERT OR IGNORE INTO user_files (user_id, file_name, file_type, auto_restart, saved_inputs, is_approved)
                                                 VALUES (?, ?, ?, 0, '', 1)""",
                                        (uid, f, "py"),
                                    )
                                    script_approvals[(uid, f)] = 1
                                get_file_id(uid, f)
        conn.commit()

        c.execute("SELECT user_id FROM active_users")
        active_users.update(uid for (uid,) in c.fetchall())

        c.execute("SELECT user_id FROM admins")
        admin_ids.update(uid for (uid,) in c.fetchall())

        conn.close()
        logger.info(
            f"Loaded {len(active_users)} users, {len(user_subscriptions)} subs, {len(admin_ids)} admins."
        )
    except Exception as e:
        logger.error(f"Error loading data: {e}", exc_info=True)


def is_owner(user_id):
    return user_id == OWNER_ID


def is_admin(user_id):
    return user_id in admin_ids or user_id == OWNER_ID


def is_unlimited_scripts(user_id):
    """Owner and Admins have unlimited script hosting capacity."""
    return user_id == OWNER_ID or is_admin(user_id)


def has_active_access(user_id):
    if is_admin(user_id):
        return True
    sub = user_subscriptions.get(user_id)
    if sub and sub.get("expiry") and sub["expiry"] > datetime.now():
        return True
    return False


def is_script_approved(user_id, file_name):
    return True


def set_script_approval_db(user_id, file_name, approved=1):
    script_approvals[(user_id, file_name)] = approved
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "UPDATE user_files SET is_approved = ? WHERE user_id = ? AND file_name = ?",
            (approved, user_id, file_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error set_script_approval: {e}")


def get_pending_scripts():
    pending = []
    for (uid, fn), status in script_approvals.items():
        if status == 0 and not is_admin(uid):
            pending.append((uid, fn))
    return pending


def get_user_days_left(user_id):
    if user_id == OWNER_ID:
        return "Unlimited (Owner 👑)"
    if is_admin(user_id):
        return "Unlimited (Admin 🛡️)"
    sub = user_subscriptions.get(user_id)
    if not sub or not sub.get("expiry"):
        return "No Plan"
    diff = sub["expiry"] - datetime.now()
    if diff.total_seconds() <= 0:
        return "Expired"
    days = diff.days
    hours = diff.seconds // 3600
    if days > 0:
        return f"{days}d {hours}h"
    return f"{hours} hours"


def get_user_script_limit(user_id):
    if is_unlimited_scripts(user_id):
        return 999999
    sub = user_subscriptions.get(user_id)
    if sub and "limit" in sub:
        return sub["limit"]
    return 1


def get_user_folder(user_id):
    folder = os.path.join(UPLOAD_BOTS_DIR, str(user_id))
    os.makedirs(folder, exist_ok=True)
    return folder


def get_workspace_lock(user_id):
    return user_workspace_locks.setdefault(user_id, threading.RLock())


def get_user_python(user_id, create=False):
    environment = Path(RUNTIMES_DIR) / str(user_id)
    executable = environment / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    with get_workspace_lock(user_id):
        if create and not executable.is_file():
            venv.EnvBuilder(with_pip=True, system_site_packages=True).create(
                environment
            )
    return str(executable) if executable.is_file() else sys.executable


def install_requirements_file(user_id, req_file_path, chat_id=None, status_msg_id=None):
    """Installs dependencies from a requirements.txt file with progress reporting."""
    with get_workspace_lock(user_id):
        req_path = Path(req_file_path).resolve()
        if not req_path.is_file():
            return False, "Requirements file not found.", []

        packages = []
        try:
            with open(req_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg_clean = re.split(r"[;<>=!~]", line)[0].strip()
                        if pkg_clean:
                            packages.append(pkg_clean)
        except Exception:
            pass

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-input",
            "--disable-pip-version-check",
            "--no-cache-dir",
            "-r",
            str(req_path),
        ]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(req_path.parent),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
                timeout=300,
            )
            if res.returncode == 0:
                logger.info(f"Successfully installed requirements for user {user_id}")
                return True, "All requirements installed successfully.", packages
            else:
                logger.error(f"Pip install failed for user {user_id}: {res.stderr}")
                err_snippet = (res.stderr or res.stdout or "Installation failed.")[-400:].strip()
                return False, err_snippet, packages
        except subprocess.TimeoutExpired:
            return False, "Installation timed out after 5 minutes.", packages
        except Exception as e:
            return False, str(e), packages


def save_subscription_db(user_id, expiry_dt, limit=1):
    user_subscriptions[user_id] = {"expiry": expiry_dt, "limit": limit}
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO subscriptions (user_id, expiry, script_limit)
                     VALUES (?, ?, ?)""",
            (user_id, expiry_dt.isoformat(), limit),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error save_subscription: {e}")


def revoke_subscription_db(user_id):
    if user_id in user_subscriptions:
        del user_subscriptions[user_id]
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error revoke_subscription: {e}")


def save_user_file_db(
    user_id, file_name, file_type="py", auto_restart=0, saved_inputs="", is_approved=1
):
    if user_id not in user_files:
        user_files[user_id] = []
    if not any(f[0] == file_name for f in user_files[user_id]):
        user_files[user_id].append((file_name, file_type))
    script_approvals[(user_id, file_name)] = is_approved
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            """INSERT OR REPLACE INTO user_files (user_id, file_name, file_type, auto_restart, saved_inputs, is_approved)
                     VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, file_name, file_type, auto_restart, saved_inputs, is_approved),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error save_user_file: {e}")


def update_file_auto_restart_db(user_id, file_name, auto_restart):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "UPDATE user_files SET auto_restart = ? WHERE user_id = ? AND file_name = ?",
            (auto_restart, user_id, file_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error update_auto_restart: {e}")


def get_saved_inputs_db(user_id, file_name):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "SELECT saved_inputs, auto_restart FROM user_files WHERE user_id = ? AND file_name = ?",
            (user_id, file_name),
        )
        row = c.fetchone()
        conn.close()
        if row:
            inputs = [line for line in row[0].split("\n") if line]
            return inputs, row[1]
    except Exception as e:
        logger.error(f"DB Error get_saved_inputs: {e}")
    return [], 0


def save_single_input_db(user_id, file_name, input_text):
    inputs, auto_restart = get_saved_inputs_db(user_id, file_name)
    inputs.append(input_text)
    joined = "\n".join(inputs)
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "UPDATE user_files SET saved_inputs = ? WHERE user_id = ? AND file_name = ?",
            (joined, user_id, file_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error save_single_input: {e}")


def clear_saved_inputs_db(user_id, file_name):
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            'UPDATE user_files SET saved_inputs = "" WHERE user_id = ? AND file_name = ?',
            (user_id, file_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error clear_saved_inputs: {e}")


def remove_user_file_db(user_id, file_name):
    if user_id in user_files:
        user_files[user_id] = [f for f in user_files[user_id] if f[0] != file_name]
    script_approvals.pop((user_id, file_name), None)
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute(
            "DELETE FROM user_files WHERE user_id = ? AND file_name = ?",
            (user_id, file_name),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"DB Error remove_user_file: {e}")


def scan_script_safety(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            code = f.read()

        traversal_patterns = [
            r"\.\./",
            r"\.\.\\",
            r"/etc/",
            r"C:\\",
            r"D:\\",
            r"bot\.py",
            r"bot_data\.db",
            r"bot_backup\.py",
            r"upload_bots[\\/]\.\.",
            r"inf[\\/]bot_data",
        ]
        for pat in traversal_patterns:
            if re.search(pat, code, re.IGNORECASE):
                return (
                    False,
                    "Access violation: Directory traversal or host file access detected.",
                )

        bot_listener_patterns = [
            r"bot\.polling\(",
            r"updater\.start_polling\(",
            r"ApplicationBuilder\(",
            r"executor\.start_polling\(",
        ]
        for pat in bot_listener_patterns:
            if re.search(pat, code):
                return (
                    False,
                    "Standard Telegram Bots are restricted. Only background / worker scripts are allowed.",
                )

        return True, ""
    except Exception as e:
        logger.error(f"Scanner error: {e}")
        return True, ""


def is_bot_running(user_id, file_name):
    script_key = f"{user_id}_{file_name}"
    info = bot_scripts.get(script_key)
    if not info or not info.get("process"):
        return False
    try:
        proc = psutil.Process(info["process"].pid)
        running = proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
        if not running:
            cleanup_script_entry(script_key)
        return running
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        cleanup_script_entry(script_key)
        return False


def cleanup_script_entry(script_key):
    info = bot_scripts.get(script_key)
    if info:
        if "stop_event" in info and info["stop_event"]:
            info["stop_event"].set()
        if "log_file" in info and not info["log_file"].closed:
            try:
                info["log_file"].flush()
                info["log_file"].close()
            except Exception:
                pass
        bot_scripts.pop(script_key, None)


def kill_process_tree(script_key, intentional=True):
    info = bot_scripts.get(script_key)
    if not info:
        return
    info["intentional_stop"] = intentional
    if "stop_event" in info and info["stop_event"]:
        info["stop_event"].set()

    proc = info.get("process")
    if proc and hasattr(proc, "pid"):
        pid = proc.pid
        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)
            for child in children:
                try:
                    child.terminate()
                except Exception:
                    pass
            try:
                parent.terminate()
            except Exception:
                pass

            gone, alive = psutil.wait_procs(children + [parent], timeout=1.0)
            for p in alive:
                try:
                    p.kill()
                except Exception:
                    pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except Exception as e:
            logger.error(f"Error killing PID {pid}: {e}")

    if "log_file" in info and not info["log_file"].closed:
        try:
            info["log_file"].flush()
            info["log_file"].close()
        except Exception:
            pass

    if intentional:
        bot_scripts.pop(script_key, None)


def read_log_tail(log_path, max_lines=30, max_bytes=32768):
    if not os.path.exists(log_path):
        return []
    try:
        file_size = os.path.getsize(log_path)
        if file_size == 0:
            return []
        seek_len = min(file_size, max_bytes)
        with open(log_path, "rb") as f:
            f.seek(file_size - seek_len)
            raw = f.read(seek_len)
        text = raw.decode("utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return lines[-max_lines:] if lines else []
    except Exception as e:
        logger.error(f"read_log_tail error: {e}")
        return []


def trim_log_if_large(log_path, max_bytes=5 * 1024 * 1024, keep_bytes=512 * 1024):
    try:
        if os.path.exists(log_path):
            file_size = os.path.getsize(log_path)
            if file_size > max_bytes:
                with open(log_path, "rb") as f:
                    f.seek(file_size - keep_bytes)
                    tail_data = f.read(keep_bytes)
                nl_idx = tail_data.find(b"\n")
                if nl_idx != -1:
                    tail_data = tail_data[nl_idx + 1 :]
                with open(log_path, "wb") as f:
                    f.write(
                        b"--- [LOG ROTATED: OLD LOGS TRIMMED FOR PERFORMANCE] ---\n"
                        + tail_data
                    )
                logger.info(
                    f"Trimmed bloated log file: {log_path} ({file_size} -> {len(tail_data)} bytes)"
                )
    except Exception as e:
        logger.error(f"trim_log_if_large error: {e}")


TELEGRAM_MODULES = {
    "telebot": "pyTelegramBotAPI",
    "telegram": "python-telegram-bot",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "tgcrypto": "tgcrypto",
    "bs4": "beautifulsoup4",
    "requests": "requests",
    "aiohttp": "aiohttp",
    "pillow": "Pillow",
    "dotenv": "python-dotenv",
    "cryptography": "cryptography",
    "psutil": "psutil",
}


def attempt_install_pip(module_name, chat_id=None):
    pkg_name = TELEGRAM_MODULES.get(module_name.lower(), module_name)
    try:
        if chat_id:
            try:
                safe_send_message(
                    chat_id,
                    f"{emo('hourglass')} <b>Auto-Installing Module:</b> <code>{escape(str(pkg_name))}</code>...",
                )
            except Exception:
                pass
        cmd = [sys.executable, "-m", "pip", "install", "--no-cache-dir", pkg_name]
        logger.info(f"Running auto pip install: {' '.join(cmd)}")
        res = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if res.returncode == 0:
            if chat_id:
                try:
                    safe_send_message(
                        chat_id,
                        f"{emo('check')} Module <code>{escape(str(pkg_name))}</code> installed! Resuming script...",
                    )
                except Exception:
                    pass
            return True
        else:
            logger.error(f"Pip install failed for {pkg_name}: {res.stderr}")
            return False
    except Exception as e:
        logger.error(f"Pip install error: {e}")
        return False


def spawn_bot_process(user_id, file_name, chat_id=None, auto_fill_inputs=False):
    """Spawns user python script with .env auto-injection."""
    script_key = f"{user_id}_{file_name}"
    user_folder = get_user_folder(user_id)
    script_path = os.path.join(user_folder, file_name)
    log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")

    if not os.path.exists(script_path):
        return False, "Script file not found in workspace."

    if not is_script_approved(user_id, file_name) and not is_admin(user_id):
        return False, "This script is pending Admin approval."

    if is_bot_running(user_id, file_name) or script_key in bot_scripts:
        kill_process_tree(script_key, intentional=True)
        time.sleep(1.0)

    trim_log_if_large(log_path)

    try:
        log_file = open(log_path, "a", encoding="utf-8", errors="ignore")
        log_file.write(
            f"\n\n--- SCRIPT STARTED [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---\n"
        )
        log_file.flush()

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE

        child_env = os.environ.copy()
        child_env["PYTHONIOENCODING"] = "utf-8"
        child_env["PYTHONUTF8"] = "1"
        child_env["PYTHONUNBUFFERED"] = "1"

        # Pre-load environment variables from .env in user workspace
        env_path = os.path.join(user_folder, ".env")
        if os.path.exists(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="ignore") as ef:
                    for line in ef:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k:
                                child_env[k] = v
            except Exception as ef_err:
                logger.warning(f"Error parsing .env for {script_key}: {ef_err}")

        process = subprocess.Popen(
            [sys.executable, "-u", script_path],
            cwd=user_folder,
            stdin=subprocess.PIPE,
            stdout=log_file,
            stderr=log_file,
            env=child_env,
            startupinfo=startupinfo,
            creationflags=creationflags,
            encoding="utf-8",
            errors="ignore",
        )

        saved_inputs, auto_restart_val = get_saved_inputs_db(user_id, file_name)

        run_id = f"{int(time.time()*1000)}_{os.urandom(4).hex()}"
        stop_event = threading.Event()

        bot_scripts[script_key] = {
            "process": process,
            "log_file": log_file,
            "file_name": file_name,
            "user_id": user_id,
            "chat_id": chat_id or user_id,
            "start_time": datetime.now(),
            "last_restart_time": datetime.now(),
            "auto_restart": auto_restart_val,
            "saved_inputs": saved_inputs if auto_fill_inputs else [],
            "auto_fill_queue": list(saved_inputs) if auto_fill_inputs else [],
            "last_prompt_sent": None,
            "status": "running",
            "run_id": run_id,
            "stop_event": stop_event,
            "intentional_stop": False,
        }

        threading.Thread(
            target=watch_script_output,
            args=(script_key, run_id, stop_event),
            daemon=True,
        ).start()
        threading.Thread(
            target=watch_script_crash, args=(script_key, run_id), daemon=True
        ).start()

        return True, process.pid
    except Exception as e:
        logger.error(f"Error spawning {script_key}: {e}", exc_info=True)
        return False, str(e)

spawn_jacking_process = spawn_bot_process


def watch_script_crash(script_key, run_id):
    info = bot_scripts.get(script_key)
    if not info or info.get("run_id") != run_id:
        return
    proc = info.get("process")
    if not proc:
        return

    retcode = proc.wait()
    user_id = info["user_id"]
    file_name = info["file_name"]
    chat_id = info.get("chat_id", user_id)

    current_info = bot_scripts.get(script_key)
    if (
        not current_info
        or current_info.get("run_id") != run_id
        or current_info.get("intentional_stop")
    ):
        return

    cleanup_script_entry(script_key)

    if retcode != 0 and retcode != -signal.SIGTERM and retcode != 15:
        logger.warning(f"Script {script_key} crashed with returncode {retcode}")
        user_folder = get_user_folder(user_id)
        log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")
        missing_module = None
        if os.path.exists(log_path):
            try:
                tail_lines = read_log_tail(log_path, max_lines=40, max_bytes=8192)
                log_text = "\n".join(tail_lines)
                matches = re.findall(
                    r"ModuleNotFoundError: No module named '(.+?)'", log_text
                )
                if matches:
                    missing_module = matches[-1].strip().strip("'\"")
            except Exception:
                pass

        if missing_module:
            installed = attempt_install_pip(missing_module, chat_id)
            if installed:
                time.sleep(1.0)
                spawn_bot_process(
                    user_id, file_name, chat_id, auto_fill_inputs=True
                )
                return

        try:
            safe_send_message(
                chat_id,
                f"<b>{emo('warn')} Script Crash Detected</b>\n\n"
                f"<blockquote>"
                f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                f"<b>Exit Code:</b> <code>{retcode}</code>\n"
                f"<b>State:</b> {emo('cross')} Stopped unexpectedly"
                f"</blockquote>\n\n"
                f"{emo('info')} <i>Use <b>View Logs</b> below to inspect tracebacks.</i>",
                reply_markup=create_crashed_keyboard(user_id, file_name),
            )
        except Exception:
            pass


def clean_log_text(raw_lines, max_lines=15):
    cleaned = []
    prev_line = None
    for raw in raw_lines:
        line = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw)
        line = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", line).strip()
        if not line:
            continue
        if line == prev_line:
            continue
        prev_line = line
        cleaned.append(line)
    return "\n".join(cleaned[-max_lines:]) if cleaned else "(No output logged yet)"


def is_real_input_prompt(line):
    line_clean = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", line)
    line_clean = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", line_clean).strip()
    if not line_clean or len(line_clean) < 3:
        return False

    line_lower = line_clean.lower()

    blacklist = [
        "hits:",
        "good:",
        "bad:",
        "checked:",
        "cpm:",
        "proxies:",
        "proxy:",
        "coded by",
        "http://",
        "https://",
        "t.me/",
        "channel:",
        "total:",
        "saved to:",
        "threads:",
        "progress:",
        "loading:",
        "completed",
        "checking",
        "testing",
        "success",
        "failure",
        "error:",
        "exception",
    ]
    if any(bl in line_lower for bl in blacklist):
        return False

    if re.search(
        r"\b(enter|input|type|provide|please enter|insert|specify)\b", line_lower
    ):
        return True

    trimmed = line_clean.rstrip()
    if (
        trimmed.endswith(":")
        or trimmed.endswith("?")
        or trimmed.endswith(">")
        or trimmed.endswith("->")
    ):
        prompt_targets = [
            "token",
            "chat id",
            "chat_id",
            "user id",
            "user_id",
            "phone",
            "password",
            "api key",
            "api_key",
            "api_id",
            "api hash",
            "api_hash",
            "code",
            "otp",
            "target",
            "key",
            "choice",
            "option",
            "username",
            "session",
        ]
        if any(pt in line_lower for pt in prompt_targets):
            return True

    return False


def watch_script_output(script_key, run_id, stop_event):
    time.sleep(1.0)
    user_id = int(script_key.split("_")[0])
    file_name = script_key.split("_", 1)[1]
    user_folder = get_user_folder(user_id)
    log_path = os.path.join(user_folder, f"{os.path.splitext(file_name)[0]}.log")

    last_checked_line = ""

    while not stop_event.is_set():
        info = bot_scripts.get(script_key)
        if (
            not info
            or info.get("run_id") != run_id
            or not is_bot_running(user_id, file_name)
        ):
            break

        tail_lines = read_log_tail(log_path, max_lines=5, max_bytes=8192)
        if tail_lines:
            last_line = tail_lines[-1]
            is_prompt = is_real_input_prompt(last_line)

            if (
                is_prompt
                and last_line != last_checked_line
                and last_line != info.get("last_prompt_sent")
            ):
                last_checked_line = last_line
                info["last_prompt_sent"] = last_line

                if info.get("auto_fill_queue"):
                    next_val = info["auto_fill_queue"].pop(0)
                    time.sleep(0.5)
                    try:
                        proc = info["process"]
                        if proc and proc.stdin and proc.poll() is None:
                            proc.stdin.write(next_val + "\n")
                            proc.stdin.flush()
                            logger.info(f"Auto-fed saved input to {script_key}.")
                            continue
                    except Exception as e:
                        logger.error(f"Auto-fill error {script_key}: {e}")

                chat_id = info.get("chat_id", user_id)
                fid = get_file_id(user_id, file_name)
                markup = types.InlineKeyboardMarkup(row_width=2)
                markup.add(
                    ui_button("Send Input", callback_data=f"inp_{fid}"),
                    ui_button("Dismiss", callback_data="dismiss_prompt"),
                )
                clean_for_msg = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", last_line).strip()[
                    :120
                ]
                try:
                    safe_send_message(
                        chat_id,
                        f"<b>{emo('note')} Interactive Input Required</b>\n\n"
                        f"<blockquote>"
                        f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                        f"<b>Prompt:</b>\n"
                        f"<code>{escape(clean_for_msg)}</code>"
                        f"</blockquote>\n\n"
                        f"{emo('pin')} <i>Click <b>Send Input</b> below to respond:</i>",
                        reply_markup=markup,
                    )
                except Exception as e:
                    logger.error(f"Failed to send prompt alert for {script_key}: {e}")

        if stop_event.wait(1.5):
            break


def auto_restart_worker():
    while True:
        try:
            now = datetime.now()
            keys = list(bot_scripts.keys())
            for script_key in keys:
                info = bot_scripts.get(script_key)
                if not info:
                    continue
                user_id = info["user_id"]
                file_name = info["file_name"]

                if info.get("auto_restart") == 1 and is_bot_running(user_id, file_name):
                    elapsed = (now - info.get("last_restart_time", now)).total_seconds()
                    if elapsed >= 1800:
                        logger.info(f"Triggering 30m Auto-Restart for {script_key}")
                        kill_process_tree(script_key, intentional=True)
                        time.sleep(1.5)
                        ok, pid = spawn_bot_process(
                            user_id,
                            file_name,
                            info.get("chat_id"),
                            auto_fill_inputs=True,
                        )
                        if ok:
                            try:
                                safe_send_message(
                                    info.get("chat_id", user_id),
                                    f"<b>{emo('reset')} Auto-Restart Routine</b>\n\n"
                                    f"<blockquote>"
                                    f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                                    f"<b>Cycle:</b> <code>30-Minute Routine</code>\n"
                                    f"<b>Status:</b> {emo('check')} Restarted successfully"
                                    f"</blockquote>\n\n"
                                    f"{emo('fire')} <i>Script restarted with cached inputs!</i>",
                                )
                            except Exception:
                                pass
        except Exception as e:
            logger.error(f"Auto restart worker error: {e}")
        time.sleep(15)


def expiry_checker_worker():
    while True:
        try:
            now = datetime.now()
            for user_id, data in list(user_subscriptions.items()):
                if is_admin(user_id):
                    continue
                if data.get("expiry") and data["expiry"] <= now:
                    logger.info(
                        f"User {user_id} plan expired. Killing running scripts."
                    )
                    for script_key in list(bot_scripts.keys()):
                        if script_key.startswith(f"{user_id}_"):
                            kill_process_tree(script_key)
                    try:
                        safe_send_message(
                            user_id,
                            f"<b>{emo('warn')} ACCESS PLAN EXPIRED</b>\n\n"
                            f"<blockquote>"
                            f"Your hosting subscription has concluded. All active processes have been stopped.\n"
                            f"Please reach out to {YOUR_USERNAME} to renew your quota."
                            f"</blockquote>",
                        )
                    except Exception:
                        pass
                    del user_subscriptions[user_id]
        except Exception as e:
            logger.error(f"Expiry checker error: {e}")
        time.sleep(60)


def create_main_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    if has_active_access(user_id):
        markup.row(ui_button("Upload script", callback_data="btn_upload"))
    else:
        markup.row(
            ui_button(
                "Request access",
                url=f"https://t.me/{YOUR_USERNAME.lstrip('@')}",
                style="primary",
            )
        )
    markup.row(
        ui_button("My scripts", callback_data="btn_my_scripts"),
        ui_button("My account", callback_data="btn_account"),
    )
    markup.row(
        ui_button("Help", callback_data="btn_help"),
        ui_button("Support", callback_data="btn_support"),
    )
    if is_admin(user_id):
        markup.row(ui_button("Admin panel", callback_data="btn_admin_panel"))
    return markup


def paginate(items, page=0):
    pages = max(1, (len(items) + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(int(page), pages - 1))
    return items[page * PAGE_SIZE : (page + 1) * PAGE_SIZE], page, pages


def add_page_buttons(markup, page, pages, prefix):
    buttons = []
    if page > 0:
        buttons.append(ui_button("Previous", callback_data=f"{prefix}{page - 1}"))
    if page + 1 < pages:
        buttons.append(ui_button("Next", callback_data=f"{prefix}{page + 1}"))
    if buttons:
        markup.row(*buttons)


def create_script_list_menu(user_id, page=0):
    markup = types.InlineKeyboardMarkup(row_width=1)
    files, page, pages = paginate(user_files.get(user_id, []), page)
    for file_name, file_type in files:
        identifier = get_file_id(user_id, file_name)
        status = "Running" if is_bot_running(user_id, file_name) else "Stopped"
        markup.row(
            ui_button(f"{status} | {file_name}", callback_data=f"mng_{identifier}")
        )
    add_page_buttons(markup, page, pages, "scripts_")
    if has_active_access(user_id):
        markup.row(ui_button("Upload script", callback_data="btn_upload"))
    markup.row(ui_button("Back to dashboard", callback_data="btn_back_main"))
    return markup


def create_script_control_panel(user_id, file_name):
    fid = get_file_id(user_id, file_name)
    markup = types.InlineKeyboardMarkup(row_width=2)
    running = is_bot_running(user_id, file_name)
    saved_inputs, auto_restart = get_saved_inputs_db(user_id, file_name)

    ar_text = "Auto-restart: ON" if auto_restart == 1 else "Auto-restart: OFF"

    if running:
        markup.row(
            ui_button("Stop", callback_data=f"stop_{fid}", style="danger"),
            ui_button("Restart", callback_data=f"ask_r_{fid}"),
        )
    else:
        markup.row(
            ui_button("Start", callback_data=f"start_{fid}", style="success"),
            ui_button("Restart options", callback_data=f"ask_r_{fid}"),
        )

    markup.row(
        ui_button(
            ar_text,
            callback_data=f"t_ar_{fid}",
            style="success" if auto_restart else None,
        ),
        ui_button("Live logs", callback_data=f"logs_{fid}"),
    )
    markup.row(
        ui_button("Send input", callback_data=f"inp_{fid}"),
        ui_button("Delete", callback_data=f"del_{fid}", style="danger"),
    )
    markup.row(ui_button("Back to Scripts", callback_data="btn_my_scripts"))
    return markup


def create_crashed_keyboard(user_id, file_name):
    fid = get_file_id(user_id, file_name)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(
        ui_button("View Logs", callback_data=f"logs_{fid}"),
        ui_button("Restart", callback_data=f"ask_r_{fid}", style="success"),
    )
    markup.row(ui_button("Back to Scripts", callback_data="btn_my_scripts"))
    return markup


def create_admin_panel_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.row(ui_button("Live processes", callback_data="adm_live", style="primary"))
    markup.row(
        ui_button("Grant / extend", callback_data="adm_grant", style="success"),
        ui_button("Script limit", callback_data="adm_limit"),
    )
    markup.row(
        ui_button("Revoke access", callback_data="adm_revoke", style="danger"),
        ui_button("Find user", callback_data="adm_user_search"),
    )
    markup.row(ui_button("Broadcast", callback_data="adm_broadcast"))
    markup.row(ui_button("Back to dashboard", callback_data="btn_back_main"))
    return markup


def render_main_menu_text(user_id):
    active_access = has_active_access(user_id)
    days_left = get_user_days_left(user_id)
    files = user_files.get(user_id, [])
    running_count = sum(1 for fn, _ in files if is_bot_running(user_id, fn))

    if is_unlimited_scripts(user_id):
        limit_str = "∞ Unlimited"
        avail_str = "∞ Unlimited"
    else:
        limit = get_user_script_limit(user_id)
        limit_str = str(limit)
        avail_str = str(max(0, limit - len(files)))

    if user_id == OWNER_ID:
        role_badge = f"{emo('bolt')} <b>Owner / Founder</b>"
    elif is_admin(user_id):
        role_badge = f"{emo('key')} <b>Administrator</b>"
    elif active_access:
        role_badge = f"{emo('check')} <b>Premium Member</b>"
    else:
        role_badge = f"{emo('warn')} <b>Guest / Inactive</b>"

    status_str = f"{emo('check')} <b>Active</b>" if active_access else f"{emo('cross')} <b>Access Required</b>"

    return (
        f"<b>{emo('bolt')} File Hosting Bot</b>\n"
        f"<i>High-Performance Python Automation & Script Runner</i>\n\n"
        f"<blockquote>"
        f"<b>Host Status:</b> {status_str}\n"
        f"<b>Access Plan:</b> <code>{escape(days_left)}</code>\n"
        f"<b>Account Role:</b> {role_badge}"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"<b>Active Tasks:</b> <code>{running_count} running</code>\n"
        f"<b>Script Quota:</b> <code>{len(files)} / {limit_str}</code>\n"
        f"<b>Available Slots:</b> <code>{avail_str}</code>\n"
        f"<b>Workspace:</b> <code>upload_bots/{user_id}/</code>"
        f"</blockquote>\n\n"
        f"{emo('id')} <b>User Account:</b> <code>{user_id}</code>"
    )


def render_admin_text():
    subscriptions = sum(
        1
        for subscription in user_subscriptions.values()
        if subscription.get("expiry", datetime.min) > datetime.now()
    )
    pending = get_pending_scripts()
    return (
        f"<b>{emo('key')} Admin Control Tower</b>\n"
        f"<i>Infrastructure & System Management</i>\n\n"
        f"<blockquote>"
        f"<b>Registered Users:</b> <code>{len(active_users)} accounts</code>\n"
        f"<b>Active Plans:</b> <code>{subscriptions} active</code>\n"
        f"<b>Running Processes:</b> <code>{len(bot_scripts)} tasks</code>\n"
        f"<b>Pending Approvals:</b> <code>{len(pending)} scripts</code>"
        f"</blockquote>\n\n"
        f"<blockquote>"
        f"<b>Owner Privileges:</b> {emo('bolt')} <i>Unlimited Scripts</i>\n"
        f"<b>Upload Pipeline:</b> {emo('check')} <i>Auto-Approve Active</i>\n"
        f"<b>Dependency Sync:</b> {emo('reset')} <i>Auto-Install Active</i>"
        f"</blockquote>\n\n"
        f"{emo('info')} <i>Broadcasts & access revocations require explicit confirmation.</i>"
    )


def render_script_text(user_id, file_name):
    running = is_bot_running(user_id, file_name)
    info = bot_scripts.get(f"{user_id}_{file_name}", {})
    saved_inputs, auto_restart = get_saved_inputs_db(user_id, file_name)

    status_badge = f"{emo('check')} <b>Running</b>" if running else f"{emo('cross')} <b>Stopped</b>"
    ar_badge = f"{emo('check')} <b>Every 30m</b>" if auto_restart else f"{emo('cross')} <b>Off</b>"

    pid_str = f"<code>{info['process'].pid}</code>" if running and info.get("process") else "<i>N/A</i>"

    if running and info.get("start_time"):
        uptime_sec = int((datetime.now() - info["start_time"]).total_seconds())
        h = uptime_sec // 3600
        m = (uptime_sec % 3600) // 60
        s = uptime_sec % 60
        uptime_str = f"<code>{h}h {m}m {s}s</code>"
    else:
        uptime_str = "<i>N/A</i>"

    user_folder = get_user_folder(user_id)
    has_env = os.path.exists(os.path.join(user_folder, ".env"))
    env_str = f"{emo('check')} <i>Active</i>" if has_env else "<i>None</i>"

    return (
        f"<b>{emo('doc')} Script Controller</b>\n"
        f"<code>{escape(file_name)}</code>\n\n"
        f"<blockquote>"
        f"<b>Status:</b> {status_badge}\n"
        f"<b>Auto-Restart:</b> {ar_badge}\n"
        f"<b>Saved Inputs:</b> <code>{len(saved_inputs)} stored</code>\n"
        f"<b>Process PID:</b> {pid_str}\n"
        f"<b>Uptime:</b> {uptime_str}\n"
        f"<b>.env File:</b> {env_str}"
        f"</blockquote>\n\n"
        f"{emo('person')} <b>Owner ID:</b> <code>{user_id}</code>\n"
        f"{emo('info')} <i>Auxiliary files (.env, .txt, etc.) in this folder are shared with this script.</i>"
    )


def menu_action_from_text(text):
    label = " ".join(re.sub(r"[^a-z\s]", " ", (text or "").lower()).split())
    return MENU_ACTIONS.get(label)


def get_menu_panel(data, user_id):
    markup = types.InlineKeyboardMarkup().add(
        ui_button("Back to dashboard", callback_data="btn_back_main")
    )
    if data == "btn_back_main":
        return render_main_menu_text(user_id), create_main_menu(user_id)
    if data == "btn_upload":
        if not has_active_access(user_id):
            return (
                f"<b>{emo('cross')} Access Required</b>\n"
                f"<i>Your workspace is awaiting activation</i>\n\n"
                f"<blockquote>An active hosting plan is required to upload and run scripts.</blockquote>\n\n"
                f"Contact support to request access or renew your plan.",
                types.InlineKeyboardMarkup().add(
                    ui_button("Support", callback_data="btn_support"),
                    ui_button("Back to dashboard", callback_data="btn_back_main"),
                ),
            )
        limit_str = "∞ Unlimited" if is_unlimited_scripts(user_id) else str(get_user_script_limit(user_id))
        return (
            f"<b>{emo('action')} Workspace Uploader</b>\n"
            f"<i>Upload Scripts, Projects & Supporting Files</i>\n\n"
            f"<blockquote>"
            f"<b>Python Scripts:</b> <code>.py</code> files\n"
            f"<b>Projects:</b> <code>.zip</code> archives (auto-extracted)\n"
            f"<b>Config & Env:</b> <code>.env</code> environment files\n"
            f"<b>Data & Sessions:</b> <code>.txt</code>, <code>.json</code>, <code>.session</code>\n"
            f"<b>Dependencies:</b> <code>requirements.txt</code> (auto-installed)"
            f"</blockquote>\n\n"
            f"<blockquote>"
            f"<b>Multi-File Upload:</b> {emo('check')} <i>Saved in same folder</i>\n"
            f"<b>Dependency Sync:</b> {emo('check')} <i>Auto-pip on upload & zip</i>\n"
            f"<b>Allowed Scripts:</b> <code>{limit_str}</code>\n"
            f"<b>Max File Size:</b> <code>20 MB (Telegram limit)</code>"
            f"</blockquote>\n\n"
            f"{emo('pin')} <i>Send your file(s) as documents directly to this chat!</i>",
            markup,
        )
    if data == "btn_my_scripts" or data.startswith("scripts_"):
        files = user_files.get(user_id, [])
        page = int(data.split("_")[-1]) if data.startswith("scripts_") else 0
        _, page, pages = paginate(files, page)
        running_count = sum(1 for fn, _ in files if is_bot_running(user_id, fn))
        limit_str = "∞ Unlimited" if is_unlimited_scripts(user_id) else str(get_user_script_limit(user_id))

        user_folder = get_user_folder(user_id)
        all_folder_files = [f for f in os.listdir(user_folder) if os.path.isfile(os.path.join(user_folder, f))]
        supporting_files = [f for f in all_folder_files if not f.endswith(".py") and not f.endswith(".log")]

        body = (
            f"<b>{emo('doc')} My Hosted Scripts</b>\n"
            f"<i>Workspace · Page {page + 1} of {pages}</i>\n\n"
            f"<blockquote>"
            f"<b>Hosted Scripts:</b> <code>{len(files)} / {limit_str}</code>\n"
            f"<b>Active Now:</b> <code>{running_count} running</code>\n"
            f"<b>Extra Files:</b> <code>{len(supporting_files)} (.env, data)</code>"
            f"</blockquote>\n\n"
        )
        if not files:
            body += f"<blockquote>{emo('info')} Your workspace has no scripts yet.\nUpload a <code>.py</code> file or <code>.zip</code> to get started!</blockquote>"
        else:
            body += f"{emo('pin')} <i>Select any script below to start, stop, view logs, or configure:</i>"
        return body, create_script_list_menu(user_id, page)

    if data == "btn_account":
        files = user_files.get(user_id, [])
        running_count = sum(
            1 for filename, _ in files if is_bot_running(user_id, filename)
        )
        limit_str = "∞ Unlimited" if is_unlimited_scripts(user_id) else str(get_user_script_limit(user_id))

        if user_id == OWNER_ID:
            role_badge = "👑 Owner / Creator"
        elif is_admin(user_id):
            role_badge = "🛡️ Administrator"
        elif has_active_access(user_id):
            role_badge = "✨ Premium Subscriber"
        else:
            role_badge = "🔒 Inactive / Expired"

        return (
            f"<b>{emo('person')} Account Profile</b>\n"
            f"<i>Membership, Quota & Server Details</i>\n\n"
            f"<blockquote>"
            f"<b>Telegram ID:</b> <code>{user_id}</code>\n"
            f"<b>Account Role:</b> <code>{role_badge}</code>\n"
            f"<b>Access Remaining:</b> <code>{escape(get_user_days_left(user_id))}</code>\n"
            f"<b>Script Quota:</b> <code>{len(files)} / {limit_str}</code>\n"
            f"<b>Running Now:</b> <code>{running_count} active</code>"
            f"</blockquote>\n\n"
            f"{emo('phone')} <b>Support Contact:</b> {escape(YOUR_USERNAME)}",
            markup,
        )
    if data == "btn_help":
        return (
            f"<b>{emo('help')} File Hosting Bot Guide</b>\n"
            f"<i>Platform Features & Operations</i>\n\n"
            f"<blockquote>"
            f"<b>1. Uploading Files</b>\n"
            f"• Send <code>.py</code> scripts or <code>.zip</code> projects.\n"
            f"• Send <code>.env</code> & <code>.txt</code> files for credentials/config.\n"
            f"• Send <code>requirements.txt</code> to auto-pip install.\n"
            f"• All files are saved together in your folder!"
            f"</blockquote>\n\n"
            f"<blockquote>"
            f"<b>2. Execution & Controls</b>\n"
            f"• <b>Start/Stop:</b> Instant background process execution.\n"
            f"• <b>Restart:</b> Re-injects cached inputs automatically.\n"
            f"• <b>Auto-Restart:</b> 30-minute automated cycling.\n"
            f"• <b>Live Logs:</b> Real-time output and full log download."
            f"</blockquote>\n\n"
            f"{emo('fire')} <i>Owner accounts enjoy unlimited script hosting capacity!</i>",
            markup,
        )
    if data == "btn_support":
        return (
            f"<b>{emo('phone')} Support & Inquiries</b>\n"
            f"<i>Direct Customer Support & Plan Requests</i>\n\n"
            f"<blockquote>"
            f"<b>Representative:</b> {escape(YOUR_USERNAME)}\n"
            f"<b>Channel:</b> {escape(UPDATE_CHANNEL)}\n"
            f"<b>Your ID:</b> <code>{user_id}</code>"
            f"</blockquote>\n\n"
            f"{emo('pin')} <i>Please provide your Telegram ID when requesting access or script extensions.</i>",
            types.InlineKeyboardMarkup().add(
                ui_button(
                    "Contact Support", url=f"https://t.me/{YOUR_USERNAME.lstrip('@')}"
                ),
                ui_button("Dashboard", callback_data="btn_back_main"),
            ),
        )
    if data == "btn_admin_panel":
        if not is_admin(user_id):
            return f"<b>{emo('cross')} Restricted area</b>\n\nAdmin access is required.", markup
        return render_admin_text(), create_admin_panel_menu()
    return None


def handle_menu_message(message):
    if message.chat.type != "private":
        bot.reply_to(
            message, "Open a private chat with this bot to manage your scripts."
        )
        return
    action = menu_action_from_text(message.text)
    if not action:
        return
    cancel_pending_input(message.chat.id)
    admin_states.pop(message.chat.id, None)
    text, markup = get_menu_panel(action, message.from_user.id)
    safe_send_message(message.chat.id, text, reply_markup=markup)


def cmd_start(message):
    if message.chat.type != "private":
        bot.reply_to(
            message, "Open a private chat with this bot to manage your scripts."
        )
        return
    cancel_pending_input(message.chat.id)
    admin_states.pop(message.chat.id, None)
    user_id = message.from_user.id
    active_users.add(user_id)
    try:
        conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO active_users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        conn.close()
    except Exception:
        pass

    text = render_main_menu_text(user_id)
    safe_send_message(message.chat.id, text, reply_markup=create_main_menu(user_id))


def cmd_admin(message):
    if message.chat.type != "private":
        bot.reply_to(
            message, "Open a private chat with this bot to manage your scripts."
        )
        return
    cancel_pending_input(message.chat.id)
    admin_states.pop(message.chat.id, None)
    user_id = message.from_user.id
    if not is_admin(user_id):
        bot.reply_to(message, f"{emo('warn')} Access denied. Admin only.")
        return
    safe_send_message(
        message.chat.id,
        render_admin_text(),
        reply_markup=create_admin_panel_menu(),
    )


def handle_uploaded_file(message):
    """Handles uploaded files: Python scripts, ZIP projects, .env, and supporting files."""
    if message.chat.type != "private":
        bot.reply_to(message, "Please upload files in a private chat with this bot.")
        return
    user_id = message.from_user.id
    if not has_active_access(user_id):
        safe_send_message(
            message.chat.id,
            f"<b>{emo('cross')} ACCESS DENIED</b>\n\n"
            f"You do not have an active hosting subscription.\n"
            f"Please reach out to {YOUR_USERNAME} to activate your plan.",
            reply_markup=create_main_menu(user_id),
        )
        return

    doc = message.document
    file_name = doc.file_name or ""
    if not file_name or any(
        character in file_name for character in ("/", "\\", ":", "\x00")
    ):
        bot.reply_to(message, f"{emo('cross')} Invalid filename. Send a file without directory paths.")
        return
    if (doc.file_size or 0) > 20 * 1024 * 1024:
        bot.reply_to(message, f"{emo('warn')} This file exceeds Telegram's 20 MB bot download limit.")
        return

    # Check dangerous executable types that should never be uploaded
    blocked_exts = (
        ".exe", ".bat", ".cmd", ".sh", ".vbs", ".ps1", ".com", ".scr", ".msi", ".dll", ".so", ".bin"
    )
    if any(file_name.lower().endswith(ext) for ext in blocked_exts):
        bot.reply_to(
            message,
            f"<b>{emo('cross')} BLOCKED FILE FORMAT</b>\n\n"
            f"Binary executables (<code>{escape(file_name)}</code>) are restricted for security reasons.\n"
            f"Please upload Python scripts (<code>.py</code>), projects (<code>.zip</code>), or data/config files (<code>.env</code>, <code>.txt</code>, <code>.json</code>).",
        )
        return

    user_folder = get_user_folder(user_id)
    save_path = os.path.join(user_folder, file_name)
    file_name_lower = file_name.lower()
    is_py = file_name_lower.endswith(".py")
    is_zip = file_name_lower.endswith(".zip")
    is_req = file_name_lower == "requirements.txt" or file_name_lower.endswith("requirements.txt") or file_name_lower == "reqs.txt"

    # Only executable scripts count towards script limit!
    # Owner and Admins have UNLIMITED scripts!
    if is_py:
        if not is_unlimited_scripts(user_id):
            limit = get_user_script_limit(user_id)
            current_count = len(user_files.get(user_id, []))
            already_exists_in_db = any(f[0] == file_name for f in user_files.get(user_id, []))
            if current_count >= limit and not already_exists_in_db:
                safe_send_message(
                    message.chat.id,
                    f"<b>{emo('warn')} Script Limit Reached</b>\n\n"
                    f"<blockquote>"
                    f"<b>Hosted Scripts:</b> <code>{current_count} scripts</code>\n"
                    f"<b>Allowed Limit:</b> <code>{limit} scripts</code>"
                    f"</blockquote>\n\n"
                    f"Delete an existing script or contact {YOUR_USERNAME} to upgrade your plan.",
                    reply_markup=create_main_menu(user_id),
                )
                return

    try:
        msg_wait = safe_send_message(
            message.chat.id,
            f"{emo('hourglass')} <i>Downloading & processing <code>{escape(file_name)}</code>...</i>"
        )
        file_info = bot.get_file(doc.file_id)
        downloaded = bot.download_file(file_info.file_path)

        with get_workspace_lock(user_id):
            with open(save_path, "wb") as f:
                f.write(downloaded)

        # CASE 1: Requirements file (direct upload)
        if is_req:
            edit_panel(
                f"{emo('reset')} <b>Auto-Installing Dependencies...</b>\n\n"
                f"Detected <code>{escape(file_name)}</code>. Running <code>pip install -r</code> in workspace...",
                chat_id=message.chat.id,
                message_id=msg_wait.message_id,
            )
            success, result_msg, packages = install_requirements_file(
                user_id, save_path, chat_id=message.chat.id, status_msg_id=msg_wait.message_id
            )
            pkg_preview = ", ".join(packages[:10]) if packages else "dependencies in file"
            if len(packages) > 10:
                pkg_preview += f" (+{len(packages)-10} more)"

            if success:
                edit_panel(
                    f"<b>{emo('check')} Requirements Installed</b>\n\n"
                    f"<blockquote>"
                    f"<b>File Name:</b> <code>{escape(file_name)}</code>\n"
                    f"<b>Packages:</b> <code>{len(packages)} identified</code>\n"
                    f"<b>Status:</b> {emo('check')} Installed successfully\n"
                    f"<b>Directory:</b> <code>upload_bots/{user_id}/</code>"
                    f"</blockquote>\n\n"
                    f"{emo('bolt')} <b>Active Packages:</b>\n<code>{escape(pkg_preview)}</code>\n\n"
                    f"{emo('fire')} <i>Your workspace is equipped and ready for your scripts!</i>",
                    chat_id=message.chat.id,
                    message_id=msg_wait.message_id,
                    reply_markup=types.InlineKeyboardMarkup().row(
                        ui_button("My Scripts", callback_data="btn_my_scripts"),
                        ui_button("Upload Script", callback_data="btn_upload"),
                    ),
                )
            else:
                edit_panel(
                    f"<b>{emo('cross')} Dependency Installation Failed</b>\n\n"
                    f"<blockquote>"
                    f"<b>File:</b> <code>{escape(file_name)}</code>\n"
                    f"<b>Status:</b> {emo('cross')} Pip exited with error"
                    f"</blockquote>\n\n"
                    f"<pre>{escape(result_msg)}</pre>\n\n"
                    f"Please check your <code>requirements.txt</code> file and re-upload.",
                    chat_id=message.chat.id,
                    message_id=msg_wait.message_id,
                )
            return

        # CASE 2: Supporting/configuration/data file (.env, .txt, .json, .session, etc.)
        if not is_py and not is_zip:
            if file_name.startswith(".env") or file_name.endswith(".env"):
                cat = "Environment Config (.env)"
                extra_hint = f"{emo('key')} <i>Environment variables in this file are automatically available to your scripts!</i>"
            elif file_name_lower.endswith(".json"):
                cat = "JSON Configuration / Data"
                extra_hint = f"{emo('info')} <i>Accessible as <code>./{escape(file_name)}</code> from your scripts.</i>"
            elif file_name_lower.endswith(".session"):
                cat = "Telegram Client Session"
                extra_hint = f"{emo('phone')} <i>Telethon / Pyrogram session file ready in workspace.</i>"
            elif file_name_lower.endswith(".txt"):
                cat = "Text / Data / Credentials"
                extra_hint = f"{emo('doc')} <i>Available for scripts to open and read.</i>"
            else:
                cat = f"Workspace Asset ({os.path.splitext(file_name)[1] or 'file'})"
                extra_hint = f"{emo('info')} <i>Saved in your personal script directory.</i>"

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                ui_button("My Scripts", callback_data="btn_my_scripts"),
                ui_button("Upload More", callback_data="btn_upload"),
            )
            markup.row(ui_button("Dashboard", callback_data="btn_back_main"))

            edit_panel(
                f"<b>{emo('paperclip')} Workspace File Saved</b>\n\n"
                f"<blockquote>"
                f"<b>File Name:</b> <code>{escape(file_name)}</code>\n"
                f"<b>Size:</b> <code>{format_size(len(downloaded))}</code>\n"
                f"<b>Category:</b> <code>{cat}</code>\n"
                f"<b>Location:</b> <code>upload_bots/{user_id}/</code>\n"
                f"<b>Storage:</b> {emo('check')} Saved in script directory"
                f"</blockquote>\n\n"
                f"{extra_hint}",
                chat_id=message.chat.id,
                message_id=msg_wait.message_id,
                reply_markup=markup,
            )
            return

        # CASE 3: Zip Project
        if is_zip:
            extracted_files_count = 0
            with zipfile.ZipFile(save_path, "r") as zip_ref:
                members = zip_ref.infolist()
                if (
                    len(members) > 1000
                    or sum(member.file_size for member in members) > 100 * 1024 * 1024
                ):
                    raise ValueError("Archive exceeds extraction limits (100 MB / 1000 entries).")
                root = os.path.realpath(user_folder)
                for member in members:
                    target = os.path.realpath(os.path.join(user_folder, member.filename))
                    if os.path.commonpath([root, target]) != root or ":" in member.filename:
                        raise ValueError("Unsafe ZIP path.")
                    if (member.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError("ZIP links are not supported.")
                zip_ref.extractall(user_folder)
                extracted_files_count = len(members)

            # Flatten single top-level directory if present so all files (.env, .py, etc.) sit in user_folder
            top_level_items = [
                item for item in os.listdir(user_folder)
                if not item.startswith(".") and os.path.isdir(os.path.join(user_folder, item))
            ]
            py_in_root = [f for f in os.listdir(user_folder) if f.endswith(".py")]
            if not py_in_root and len(top_level_items) == 1:
                single_dir = os.path.join(user_folder, top_level_items[0])
                for sf in os.listdir(single_dir):
                    src = os.path.join(single_dir, sf)
                    dst = os.path.join(user_folder, sf)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                try:
                    shutil.rmtree(single_dir, ignore_errors=True)
                except Exception:
                    pass

            # Search for requirements.txt anywhere in extracted files
            req_candidates = ["requirements.txt", "requirement.txt", "reqs.txt"]
            found_req_path = None
            for r_dir, _, r_files in os.walk(user_folder):
                for rf in r_files:
                    if rf.lower() in req_candidates:
                        found_req_path = os.path.join(r_dir, rf)
                        break
                if found_req_path:
                    break

            req_status = f"{emo('info')} <i>None found</i>"
            if found_req_path and os.path.exists(found_req_path):
                edit_panel(
                    f"{emo('reset')} <b>Auto-Installing Zip Dependencies...</b>\n\n"
                    f"Found <code>{escape(os.path.basename(found_req_path))}</code> inside zip. Running pip install...",
                    chat_id=message.chat.id,
                    message_id=msg_wait.message_id,
                )
                req_ok, _, pkgs = install_requirements_file(
                    user_id, found_req_path, chat_id=message.chat.id, status_msg_id=msg_wait.message_id
                )
                if req_ok:
                    req_status = f"{emo('check')} <i>{len(pkgs)} packages installed</i>"
                else:
                    req_status = f"{emo('warn')} <i>Install finished with warnings</i>"

            py_files = [f for f in os.listdir(user_folder) if f.endswith(".py")]
            if not py_files:
                edit_panel(
                    f"{emo('cross')} <b>No Python (.py) Script Found</b>\n\n"
                    f"The zip was extracted ({extracted_files_count} files), but no executable <code>.py</code> file was found.\n"
                    f"Please include a main <code>.py</code> file in your zip.",
                    chat_id=message.chat.id,
                    message_id=msg_wait.message_id,
                )
                return

            preferred_py = ["main.py", "bot.py", "app.py", "run.py", "start.py"]
            main_script = None
            for p in preferred_py:
                if p in py_files:
                    main_script = p
                    break
            if not main_script:
                main_script = py_files[0]

            file_name = main_script
            save_path = os.path.join(user_folder, file_name)

        # CASE 4: Python script (.py) or zip main script
        is_safe, reason = scan_script_safety(save_path)
        if not is_safe:
            try:
                os.remove(save_path)
            except Exception:
                pass
            edit_panel(
                f"{emo('cross')} <b>Security Alert: Upload Rejected</b>\n\n{reason}",
                chat_id=message.chat.id,
                message_id=msg_wait.message_id,
            )
            return

        fid = get_file_id(user_id, file_name)
        save_user_file_db(user_id, file_name, "py", is_approved=1)

        limit_display = "∞ Unlimited" if is_unlimited_scripts(user_id) else str(get_user_script_limit(user_id))
        cur_count = len(user_files.get(user_id, []))

        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            ui_button("Start Now", callback_data=f"start_{fid}", style="success"),
            ui_button("My Scripts", callback_data="btn_my_scripts"),
        )
        markup.row(ui_button("Dashboard", callback_data="btn_back_main"))

        edit_panel(
            f"<b>{emo('check')} Script Deployed Successfully</b>\n\n"
            f"<blockquote>"
            f"<b>Script Name:</b> <code>{escape(file_name)}</code>\n"
            f"<b>File Size:</b> <code>{format_size(os.path.getsize(save_path))}</code>\n"
            f"<b>Script Quota:</b> <code>{cur_count} / {limit_display}</code>\n"
            f"<b>Workspace:</b> <code>upload_bots/{user_id}/</code>\n"
            f"<b>Security:</b> {emo('check')} Safety scan passed"
            f"</blockquote>\n\n"
            f"{emo('fire')} <i>Tap <b>Start Now</b> below to execute this script in the background!</i>",
            chat_id=message.chat.id,
            message_id=msg_wait.message_id,
            reply_markup=markup,
        )

        if not is_admin(user_id):
            user_uname = (
                f"@{message.from_user.username}"
                if message.from_user.username
                else f"{message.from_user.first_name}"
            )
            admin_markup = types.InlineKeyboardMarkup(row_width=1)
            admin_markup.row(
                ui_button("Download Script", callback_data=f"dscr_{fid}")
            )
            for adm_id in admin_ids:
                try:
                    safe_send_message(
                        adm_id,
                        f"🔔 <b>NEW SCRIPT UPLOADED</b> 🔔\n\n"
                        f"👤 <b>User:</b> {escape(user_uname)} (<code>{user_id}</code>)\n"
                        f"📁 <b>File Name:</b> <code>{escape(str(file_name))}</code>\n"
                        f"⏰ <b>Uploaded At:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"🔒 Scanner Check: Passed ✅\n\n"
                        f"⚡ Auto-Approved: Ready to run",
                        reply_markup=admin_markup,
                    )
                except Exception as adm_e:
                    logger.error(f"Failed to notify admin {adm_id}: {adm_e}")

    except Exception as e:
        logger.error(f"Upload error: {e}", exc_info=True)
        bot.reply_to(message, f"{emo('cross')} <b>Failed to process upload:</b> {escape(str(e))}")


def handle_all_callbacks(call):
    callback_context.answered_id = None
    try:
        if not call.message or call.message.chat.type != "private":
            answer_callback(
                call.id, "Open a private chat with this bot.", show_alert=True
            )
            return
        user_id = call.from_user.id
        if call.message.chat.id != user_id:
            answer_callback(call.id, "Permission denied.", show_alert=True)
            return
        data = call.data or ""
        if data == "btn_admin_panel" or data.startswith(
            ("adm_", "appr_", "rej_", "dscr_", "setdays_", "setlimit_", "confirm_kill_")
        ):
            if not is_admin(user_id):
                answer_callback(call.id, "Admin access is required.", show_alert=True)
                return
        if data.startswith(FILE_ACTION_PREFIXES):
            target_uid, file_name = parse_callback_target(data, FILE_ACTION_PREFIXES)
            if target_uid is None or not file_name:
                answer_callback(
                    call.id, "This button has expired. Open /menu.", show_alert=True
                )
                return
            if target_uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return
            if "/" in file_name or "\\" in file_name or ":" in file_name:
                answer_callback(call.id, "Invalid script path.", show_alert=True)
                return
            if data.startswith(
                (
                    "start_",
                    "r_prev_",
                    "r_fresh_",
                    "do_restart_",
                    "t_ar_",
                    "toggle_ar_",
                    "inp_",
                    "send_inp_",
                )
            ):
                if not has_active_access(target_uid):
                    answer_callback(
                        call.id, "This account has no active access.", show_alert=True
                    )
                    return
        if not data.startswith("adm_confirm_"):
            admin_states.pop(call.message.chat.id, None)
        cancel_pending_input(call.message.chat.id)
        dispatch_callback(call)
    except Exception:
        logger.exception("Callback handling failed.")
        answer_callback(
            call.id,
            "Unable to complete this action. Open /menu and try again.",
            show_alert=True,
        )
    finally:
        answer_callback(call.id)


def dispatch_callback(call):
    user_id = call.from_user.id
    chat_id = call.message.chat.id
    data = call.data

    try:
        panel = get_menu_panel(data, user_id)
        if panel is not None:
            text, markup = panel
            edit_panel(
                text,
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        elif data == "dismiss_prompt":
            try:
                bot.delete_message(chat_id, call.message.message_id)
            except Exception:
                answer_callback(call.id, "Dismissed.")

        elif data.startswith("mng_") or data.startswith("manage_"):
            pair = parse_callback_target(data, ["mng_", "manage_"])
            if not pair:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            uid, file_name = pair
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            fid = get_file_id(uid, file_name)

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                markup = types.InlineKeyboardMarkup(row_width=1)
                markup.add(
                    ui_button("Cancel & Delete Script", callback_data=f"del_{fid}", style="danger"),
                    ui_button("Back to Scripts", callback_data="btn_my_scripts"),
                )
                edit_panel(
                    f"<b>{emo('hourglass')} Pending Approval</b>\n\n"
                    f"<blockquote>"
                    f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                    f"<b>Status:</b> 🟡 Waiting for Admin Review"
                    f"</blockquote>\n\n"
                    f"You will receive an automatic notification as soon as it gets approved!",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
                return

            edit_panel(
                render_script_text(uid, file_name),
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=create_script_control_panel(uid, file_name),
            )

        elif data.startswith("start_"):
            uid, file_name = parse_callback_target(data, ["start_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                answer_callback(
                    call.id, "Script is pending Admin approval.", show_alert=True
                )
                return

            if is_bot_running(uid, file_name):
                answer_callback(
                    call.id, "Already running. Use Restart to start a new run."
                )
                return
            answer_callback(call.id, "Starting script...")
            ok, res = spawn_bot_process(
                uid, file_name, chat_id, auto_fill_inputs=False
            )
            if ok:
                edit_panel(
                    f"<b>{emo('check')} Script Started (PID: {res})</b>\n\n"
                    f"<blockquote>"
                    f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                    f"<b>PID:</b> <code>{res}</code>\n"
                    f"<b>State:</b> {emo('check')} Active in background"
                    f"</blockquote>\n\n"
                    f"{emo('fire')} <i>If this script asks for input, you will receive an instant prompt!</i>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )
            else:
                answer_callback(call.id, f"Failed: {res}", show_alert=True)
                edit_panel(
                    f"<b>{emo('cross')} Start Failed</b>\n\n<code>{escape(str(res))}</code>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )

        elif data.startswith("stop_"):
            uid, file_name = parse_callback_target(data, ["stop_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            script_key = f"{uid}_{file_name}"
            kill_process_tree(script_key)
            answer_callback(call.id, "Script stopped.")
            edit_panel(
                f"<b>{emo('cross')} Script Terminated</b>\n\n"
                f"<blockquote>"
                f"<code>{escape(str(file_name))}</code> process has been cleanly stopped."
                f"</blockquote>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=create_script_control_panel(uid, file_name),
            )

        elif data.startswith("ask_r_") or data.startswith("ask_restart_"):
            uid, file_name = parse_callback_target(data, ["ask_r_", "ask_restart_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                answer_callback(
                    call.id, "Script is pending Admin approval.", show_alert=True
                )
                return

            try:
                answer_callback(call.id)
            except Exception:
                pass

            fid = get_file_id(uid, file_name)
            saved_inputs, _ = get_saved_inputs_db(uid, file_name)
            markup = types.InlineKeyboardMarkup(row_width=1)
            if saved_inputs:
                markup.add(
                    ui_button(
                        "Replay Inputs (Auto-Fill)",
                        callback_data=f"r_prev_{fid}",
                        style="success",
                    )
                )
            markup.add(
                ui_button(
                    "Fresh Restart (Clear Cache)",
                    callback_data=f"r_fresh_{fid}",
                ),
                ui_button("Cancel", callback_data=f"mng_{fid}"),
            )

            edit_panel(
                f"<b>{emo('reset')} Restart Options</b>\n"
                f"<code>{escape(str(file_name))}</code>\n\n"
                f"<blockquote>"
                f"<b>Stored Inputs:</b> <code>{len(saved_inputs)} cached values</code>"
                f"</blockquote>\n\n"
                f"{emo('bolt')} <b>Replay Inputs:</b> Re-injects cached terminal values automatically.\n"
                f"{emo('edit')} <b>Fresh Restart:</b> Clears input memory and resets live log.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        elif data.startswith("r_prev_") or data.startswith("do_restart_prev_"):
            uid, file_name = parse_callback_target(
                data, ["r_prev_", "do_restart_prev_"]
            )
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                answer_callback(
                    call.id, "Script is pending Admin approval.", show_alert=True
                )
                return

            answer_callback(call.id, "Restarting with previous inputs...")
            kill_process_tree(f"{uid}_{file_name}", intentional=True)
            time.sleep(1.0)
            ok, res = spawn_bot_process(
                uid, file_name, chat_id, auto_fill_inputs=True
            )
            if ok:
                edit_panel(
                    f"<b>{emo('check')} Restarted with Saved Inputs</b>\n\n"
                    f"<blockquote>"
                    f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                    f"<b>PID:</b> <code>{res}</code>\n"
                    f"<b>Mode:</b> {emo('bolt')} <i>Auto-filling credentials</i>"
                    f"</blockquote>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )
            else:
                answer_callback(call.id, f"Restart failed: {res}", show_alert=True)
                edit_panel(
                    f"<b>{emo('cross')} Restart Failed</b>\n\n<code>{escape(str(res))}</code>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )

        elif data.startswith("r_fresh_") or data.startswith("do_restart_fresh_"):
            uid, file_name = parse_callback_target(
                data, ["r_fresh_", "do_restart_fresh_"]
            )
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                answer_callback(
                    call.id, "Script is pending Admin approval.", show_alert=True
                )
                return

            answer_callback(call.id, "Starting fresh...")
            kill_process_tree(f"{uid}_{file_name}", intentional=True)
            clear_saved_inputs_db(uid, file_name)
            user_folder = get_user_folder(uid)
            log_path = os.path.join(
                user_folder, f"{os.path.splitext(file_name)[0]}.log"
            )
            try:
                if os.path.exists(log_path):
                    with open(log_path, "w", encoding="utf-8") as f:
                        f.write(
                            f"--- FRESH RUN LOG STARTED [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ---\n"
                        )
            except Exception:
                pass

            time.sleep(1.0)
            ok, res = spawn_bot_process(
                uid, file_name, chat_id, auto_fill_inputs=False
            )
            if ok:
                edit_panel(
                    f"<b>{emo('check')} Restarted Fresh</b>\n\n"
                    f"<blockquote>"
                    f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                    f"<b>PID:</b> <code>{res}</code>\n"
                    f"<b>Cache:</b> {emo('reset')} <i>Cleared & Ready</i>"
                    f"</blockquote>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )
            else:
                answer_callback(call.id, f"Restart failed: {res}", show_alert=True)
                edit_panel(
                    f"<b>{emo('cross')} Restart Failed</b>\n\n<code>{escape(str(res))}</code>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_script_control_panel(uid, file_name),
                )

        elif data.startswith("t_ar_") or data.startswith("toggle_ar_"):
            uid, file_name = parse_callback_target(data, ["t_ar_", "toggle_ar_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            saved_inputs, curr_ar = get_saved_inputs_db(uid, file_name)
            new_ar = 0 if curr_ar == 1 else 1
            update_file_auto_restart_db(uid, file_name, new_ar)

            script_key = f"{uid}_{file_name}"
            if script_key in bot_scripts:
                bot_scripts[script_key]["auto_restart"] = new_ar
                bot_scripts[script_key]["last_restart_time"] = datetime.now()

            state_label = "Enabled (Every 30m)" if new_ar == 1 else "Disabled"
            answer_callback(call.id, f"Auto-Restart: {state_label}")

            edit_panel(
                render_script_text(uid, file_name),
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=create_script_control_panel(uid, file_name),
            )

        elif data.startswith("logs_"):
            uid, file_name = parse_callback_target(data, ["logs_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            fid = get_file_id(uid, file_name)
            user_folder = get_user_folder(uid)
            log_path = os.path.join(
                user_folder, f"{os.path.splitext(file_name)[0]}.log"
            )
            log_tail = "(No logs available yet)"
            if os.path.exists(log_path):
                tail_raw = read_log_tail(log_path, max_lines=30, max_bytes=32768)
                if tail_raw:
                    log_tail = clean_log_text(tail_raw, max_lines=15)

            log_tail = log_tail.encode("utf-16-le")[-5200:].decode(
                "utf-16-le", errors="ignore"
            )

            markup = types.InlineKeyboardMarkup(row_width=2)
            markup.row(
                ui_button("Refresh Logs", callback_data=f"logs_{fid}"),
                ui_button("Download Log File", callback_data=f"dlog_{fid}"),
            )
            markup.row(ui_button("Back to Script", callback_data=f"mng_{fid}"))

            current_time = datetime.now().strftime("%H:%M:%S")
            text = (
                f"<b>{emo('doc')} Live Script Output</b>\n"
                f"<code>{escape(file_name)}</code>\n"
                f"<i>Refreshed at {current_time} (server clock)</i>\n\n"
                f"<pre>{escape(log_tail)}</pre>"
            )

            try:
                edit_panel(
                    text,
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
                answer_callback(call.id, "Logs updated.")
            except telebot.apihelper.ApiTelegramException as e:
                if "message is not modified" in str(e).lower():
                    answer_callback(call.id, "Logs are up to date.")
                else:
                    raise

        elif data.startswith("dlog_") or data.startswith("downlog_"):
            uid, file_name = parse_callback_target(data, ["dlog_", "downlog_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            user_folder = get_user_folder(uid)
            log_path = os.path.join(
                user_folder, f"{os.path.splitext(file_name)[0]}.log"
            )
            if os.path.exists(log_path):
                answer_callback(call.id, "Sending log file...")
                with open(log_path, "rb") as f:
                    bot.send_document(
                        chat_id, f, caption=f"Full log: {escape(file_name)}"
                    )
            else:
                answer_callback(call.id, "No log file found.", show_alert=True)

        elif data.startswith("inp_") or data.startswith("send_inp_"):
            uid, file_name = parse_callback_target(data, ["inp_", "send_inp_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if not is_script_approved(uid, file_name) and not is_admin(user_id):
                answer_callback(
                    call.id, "Script is pending Admin approval.", show_alert=True
                )
                return

            if not is_bot_running(uid, file_name):
                answer_callback(
                    call.id, "Script is not currently running.", show_alert=True
                )
                return

            fid = get_file_id(uid, file_name)
            answer_callback(call.id)
            info = bot_scripts.get(f"{uid}_{file_name}")
            if not info:
                safe_send_message(
                    chat_id, "The script has stopped. Open controls to restart."
                )
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('note')} Terminal Input Dispatcher</b>\n"
                f"<code>{escape(file_name)}</code>\n\n"
                f"Type the next input value to send to the running script, or /cancel.\n\n"
                f"<blockquote><b>Privacy Note:</b> Values are stored for replay. "
                f"Only send values you trust this script to process.</blockquote>",
                process_user_terminal_input,
                uid,
                file_name,
                info["run_id"],
                back=f"mng_{fid}",
            )

        elif data.startswith("del_") or data.startswith("confirm_del_"):
            uid, file_name = parse_callback_target(data, ["del_", "confirm_del_"])
            if not uid or not file_name:
                answer_callback(
                    call.id, "Session expired, please refresh menu.", show_alert=True
                )
                return
            if uid != user_id and not is_admin(user_id):
                answer_callback(call.id, "Permission denied.", show_alert=True)
                return

            if data.startswith("del_"):
                fid = get_file_id(uid, file_name)
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    ui_button("Delete Permanently", callback_data=f"confirm_del_{fid}", style="danger"),
                    ui_button("Cancel", callback_data=f"mng_{fid}"),
                )
                edit_panel(
                    f"<b>{emo('cross')} Delete Script Confirmation</b>\n"
                    f"<code>{escape(file_name)}</code>\n\n"
                    f"<blockquote>This action terminates the running process and removes its file, log, and saved inputs.</blockquote>\n\n"
                    f"<b>This action cannot be undone.</b>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
                return
            answer_callback(call.id, "Deleting script...")
            kill_process_tree(f"{uid}_{file_name}")
            user_folder = get_user_folder(uid)
            script_path = os.path.join(user_folder, file_name)
            log_path = os.path.join(
                user_folder, f"{os.path.splitext(file_name)[0]}.log"
            )
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
                if os.path.exists(log_path):
                    os.remove(log_path)
            except Exception:
                pass

            remove_user_file_db(uid, file_name)
            answer_callback(call.id, "Script deleted.")

            edit_panel(
                f"<b>{emo('check')} Script Deleted</b>\n\n"
                f"Successfully removed <code>{escape(str(file_name))}</code>.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=create_script_list_menu(uid),
            )

        elif data == "adm_pending":
            if not is_admin(user_id):
                return
            pending = get_pending_scripts()
            if not pending:
                answer_callback(
                    call.id, "No scripts pending approval!", show_alert=True
                )
                return
            markup = types.InlineKeyboardMarkup(row_width=2)
            lines = [f"<b>{emo('hourglass')} Pending Scripts ({len(pending)})</b>\n"]
            for target_uid, fn in pending:
                fid = get_file_id(target_uid, fn)
                lines.append(
                    f"• User <code>{target_uid}</code>: <code>{escape(str(fn))}</code>"
                )
                markup.row(
                    ui_button(f"Approve {fn[:12]}", callback_data=f"appr_{fid}", style="success"),
                    ui_button(f"Reject {fn[:12]}", callback_data=f"rej_{fid}", style="danger"),
                )
                markup.row(
                    ui_button(f"Download {fn[:15]}", callback_data=f"dscr_{fid}")
                )
            markup.row(ui_button("Back to Admin", callback_data="btn_admin_panel"))
            edit_panel(
                "\n".join(lines),
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        elif data.startswith("appr_"):
            if not is_admin(user_id):
                answer_callback(call.id, "Admin only.", show_alert=True)
                return
            pair = parse_callback_target(data, ["appr_"])
            if not pair or not pair[0] or not pair[1]:
                answer_callback(
                    call.id, "Session expired, please refresh.", show_alert=True
                )
                return
            target_uid, file_name = pair
            set_script_approval_db(target_uid, file_name, 1)
            answer_callback(call.id, "Script Approved!")
            edit_panel(
                f"<b>{emo('check')} Script Approved</b>\n\n"
                f"<blockquote>"
                f"<b>User:</b> <code>{target_uid}</code>\n"
                f"<b>Script:</b> <code>{escape(str(file_name))}</code>\n"
                f"<b>State:</b> {emo('check')} Ready for execution"
                f"</blockquote>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    ui_button("Admin Panel", callback_data="btn_admin_panel")
                ),
            )
            target_fid = get_file_id(target_uid, file_name)
            user_markup = types.InlineKeyboardMarkup(row_width=2)
            user_markup.add(
                ui_button("Start Script", callback_data=f"start_{target_fid}", style="success"),
                ui_button("My Scripts", callback_data="btn_my_scripts"),
            )
            try:
                safe_send_message(
                    target_uid,
                    f"<b>{emo('fire')} Script Approved by Admin</b>\n\n"
                    f"Your script <code>{escape(str(file_name))}</code> has been verified and approved!\n"
                    f"You can now launch and monitor it from <b>My Scripts</b>.",
                    reply_markup=user_markup,
                )
            except Exception as notify_err:
                logger.error(f"Failed to notify user {target_uid} about approval: {notify_err}")

        elif data.startswith("rej_"):
            if not is_admin(user_id):
                answer_callback(call.id, "Admin only.", show_alert=True)
                return
            pair = parse_callback_target(data, ["rej_"])
            if not pair or not pair[0] or not pair[1]:
                answer_callback(
                    call.id, "Session expired, please refresh.", show_alert=True
                )
                return
            target_uid, file_name = pair
            kill_process_tree(f"{target_uid}_{file_name}")
            user_folder = get_user_folder(target_uid)
            script_path = os.path.join(user_folder, file_name)
            log_path = os.path.join(
                user_folder, f"{os.path.splitext(file_name)[0]}.log"
            )
            try:
                if os.path.exists(script_path):
                    os.remove(script_path)
                if os.path.exists(log_path):
                    os.remove(log_path)
            except Exception:
                pass
            remove_user_file_db(target_uid, file_name)
            answer_callback(call.id, "Script Rejected.")
            edit_panel(
                f"<b>{emo('cross')} Script Rejected & Removed</b>\n\n"
                f"User: <code>{target_uid}</code>\n"
                f"File: <code>{escape(str(file_name))}</code>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    ui_button("Admin Panel", callback_data="btn_admin_panel")
                ),
            )
            try:
                safe_send_message(
                    target_uid,
                    f"<b>{emo('cross')} Script Rejected</b>\n\n"
                    f"Your script <code>{escape(str(file_name))}</code> was reviewed and declined by Admin.",
                )
            except Exception as notify_err:
                logger.error(f"Failed to notify user {target_uid}: {notify_err}")

        elif data.startswith("dscr_"):
            if not is_admin(user_id):
                answer_callback(call.id, "Admin only.", show_alert=True)
                return
            pair = parse_callback_target(data, ["dscr_"])
            if not pair or not pair[0] or not pair[1]:
                answer_callback(
                    call.id, "Session expired, please refresh.", show_alert=True
                )
                return
            target_uid, file_name = pair
            user_folder = get_user_folder(target_uid)
            script_path = os.path.join(user_folder, file_name)
            if os.path.exists(script_path):
                answer_callback(call.id, "Sending file...")
                with open(script_path, "rb") as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption=f"📄 Script File: {escape(str(file_name))} (User: {target_uid})",
                    )
            else:
                answer_callback(call.id, "File not found.", show_alert=True)

        elif data.startswith("adm_confirm_"):
            confirmation = admin_states.pop(chat_id, None)
            if (
                not confirmation
                or confirmation["actor_id"] != user_id
                or data != f"adm_confirm_{confirmation['nonce']}"
            ):
                answer_callback(
                    call.id, "This confirmation has expired.", show_alert=True
                )
                return
            answer_callback(call.id, "Confirmed. Processing...")
            if confirmation["action"] == "broadcast":
                send_broadcast(chat_id, confirmation["payload"])
            elif confirmation["action"] == "revoke":
                target_uid = confirmation["payload"]
                if is_admin(target_uid):
                    safe_send_message(
                        chat_id, "Admin access cannot be revoked through subscriptions."
                    )
                    return
                for script_key in list(bot_scripts):
                    if script_key.startswith(f"{target_uid}_"):
                        kill_process_tree(script_key)
                revoke_subscription_db(target_uid)
                edit_panel(
                    f"<b>{emo('cross')} Access Revoked</b>\n\n"
                    f"User <code>{target_uid}</code> subscription cancelled and processes stopped.",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=create_admin_panel_menu(),
                )

        elif data == "adm_grant":
            if not is_admin(user_id):
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('key')} Grant / Extend Access</b>\n\nSend the Telegram user ID to grant access.",
                admin_step_grant_user_id,
                back="btn_admin_panel",
            )

        elif data == "adm_limit":
            if not is_admin(user_id):
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('action')} Script Limit Adjuster</b>\n\nSend the Telegram user ID to modify limit.",
                admin_step_limit_user_id,
                back="btn_admin_panel",
            )

        elif data == "adm_revoke":
            if not is_admin(user_id):
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('cross')} Revoke User Access</b>\n\nSend the Telegram user ID to revoke.",
                admin_step_revoke_user_id,
                back="btn_admin_panel",
            )

        elif data == "adm_live" or data.startswith("adm_live_page_"):
            if not is_admin(user_id):
                return
            page = (
                int(data.rsplit("_", 1)[1]) if data.startswith("adm_live_page_") else 0
            )
            entries, page, pages = paginate(list(bot_scripts.items()), page)
            markup = types.InlineKeyboardMarkup(row_width=1)
            text_lines = [
                f"<b>{emo('stats')} Live Server Processes</b>\n<i>Page {page + 1} of {pages}</i>\n"
            ]
            if not entries:
                text_lines.append(f"<blockquote>{emo('info')} No background scripts currently running.</blockquote>")
            for sk, info in entries:
                uid = info["user_id"]
                fn = info["file_name"]
                fid = get_file_id(uid, fn)
                pid = info["process"].pid
                uptime = str(datetime.now() - info["start_time"]).split(".")[0]
                text_lines.append(
                    f"• <b>{escape(fn[:60])}</b> (PID: <code>{pid}</code> | User: <code>{uid}</code> | {uptime})"
                )
                markup.add(
                    ui_button(f"Stop {pid} | {fn}", callback_data=f"adm_kill_{fid}", style="danger")
                )
            add_page_buttons(markup, page, pages, "adm_live_page_")
            markup.row(ui_button("Refresh", callback_data=f"adm_live_page_{page}"))
            markup.add(ui_button("Back to Admin", callback_data="btn_admin_panel"))
            edit_panel(
                "\n".join(text_lines),
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        elif data.startswith("adm_kill_") or data.startswith("confirm_kill_"):
            if not is_admin(user_id):
                return
            target_uid, file_name = parse_callback_target(
                data, ["adm_kill_", "confirm_kill_"]
            )
            target_sk = f"{target_uid}_{file_name}"
            if data.startswith("adm_kill_"):
                fid = get_file_id(target_uid, file_name)
                markup = types.InlineKeyboardMarkup()
                markup.row(
                    ui_button("Terminate Process", callback_data=f"confirm_kill_{fid}", style="danger"),
                    ui_button("Cancel", callback_data="adm_live"),
                )
                edit_panel(
                    f"<b>{emo('cross')} Stop Process Confirmation</b>\n\n"
                    f"<code>{escape(file_name)}</code>\nOwner: <code>{target_uid}</code>",
                    chat_id=chat_id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
                return
            answer_callback(call.id, "Stopping process...")
            kill_process_tree(target_sk)
            answer_callback(call.id, f"Killed {target_sk}")
            edit_panel(
                f"<b>{emo('check')} Process Terminated</b>\n\n<code>{escape(str(target_sk))}</code> stopped successfully.",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    ui_button("Admin Panel", callback_data="btn_admin_panel")
                ),
            )

        elif data.startswith("adm_user_page_"):
            target_uid, page = data[len("adm_user_page_") :].split("_")
            text, markup = render_user_details(parse_user_id(target_uid), int(page))
            edit_panel(
                text,
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        elif data == "adm_user_search":
            if not is_admin(user_id):
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('person')} Search User Account</b>\n\nSend the Telegram numeric user ID.",
                admin_step_search_user,
                back="btn_admin_panel",
            )

        elif data == "adm_broadcast":
            if not is_admin(user_id):
                return
            request_text_input(
                chat_id,
                user_id,
                f"<b>{emo('megaphone')} Broadcast Dispatcher</b>\n\nSend the message text to broadcast to all users.",
                admin_step_broadcast,
                back="btn_admin_panel",
            )

        elif data.startswith("setdays_"):
            if not is_admin(user_id):
                return
            _, uid_str, days_str = data.split("_")
            target_uid = int(uid_str)
            days = int(days_str)
            if target_uid <= 0 or days not in (1, 7, 15, 30, 60, 365):
                answer_callback(call.id, "Invalid access duration.", show_alert=True)
                return
            current_expiry = user_subscriptions.get(target_uid, {}).get(
                "expiry", datetime.min
            )
            expiry = max(datetime.now(), current_expiry) + timedelta(days=days)
            curr_limit = get_user_script_limit(target_uid)
            save_subscription_db(target_uid, expiry, curr_limit)
            answer_callback(call.id, f"Access granted for {days} days!")
            edit_panel(
                f"<b>{emo('check')} Access Granted</b>\n\n"
                f"<blockquote>"
                f"<b>User:</b> <code>{target_uid}</code>\n"
                f"<b>Duration:</b> <code>{days} Days</code>\n"
                f"<b>Expiry:</b> <code>{expiry.strftime('%Y-%m-%d %H:%M')}</code>\n"
                f"<b>Quota:</b> <code>{curr_limit} scripts</code>"
                f"</blockquote>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    ui_button("Admin Panel", callback_data="btn_admin_panel")
                ),
            )

        elif data.startswith("setlimit_"):
            if not is_admin(user_id):
                return
            _, uid_str, limit_str = data.split("_")
            target_uid = int(uid_str)
            limit = int(limit_str)
            sub = user_subscriptions.get(target_uid)
            if (
                limit not in (1, 2, 3, 5, 10, 50, 999)
                or not sub
                or not has_active_access(target_uid)
            ):
                answer_callback(
                    call.id,
                    "Grant active access first, then choose a valid limit.",
                    show_alert=True,
                )
                return
            expiry = sub["expiry"]
            save_subscription_db(target_uid, expiry, limit)
            answer_callback(call.id, f"Limit set to {limit} scripts!")
            edit_panel(
                f"<b>{emo('check')} Script Limit Updated</b>\n\n"
                f"<blockquote>"
                f"<b>User:</b> <code>{target_uid}</code>\n"
                f"<b>Quota:</b> <b>{limit}</b> scripts"
                f"</blockquote>",
                chat_id=chat_id,
                message_id=call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    ui_button("Admin Panel", callback_data="btn_admin_panel")
                ),
            )

        else:
            answer_callback(
                call.id,
                "This button is no longer available. Open /menu.",
                show_alert=True,
            )

    except Exception:
        logger.exception("Callback action failed.")
        safe_send_message(
            chat_id,
            f"{emo('cross')} This action could not be completed. Please try again.",
            reply_markup=create_main_menu(user_id),
        )


def process_user_terminal_input(message, target_uid, file_name, run_id=None):
    chat_id = message.chat.id
    text = (message.text or "").strip()

    if text.lower() == "/cancel":
        bot.reply_to(message, f"{emo('cross')} Input submission cancelled.")
        return

    script_key = f"{target_uid}_{file_name}"
    info = bot_scripts.get(script_key)

    if message.from_user.id != target_uid and not is_admin(message.from_user.id):
        bot.reply_to(message, "Permission denied.")
        return
    if not has_active_access(target_uid):
        bot.reply_to(message, "This account has no active access.")
        return
    if run_id is not None and (not info or info.get("run_id") != run_id):
        bot.reply_to(message, "The script has restarted. Open Send Input again.")
        return

    if not info or not is_bot_running(target_uid, file_name):
        bot.reply_to(
            message,
            f"{emo('warn')} Script <code>{escape(str(file_name))}</code> is not running.",
        )
        return

    proc = info.get("process")
    if not proc or proc.poll() is not None or not proc.stdin:
        bot.reply_to(message, f"{emo('warn')} Terminal stdin is not available.")
        return

    try:
        proc.stdin.write(text + "\n")
        proc.stdin.flush()
        save_single_input_db(target_uid, file_name, text)
        if "saved_inputs" in info:
            info["saved_inputs"].append(text)

        bot.reply_to(
            message,
            f"<b>{emo('check')} Input Transmitted</b>\n\n"
            f"Input injected to <code>{escape(str(file_name))}</code>!\n"
            f"Check <b>Live Logs</b> to verify script progress.",
            reply_markup=types.InlineKeyboardMarkup().add(
                ui_button(
                    "Live logs",
                    callback_data=f"logs_{get_file_id(target_uid, file_name)}",
                ),
                ui_button(
                    "Script controls",
                    callback_data=f"mng_{get_file_id(target_uid, file_name)}",
                ),
            ),
        )
    except Exception as e:
        logger.error(f"Error injecting stdin: {e}")
        bot.reply_to(message, f"{emo('cross')} Failed to deliver input: {e}")


def admin_step_grant_user_id(message):
    try:
        target_uid = parse_user_id(message.text)
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.row(
            ui_button("1 Day", callback_data=f"setdays_{target_uid}_1"),
            ui_button("7 Days", callback_data=f"setdays_{target_uid}_7"),
            ui_button("15 Days", callback_data=f"setdays_{target_uid}_15"),
        )
        markup.row(
            ui_button("30 Days (1M)", callback_data=f"setdays_{target_uid}_30"),
            ui_button("60 Days (2M)", callback_data=f"setdays_{target_uid}_60"),
            ui_button("365 Days", callback_data=f"setdays_{target_uid}_365"),
        )
        markup.add(ui_button("Cancel", callback_data="btn_admin_panel"))

        safe_send_message(
            message.chat.id,
            f"Select duration for User ID: <code>{target_uid}</code>:",
            reply_markup=markup,
        )
    except ValueError:
        bot.reply_to(message, f"{emo('cross')} Invalid User ID. Must be numeric.")


def admin_step_limit_user_id(message):
    try:
        target_uid = parse_user_id(message.text)
        markup = types.InlineKeyboardMarkup(row_width=3)
        markup.row(
            ui_button("1 File", callback_data=f"setlimit_{target_uid}_1"),
            ui_button("2 Files", callback_data=f"setlimit_{target_uid}_2"),
            ui_button("3 Files", callback_data=f"setlimit_{target_uid}_3"),
        )
        markup.row(
            ui_button("5 Files", callback_data=f"setlimit_{target_uid}_5"),
            ui_button("10 Files", callback_data=f"setlimit_{target_uid}_10"),
            ui_button("50 Files", callback_data=f"setlimit_{target_uid}_50"),
        )
        markup.add(ui_button("Cancel", callback_data="btn_admin_panel"))

        safe_send_message(
            message.chat.id,
            f"Select upload limit for User ID: <code>{target_uid}</code>:",
            reply_markup=markup,
        )
    except ValueError:
        bot.reply_to(message, f"{emo('cross')} Invalid User ID. Must be numeric.")


def admin_step_revoke_user_id(message):
    try:
        target_uid = parse_user_id(message.text)
        if is_admin(target_uid):
            bot.reply_to(
                message, "Admin access cannot be revoked through subscriptions."
            )
            return
        confirm_admin_action(message, "revoke", target_uid)
    except ValueError:
        bot.reply_to(message, f"{emo('cross')} Invalid User ID.")


def render_user_details(target_uid, page=0):
    files = user_files.get(target_uid, [])
    entries, page, pages = paginate(files, page)
    limit_str = "∞ Unlimited" if is_unlimited_scripts(target_uid) else str(get_user_script_limit(target_uid))
    text = (
        f"<b>{emo('person')} User Profile Audit</b>\n"
        f"<i>Page {page + 1} of {pages}</i>\n\n"
        f"<blockquote>"
        f"<b>Telegram ID:</b> <code>{target_uid}</code>\n"
        f"<b>Days Left:</b> <code>{escape(get_user_days_left(target_uid))}</code>\n"
        f"<b>Hosted Quota:</b> <code>{len(files)} / {limit_str}</code>"
        f"</blockquote>"
    )
    markup = types.InlineKeyboardMarkup(row_width=1)
    for file_name, file_type in entries:
        status = "Running" if is_bot_running(target_uid, file_name) else "Stopped"
        markup.row(
            ui_button(
                f"{status} | {file_name}",
                callback_data=f"mng_{get_file_id(target_uid, file_name)}",
            )
        )
    add_page_buttons(markup, page, pages, f"adm_user_page_{target_uid}_")
    markup.row(ui_button("Back to admin", callback_data="btn_admin_panel"))
    return text, markup


def admin_step_search_user(message):
    try:
        text, markup = render_user_details(parse_user_id(message.text))
        safe_send_message(message.chat.id, text, reply_markup=markup)
    except ValueError:
        bot.reply_to(message, "Invalid user ID. Send a positive numeric Telegram ID.")


def admin_step_broadcast(message):
    text = message.text or message.caption
    if not text or text.strip().lower() == "/cancel":
        bot.reply_to(message, f"{emo('cross')} Broadcast cancelled.")
        return
    if len(text.encode("utf-16-le")) // 2 > 3500:
        bot.reply_to(
            message,
            "Announcement is too long. Use up to 3500 characters.",
        )
        return
    confirm_admin_action(message, "broadcast", text)


def send_broadcast(chat_id, text):
    sent = 0
    failed = 0
    for uid in list(active_users):
        try:
            safe_send_message(uid, f"<b>{emo('megaphone')} Announcement</b>\n\n{escape(text)}")
            sent += 1
            time.sleep(0.05)
        except Exception:
            failed += 1

    safe_send_message(
        chat_id,
        f"<b>{emo('check')} Broadcast Completed</b>\n\n"
        f"• Delivered: <code>{sent}</code>\n"
        f"• Failed / Blocked: <code>{failed}</code>",
        reply_markup=types.InlineKeyboardMarkup().add(
            ui_button("Admin Panel", callback_data="btn_admin_panel")
        ),
    )


def full_system_cleanup():
    logger.info("Cleaning up all background scripts on exit...")
    for sk in list(bot_scripts.keys()):
        try:
            kill_process_tree(sk)
        except Exception:
            pass


def register_handlers():
    bot.register_message_handler(cmd_start, commands=["start", "menu", "cancel"])
    bot.register_message_handler(cmd_admin, commands=["admin"])
    bot.register_message_handler(handle_uploaded_file, content_types=["document"])
    bot.register_message_handler(
        handle_menu_message,
        content_types=["text"],
        func=lambda message: menu_action_from_text(message.text) is not None,
    )
    bot.register_callback_query_handler(handle_all_callbacks, func=lambda call: True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "Set TELEGRAM_BOT_TOKEN to your bot token before starting."
        )
    bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
    init_db()
    load_data()
    register_handlers()
    atexit.register(full_system_cleanup)
    threading.Thread(target=auto_restart_worker, daemon=True).start()
    threading.Thread(target=expiry_checker_worker, daemon=True).start()
    logger.info("⚡ Starting File Hosting Bot Runner...")
    keep_alive()

    try:
        bot.set_my_commands(
            [
                types.BotCommand("start", "Open dashboard"),
                types.BotCommand("menu", "Open dashboard"),
                types.BotCommand("cancel", "Cancel pending input"),
            ]
        )
    except Exception:
        logger.warning("Could not register the command menu.")

    try:
        bot.remove_webhook()
    except Exception:
        pass

    while True:
        try:
            logger.info("Connecting to Telegram Bot API (Polling)...")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=20,
                skip_pending=True,
                allowed_updates=["message", "callback_query"],
            )
        except Exception as e:
            logger.error(f"Polling crashed: {e}", exc_info=True)
            time.sleep(5)

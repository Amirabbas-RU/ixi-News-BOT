import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import re
import sys
from logger import logger
import set_path
import config

ENV_PATH = os.path.join(set_path.base_path, "main.env")
ITEMS_PER_PAGE = 20
user_state = {}


def _read_env_value(key: str) -> str:
    with open(ENV_PATH, encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"^{key}\s*=\s*'(.*?)'", text, re.MULTILINE | re.DOTALL)
    if not m:
        m = re.search(rf'^{key}\s*=\s*"(.*?)"', text, re.MULTILINE | re.DOTALL)
    if not m:
        m = re.search(rf"^{key}\s*=\s*(\S+)", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


_panel_token = _read_env_value("BOT_PANEL_BOT_TOKEN")
BOT_TOKEN = _panel_token if _panel_token else _read_env_value("TELEGRAM_BOT_TOKEN")
ADMIN_ID = _read_env_value("ADMIN_TELEGRAM_ID")
ADMIN_ID = int(ADMIN_ID) if ADMIN_ID.isdigit() else 0


# ---------------------------------<< env helpers >>---------------------------------
def _read_env_section(key: str):
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    start = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(rf"^{re.escape(key)}\s*=", stripped):
            start = i
    if start < 0:
        return lines, 0, 0
    value_part = lines[start].strip()
    if "='" in value_part:
        end = start
        while end < len(lines) and not lines[end].strip().endswith("'"):
            end += 1
        end = end + 1 if end < len(lines) else start + 1
    else:
        end = start + 1
    return lines, start, end


def _get_env_raw(key: str) -> str:
    _, s, e = _read_env_section(key)
    if s == e:
        return ""
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    raw = "".join(lines[s:e])
    raw = re.sub(r"\s*#.*$", "", raw.strip(), flags=re.MULTILINE)
    m = re.match(
        rf"^{key}\s*=\s*(?P<q>['\"]?)(?P<val>.*?)(?P=q)\s*$", raw, re.DOTALL
    )
    return m.group("val").strip() if m else raw.split("=", 1)[-1].strip().strip("'\"")


def _get_env_json(key: str) -> dict:
    raw = _get_env_raw(key)
    try:
        return json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return {}


def _set_env_line(key: str, value: str):
    with open(ENV_PATH, encoding="utf-8") as f:
        lines = f.readlines()
    match_indices = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if re.match(rf"^{re.escape(key)}\s*=", stripped):
            match_indices.append(i)
    if match_indices:
        insert_pos = match_indices[-1]
        for idx in reversed(match_indices):
            del lines[idx]
        lines.insert(insert_pos, f"{key} = {value}\n")
    else:
        lines.append(f"{key} = {value}\n")
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


def _fmt_keywords(data: dict) -> str:
    by_impact = {}
    for k, v in data.items():
        by_impact.setdefault(v, []).append(k)
    lines = ["{"]
    all_entries = []
    for impact in sorted(by_impact.keys(), reverse=True):
        for kw in sorted(by_impact[impact], key=str.lower):
            all_entries.append((kw, impact))
    for i, (kw, impact) in enumerate(all_entries):
        comma = "," if i < len(all_entries) - 1 else ""
        lines.append(f'"{kw}":{impact}{comma}')
    lines.append("}")
    return "\n".join(lines)


def _set_env_json(key: str, data: dict):
    if key == "HIGH_IMPACT_KEYWORDS":
        json_str = _fmt_keywords(data)
    else:
        json_str = json.dumps(data, indent=0, ensure_ascii=False)
    lines, s, e = _read_env_section(key)
    new_val = f"{key}='{json_str}'\n"
    if s == e:
        lines.append(new_val)
    else:
        lines[s:e] = [new_val]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)


# ---------------------------------<< helpers >>---------------------------------
def _sync_runtime():
    config.reload_env()
    main_mod = sys.modules.get("__main__")
    if main_mod is None or not hasattr(main_mod, "reload_config"):
        main_mod = sys.modules.get("main")
    if main_mod and hasattr(main_mod, "reload_config"):
        main_mod.reload_config()


def _btn(text, cb_data):
    return InlineKeyboardButton(text, callback_data=cb_data)


def _main_menu():
    kbd = InlineKeyboardMarkup(row_width=2)
    kbd.add(
        _btn("📰 Sources", "src"),
        _btn("🤖 Model", "model"),
        _btn("🔑 Keywords", "kw:pg:0"),
        _btn("📊 Scores", "scores"),
        _btn("⚙️ Env", "env"),
    )
    return kbd


def _back_kbd(cb="menu"):
    return InlineKeyboardMarkup().add(_btn("◀️ Back", cb))


def _is_admin(user_id):
    return not ADMIN_ID or user_id == ADMIN_ID


# ---------------------------------<< register handlers >>---------------------------------
def register_handlers(bot):
    @bot.message_handler(commands=["start", "help"])
    def cmd_start(message):
        if not _is_admin(message.from_user.id):
            return
        bot.send_message(
            message.chat.id,
            "📡 <b>Control Bot</b>\nSelect a section:\n\n✅ Changes apply immediately — no restart needed.",
            parse_mode="HTML",
            reply_markup=_main_menu(),
        )

    # ---- Sources ----
    def _show_sources(chat_id, msg_id=None):
        keys = [
            ("CNBC_RSS_URL", "CNBC"),
            ("YAHOO_RSS_URL", "Yahoo"),
            ("REUTERS_RSS_URL", "Reuters"),
            ("INVESTING_RSS_URL", "Investing"),
            ("FOREXFACTORY_CALENDAR_URL", "ForexFactory"),
        ]
        source_scores = _get_env_json("SOURCE_SCORE")
        text = "<b>📰 RSS Sources</b>\n\n"
        kbd = InlineKeyboardMarkup(row_width=2)
        row_btns = []
        for env_key, label in keys:
            val = _get_env_raw(env_key)
            score = source_scores.get(label, 0)
            is_on = bool(val) and score != 0
            status = "✅" if is_on else "❌"
            short = val[:50] + "..." if len(val) > 50 else val
            text += f"{status} <b>{label}</b>\n<code>{short}</code>\n\n"
            row_btns.append(_btn(f"✏️ {label}", f"src_edit:{env_key}"))
        kbd.add(*row_btns[0:2])
        kbd.add(*row_btns[2:4])
        kbd.add(*row_btns[4:])
        kbd.add(_btn("◀️ Back", "menu"))
        if msg_id:
            bot.edit_message_text(
                text, chat_id, msg_id, parse_mode="HTML", reply_markup=kbd
            )
        else:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kbd)

    @bot.callback_query_handler(func=lambda c: c.data == "src")
    def cb_sources(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        _show_sources(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("src_edit:"))
    def cb_src_edit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        key = call.data.split(":", 1)[1]
        user_state[call.from_user.id] = {"mode": "src_edit", "key": key}
        bot.send_message(
            call.message.chat.id,
            f"Send the new URL for <b>{key}</b>:",
            parse_mode="HTML",
        )
        bot.answer_callback_query(call.id)

    # ---- Model ----
    def _show_model(chat_id, msg_id=None):
        api_key = _read_env_value("OPENROUTER_API_KEY")
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "not set"
        model = _get_env_raw("OPENROUTER_MODEL")
        base = _get_env_raw("OPENROUTER_BASE_URL")
        text = (
            f"<b>🤖 OpenRouter</b>\n\n"
            f"<b>Model:</b> <code>{model}</code>\n"
            f"<b>API Key:</b> <code>{masked}</code>\n"
            f"<b>Base URL:</b> <code>{base}</code>"
        )
        kbd = InlineKeyboardMarkup(row_width=1)
        kbd.add(
            _btn("✏️ Model", "model_edit"),
            _btn("✏️ API Key", "apikey_edit"),
            _btn("◀️ Back", "menu"),
        )
        if msg_id:
            bot.edit_message_text(
                text, chat_id, msg_id, parse_mode="HTML", reply_markup=kbd
            )
        else:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kbd)

    @bot.callback_query_handler(func=lambda c: c.data == "model")
    def cb_model(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        _show_model(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "model_edit")
    def cb_model_edit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        user_state[call.from_user.id] = {"mode": "model_edit"}
        bot.send_message(call.message.chat.id, "Send the new model name:")
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "apikey_edit")
    def cb_apikey_edit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        user_state[call.from_user.id] = {"mode": "apikey_edit"}
        bot.send_message(call.message.chat.id, "Send the new API key:")
        bot.answer_callback_query(call.id)

    # ---- Keywords ----
    def _show_keywords_page(chat_id, page, msg_id=None):
        data = _get_env_json("HIGH_IMPACT_KEYWORDS")
        sorted_kw = sorted(data.items(), key=lambda x: -x[1])
        total = len(sorted_kw)
        total_pages = max(1, (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
        start = page * ITEMS_PER_PAGE
        end = min(start + ITEMS_PER_PAGE, total)
        page_items = sorted_kw[start:end]

        text = f"<b>🔑 Keywords</b> ({total}) — Page {page + 1}/{total_pages}\n\n"
        text += "\n".join(f"<b>{w}</b>: {s}" for w, s in page_items)

        kbd = InlineKeyboardMarkup(row_width=5)
        if total_pages > 1:
            row = []
            if page > 0:
                row.append(_btn("◀️", f"kw:pg:{page - 1}"))
            row.append(_btn(f"{page + 1}/{total_pages}", "kw:nop"))
            if page < total_pages - 1:
                row.append(_btn("▶️", f"kw:pg:{page + 1}"))
            kbd.row(*row)
        kbd.row(_btn("➕ Add", "kw:add"), _btn("🗑️ Delete", "kw:del"))
        kbd.row(_btn("◀️ Back", "menu"))

        if msg_id:
            bot.edit_message_text(
                text, chat_id, msg_id, parse_mode="HTML", reply_markup=kbd
            )
        else:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kbd)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("kw:pg:"))
    def cb_kw_page(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        page = int(call.data.split(":")[2])
        if page < 0:
            bot.answer_callback_query(call.id)
            return
        _show_keywords_page(call.message.chat.id, page, call.message.message_id)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "kw:nop")
    def cb_kw_nop(call):
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "kw:add")
    def cb_kw_add(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        user_state[call.from_user.id] = {"mode": "kw_add"}
        bot.send_message(call.message.chat.id, "Send the keyword name:")
        bot.answer_callback_query(call.id)

    def _show_score_picker(chat_id, word):
        kbd = InlineKeyboardMarkup(row_width=5)
        kbd.add(*(_btn(str(i), f"kw:score:{i}") for i in range(1, 6)))
        kbd.add(_btn("◀️ Cancel", "kw:pg:0"))
        bot.send_message(
            chat_id,
            f"Select impact level for <b>{word}</b>:",
            parse_mode="HTML",
            reply_markup=kbd,
        )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("kw:score:"))
    def cb_kw_score(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        score = int(call.data.split(":")[2])
        state = user_state.get(call.from_user.id, {})
        word = state.get("pending_word", "")
        if not word:
            bot.answer_callback_query(call.id, "❌ No pending keyword")
            return
        data = _get_env_json("HIGH_IMPACT_KEYWORDS")
        data[word] = score
        _set_env_json("HIGH_IMPACT_KEYWORDS", data)
        _sync_runtime()
        user_state.pop(call.from_user.id, None)
        bot.edit_message_text(
            f"✅ <b>{word}</b> = {score}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=_back_kbd("kw:pg:0"),
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data == "kw:del")
    def cb_kw_del(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        user_state[call.from_user.id] = {"mode": "kw_del"}
        bot.send_message(call.message.chat.id, "Send the keyword name to delete:")
        bot.answer_callback_query(call.id)

    # ---- Scores ----
    def _show_scores(chat_id, msg_id=None):
        data = _get_env_json("SOURCE_SCORE")
        total = sum(data.values())
        text = f"<b>📊 Source Scores</b> (total: {total})\n\n"
        kbd = InlineKeyboardMarkup(row_width=1)
        for name, score in sorted(data.items()):
            text += f"<b>{name}</b>: {score}\n"
            kbd.add(_btn(f"✏️ {name}", f"score_edit:{name}"))
        kbd.add(_btn("◀️ Back", "menu"))
        if msg_id:
            bot.edit_message_text(
                text, chat_id, msg_id, parse_mode="HTML", reply_markup=kbd
            )
        else:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kbd)

    @bot.callback_query_handler(func=lambda c: c.data == "scores")
    def cb_scores(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        _show_scores(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    def _show_source_score_picker(chat_id, name):
        kbd = InlineKeyboardMarkup(row_width=6)
        kbd.add(
            _btn("❌ Off", "src_score:0"),
            *(_btn(str(i), f"src_score:{i}") for i in range(1, 6)),
        )
        kbd.add(_btn("◀️ Cancel", "scores"))
        bot.send_message(
            chat_id,
            f"Select score for <b>{name}</b>:",
            parse_mode="HTML",
            reply_markup=kbd,
        )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("score_edit:"))
    def cb_score_edit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        name = call.data.split(":", 1)[1]
        user_state[call.from_user.id] = {"mode": "src_score", "name": name}
        _show_source_score_picker(call.message.chat.id, name)
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("src_score:"))
    def cb_src_score(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        score = int(call.data.split(":")[1])
        state = user_state.get(call.from_user.id, {})
        name = state.get("name", "")
        if not name:
            bot.answer_callback_query(call.id, "❌ No source selected")
            return
        data = _get_env_json("SOURCE_SCORE")
        data[name] = score
        _set_env_json("SOURCE_SCORE", data)
        _sync_runtime()
        user_state.pop(call.from_user.id, None)
        bot.edit_message_text(
            f"✅ <b>{name}</b> = {score}",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=_back_kbd("scores"),
        )
        bot.answer_callback_query(call.id)

    # ---- Env ----
    def _get_env_line_raw(key: str) -> str:
        _, s, e = _read_env_section(key)
        if s == e:
            return ""
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.readlines()
        return "".join(lines[s:e]).strip()

    def _show_env(chat_id, msg_id=None):
        env_keys = [
            ("NEWS_UPDATE_INTERVAL_MINUTES", "Update Interval"),
            ("MIN_IMPACT_SCORE", "Min Impact"),
            ("FOREX_MIN_SCORE", "Forex Min"),
            ("MAX_NEWS_PER_DAY", "Max News/Day"),
            ("FOREX_ALERT_IMPACTS", "Alert Impacts"),
            ("ENABLE_FOREX_ALERTS", "Enable Forex"),
            ("RESET_DATABASE", "Reset DB"),
        ]
        text = "<b>⚙️ Config</b>\n\n"
        kbd = InlineKeyboardMarkup(row_width=2)
        row_buttons = []
        for key, label in env_keys:
            raw = _get_env_line_raw(key)
            if raw:
                no_comment = re.sub(r"\s+#.*$", "", raw).strip()
                parts = re.split(r"\s*=\s*", no_comment, maxsplit=1)
                if len(parts) == 2:
                    display = f"<b>{parts[0]}</b> = <code>{parts[1]}</code>"
                else:
                    display = f"<b>{key}</b>"
            else:
                display = f"<b>{key}</b>"
            text += f"{display}\n"
            row_buttons.append(_btn(f"✏️ {label}", f"env_edit:{key}"))
            if len(row_buttons) == 2:
                kbd.row(*row_buttons)
                row_buttons = []
        if row_buttons:
            kbd.row(*row_buttons)
        kbd.row(_btn("◀️ Back", "menu"))
        if msg_id:
            bot.edit_message_text(
                text, chat_id, msg_id, parse_mode="HTML", reply_markup=kbd
            )
        else:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=kbd)

    @bot.callback_query_handler(func=lambda c: c.data == "env")
    def cb_env(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        _show_env(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id)

    def _show_bool_picker(chat_id, msg_id, key):
        raw = _get_env_raw(key)
        current = raw.strip().lower() == "true"
        kbd = InlineKeyboardMarkup(row_width=2)
        kbd.add(
            _btn(f"{'✅' if current else '❌'} True", f"toggle_bool:{key}:true"),
            _btn(f"{'✅' if not current else '❌'} False", f"toggle_bool:{key}:false"),
        )
        kbd.add(_btn("Done", "env"))
        label = key.replace("_", " ").title()
        if msg_id:
            bot.edit_message_text(
                f"<b>{label}</b>\n\nSelect value:",
                chat_id, msg_id, parse_mode="HTML", reply_markup=kbd,
            )
        else:
            bot.send_message(
                chat_id,
                f"<b>{label}</b>\n\nSelect value:",
                parse_mode="HTML", reply_markup=kbd,
            )

    def _show_impact_picker(chat_id, msg_id=None):
        raw = _get_env_raw("FOREX_ALERT_IMPACTS")
        selected = {x.strip() for x in raw.split(",")} if raw else set()
        all_impacts = ["High", "Medium", "Low"]
        kbd = InlineKeyboardMarkup(row_width=1)
        for impact in all_impacts:
            status = "✅" if impact in selected else "❌"
            kbd.add(_btn(f"{status} {impact}", f"toggle_impact:{impact}"))
        kbd.add(_btn("Done", "env"))
        if msg_id:
            bot.edit_message_text(
                "<b>FOREX_ALERT_IMPACTS</b>\n\nSelect impact levels to alert:",
                chat_id,
                msg_id,
                parse_mode="HTML",
                reply_markup=kbd,
            )
        else:
            bot.send_message(
                chat_id,
                "<b>FOREX_ALERT_IMPACTS</b>\n\nSelect impact levels to alert:",
                parse_mode="HTML",
                reply_markup=kbd,
            )

    @bot.callback_query_handler(func=lambda c: c.data.startswith("env_edit:"))
    def cb_env_edit(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        key = call.data.split(":", 1)[1]
        if key == "FOREX_ALERT_IMPACTS":
            _show_impact_picker(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
            return
        if key in ("RESET_DATABASE", "ENABLE_FOREX_ALERTS"):
            _show_bool_picker(call.message.chat.id, call.message.message_id, key)
            bot.answer_callback_query(call.id)
            return
        user_state[call.from_user.id] = {"mode": "env_edit", "key": key}
        bot.send_message(
            call.message.chat.id, f"Send new value for <b>{key}</b>:", parse_mode="HTML"
        )
        bot.answer_callback_query(call.id)

    @bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_impact:"))
    def cb_toggle_impact(call):
        try:
            if not _is_admin(call.from_user.id):
                bot.answer_callback_query(call.id, "⛔ Unauthorized")
                return
            impact = call.data.split(":", 1)[1]
            raw = _get_env_raw("FOREX_ALERT_IMPACTS")
            selected = {x.strip() for x in raw.split(",")} if raw else set()
            if impact in selected:
                selected.discard(impact)
            else:
                selected.add(impact)
            new_val = ",".join(sorted(selected, key=["High", "Medium", "Low"].index))
            _set_env_line("FOREX_ALERT_IMPACTS", f'"{new_val}"')
            _sync_runtime()
            _show_impact_picker(call.message.chat.id, call.message.message_id)
            bot.answer_callback_query(call.id)
        except Exception as e:
            logger.exception(f"cb_toggle_impact error: {e}")
            bot.answer_callback_query(call.id, f"Error: {e}")

    @bot.callback_query_handler(func=lambda c: c.data.startswith("toggle_bool:"))
    def cb_toggle_bool(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        _, key, val = call.data.split(":", 2)
        _set_env_line(key, val)
        _sync_runtime()
        _show_bool_picker(call.message.chat.id, call.message.message_id, key)
        bot.answer_callback_query(call.id, f"✅ Set to {val}")

    # ---- Back to menu ----
    @bot.callback_query_handler(func=lambda c: c.data == "menu")
    def cb_menu(call):
        if not _is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "⛔ Unauthorized")
            return
        bot.edit_message_text(
            "📡 <b>Control Bot</b>\nSelect a section:\n\n✅ Changes apply immediately — no restart needed.",
            call.message.chat.id,
            call.message.message_id,
            parse_mode="HTML",
            reply_markup=_main_menu(),
        )
        bot.answer_callback_query(call.id)

    # ---- Text input handler ----
    @bot.message_handler(func=lambda m: m.from_user.id in user_state)
    def handle_text_input(message):
        uid = message.from_user.id
        state = user_state.get(uid, {})
        mode = state.get("mode")
        text = message.text.strip()

        if mode == "src_edit":
            key = state["key"]
            _set_env_line(key, f'"{text}"')
            _sync_runtime()
            bot.reply_to(message, f"✅ <b>{key}</b> updated.", parse_mode="HTML")
            user_state.pop(uid, None)
            _show_sources(message.chat.id)

        elif mode == "model_edit":
            _set_env_line("OPENROUTER_MODEL", text)
            _sync_runtime()
            bot.reply_to(
                message, f"✅ Model set to: <code>{text}</code>", parse_mode="HTML"
            )
            user_state.pop(uid, None)
            _show_model(message.chat.id)

        elif mode == "apikey_edit":
            _set_env_line("OPENROUTER_API_KEY", text)
            _sync_runtime()
            bot.reply_to(message, "✅ API key updated.")
            user_state.pop(uid, None)
            _show_model(message.chat.id)

        elif mode == "kw_add":
            user_state[uid] = {"mode": "kw_score", "pending_word": text}
            _show_score_picker(message.chat.id, text)

        elif mode == "kw_del":
            data = _get_env_json("HIGH_IMPACT_KEYWORDS")
            if text in data:
                del data[text]
                _set_env_json("HIGH_IMPACT_KEYWORDS", data)
                _sync_runtime()
                bot.reply_to(message, f"✅ Removed <b>{text}</b>", parse_mode="HTML")
            else:
                bot.reply_to(message, f"❌ <b>{text}</b> not found.", parse_mode="HTML")
            user_state.pop(uid, None)
            _show_keywords_page(message.chat.id, 0)

        elif mode == "env_edit":
            key = state["key"]
            _set_env_line(key, text)
            _sync_runtime()
            bot.reply_to(message, f"✅ <b>{key}</b> updated.", parse_mode="HTML")
            user_state.pop(uid, None)
            _show_env(message.chat.id)

        elif mode == "src_score":
            bot.reply_to(message, "Please use the score buttons above.")

        elif mode == "kw_score":
            bot.reply_to(message, "Please use the score buttons above.")

    @bot.message_handler(func=lambda m: True)
    def fallback(message):
        if not _is_admin(message.from_user.id):
            return
        bot.reply_to(
            message,
            "Use /start to open the control panel.",
            reply_markup=_main_menu(),
        )


# ---------------------------------<< standalone entry point >>---------------------------------
def start_standalone():
    bot = telebot.TeleBot(BOT_TOKEN)
    register_handlers(bot)
    logger.info("Control bot started (standalone mode).")
    bot.infinity_polling()


if __name__ == "__main__":
    start_standalone()

from __future__ import annotations

import os
from typing import Dict, Optional
from dotenv import load_dotenv
from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    filters,
)

from .game_state import ChatGameState, GamePhase

# Load .env if present
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

# In-memory state per chat
CHAT_STATES: Dict[int, ChatGameState] = {}


def ensure_state(chat_id: int, creator_user_id: int) -> ChatGameState:
    if chat_id not in CHAT_STATES:
        CHAT_STATES[chat_id] = ChatGameState(chat_id=chat_id, creator_user_id=creator_user_id)
    return CHAT_STATES[chat_id]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Բարև, ես Մաֆիայի բոտն եմ. Օգտագործեք հրամանները խմբում:\n"
        "- /newgame — սկսել նոր լոբբի\n"
        "- /join — միանալ խաղին (լոբբի)\n"
        "- /startgame — սկսել խաղը\n"
        "- /votestart — սկսել օրվա քվեարկությունը\n"
        "- /endday — ավարտել օրվա քվեարկությունը\n"
        "- /endnight — ավարտել գիշերվա քայլերը\n"
        "- /status — տեսնել վիճակը\n"
        "- /endgame — ավարտել խաղը",
    )


async def cmd_newgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)
    state.__init__(chat_id=chat.id, creator_user_id=user.id)  # reset state
    await update.effective_message.reply_text(
        "Սկսվեց նոր լոբբի։ Մասնակցելու համար գրեք /join",
    )


async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    if state.phase != GamePhase.LOBBY:
        await update.effective_message.reply_text("Խաղը արդեն մեկնարկել է։")
        return

    added = state.add_player(user.id, user.full_name)
    if added:
        await update.effective_message.reply_text(f"{user.full_name} միացավ խաղին ({len(state.players)} խաղացող)")
    else:
        await update.effective_message.reply_text("Դուք արդեն լոբբիում եք։")


async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    removed = state.remove_player(user.id)
    if removed:
        await update.effective_message.reply_text(f"{user.full_name} դուրս եկավ լոբբից")
    else:
        await update.effective_message.reply_text("Չեք կարող դուրս գալ հիմա։")


async def notify_roles(context: ContextTypes.DEFAULT_TYPE, state: ChatGameState) -> None:
    for uid, player in state.players.items():
        try:
            await context.bot.send_message(chat_id=uid, text=f"Ձեր դերը՝ <b>{state.role_of(uid)}</b>", parse_mode=ParseMode.HTML)
        except Exception:
            # Ignore failures (user may not have started DM)
            pass


def alive_keyboard(state: ChatGameState, exclude_user_id: Optional[int] = None) -> InlineKeyboardMarkup:
    buttons = []
    for p in state.alive_players():
        if exclude_user_id is not None and p.user_id == exclude_user_id:
            continue
        buttons.append([InlineKeyboardButton(p.full_name, callback_data=f"pick:{p.user_id}")])
    return InlineKeyboardMarkup(buttons)


async def start_night(update: Update, context: ContextTypes.DEFAULT_TYPE, state: ChatGameState) -> None:
    # Mafia choose target
    for mafia_id in list(state.mafia_ids):
        if mafia_id in state.alive_ids():
            try:
                await context.bot.send_message(
                    chat_id=mafia_id,
                    text="Գիշեր է։ Ընտրեք զոհին:",
                    reply_markup=alive_keyboard(state, exclude_user_id=mafia_id),
                )
            except Exception:
                pass

    # Doctor choose save
    if state.doctor_id and state.doctor_id in state.alive_ids():
        try:
            await context.bot.send_message(
                chat_id=state.doctor_id,
                text="Գիշեր է։ Ո՞ւմ եք փրկում:",
                reply_markup=alive_keyboard(state),
            )
        except Exception:
            pass

    # Detective choose check
    if state.detective_id and state.detective_id in state.alive_ids():
        try:
            await context.bot.send_message(
                chat_id=state.detective_id,
                text="Գիշեր է։ Ո՞ւմ եք ստուգում:",
                reply_markup=alive_keyboard(state),
            )
        except Exception:
            pass

    await context.bot.send_message(chat_id=state.chat_id, text="Գիշեր է ընկել… Քայլերը կատարեք անձնական հաղորդագրությամբ։")


async def cmd_startgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    if state.phase != GamePhase.LOBBY:
        await update.effective_message.reply_text("Խաղը արդեն սկսված է։")
        return

    if len(state.players) < 4:
        await update.effective_message.reply_text("Պետք է առնվազն 4 խաղացող։")
        return

    state.assign_roles()
    await update.effective_message.reply_text("Դերերը բաժանվեցին։ Գիշերն սկսվեց։ Ստուգեք անձնական հաղորդագրությունները։")
    await notify_roles(context, state)
    await start_night(update, context, state)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    alive = ", ".join([p.full_name for p in state.alive_players()]) or "—"
    phase_name = {
        GamePhase.LOBBY: "Լոբբի",
        GamePhase.NIGHT: "Գիշեր",
        GamePhase.DAY: "Օր",
        GamePhase.ENDED: "Ավարտված",
    }[state.phase]

    await update.effective_message.reply_text(
        f"Փուլ՝ {phase_name}\nՕրերի քանակ՝ {state.day_number}\nԿենդանի են՝ {alive}"
    )


async def cmd_endnight(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    if state.phase != GamePhase.NIGHT:
        await update.effective_message.reply_text("Հիմա գիշեր չէ։")
        return

    result = state.resolve_night()
    parts = []
    if result["killed_user_id"] is not None:
        name = state.players.get(result["killed_user_id"], None)
        parts.append(f"Գիշերը սպանվեց: {name.full_name if name else result['killed_user_id']}")
    else:
        parts.append("Գիշերը ոչ ոք չսպանվեց։")

    if result["saved_user_id"] is not None:
        name = state.players.get(result["saved_user_id"], None)
        parts.append(f"Բժիշկը փրկեց: {name.full_name if name else result['saved_user_id']}")

    await update.effective_message.reply_text("\n".join(parts))

    # Check win
    win = state.check_win()
    if win:
        await context.bot.send_message(chat_id=state.chat_id, text=f"Խաղն ավարտվեց. {win}")
        return

    # Announce day
    await context.bot.send_message(chat_id=state.chat_id, text=f"Սկսվեց {state.day_number}-րդ օրը։ Քննարկեք և սկսեք քվեարկությունը /votestart")


async def cmd_votestart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    if state.phase != GamePhase.DAY:
        await update.effective_message.reply_text("Հիմա օր չէ։")
        return

    keyboard = [[InlineKeyboardButton(p.full_name, callback_data=f"vote:{p.user_id}")]
                for p in state.alive_players()]
    await update.effective_message.reply_text(
        "Ընտրեք ում եք մեղադրում (ամեն կենդանի խաղացող թող ընտրի մեկին):",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def cmd_endday(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    state = ensure_state(chat.id, user.id)

    if state.phase != GamePhase.DAY:
        await update.effective_message.reply_text("Հիմա օր չէ։")
        return

    executed = state.apply_day_result()

    if executed is None:
        await update.effective_message.reply_text("Հավասարություն կամ քվեարկություն չկար։ Ոչ ոք չի հեռացվում։")
    else:
        name = state.players.get(executed)
        await update.effective_message.reply_text(f"Քվեարկությամբ հեռացվեց՝ {name.full_name if name else executed}")

    win = state.check_win()
    if win:
        await context.bot.send_message(chat_id=state.chat_id, text=f"Խաղն ավարտվեց. {win}")
        return

    # Start next night
    await context.bot.send_message(chat_id=state.chat_id, text="Գիշերը սկսվեց։ Ստուգեք անձնական հաղորդագրությունները։")
    await start_night(update, context, state)


async def cmd_endgame(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    user = update.effective_user
    if chat.id in CHAT_STATES:
        del CHAT_STATES[chat.id]
    await update.effective_message.reply_text("Խաղն ավարտվեց և մաքրվեց։")


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    user = query.from_user
    # Identify chat by trying message chat (group) or fallback to user's last known chat not feasible; we store picks in per-user DMs.
    # We require that user is in exactly one active game DMing.
    # To keep simple, we search all states and find one where user participates.
    target_state: Optional[ChatGameState] = None
    for state in CHAT_STATES.values():
        if state.is_participant(user.id) and state.phase in (GamePhase.NIGHT, GamePhase.DAY):
            target_state = state
            break

    if target_state is None:
        return

    if data.startswith("pick:") and target_state.phase == GamePhase.NIGHT:
        try:
            picked_id = int(data.split(":", 1)[1])
        except Exception:
            return

        # Determine role of picker
        if user.id in target_state.mafia_ids and user.id in target_state.alive_ids():
            target_state.mafia_target = picked_id
            await query.edit_message_text("Մաֆիայի թիրախը ընտրված է։")
        elif user.id == target_state.doctor_id and user.id in target_state.alive_ids():
            target_state.doctor_save = picked_id
            await query.edit_message_text("Փրկվողը ընտրված է։")
        elif user.id == target_state.detective_id and user.id in target_state.alive_ids():
            target_state.detective_check = picked_id
            role_name = target_state.role_of(picked_id)
            await query.edit_message_text(f"Ստուգվեց. {role_name}")

    elif data.startswith("vote:") and target_state.phase == GamePhase.DAY:
        try:
            vote_id = int(data.split(":", 1)[1])
        except Exception:
            return
        if user.id in target_state.alive_ids() and vote_id in target_state.alive_ids():
            target_state.day_votes[user.id] = vote_id
            await query.edit_message_text(f"Ձեր քվեարկությունը գրանցվեց։")


def main() -> None:
    token = BOT_TOKEN
    if not token:
        raise RuntimeError("BOT_TOKEN is not set. Put it in environment or .env file.")

    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("newgame", cmd_newgame))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("leave", cmd_leave))
    app.add_handler(CommandHandler("startgame", cmd_startgame))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("endnight", cmd_endnight))
    app.add_handler(CommandHandler("votestart", cmd_votestart))
    app.add_handler(CommandHandler("endday", cmd_endday))
    app.add_handler(CommandHandler("endgame", cmd_endgame))

    app.add_handler(CallbackQueryHandler(on_callback))

    app.run_polling()


if __name__ == "__main__":
    main()
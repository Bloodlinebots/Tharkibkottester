from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

ADMIN_ID = 7755789304  # Change as needed

def is_admin(uid): return uid == ADMIN_ID

def get_admin_panel():
    buttons = [
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Manage Coins", callback_data="admin_coins")],
        [InlineKeyboardButton("❌ Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎁 Send Points to All", callback_data="admin_gift")]
    ]
    return InlineKeyboardMarkup(buttons)

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return await update.message.reply_text("❌ Access denied.")
    await update.message.reply_text("🧑‍💻 Welcome to Admin Panel", reply_markup=get_admin_panel())

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if not is_admin(uid):
        return await query.edit_message_text("❌ Not allowed.")

    db = context.bot_data["db"]

    if query.data == "admin_stats":
        total = await db.users.count_documents({})
        banned = await db.banned.count_documents({})
        await query.edit_message_text(
            f"📊 Stats:\n👥 Total Users: {total}\n🚫 Banned: {banned}",
            reply_markup=back_button()
        )

    elif query.data == "admin_coins":
        await query.edit_message_text(
            "💰 Manage Coins:\nUse `/addpoints <user_id> <coins>` to add.",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )

    elif query.data == "admin_ban":
        await query.edit_message_text(
            "❌ Ban Control:\nUse:\n`/ban <user_id>` to ban\n`/unban <user_id>` to unban",
            reply_markup=back_button(),
            parse_mode="Markdown"
        )

    elif query.data == "admin_broadcast":
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text(
            "📢 Please send the message you want to broadcast to all users.",
            reply_markup=back_button()
        )

    elif query.data == "admin_gift":
        context.user_data["awaiting_gift"] = True
        await query.edit_message_text(
            "🎁 Please enter the number of coins to send to all users.",
            reply_markup=back_button()
        )

def back_button():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="admin_back")]
    ])

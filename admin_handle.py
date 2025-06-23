from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

def is_admin(uid):
    return uid == 7755789304  # Replace with your real admin ID

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return await update.message.reply_text("❌ Access denied.")

    buttons = [
        [InlineKeyboardButton("📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 Manage Coins", callback_data="admin_coins")],
        [InlineKeyboardButton("❌ Ban User", callback_data="admin_ban")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🎁 Send Points to All", callback_data="admin_gift")]
    ]
    markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("🧑‍💻 Welcome to Admin Panel", reply_markup=markup)

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if not is_admin(uid):
        return await query.edit_message_text("❌ Not allowed.")

    if query.data == "admin_stats":
        total = await context.bot_data['db'].users.count_documents({})
        banned = await context.bot_data['db'].banned.count_documents({})
        await query.edit_message_text(f"📊 Stats:\n👥 Users: {total}\n❌ Banned: {banned}")

    elif query.data == "admin_coins":
        await query.edit_message_text("💰 Send /addpoints <user_id> <coins> to add points.")

    elif query.data == "admin_ban":
        await query.edit_message_text("❌ Use /ban <user_id> and /unban <user_id> to manage bans.")

    elif query.data == "admin_broadcast":
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text("📢 Send the message you want to broadcast to all users.")

    elif query.data == "admin_gift":
        context.user_data["awaiting_gift"] = True
        await query.edit_message_text("🎁 Enter number of coins to send to all users:")

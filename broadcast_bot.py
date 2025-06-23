from telegram import Update
from telegram.ext import ContextTypes
from admin_handle import is_admin

async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("awaiting_broadcast"):
        context.user_data["awaiting_broadcast"] = False
        db = context.bot_data["db"]
        users = db.users.find({})
        count = 0
        async for user in users:
            try:
                await context.bot.copy_message(
                    chat_id=user["_id"],
                    from_chat_id=update.effective_chat.id,
                    message_id=update.message.message_id
                )
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

async def handle_gift_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    if context.user_data.get("awaiting_gift"):
        try:
            coins = int(update.message.text)
            db = context.bot_data["db"]
            users = db.users.find({})
            count = 0
            async for user in users:
                await db.users.update_one({"_id": user["_id"]}, {"$inc": {"points": coins}})
                count += 1
            context.user_data["awaiting_gift"] = False
            await update.message.reply_text(f"🎁 Gifted {coins} coins to {count} users.")
        except ValueError:
            await update.message.reply_text("❌ Invalid number. Please enter a valid integer.")

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import TelegramError

# --- Broadcast Handler ---
async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_broadcast"):
        return

    context.user_data["awaiting_broadcast"] = False
    db = context.bot_data["db"]
    text = update.message.text

    await update.message.reply_text("📣 Broadcasting...")

    total = 0
    failed = 0

    async for user in db.users.find({}):
        try:
            await context.bot.send_message(user["_id"], text)
            total += 1
        except TelegramError:
            failed += 1

    await update.message.reply_text(
        f"✅ Broadcast complete!\n\n📤 Sent: {total}\n❌ Failed: {failed}"
    )

# --- Gift Points Handler ---
async def handle_gift_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get("awaiting_gift"):
        return

    context.user_data["awaiting_gift"] = False
    db = context.bot_data["db"]

    try:
        coins = int(update.message.text)
    except ValueError:
        return await update.message.reply_text("❌ Please enter a valid number.")

    await update.message.reply_text(f"🎁 Sending {coins} coins to all users...")

    total = 0
    async for user in db.users.find({}):
        await db.users.update_one({"_id": user["_id"]}, {"$inc": {"points": coins}})
        total += 1

    await update.message.reply_text(f"✅ Successfully gifted {coins} coins to {total} users.")

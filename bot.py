import os
import asyncio
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    BotCommand, ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# CONFIG
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup", "name": "RASILI CHU💦"},
    {"type": "private", "chat_id": -1002799718375, "name": "RASMALAI🥵"}
]
ADMIN_USER_ID = 7755789304
DEFAULT_POINTS = 20
REFERRAL_REWARD = 25
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/your_support_channel"
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid):
    return uid == ADMIN_USER_ID

async def check_force_join(uid, bot):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await bot.get_chat_member(
                f"@{channel['username']}" if channel["type"] == "public" else channel["chat_id"],
                uid
            )
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.warning(f"Force join check failed: {e}")
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    if not await check_force_join(uid, context.bot):
        return await update.message.reply_text("🛑 Join all required channels to use this bot.")

    referred_by = None
    if update.message and context.args:
        if len(context.args) > 0 and context.args[0].isdigit():
            referred_by = int(context.args[0])
            if referred_by == uid:
                referred_by = None

    existing = await db.users.find_one({"_id": uid})
    if not existing:
        await db.users.insert_one({"_id": uid, "points": DEFAULT_POINTS})
        if referred_by:
            if not await db.referrals.find_one({"_id": uid}):
                await db.referrals.insert_one({"_id": uid, "by": referred_by})
                await db.users.update_one({"_id": referred_by}, {"$inc": {"points": REFERRAL_REWARD}})
                try:
                    await context.bot.send_message(referred_by, f"🎉 You earned {REFERRAL_REWARD} coins for referring!")
                except Exception:
                    pass

    keyboard = ReplyKeyboardMarkup([
        ["📽 VIDEO", "📷 PHOTO"],
        ["💰 POINTS", "💸 BUY"],
        ["🔗 /refer"]
    ], resize_keyboard=True)

    bot_info = await context.bot.get_me()
    bot_name = bot_info.first_name

    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=(
            f"**👋 Welcome to {bot_name}!**\n\n"
            "🎯 Use the buttons below to get started.\n\n"
            f"👨‍💻 Developer: [UnbornVillian]({DEVELOPER_LINK})\n"
            f"🛠 Support: [Join Support]({SUPPORT_LINK})"
        ),
        parse_mode="Markdown"
    )
    await update.message.reply_text("Select an option:", reply_markup=keyboard)
    await context.bot.send_message(LOG_CHANNEL_ID, f"📥 New User Started Bot\n👤 {user.full_name}\n🆔 {user.id}")

async def send_random(update, context, collection, seen_field, file_type):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    user_doc = await db.users.find_one({"_id": uid})
    if not is_admin(uid) and user_doc.get("points", 0) < 1:
        return await update.message.reply_text("🥺 No coins left! Refer friends or buy premium.")

    seen_doc = await db[seen_field].find_one({"_id": uid})
    seen = seen_doc.get("seen", []) if seen_doc else []

    doc = await db[collection].aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not doc:
        return await update.message.reply_text("📭 No more unseen items.")

    msg_id = doc[0]["msg_id"]
    try:
        await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id, protect_content=(file_type == "video"))
        if not is_admin(uid):
            await db.users.update_one({"_id": uid}, {"$inc": {"points": -1}})
            new_points = (await db.users.find_one({"_id": uid})).get("points", 0)
            await update.message.reply_text(f"✅ Sent!\n💰 Remaining points: {new_points}")
        else:
            await update.message.reply_text("✅ Sent! (Admin Access - Unlimited)")
        await db[seen_field].update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
    except Exception as e:
        logger.error(f"Error copying message: {e}")
        await update.message.reply_text("⚠️ Error sending item.")

async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "videos", "user_videos", "video")

async def photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "photos", "user_photos", "photo")

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await db.users.find_one({"_id": uid})
    await update.message.reply_text(f"💰 You have {user.get('points', 0)} points left.")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        bot_user = await context.bot.get_me()
        await update.message.reply_text(f"🔗 Refer link: https://t.me/{bot_user.username}?start={uid}")
    except Exception as e:
        logger.error(f"Refer command error: {e}")
        await update.message.reply_text("❌ Could not fetch refer link.")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📈 Point Prices", url="https://t.me/your_pricing_channel")],
        [InlineKeyboardButton("💬 Contact Owner", url=DEVELOPER_LINK)]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await update.message.reply_photo(
        photo="https://graph.org/file/55ccf9b9e08fa4ce5f278.jpg",
        caption=(
            "💸 Purchase Points Now! 💸\n\n"
            "✅ Want to Buy more points?\n"
            "Check the latest prices and contact the owner for secure purchases.\n\n"
            "🔗 Use the buttons below 👇"
        ),
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def addpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    args = context.args
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        return await update.message.reply_text("Usage: /addpoints <user_id> <points>")

    target_id = int(args[0])
    points = int(args[1])

    await db.users.update_one({"_id": target_id}, {"$inc": {"points": points}}, upsert=True)
    await context.bot.send_message(target_id, f"🏷 You received {points} points from admin!")
    await update.message.reply_text(f"✅ {points} points added to user {target_id}.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    msg = update.message
    try:
        if msg.video:
            file_id = msg.video.file_unique_id
            if not await db.videos.find_one({"unique_id": file_id}):
                await db.videos.insert_one({"msg_id": msg.message_id, "unique_id": file_id})
                await msg.reply_text("✅ Video saved to vault.")
        elif msg.photo:
            photo_id = msg.photo[-1].file_unique_id
            if not await db.photos.find_one({"unique_id": photo_id}):
                await db.photos.insert_one({"msg_id": msg.message_id, "unique_id": photo_id})
                await msg.reply_text("✅ Photo saved to vault.")
    except Exception as e:
        logger.error(f"Auto upload error: {e}")
        await msg.reply_text("❌ Upload failed.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("photo", photo_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CommandHandler("refer", refer_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("addpoints", addpoints_command))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)📽 VIDEO"), video_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)📷 PHOTO"), photo_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)💰 POINTS"), points_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)💸 BUY"), buy_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex(r"(?i)/refer"), refer_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO, auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()

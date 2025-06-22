import os
import asyncio
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

# ----- CONFIG -----
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
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid):
    return uid == ADMIN_USER_ID

async def check_force_join(uid, bot):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            if channel["type"] == "public":
                member = await bot.get_chat_member(f"@{channel['username']}", uid)
                if member.status in ["left", "kicked"]:
                    return False
            elif channel["type"] == "private":
                member = await bot.get_chat_member(channel["chat_id"], uid)
                if member.status in ["left", "kicked"]:
                    return False
        except:
            return False
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    if not await check_force_join(uid, context.bot):
        return await update.message.reply_text("🛑 Join all required channels to use this bot.")

    # Referral
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    existing = await db.users.find_one({"_id": uid})
    if not existing:
        await db.users.insert_one({"_id": uid, "points": DEFAULT_POINTS})
        if referred_by and referred_by != uid:
            if not await db.referrals.find_one({"_id": uid}):
                await db.referrals.insert_one({"_id": uid, "by": referred_by})
                await db.users.update_one({"_id": referred_by}, {"$inc": {"points": REFERRAL_REWARD}})
                await context.bot.send_message(referred_by, f"🎉 You earned {REFERRAL_REWARD} coins for referring!")

    keyboard = ReplyKeyboardMarkup([
        ["📽 VIDEO", "📷 PHOTO"],
        ["💰 POINTS"],
        ["🔗 /REFER"]
    ], resize_keyboard=True)

    await context.bot.send_photo(uid, photo=WELCOME_IMAGE, caption="Welcome! Use the buttons below.")
    await update.message.reply_text("Select an option:", reply_markup=keyboard)
    await context.bot.send_message(LOG_CHANNEL_ID, f"📥 New User Started Bot\n👤 {user.full_name}\n🆔 {user.id}")

async def send_random(update, context, collection, seen_field, file_type):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    user_doc = await db.users.find_one({"_id": uid})
    if user_doc.get("points", 0) < 1:
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
        if file_type == "video":
            await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id, protect_content=True)
        else:
            await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id)
        await db.users.update_one({"_id": uid}, {"$inc": {"points": -1}})
        await db[seen_field].update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
    except:
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
    username = (await context.bot.get_me()).username
    await update.message.reply_text(f"🔗 Refer link: https://t.me/{username}?start={uid}")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        return

    if update.message.video:
        file_id = update.message.video.file_unique_id
        existing = await db.videos.find_one({"unique_id": file_id})
        if not existing:
            await db.videos.insert_one({"msg_id": update.message.message_id, "unique_id": file_id})
            await update.message.reply_text("✅ Video saved to vault.")

    elif update.message.photo:
        photo_id = update.message.photo[-1].file_unique_id
        existing = await db.photos.find_one({"unique_id": photo_id})
        if not existing:
            await db.photos.insert_one({"msg_id": update.message.message_id, "unique_id": photo_id})
            await update.message.reply_text("✅ Photo saved to vault.")

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("photo", photo_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CommandHandler("refer", refer_command))

    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📽 VIDEO"), video_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("📷 PHOTO"), photo_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("💰 POINTS"), points_command))
    app.add_handler(MessageHandler(filters.VIDEO | filters.PHOTO, auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()

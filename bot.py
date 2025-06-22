import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
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

async def is_sudo(uid):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    return uid in sudo_list or is_admin(uid)

async def add_video(msg_id, unique_id=None):
    data = {"msg_id": msg_id}
    if unique_id:
        data["unique_id"] = unique_id
    await db.videos.update_one({"msg_id": msg_id}, {"$set": data}, upsert=True)

async def check_force_join(uid, bot):
    joined_all = True
    for channel in FORCE_JOIN_CHANNELS:
        try:
            if channel["type"] == "public":
                member = await bot.get_chat_member(f"@{channel['username']}", uid)
                if member.status in ["left", "kicked"]:
                    joined_all = False
            elif channel["type"] == "private":
                chat_id = channel["chat_id"]
                member = await bot.get_chat_member(chat_id, uid)
                if member.status in ["left", "kicked"]:
                    joined_all = False
        except:
            joined_all = False
    return joined_all

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    joined_all = await check_force_join(uid, context.bot)
    if not joined_all:
        return await update.message.reply_text("🛑 Join all required channels to use this bot.")

    # Referral system
    args = context.args
    referred_by = int(args[0]) if args and args[0].isdigit() else None
    existing = await db.users.find_one({"_id": uid})
    if not existing:
        await db.users.insert_one({"_id": uid, "points": DEFAULT_POINTS})
        if referred_by and referred_by != uid:
            already = await db.referrals.find_one({"_id": uid})
            if not already:
                await db.referrals.insert_one({"_id": uid, "by": referred_by})
                await db.users.update_one({"_id": referred_by}, {"$inc": {"points": REFERRAL_REWARD}})
                await context.bot.send_message(
                    referred_by,
                    f"🎉 You earned {REFERRAL_REWARD} coins for referring!"
                )

    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption="Welcome to the bot! Use /video to get video, /points to check coins."
    )

    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"📥 New User Started Bot\n👤 Name: {user.full_name}\n🆔 ID: {user.id}\n📛 Username: @{user.username or 'N/A'}"
    )

async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    user_doc = await db.users.find_one({"_id": uid})
    points = user_doc.get("points", 0)
    if points < 1:
        return await update.message.reply_text(
            "🥺 No coins left! Refer friends or buy premium."
        )

    seen_doc = await db.user_videos.find_one({"_id": uid})
    seen = seen_doc.get("seen", []) if seen_doc else []

    video_doc = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not video_doc:
        return await update.message.reply_text("📭 No more unseen videos.")

    video = video_doc[0]
    msg_id = video["msg_id"]
    try:
        await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id, protect_content=True)
        await db.users.update_one({"_id": uid}, {"$inc": {"points": -1}})
        await db.user_videos.update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
    except:
        return await update.message.reply_text("⚠️ Error sending video.")

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await db.users.find_one({"_id": uid})
    points = user.get("points", 0)
    await update.message.reply_text(f"💰 You have {points} points left.", parse_mode="Markdown")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    username = (await context.bot.get_me()).username
    await update.message.reply_text(
        f"🔗 Share this link to earn {REFERRAL_REWARD} coins: https://t.me/{username}?start={uid}"
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CommandHandler("refer", refer_command))

    async def set_menu():
        await app.bot.set_my_commands([
            BotCommand("video", "Get 1 Random Video 🎥"),
            BotCommand("photo", "Coming soon 📷"),
            BotCommand("points", "Check your coin balance 🏅"),
            BotCommand("refer", "Refer friends & earn coins 🔗")
        ])

    app.post_init = set_menu
    app.run_polling()

if __name__ == "__main__":
    main()

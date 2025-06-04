import os
import asyncio
import random
import threading
import zipfile
import tempfile

from motor.motor_asyncio import AsyncIOMotorClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters,
)

# ---------------- CONFIG ----------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI")
VAULT_CHANNEL_ID = int(os.getenv("VAULT_CHANNEL_ID"))
CHAT_CHANNEL_ID = int(os.getenv("CHAT_CHANNEL_ID"))
FORCE_JOIN_CHANNEL = "bot_backup"
ADMIN_USER_ID = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
WELCOME_IMAGE = "https://files.catbox.moe/19j4mc.jpg"
COOLDOWN = 8

# ---------------- DATABASE INIT ----------------

mongo = AsyncIOMotorClient(MONGO_URI)
db = mongo.bot_db
videos_col = db.videos
users_col = db.users
sudo_col = db.sudos
banned_col = db.banned
cooldowns = {}

# ---------------- HELPERS ----------------

def is_admin(uid):
    return uid == ADMIN_USER_ID

async def is_sudo(uid):
    return (await sudo_col.find_one({"_id": uid})) or is_admin(uid)

async def is_banned(uid):
    return await banned_col.find_one({"_id": uid})

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

# ---------------- HANDLERS ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await is_banned(uid):
        await update.message.reply_text("🚫 You are banned from using this bot.")
        return

    try:
        member = await context.bot.get_chat_member(f"@{FORCE_JOIN_CHANNEL}", uid)
        if member.status in ["left", "kicked"]:
            btn = InlineKeyboardMarkup(
                [[InlineKeyboardButton("Join Channel", url=f"https://t.me/{FORCE_JOIN_CHANNEL}")]]
            )
            await update.message.reply_text(
                "🚫 You must join our channel to use this bot.\n\n"
                "⚠️ If you leave, you will be restricted.\n\n"
                "✅ After joining, use /start",
                reply_markup=btn,
            )
            return
    except:
        pass

    user = update.effective_user
    await context.bot.send_message(
        chat_id=VAULT_CHANNEL_ID,
        text=(
            f"📥 New User Started Bot\n\n"
            f"👤 Name: {user.full_name}\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Username: @{user.username if user.username else 'N/A'}"
        )
    )

    bot_name = (await context.bot.get_me()).first_name
    caption = f"🥵 Welcome to {bot_name}!\nHere you will access the most unseen videos.\n👇 Tap below to explore:"

    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=caption,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK), InlineKeyboardButton("Help", callback_data="show_privacy_info")]
        ])
    )

    await context.bot.send_message(
        chat_id=uid,
        text=(
            "⚠️ **Disclaimer** ⚠️\n\n"
            "We do NOT produce or spread adult content.\n"
            "This bot is only for forwarding files.\n"
            "If videos are adult, we take no responsibility.\n"
            "Please read terms and conditions."
        ),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]
        ),
        parse_mode="Markdown"
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    await query.answer()

    if await is_banned(uid):
        await query.message.reply_text("🚫 You are banned from using this bot.")
        return

    now = asyncio.get_event_loop().time()
    if not is_admin(uid):
        if uid in cooldowns and cooldowns[uid] > now:
            wait = int(cooldowns[uid] - now)
            await query.message.reply_text(f"⏳ Please wait {wait} seconds before getting another video.")
            return
        cooldowns[uid] = now + COOLDOWN

    user = await users_col.find_one({"_id": uid}) or {"_id": uid, "seen": [], "msg_sent": False}
    all_videos = await videos_col.distinct("msg_id")
    unseen = list(set(all_videos) - set(user.get("seen", [])))

    if not unseen:
        if not user.get("msg_sent", False):
            await query.message.reply_text("✅ You have watched all videos. Restarting the list for you!")
            user["msg_sent"] = True
        user["seen"] = []
        unseen = all_videos.copy()

    random.shuffle(unseen)

    for msg_id in unseen:
        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            user["seen"].append(msg_id)
            user["msg_sent"] = False
            await users_col.replace_one({"_id": uid}, user, upsert=True)

            await query.message.reply_text(
                f"🎬 Video {len(user['seen'])}/{len(all_videos)} watched.\nWant another? 😈",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("📥 Get Another Video", callback_data="get_video")]]
                )
            )

            asyncio.create_task(delete_after_delay(context.bot, uid, sent.message_id, 10800))
            return
        except:
            await videos_col.delete_one({"msg_id": msg_id})

    await query.message.reply_text("⚠️ No videos available right now, please try later.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid):
        return

    if update.message.video:
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=CHAT_CHANNEL_ID,
                message_id=update.message.message_id,
            )
            await videos_col.insert_one({"msg_id": sent.message_id})
            await update.message.reply_text("✅ Video uploaded and saved to vault.")
        except:
            await update.message.reply_text("⚠️ Failed to upload.")

async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("/privacy - Use this to see bot's Terms and Conditions")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7
        )
    except:
        await update.message.reply_text("⚠️ Failed to fetch privacy message.")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid):
        await update.message.reply_text("🚫 You are not authorized.")
        return

    text = update.message.text.partition(" ")[2]
    if not text:
        await update.message.reply_text("Usage: /broadcast Your message here")
        return

    count = 0
    async for user in users_col.find():
        try:
            await context.bot.send_message(chat_id=user["_id"], text=text)
            count += 1
        except:
            pass

    await update.message.reply_text(f"📣 Broadcast sent to {count} users.")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only owner can add sudo.")
        return

    try:
        new_sudo = int(context.args[0])
        await sudo_col.update_one({"_id": new_sudo}, {"$set": {"_id": new_sudo}}, upsert=True)
        await update.message.reply_text(f"✅ Added {new_sudo} as sudo.")
    except:
        await update.message.reply_text("Invalid user ID.")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid):
        await update.message.reply_text("🚫 Only owner can remove sudo.")
        return

    try:
        rem_sudo = int(context.args[0])
        await sudo_col.delete_one({"_id": rem_sudo})
        await update.message.reply_text(f"✅ Removed {rem_sudo} from sudo.")
    except:
        await update.message.reply_text("Invalid user ID.")

# ---------------- MAIN ----------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    app.run_polling()

if __name__ == "__main__":
    main()

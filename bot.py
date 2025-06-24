import os
import asyncio
from datetime import datetime
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from motor.motor_asyncio import AsyncIOMotorClient
from telegram.error import BadRequest, TelegramError

# ----- CONFIG -----
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
VAULT_CHANNEL_ID = -1002564608005
LOG_CHANNEL_ID = -1002624785490
HELP_VIDEO_MSG_ID = 7  # Your help video message ID
HELP_VIDEO_CHANNEL = "@bot_backup"  # Channel where it's posted
ADMIN_USER_ID = 7755789304

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid): return uid == ADMIN_USER_ID

# --- Admin Command: Create Token ---
async def new_token_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("❌ Usage: /newtoken <TOKEN>")
    token = context.args[0].strip().upper()

    await db.tokens.insert_one({
        "_id": token,
        "active": True,
        "created_at": datetime.utcnow(),
        "used_by": []
    })

    await update.message.reply_text(f"✅ New token `{token}` created successfully.", parse_mode="Markdown")

# --- Admin Command: Expire Token ---
async def expire_token_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    result = await db.tokens.update_many({"active": True}, {"$set": {"active": False}})
    await update.message.reply_text(f"❌ {result.modified_count} token(s) expired.")

# --- START Command ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    args = context.args
    user_data = await db.users.find_one({"_id": uid})

    # Referral logic
    ref_by = int(args[0]) if args and args[0].isdigit() and int(args[0]) != uid else None

    if user_data and user_data.get("verified"):
        return await send_welcome(uid, context)

    await db.users.update_one({"_id": uid}, {
        "$setOnInsert": {
            "verified": False,
            "coins": 0,
            "ref_by": ref_by
        }
    }, upsert=True)

    # Send help video
    try:
        await context.bot.forward_message(
            chat_id=uid,
            from_chat_id=HELP_VIDEO_CHANNEL,
            message_id=HELP_VIDEO_MSG_ID
        )
    except:
        pass

    await update.message.reply_text(
        "🔒 Access Restricted\n\nYou need a valid token to use this bot.\nClick below to proceed.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Get Token", url="https://your-site.com/token")],
            [InlineKeyboardButton("✅ I Have a Token", callback_data="submit_token")]
        ])
    )

# --- Handle "I Have Token" Button ---
async def token_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✏️ Send your token below to unlock access.")

# --- Handle Text Input as Token ---
async def handle_token_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await db.users.find_one({"_id": uid})
    if not user or user.get("verified"):
        return

    token = update.message.text.strip().upper()
    token_doc = await db.tokens.find_one({"_id": token, "active": True})
    if not token_doc:
        return await update.message.reply_text("❌ Invalid or expired token.")

    await db.tokens.update_one({"_id": token}, {"$addToSet": {"used_by": uid}})

    updates = {"verified": True, "token": token, "coins": 10}
    ref = user.get("ref_by")

    if ref:
        await db.users.update_one({"_id": ref}, {"$inc": {"coins": 5}})
        try:
            await context.bot.send_message(ref, "🎁 You earned 5 coins from a referral!")
        except:
            pass

    await db.users.update_one({"_id": uid}, {"$set": updates})
    await update.message.reply_text("✅ Token verified! You now have 10 coins.")
    await send_welcome(uid, context)

# --- Welcome Message After Verify ---
async def send_welcome(uid, context):
    bot = context.bot
    username = (await bot.get_me()).username
    referral_link = f"https://t.me/{username}?start={uid}"

    await bot.send_message(
        chat_id=uid,
        text="🎉 Welcome! You're now verified.\nUse the buttons below to start watching videos.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Watch Videos", callback_data="get_video")],
            [InlineKeyboardButton("📢 Share & Earn 5 Coins", url=referral_link)]
        ])
    )
    # ------------------ GET VIDEO ------------------

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    user = await db.users.find_one({"_id": uid})
    if not user or not user.get("verified"):
        return await query.message.reply_text("🔐 Please verify using a token to access videos.")

    coins = user.get("coins", 0)
    if coins <= 0:
        return await query.message.reply_text(
            "❌ You’ve used all your video access.\nGet a new token to continue.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔑 Get New Token", url="https://your-site.com/token")]
            ])
        )

    user_videos_doc = await db.user_videos.find_one({"_id": uid})
    seen = user_videos_doc.get("seen", []) if user_videos_doc else []

    video_docs = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not video_docs:
        return await query.message.reply_text("📭 No more unseen videos. Please wait for more uploads.")

    for video in video_docs:
        msg_id = video["msg_id"]
        try:
            sent = await context.bot.copy_message(
                chat_id=uid,
                from_chat_id=VAULT_CHANNEL_ID,
                message_id=msg_id,
                protect_content=True,
            )
            await db.user_videos.update_one(
                {"_id": uid},
                {"$addToSet": {"seen": msg_id}},
                upsert=True
            )
            await db.users.update_one({"_id": uid}, {"$inc": {"coins": -1}})
        except BadRequest as e:
            if "MESSAGE_ID_INVALID" in str(e):
                await db.videos.delete_one({"msg_id": msg_id})
                await db.user_videos.update_many({}, {"$pull": {"seen": msg_id}})
                return await callback_get_video(update, context)
        except:
            return

    await context.bot.send_message(
        chat_id=uid,
        text="⏳ This video will self-destruct in 1 hour.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get Another", callback_data="get_video")]
        ])
    )


# ------------------ AUTO UPLOAD ------------------

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not is_admin(uid): return

    if update.message.video:
        video = update.message.video
        unique_id = video.file_unique_id

        exists = await db.videos.find_one({"unique_id": unique_id})
        if exists:
            return await update.message.reply_text("⚠️ Video already exists.")

        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            await db.videos.insert_one({"msg_id": sent.message_id, "unique_id": unique_id})
            await update.message.reply_text("✅ Video saved to vault.")
        except Exception as e:
            await update.message.reply_text(f"❌ Failed to upload: {e}")


# ------------------ STATS & RESET ------------------

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    v = await db.videos.count_documents({})
    u = await db.users.count_documents({})
    t = await db.tokens.count_documents({})
    await update.message.reply_text(
        f"📊 Stats:\nUsers: {u}\nVideos: {v}\nTokens: {t}"
    )

async def reset_seen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        target = int(context.args[0])
        await db.user_videos.update_one({"_id": target}, {"$set": {"seen": []}})
        await update.message.reply_text("✅ Reset done.")
    except:
        await update.message.reply_text("⚠️ Usage: /reset_seen <user_id>")


# ------------------ MAIN ------------------

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newtoken", new_token_cmd))
    app.add_handler(CommandHandler("expire", expire_token_cmd))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("reset_seen", reset_seen))

    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(token_button_callback, pattern="submit_token"))

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_token_input))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    print("✅ Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()

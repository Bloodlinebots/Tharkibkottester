import os
import logging
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import TelegramError
from motor.motor_asyncio import AsyncIOMotorClient
from admin_handle import admin_command, admin_callback  # Admin panel
from broadcast_bot import handle_broadcast, handle_gift_points

# --- LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
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

# --- DB SETUP ---
client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

# --- UTILITIES ---
def is_admin(uid): return uid == ADMIN_USER_ID

async def check_force_join(uid, bot):
    for channel in FORCE_JOIN_CHANNELS:
        try:
            chat_id = f"@{channel['username']}" if channel["type"] == "public" else channel["chat_id"]
            member = await bot.get_chat_member(chat_id, uid)
            if member.status in ["left", "kicked"]:
                return False
        except Exception as e:
            logger.warning(f"[ForceJoin] Error: {e}")
            return False
    return True

def main_keyboard():
    return ReplyKeyboardMarkup([
        ["🏙 VIDEO", "📷 PHOTO"],
        ["💰 POINTS", "💸 BUY"],
        ["🔗 /refer"]
    ], resize_keyboard=True)

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🔚 You are banned from using this bot.")

    if not await check_force_join(uid, context.bot):
        buttons = []
        for ch in FORCE_JOIN_CHANNELS:
            if ch["type"] == "public":
                buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=f"https://t.me/{ch['username']}")])
            else:
                invite_link = await context.bot.create_chat_invite_link(chat_id=ch["chat_id"])
                buttons.append([InlineKeyboardButton(f"🔗 Join {ch['name']}", url=invite_link.invite_link)])
        buttons.append([InlineKeyboardButton("✅ Subscribed", callback_data="check_joined")])
        return await update.message.reply_text(
            "🚫 You must join our channels to use this bot.\n\n✅ After joining, press 'Subscribed'",
            reply_markup=InlineKeyboardMarkup(buttons)
        )

    referred_by = None
    if context.args and len(context.args) > 0 and context.args[0].isdigit():
        referred_by = int(context.args[0])
        if referred_by == uid:
            referred_by = None

    if not await db.users.find_one({"_id": uid}):
        await db.users.insert_one({"_id": uid, "points": DEFAULT_POINTS})
        if referred_by and not await db.referrals.find_one({"_id": uid}):
            await db.referrals.insert_one({"_id": uid, "by": referred_by})
            await db.users.update_one({"_id": referred_by}, {"$inc": {"points": REFERRAL_REWARD}})
            try:
                await context.bot.send_message(referred_by, f"🎉 You earned {REFERRAL_REWARD} coins for referring!")
            except Exception:
                pass

    bot_info = await context.bot.get_me()
    caption = (
        f"👋 **Welcome to {bot_info.first_name}**\n\n"
        "🚀 This bot gives you access to high-quality media!\n\n"
        "🎯 Features:\n"
        "▪️ Random Photos/Videos\n▪️ Earn Coins via Referrals\n▪️ Buy Premium Access\n\n"
        f"👥 Referral Bonus: {REFERRAL_REWARD} coins\n"
        f"🪙 You start with {DEFAULT_POINTS} Free coins!\n\n"
        f"🔗 [Refer Friends](https://t.me/{bot_info.username}?start={uid})"
    )

    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=caption,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👨‍💻 Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK)]
        ])
    )

    await update.message.reply_text("Select an option:", reply_markup=main_keyboard())
    await context.bot.send_message(LOG_CHANNEL_ID, f"📅 New user: {user.full_name} | ID: {uid}")

async def joined_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if await check_force_join(query.from_user.id, context.bot):
        await query.edit_message_text("✅ Subscribed! Now use /start again.")
    else:
        await query.answer("❌ You haven't joined all channels!", show_alert=True)

async def send_random(update, context, collection, seen_field, file_type):
    uid = update.effective_user.id
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🔚 You are banned.")

    user_doc = await db.users.find_one({"_id": uid})
    if not is_admin(uid) and user_doc.get("points", 0) < 1:
        return await update.message.reply_text("🥺 No coins! Refer or Buy.")

    seen_doc = await db[seen_field].find_one({"_id": uid}) or {}
    seen = seen_doc.get("seen", [])

    doc = await db[collection].aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not doc:
        await db[seen_field].update_one({"_id": uid}, {"$set": {"seen": []}}, upsert=True)
        return await update.message.reply_text("📬 No more content now. Come back later.")

    msg_id = doc[0]["msg_id"]
    await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id)
    if not is_admin(uid):
        await db.users.update_one({"_id": uid}, {"$inc": {"points": -1}})
        points = (await db.users.find_one({"_id": uid})).get("points", 0)
        await update.message.reply_text(f"✅ Sent!\n💰 Remaining: {points}")
    else:
        await update.message.reply_text("✅ Sent! (Admin)")

    await db[seen_field].update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)

# --- Commands ---
async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "videos", "user_videos", "video")

async def photo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_random(update, context, "photos", "user_photos", "photo")

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = await db.users.find_one({"_id": update.effective_user.id})
    await update.message.reply_text(f"💰 You have {user.get('points', 0)} coins.")

async def refer_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_user = await context.bot.get_me()
    uid = update.effective_user.id
    await update.message.reply_text(f"🔗 Refer link:\nhttps://t.me/{bot_user.username}?start={uid}")

async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("📈 Payment Help", url="https://t.me/unbornvillian")],
        [InlineKeyboardButton("💬 Contact Owner", url="https://t.me/PSYCHO_X_KING")]
    ]
    await update.message.reply_photo(
        photo="https://graph.org/file/0921938be954fb02160e8-6a599c5fb10268f7b2.jpg",
        caption="💸 Buy more coins now!\nContact the owner for safe transactions.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_user.id,
            from_chat_id="@bot_backup",
            message_id=7
        )
    except Exception:
        await update.message.reply_text("⚠️ Couldn't send the privacy message.")

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    msg = update.message
    try:
        if msg.video:
            return await msg.reply_text("❌ Video uploads are disabled.")
        elif msg.photo:
            file_id = msg.photo[-1].file_unique_id
            if not await db.photos.find_one({"unique_id": file_id}):
                await db.photos.insert_one({"msg_id": msg.message_id, "unique_id": file_id})
                await msg.reply_text("✅ Photo saved.")
    except Exception as e:
        logger.error(f"[Auto Upload] Error: {e}")
        await msg.reply_text("❌ Upload failed.")

async def addpoints_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return

    args = context.args
    if len(args) != 2 or not args[0].isdigit() or not args[1].isdigit():
        return await update.message.reply_text("Usage: /addpoints <user_id> <coins>")

    uid, coins = int(args[0]), int(args[1])
    await db.users.update_one({"_id": uid}, {"$inc": {"points": coins}}, upsert=True)
    await update.message.reply_text(f"✅ Added {coins} coins to user {uid}")

# --- MAIN ---
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.bot_data["db"] = db

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("photo", photo_command))
    app.add_handler(CommandHandler("video", video_command))
    app.add_handler(CommandHandler("points", points_command))
    app.add_handler(CommandHandler("refer", refer_command))
    app.add_handler(CommandHandler("buy", buy_command))
    app.add_handler(CommandHandler("admin", admin_command))
    app.add_handler(CommandHandler("addpoints", addpoints_command))

    # Callbacks
    app.add_handler(CallbackQueryHandler(joined_callback, pattern="check_joined"))
    app.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))

    # Button Handlers
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)🏙 VIDEO"), video_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)📷 PHOTO"), photo_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)💰 POINTS"), points_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)💸 BUY"), buy_command))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("(?i)/refer"), refer_command))

    # Upload Handler
    app.add_handler(MessageHandler(filters.PHOTO, auto_upload))

    # Broadcast & Gift Logic
    app.add_handler(MessageHandler(filters.TEXT & filters.ALL, handle_broadcast))
    app.add_handler(MessageHandler(filters.TEXT & filters.ALL, handle_gift_points))

    app.run_polling()

if __name__ == "__main__":
    main()

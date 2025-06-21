import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
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
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"
BUY_PREMIUM_URL = "https://t.me/unbornvillian"
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

# --- UTILS ---

def is_admin(uid):
    return uid == ADMIN_USER_ID

async def is_sudo(uid):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    return uid in sudo_list or is_admin(uid)

async def ensure_user_exists(uid):
    await db.users.update_one({"_id": uid}, {"$setOnInsert": {"coins": 40}}, upsert=True)

def join_button_text(channel):
    return f"Join {channel.get('name')}" if channel.get('name') else (
        f"Join @{channel['username']}" if channel['type'] == 'public' else "Join Private"
    )

async def check_force_join(uid, bot):
    join_buttons = []
    joined_all = True

    for channel in FORCE_JOIN_CHANNELS:
        try:
            if channel["type"] == "public":
                member = await bot.get_chat_member(f"@{channel['username']}", uid)
                if member.status in ["left", "kicked"]:
                    joined_all = False
                    join_buttons.append(InlineKeyboardButton(join_button_text(channel), url=f"https://t.me/{channel['username']}"))
            elif channel["type"] == "private":
                chat_id = channel["chat_id"]
                member = await bot.get_chat_member(chat_id, uid)
                if member.status in ["left", "kicked"]:
                    joined_all = False
                    invite = await bot.create_chat_invite_link(chat_id=chat_id, name="ForceJoin", creates_join_request=False)
                    join_buttons.append(InlineKeyboardButton(join_button_text(channel), url=invite.invite_link))
        except:
            joined_all = False
            try:
                if channel["type"] == "public":
                    join_buttons.append(InlineKeyboardButton(join_button_text(channel), url=f"https://t.me/{channel['username']}"))
                else:
                    invite = await bot.create_chat_invite_link(chat_id=channel["chat_id"], name="ForceJoin", creates_join_request=False)
                    join_buttons.append(InlineKeyboardButton(join_button_text(channel), url=invite.invite_link))
            except:
                pass

    return joined_all, join_buttons

# --- HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    joined_all, join_buttons = await check_force_join(uid, context.bot)
    if not joined_all:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await update.message.reply_text(
            "🛑 You must join all required channels to use this bot:",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons])
        )

    await ensure_user_exists(uid)

    if context.args:
        try:
            ref_id = int(context.args[0])
            if ref_id != uid and not await db.users.find_one({"_id": uid, "referred": True}):
                await db.users.update_one({"_id": ref_id}, {"$inc": {"coins": 12}})
                await db.users.update_one({"_id": uid}, {"$set": {"referred": True}})
                await context.bot.send_message(ref_id, "🎉 You earned 12 coins by referring a user!")
        except:
            pass

    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"📅 New User Joined\nName: {user.full_name}\nID: {user.id}\nUsername: @{user.username or 'N/A'}"
    )

    await send_welcome(uid, context)

async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    joined_all, join_buttons = await check_force_join(uid, context.bot)
    if not joined_all:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await query.message.edit_text(
            "❗ You still haven't joined all required channels.",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons])
        )

    await ensure_user_exists(uid)
    await query.message.delete()
    await send_welcome(uid, context)

async def send_welcome(uid, context):
    coins = (await db.users.find_one({"_id": uid}) or {}).get("coins", 0)
    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=f"🥵 Welcome! You have {coins} coins.\n\nGet unseen videos using your coins.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📈 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("💸 Buy Premium", url=BUY_PREMIUM_URL), InlineKeyboardButton("📅 Your Coins", callback_data="check_coins")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK), InlineKeyboardButton("Terms", url=TERMS_LINK)]
        ])
    )

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    await ensure_user_exists(uid)
    user = await db.users.find_one({"_id": uid})
    if user.get("coins", 0) < 1:
        return await query.message.reply_text(
            f"🚫 You have no coins left!\n\nRefer friends to earn coins:\nhttps://t.me/{(await context.bot.get_me()).username}?start={uid}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💸 Buy Premium", url=BUY_PREMIUM_URL)],
                [InlineKeyboardButton("📅 Your Coins", callback_data="check_coins")]
            ])
        )

    video_doc = await db.videos.aggregate([{"$sample": {"size": 1}}]).to_list(1)
    if not video_doc:
        return await query.message.reply_text("📅 No videos available yet.")

    msg_id = video_doc[0]["msg_id"]
    try:
        await context.bot.copy_message(uid, VAULT_CHANNEL_ID, msg_id)
        await db.users.update_one({"_id": uid}, {"$inc": {"coins": -1}})
    except:
        return

async def check_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.callback_query.from_user.id
    user = await db.users.find_one({"_id": uid})
    coins = user.get("coins", 0)
    await update.callback_query.answer()
    await update.callback_query.message.reply_text(f"💰 You currently have {coins} coins.")

async def addcoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id): return
    try:
        target = int(context.args[0])
        qty = int(context.args[1])
        await db.users.update_one({"_id": target}, {"$inc": {"coins": qty}})
        await update.message.reply_photo(InputFile("certificate.jpg"), caption=f"🌟 Added {qty} coins to {target}")
    except:
        await update.message.reply_text("Usage: /addcoin user_id qty")

# --- Admin / Sudo Commands ---

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Need help? Contact the developer.")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    try:
        target = int(context.args[0])
        await db.sudos.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"✅ Added {target} as sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /addsudo user_id")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    try:
        target = int(context.args[0])
        await db.sudos.delete_one({"_id": target})
        await update.message.reply_text(f"❌ Removed {target} from sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /remsudo user_id")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    try:
        target = int(context.args[0])
        await db.banned.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"🚫 Banned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /ban user_id")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    try:
        target = int(context.args[0])
        await db.banned.delete_one({"_id": target})
        await update.message.reply_text(f"✅ Unbanned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /unban user_id")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    if not context.args:
        return await update.message.reply_text("⚠️ Usage: /broadcast your message")
    msg = " ".join(context.args)
    count = 0
    async for user in db.users.find():
        try:
            await context.bot.send_message(user["_id"], msg)
            count += 1
        except:
            pass
    await update.message.reply_text(f"✅ Broadcast sent to {count} users.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    v = await db.videos.count_documents({})
    u = await db.users.count_documents({})
    s = await db.sudos.count_documents({})
    b = await db.banned.count_documents({})
    await update.message.reply_text(
        f"📊 Bot Stats\n\n🎞 Videos: {v}\n👥 Users: {u}\n🛡 Sudo: {s}\n🚫 Banned: {b}",
        parse_mode="Markdown"
    )

# --- INIT ---

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(force_check_callback, pattern="force_check"))
    app.add_handler(CallbackQueryHandler(check_coins, pattern="check_coins"))
    app.add_handler(CommandHandler("addcoin", addcoin))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler(["stats", "status"], stats_command))

    app.run_polling()

if __name__ == "__main__":
    main()

import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

DEFAULT_COINS = 40
REFERRAL_REWARD = 10

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid): return uid == ADMIN_USER_ID

async def is_sudo(uid):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    return uid in sudo_list or is_admin(uid)

async def add_video(msg_id, unique_id=None):
    data = {"msg_id": msg_id}
    if unique_id:
        data["unique_id"] = unique_id
    await db.videos.update_one({"msg_id": msg_id}, {"$set": data}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

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

async def send_welcome(uid, context):
    bot_name = (await context.bot.get_me()).first_name
    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=f"🥵 Welcome to {bot_name}!\nHere you will access the most unseen 💦 videos.\n👇 Tap below to explore:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("Support", url=SUPPORT_LINK), InlineKeyboardButton("Help", callback_data="show_privacy_info")]
        ])
    )
    await context.bot.send_message(
        uid,
        "⚠️ **Disclaimer** ⚠️\n\nWe do NOT produce or spread adult content.\nThis bot is only for forwarding files.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]),
        parse_mode="Markdown"
    )
async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    uid = query.from_user.id
    joined_all, join_buttons = await check_force_join(uid, context.bot)
    if not joined_all:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await query.message.edit_text(
            "❗ You still haven't joined all required channels.",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons])
        )

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)
    await query.message.delete()
    await send_welcome(uid, context)
    
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

    args = context.args
    existing_user = await db.users.find_one({"_id": uid})
    if not existing_user:
        await db.users.insert_one({"_id": uid, "coins": DEFAULT_COINS, "referrals": 0})
        if args and args[0].isdigit():
            ref_id = int(args[0])
            if ref_id != uid:
                ref_user = await db.users.find_one({"_id": ref_id})
                if ref_user:
                    await db.users.update_one({"_id": ref_id}, {"$inc": {"coins": REFERRAL_REWARD, "referrals": 1}})
    else:
        await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)

    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"📥 New User Started Bot\n👤 Name: {user.full_name}\n🆔 ID: {user.id}\n📛 Username: @{user.username or 'N/A'}"
    )

    await send_welcome(uid, context)

async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id

    if await db.banned.find_one({"_id": uid}):
        return await query.message.reply_text("🛑 You are banned from using this bot.")

    user = await db.users.find_one({"_id": uid})
    if not user or user.get("coins", 0) < 4:
        return await query.message.reply_text(
            "🪙 You don't have enough coins to get videos.\n\n"
            "💎 Buy Premium to get unlimited access\n"
            "🎁 Or invite friends to earn more coins!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Buy Premium", url=DEVELOPER_LINK)],
                [InlineKeyboardButton("🎁 Invite & Earn", callback_data="referral_link")]
            ])
        )

    await db.users.update_one({"_id": uid}, {"$inc": {"coins": -4}})
    seen = user.get("seen", [])
    video_docs = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 4}}
    ]).to_list(4)

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
            await db.users.update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
            context.application.create_task(delete_after_delay(context.bot, uid, sent.message_id, 3600))
        except BadRequest as e:
            if "MESSAGE_ID_INVALID" in str(e):
                await db.videos.delete_one({"msg_id": msg_id})
                await db.users.update_many({}, {"$pull": {"seen": msg_id}})
                return await callback_get_video(update, context)

    await context.bot.send_message(
        chat_id=uid,
        text="This video will auto-destruct in 1 hour ⌛",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get More Random Videos", callback_data="get_video")]
        ])
    )

async def referral_link_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    bot_user = await context.bot.get_me()
    link = f"https://t.me/{bot_user.username}?start={uid}"
    await query.message.reply_text(
        f"🎁 Invite your friends using the link below and earn 10 coins for each successful referral:\n\n{link}"
    )

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = await db.users.find_one({"_id": uid}) or {}
    coins = user.get("coins", 0)
    refs = user.get("referrals", 0)
    await update.message.reply_text(f"💰 Coins: {coins}\n🎯 Referrals: {refs}")

async def add_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
        await db.users.update_one({"_id": uid}, {"$inc": {"coins": amount}}, upsert=True)
        await update.message.reply_text(f"✅ Added {amount} coins to {uid}.")
    except:
        await update.message.reply_text("⚠️ Usage: /addcoins user_id amount")

async def remove_coins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id): return
    try:
        uid = int(context.args[0])
        amount = int(context.args[1])
        await db.users.update_one({"_id": uid}, {"$inc": {"coins": -amount}})
        await update.message.reply_text(f"❌ Removed {amount} coins from {uid}.")
    except:
        await update.message.reply_text("⚠️ Usage: /removecoins user_id amount")
async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid):
        return

    if update.message.video:
        video = update.message.video
        unique_id = video.file_unique_id

        existing = await db.videos.find_one({"unique_id": unique_id})
        if existing:
            return await update.message.reply_text("⚠️ This video already exists in the vault.")

        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            await add_video(sent.message_id, unique_id=unique_id)
            await update.message.reply_text("✅ Uploaded to vault and saved.")
        except Exception as e:
            await update.message.reply_text(f"⚠️ Upload failed: {e}")
            await context.bot.send_message(LOG_CHANNEL_ID, f"❌ Upload error by {uid}: {e}")

async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass

    await query.message.reply_text("/privacy - View bot's Terms and Conditions")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except:
        await update.message.reply_text("⚠️ Could not fetch privacy policy.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Need help? Contact the developer.")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target = int(context.args[0])
        await db.sudos.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"✅ Added {target} as sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /addsudo user_id")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID:
        return
    try:
        target = int(context.args[0])
        await db.sudos.delete_one({"_id": target})
        await update.message.reply_text(f"❌ Removed {target} from sudo.")
    except:
        await update.message.reply_text("⚠️ Usage: /remsudo user_id")

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        await db.banned.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"🚫 Banned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /ban user_id")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
    try:
        target = int(context.args[0])
        await db.banned.delete_one({"_id": target})
        await update.message.reply_text(f"✅ Unbanned user {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /unban user_id")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_sudo(update.effective_user.id):
        return
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
    if not await is_sudo(update.effective_user.id):
        return
    v = await db.videos.count_documents({})
    u = await db.users.count_documents({})
    s = await db.sudos.count_documents({})
    b = await db.banned.count_documents({})
    await update.message.reply_text(
        f"📊 **Bot Stats**\n\n🎞 Videos: `{v}`\n👥 Users: `{u}`\n🛡 Sudo: `{s}`\n🚫 Banned: `{b}`",
        parse_mode="Markdown"
    )
    
def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(referral_link_button, pattern="referral_link"))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("addcoins", add_coins))
    app.add_handler(CommandHandler("removecoins", remove_coins))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(CallbackQueryHandler(force_check_callback, pattern="force_check"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler(["stats", "status"], stats_command))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))
    app.run_polling()

if __name__ == "__main__":
    main() 

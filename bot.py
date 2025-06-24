import os
import asyncio
from datetime import datetime, timedelta
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup
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
ADMIN_USER_ID = 7755789304

WELCOME_IMAGE = "https://graph.org/file/a13e9733afdad69720d67.jpg"

client = AsyncIOMotorClient(MONGO_URI)
db = client["telegram_bot"]

def is_admin(uid): return uid == ADMIN_USER_ID

async def is_sudo(uid):
    sudo_list = [s["_id"] async for s in db.sudos.find()]
    return uid in sudo_list or is_admin(uid)

# --- UTILS ---

async def can_user_watch_video(uid):
    user = await db.users.find_one({"_id": uid}) or {}
    now = datetime.utcnow()
    last = user.get("last_view_time")
    views = user.get("views_today", 0)
    bonus = user.get("referrals", 0) * 5

    if not last or now - last >= timedelta(hours=24):
        await db.users.update_one(
            {"_id": uid},
            {"$set": {"views_today": 0, "last_view_time": now}},
            upsert=True
        )
        return True, 0, 5 + bonus

    if views < (5 + bonus):
        return True, views, 5 + bonus

    return False, views, 5 + bonus

async def increment_view_count(uid):
    await db.users.update_one(
        {"_id": uid},
        {
            "$inc": {"views_today": 1},
            "$set": {"last_view_time": datetime.utcnow()}
        },
        upsert=True
    )

async def handle_referral(referred_id, referrer_id):
    referred_user = await db.users.find_one({"_id": referred_id})
    if referred_user:
        return
    await db.users.update_one(
        {"_id": referred_id},
        {"$set": {"_id": referred_id, "referred_by": referrer_id}},
        upsert=True
    )
    await db.users.update_one(
        {"_id": referrer_id},
        {"$inc": {"referrals": 1}},
        upsert=True
    )
    return True
    # --- PART 2: /start Command, Referral, Force Join ---

FORCE_JOIN_CHANNELS = [
    {"type": "public", "username": "bot_backup", "name": "RASILI CHU💦"},
    {"type": "private", "chat_id": -1002799718375, "name": "RASMALAI🥵"}
]
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK = "https://t.me/botmine_tech"
TERMS_LINK = "https://t.me/bot_backup/7"

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
                    join_buttons.append(
                        InlineKeyboardButton(
                            join_button_text(channel),
                            url=f"https://t.me/{channel['username']}"
                        )
                    )
            elif channel["type"] == "private":
                chat_id = channel["chat_id"]
                member = await bot.get_chat_member(chat_id, uid)
                if member.status in ["left", "kicked"]:
                    joined_all = False
                    invite = await bot.create_chat_invite_link(
                        chat_id=chat_id,
                        name="ForceJoin",
                        creates_join_request=False
                    )
                    join_buttons.append(
                        InlineKeyboardButton(
                            join_button_text(channel),
                            url=invite.invite_link
                        )
                    )
        except:
            joined_all = False
            try:
                if channel["type"] == "public":
                    join_buttons.append(
                        InlineKeyboardButton(
                            join_button_text(channel),
                            url=f"https://t.me/{channel['username']}"
                        )
                    )
                else:
                    invite = await bot.create_chat_invite_link(
                        chat_id=channel["chat_id"],
                        name="ForceJoin",
                        creates_join_request=False
                    )
                    join_buttons.append(
                        InlineKeyboardButton(
                            join_button_text(channel),
                            url=invite.invite_link
                        )
                    )
            except:
                pass

    return joined_all, join_buttons

async def send_welcome(uid, context):
    bot_name = (await context.bot.get_me()).first_name
    await context.bot.send_photo(
        uid,
        photo=WELCOME_IMAGE,
        caption=(
            f"👋 <b>Welcome to {bot_name}!</b>\n\n"
            "🔥 <b>Watch the most unseen, secret vault videos!</b>\n"
            "⏱ <b>You can watch 5 videos every 24 hours.</b>\n"
            "🎯 <b>Refer 1 user = +5 extra videos instantly!</b>\n\n"
            "👇 Tap below to get started:"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📩 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("👤 Developer", url=DEVELOPER_LINK)],
            [InlineKeyboardButton("💬 Support", url=SUPPORT_LINK), InlineKeyboardButton("📘 Help", callback_data="show_privacy_info")]
        ]),
        parse_mode="HTML"
    )
    await context.bot.send_message(
        uid,
        "⚠️ <b>Disclaimer</b>\n\nWe do not host or produce any adult content. "
        "This bot simply forwards videos already available on Telegram.\n\n"
        "By using this bot, you agree to the terms and conditions.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📘 View Terms", url=TERMS_LINK)]
        ]),
        parse_mode="HTML"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = update.effective_user
    args = context.args

    # ✅ Referral handling
    if args:
        try:
            referrer_id = int(args[0])
            if referrer_id != uid:
                if await handle_referral(uid, referrer_id):
                    try:
                        await context.bot.send_message(
                            referrer_id,
                            text="🎉 <b>Someone joined using your referral!</b>\nYou've earned <b>+5 more videos</b> for today!",
                            parse_mode="HTML"
                        )
                    except: pass
        except: pass

    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🚫 You are banned from using this bot.")

    joined_all, join_buttons = await check_force_join(uid, context.bot)
    if not joined_all:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await update.message.reply_text(
            "🚫 <b>Access Blocked</b>\n\nYou must join all required channels to use this bot:",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons]),
            parse_mode="HTML"
        )

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)

    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"📥 <b>New User Joined</b>\n\n👤 <b>{user.full_name}</b>\n🆔 <code>{uid}</code>\n@{user.username or 'N/A'}",
        parse_mode="HTML"
    )

    await send_welcome(uid, context)

async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try: await query.answer()
    except: pass

    uid = query.from_user.id
    joined_all, join_buttons = await check_force_join(uid, context.bot)
    if not joined_all:
        join_buttons.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await query.message.edit_text(
            "❗ <b>You still haven't joined all required channels.</b>",
            reply_markup=InlineKeyboardMarkup([[btn] for btn in join_buttons]),
            parse_mode="HTML"
        )

    await db.users.update_one({"_id": uid}, {"$set": {"_id": uid}}, upsert=True)
    await query.message.delete()
    await send_welcome(uid, context)
    # --- PART 3: Video System, Admin Panel ---

 async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    uid = query.from_user.id

    # 🚫 Banned check
    if await db.banned.find_one({"_id": uid}):
        return await query.message.reply_text("🚫 <b>You are banned from using this bot.</b>", parse_mode="HTML")

    # 🔄 Admin limit bypass
    is_limit_free = await is_sudo(uid)

    # 🧠 View limit check
    if not is_limit_free:
        allowed, views, limit = await can_user_watch_video(uid)
        if not allowed:
            return await query.message.reply_text(
                f"🚫 <b>Your Daily Limit Exceeded!</b>\n\n"
                f"📺 You've watched <b>{views}/{limit}</b> videos in the last 24 hours.\n\n"
                f"🎯 <b>Refer 1 friend</b> to unlock +5 more videos today!\n\n"
                f"👇 Tap below to get your referral link:",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎁 Get Referral Link", url=f"https://t.me/{(await context.bot.get_me()).username}?start={uid}")],
                    [InlineKeyboardButton("🔁 Try Again", callback_data="get_video")]
                ]),
                parse_mode="HTML"
            )

    # 🎞 Get unseen video
    seen = (await db.user_videos.find_one({"_id": uid}) or {}).get("seen", [])
    video_docs = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 1}}
    ]).to_list(1)

    if not video_docs:
        return await query.message.reply_text("📭 <b>No new videos available right now.</b>\nTry again later.", parse_mode="HTML")

    video = video_docs[0]
    msg_id = video["msg_id"]

    try:
        sent = await context.bot.copy_message(
            chat_id=uid,
            from_chat_id=VAULT_CHANNEL_ID,
            message_id=msg_id,
            protect_content=True
        )
        await increment_view_count(uid)
        await db.user_videos.update_one({"_id": uid}, {"$addToSet": {"seen": msg_id}}, upsert=True)
        context.application.create_task(delete_after_delay(context.bot, uid, sent.message_id, 3600))

        await context.bot.send_message(
            chat_id=uid,
            text="⌛ <b>This video will self-destruct in 1 hour.</b>\n\n👇 Tap below to get more:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📩 Get Another Video", callback_data="get_video")]
            ]),
            parse_mode="HTML"
        )
    except BadRequest as e:
        if "MESSAGE_ID_INVALID" in str(e):
            await db.videos.delete_one({"msg_id": msg_id})
            await db.user_videos.update_many({}, {"$pull": {"seen": msg_id}})
            await context.bot.send_message(LOG_CHANNEL_ID, f"⚠️ Deleted broken video `{msg_id}`", parse_mode="Markdown")
        else:
            return
    except TelegramError:
        return
    except:
        return

async def auto_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if not await is_sudo(uid): return
    if update.message.video:
        video = update.message.video
        unique_id = video.file_unique_id
        existing = await db.videos.find_one({"unique_id": unique_id})
        if existing:
            return await update.message.reply_text("⚠️ This video is already saved.")
        try:
            sent = await context.bot.copy_message(
                chat_id=VAULT_CHANNEL_ID,
                from_chat_id=update.message.chat_id,
                message_id=update.message.message_id,
            )
            await db.videos.update_one({"msg_id": sent.message_id}, {"$set": {"msg_id": sent.message_id, "unique_id": unique_id}}, upsert=True)
            await update.message.reply_text("✅ Saved to vault successfully.")
        except Exception as e:
            await update.message.reply_text(f"❌ Upload failed: {e}")

async def show_privacy_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.callback_query.answer()
    except: pass
    await update.callback_query.message.reply_text("/privacy - Read terms and policy.")

async def privacy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await context.bot.forward_message(
            chat_id=update.effective_chat.id,
            from_chat_id="@bot_backup",
            message_id=7,
        )
    except:
        await update.message.reply_text("⚠️ Couldn't fetch terms.")

# --- ADMIN COMMANDS ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❓ Contact developer: @unbornvillian")

async def add_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    try:
        target = int(context.args[0])
        await db.sudos.update_one({"_id": target}, {"$set": {"_id": target}}, upsert=True)
        await update.message.reply_text(f"✅ Added sudo: {target}")
    except:
        await update.message.reply_text("⚠️ Usage: /addsudo user_id")

async def remove_sudo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_USER_ID: return
    try:
        target = int(context.args[0])
        await db.sudos.delete_one({"_id": target})
        await update.message.reply_text(f"✅ Removed sudo: {target}")
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
        f"📊 <b>Bot Stats</b>\n\n🎞 Videos: <code>{v}</code>\n👥 Users: <code>{u}</code>\n🛡 Sudo: <code>{s}</code>\n🚫 Banned: <code>{b}</code>",
        parse_mode="HTML"
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(callback_get_video, pattern="get_video"))
    app.add_handler(CallbackQueryHandler(show_privacy_info, pattern="show_privacy_info"))
    app.add_handler(CallbackQueryHandler(force_check_callback, pattern="force_check"))
    app.add_handler(CommandHandler("privacy", privacy_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addsudo", add_sudo))
    app.add_handler(CommandHandler("remsudo", remove_sudo))
    app.add_handler(CommandHandler("ban", ban_user))
    app.add_handler(CommandHandler("unban", unban_user))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(CommandHandler(["stats", "status"], stats_command))
    app.add_handler(MessageHandler(filters.VIDEO, auto_upload))

    print("✅ Bot started with polling...")
    app.run_polling()

if __name__ == "__main__":
    main()

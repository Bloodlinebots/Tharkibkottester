import os, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import BadRequest, TelegramError
from motor.motor_asyncio import AsyncIOMotorClient

# ───────── CONFIG ─────────
TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN")
MONGO_URI    = os.getenv("MONGO_URI", "mongodb://localhost:27017")

VAULT_CHANNEL_ID = -1002810591637
LOG_CHANNEL_ID   = -1002624785490
FORCE_JOIN_CHANNELS = [
    {"type": "public",  "username": "bot_backup",   "name": "RASILI CHU💦"},
    {"type": "private", "chat_id":  -1002799718375, "name": "RASMALAI🥵"}
]
ADMIN_USER_ID  = 7755789304
DEVELOPER_LINK = "https://t.me/unbornvillian"
SUPPORT_LINK   = "https://t.me/botmine_tech"
TERMS_LINK     = "https://t.me/bot_backup/7"
WELCOME_IMAGE  = "https://graph.org/file/a13e9733afdad69720d67.jpg"

client = AsyncIOMotorClient(MONGO_URI)
db     = client["telegram_bot"]

# ───────── HELPER FUNCS ─────────
def is_admin(uid): return uid == ADMIN_USER_ID

async def is_sudo(uid):
    sudos = [s["_id"] async for s in db.sudos.find()]
    return uid in sudos or is_admin(uid)

# --- NEW COIN / PREMIUM HELPERS ---
async def get_user(uid):
    user = await db.users.find_one({"_id": uid})
    if not user:
        user = {"_id": uid, "coins": 50, "premium": False}
        await db.users.insert_one(user)
    return user

async def change_coins(uid, delta):
    await db.users.update_one({"_id": uid}, {"$inc": {"coins": delta}})

async def make_premium(uid):
    await db.users.update_one({"_id": uid},
                              {"$set": {"premium": True, "coins": 99999}})

async def handle_referral(maybe_ref, new_uid, bot):
    """
    maybe_ref = str from /start payload, or None
    Adds +10 coins to referrer if valid & first-time.
    """
    if not maybe_ref: return
    try:
        ref_id = int(maybe_ref)
        if ref_id == new_uid: return          # self-ref skip
        new_doc = await db.users.find_one({"_id": new_uid})
        if new_doc and new_doc.get("referred_by"): return  # already counted once
        await db.users.update_one({"_id": new_uid},
                                  {"$set": {"referred_by": ref_id}})
        await change_coins(ref_id, 10)
        await bot.send_message(
            ref_id,
            "🎉 You successfully referred someone!\n"
            "💰 <b>10 coins</b> added to your wallet!",
            parse_mode="HTML"
        )
    except:    # payload wasn’t an int, ignore
        pass


# ───────── OLD UTILS (unchanged) ─────────
async def add_video(msg_id, unique_id=None):
    data = {"msg_id": msg_id}
    if unique_id:
        data["unique_id"] = unique_id
    await db.videos.update_one({"msg_id": msg_id}, {"$set": data}, upsert=True)

async def delete_after_delay(bot, chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try: await bot.delete_message(chat_id, message_id)
    except: pass

def join_button_text(c):
    return f"Join {c.get('name')}" if c.get('name') else (
           f"Join @{c['username']}" if c['type']=='public' else "Join Private")

async def check_force_join(uid, bot):
    buttons, joined_all = [], True
    for ch in FORCE_JOIN_CHANNELS:
        try:
            if ch["type"] == "public":
                m = await bot.get_chat_member(f"@{ch['username']}", uid)
                if m.status in ["left", "kicked"]:
                    joined_all = False
                    buttons.append(InlineKeyboardButton(join_button_text(ch),
                                      url=f"https://t.me/{ch['username']}"))
            else:
                m = await bot.get_chat_member(ch["chat_id"], uid)
                if m.status in ["left", "kicked"]:
                    joined_all = False
                    invite = await bot.create_chat_invite_link(
                                chat_id=ch["chat_id"],
                                name="ForceJoin", creates_join_request=False)
                    buttons.append(InlineKeyboardButton(join_button_text(ch),
                                      url=invite.invite_link))
        except:
            joined_all = False
            if ch["type"] == "public":
                buttons.append(InlineKeyboardButton(join_button_text(ch),
                                url=f"https://t.me/{ch['username']}"))
            else:
                invite = await bot.create_chat_invite_link(
                            chat_id=ch["chat_id"], name="ForceJoin",
                            creates_join_request=False)
                buttons.append(InlineKeyboardButton(join_button_text(ch),
                                url=invite.invite_link))
    return joined_all, buttons


# ───────── HANDLERS ─────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    user = update.effective_user

    # ban check
    if await db.banned.find_one({"_id": uid}):
        return await update.message.reply_text("🛑 You are banned from using this bot.")

    # referral check ( payload after /start )
    if context.args:
        await handle_referral(context.args[0], uid, context.bot)

    # ensure user doc exists & earns default coins
    await get_user(uid)

    # force-join
    joined_all, join_btns = await check_force_join(uid, context.bot)
    if not joined_all:
        join_btns.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await update.message.reply_text(
            "🛑 You must join all required channels to use this bot:",
            reply_markup=InlineKeyboardMarkup([[b] for b in join_btns])
        )

    # mark joined flag
    await db.users.update_one({"_id": uid},
                              {"$set": {"joined_channels": True}}, upsert=True)

    # log
    await context.bot.send_message(
        LOG_CHANNEL_ID,
        f"📥 <b>New User Started Bot</b>\n👤 {user.full_name}\n🆔 {uid}\n"
        f"📛 @{user.username or 'N/A'}",
        parse_mode="HTML"
    )

    # welcome
    bot_name = (await context.bot.get_me()).first_name
    await update.message.reply_photo(
        photo=WELCOME_IMAGE,
        caption=(
            f"🥵 Welcome to {bot_name}!\n"
            "Here you’ll access the most unseen 💦 videos.\n👇 Tap below to explore:"
        ),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get Random Video", callback_data="get_video")],
            [InlineKeyboardButton("Developer", url=DEVELOPER_LINK)],
            [
                InlineKeyboardButton("Support", url=SUPPORT_LINK),
                InlineKeyboardButton("Help",    callback_data="show_privacy_info")
            ],
            [InlineKeyboardButton("🔢 Coins / Refer", callback_data="show_coins")]
        ])
    )

    # disclaimer PM
    await context.bot.send_message(
        uid,
        "⚠️ <b>Disclaimer</b> ⚠️\n\n"
        "We do <b>NOT</b> produce or spread adult content.\n"
        "This bot only forwards files already available on Telegram.\n"
        "Please read terms and conditions.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("📘 Terms & Conditions", url=TERMS_LINK)]]
        )
    )


async def force_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.callback_query.answer()
    joined_all, btns = await check_force_join(uid, context.bot)
    if not joined_all:
        btns.append(InlineKeyboardButton("✅ I Joined", callback_data="force_check"))
        return await update.callback_query.message.edit_text(
            "❗ You still haven't joined all required channels.",
            reply_markup=InlineKeyboardMarkup([[b] for b in btns])
        )
    await db.users.update_one({"_id": uid},
                              {"$set": {"joined_channels": True}}, upsert=True)
    await update.callback_query.message.delete()
    # simulate /start again
    fake = Update(update.update_id, message=update.effective_message)
    await start(fake, context)


# ---------- VIDEO FETCH (now with coins) ----------
async def callback_get_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    await q.answer()

    # ban check
    if await db.banned.find_one({"_id": uid}):
        return await q.message.reply_text("🛑 You are banned from using this bot.")

    user = await get_user(uid)

    # premium / coin check
    if not user.get("premium") and user.get("coins", 0) <= 0:
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start={uid}"
        return await q.message.reply_text(
            "😈 You’ve used up all your coins, you naughty beast!\n\n"
            "💎 <b>Buy Premium</b> to unlock <i>everything</i> – Russian content, "
            "step-sis, and more 😜\n\nOR\n\n"
            "👯‍♂️ <b>Invite friends</b> & earn 10 coins each!\n"
            f"\n🔗 Your Referral Link:\n<code>{ref_link}</code>",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Buy Premium", url=DEVELOPER_LINK)],
                [InlineKeyboardButton("🔗 Refer & Earn Coins", url=ref_link)]
            ])
        )

    # deduct 1 coin if not premium
    if not user.get("premium"):
        await change_coins(uid, -1)

    # original video-sending logic (unchanged)
    user_videos_doc = await db.user_videos.find_one({"_id": uid})
    seen = user_videos_doc.get("seen", []) if user_videos_doc else []

    video_docs = await db.videos.aggregate([
        {"$match": {"msg_id": {"$nin": seen}}},
        {"$sample": {"size": 4}}
    ]).to_list(4)

    if not video_docs:
        return await q.message.reply_text(
            "📭 No more unseen videos. Please wait for more uploads."
        )

    for v in video_docs:
        try:
            sent = await context.bot.copy_message(
                chat_id     = uid,
                from_chat_id= VAULT_CHANNEL_ID,
                message_id  = v["msg_id"],
                protect_content=True
            )
            await db.user_videos.update_one(
                {"_id": uid},
                {"$addToSet": {"seen": v["msg_id"]}},
                upsert=True
            )
            context.application.create_task(
                delete_after_delay(context.bot, uid, sent.message_id, 3600)
            )
        except BadRequest as e:
            if "MESSAGE_ID_INVALID" in str(e):
                await db.videos.delete_one({"msg_id": v["msg_id"]})
                await db.user_videos.update_many({}, {"$pull": {"seen": v["msg_id"]}})
                await context.bot.send_message(
                    LOG_CHANNEL_ID,
                    f"⚠️ Removed broken video `{v['msg_id']}`", parse_mode="Markdown"
                )
                return await callback_get_video(update, context)
            else:
                return await q.message.reply_text(f"⚠️ Error: {e}")
        except TelegramError as e:
            return await q.message.reply_text(f"⚠️ Telegram error: {e}")
        except Exception as e:
            return await q.message.reply_text(f"⚠️ Unknown error: {e}")

    await context.bot.send_message(
        uid,
        "This video will auto-destruct in 1 hour ⌛\n"
        "We auto-delete it to keep things clean & copyright-safe 🚫",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📥 Get More Random Videos", callback_data="get_video")]
        ])
    )

# ---------- COINS / REFER DASH ----------
async def show_coins_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await coins_command(update.callback_query, context, as_cb=True)

async def coins_command(entity, context: ContextTypes.DEFAULT_TYPE, *, as_cb=False):
    # entity is Message (from /coins) OR CallbackQuery
    uid  = entity.from_user.id
    user = await get_user(uid)
    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start={uid}"
    text = (
        "🔢 <b>Coin Balance:</b> "
        f"<code>{user.get('coins', 0)}</code>\n"
        "🔗 <b>Referral Link:</b>\n"
        f"<code>{ref_link}</code>\n\n"
        "📲 <i>Invite friends & earn 10 coins each!</i>"
    )
    reply_markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 Buy Premium", url=DEVELOPER_LINK)],
        [InlineKeyboardButton("🔗 Refer & Earn Coins", url=ref_link)]
    ])
    if as_cb:
        await entity.message.edit_text(text, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await entity.reply_text(text, parse_mode="HTML", reply_markup=reply_markup)

# ---------- ADMIN ADDCOIN / PREMIUM ----------
async def addcoin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if len(context.args) < 2:
        return await update.message.reply_text("⚠️ Usage: /addcoin <user_id> <amount|unlimited>")

    try:
        tgt = int(context.args[0])
        amt = context.args[1].lower()
        if amt == "unlimited":
            await make_premium(tgt)
            await context.bot.send_message(
                tgt,
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "      ✨ PREMIUM CERTIFICATE ✨\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                "You're now a 🔥 <b>PREMIUM MEMBER</b> 🔥\n"
                "Enjoy <b>UNLIMITED</b> spicy content 🥵\n\n"
                "Issued by: <a href='https://t.me/unbornvillian'>UnbornVillian</a>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
        else:
            delta = int(amt)
            await change_coins(tgt, delta)
            bal_doc = await get_user(tgt)
            await context.bot.send_message(
                tgt,
                "━━━━━━━━━━━━━━━━━━━━━━━\n"
                "      💰 COIN TOP-UP SUCCESSFUL 💰\n"
                "━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"You received <b>{delta}</b> coins!\n"
                f"New balance: <b>{bal_doc['coins']}</b>\n"
                "━━━━━━━━━━━━━━━━━━━━━━━",
                parse_mode="HTML"
            )
        await update.message.reply_text("✅ Done.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

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
    await update.callback_query.answer()
    await update.callback_query.message.reply_text("/privacy - View bot's Terms and Conditions")

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
# ───────── MAIN ─────────
async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # original handlers
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

    # new handlers
    app.add_handler(CommandHandler("coins", coins_command))
    app.add_handler(CallbackQueryHandler(show_coins_cb, pattern="show_coins"))
    app.add_handler(CommandHandler("addcoin", addcoin_command))

    await app.run_polling()


if __name__ == "__main__":
    asyncio.run(main())

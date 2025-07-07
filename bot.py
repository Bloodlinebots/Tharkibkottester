import os
import json
import logging
import asyncio
import nest_asyncio
from telegram import Update
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    ContextTypes, filters
)
from telethon import TelegramClient
from telethon.tl.functions.channels import GetParticipantRequest
from telethon.errors import ChannelInvalidError, ChatAdminRequiredError

# === CONFIG ===
API_ID = 29587868
API_HASH = "d9fb9ba59c30ae80c25c30d5c4c26e87"
BOT_TOKEN = "8076902558:AAH2_zkW1ytplhFxtdIGPfJVLEj_gKzKukQ"
SESSION_NAME = "session_privacy_destroyer"
CONFIG_FILE = "config.json"

# === Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === JSON Storage ===
def load_channel_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f).get("channel_id")
    return None

def save_channel_id(channel_id):
    with open(CONFIG_FILE, "w") as f:
        json.dump({"channel_id": channel_id}, f)

# === Admin Check ===
async def is_bot_admin(channel_id):
    try:
        async with TelegramClient(SESSION_NAME, API_ID, API_HASH).start(bot_token=BOT_TOKEN) as client:
            me = await client.get_me()
            result = await client(GetParticipantRequest(channel_id, me.id))
            return hasattr(result.participant, 'admin_rights')
    except ChatAdminRequiredError:
        return False
    except ChannelInvalidError:
        return False
    except Exception as e:
        logger.error(f"Admin check failed: {e}")
        return False

# === Handlers ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Welcome to Privacy Destroyer Bot!\n"
        "Use /connect <channel_id> to link your channel.\n"
        "Once connected, just send videos here and I’ll post them to your channel."
    )

async def connect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text("❗ Usage: /connect <channel_id>")
        return

    channel_id = context.args[0]
    await update.message.reply_text("⏳ Checking admin access...")

    if await is_bot_admin(channel_id):
        save_channel_id(channel_id)
        await update.message.reply_text(f"✅ Connected to channel `{channel_id}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(
            "❌ Bot is not an admin in that channel.\n"
            "Please make me an admin first and try again."
        )

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    channel_id = load_channel_id()
    if not channel_id:
        await update.message.reply_text("⚠️ No channel connected. Use /connect first.")
        return

    try:
        await context.bot.send_video(
            chat_id=channel_id,
            video=update.message.video.file_id,
            caption=update.message.caption or ""
        )
        await update.message.reply_text("✅ Posted to channel.")
    except Exception as e:
        logger.error(f"Video post error: {e}")
        await update.message.reply_text("❌ Failed to post to channel.")

# === Main ===
async def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("connect", connect))
    app.add_handler(MessageHandler(filters.VIDEO, handle_video))

    print("🤖 Bot is running...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await app.updater.idle()
    await app.shutdown()

if __name__ == "__main__":
    nest_asyncio.apply()
    asyncio.run(main())

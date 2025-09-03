import logging
import os
import re
import traceback
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telethon import TelegramClient
from telethon.tl.types import PeerChannel

# --- CONFIGURATION ---

BBOT_TOKEN = '8009074609:AAE1yEhrAf-VKSHFI6IHhjRKZhWyYp-0iKI'
API_ID = 28803298
API_HASH = 'd8ea0f3e56c55b8ef9c0e8cb39b9c857'
PHONE_NUMBER = '+918210671539'  # <-- Your mobile number here (with country code)
ALLOWED_USER_IDS = [6065778458]  # Only your user ID is allowed

DOWNLOAD_DIR = 'downloads'
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- TELETHON CLIENT SETUP ---

client = TelegramClient('my_account_session', API_ID, API_HASH)

async def start_telethon():
    PHONE_NUMBER = os.environ.get("+918210671539")  # or hardcode for testing
import asyncio

async def main():
    await client.start(phone='+918210671539')  # phone should be a string

# Run the async function
asyncio.run(main())

# --- HELPER FUNCTIONS ---

async def parse_link(link: str):
    """
    Parse Telegram message link to get chat_id and message_id.
    Supports:
    - Private groups/channels links like https://t.me/c/0123456789/456
    - Private groups/channels links with extra parts: https://t.me/c/0123456789/6/456
    - Public links like https://t.me/username/123
    """
    link = link.strip().replace("telegram.me", "t.me")  # unify domains

    # Handle private groups/channels: links contain /c/
    if "t.me/c/" in link:
        # Extract everything after /c/
        match = re.search(r't\.me/c/([\d/]+)', link)
        if not match:
            raise ValueError("Invalid private group link format")
        parts = match.group(1).split('/')
        if len(parts) < 2:
            raise ValueError("Invalid private link, not enough parts")
        chat_id_raw = parts[0]
        message_id = int(parts[-1])
        chat_id = int(f"-100{chat_id_raw}")  # full chat id with -100 prefix
        return chat_id, message_id

    # Handle public links: https://t.me/username/123
    match = re.search(r't\.me/([\w\d_]+)/(\d+)', link)
    if not match:
        raise ValueError("Invalid public link format")
    username = match.group(1)
    message_id = int(match.group(2))

    # Use Telethon get_entity to get chat_id from username
    entity = await client.get_entity(username)
    return entity.id, message_id

# --- TELEGRAM BOT HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return
    await update.message.reply_text("👋 Send me a Telegram message link and I will fetch the media or text for you!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ALLOWED_USER_IDS:
        await update.message.reply_text("🚫 You are not authorized to use this bot.")
        return

    text = update.message.text
    if not text:
        await update.message.reply_text("⚠️ Please send a valid Telegram message link.")
        return

    try:
        chat_id, message_id = await parse_link(text)
        message = await client.get_messages(chat_id, ids=message_id)
        if not message:
            await update.message.reply_text("⚠️ Could not find that message. Make sure your account has access to that chat.")
            return

        keyboard = [
            [
                InlineKeyboardButton("📥 Download Media", callback_data=f"download|{chat_id}|{message_id}"),
                InlineKeyboardButton("📝 Get Text", callback_data=f"text|{chat_id}|{message_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f"Message found in chat {chat_id} with ID {message_id}. What do you want to do?",
            reply_markup=reply_markup
        )
    except Exception as e:
        logging.error(f"Error in handle_message: {e}")
        traceback.print_exc()
        await update.message.reply_text("❌ Invalid Telegram link or error occurred. Please check your link and try again.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in ALLOWED_USER_IDS:
        await query.edit_message_text("🚫 You are not authorized to use this bot.")
        return

    try:
        data = query.data.split('|')
        if len(data) != 3:
            await query.edit_message_text("❌ Invalid callback data.")
            return
        action, chat_id_str, message_id_str = data
        chat_id = int(chat_id_str)
        message_id = int(message_id_str)

        message = await client.get_messages(chat_id, ids=message_id)
        if not message:
            await query.edit_message_text("⚠️ Could not retrieve message. Maybe no access or invalid message ID.")
            return

        if action == "download":
            if not message.media:
                await query.edit_message_text("⚠️ No downloadable media found in that message.")
                return

            file_path = await message.download_media(file=DOWNLOAD_DIR)
            if not file_path:
                await query.edit_message_text("⚠️ Failed to download media.")
                return

            chat = update.effective_chat.id
            with open(file_path, 'rb') as f:
                if message.video:
                    await context.bot.send_video(chat_id=chat, video=f, caption=message.text or "")
                elif message.photo:
                    await context.bot.send_photo(chat_id=chat, photo=f, caption=message.text or "")
                elif message.document:
                    await context.bot.send_document(chat_id=chat, document=f, caption=message.text or "")
                elif message.audio:
                    await context.bot.send_audio(chat_id=chat, audio=f, caption=message.text or "")
                else:
                    # fallback to document for other media types
                    await context.bot.send_document(chat_id=chat, document=f, caption=message.text or "")

            try:
                os.remove(file_path)
            except Exception as e:
                logging.warning(f"Could not delete file: {file_path} - {e}")

            await query.edit_message_text("✅ Media downloaded and sent.")

        elif action == "text":
            text = message.text or message.message or "⚠️ No text found in the message."
            await query.edit_message_text(f"📝 Message text:\n\n{text}")

        else:
            await query.edit_message_text("❌ Unknown action.")

    except Exception as e:
        logging.error(f"Callback error: {e}")
        traceback.print_exc()
        await query.edit_message_text("❌ Error handling your request.")

# --- MAIN FUNCTION ---

import asyncio

def main():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(start_telethon())

    application = ApplicationBuilder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    application.run_polling()

if __name__ == '__main__':
    main()

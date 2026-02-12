import os
import time
import yt_dlp
import asyncio
import threading
from fastapi import FastAPI
import uvicorn
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# Load .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not found in environment!")

# ------------------ FastAPI ------------------
app = FastAPI()

@app.get("/")
def health():
    return {"status": "Bot is running"}

def run_fastapi():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")


# ------------------ Telegram Bot ------------------

def progress_hook(d, context, chat_id, message_id, loop):
    if d["status"] == "downloading":
        now = time.time()
        last = context.user_data.get("last_update", 0)

        if now - last > 4:
            percent = d.get("_percent_str", "0%")
            speed = d.get("_speed_str", "0 KB/s")

            text = f"📥 Downloading...\n\n📊 {percent}\n⚡ {speed}"

            asyncio.run_coroutine_threadsafe(
                context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=message_id,
                    text=text,
                ),
                loop,
            )

            context.user_data["last_update"] = now


# ------------------ Handlers ------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Send me a YouTube link to download video."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if "youtube.com" not in url and "youtu.be" not in url:
        return

    status = await update.message.reply_text("🔍 Fetching video info...")

    try:
        ydl_opts = {"quiet": True}

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get("formats", [])
        keyboard = []
        seen = set()

        for f in formats:
            height = f.get("height")

            if (
                height
                and height not in seen
                and f.get("vcodec") != "none"
                and f.get("acodec") != "none"
            ):
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            f"🎬 {height}p ({f['ext']})",
                            callback_data=f"{f['format_id']}|{url}",
                        )
                    ]
                )
                seen.add(height)

        if not keyboard:
            await status.edit_text("❌ No downloadable format found.")
            return

        await status.edit_text(
            f"🎥 {info.get('title','Video')[:50]}\n\nSelect quality:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    except Exception:
        await status.edit_text("❌ Failed to fetch video info.")


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    format_id, url = query.data.split("|")
    chat_id = query.message.chat_id
    message_id = query.message.message_id

    file_path = f"video_{chat_id}.mp4"
    loop = asyncio.get_running_loop()

    ydl_opts = {
        "format": format_id,
        "outtmpl": file_path,
        "quiet": True,
        "progress_hooks": [
            lambda d: progress_hook(d, context, chat_id, message_id, loop)
        ],
    }

    try:
        await query.edit_message_text("🚀 Downloading...")

        await loop.run_in_executor(
            None,
            lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]),
        )

        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text="📤 Uploading...",
        )

        with open(file_path, "rb") as video:
            await context.bot.send_video(
                chat_id,
                video,
                caption="✅ Download Complete",
                supports_streaming=True,
            )

        await context.bot.delete_message(chat_id, message_id)

    except Exception:
        await context.bot.send_message(chat_id, "❌ Download failed.")

    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


# ------------------ Main ------------------

async def main():
    # Run FastAPI in background
    threading.Thread(target=run_fastapi, daemon=True).start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )
    application.add_handler(CallbackQueryHandler(button_callback))

    print("Bot started...")
    await application.start()
    await application.updater.start_polling()  # v20 compatible
    await application.idle()


if __name__ == "__main__":
    asyncio.run(main())

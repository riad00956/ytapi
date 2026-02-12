import os
import time
import yt_dlp
import asyncio
import threading
import random
from fastapi import FastAPI
import uvicorn
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- Configuration ---
BOT_TOKEN = "8560427479:AAEcOrSAkkYPy7o-C4iU7tOmSWgAbtdtc00"
app = FastAPI()

# Proxy List
MANUAL_PROXIES = [
    "http://197.155.64.226:8090", "http://168.194.248.18:8080",
    "socks5://115.127.107.106:1080", "http://177.130.25.76:8080",
    "socks5://111.67.103.90:1080", "socks5://110.235.248.150:1080",
    "http://93.183.126.135:3128"
]

def get_proxy():
    return random.choice(MANUAL_PROXIES)

# --- Progress Hook ---
def progress_hook(d, context, chat_id, message_id, loop):
    if d['status'] == 'downloading':
        curr = time.time()
        last = context.user_data.get('last_up', 0)
        if curr - last > 4.0:
            p = d.get('_percent_str', '0%')
            s = d.get('_speed_str', '0 KB/s')
            txt = f"📥 **Downloading...**\n\n📊 Progress: `{p}`\n⚡ Speed: `{s}`"
            asyncio.run_coroutine_threadsafe(context.bot.edit_message_text(txt, chat_id, message_id), loop)
            context.user_data['last_up'] = curr

# --- Bot Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! Send me a YouTube link, and I will provide download options like SnapTube.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com" not in url and "youtu.be" not in url: 
        return
    
    status = await update.message.reply_text("🔍 Fetching video info via proxy...")
    
    opts = {'quiet': True, 'proxy': get_proxy(), 'nocheckcertificate': True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            keyboard = []
            seen = set()
            for f in formats:
                h = f.get('height')
                # Filter formats with both video and audio
                if h and h not in seen and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    keyboard.append([InlineKeyboardButton(f"🎬 {h}p ({f['ext'].upper()})", callback_data=f"{f['format_id']}|{url}")])
                    seen.add(h)
        
        if not keyboard:
            await status.edit_text("❌ No suitable video formats found.")
            return
            
        await status.edit_text(f"🎥 **{info.get('title')[:50]}...**\n\nSelect Quality:", reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception:
        await status.edit_text("❌ Failed to fetch info. The link might be broken or proxy is down.")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fid, url = query.data.split('|')
    chat_id, mid = query.message.chat_id, query.message.message_id
    path = f"vid_{chat_id}.mp4"
    loop = asyncio.get_running_loop()
    
    opts = {
        'format': fid, 'outtmpl': path, 'proxy': get_proxy(),
        'progress_hooks': [lambda d: progress_hook(d, context, chat_id, mid, loop)], 'quiet': True
    }
    
    try:
        await query.edit_message_text("🚀 Starting download...")
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).download([url]))
        await context.bot.edit_message_text("📤 Uploading to Telegram...", chat_id, mid)
        with open(path, 'rb') as v:
            await context.bot.send_video(chat_id, v, caption="✅ Download Complete!", supports_streaming=True)
        await context.bot.delete_message(chat_id, mid)
    except:
        await context.bot.send_message(chat_id, "❌ Download failed. The file might be too large for the server.")
    finally:
        if os.path.exists(path): os.remove(path)

# --- FastAPI & Runner ---
@app.get("/")
def health(): 
    return {"status": "Bot is running"}

def run_fastapi():
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="error")

if __name__ == "__main__":
    # Run FastAPI in background thread
    threading.Thread(target=run_fastapi, daemon=True).start()
    
    # Run Bot in main thread to avoid signal/wakeup_fd errors
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    
    print("Bot is starting...")
    # Using stop_signals=None for maximum compatibility in threads
    application.run_polling(stop_signals=None)

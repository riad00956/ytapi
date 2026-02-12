import os
import random
import asyncio
import yt_dlp
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ---------------- Configuration ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

MANUAL_PROXIES = [
    "http://197.155.64.226:8090", "http://168.194.248.18:8080",
    "socks5://115.127.107.106:1080", "http://177.130.25.76:8080",
    "socks5://111.67.103.90:1080", "socks5://110.235.248.150:1080",
    "http://93.183.126.135:3128"
]

def get_proxy():
    return random.choice(MANUAL_PROXIES)

# ---------------- Bot Logic ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! Send me a YouTube link to get download options.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com" not in url and "youtu.be" not in url:
        return

    status = await update.message.reply_text("🔍 Fetching video info...")
    opts = {'quiet': True, 'proxy': get_proxy(), 'nocheckcertificate': True}

    try:
        # Running blocking yt-dlp call in a thread
        loop = asyncio.get_running_loop()
        def fetch_info():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        
        info = await loop.run_in_executor(None, fetch_info)
        
        formats, keyboard, seen = info.get('formats', []), [], set()
        for f in formats:
            h = f.get('height')
            if h and h not in seen and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                keyboard.append([InlineKeyboardButton(f"🎬 {h}p ({f['ext'].upper()})", callback_data=f"{f['format_id']}|{url}")])
                seen.add(h)
        
        if not keyboard:
            await status.edit_text("❌ No formats found.")
            return
        
        await status.edit_text(f"🎥 **{info.get('title')[:50]}...**\n\nSelect Quality:",
                               reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    except Exception as e:
        await status.edit_text(f"❌ Failed to fetch info: {e}")

async def progress_hook(d, context, chat_id, message_id):
    if d['status'] == 'downloading':
        curr = asyncio.get_running_loop().time()
        last = context.user_data.get('last_up', 0)
        if curr - last > 4.0:
            p = d.get('_percent_str', '0%')
            s = d.get('_speed_str', '0 KB/s')
            txt = f"📥 **Downloading...**\n\n📊 Progress: `{p}`\n⚡ Speed: `{s}`"
            try:
                # We use context.bot directly since we need thread safety
                await context.bot.edit_message_text(txt, chat_id, message_id, parse_mode="Markdown")
            except: pass
            context.user_data['last_up'] = curr

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    fid, url = query.data.split('|')
    chat_id, mid = query.message.chat.id, query.message.message_id
    path = f"vid_{chat_id}_{random.randint(1000,9999)}.mp4"

    # Define the hook function inside to capture loop and context
    def sync_hook(d):
        asyncio.run_coroutine_threadsafe(progress_hook(d, context, chat_id, mid), asyncio.get_event_loop())

    opts = {
        'format': fid,
        'outtmpl': path,
        'proxy': get_proxy(),
        'quiet': True,
        'progress_hooks': [sync_hook]
    }

    try:
        await query.edit_message_text("🚀 Downloading...")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).download([url]))

        await context.bot.edit_message_text("📤 Uploading...", chat_id, mid)
        with open(path, 'rb') as v:
            await context.bot.send_video(chat_id, v, caption="✅ Success!", supports_streaming=True)
        
        await context.bot.delete_message(chat_id, mid)
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ Error occurred: {e}")
    finally:
        if os.path.exists(path):
            os.remove(path)

# ---------------- FastAPI & Lifecycle ----------------
telegram_app = ApplicationBuilder().token(BOT_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup handlers
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    telegram_app.add_handler(CallbackQueryHandler(button_callback))
    
    # Start bot
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling() # Render-এ পোলিং সহজ, ওয়েবহুক চাইলে সেটিংস আলাদা লাগে
    print("--- Bot Started Successfully ---")
    yield
    # Shutdown bot
    await telegram_app.stop()
    await telegram_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "online", "python_version": "3.14"}

# ---------------- Main ----------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 10000))
    # Render-এ রান করার জন্য host "0.0.0.0" এবং সঠিক port জরুরি
    uvicorn.run(app, host="0.0.0.0", port=port)

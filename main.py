import os
import random
import asyncio
import yt_dlp
from contextlib import asynccontextmanager
from fastapi import FastAPI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

# ---------------- Config ----------------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
# প্রোডাশন এনভায়রনমেন্টে PORT অটোমেটিক রেন্ডার থেকে আসবে
PORT = int(os.environ.get("PORT", 10000))

PROXIES = [
    "http://197.155.64.226:8090", "http://168.194.248.18:8080",
    "socks5://115.127.107.106:1080", "http://177.130.25.76:8080"
]

# ---------------- Bot logic ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 Hello! YouTube লিংক পাঠান ডাউনলোড করার জন্য।")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if "youtube.com" not in url and "youtu.be" not in url: return
    
    msg = await update.message.reply_text("🔍 তথ্য খোঁজা হচ্ছে...")
    opts = {'quiet': True, 'proxy': random.choice(PROXIES), 'nocheckcertificate': True}

    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).extract_info(url, download=False))
        
        keyboard = []
        seen_res = set()
        for f in info.get('formats', []):
            res = f.get('height')
            if res and res not in seen_res and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                keyboard.append([InlineKeyboardButton(f"🎬 {res}p", callback_data=f"{f['format_id']}|{url}")])
                seen_res.add(res)
        
        await msg.edit_text(f"🎥 {info.get('title')[:50]}...\n\nকোয়ালিটি সিলেক্ট করুন:", 
                            reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        await msg.edit_text(f"❌ এরর: {str(e)[:100]}")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fid, url = query.data.split('|')
    chat_id = query.message.chat_id
    path = f"video_{chat_id}.mp4"

    try:
        await query.edit_message_text("🚀 ডাউনলোড শুরু হয়েছে...")
        opts = {'format': fid, 'outtmpl': path, 'proxy': random.choice(PROXIES), 'quiet': True}
        
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(opts).download([url]))

        await context.bot.send_video(chat_id, open(path, 'rb'), caption="✅ সম্পন্ন!")
    except Exception as e:
        await context.bot.send_message(chat_id, f"❌ সমস্যা হয়েছে: {str(e)[:100]}")
    finally:
        if os.path.exists(path): os.remove(path)

# ---------------- FastAPI & Bot Runner ----------------
bot_app = ApplicationBuilder().token(BOT_TOKEN).build()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # বট সেটআপ
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    bot_app.add_handler(CallbackQueryHandler(button_callback))
    
    await bot_app.initialize()
    await bot_app.start()
    # পোলিং মোড (সবচেয়ে হালকা ও সহজ পদ্ধতি)
    polling_task = asyncio.create_task(bot_app.updater.start_polling())
    print("🚀 Bot is Online!")
    yield
    # বন্ধ করার সময় ক্লিনআপ
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def health():
    return {"status": "running"}

if __name__ == "__main__":
    import uvicorn
    # এখানে কোনো asyncio.get_event_loop() নেই, তাই এরর আসার চান্স নেই
    uvicorn.run(app, host="0.0.0.0", port=PORT)

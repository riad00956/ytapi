import os
import time
import yt_dlp
import asyncio
import threading
import random
import requests
from fastapi import FastAPI
import uvicorn
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes

# --- কনফিগারেশন ---
BOT_TOKEN = "8560427479:AAEcOrSAkkYPy7o-C4iU7tOmSWgAbtdtc00"
app = FastAPI()

# আপনার দেওয়া প্রক্সি লিস্ট
MANUAL_PROXIES = [
    "http://197.155.64.226:8090", "http://168.194.248.18:8080",
    "socks5://115.127.107.106:1080", "http://177.130.25.76:8080",
    "socks5://111.67.103.90:1080", "socks5://110.235.248.150:1080",
    "http://93.183.126.135:3128"
]

def get_proxy():
    all_p = MANUAL_PROXIES.copy()
    random.shuffle(all_p)
    return all_p[0]

# --- প্রগ্রেস হুক ---
def progress_hook(d, context, chat_id, message_id, loop):
    if d['status'] == 'downloading':
        current_time = time.time()
        last_update = context.user_data.get('last_update', 0)
        
        if current_time - last_update > 4.0:
            percentage = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', '0 KB/s')
            text = f"📥 **Downloading...**\n\n📊 Progress: `{percentage}`\n⚡ Speed: `{speed}`"
            
            asyncio.run_coroutine_threadsafe(
                context.bot.edit_message_text(text, chat_id=chat_id, message_id=message_id),
                loop
            )
            context.user_data['last_update'] = current_time

# --- বট ফাংশনস ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ইউটিউব লিঙ্ক পাঠান, আমি আপনার পছন্দমতো কোয়ালিটি ডাউনলোড করে দেব।")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text
    if not ("youtube.com" in url or "youtu.be" in url):
        return

    status_msg = await update.message.reply_text("🔍 ভিডিওর তথ্য চেক করছি...")

    ydl_opts = {
        'quiet': True,
        'proxy': get_proxy(),
        'nocheckcertificate': True,
        'socket_timeout': 10
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            formats = info.get('formats', [])
            
            keyboard = []
            seen_res = set()
            # শুধু ভিডিও + অডিও যুক্ত ফরম্যাট ফিল্টার
            for f in formats:
                height = f.get('height')
                if height and height not in seen_res and f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                    btn_text = f"🎬 {height}p ({f['ext'].upper()})"
                    keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"{f['format_id']}|{url}")])
                    seen_res.add(height)

        if not keyboard:
            await status_msg.edit_text("❌ সরাসরি ভিডিও ফরম্যাট পাওয়া যায়নি।")
            return

        await status_msg.edit_text(f"🎥 **{info.get('title')[:60]}**\n\nকোয়ালিটি বেছে নিন:", 
                                  reply_markup=InlineKeyboardMarkup(keyboard))

    except Exception as e:
        await status_msg.edit_text(f"❌ এরর: প্রক্সি কাজ করছে না বা লিঙ্ক ভুল।")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    format_id, url = query.data.split('|')
    chat_id, message_id = query.message.chat_id, query.message.message_id
    file_path = f"vid_{chat_id}_{int(time.time())}.mp4"
    context.user_data['last_update'] = 0
    loop = asyncio.get_running_loop()

    ydl_opts = {
        'format': format_id,
        'outtmpl': file_path,
        'proxy': get_proxy(),
        'progress_hooks': [lambda d: progress_hook(d, context, chat_id, message_id, loop)],
        'quiet': True,
    }

    try:
        await query.edit_message_text("🚀 ডাউনলোড শুরু হয়েছে...")
        await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(ydl_opts).download([url]))

        await context.bot.edit_message_text("📤 টেলিগ্রামে আপলোড করছি...", chat_id=chat_id, message_id=message_id)
        
        with open(file_path, 'rb') as video_file:
            await context.bot.send_video(
                chat_id=chat_id, 
                video=video_file, 
                caption="✅ সফলভাবে ডাউনলোড হয়েছে!",
                supports_streaming=True
            )
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        
    except Exception as e:
        await context.bot.send_message(chat_id=chat_id, text=f"❌ ফেইল হয়েছে: ফাইলটি সম্ভবত খুব বড়।")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)

# --- FastAPI & Bot Runner ---
@app.get("/")
def home():
    return {"status": "SnapTube Bot is active"}

def start_bot():
    # নতুন ইভেন্ট লুপ সেটআপ যাতে FastAPI এর সাথে কনফ্লিক্ট না হয়
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))
    print("Bot is polling...")
    application.run_polling(close_loop=False)

if __name__ == "__main__":
    # বটকে আলাদা থ্রেডে চালানো
    threading.Thread(target=start_bot, daemon=True).start()
    # সার্ভার চালানো
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

import os
import telebot
import yt_dlp
import threading
import requests
import random
from fastapi import FastAPI
import uvicorn

# --- কনফিগারেশন ---
BOT_TOKEN = '8377715516:AAHa0eJOgQPJ-VNw-AMvwk4CuVkCrTk1LEU'
GEONODE_API = "https://proxylist.geonode.com/api/proxy-list?limit=100&page=1&sort_by=lastChecked&sort_type=desc"

bot = telebot.TeleBot(BOT_TOKEN)
app = FastAPI()

# --- ১. অটোমেটিক প্রক্সি সংগ্রহকারী ---
def get_fresh_proxies():
    try:
        response = requests.get(GEONODE_API)
        data = response.json()
        proxy_list = []
        for item in data['data']:
            # শুধুমাত্র HTTP এবং HTTPS প্রক্সি ফিল্টার করছি
            ip = item['ip']
            port = item['port']
            proxy_list.append(f"http://{ip}:{port}")
        return proxy_list
    except:
        return []

# --- ২. ভিডিও ইনফো এক্সট্রাক্টর ---
def get_video_info(url):
    proxies = get_fresh_proxies()
    random.shuffle(proxies) # প্রক্সিগুলো এলোমেলো করে নেওয়া

    # কয়েকটা প্রক্সি দিয়ে ট্রাই করার লজিক
    for proxy in proxies[:5]: # সেরা ৫টি প্রক্সি ট্রাই করবে
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'proxy': proxy,
            'socket_timeout': 10 # খুব স্লো প্রক্সি বাদ দেওয়ার জন্য
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    "status": "success",
                    "title": info.get('title'),
                    "thumbnail": info.get('thumbnail'),
                    "video_url": info.get('url'),
                    "proxy_used": proxy
                }
        except Exception:
            continue # এই প্রক্সি কাজ না করলে পরেরটায় যাবে
            
    return {"status": "error", "message": "সব প্রক্সি ব্যর্থ হয়েছে বা ইউটিউব ব্লক করেছে।"}

# --- ৩. টেলিগ্রাম বট হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "লিঙ্ক পাঠান, আমি Geonode প্রক্সি ব্যবহার করে লিঙ্ক তৈরি করে দিচ্ছি।")

@bot.message_handler(func=lambda message: "youtube.com" in message.text or "youtu.be" in message.text)
def handle_yt_link(message):
    msg = bot.reply_to(message, "তাজা প্রক্সি দিয়ে চেষ্টা করছি... একটু সময় দিন।")
    data = get_video_info(message.text)

    if data["status"] == "success":
        caption = f"🎬 **{data['title']}**\n\n✅ প্রক্সি সফল!"
        markup = telebot.types.InlineKeyboardMarkup()
        btn = telebot.types.InlineKeyboardButton("📥 Download Now", url=data['video_url'])
        markup.add(btn)
        
        bot.send_photo(message.chat.id, data['thumbnail'], caption=caption, reply_markup=markup, parse_mode="Markdown")
        bot.delete_message(message.chat.id, msg.message_id)
    else:
        bot.edit_message_text(f"ভুল হয়েছে: {data['message']}", message.chat.id, msg.message_id)

# --- ৪. Render Web Server ---
@app.get("/")
def health_check():
    return {"status": "Bot is active with Auto-Proxy"}

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

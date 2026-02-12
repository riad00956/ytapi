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
bot = telebot.TeleBot(BOT_TOKEN)
app = FastAPI()

# আপনার দেওয়া নির্দিষ্ট প্রক্সি লিস্ট
MANUAL_PROXIES = [
    "http://197.155.64.226:8090",
    "http://168.194.248.18:8080",
    "socks5://115.127.107.106:1080",
    "http://177.130.25.76:8080",
    "socks5://111.67.103.90:1080",
    "socks5://110.235.248.150:1080",
    "http://93.183.126.135:3128"
]

# --- ১. প্রক্সি স্ক্র্যাপার (আপনার প্রক্সি + অটো সোর্স) ---
def get_all_proxies():
    proxy_list = MANUAL_PROXIES.copy()
    
    # অটো সোর্স থেকেও কিছু প্রক্সি যোগ করা হচ্ছে ব্যাকআপ হিসেবে
    try:
        r = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", timeout=5)
        if r.status_code == 200:
            proxy_list.extend([f"http://{p}" for p in r.text.strip().split('\r\n')][:20])
    except: pass

    return list(set(proxy_list))

# --- ২. ভিডিও ইনফো এক্সট্রাক্টর ---
def get_video_info(url):
    all_proxies = get_all_proxies()
    random.shuffle(all_proxies)

    # অন্তত ১০টি প্রক্সি ট্রাই করবে
    for proxy in all_proxies[:10]:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'proxy': proxy,
            'socket_timeout': 10 
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return {
                    "status": "success",
                    "title": info.get('title'),
                    "thumbnail": info.get('thumbnail'),
                    "video_url": info.get('url')
                }
        except Exception as e:
            print(f"Failed with {proxy}, trying next...")
            continue
            
    return {"status": "error", "message": "দুঃখিত, কোনো প্রক্সি কাজ করছে না। আইপিগুলো ব্লক হয়ে থাকতে পারে।"}

# --- ৩. টেলিগ্রাম বট হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "বটটি সক্রিয় হয়েছে! এখন ইউটিউব লিঙ্ক পাঠান।")

@bot.message_handler(func=lambda message: "youtube.com" in message.text or "youtu.be" in message.text)
def handle_yt_link(message):
    msg = bot.reply_to(message, "আপনার দেওয়া প্রক্সি ব্যবহার করে লিঙ্ক তৈরি করছি... অপেক্ষা করুন।")
    data = get_video_info(message.text)

    if data["status"] == "success":
        caption = f"🎬 **{data['title']}**\n\n✅ ডাউনলোড লিঙ্ক তৈরি হয়েছে।"
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
    return {"status": "Bot is active with your custom proxies"}

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)

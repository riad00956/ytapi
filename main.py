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

# --- ১. মাল্টি-সোর্স প্রক্সি স্ক্র্যাপার (লোকাল ও পাবলিক) ---
def get_combined_proxies():
    proxy_list = []
    
    # সোর্স ১: Geonode
    try:
        r = requests.get("https://proxylist.geonode.com/api/proxy-list?limit=50&page=1&sort_by=lastChecked&sort_type=desc", timeout=5)
        for item in r.json()['data']:
            proxy_list.append(f"http://{item['ip']}:{item['port']}")
    except: pass

    # সোর্স ২: Proxyscrape (খুবই দ্রুত কাজ করে)
    try:
        r = requests.get("https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all", timeout=5)
        if r.status_code == 200:
            proxy_list.extend([f"http://{p}" for p in r.text.strip().split('\r\n')])
    except: pass

    # সোর্স ৩: Free Proxy List
    try:
        r = requests.get("https://www.proxy-list.download/api/v1/get?type=https", timeout=5)
        if r.status_code == 200:
            proxy_list.extend([f"http://{p}" for p in r.text.strip().split('\n')])
    except: pass

    return list(set(proxy_list)) # ডুপ্লিকেট রিমুভ করা

# --- ২. ভিডিও ইনফো এক্সট্রাক্টর (উন্নত রিট্রাই লজিক) ---
def get_video_info(url):
    all_proxies = get_combined_proxies()
    random.shuffle(all_proxies)

    # সেরা ১৫টি প্রক্সি ট্রাই করবে
    for proxy in all_proxies[:15]:
        ydl_opts = {
            'format': 'best',
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'proxy': proxy,
            'socket_timeout': 7 
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
            
    return {"status": "error", "message": "কোনো প্রক্সি কাজ করছে না। কিছুক্ষণ পর আবার চেষ্টা করুন।"}

# --- ৩. টেলিগ্রাম বট হ্যান্ডলার ---
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "লিঙ্ক পাঠান। আমি মাল্টি-সোর্স প্রক্সি ব্যবহার করে চেষ্টা করছি।")

@bot.message_handler(func=lambda message: "youtube.com" in message.text or "youtu.be" in message.text)
def handle_yt_link(message):
    msg = bot.reply_to(message, "তাজা লোকাল প্রক্সি চেক করছি... ২-১০ সেকেন্ড সময় লাগতে পারে।")
    data = get_video_info(message.text)

    if data["status"] == "success":
        caption = f"🎬 **{data['title']}**\n\n✅ ডাউনলোড লিঙ্ক তৈরি!"
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
    return {"status": "Bot is active with Multi-Proxy Logic"}

def run_bot():
    bot.infinity_polling()

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
    

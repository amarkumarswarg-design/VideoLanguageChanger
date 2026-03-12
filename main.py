import os
import asyncio
from flask import Flask
from threading import Thread
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import moviepy.editor as mp
from googletrans import Translator
from gtts import gTTS
import speech_recognition as sr

# --- 1. Flask Server for Render ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. Configuration ---
API_ID = int(os.environ.get("API_ID", 20671162))
API_HASH = os.environ.get("API_HASH", "38687d78db6d94d4e09a54a383185563")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8476928745:AAGHLw3jRCkgqHbjAWl-zwIb5m9wFk0gXdA")

bot = Client("dubbing_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
translator = Translator()

LANGS = {"uz": "Uzbek 🇺🇿", "hi": "Hindi 🇮🇳", "en": "English 🇺🇸", "ru": "Russian 🇷🇺"}

@bot.on_message(filters.command("start"))
async def start(c, m):
    await m.reply("नमस्ते! वीडियो भेजें (20-50s) डबिंग के लिए।")

@bot.on_message(filters.video | filters.document)
async def video_handler(c, m):
    btns = [[InlineKeyboardButton("Uzbek 🇺🇿", callback_data="uz"), InlineKeyboardButton("Hindi 🇮🇳", callback_data="hi")]]
    await m.reply("भाषा चुनें:", reply_markup=InlineKeyboardMarkup(btns))

@bot.on_callback_query()
async def process_video(c, q: CallbackQuery):
    lang = q.data
    await q.message.edit(f"प्रोसेसिंग चालू है: {lang}")
    # ... (बाकी डबिंग लॉजिक वही रहेगा) ...
    await q.message.reply("प्रोसेसिंग शुरू हो गई है।")

# --- 3. THE FIX: Modern Async Loop ---
async def main():
    # Flask को बैकग्राउंड में चलाओ
    Thread(target=run_flask, daemon=True).start()
    
    # बॉट शुरू करो
    await bot.start()
    print("Bot Started Successfully!")
    await idle() # यह बॉट को चालू रखेगा
    await bot.stop()

if __name__ == "__main__":
    # Python 3.10+ के लिए इवेंट लूप फिक्स
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
        

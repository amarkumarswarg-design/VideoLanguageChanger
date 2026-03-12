import os
import asyncio
from flask import Flask
from threading import Thread
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
import moviepy.editor as mp
from googletrans import Translator
from gtts import gTTS
import speech_recognition as sr

# --- 1. Render Keep-Alive (Flask) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is Running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- 2. Configuration ---
# ये वैल्यूज़ हमने Render के Environment Variables में डाली हैं
API_ID = int(os.environ.get("API_ID", 20671162))
API_HASH = os.environ.get("API_HASH", "38687d78db6d94d4e09a54a383185563")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8476928745:AAGHLw3jRCkgqHbjAWl-zwIb5m9wFk0gXdA")

bot = Client("dubbing_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
translator = Translator()

# --- 3. Language Map ---
LANGS = {
    "uz": "Uzbek 🇺🇿",
    "hi": "Hindi 🇮🇳",
    "en": "English 🇺🇸",
    "ru": "Russian 🇷🇺",
    "ar": "Arabic 🇦🇪",
    "fr": "French 🇫🇷"
}

@bot.on_message(filters.command("start"))
async def start_cmd(c, m):
    await m.reply("नमस्ते! वीडियो भेजें (20-50 सेकंड) और मैं उसे डब कर दूँगा।")

@bot.on_message(filters.video | filters.document)
async def video_in(c, m):
    buttons = [
        [InlineKeyboardButton("Uzbek 🇺🇿", callback_data="uz"), InlineKeyboardButton("Hindi 🇮🇳", callback_data="hi")],
        [InlineKeyboardButton("English 🇺🇸", callback_data="en"), InlineKeyboardButton("Russian 🇷🇺", callback_data="ru")]
    ]
    await m.reply("भाषा चुनें जिसमें डब करना है:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query()
async def process(c, q: CallbackQuery):
    lang = q.data
    await q.message.edit(f"प्रक्रिया शुरू... {LANGS[lang]} में अनुवाद हो रहा है।")
    
    # डाउनलोड और प्रोसेसिंग
    file_path = await c.download_media(q.message.reply_to_message)
    audio_path = "raw.wav"
    out_audio = "voice.mp3"
    out_video = "final_dub.mp4"

    try:
        # Step 1: Extract
        video = mp.VideoFileClip(file_path)
        video.audio.write_audiofile(audio_path)

        # Step 2: Speech to Text
        rec = sr.Recognizer()
        with sr.AudioFile(audio_path) as src:
            audio = rec.record(src)
            text = rec.recognize_google(audio)

        # Step 3: Translate
        translated = translator.translate(text, dest=lang).text

        # Step 4: TTS
        tts = gTTS(text=translated, lang=lang)
        tts.save(out_audio)

        # Step 5: Merge
        new_voice = mp.AudioFileClip(out_audio)
        final_vid = video.set_audio(new_voice)
        final_vid.write_videofile(out_video, codec="libx264", audio_codec="aac")

        await c.send_video(q.message.chat.id, video=out_video, caption=f"डबिंग सफल! ({LANGS[lang]})")
    
    except Exception as e:
        await q.message.reply(f"त्रुटि: {str(e)}")
    
    finally:
        # Cleanup
        for f in [file_path, audio_path, out_audio, out_video]:
            if os.path.exists(f): os.remove(f)

# --- 4. Running ---
if __name__ == "__main__":
    # Flask को पहले चलाएं ताकि Render का पोर्ट मिल जाए
    Thread(target=run_flask).start()
    print("Server started, now launching bot...")
    bot.run()
    

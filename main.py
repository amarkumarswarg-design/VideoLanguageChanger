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

# --- 1. Render Keep-Alive System (Flask) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot is Running! (Dubbing Bot Alive)"

def run_flask():
    # Render पोर्ट अपने आप उठाएगा, वरना 8080 यूज़ करेगा
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

# --- 2. Configuration ---
API_ID = int(os.environ.get("API_ID", "20671162"))
API_HASH = os.environ.get("API_HASH", "38687d78db6d94d4e09a54a383185563")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8476928745:AAGHLw3jRCkgqHbjAWl-zwIb5m9wFk0gXdA")

bot = Client("dubbing_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
translator = Translator()

# --- 3. Languages List (Uzbek + Global) ---
LANGS = {
    "uz": "Uzbek 🇺🇿", "hi": "Hindi 🇮🇳", "en": "English 🇺🇸", "ru": "Russian 🇷🇺",
    "ar": "Arabic 🇦🇪", "fr": "French 🇫🇷", "de": "German 🇩🇪", "zh-cn": "Chinese 🇨🇳",
    "es": "Spanish 🇪🇸", "it": "Italian 🇮🇹", "tr": "Turkish 🇹🇷", "ja": "Japanese 🇯🇵",
    "ko": "Korean 🇰🇷", "pt": "Portuguese 🇵🇹", "bn": "Bengali 🇧🇩", "ur": "Urdu 🇵🇰"
}

@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply("नमस्ते! मैं 'Video Dubber' बॉट हूँ।\nमुझे 20-50 सेकंड की वीडियो भेजें और भाषा चुनें।")

@bot.on_message(filters.video | filters.document)
async def handle_video(client, message):
    # Inline Buttons बनाना
    buttons = []
    keys = list(LANGS.keys())
    for i in range(0, len(keys), 2):
        row = [
            InlineKeyboardButton(LANGS[keys[i]], callback_data=keys[i]),
            InlineKeyboardButton(LANGS[keys[i+1]], callback_data=keys[i+1]) if i+1 < len(keys) else None
        ]
        buttons.append([btn for btn in row if btn])

    await message.reply("वीडियो मिल गया! डबिंग की भाषा चुनें:", reply_markup=InlineKeyboardMarkup(buttons))

@bot.on_callback_query()
async def process_dubbing(client, callback_query: CallbackQuery):
    target_lang = callback_query.data
    msg = callback_query.message
    await msg.edit(f"प्रोसेसिंग चालू है... {LANGS[target_lang]} में डब किया जा रहा है।")

    # फाइल मैनेजमेंट
    video_path = await client.download_media(msg.reply_to_message)
    audio_path = "temp.wav"
    output_audio = "trans.mp3"
    final_video = "final.mp4"

    try:
        # Step 1: ऑडियो निकालो
        clip = mp.VideoFileClip(video_path)
        clip.audio.write_audiofile(audio_path)

        # Step 2: स्पीच टू टेक्स्ट
        r = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio_data = r.record(source)
            text = r.recognize_google(audio_data)

        # Step 3: अनुवाद
        trans_text = translator.translate(text, dest=target_lang).text

        # Step 4: टेक्स्ट टू स्पीच
        tts = gTTS(text=trans_text, lang=target_lang)
        tts.save(output_audio)

        # Step 5: वीडियो मर्च
        new_audio = mp.AudioFileClip(output_audio)
        final_clip = clip.set_audio(new_audio)
        final_clip.write_videofile(final_video, codec="libx264", audio_codec="aac")

        await client.send_video(msg.chat.id, video=final_video, caption=f"डबिंग सफल: {LANGS[target_lang]}")
    
    except Exception as e:
        await msg.reply(f"माफी चाहता हूँ, एरर आया: {str(e)}")
    
    finally:
        # फाइलें साफ़ करना
        for f in [video_path, audio_path, output_audio, final_video]:
            if os.path.exists(f): os.remove(f)

# --- 4. Execution ---
if __name__ == "__main__":
    # Flask को अलग थ्रेड में चलाओ ताकि पोर्ट ओपन रहे
    Thread(target=run_flask).start()
    # बॉट शुरू करो
    bot.run()
    

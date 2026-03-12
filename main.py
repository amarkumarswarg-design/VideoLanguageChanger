import os
import asyncio
import tempfile
import time
from threading import Thread
from datetime import datetime

from flask import Flask
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
import moviepy.editor as mp
from googletrans import Translator
from gtts import gTTS
import speech_recognition as sr

# -------------------- Flask Server (Render Port) --------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# -------------------- Configuration --------------------
API_ID = int(os.environ["API_ID"])          # Render Environment Variable
API_HASH = os.environ["API_HASH"]            # Render Environment Variable
BOT_TOKEN = os.environ["BOT_TOKEN"]          # Render Environment Variable

# Language list (code : display name)
# Google Speech Recognition uses BCP-47 codes like 'hi-IN', 'en-US', 'ru-RU'
# gTTS uses ISO 639-1 codes like 'hi', 'en', 'ru'
# We'll maintain a mapping for both
LANGS = {
    "af": "Afrikaans", "ar": "Arabic", "bg": "Bulgarian", "bn": "Bengali",
    "ca": "Catalan", "cs": "Czech", "da": "Danish", "de": "German",
    "el": "Greek", "en": "English", "es": "Spanish", "et": "Estonian",
    "fa": "Persian", "fi": "Finnish", "fr": "French", "gu": "Gujarati",
    "he": "Hebrew", "hi": "Hindi", "hr": "Croatian", "hu": "Hungarian",
    "id": "Indonesian", "it": "Italian", "ja": "Japanese", "kn": "Kannada",
    "ko": "Korean", "lt": "Lithuanian", "lv": "Latvian", "ml": "Malayalam",
    "mr": "Marathi", "ms": "Malay", "nl": "Dutch", "no": "Norwegian",
    "pa": "Punjabi", "pl": "Polish", "pt": "Portuguese", "ro": "Romanian",
    "ru": "Russian", "sk": "Slovak", "sl": "Slovenian", "sr": "Serbian",
    "sv": "Swedish", "ta": "Tamil", "te": "Telugu", "th": "Thai",
    "tl": "Tagalog", "tr": "Turkish", "uk": "Ukrainian", "ur": "Urdu",
    "vi": "Vietnamese", "zh-cn": "Chinese (Simplified)"
}

# Mapping for Google Speech Recognition (add region if needed, but basic code often works)
# For many languages, just the code works; for some we need region variants.
# We'll use the same code for simplicity; speech_recognition accepts many.
def get_sr_lang(code):
    # You can customize if needed, e.g., 'en' -> 'en-US', 'hi' -> 'hi-IN'
    return code

# Mapping for gTTS (it expects ISO 639-1, same as our codes)
def get_gtts_lang(code):
    return code

# -------------------- Bot Client --------------------
bot = Client("dubbing_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
translator = Translator()

# Temporary user data storage
user_data = {}  # {user_id: {'source_lang': None, 'target_lang': None, 'video_path': None, 'step': 'source'}}

# Helper to create language keyboard (multiple rows)
def lang_keyboard(prefix):
    buttons = []
    row = []
    for i, (code, name) in enumerate(LANGS.items(), 1):
        row.append(InlineKeyboardButton(name, callback_data=f"{prefix}:{code}"))
        if i % 3 == 0:   # 3 buttons per row
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

# -------------------- Handlers --------------------
@bot.on_message(filters.command("start"))
async def start(client, message):
    await message.reply(
        "👋 नमस्ते! मैं वीडियो डबिंग बॉट हूँ।\n"
        "कृपया 20 से 50 सेकंड की वीडियो भेजें।"
    )

@bot.on_message(filters.video)
async def video_handler(client, message):
    # Check video duration
    if message.video.duration < 20 or message.video.duration > 50:
        await message.reply("⚠️ कृपया 20 से 50 सेकंड के बीच की वीडियो भेजें।")
        return

    # Ask for source language
    user_id = message.from_user.id
    user_data[user_id] = {'step': 'source', 'video_path': None}  # reset
    await message.reply(
        "🎤 वीडियो में कौन-सी भाषा बोली जा रही है? (स्रोत भाषा चुनें)",
        reply_markup=lang_keyboard("src")
    )

@bot.on_callback_query()
async def callback_handler(client, callback: CallbackQuery):
    await callback.answer()  # Important!
    user_id = callback.from_user.id
    data = callback.data

    if data.startswith("src:"):
        # Source language selected
        lang_code = data.split(":", 1)[1]
        user_data[user_id]['source_lang'] = lang_code
        user_data[user_id]['step'] = 'target'
        await callback.message.edit_text(
            "🌍 अब वीडियो को किस भाषा में डब करना है? (लक्ष्य भाषा चुनें)",
            reply_markup=lang_keyboard("tgt")
        )

    elif data.startswith("tgt:"):
        # Target language selected
        lang_code = data.split(":", 1)[1]
        user_data[user_id]['target_lang'] = lang_code
        user_data[user_id]['step'] = 'processing'

        await callback.message.edit_text(
            "⏳ प्रोसेसिंग शुरू... कृपया प्रतीक्षा करें (इसमें कुछ मिनट लग सकते हैं)।"
        )

        # Start processing in background
        asyncio.create_task(process_video(callback.message, user_id))

# -------------------- Video Processing --------------------
async def process_video(msg, user_id):
    try:
        data = user_data.get(user_id)
        if not data:
            await msg.edit_text("❌ कोई डेटा नहीं मिला। फिर से शुरू करें /start")
            return

        # Download video
        video_msg = msg.reply_to_message  # the original video message
        if not video_msg or not video_msg.video:
            await msg.edit_text("❌ वीडियो नहीं मिला।")
            return

        await msg.edit_text("📥 वीडियो डाउनलोड हो रहा है...")
        temp_dir = tempfile.mkdtemp()
        video_path = os.path.join(temp_dir, "input_video.mp4")
        await video_msg.download(file_name=video_path)

        # Extract audio
        await msg.edit_text("🎵 ऑडियो निकाला जा रहा है...")
        audio_path = os.path.join(temp_dir, "audio.wav")
        video_clip = mp.VideoFileClip(video_path)
        video_clip.audio.write_audiofile(audio_path, logger=None)
        video_clip.close()

        # Speech to text
        await msg.edit_text("🗣️ आवाज़ को टेक्स्ट में बदला जा रहा है...")
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            audio_data = recognizer.record(source)
            try:
                source_lang = get_sr_lang(data['source_lang'])
                text = recognizer.recognize_google(audio_data, language=source_lang)
            except sr.UnknownValueError:
                await msg.edit_text("❌ आवाज़ साफ नहीं थी, टेक्स्ट नहीं निकाल सके।")
                return
            except sr.RequestError as e:
                await msg.edit_text(f"❌ Google Speech Recognition error: {e}")
                return

        # Translate text
        await msg.edit_text("🔄 टेक्स्ट का अनुवाद किया जा रहा है...")
        target_lang = data['target_lang']
        translated = translator.translate(text, dest=target_lang)
        translated_text = translated.text

        # Generate TTS
        await msg.edit_text("🔊 नई आवाज़ बनाई जा रही है...")
        tts_lang = get_gtts_lang(target_lang)
        tts = gTTS(translated_text, lang=tts_lang)
        tts_path = os.path.join(temp_dir, "tts.mp3")
        tts.save(tts_path)

        # Merge new audio with video
        await msg.edit_text("🎬 वीडियो तैयार किया जा रहा है...")
        video_clip = mp.VideoFileClip(video_path)
        new_audio = mp.AudioFileClip(tts_path)

        # If new audio shorter than video, loop it; if longer, trim it (simplest: set duration to video)
        # For simplicity, we'll set the audio duration to match video exactly
        if new_audio.duration < video_clip.duration:
            # Loop to fill
            n = int(video_clip.duration / new_audio.duration) + 1
            new_audio = mp.concatenate_audioclips([new_audio] * n)
        new_audio = new_audio.subclip(0, video_clip.duration)

        final_video = video_clip.set_audio(new_audio)
        output_path = os.path.join(temp_dir, "output_video.mp4")
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac', logger=None)
        video_clip.close()
        new_audio.close()

        # Send video
        await msg.edit_text("📤 वीडियो भेजा जा रहा है...")
        await msg.reply_video(
            video=output_path,
            caption=f"✅ डबिंग पूरी!\nस्रोत: {LANGS[data['source_lang']]}\nलक्ष्य: {LANGS[data['target_lang']]}"
        )

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        await msg.delete()  # remove processing message

    except Exception as e:
        await msg.edit_text(f"❌ प्रोसेसिंग में त्रुटि: {str(e)}")
        # Cleanup if possible
    finally:
        if user_id in user_data:
            del user_data[user_id]

# -------------------- Main Async Entry --------------------
async def main():
    # Start Flask in background thread
    Thread(target=run_flask, daemon=True).start()

    # Start Pyrogram client
    await bot.start()
    print("Bot started successfully!")
    await idle()
    await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")

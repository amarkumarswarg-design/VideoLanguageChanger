#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Video Dubbing Bot for Telegram
Supports 40+ languages, uses TgCrypto for speed, Flask for Render port binding.
Author: DeepSeek
"""

import os
import sys
import asyncio
import tempfile
import shutil
import time
import logging
import traceback
from threading import Thread
from datetime import datetime
from typing import Dict, Optional, Any

# -------------------- FIX EVENT LOOP FOR PYTHON 3.10+ --------------------
try:
    loop = asyncio.get_running_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# -------------------- THIRD PARTY IMPORTS --------------------
# (Ensure TgCrypto is installed for faster Pyrogram)
try:
    import tgcrypto  # noqa
except ImportError:
    print("TgCrypto not installed. Pyrogram will run slower. Install it for speed.")

from flask import Flask
import pyrogram
from pyrogram import Client, filters, idle
from pyrogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, Message
)
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError

import moviepy.editor as mp
from moviepy.config import change_settings
from googletrans import Translator
from gtts import gTTS
import speech_recognition as sr

# -------------------- CONFIGURE LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# -------------------- FLASK SERVER FOR RENDER PORT --------------------
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is Running! | Uptime: {}".format(datetime.utcnow().isoformat())

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)

# -------------------- CONFIGURATION (ENVIRONMENT VARIABLES) --------------------
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("Missing API_ID, API_HASH or BOT_TOKEN environment variables.")
    sys.exit(1)

# -------------------- LANGUAGE SUPPORT (40+ LANGUAGES) --------------------
# Format: ISO-639-1 code : Display name
LANGS = {
    "af": "Afrikaans", "ar": "العربية (Arabic)", "bg": "Български (Bulgarian)",
    "bn": "বাংলা (Bengali)", "ca": "Català (Catalan)", "cs": "Čeština (Czech)",
    "da": "Dansk (Danish)", "de": "Deutsch (German)", "el": "Ελληνικά (Greek)",
    "en": "English", "es": "Español (Spanish)", "et": "Eesti (Estonian)",
    "fa": "فارسی (Persian)", "fi": "Suomi (Finnish)", "fr": "Français (French)",
    "gu": "ગુજરાતી (Gujarati)", "he": "עברית (Hebrew)", "hi": "हिन्दी (Hindi)",
    "hr": "Hrvatski (Croatian)", "hu": "Magyar (Hungarian)", "id": "Indonesia (Indonesian)",
    "it": "Italiano (Italian)", "ja": "日本語 (Japanese)", "kn": "ಕನ್ನಡ (Kannada)",
    "ko": "한국어 (Korean)", "lt": "Lietuvių (Lithuanian)", "lv": "Latviešu (Latvian)",
    "ml": "മലയാളം (Malayalam)", "mr": "मराठी (Marathi)", "ms": "Bahasa Melayu (Malay)",
    "nl": "Nederlands (Dutch)", "no": "Norsk (Norwegian)", "pa": "ਪੰਜਾਬੀ (Punjabi)",
    "pl": "Polski (Polish)", "pt": "Português (Portuguese)", "ro": "Română (Romanian)",
    "ru": "Русский (Russian)", "sk": "Slovenčina (Slovak)", "sl": "Slovenščina (Slovenian)",
    "sr": "Српски (Serbian)", "sv": "Svenska (Swedish)", "ta": "தமிழ் (Tamil)",
    "te": "తెలుగు (Telugu)", "th": "ไทย (Thai)", "tl": "Tagalog",
    "tr": "Türkçe (Turkish)", "uk": "Українська (Ukrainian)", "ur": "اردو (Urdu)",
    "vi": "Tiếng Việt (Vietnamese)", "zh-cn": "中文 (Chinese Simplified)"
}

# Mapping for Google Speech Recognition (some languages need region codes)
SR_LANG_MAP = {
    "en": "en-US", "hi": "hi-IN", "es": "es-ES", "fr": "fr-FR",
    "de": "de-DE", "ru": "ru-RU", "ar": "ar-SA", "bn": "bn-IN",
    "pt": "pt-PT", "ja": "ja-JP", "ko": "ko-KR", "zh-cn": "zh-CN",
    # For others, fallback to ISO code
}
def get_sr_lang(code):
    return SR_LANG_MAP.get(code, code)

# gTTS uses ISO 639-1 directly
def get_gtts_lang(code):
    return code

# -------------------- INITIALIZE BOT AND TRANSLATOR --------------------
bot = Client(
    "dubbing_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10,  # Number of worker threads
    sleep_threshold=10  # Sleep threshold for flood wait
)
translator = Translator()

# -------------------- USER DATA STORAGE (IN-MEMORY) --------------------
# Structure: user_id -> {
#    'source_lang': str,
#    'target_lang': str,
#    'video_msg_id': int,
#    'step': str ('source'|'target'|'processing'),
#    'temp_dir': str (path),
#    'start_time': float
# }
user_data: Dict[int, Dict[str, Any]] = {}

# -------------------- HELPER: LANGUAGE KEYBOARD (WITH PAGINATION) --------------------
def lang_keyboard(prefix: str, page: int = 0, items_per_page: int = 9):
    """
    Create an inline keyboard with languages, paginated.
    prefix: 'src' or 'tgt'
    page: current page number (0-indexed)
    """
    lang_list = list(LANGS.items())
    total_pages = (len(lang_list) + items_per_page - 1) // items_per_page
    start = page * items_per_page
    end = min(start + items_per_page, len(lang_list))
    current_page_langs = lang_list[start:end]

    buttons = []
    row = []
    for i, (code, name) in enumerate(current_page_langs):
        row.append(InlineKeyboardButton(name, callback_data=f"{prefix}:{code}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # Navigation row
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ पिछला", callback_data=f"{prefix}_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("अगला ▶️", callback_data=f"{prefix}_page:{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons)

# -------------------- HANDLER: /start --------------------
@bot.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    await message.reply(
        "👋 **नमस्ते! मैं वीडियो डबिंग बॉट हूँ।**\n\n"
        "मैं आपकी वीडियो में आवाज़ बदलकर किसी भी 40+ भाषा में डब कर सकता हूँ।\n\n"
        "**बस इतना करें:**\n"
        "1. 20 से 50 सेकंड की वीडियो भेजें।\n"
        "2. वीडियो की भाषा चुनें।\n"
        "3. जिस भाषा में डब करना है, वह चुनें।\n"
        "4. कुछ सेकंड प्रतीक्षा करें।\n\n"
        "✨ **फास्ट प्रोसेसिंग के लिए TgCrypto इंस्टॉल है।**",
        parse_mode=ParseMode.MARKDOWN
    )

# -------------------- HANDLER: VIDEO MESSAGES --------------------
@bot.on_message(filters.video)
async def video_handler(client: Client, message: Message):
    user_id = message.from_user.id
    duration = message.video.duration

    # Check video length
    if duration < 20 or duration > 50:
        await message.reply(
            "⚠️ **कृपया 20 से 50 सेकंड के बीच की वीडियो भेजें।**\n"
            f"आपकी वीडियो की लंबाई: {duration} सेकंड"
        )
        return

    # Store basic info
    user_data[user_id] = {
        'step': 'source',
        'video_msg_id': message.id,
        'start_time': time.time()
    }

    # Ask for source language
    await message.reply(
        "🎤 **वीडियो में कौन-सी भाषा बोली जा रही है?**\n"
        "कृपया स्रोत भाषा चुनें:",
        reply_markup=lang_keyboard("src", 0)
    )

# -------------------- HANDLER: CALLBACK QUERIES (LANGUAGE SELECTION) --------------------
@bot.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    await callback.answer()  # Always answer to stop loading animation
    user_id = callback.from_user.id
    data = callback.data

    # Pagination for source language
    if data.startswith("src_page:"):
        page = int(data.split(":")[1])
        await callback.message.edit_text(
            "🎤 **वीडियो में कौन-सी भाषा बोली जा रही है?**\n"
            "कृपया स्रोत भाषा चुनें:",
            reply_markup=lang_keyboard("src", page)
        )
        return

    # Pagination for target language
    if data.startswith("tgt_page:"):
        page = int(data.split(":")[1])
        await callback.message.edit_text(
            "🌍 **अब वीडियो को किस भाषा में डब करना है?**\n"
            "लक्ष्य भाषा चुनें:",
            reply_markup=lang_keyboard("tgt", page)
        )
        return

    # Source language selected
    if data.startswith("src:"):
        lang_code = data.split(":", 1)[1]
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['source_lang'] = lang_code
        user_data[user_id]['step'] = 'target'

        await callback.message.edit_text(
            "🌍 **अब वीडियो को किस भाषा में डब करना है?**\n"
            "लक्ष्य भाषा चुनें:",
            reply_markup=lang_keyboard("tgt", 0)
        )
        return

    # Target language selected
    if data.startswith("tgt:"):
        lang_code = data.split(":", 1)[1]
        if user_id not in user_data:
            await callback.message.edit_text("❌ **कोई डेटा नहीं मिला।** /start से शुरू करें।")
            return

        user_data[user_id]['target_lang'] = lang_code
        user_data[user_id]['step'] = 'processing'

        # Send processing started message
        processing_msg = await callback.message.edit_text(
            "⏳ **प्रोसेसिंग शुरू...**\n"
            f"स्रोत: {LANGS[user_data[user_id]['source_lang']]}\n"
            f"लक्ष्य: {LANGS[lang_code]}\n\n"
            "यह प्रक्रिया 1-2 मिनट ले सकती है। कृपया धैर्य रखें..."
        )

        # Start processing in background
        asyncio.create_task(process_video(processing_msg, user_id))

# -------------------- VIDEO PROCESSING FUNCTION --------------------
async def process_video(msg: Message, user_id: int):
    """
    Core function: download video, extract audio, speech-to-text, translate, TTS, merge, upload.
    """
    temp_dir = None
    try:
        data = user_data.get(user_id)
        if not data:
            await msg.edit_text("❌ **उपयोगकर्ता डेटा नहीं मिला।** /start से पुनः प्रयास करें।")
            return

        # Get original video message
        video_msg = await msg.chat.get_messages(data['video_msg_id'])
        if not video_msg or not video_msg.video:
            await msg.edit_text("❌ **वीडियो संदेश नहीं मिल सका।** कृपया वीडियो फिर से भेजें।")
            return

        # Step 1: Download video
        await msg.edit_text("📥 **चरण 1/7:** वीडियो डाउनलोड हो रहा है...")
        temp_dir = tempfile.mkdtemp(prefix="dub_")
        video_path = os.path.join(temp_dir, "input_video.mp4")
        await video_msg.download(file_name=video_path)
        logger.info(f"Video downloaded for user {user_id}: {video_path}")

        # Step 2: Extract audio
        await msg.edit_text("🎵 **चरण 2/7:** ऑडियो निकाला जा रहा है...")
        audio_path = os.path.join(temp_dir, "audio.wav")
        video_clip = mp.VideoFileClip(video_path)
        video_clip.audio.write_audiofile(audio_path, logger=None, verbose=False)
        video_clip.close()
        logger.info(f"Audio extracted: {audio_path}")

        # Step 3: Speech to Text
        await msg.edit_text("🗣️ **चरण 3/7:** आवाज़ को टेक्स्ट में बदला जा रहा है...")
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            # Adjust for ambient noise
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio_data = recognizer.record(source)

        try:
            source_lang = get_sr_lang(data['source_lang'])
            text = recognizer.recognize_google(audio_data, language=source_lang, show_all=False)
            logger.info(f"Recognized text ({source_lang}): {text[:100]}")
        except sr.UnknownValueError:
            await msg.edit_text("❌ **आवाज़ साफ नहीं थी।** कृपया बेहतर ऑडियो गुणवत्ता वाली वीडियो भेजें।")
            return
        except sr.RequestError as e:
            await msg.edit_text(f"❌ **Google Speech Recognition में त्रुटि:** {e}")
            return
        except Exception as e:
            await msg.edit_text(f"❌ **अप्रत्याशित त्रुटि:** {e}")
            return

        # Step 4: Translate text
        await msg.edit_text("🔄 **चरण 4/7:** टेक्स्ट का अनुवाद किया जा रहा है...")
        target_lang = data['target_lang']
        try:
            translated = translator.translate(text, dest=target_lang)
            translated_text = translated.text
            logger.info(f"Translated to {target_lang}: {translated_text[:100]}")
        except Exception as e:
            await msg.edit_text(f"❌ **अनुवाद में त्रुटि:** {e}")
            return

        # Step 5: Text-to-Speech (TTS)
        await msg.edit_text("🔊 **चरण 5/7:** नई आवाज़ बनाई जा रही है...")
        tts_lang = get_gtts_lang(target_lang)
        try:
            tts = gTTS(translated_text, lang=tts_lang, slow=False)
            tts_path = os.path.join(temp_dir, "tts.mp3")
            tts.save(tts_path)
            logger.info(f"TTS saved: {tts_path}")
        except Exception as e:
            await msg.edit_text(f"❌ **TTS निर्माण में त्रुटि:** {e}")
            return

        # Step 6: Merge new audio with video
        await msg.edit_text("🎬 **चरण 6/7:** वीडियो तैयार किया जा रहा है...")
        video_clip = mp.VideoFileClip(video_path)
        new_audio = mp.AudioFileClip(tts_path)

        # Adjust audio duration to match video
        if new_audio.duration < video_clip.duration:
            # Loop audio to fill
            n = int(video_clip.duration / new_audio.duration) + 1
            new_audio = mp.concatenate_audioclips([new_audio] * n)
        new_audio = new_audio.subclip(0, video_clip.duration)

        final_video = video_clip.set_audio(new_audio)
        output_path = os.path.join(temp_dir, "output_video.mp4")
        final_video.write_videofile(
            output_path,
            codec='libx264',
            audio_codec='aac',
            temp_audiofile=os.path.join(temp_dir, 'temp-audio.m4a'),
            remove_temp=True,
            logger=None,
            verbose=False
        )
        video_clip.close()
        new_audio.close()
        logger.info(f"Final video created: {output_path}")

        # Step 7: Upload video
        await msg.edit_text("📤 **चरण 7/7:** वीडियो भेजा जा रहा है...")
        caption = (
            f"✅ **डबिंग पूरी!**\n\n"
            f"**स्रोत भाषा:** {LANGS[data['source_lang']]}\n"
            f"**लक्ष्य भाषा:** {LANGS[target_lang]}\n"
            f"**अनुवादित टेक्स्ट:**\n`{translated_text[:200]}`" + ("..." if len(translated_text) > 200 else "")
        )
        await msg.reply_video(
            video=output_path,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN,
            supports_streaming=True
        )

        # Cleanup
        await msg.delete()  # remove processing message
        logger.info(f"Processing completed for user {user_id}")

    except FloodWait as e:
        logger.warning(f"FloodWait: {e.value} seconds")
        await msg.edit_text(f"⏳ **बहुत अधिक अनुरोध।** कृपया {e.value} सेकंड प्रतीक्षा करें।")
    except RPCError as e:
        logger.error(f"Telegram RPC error: {e}")
        await msg.edit_text(f"❌ **Telegram API त्रुटि:** {e}")
    except Exception as e:
        logger.error(f"Unexpected error in process_video: {traceback.format_exc()}")
        await msg.edit_text(f"❌ **प्रोसेसिंग में अप्रत्याशित त्रुटि:** {str(e)}")
    finally:
        # Clean up temporary directory
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        # Remove user data
        if user_id in user_data:
            del user_data[user_id]

# -------------------- HANDLER: UNSUPPORTED MESSAGES --------------------
@bot.on_message(filters.command("help"))
async def help_command(client: Client, message: Message):
    await message.reply(
        "**सहायता**\n\n"
        "• 20-50 सेकंड की वीडियो भेजें।\n"
        "• स्रोत और लक्ष्य भाषा चुनें।\n"
        "• प्रोसेसिंग के बाद डब वीडियो मिलेगा।\n\n"
        "**सभी 40+ भाषाएँ सपोर्टेड हैं।**"
    )

@bot.on_message(filters.audio | filters.document | filters.photo)
async def unsupported_handler(client: Client, message: Message):
    await message.reply("❌ **केवल वीडियो फ़ाइलें स्वीकार की जाती हैं।** कृपया 20-50 सेकंड की वीडियो भेजें।")

@bot.on_message(filters.text & ~filters.command(["start", "help"]))
async def text_handler(client: Client, message: Message):
    await message.reply("कृपया वीडियो भेजें। /start देखें।")

# -------------------- MAIN FUNCTION --------------------
async def main():
    # Start Flask in background thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask server started on port %s", os.environ.get("PORT", 8080))

    # Start Pyrogram bot
    await bot.start()
    logger.info("Bot started successfully! @%s", bot.me.username)

    # Keep bot running
    await idle()

    # Stop bot
    await bot.stop()
    logger.info("Bot stopped.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        sys.exit(1)

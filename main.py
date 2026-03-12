import os
import sys
import asyncio
import tempfile
import shutil
import logging
import traceback
from threading import Thread
from datetime import datetime

# -------------------- FIX EVENT LOOP FOR PYTHON 3.10+ --------------------
try:
    loop = asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# -------------------- LOGGING --------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# -------------------- FLASK FOR RENDER PORT --------------------
from flask import Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running! | Uptime: {}".format(datetime.utcnow().isoformat())

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, threaded=True)

# -------------------- ENVIRONMENT VARIABLES --------------------
API_ID = int(os.environ.get("API_ID", 0))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

if not API_ID or not API_HASH or not BOT_TOKEN:
    logger.error("Missing API_ID, API_HASH or BOT_TOKEN environment variables.")
    sys.exit(1)

# -------------------- TGCRYPTO (SPEED) --------------------
try:
    import tgcrypto
    logger.info("TgCrypto installed. Pyrogram will run fast.")
except ImportError:
    logger.warning("TgCrypto not installed. Pyrogram will run slower. Install it for speed.")

# -------------------- PYROGRAM --------------------
from pyrogram import Client, filters, idle
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait, RPCError

# -------------------- VIDEO PROCESSING --------------------
# सही तरीके से moviepy इम्पोर्ट करें
try:
    import moviepy.editor as mp
    # ffmpeg की उपलब्धता सुनिश्चित करें
    import imageio_ffmpeg
    mp.change_settings({"FFMPEG_BINARY": imageio_ffmpeg.get_ffmpeg_exe()})
    logger.info("MoviePy imported successfully with ffmpeg.")
except ImportError as e:
    logger.error(f"MoviePy import failed: {e}")
    logger.error("Please ensure moviepy and imageio-ffmpeg are installed.")
    sys.exit(1)

from googletrans import Translator
from gtts import gTTS
import speech_recognition as sr

# -------------------- LANGUAGE DATA --------------------
# 1. बॉट इंटरफ़ेस के लिए भाषाएँ (UI भाषा)
UI_LANGS = {
    "hi": "हिन्दी",
    "en": "English",
    "ru": "Русский",
    "ar": "العربية",
    "es": "Español",
    "fr": "Français",
    "de": "Deutsch",
    "zh-cn": "中文"
}

# 2. डबिंग के लिए 40+ भाषाएँ (स्रोत और लक्ष्य)
DUB_LANGS = {
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

# Speech Recognition के लिए भाषा मैपिंग (कुछ भाषाओं को क्षेत्रीय कोड चाहिए)
SR_LANG_MAP = {
    "en": "en-US", "hi": "hi-IN", "es": "es-ES", "fr": "fr-FR",
    "de": "de-DE", "ru": "ru-RU", "ar": "ar-SA", "bn": "bn-IN",
    "pt": "pt-PT", "ja": "ja-JP", "ko": "ko-KR", "zh-cn": "zh-CN",
}
def get_sr_lang(code):
    return SR_LANG_MAP.get(code, code)

# gTTS के लिए सीधे ISO कोड
def get_gtts_lang(code):
    return code

# -------------------- BOT CLIENT --------------------
bot = Client(
    "dubbing_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=10,
    sleep_threshold=10
)
translator = Translator()

# -------------------- USER DATA STORAGE --------------------
# user_id -> {
#   'ui_lang': 'hi',  # बॉट इंटरफ़ेस की भाषा
#   'source_lang': None,
#   'target_lang': None,
#   'video_msg_id': None,
#   'step': 'ui_lang'|'source'|'target'|'processing',
#   'temp_dir': None
# }
user_data = {}

# -------------------- HELPER: GET LOCALIZED TEXT --------------------
def get_text(ui_lang, key):
    """key के अनुसार स्थानीय भाषा में टेक्स्ट लौटाएँ"""
    texts = {
        "hi": {
            "welcome": "👋 नमस्ते! मैं वीडियो डबिंग बॉट हूँ।\nकृपया अपनी पसंदीदा भाषा चुनें:",
            "choose_ui_lang": "🌐 कृपया बॉट की भाषा चुनें:",
            "ui_lang_set": "✅ भाषा सेट हो गई: {}",
            "send_video": "🎥 अब 20 से 50 सेकंड की वीडियो भेजें।",
            "video_length_error": "⚠️ कृपया 20 से 50 सेकंड के बीच की वीडियो भेजें। आपकी वीडियो {} सेकंड की है।",
            "choose_source": "🎤 वीडियो में कौन-सी भाषा बोली जा रही है? (स्रोत भाषा चुनें)",
            "choose_target": "🌍 अब वीडियो को किस भाषा में डब करना है? (लक्ष्य भाषा चुनें)",
            "processing_start": "⏳ प्रोसेसिंग शुरू...\nस्रोत: {}\nलक्ष्य: {}\nकृपया प्रतीक्षा करें (1-2 मिनट)।",
            "step_download": "📥 चरण 1/7: वीडियो डाउनलोड हो रहा है...",
            "step_audio": "🎵 चरण 2/7: ऑडियो निकाला जा रहा है...",
            "step_stt": "🗣️ चरण 3/7: आवाज़ को टेक्स्ट में बदला जा रहा है...",
            "step_translate": "🔄 चरण 4/7: टेक्स्ट का अनुवाद किया जा रहा है...",
            "step_tts": "🔊 चरण 5/7: नई आवाज़ बनाई जा रही है...",
            "step_merge": "🎬 चरण 6/7: वीडियो तैयार किया जा रहा है...",
            "step_upload": "📤 चरण 7/7: वीडियो भेजा जा रहा है...",
            "success": "✅ डबिंग पूरी!\n\nस्रोत: {}\nलक्ष्य: {}\n\nअनुवादित टेक्स्ट:\n{}",
            "error_no_data": "❌ कोई डेटा नहीं मिला। /start से शुरू करें।",
            "error_video_not_found": "❌ वीडियो नहीं मिला। कृपया फिर से भेजें।",
            "error_stt_failed": "❌ आवाज़ साफ नहीं थी। कृपया बेहतर ऑडियो वाली वीडियो भेजें।",
            "error_general": "❌ प्रोसेसिंग में त्रुटि: {}",
        },
        "en": {
            "welcome": "👋 Hello! I am a video dubbing bot.\nPlease choose your preferred language:",
            "choose_ui_lang": "🌐 Please choose bot language:",
            "ui_lang_set": "✅ Language set to: {}",
            "send_video": "🎥 Now send a video of 20-50 seconds.",
            "video_length_error": "⚠️ Please send a video between 20-50 seconds. Your video is {} seconds.",
            "choose_source": "🎤 What language is spoken in the video? (Source language)",
            "choose_target": "🌍 Now choose the target language for dubbing:",
            "processing_start": "⏳ Processing started...\nSource: {}\nTarget: {}\nPlease wait (1-2 minutes).",
            "step_download": "📥 Step 1/7: Downloading video...",
            "step_audio": "🎵 Step 2/7: Extracting audio...",
            "step_stt": "🗣️ Step 3/7: Converting speech to text...",
            "step_translate": "🔄 Step 4/7: Translating text...",
            "step_tts": "🔊 Step 5/7: Generating new audio...",
            "step_merge": "🎬 Step 6/7: Merging audio with video...",
            "step_upload": "📤 Step 7/7: Uploading video...",
            "success": "✅ Dubbing complete!\n\nSource: {}\nTarget: {}\n\nTranslated text:\n{}",
            "error_no_data": "❌ No data found. Please /start again.",
            "error_video_not_found": "❌ Video not found. Please send again.",
            "error_stt_failed": "❌ Speech not clear. Please send a video with better audio.",
            "error_general": "❌ Processing error: {}",
        },
        # आप चाहें तो और भाषाएँ जोड़ सकते हैं (ru, ar, etc.)
    }
    # अगर चुनी हुई भाषा उपलब्ध न हो तो अंग्रेज़ी इस्तेमाल करें
    if ui_lang not in texts:
        ui_lang = "en"
    return texts[ui_lang].get(key, key)

# -------------------- KEYBOARD BUILDERS --------------------
def ui_lang_keyboard():
    """बॉट इंटरफ़ेस भाषा चुनने के लिए कीबोर्ड"""
    buttons = []
    row = []
    for i, (code, name) in enumerate(UI_LANGS.items(), 1):
        row.append(InlineKeyboardButton(name, callback_data=f"ui:{code}"))
        if i % 3 == 0:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    return InlineKeyboardMarkup(buttons)

def dub_lang_keyboard(prefix, ui_lang, page=0):
    """डबिंग भाषा चुनने के लिए कीबोर्ड (40+ भाषाएँ)"""
    items_per_page = 9
    lang_list = list(DUB_LANGS.items())
    total_pages = (len(lang_list) + items_per_page - 1) // items_per_page
    start = page * items_per_page
    end = min(start + items_per_page, len(lang_list))
    current_page = lang_list[start:end]

    buttons = []
    row = []
    for i, (code, name) in enumerate(current_page):
        # नाम को UI भाषा में दिखाने के लिए यहाँ सिर्फ अंग्रेज़ी नाम ही रखा है
        # आप चाहें तो हर भाषा का नाम UI भाषा में अनुवाद कर सकते हैं
        row.append(InlineKeyboardButton(name, callback_data=f"{prefix}:{code}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    # नेविगेशन बटन
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("◀️ " + ("पिछला" if ui_lang=="hi" else "Previous"), callback_data=f"{prefix}_page:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(("अगला" if ui_lang=="hi" else "Next") + " ▶️", callback_data=f"{prefix}_page:{page+1}"))
    if nav_buttons:
        buttons.append(nav_buttons)

    return InlineKeyboardMarkup(buttons)

# -------------------- HANDLERS --------------------
@bot.on_message(filters.command("start"))
async def start_command(client: Client, message: Message):
    user_id = message.from_user.id
    # पहली बार, UI भाषा चुनने के लिए कहें
    user_data[user_id] = {'step': 'ui_lang'}
    await message.reply(
        get_text("en", "welcome"),  # डिफ़ॉल्ट अंग्रेज़ी में स्वागत
        reply_markup=ui_lang_keyboard()
    )

@bot.on_callback_query()
async def callback_handler(client: Client, callback: CallbackQuery):
    await callback.answer()
    user_id = callback.from_user.id
    data = callback.data

    # UI भाषा चयन
    if data.startswith("ui:"):
        ui_lang = data.split(":", 1)[1]
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['ui_lang'] = ui_lang
        user_data[user_id]['step'] = 'video_wait'
        await callback.message.edit_text(
            get_text(ui_lang, "send_video")
        )
        return

    # बाकी सब काम के लिए UI भाषा चाहिए
    if user_id not in user_data or 'ui_lang' not in user_data[user_id]:
        await callback.message.edit_text("❌ Please /start again.")
        return
    ui_lang = user_data[user_id]['ui_lang']

    # पेजिनेशन हैंडलिंग
    if data.startswith("src_page:"):
        page = int(data.split(":")[1])
        await callback.message.edit_text(
            get_text(ui_lang, "choose_source"),
            reply_markup=dub_lang_keyboard("src", ui_lang, page)
        )
        return
    if data.startswith("tgt_page:"):
        page = int(data.split(":")[1])
        await callback.message.edit_text(
            get_text(ui_lang, "choose_target"),
            reply_markup=dub_lang_keyboard("tgt", ui_lang, page)
        )
        return

    # स्रोत भाषा चयन
    if data.startswith("src:"):
        lang_code = data.split(":", 1)[1]
        user_data[user_id]['source_lang'] = lang_code
        user_data[user_id]['step'] = 'target'
        await callback.message.edit_text(
            get_text(ui_lang, "choose_target"),
            reply_markup=dub_lang_keyboard("tgt", ui_lang, 0)
        )
        return

    # लक्ष्य भाषा चयन
    if data.startswith("tgt:"):
        lang_code = data.split(":", 1)[1]
        user_data[user_id]['target_lang'] = lang_code
        user_data[user_id]['step'] = 'processing'

        processing_msg = await callback.message.edit_text(
            get_text(ui_lang, "processing_start").format(
                DUB_LANGS[user_data[user_id]['source_lang']],
                DUB_LANGS[lang_code]
            )
        )
        # प्रोसेसिंग शुरू करें
        asyncio.create_task(process_video(processing_msg, user_id))

@bot.on_message(filters.video)
async def video_handler(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in user_data or 'ui_lang' not in user_data[user_id]:
        await message.reply("❌ Please /start first.")
        return
    if user_data[user_id].get('step') != 'video_wait':
        await message.reply("❌ Please /start first.")
        return

    ui_lang = user_data[user_id]['ui_lang']
    duration = message.video.duration

    if duration < 20 or duration > 50:
        await message.reply(get_text(ui_lang, "video_length_error").format(duration))
        return

    user_data[user_id]['video_msg_id'] = message.id
    user_data[user_id]['step'] = 'source'
    await message.reply(
        get_text(ui_lang, "choose_source"),
        reply_markup=dub_lang_keyboard("src", ui_lang, 0)
    )

# -------------------- VIDEO PROCESSING --------------------
async def process_video(msg: Message, user_id: int):
    temp_dir = None
    try:
        data = user_data.get(user_id)
        if not data:
            await msg.edit_text(get_text("en", "error_no_data"))
            return
        ui_lang = data['ui_lang']
        source_lang = data['source_lang']
        target_lang = data['target_lang']
        video_msg_id = data['video_msg_id']

        # वीडियो मैसेज लाएँ
        video_msg = await msg.chat.get_messages(video_msg_id)
        if not video_msg or not video_msg.video:
            await msg.edit_text(get_text(ui_lang, "error_video_not_found"))
            return

        # डाउनलोड
        await msg.edit_text(get_text(ui_lang, "step_download"))
        temp_dir = tempfile.mkdtemp(prefix="dub_")
        video_path = os.path.join(temp_dir, "input_video.mp4")
        await video_msg.download(file_name=video_path)
        logger.info(f"Video downloaded for user {user_id}")

        # ऑडियो निकालें
        await msg.edit_text(get_text(ui_lang, "step_audio"))
        audio_path = os.path.join(temp_dir, "audio.wav")
        video_clip = mp.VideoFileClip(video_path)
        video_clip.audio.write_audiofile(audio_path, logger=None, verbose=False)
        video_clip.close()

        # Speech to Text
        await msg.edit_text(get_text(ui_lang, "step_stt"))
        recognizer = sr.Recognizer()
        with sr.AudioFile(audio_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=1)
            audio_data = recognizer.record(source)
        try:
            text = recognizer.recognize_google(audio_data, language=get_sr_lang(source_lang))
            logger.info(f"Recognized text: {text[:100]}")
        except sr.UnknownValueError:
            await msg.edit_text(get_text(ui_lang, "error_stt_failed"))
            return
        except Exception as e:
            await msg.edit_text(get_text(ui_lang, "error_general").format(str(e)))
            return

        # अनुवाद
        await msg.edit_text(get_text(ui_lang, "step_translate"))
        translated = translator.translate(text, dest=target_lang)
        translated_text = translated.text
        logger.info(f"Translated text: {translated_text[:100]}")

        # TTS
        await msg.edit_text(get_text(ui_lang, "step_tts"))
        tts = gTTS(translated_text, lang=get_gtts_lang(target_lang), slow=False)
        tts_path = os.path.join(temp_dir, "tts.mp3")
        tts.save(tts_path)

        # मर्ज
        await msg.edit_text(get_text(ui_lang, "step_merge"))
        video_clip = mp.VideoFileClip(video_path)
        new_audio = mp.AudioFileClip(tts_path)

        if new_audio.duration < video_clip.duration:
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

        # अपलोड
        await msg.edit_text(get_text(ui_lang, "step_upload"))
        caption = get_text(ui_lang, "success").format(
            DUB_LANGS[source_lang],
            DUB_LANGS[target_lang],
            translated_text[:200] + ("..." if len(translated_text) > 200 else "")
        )
        await msg.reply_video(
            video=output_path,
            caption=caption,
            parse_mode=ParseMode.MARKDOWN
        )
        await msg.delete()  # प्रोसेसिंग मैसेज हटाएँ
        logger.info(f"Processing complete for user {user_id}")

    except FloodWait as e:
        logger.warning(f"FloodWait: {e.value}")
        await msg.edit_text(f"⏳ Too many requests. Please wait {e.value} seconds.")
    except RPCError as e:
        logger.error(f"RPC error: {e}")
        await msg.edit_text(f"❌ Telegram API error: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {traceback.format_exc()}")
        await msg.edit_text(get_text(ui_lang if 'ui_lang' in locals() else "en", "error_general").format(str(e)))
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        if user_id in user_data:
            # step को वापस video_wait पर सेट करें ताकि अगली वीडियो भेज सके
            if user_id in user_data:
                user_data[user_id]['step'] = 'video_wait'

# -------------------- MAIN --------------------
async def main():
    # Flask चलाएँ
    Thread(target=run_flask, daemon=True).start()
    logger.info("Flask server started.")

    # बॉट शुरू करें
    await bot.start()
    logger.info(f"Bot started: @{bot.me.username}")

    await idle()
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

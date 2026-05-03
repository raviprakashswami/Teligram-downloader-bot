import os
import re
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
import yt_dlp
import requests
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def detect_platform(url: str) -> str:
    if re.search(r'(youtube\.com|youtu\.be)', url):
        return 'youtube'
    elif re.search(r'instagram\.com', url):
        return 'instagram'
    elif re.search(r'facebook\.com|fb\.watch', url):
        return 'facebook'
    elif re.search(r'pinterest\.com|pin\.it', url):
        return 'pinterest'
    elif re.search(r'twitter\.com|x\.com', url):
        return 'twitter'
    return 'unknown'

def is_valid_url(url: str) -> bool:
    return url.startswith('http://') or url.startswith('https://')

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Namaste! Media Downloader Bot mein aapka swagat hai!*\n\n"
        "🔗 Koi bhi public video/post ka link bhejo:\n\n"
        "✅ *Supported Platforms:*\n"
        "• 🎬 YouTube (Video + MP3)\n"
        "• 📸 Instagram (Reels, Posts)\n"
        "• 📘 Facebook (Public Videos)\n"
        "• 📌 Pinterest (Images, Videos)\n"
        "• 🐦 Twitter/X (Videos)\n\n"
        "💡 *Link bhejo aur format choose karo!*",
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Help Guide:*\n\n"
        "1️⃣ Public video ka link copy karo\n"
        "2️⃣ Yahan paste karo\n"
        "3️⃣ Format choose karo (MP3 ya Video)\n"
        "4️⃣ Quality choose karo\n"
        "5️⃣ Download enjoy karo! 🎉\n\n"
        "⚠️ *Note:* Sirf public content download hoga",
        parse_mode='Markdown'
    )

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_valid_url(url):
        await update.message.reply_text("❌ Yeh valid URL nahi hai. Kripya sahi link bhejein.")
        return

    platform = detect_platform(url)

    if platform == 'unknown':
        await update.message.reply_text(
            "⚠️ Yeh platform supported nahi hai.\n"
            "Supported: YouTube, Instagram, Facebook, Pinterest, Twitter"
        )
        return

    platform_emoji = {
        'youtube': '🎬', 'instagram': '📸',
        'facebook': '📘', 'pinterest': '📌', 'twitter': '🐦'
    }

    context.user_data['url'] = url
    context.user_data['platform'] = platform

    keyboard = [
        [
            InlineKeyboardButton("🎵 MP3 (Audio)", callback_data="format_mp3"),
            InlineKeyboardButton("🎬 Video", callback_data="format_video"),
        ]
    ]

    await update.message.reply_text(
        f"{platform_emoji.get(platform, '🔗')} *{platform.capitalize()}* link mila!\n\n"
        f"📥 *Kaunsa format chahiye?*",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "format_mp3":
        context.user_data['format'] = 'mp3'
        keyboard = [[InlineKeyboardButton("🎵 Best Quality MP3", callback_data="quality_mp3_best")]]
        await query.edit_message_text(
            "🎵 *MP3 Download*\n\nQuality choose karo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data == "format_video":
        context.user_data['format'] = 'video'
        platform = context.user_data.get('platform', '')

        if platform == 'youtube':
            keyboard = [
                [InlineKeyboardButton("🔵 1080p (Full HD)", callback_data="quality_1080")],
                [InlineKeyboardButton("🟢 720p (HD)", callback_data="quality_720")],
                [InlineKeyboardButton("🟡 480p (SD)", callback_data="quality_480")],
                [InlineKeyboardButton("🔴 360p (Low)", callback_data="quality_360")],
            ]
        else:
            keyboard = [
                [InlineKeyboardButton("⭐ Best Quality", callback_data="quality_best")],
                [InlineKeyboardButton("📱 Medium Quality", callback_data="quality_medium")],
            ]

        await query.edit_message_text(
            "🎬 *Video Download*\n\nQuality choose karo:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

    elif data.startswith("quality_"):
        quality = data.replace("quality_", "")
        context.user_data['quality'] = quality
        await query.edit_message_text("⏳ *Downloading... please wait!*", parse_mode='Markdown')
        await download_and_send(query, context)

async def download_youtube_rapidapi(url, fmt, quality, chat_id, context):
    """YouTube download using RapidAPI YouTube Media Downloader"""
    RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY", "")
    if not RAPIDAPI_KEY:
        raise Exception("RAPIDAPI_KEY not set")

    # Extract video ID
    video_id = None
    if 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[1].split('?')[0]
    elif 'v=' in url:
        video_id = url.split('v=')[1].split('&')[0]

    if not video_id:
        raise Exception("YouTube video ID nahi mila")

    headers = {
        "x-rapidapi-host": "youtube-media-downloader.p.rapidapi.com",
        "x-rapidapi-key": RAPIDAPI_KEY,
    }

    # Get video info
    info_url = "https://youtube-media-downloader.p.rapidapi.com/v2/video/details"
    params = {"videoId": video_id}
    resp = requests.get(info_url, headers=headers, params=params, timeout=30)
    data = resp.json()

    if not data.get('status'):
        raise Exception(f"API Error: {data.get('message', 'Unknown error')}")

    title = data.get('title', 'video')[:50]

    if fmt == 'mp3':
        # Get audio streams
        audios = data.get('audios', [])
        if not audios:
            raise Exception("Audio stream nahi mila")
        audio_url = audios[0].get('url')
        ext = 'mp3'
    else:
        # Get video streams
        quality_map = {'1080': 1080, '720': 720, '480': 480, '360': 360, 'best': 9999, 'medium': 480}
        target_height = quality_map.get(quality, 720)

        videos = data.get('videos', {}).get('items', [])
        if not videos:
            raise Exception("Video stream nahi mila")

        # Find best matching quality
        best = None
        for v in videos:
            h = v.get('height', 0)
            if h <= target_height:
                if best is None or h > best.get('height', 0):
                    best = v

        if not best:
            best = videos[-1]

        audio_url = None
        audios = data.get('audios', [])
        if audios:
            audio_url = audios[0].get('url')

        video_dl_url = best.get('url')
        ext = 'mp4'
        title_safe = re.sub(r'[^\w\s-]', '', title).strip()[:40]
        video_path = f"{DOWNLOAD_DIR}/{title_safe}.mp4"

        await context.bot.send_message(chat_id=chat_id, text=f"📤 Uploading: {title}...")

        # Download video
        v_resp = requests.get(video_dl_url, stream=True, timeout=60)
        with open(video_path, 'wb') as vf:
            for chunk in v_resp.iter_content(chunk_size=8192):
                vf.write(chunk)

        file_size = os.path.getsize(video_path)
        if file_size > 50 * 1024 * 1024:
            os.remove(video_path)
            await context.bot.send_message(chat_id=chat_id, text="❌ File 50MB se badi hai! Chhoti quality try karo.")
            return

        with open(video_path, 'rb') as vf:
            await context.bot.send_video(chat_id=chat_id, video=vf, supports_streaming=True)
        os.remove(video_path)
        return

    # Download audio (MP3)
    title_safe = re.sub(r'[^\w\s-]', '', title).strip()[:40]
    audio_path = f"{DOWNLOAD_DIR}/{title_safe}.mp3"
    a_resp = requests.get(audio_url, stream=True, timeout=60)
    with open(audio_path, 'wb') as af:
        for chunk in a_resp.iter_content(chunk_size=8192):
            af.write(chunk)

    await context.bot.send_message(chat_id=chat_id, text=f"📤 Uploading: {title}...")

    with open(audio_path, 'rb') as af:
        await context.bot.send_audio(chat_id=chat_id, audio=af, title=title)
    os.remove(audio_path)


async def download_and_send(query, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data.get('url')
    fmt = context.user_data.get('format')
    quality = context.user_data.get('quality')
    chat_id = query.message.chat_id
    platform = context.user_data.get('platform', '')

    # Clean old files
    for f in os.listdir(DOWNLOAD_DIR):
        try:
            os.remove(os.path.join(DOWNLOAD_DIR, f))
        except:
            pass

    try:
        # YouTube - use RapidAPI
        if platform == 'youtube':
            await download_youtube_rapidapi(url, fmt, quality, chat_id, context)
            return

        # Other platforms - use yt-dlp
        base_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
        }

        if fmt == 'mp3':
            ydl_opts = {
                **base_opts,
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            }
        else:
            quality_map = {
                '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]',
                '720':  'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]',
                '480':  'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
                '360':  'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360]',
                'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best',
                'medium': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]',
            }
            ydl_opts = {
                **base_opts,
                'format': quality_map.get(quality, 'best'),
                'merge_output_format': 'mp4',
            }

        loop = asyncio.get_event_loop()

        def do_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=True)

        info = await loop.run_in_executor(None, do_download)
        title = info.get('title', 'video')[:50]

        downloaded_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            full_path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(full_path):
                downloaded_file = full_path
                break

        if not downloaded_file:
            raise Exception("File nahi mili")

        file_size = os.path.getsize(downloaded_file)
        if file_size > 50 * 1024 * 1024:
            os.remove(downloaded_file)
            await context.bot.send_message(chat_id=chat_id, text="❌ File 50MB se badi hai!\nChhoti quality try karo!")
            return

        await context.bot.send_message(chat_id=chat_id, text=f"📤 Uploading: {title}...")

        with open(downloaded_file, 'rb') as f:
            if fmt == 'mp3':
                await context.bot.send_audio(chat_id=chat_id, audio=f, title=title)
            else:
                await context.bot.send_video(chat_id=chat_id, video=f, supports_streaming=True)

        os.remove(downloaded_file)

    except Exception as e:
        logger.error(f"Error: {e}")
        for f in os.listdir(DOWNLOAD_DIR):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except:
                pass

        err = str(e).lower()
        if 'private' in err or 'login' in err:
            msg = "🔒 Yeh private content hai!"
        elif 'unavailable' in err:
            msg = "❌ Video unavailable hai."
        else:
            msg = f"❌ Download fail hua.\n{str(e)[:150]}"

        await context.bot.send_message(chat_id=chat_id, text=msg)

async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable set nahi hai!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("🤖 Bot starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == '__main__':
    asyncio.run(main())

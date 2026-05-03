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

# Cobalt API instances - multiple fallbacks
COBALT_INSTANCES = [
    "https://cobalt.api.bludger.de",
    "https://cobalt.serenov.dev",
    "https://api.cobalt.tools",
]

async def download_youtube_cobalt(url, fmt, quality, chat_id, context):
    """YouTube download using Cobalt API - free, no key needed"""
    
    quality_map = {'1080': '1080', '720': '720', '480': '480', '360': '360', 'best': '1080', 'medium': '480', 'mp3_best': '320'}
    
    payload = {
        "url": url,
        "videoQuality": quality_map.get(quality, '720'),
        "audioFormat": "mp3" if fmt == 'mp3' else "best",
        "filenameStyle": "basic",
    }
    if fmt == 'mp3':
        payload["downloadMode"] = "audio"
    
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    
    download_url = None
    last_error = None
    
    for instance in COBALT_INSTANCES:
        try:
            resp = requests.post(instance, json=payload, headers=headers, timeout=20)
            data = resp.json()
            logger.info(f"Cobalt response from {instance}: {data}")
            
            status = data.get('status', '')
            if status in ('tunnel', 'redirect', 'stream'):
                download_url = data.get('url')
                break
            elif status == 'picker':
                items = data.get('picker', [])
                if items:
                    download_url = items[0].get('url')
                    break
            else:
                last_error = data.get('error', {}).get('code', str(data))
        except Exception as e:
            last_error = str(e)
            continue
    
    if not download_url:
        raise Exception(f"Cobalt API se download link nahi mila: {last_error}")
    
    ext = 'mp3' if fmt == 'mp3' else 'mp4'
    file_path = f"{DOWNLOAD_DIR}/youtube_video.{ext}"
    
    dl_resp = requests.get(download_url, stream=True, timeout=120)
    with open(file_path, 'wb') as f:
        for chunk in dl_resp.iter_content(chunk_size=65536):
            f.write(chunk)
    
    file_size = os.path.getsize(file_path)
    if file_size > 50 * 1024 * 1024:
        os.remove(file_path)
        await context.bot.send_message(chat_id=chat_id, text="❌ File 50MB se badi hai! Chhoti quality try karo.")
        return
    
    await context.bot.send_message(chat_id=chat_id, text="📤 Uploading...")
    
    with open(file_path, 'rb') as f:
        if fmt == 'mp3':
            await context.bot.send_audio(chat_id=chat_id, audio=f, title="YouTube Audio")
        else:
            await context.bot.send_video(chat_id=chat_id, video=f, supports_streaming=True)
    
    os.remove(file_path)


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
            await download_youtube_cobalt(url, fmt, quality, chat_id, context)
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

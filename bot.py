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

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
DOWNLOAD_DIR = "/tmp/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ─── Platform Detection ───────────────────────────────────────────────────────

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
    else:
        return 'unknown'

def is_valid_url(url: str) -> bool:
    pattern = re.compile(
        r'^(https?://)'
        r'(\w+\.)+\w{2,}'
        r'(/\S*)?$'
    )
    return bool(pattern.match(url.strip()))

# ─── Command Handlers ─────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Namaste! Media Downloader Bot mein aapka swagat hai!*\n\n"
        "🔗 Bas koi bhi public video/post ka link bhejo:\n\n"
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
        "1️⃣ Koi bhi public video ka link copy karo\n"
        "2️⃣ Yahan paste karo\n"
        "3️⃣ Format choose karo (MP3 ya Video)\n"
        "4️⃣ Quality choose karo\n"
        "5️⃣ Download enjoy karo! 🎉\n\n"
        "⚠️ *Note:* Sirf public content download hoga",
        parse_mode='Markdown'
    )

# ─── URL Handler ─────────────────────────────────────────────────────────────

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()

    if not is_valid_url(url):
        await update.message.reply_text("❌ Yeh valid URL nahi hai. Kripya sahi link bhejein.")
        return

    platform = detect_platform(url)

    if platform == 'unknown':
        await update.message.reply_text(
            "⚠️ Yeh platform abhi supported nahi hai.\n"
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

# ─── Callback Handler ─────────────────────────────────────────────────────────

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

# ─── Download & Send ──────────────────────────────────────────────────────────

async def download_and_send(query, context: ContextTypes.DEFAULT_TYPE):
    url = context.user_data.get('url')
    fmt = context.user_data.get('format')
    quality = context.user_data.get('quality')
    chat_id = query.message.chat_id

    try:
        if fmt == 'mp3':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'no_warnings': True,
            }
        else:
            quality_map = {
                '1080': 'bestvideo[height<=1080]+bestaudio/best[height<=1080]',
                '720': 'bestvideo[height<=720]+bestaudio/best[height<=720]',
                '480': 'bestvideo[height<=480]+bestaudio/best[height<=480]',
                '360': 'bestvideo[height<=360]+bestaudio/best[height<=360]',
                'best': 'bestvideo+bestaudio/best',
                'medium': 'bestvideo[height<=480]+bestaudio/best',
            }
            format_str = quality_map.get(quality, 'best')
            ydl_opts = {
                'format': format_str,
                'outtmpl': f'{DOWNLOAD_DIR}/%(title)s.%(ext)s',
                'merge_output_format': 'mp4',
                'quiet': True,
                'no_warnings': True,
            }

        loop = asyncio.get_event_loop()

        def do_download():
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info

        info = await loop.run_in_executor(None, do_download)
        title = info.get('title', 'video')[:50]

        # Find downloaded file
        downloaded_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            full_path = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(full_path):
                downloaded_file = full_path
                break

        if not downloaded_file:
            raise Exception("File download nahi hua")

        file_size = os.path.getsize(downloaded_file)
        max_size = 50 * 1024 * 1024  # 50MB Telegram limit

        if file_size > max_size:
            os.remove(downloaded_file)
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ File bahut badi hai (50MB se zyada).\nChhoti quality try karo!"
            )
            return

        await context.bot.send_message(chat_id=chat_id, text=f"📤 *Uploading:* {title}...", parse_mode='Markdown')

        with open(downloaded_file, 'rb') as f:
            if fmt == 'mp3':
                await context.bot.send_audio(
                    chat_id=chat_id,
                    audio=f,
                    title=title,
                    caption=f"🎵 *{title}*\n\n_Downloaded by @{(await context.bot.get_me()).username}_",
                    parse_mode='Markdown'
                )
            else:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=f,
                    caption=f"🎬 *{title}*\n\n_Downloaded by @{(await context.bot.get_me()).username}_",
                    parse_mode='Markdown',
                    supports_streaming=True
                )

        os.remove(downloaded_file)

    except Exception as e:
        logger.error(f"Download error: {e}")
        # Clean up
        for f in os.listdir(DOWNLOAD_DIR):
            try:
                os.remove(os.path.join(DOWNLOAD_DIR, f))
            except:
                pass

        error_msg = str(e)
        if 'Private' in error_msg or 'login' in error_msg.lower():
            msg = "🔒 Yeh private content hai. Sirf public links kaam karte hain!"
        elif 'unavailable' in error_msg.lower():
            msg = "❌ Yeh video unavailable hai ya delete ho chuka hai."
        else:
            msg = f"❌ Download fail hua.\n\nError: {error_msg[:100]}"

        await context.bot.send_message(chat_id=chat_id, text=msg)

# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))

    logger.info("🤖 Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()

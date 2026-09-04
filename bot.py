import os
import asyncio
import logging
import tempfile
from pathlib import Path

import yt_dlp
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# =========================
# НАСТРОЙКИ
# =========================

BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = os.getenv("OWNER_ID")

MAX_FILE_SIZE = 49 * 1024 * 1024  # примерно 49 МБ

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# =========================
# ПРОВЕРКА ПОЛЬЗОВАТЕЛЯ
# =========================

def is_owner(update: Update) -> bool:
    if not OWNER_ID:
        return False

    user = update.effective_user

    if not user:
        return False

    return str(user.id) == OWNER_ID


# =========================
# /start
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_owner(update):
        await update.message.reply_text(
            "⛔ Этот бот находится в личном режиме."
        )
        return

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Отправь мне ссылку на YouTube-видео, "
        "и я попробую скачать его и отправить тебе.\n\n"
        "📹 Максимальный размер файла — около 49 МБ."
    )


# =========================
# /myid
# =========================

async def myid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if user:
        await update.message.reply_text(
            f"Твой Telegram ID:\n\n{user.id}"
        )


# =========================
# СКАЧИВАНИЕ
# =========================

def download_video(url: str, output_dir: str) -> Path:

    output_template = str(
        Path(output_dir) / "%(title).80s.%(ext)s"
    )

    ydl_opts = {
        # Стараемся получить MP4 с аудио.
        # Если такого варианта нет — yt-dlp выберет доступный.
        "format": (
            "best[ext=mp4][height<=480]/"
            "best[height<=480]/"
            "best"
        ),

        "outtmpl": output_template,

        "noplaylist": True,

        "quiet": True,
        "no_warnings": True,

        # Не скачиваем огромные видео.
        "max_filesize": MAX_FILE_SIZE,

        # Иногда YouTube отдаёт более удобный формат.
        "merge_output_format": "mp4",
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

    path = Path(filename)

    # После объединения расширение может стать .mp4
    if not path.exists():
        possible = list(Path(output_dir).glob("*"))

        if possible:
            path = possible[0]

    return path


# =========================
# ОБРАБОТКА ССЫЛКИ
# =========================

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not is_owner(update):
        await update.message.reply_text(
            "⛔ У тебя нет доступа к этому боту."
        )
        return

    text = update.message.text.strip()

    if not (
        "youtube.com" in text
        or "youtu.be" in text
    ):
        await update.message.reply_text(
            "❌ Это не похоже на ссылку YouTube."
        )
        return

    status = await update.message.reply_text(
        "⏳ Скачиваю видео..."
    )

    temp_dir = tempfile.mkdtemp()

    try:

        # Скачивание запускаем отдельно,
        # чтобы не блокировать Telegram-бота.
        path = await asyncio.to_thread(
            download_video,
            text,
            temp_dir
        )

        if not path.exists():
            raise Exception("Файл после скачивания не найден.")

        file_size = path.stat().st_size

        if file_size > MAX_FILE_SIZE:
            await status.edit_text(
                "❌ Видео получилось слишком большим "
                "для отправки через Telegram."
            )
            return

        await status.edit_text(
            "📤 Скачивание завершено!\n"
            "Отправляю видео..."
        )

        with open(path, "rb") as video:

            await update.message.reply_video(
                video=video,
                caption="✅ Готово!"
            )

        await status.delete()

    except Exception as e:

        logger.exception("Ошибка скачивания")

        error_text = str(e)

        if len(error_text) > 500:
            error_text = error_text[:500]

        await status.edit_text(
            "❌ Не удалось скачать видео.\n\n"
            f"Ошибка: {error_text}"
        )

    finally:

        # Удаляем временные файлы.
        try:
            for file in Path(temp_dir).glob("*"):
                file.unlink(missing_ok=True)

            Path(temp_dir).rmdir()

        except Exception:
            pass


# =========================
# ЗАПУСК
# =========================

def main():

    if not BOT_TOKEN:
        raise RuntimeError(
            "Не задан BOT_TOKEN"
        )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("myid", myid)
    )

    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message
        )
    )

    logger.info("Бот запущен!")

    application.run_polling(
        drop_pending_updates=True
    )


if __name__ == "__main__":
    main()

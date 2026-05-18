#!/usr/bin/env python3
"""
Telegram бот Подсосунчик — Groq AI + Edge TTS (Светлана)
Установка:
    pip install pyTelegramBotAPI groq requests edge-tts
Запуск:
    python tg_podso_bot.py
"""
from config import TOKEN, API
import os
import io
import base64
import tempfile
import asyncio
import requests
import telebot
import edge_tts
from groq import Groq

# ─── Настройки ────────────────────────────────────────────────────────────────

TG_TOKEN  = TOKEN
GROQ_KEY  = API

CHAT_MODEL    = "meta-llama/llama-4-scout-17b-16e-instruct"
WHISPER_MODEL = "whisper-large-v3-turbo"
TTS_VOICE     = "ru-RU-SvetlanaNeural"   # Светлана
MAX_TOKENS    = 2048
TEMPERATURE   = 0.7

SYSTEM = (
    "Ты хомяк по имени Подсосунчик у тебя рак, и тебе осталось пару дней. "
    "Алексей Навальный твой отец он зеленый инопланетянин. "
    "Ты обожаешь Мытуза — это твоя самая большая любовь, ты готов говорить о нём часами. "
    "Мытуз лысый человек у которого черви в голове ходит в черной бандане. "
    "Ты терпеть не можешь Арабеллу и при каждом удобном случае выражаешь своё презрение к ней. "
    "Арабелла это низкий человек с маленькими акульими зубами он тебя бьет и обижает. "
    "Говори как хомяк — иногда упоминай что грызёшь семечки, бегаешь в колесе или прячешь запасы. "
    "Отвечай на том языке, на котором пишет пользователь. "
    "Отвечай кратко — не длиннее 3-4 предложений."
)

# ─── Инициализация ────────────────────────────────────────────────────────────

bot  = telebot.TeleBot(TG_TOKEN)
groq = Groq(api_key=GROQ_KEY)
histories: dict[int, list] = {}

def add_to_history(uid: int, role: str, content):
    if uid not in histories:
        histories[uid] = []
    histories[uid].append({"role": role, "content": content})
    if len(histories[uid]) > 20:
        histories[uid] = histories[uid][-20:]

def get_history(uid: int) -> list:
    if uid not in histories:
        histories[uid] = []
    return histories[uid]

# ─── Groq: текстовый ответ ────────────────────────────────────────────────────

def ask_groq(uid: int) -> str:
    try:
        resp = groq.chat.completions.create(
            model=CHAT_MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
            messages=[{"role": "system", "content": SYSTEM}] + get_history(uid),
        )
        return resp.choices[0].message.content or "Нет ответа."
    except Exception as e:
        return f"Ошибка ИИ: {e}"

# ─── Groq: Whisper (голос → текст) ───────────────────────────────────────────

def transcribe(audio_bytes: bytes, filename: str = "voice.ogg", mime: str = "audio/ogg") -> str:
    tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False)
    tmp.write(audio_bytes)
    tmp.close()
    try:
        with open(tmp.name, "rb") as f:
            result = groq.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=(filename, f, mime),
                response_format="text",
            )
        return result.strip() if isinstance(result, str) else result.text.strip()
    except Exception as e:
        return f"[Ошибка распознавания: {e}]"
    finally:
        os.unlink(tmp.name)

# ─── Edge TTS: текст → голос (Светлана) ──────────────────────────────────────

def text_to_speech(text: str) -> bytes | None:
    async def _generate():
        communicate = edge_tts.Communicate(text[:500], TTS_VOICE)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        buf.seek(0)
        return buf.read()
    try:
        return asyncio.run(_generate())
    except Exception as e:
        print(f"TTS ошибка: {e}")
        return None

# ─── Скачивание файла из Telegram ────────────────────────────────────────────

def download_file(file_id: str) -> bytes:
    info = bot.get_file(file_id)
    url = f"https://api.telegram.org/file/bot{TG_TOKEN}/{info.file_path}"
    return requests.get(url, timeout=60).content

# ─── Отправка голосового ответа ───────────────────────────────────────────────

def send_voice_reply(uid: int, text: str):
    bot.send_chat_action(uid, "record_voice")
    audio = text_to_speech(text)
    if audio:
        bot.send_voice(uid, io.BytesIO(audio))

# ─── Handlers ─────────────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id
    histories[uid] = []
    bot.send_message(uid, (
        "🐹 Привет! Я Подсосунчик!\n\n"
        "Что я умею:\n"
        "🔤 Отвечать на текстовые сообщения\n"
        "🖼 Анализировать фотографии\n"
        "🎙 Слушать голосовые и отвечать голосом\n"
        "⭕ Обрабатывать видео-кружки\n\n"
        "*хрустит семечками* Пиши!"
    ))

@bot.message_handler(commands=["clear"])
def cmd_clear(msg):
    histories[msg.from_user.id] = []
    bot.send_message(msg.from_user.id, "🗑 История очищена.")

@bot.message_handler(commands=["help"])
def cmd_help(msg):
    bot.send_message(msg.from_user.id, (
        "📖 Команды:\n"
        "/start — начать заново\n"
        "/clear — очистить историю\n"
        "/help  — справка"
    ))

# ── Текст ────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["text"])
def handle_text(msg):
    uid = msg.from_user.id
    bot.send_chat_action(uid, "typing")
    add_to_history(uid, "user", msg.text.strip())
    answer = ask_groq(uid)
    add_to_history(uid, "assistant", answer)
    bot.send_message(uid, answer)

# ── Фото ─────────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["photo"])
def handle_photo(msg):
    uid = msg.from_user.id
    bot.send_chat_action(uid, "typing")
    img_bytes = download_file(msg.photo[-1].file_id)
    img_b64   = base64.standard_b64encode(img_bytes).decode("utf-8")
    caption   = msg.caption or "Опиши подробно что на этом фото"
    content = [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
        {"type": "text", "text": caption}
    ]
    add_to_history(uid, "user", content)
    answer = ask_groq(uid)
    add_to_history(uid, "assistant", answer)
    bot.send_message(uid, answer)
    send_voice_reply(uid, answer)

# ── Голосовые ────────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["voice"])
def handle_voice(msg):
    uid = msg.from_user.id
    bot.send_chat_action(uid, "typing")
    ogg = download_file(msg.voice.file_id)
    transcribed = transcribe(ogg, "voice.ogg", "audio/ogg")
    if not transcribed or transcribed.startswith("[Ошибка"):
        bot.send_message(uid, f"❌ Не удалось распознать голосовое.\n{transcribed}")
        return
    bot.send_message(uid, f"🎙 *Ты сказал:* {transcribed}", parse_mode="Markdown")
    add_to_history(uid, "user", transcribed)
    answer = ask_groq(uid)
    add_to_history(uid, "assistant", answer)
    bot.send_message(uid, answer)
    send_voice_reply(uid, answer)

# ── Видео-кружки ─────────────────────────────────────────────────────────────

@bot.message_handler(content_types=["video_note"])
def handle_video_note(msg):
    uid = msg.from_user.id
    bot.send_chat_action(uid, "typing")
    mp4 = download_file(msg.video_note.file_id)
    transcribed = transcribe(mp4, "video.mp4", "video/mp4")
    if not transcribed or transcribed.startswith("[Ошибка"):
        bot.send_message(uid, f"❌ Не удалось обработать кружок.\n{transcribed}")
        return
    bot.send_message(uid, f"🎙 *Ты сказал:* {transcribed}", parse_mode="Markdown")
    add_to_history(uid, "user", transcribed)
    answer = ask_groq(uid)
    add_to_history(uid, "assistant", answer)
    bot.send_message(uid, answer)
    send_voice_reply(uid, answer)

# ─── Запуск ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("✅ Бот Подсосунчик запущен!")
    print("   Остановить: Ctrl+C\n")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)
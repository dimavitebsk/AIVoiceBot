import os
import aiohttp
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import FSInputFile
from aiogram.filters import CommandStart
from pydantic_settings import BaseSettings
from openai import AsyncOpenAI

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Класс конфигурации с PydanticSettings
class Settings(BaseSettings):
    BOT_TOKEN: str
    OPENAI_API_KEY: str

    class Config:
        env_file = ".env"

settings = Settings()

# Инициализация бота и OpenAI клиента
bot = Bot(token=settings.BOT_TOKEN)
dp = Dispatcher()
openai_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)

@dp.message(CommandStart())
async def start_command(message: types.Message):
    await message.answer("Привет! Отправь мне голосовое сообщение, и я преобразую его в текст, отвечу и озвучу ответ.")

@dp.message(lambda message: message.voice)
async def handle_voice_message(message: types.Message):
    voice = message.voice
    file_info = await bot.get_file(voice.file_id)
    file_path = file_info.file_path
    file_url = f"https://api.telegram.org/file/bot{settings.BOT_TOKEN}/{file_path}"

    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            audio_data = await resp.read()

    # Отправляем аудио в Whisper API
    transcription = await openai_client.audio.transcriptions.create(
        model="whisper-1",
        file=("voice.ogg", audio_data, "audio/ogg")
    )
    text = transcription.text
    await message.answer(f"Распознанный текст: {text}")

     # Запрос в OpenAI Assistant API
    thread = await openai_client.beta.threads.create()
    message_response = await openai_client.beta.threads.messages.create(
        thread_id=thread.id,
        role="user",
        content=text
    )
    run = await openai_client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id=settings.OPENAI_ASSISTANT_ID
    )
    
    while run.status not in ["completed", "failed"]:
        run = await openai_client.beta.threads.runs.retrieve(
            thread_id=thread.id,
            run_id=run.id
        )
        await asyncio.sleep(0.5) 
    
    if run.status == "completed":
        messages = await openai_client.beta.threads.messages.list(thread_id=thread.id)
        reply_text = messages.data[0].content[0].text.value
    else:
        reply_text = "Произошла ошибка при получении ответа."
    
    await message.answer(reply_text)

    # Озвучка ответа через TTS API
    tts_audio = await openai_client.audio.speech.create(
        model="tts-1",
        voice="alloy",
        input=reply_text
    )
    audio_file_path = "response.mp3"
    with open(audio_file_path, "wb") as audio_file:
        audio_file.write(tts_audio.content)

    await message.answer_voice(FSInputFile(audio_file_path))
    os.remove(audio_file_path)

if __name__ == "__main__":
    import asyncio

    async def main():
        await dp.start_polling(bot)

    asyncio.run(main())
import asyncio
import os
import random
import hashlib
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, BufferedInputFile
from db.database import init_db, async_session
from db.models import Post
from services.generator import generate_post, generate_image_url, download_image, sanitize_text

load_dotenv()

async def main():
    await init_db()
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    admin_id = int(os.getenv("ADMIN_ID"))

    topics = [
        "Горизонт событий: что происходит с материей на границе чёрной дыры",
        "Излучение Хокинга: как чёрные дыры испаряются",
        "Стрела времени: почему время идёт только вперёд",
        "Квантовая запутанность: связь быстрее света",
        "Тёмная материя: невидимый каркас мироздания",
        "Парадокс Ферми: почему мы одни во Вселенной",
        "Телепортация: как это работает в реальности",
        "Смерть Вселенной: как всё закончится",
        "Мультивселенная: сколько реальностей существует одновременно",
        "Замедление времени: как гравитация растягивает секунды",
    ]
    selected = random.sample(topics, 3)

    async with async_session() as session:
        for i, topic in enumerate(selected, start=1):
            post_data = await generate_post(topic)
            post_hash = hashlib.md5(post_data["body"].encode("utf-8")).hexdigest()

            new_post = Post(
                title=post_data["title"],
                body=post_data["body"],
                image_url=None,
                status="draft",
                hash=post_hash
            )
            session.add(new_post)
            await session.commit()
            await session.refresh(new_post)
            post_id = new_post.id

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish_{post_id}")],
                [InlineKeyboardButton(text="💾 Сохранить", callback_data=f"save_{post_id}")],
                [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{post_id}")]
            ])

            safe_title = sanitize_text(post_data["title"])
            safe_body = sanitize_text(post_data["body"])
            text_message = f"📌 <b>Пост {i} из 3</b>\n\n<b>{safe_title}</b>\n\n{safe_body}"

            try:
                # Скачиваем картинку сами
                image_url = generate_image_url(post_data["title"])
                print(f"Скачиваем картинку для поста {i}...")
                image_bytes = await download_image(image_url)

                if image_bytes:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=BufferedInputFile(image_bytes, filename=f"post_{post_id}.jpg")
                    )
                    print(f"Картинка поста {i} отправлена.")
                else:
                    print(f"Не удалось скачать картинку для поста {i}, отправляем без неё.")

                await bot.send_message(
                    chat_id=admin_id,
                    text=text_message,
                    parse_mode="HTML",
                    reply_markup=kb
                )
                print(f"Пост {i} (ID {post_id}) отправлен админу.")
            except Exception as e:
                print(f"Ошибка отправки поста {i}: {e}")

    await bot.session.close()
    print("Генерация завершена.")

if __name__ == "__main__":
    asyncio.run(main())

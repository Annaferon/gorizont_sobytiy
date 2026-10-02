import asyncio
import os
import random
import hashlib
from dotenv import load_dotenv
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from db.database import init_db, async_session
from db.models import Post
from services.generator import generate_post

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
        "Смерть Вселенной: как всё закончится"
    ]
    selected = random.sample(topics, 3)

    async with async_session() as session:
        for topic in selected:
            post_data = await generate_post(topic)
            post_hash = hashlib.md5(post_data["body"].encode()).hexdigest()
            
            new_post = Post(
                title=post_data["title"],
                body=post_data["body"],
                image_url=post_data["image_url"],
                status="draft",
                hash=post_hash
            )
            session.add(new_post)
            await session.commit()
            await session.refresh(new_post)
            post_id = new_post.id

            kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Опубликовать", callback_data=f"publish_{post_id}"),
                 InlineKeyboardButton(text="💾 Сохранить", callback_data=f"save_{post_id}"),
                 InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_{post_id}")]
            ])
            
            try:
                await bot.send_photo(
                    chat_id=admin_id,
                    photo=post_data["image_url"],
                    caption=f"<b>{post_data['title']}</b>\n\n{post_data['body'][:500]}...",
                    parse_mode="HTML",
                    reply_markup=kb
                )
                print(f"Пост на тему '{topic}' отправлен админу.")
            except Exception as e:
                print(f"Ошибка отправки поста: {e}")

    await bot.session.close()
    print("Генерация завершена.")

if __name__ == "__main__":
    asyncio.run(main())

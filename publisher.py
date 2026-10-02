import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot
from sqlalchemy import select
from db.database import async_session
from db.models import Post, Queue

load_dotenv()

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    channel_id = os.getenv("CHANNEL_ID")

    async with async_session() as session:
        now = datetime.utcnow()
        result = await session.execute(
            select(Queue).where(Queue.status == "pending", Queue.scheduled_at <= now)
        )
        items = result.scalars().all()
        
        for item in items:
            post = await session.get(Post, item.post_id)
            if post and post.status == "saved":
                try:
                    await bot.send_photo(
                        chat_id=channel_id,
                        photo=post.image_url,
                        caption=f"<b>{post.title}</b>\n\n{post.body}",
                        parse_mode="HTML"
                    )
                    post.status = "published"
                    post.published_at = datetime.utcnow()
                    item.status = "sent"
                    await session.commit()
                    print(f"Пост '{post.title}' успешно опубликован в канал.")
                except Exception as e:
                    print(f"Ошибка публикации поста {post.id}: {e}")
                    item.status = "failed"
                    await session.commit()

    await bot.session.close()
    print("Проверка очереди завершена.")

if __name__ == "__main__":
    asyncio.run(main())

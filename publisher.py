import asyncio
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from aiogram import Bot
from sqlalchemy import select
from db.database import async_session
from db.models import Post, Queue, BotState
from services.generator import generate_image_url, sanitize_text

load_dotenv()

async def get_state(session, key: str):
    result = await session.execute(select(BotState).where(BotState.key == key))
    state = result.scalar_one_or_none()
    return state.value if state else None

async def set_state(session, key: str, value: str):
    result = await session.execute(select(BotState).where(BotState.key == key))
    state = result.scalar_one_or_none()
    if state:
        state.value = value
    else:
        session.add(BotState(key=key, value=value))
    await session.commit()

async def process_callbacks(bot: Bot):
    admin_id = int(os.getenv("ADMIN_ID"))
    last_update_id = 0

    async with async_session() as session:
        raw = await get_state(session, "last_update_id")
        if raw:
            last_update_id = int(raw)

    updates = await bot.get_updates(offset=last_update_id + 1, timeout=0)
    if not updates:
        return

    async with async_session() as session:
        for update in updates:
            last_update_id = update.update_id
            cb = update.callback_query
            if not cb:
                continue
            if cb.from_user.id != admin_id:
                await cb.answer("Это не для тебя 🙂", show_alert=False)
                continue

            data = cb.data or ""
            if "_" not in data:
                await cb.answer()
                continue

            action, post_id_str = data.split("_", 1)
            try:
                post_id = int(post_id_str)
            except ValueError:
                await cb.answer("Некорректные данные", show_alert=True)
                continue

            post = await session.get(Post, post_id)
            if not post:
                await cb.answer("Пост не найден", show_alert=True)
                try:
                    await cb.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass
                continue

            if action == "publish":
                post.status = "saved"
                session.add(Queue(
                    post_id=post_id,
                    scheduled_at=datetime.utcnow() + timedelta(hours=1)
                ))
                await session.commit()
                await cb.answer("✅ Пост в очереди. Опубликуется через 1 час.")
                try:
                    await cb.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass

            elif action == "save":
                post.status = "saved"
                session.add(Queue(
                    post_id=post_id,
                    scheduled_at=datetime.utcnow() + timedelta(days=1)
                ))
                await session.commit()
                await cb.answer("💾 Пост сохранён. Выйдет через 1 день.")
                try:
                    await cb.message.edit_reply_markup(reply_markup=None)
                except Exception:
                    pass

            elif action == "delete":
                await session.delete(post)
                await session.commit()
                await cb.answer("🗑 Пост удалён.")
                try:
                    await cb.message.delete()
                except Exception:
                    pass
                try:
                    # Удалить и картинку — она шла отдельным сообщением выше
                    await bot.delete_message(chat_id=admin_id, message_id=cb.message.message_id - 1)
                except Exception:
                    pass
            else:
                await cb.answer("Неизвестное действие", show_alert=True)

        await set_state(session, "last_update_id", str(last_update_id))

async def publish_queue(bot: Bot):
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
                    # Картинка генерируется заново из заголовка
                    image_url = generate_image_url(post.title)

                    await bot.send_photo(chat_id=channel_id, photo=image_url)

                    safe_title = sanitize_text(post.title)
                    safe_body = sanitize_text(post.body)
                    text_message = f"<b>{safe_title}</b>\n\n{safe_body}"

                    await bot.send_message(
                        chat_id=channel_id,
                        text=text_message,
                        parse_mode="HTML"
                    )
                    post.status = "published"
                    post.published_at = datetime.utcnow()
                    item.status = "sent"
                    await session.commit()
                    print(f"Пост '{post.title}' опубликован.")
                except Exception as e:
                    print(f"Ошибка публикации {post.id}: {e}")
                    item.status = "failed"
                    await session.commit()

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    await process_callbacks(bot)
    await publish_queue(bot)
    await bot.session.close()
    print("Цикл завершён.")

if __name__ == "__main__":
    asyncio.run(main())

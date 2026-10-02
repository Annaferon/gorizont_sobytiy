import os
import urllib.parse
from openai import OpenAI

def _get_client():
    """Создаём клиент OpenAI, но указываем base_url OpenRouter"""
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

def _build_prompt(topic: str) -> str:
    return f"""Ты — автор научно-популярного Telegram-канала «Горизонт событий» о космосе, времени и физике в духе Стивена Хокинга.
Напиши пост на тему: {topic}
Требования:
1. Заголовок — цепляющий, интригующий, 5–9 слов. Без банальностей вроде «интересные факты о...».
2. Текст — 1800–2300 знаков.
3. Стиль: увлекательно, но научно корректно. Как будто объясняешь другу, который умный, но не физик.
4. Обязательно: 3–5 эмодзи по смыслу (не в каждом предложении).
5. Разбей на 3–4 коротких абзаца — легко читать с телефона.
6. В конце — 3 хештега: #космос #время #физика (по теме).
7. Не выдумывай факты. Если сомневаешься — используй известные теории.

Формат ответа строго:
ЗАГОЛОВОК: <заголовок>
ТЕКСТ:
<текст поста>
"""

def _split_response(text: str) -> tuple[str, str]:
    """Разделяем ответ модели на заголовок и тело"""
    text = text.strip()
    title = ""
    body = text

    # Ищем "ЗАГОЛОВОК:" в начале
    if text.upper().startswith("ЗАГОЛОВОК"):
        # Отрезаем заголовок до "ТЕКСТ:" или до первого переноса строки
        after_title = text.split(":", 1)[1] if ":" in text else text
        if "ТЕКСТ" in after_title.upper():
            title_part, body_part = after_title.split("ТЕКСТ", 1)
            title = title_part.strip()
            body = body_part.split(":", 1)[1].strip() if ":" in body_part else body_part.strip()
        else:
            lines = after_title.strip().split("\n", 1)
            title = lines[0].strip()
            body = lines[1].strip() if len(lines) > 1 else ""
    else:
        # Фолбэк: первая строка = заголовок
        lines = text.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

    # Убираем звёздочки и лишние кавычки
    title = title.strip('*"«» ').strip()
    return title, body

async def generate_post(topic: str) -> dict:
    client = _get_client()
    model = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "user", "content": _build_prompt(topic)}
        ],
        temperature=0.8,
        max_tokens=1500,
    )

    text = response.choices[0].message.content or ""
    title, body = _split_response(text)

    if not title:
        title = f"Загадка Вселенной: {topic[:60]}"

    # Промпт для картинки через Pollinations
    prompt_img = (
        f"Cosmic {topic}, deep space, nebula, stars, black hole, "
        f"cinematic, dark atmosphere, 4k, awe-inspiring"
    )
    image_url = (
        f"https://image.pollinations.ai/prompt/"
        f"{urllib.parse.quote(prompt_img)}?width=1024&height=1024&nologo=true"
    )

    return {"title": title, "body": body, "image_url": image_url}

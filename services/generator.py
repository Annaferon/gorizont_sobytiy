import os
import re
import html
import asyncio
import urllib.parse
import hashlib
import random as rnd
import aiohttp
from openai import OpenAI

STYLES = [
    "realistic NASA photography, Hubble telescope style",
    "digital art, cinematic sci-fi",
    "oil painting, impressionist style",
    "surreal dreamlike cosmic art",
    "watercolor nebula painting",
    "vintage space poster, art deco",
    "cyberpunk neon cosmic",
    "minimalist dark space illustration",
    "glowing plasma energy art",
    "detailed ink drawing of cosmos",
    "hyperrealistic 3d render, octane",
    "matte painting, epic scale",
]

SUBJECTS = [
    "black hole accretion disk",
    "spiral galaxy with bright core",
    "supernova explosion",
    "colorful cosmic nebula",
    "pulsar with radiation beams",
    "wormhole in deep space",
    "distant exoplanet with rings",
    "astronaut floating in space",
    "comet with long tail",
    "cosmic web of interconnected galaxies",
    "quasar with jet stream",
    "dark matter visualization",
    "time dilation visualization",
    "quantum entanglement concept",
]

def generate_image_url(seed_text: str) -> str:
    seed = int(hashlib.md5(seed_text.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = rnd.Random(seed)
    style = rng.choice(STYLES)
    subject = rng.choice(SUBJECTS)
    prompt = f"{subject}, {style}, deep space, stars, cinematic, 4k, awe-inspiring"
    quoted = urllib.parse.quote(prompt)
    return (
        f"https://image.pollinations.ai/prompt/{quoted}"
        f"?width=1024&height=1024&nologo=true&seed={seed}"
    )

async def download_image(url: str, retries: int = 4, timeout: int = 60) -> bytes | None:
    """Скачивает картинку с ретраями. Pollinations иногда отвечает медленно."""
    for attempt in range(retries):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                    allow_redirects=True,
                ) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        if data and len(data) > 1000:
                            return data
        except Exception as e:
            print(f"Попытка {attempt + 1} скачать картинку не удалась: {e}")
        await asyncio.sleep(3)
    return None

def sanitize_text(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", text)
    return html.escape(text)

def _get_client():
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
8. НЕ используй HTML-теги (никаких <b>, <i>, <headline> и т.п.). Только чистый текст.

Формат ответа строго:
ЗАГОЛОВОК: <заголовок>
ТЕКСТ:
<текст поста>
"""

def _split_response(text: str) -> tuple[str, str]:
    text = text.strip()
    title = ""
    body = text

    if text.upper().startswith("ЗАГОЛОВОК"):
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
        lines = text.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""

    title = title.strip('*"«»<>').strip()
    return title, body

async def generate_post(topic: str) -> dict:
    client = _get_client()
    model = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": _build_prompt(topic)}],
        temperature=0.9,
        max_tokens=1500,
    )

    text = response.choices[0].message.content or ""
    title, body = _split_response(text)

    if not title:
        title = f"Загадка Вселенной: {topic[:60]}"

    return {"title": title, "body": body}

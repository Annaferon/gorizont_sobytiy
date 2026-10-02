import os
import sys
import json
import time
import random
import requests
import psycopg2
from urllib.parse import quote
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.environ["DATABASE_URL"]
OPENROUTER_KEY = os.environ["OPENROUTER_API_KEY"]
TG_BOT_TOKEN = os.environ["BOT_TOKEN"]
TG_ADMIN_ID = int(os.environ["ADMIN_ID"])
_raw_channel = os.environ["CHANNEL_ID"]
TG_CHANNEL_ID = _raw_channel if _raw_channel.startswith("@") else int(_raw_channel)
LLM_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3.5-lightning:free")

CANDIDATES_PER_DAY = 3
TG_API = f"https://api.telegram.org/bot{TG_BOT_TOKEN}"

TOPICS = [
    "Горизонт событий чёрной дыры: где заканчивается привычная физика",
    "Излучение Хокинга: как чёрные дыры испаряются",
    "Стрела времени: почему время идёт только вперёд",
    "Парадокс дедушки: можно ли убить своего предка",
    "Квантовая запутанность: связь быстрее света",
    "Кот Шрёдингера: жив или мёртв",
    "Тёмная материя: невидимый каркас мироздания",
    "Тёмная энергия: сила, разрывающая Вселенную",
    "Большой взрыв: что было до него",
    "Мультивселенная: сколько реальностей существует",
    "Парадокс Ферми: почему мы одни во Вселенной",
    "Телепортация: как это работает в реальности",
    "Спагеттификация: что будет при падении в чёрную дыру",
    "Смерть Вселенной: как всё закончится",
    "Замедление времени: как гравитация растягивает секунды",
    "Принцип неопределённости Гейзенберга",
    "Космический горизонт: что скрыто за пределами видимого",
    "Стивен Хокинг: человек, победивший время",
    "Эйнштейн и его ошибки: где гений промахнулся",
    "Размер Вселенной: где заканчивается космос",
]


def db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')


def tg(method, **kwargs):
    r = requests.post(f"{TG_API}/{method}", json=kwargs, timeout=30)
    return r.json()


def send_tg(chat_id, text, parse_mode="HTML", reply_markup=None):
    chunks = []
    while text:
        if len(text) <= 4000:
            chunks.append(text)
            break
        split = text.rfind("\n\n", 0, 4000) or 4000
        chunks.append(text[:split])
        text = text[split:].lstrip()
    out = []
    for i, c in enumerate(chunks):
        payload = {"chat_id": chat_id, "text": c, "parse_mode": parse_mode,
                   "disable_web_page_preview": True}
        if reply_markup and i == len(chunks) - 1:
            payload["reply_markup"] = reply_markup
        out.append(tg("sendMessage", **payload))
        time.sleep(0.4)
    return out


def pollinations_url(image_prompt):
    return (
        f"https://image.pollinations.ai/prompt/"
        f"{quote(image_prompt)}?width=1024&height=1024&nologo=true&model=flux"
    )


def send_photo_then_text(chat_id, image_prompt, full_text, reply_markup=None):
    url = pollinations_url(image_prompt or "deep space cinematic cosmic scene, no text")
    tg("sendPhoto", chat_id=chat_id, photo=url)
    time.sleep(0.5)
    send_tg(chat_id, full_text, reply_markup=reply_markup)


def call_llm(prompt):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                 "Content-Type": "application/json"},
        json={"model": LLM_MODEL,
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.95, "max_tokens": 1800},
        timeout=240,
    )
    data = r.json()
    if "choices" not in data:
        raise Exception(f"LLM error: {data}")
    return data["choices"][0]["message"]["content"].strip()


def parse_json(text):
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise


WRITER_PROMPT = """Ты — автор научно-популярного Telegram-канала «Горизонт событий» о космосе, времени и физике в духе Стивена Хокинга.

ЗАДАЧА: напиши один пост на заданную тему.

ТЕМА: {topic}

ТРЕБОВАНИЯ К ТЕКСТУ:
- Язык строго русский. Только кириллица.
- Увлекательно, но научно корректно. Как будто объясняешь другу, который умный, но не физик.
- Длина тела поста 1800–2300 знаков (критично).
- Разбей на 3–4 коротких абзаца, разделённых пустой строкой.
- Обязательно 3–5 эмодзи по смыслу (не в каждом предложении).
- В конце текста — 3 хештега: #космос #время #физика (или более подходящие по теме).
- Не выдумывай факты. Если сомневаешься — используй известные теории.
- Не используй HTML-теги и маркеры типа "ЗАГОЛОВОК:".

ЗАГОЛОВОК: 5–9 слов, цепляющий, интригующий. Без банальностей вроде «интересные факты о...».

КАРТИНКА (image_prompt): промпт на английском, 10–18 слов. Опиши конкретную космическую сцену. Обязательно включи: deep space, cinematic, 4k, ultra detailed, no text, no people.

ОТВЕТЬ СТРОГО JSON БЕЗ КОММЕНТАРИЕВ:
{{"title": "...", "body": "...", "image_prompt": "..."}}
"""


def task_write():
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""SELECT COUNT(*) AS c FROM ai_drafts
                   WHERE created_at > NOW() - INTERVAL '24 hours'
                   AND status='pending'""")
    if cur.fetchone()["c"] > 0:
        print("Свежие черновики уже есть — пропуск")
        cur.close()
        conn.close()
        return

    topic = random.choice(TOPICS)
    created = []

    for i in range(CANDIDATES_PER_DAY):
        try:
            raw = call_llm(WRITER_PROMPT.format(topic=topic))
            p = parse_json(raw)
            title = p.get("title", "").strip()
            body = p.get("body", "").strip()
            img = p.get("image_prompt", "").strip()
            if not (title and body and img):
                print(f"Пост {i+1}: неполные поля, пропуск")
                continue
            cur.execute("""INSERT INTO ai_drafts (topic, title, content, image_prompt, status)
                           VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
                        (topic, title, body, img))
            did = cur.fetchone()["id"]
            conn.commit()
            created.append((did, title, body, img))
        except Exception as e:
            print(f"Error {i+1}: {e}")

    cur.close()
    conn.close()

    if not created:
        send_tg(TG_ADMIN_ID, "⚠️ Writer ничего не сгенерил. Проверь лог.")
        return

    for idx, (did, title, body, img) in enumerate(created, 1):
        full_text = f"<b>Вариант {idx} из {len(created)}</b>\n\n<b>{title}</b>\n\n{body}"
        kb = {"inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"ok:{did}"},
            {"text": "📁 Сохранить", "callback_data": f"save:{did}"},
            {"text": "❌ Удалить", "callback_data": f"no:{did}"},
        ]]}
        try:
            send_photo_then_text(TG_ADMIN_ID, img, full_text, reply_markup=kb)
        except Exception as e:
            print(f"Send error {idx}: {e}")

    send_tg(TG_ADMIN_ID, f"📌 Тема дня: <b>{topic}</b>.")


def task_publish():
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("SELECT value FROM bot_state WHERE key='publishing_enabled'")
    row = cur.fetchone()
    enabled = row and row["value"] == "true"
    if not enabled:
        print("Публикация выключена")
        cur.close()
        conn.close()
        return

    cur.execute("""SELECT 1 FROM publish_queue
                   WHERE published_at > NOW() - INTERVAL '20 hours' LIMIT 1""")
    if cur.fetchone():
        print("Недавно уже был пост")
        cur.close()
        conn.close()
        return

    cur.execute("""SELECT * FROM publish_queue WHERE published_at IS NULL
                   ORDER BY position NULLS LAST, id LIMIT 1""")
    d = cur.fetchone()
    if not d:
        print("Очередь пуста")
        cur.close()
        conn.close()
        return

    img_prompt = d["image_prompt"] or "deep space cinematic cosmic scene, no text"
    full_text = f"<b>{d['title']}</b>\n\n{d['content']}"
    try:
        send_photo_then_text(TG_CHANNEL_ID, img_prompt, full_text)
    except Exception as e:
        print(f"Publish error: {e}")
        cur.close()
        conn.close()
        return

    cur.execute("UPDATE publish_queue SET published_at=NOW() WHERE id=%s", (d["id"],))
    conn.commit()
    print(f"Опубликован #{d['id']}: {d['title']}")
    cur.close()
    conn.close()


def task_stats():
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT COUNT(*) AS c FROM publish_queue WHERE published_at IS NULL")
    queue = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM ai_drafts WHERE status='pending'")
    pending = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) AS c FROM ai_drafts WHERE status='saved'")
    saved = cur.fetchone()["c"]
    cur.execute("SELECT value FROM bot_state WHERE key='publishing_enabled'")
    row = cur.fetchone()
    enabled = row["value"] if row else "true"
    msg = (f"📊 <b>Статус «Горизонт событий»</b>\n\n"
           f"В очереди на публикацию: {queue}\n"
           f"Черновиков на проверке: {pending}\n"
           f"Сохранённых в банке: {saved}\n"
           f"Публикация: <b>{enabled}</b>")
    send_tg(TG_ADMIN_ID, msg)
    cur.close()
    conn.close()


def task_callbacks():
    conn = db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT value FROM bot_state WHERE key='tg_offset'")
    row = cur.fetchone()
    offset = int(row["value"]) if row else 0

    r = requests.get(f"{TG_API}/getUpdates",
                     params={"offset": offset, "timeout": 0}, timeout=30).json()
    if not r.get("ok"):
        print(f"getUpdates error: {r}")
        cur.close()
        conn.close()
        return

    updates = r.get("result", [])
    max_id = offset - 1
    processed = 0

    for u in updates:
        max_id = max(max_id, u["update_id"])
        cb = u.get("callback_query")
        if not cb:
            continue
        data = cb.get("data", "")
        cb_id = cb["id"]
        msg_id = cb["message"]["message_id"]

        try:
            action, did = data.split(":", 1)
            did = int(did)
        except Exception:
            continue

        cur.execute("SELECT * FROM ai_drafts WHERE id=%s", (did,))
        d = cur.fetchone()
        if not d:
            tg("answerCallbackQuery", callback_query_id=cb_id, text="Черновик не найден")
            continue

        if action == "ok":
            cur.execute("""INSERT INTO publish_queue (title, content, image_prompt, source, position)
                           VALUES (%s, %s, %s, 'ai',
                           (SELECT COALESCE(MAX(position), 0) + 1 FROM publish_queue))""",
                        (d["title"], d["content"], d["image_prompt"]))
            cur.execute("UPDATE ai_drafts SET status='approved' WHERE id=%s", (did,))
            new_text = f"<b>{d['title']}</b>\n\n{d['content']}\n\n✅ <i>В очереди на публикацию</i>"
            tg("answerCallbackQuery", callback_query_id=cb_id, text="✅ В очередь")
        elif action == "save":
            cur.execute("UPDATE ai_drafts SET status='saved' WHERE id=%s", (did,))
            new_text = f"<b>{d['title']}</b>\n\n{d['content']}\n\n📁 <i>Сохранено в банк</i>"
            tg("answerCallbackQuery", callback_query_id=cb_id, text="📁 Сохранено")
        elif action == "no":
            cur.execute("UPDATE ai_drafts SET status='rejected', rejected_at=NOW() WHERE id=%s", (did,))
            new_text = f"<b>{d['title']}</b>\n\n{d['content']}\n\n❌ <i>Удалено</i>"
            tg("answerCallbackQuery", callback_query_id=cb_id, text="❌ Удалено")
        else:
            continue

        conn.commit()
        try:
            tg("editMessageText", chat_id=cb["message"]["chat"]["id"],
               message_id=msg_id, text=new_text, parse_mode="HTML",
               disable_web_page_preview=True)
        except Exception as e:
            print(f"edit error: {e}")
        processed += 1

    cur.execute("""INSERT INTO bot_state (key, value, updated_at) VALUES ('tg_offset', %s, NOW())
                   ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()""",
                (str(max_id + 1),))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Обработано: {processed}, offset={max_id+1}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py [write|publish|stats|callbacks]")
        sys.exit(1)
    t = sys.argv[1]
    if t == "write":
        task_write()
    elif t == "publish":
        task_publish()
    elif t == "stats":
        task_stats()
    elif t == "callbacks":
        task_callbacks()
    else:
        print(f"Unknown: {t}")

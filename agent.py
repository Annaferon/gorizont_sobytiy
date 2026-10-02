import os
import sys
import json
import time
import html
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

STYLE_MODIFIERS = [
    "with vibrant purple and blue nebula",
    "with dramatic orange and gold lighting",
    "with distant stars and galaxies",
    "with a glowing accretion disk",
    "with subtle teal and green tones",
    "with harsh red light and shadows",
    "with a soft cosmic glow",
    "with swirling galactic dust",
]

COSMIC_PREFIX = "cosmic space scene, deep space, astronomy, nebula, stars, cinematic 4k, ultra detailed"

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
    data = r.json()
    if not data.get("ok"):
        print(f"[TG ERROR] {method}: {data}")
    return data


def esc(text):
    return html.escape(text or "", quote=False)


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
        res = tg("sendMessage", **payload)
        out.append(res)
        time.sleep(0.4)
    return out


def pollinations_url(image_prompt, seed):
    base = f"https://image.pollinations.ai/prompt/{quote(image_prompt)}"
    params = f"?width=1024&height=1024&nologo=true&model=flux&seed={seed}"
    return base + params


def send_photo_then_text(chat_id, image_prompt, title, body, reply_markup=None):
    modifier = random.choice(STYLE_MODIFIERS)
    seed = random.randint(1, 2_147_483_647)
    enhanced_prompt = f"{COSMIC_PREFIX}, {image_prompt}, {modifier}"
    url = pollinations_url(enhanced_prompt, seed)

    print(f"[IMG] seed={seed}, prompt={enhanced_prompt[:120]}")
    photo_res = tg("sendPhoto", chat_id=chat_id, photo=url)
    if not photo_res.get("ok"):
        # Фолбэк: пробуем без модели flux
        url2 = url.replace("&model=flux", "")
        print(f"[IMG] retry without flux: {url2[:120]}")
        tg("sendPhoto", chat_id=chat_id, photo=url2)
    time.sleep(0.5)

    safe_title = esc(title)
    safe_body = esc(body)
    text = f"<b>{safe_title}</b>\n\n{safe_body}"
    return send_tg(chat_id, text, reply_markup=reply_markup)


def call_llm(prompt):
    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={"Authorization": f"Bearer {OPENROUTER_KEY}",
                 "Content-Type": "application/json"},
        json={"model": LLM_MODEL,
              "messages": [{"role": "user", "content": prompt}],
              "temperature": 0.95, "max_tokens": 2200},
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

ЗАДАЧА: напиши ОДИН пост на заданную тему. Это должен быть полноценный большой текст.

ТЕМА: {topic}

ЖЁСТКИЕ ТРЕБОВАНИЯ:
- Язык: строго русский. Только кириллица (латиница — только в общепринятых терминах).
- Длина тела поста: РОВНО 1800–2300 знаков. Это критично. Короткий ответ не принимается.
- Разбей текст на 3–4 абзаца, разделённых пустой строкой.
- Обязательно 3–5 эмодзи по смыслу.
- В САМОМ КОНЦЕ текста добавь 3 хештега: #космос #время #физика (или более подходящие).
- Не используй HTML-теги, markdown-звёздочки и служебные метки.
- НЕ пиши слов «ЗАГОЛОВОК:» или «ТЕКСТ:» внутри body.

ЗАГОЛОВОК: 5–9 слов, цепляющий, интригующий. Не банальности.

КАРТИНКА (image_prompt): строго английский, 12–18 слов. Тема — КОСМОС: чёрные дыры, галактики, туманности, планеты, звёзды, космические явления. БЕЗ тигров, людей, животных, лесов, машин. Добавь: deep space, cinematic, 4k, ultra detailed, no text.

ОТВЕТЬ СТРОГО JSON БЕЗ КОММЕНТАРИЕВ:
{{"title": "...", "body": "...", "image_prompt": "..."}}
"""


def validate(title, body, img):
    """Базовая валидация контента."""
    if not title or not body or not img:
        return False
    if len(body.strip()) < 500:
        return False
    if len(title.strip()) < 8:
        return False
    if title.strip() in ("...", "…"):
        return False
    return True


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
    print(f"[TOPIC] {topic}")
    created = []

    for i in range(CANDIDATES_PER_DAY):
        try:
            raw = call_llm(WRITER_PROMPT.format(topic=topic))
            p = parse_json(raw)
            title = (p.get("title") or "").strip()
            body = (p.get("body") or "").strip()
            img = (p.get("image_prompt") or "").strip()

            if not validate(title, body, img):
                print(f"[SKIP] {i+1}: title={len(title)} body={len(body)} img={len(img)}")
                print(f"       raw={raw[:200]}")
                continue

            cur.execute("""INSERT INTO ai_drafts (topic, title, content, image_prompt, status)
                           VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
                        (topic, title, body, img))
            did = cur.fetchone()["id"]
            conn.commit()
            created.append((did, title, body, img))
            print(f"[OK] draft #{did}: {title} ({len(body)} znakov)")
        except Exception as e:
            print(f"[ERROR] {i+1}: {e}")

    cur.close()
    conn.close()

    if not created:
        send_tg(TG_ADMIN_ID, "⚠️ Writer ничего не сгенерил. Проверь лог.")
        return

    for idx, (did, title, body, img) in enumerate(created, 1):
        full_text = f"<b>Вариант {idx} из {len(created)}</b>\n\n<b>{esc(title)}</b>\n\n{esc(body)}"
        kb = {"inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"ok:{did}"},
            {"text": "📁 Сохранить", "callback_data": f"save:{did}"},
            {"text": "❌ Удалить", "callback_data": f"no:{did}"},
        ]]}
        try:
            send_photo_then_text(TG_ADMIN_ID, img, title, body, reply_markup=kb)
            print(f"[SENT] variant {idx} (draft #{did})")
        except Exception as e:
            print(f"[SEND ERROR] {idx}: {e}")

    send_tg(TG_ADMIN_ID, f"📌 Тема дня: <b>{esc(topic)}</b>.")


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

    img_prompt = d["image_prompt"] or "cosmic deep space nebula stars"
    try:
        send_photo_then_text(TG_CHANNEL_ID, img_prompt, d["title"], d["content"])
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
            new_text = f"<b>{esc(d['title'])}</b>\n\n{esc(d['content'])}\n\n✅ <i>В очереди на публикацию</i>"
            tg("answerCallbackQuery", callback_query_id=cb_id, text="✅ В очередь")
        elif action == "save":
            cur.execute("UPDATE ai_drafts SET status='saved' WHERE id=%s", (did,))
            new_text = f"<b>{esc(d['title'])}</b>\n\n{esc(d['content'])}\n\n📁 <i>Сохранено в банк</i>"
            tg("answerCallbackQuery", callback_query_id=cb_id, text="📁 Сохранено")
        elif action == "no":
            cur.execute("UPDATE ai_drafts SET status='rejected', rejected_at=NOW() WHERE id=%s", (did,))
            new_text = f"<b>{esc(d['title'])}</b>\n\n{esc(d['content'])}\n\n❌ <i>Удалено</i>"
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

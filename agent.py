import os
import sys
import json
import time
import html
import random
import re
import unicodedata
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
LLM_MODEL = os.environ.get("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "qwen/qwen-2.5-72b-instruct:free")

CANDIDATES_PER_DAY = 5
MAX_RETRIES = 3
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
    "Время и гравитация: почему у поверхности Земли время идёт медленнее",
    "Путешествия во времени: что говорит физика",
    "Гравитационные волны: как звучит пространство-время",
    "Антиматерия: где она во Вселенной",
    "Реликтовое излучение: эхо Большого взрыва",
    "Гравитационное линзирование: космические лупы",
    "Предел Чандрасекара: почему звёзды умирают",
    "Квазары: самые яркие объекты Вселенной",
    "Тёмные века Вселенной: что было после Большого взрыва",
    "Эффект Унру: как ускорение рождает частицы",
]


AUTO_FIXES = [
    (r"\bСЗИ\b", "СМВ"),
    (r"\bСМБ\b", "СМВ"),
    (r"\bАЛС\b", "БАС"),
    (r"\bреlict\b", "реликтовый"),
    (r"\bреlictов\w*", "реликтовое"),
    (r"\bчастицов\w+", "частичный"),
    (r"\bЧастицов\w+", "Частичный"),
    (r"\bпузырёв\w+", "пузырьковых"),
    (r"\bзамерлит\w*", "замрёте"),
    (r"\bОккама бритв\w+", "бритвы Оккама"),
    (r"\bбритвой Оккама\b", "бритвы Оккама"),
    (r"\bнаш наблюдаемый Вселенная\b", "наша наблюдаемая Вселенная"),
    (r"\bНаш наблюдаемый Вселенная\b", "Наша наблюдаемая Вселенная"),
    (r"\bнамеками\b", "намёками"),
    (r"\bНамеками\b", "Намёками"),
]


def auto_fix(text):
    if not text:
        return text
    original = text
    for pattern, repl in AUTO_FIXES:
        text = re.sub(pattern, repl, text)
    if text != original:
        print(f"[AUTO-FIX] применены автозамены")
    return text


def is_allowed_char(ch):
    if ch in "\n\r\t ":
        return True
    cat = unicodedata.category(ch)
    if cat in ('Lu', 'Ll'):
        code = ord(ch)
        if 0x0400 <= code <= 0x04FF:
            return True
        if 0x0041 <= code <= 0x005A:
            return True
        if 0x0061 <= code <= 0x007A:
            return True
        return False
    if cat == 'Nd':
        return True
    if cat[0] in ('P', 'S'):
        return True
    if cat in ('Mn', 'Mc', 'Me', 'Cf'):
        return True
    if cat == 'Zs':
        return True
    return False


def find_bad_chars(text):
    return [ch for ch in text if not is_allowed_char(ch)]


def find_mixed_scripts(text):
    bad = []
    for word in re.findall(r"[А-Яа-яЁёA-Za-z]+", text):
        has_cyr = any("\u0400" <= c <= "\u04FF" for c in word)
        has_lat = any(("a" <= c.lower() <= "z") for c in word)
        if has_cyr and has_lat:
            bad.append(word)
    return bad


SUSPICIOUS_PATTERNS = [
    (r"\bСЗИ\b", "СЗИ вместо СМВ"),
    (r"\bСМБ\b", "СМБ вместо СМВ"),
    (r"\bАЛС\b", "АЛС вместо БАС"),
    (r"реlict", "реlict — смешение алфавитов"),
    (r"частицов", "частицовый — ошибка"),
    (r"Частицов", "Частицовый — ошибка"),
    (r"пузырёв", "пузырёвый — ошибка"),
    (r"замерлит", "замерлите — ошибка"),
    (r"Оккама бритв", "Оккама бритвой — порядок слов"),
    (r"наш наблюдаемый Вселенная", "согласование рода"),
    (r"Наш наблюдаемый Вселенная", "согласование рода"),
    (r"намеками", "намёками — потеряна ё"),
]


def find_suspicious(text):
    found = []
    for pattern, label in SUSPICIOUS_PATTERNS:
        if re.search(pattern, text or ""):
            found.append(label)
    return found


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
        url2 = url.replace("&model=flux", "")
        print("[IMG] retry without flux")
        tg("sendPhoto", chat_id=chat_id, photo=url2)
    time.sleep(0.5)

    safe_title = esc(title)
    safe_body = esc(body)
    text = f"<b>{safe_title}</b>\n\n{safe_body}"
    return send_tg(chat_id, text, reply_markup=reply_markup)


def call_llm(prompt, temperature=0.9, max_tokens=3000, model=None, use_prefill=True):
    """Запрос к LLM. use_prefill=True заставляет модель продолжить JSON, а не размышлять."""
    target_model = model or LLM_MODEL

    messages = [{"role": "user", "content": prompt}]
    if use_prefill:
        # Начинаем ответ ассистента с открывающей скобки — модель будет продолжать JSON
        messages.append({"role": "assistant", "content": '{"title": "'})

    body = {
        "model": target_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if not use_prefill:
        body["response_format"] = {"type": "json_object"}

    r = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com",
            "X-Title": "Gorizont Events",
        },
        json=body,
        timeout=240,
    )
    data = r.json()
    if "choices" not in data:
        raise Exception(f"LLM error: {data}")
    content = (data["choices"][0]["message"]["content"] or "").strip()
    # Возвращаем prefill к результату, если он был отрезан
    if use_prefill and not content.startswith("{"):
        content = '{"title": "' + content
    return content


def parse_json(text):
    if not text:
        raise ValueError("empty response")
    # Ищем первый { и последний }
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"no JSON object: {text[:200]}")
    candidate = text[start:end + 1]
    try:
        result = json.loads(candidate)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON: {e}: {candidate[:200]}")

    if isinstance(result, dict) and len(result) == 1:
        only_val = list(result.values())[0]
        if isinstance(only_val, dict) and "title" in only_val and "body" in only_val:
            return only_val
    if isinstance(result, dict):
        for v in result.values():
            if isinstance(v, dict) and "title" in v and "body" in v:
                return v
    return result


WRITER_PROMPT = """Ты — автор научно-популярного Telegram-канала о космосе. Напиши пост на тему: {topic}

Формат ответа: JSON-объект с полями title, body, image_prompt.

title — заголовок, 5-9 слов, цепляющий.
body — текст поста на русском, 1500-2000 знаков. 3-4 абзаца, между ними пустые строки. 3-5 эмодзи. В конце хештеги #космос #время #физика.
image_prompt — английский промпт для картинки, 12-18 слов. Космос: чёрные дыры, галактики, туманности, звёзды.

Пиши только кириллицей, без латиницы в русских словах. Проверь орфографию.
"""


PROOFREAD_PROMPT = """Ты — строгий корректор русского научно-популярного текста.

Исправь в этом JSON ошибки:

{json_text}

{extra_note}

ЧЕК-ЛИСТ:
1. Согласование рода/числа/падежа: «наш наблюдаемый Вселенная» → «наша наблюдаемая Вселенная», «Оккама бритвой» → «бритвы Оккама».
2. Термины: СЗИ/СМБ → СМВ; АЛС → БАС; «частицовый» → «частичный»; «замерлите» → «замрёте»; «пузырёвый» → «пузырьковый».
3. Орфография: ставь ё (намёками, звёзды, замёрз).
4. Смешение алфавитов: «реlict» → «реликтовый».
5. Естественный порядок слов — если фраза звучит как машинный перевод, перестрой.
6. Длина body 1500-2000 знаков: если короче — расширь, если длиннее — сократи.

НЕ меняй: image_prompt (если там нет ошибок), смысл, хештеги.

Верни JSON с теми же тремя полями: title, body, image_prompt.
"""


def validate(title, body, img):
    if not title or not body or not img:
        return False, "пустые поля"
    blen = len(body.strip())
    if blen < 1200:
        return False, f"body короткий ({blen})"
    if blen > 3000:
        return False, f"body длинный ({blen})"
    if len(title.strip()) < 8:
        return False, "заголовок короткий"
    if title.strip() in ("...", "…"):
        return False, "заголовок-заглушка"

    bad_title = find_bad_chars(title)
    bad_body = find_bad_chars(body)
    if bad_title or bad_body:
        bad = (bad_title + bad_body)[:5]
        return False, f"посторонние символы: {bad}"

    mixed_title = find_mixed_scripts(title)
    mixed_body = find_mixed_scripts(body)
    if mixed_title or mixed_body:
        bad = (mixed_title + mixed_body)[:5]
        return False, f"смешанные алфавиты: {bad}"

    return True, "ok"


def proofread(title, body, img, model=None):
    """Вычитка через LLM. Возвращает (title, body, img, applied)."""
    payload = {"title": title, "body": body, "image_prompt": img}
    json_text = json.dumps(payload, ensure_ascii=False)

    current = (title, body, img)
    for attempt in (1, 2):
        try:
            suspicious = find_suspicious(current[0] + " " + current[1])
            extra_note = ""
            if suspicious:
                extra_note = "ОСОБОЕ ВНИМАНИЕ: " + "; ".join(suspicious)

            raw = call_llm(PROOFREAD_PROMPT.format(json_text=json_text, extra_note=extra_note),
                           temperature=0.2, max_tokens=3000,
                           model=model, use_prefill=False)
            p = parse_json(raw)
            t2 = (p.get("title") or "").strip()
            b2 = (p.get("body") or "").strip()
            i2 = (p.get("image_prompt") or "").strip()
            if not (t2 and b2 and i2):
                continue
            current = (t2, b2, i2)

            remaining = find_suspicious(t2 + " " + b2)
            if not remaining:
                print("[PROOFREAD] чисто")
                return current + (True,)
            print(f"[PROOFREAD] остались: {remaining}, повтор")
            json_text = json.dumps({"title": t2, "body": b2, "image_prompt": i2}, ensure_ascii=False)
        except Exception as e:
            print(f"[PROOFREAD ERROR] {attempt}: {e}")
            time.sleep(1)

    return current + (True,)


def try_generate(topic, model, use_prefill, attempts):
    """Пробует сгенерировать пост с указанной моделью."""
    for attempt in range(1, attempts + 1):
        try:
            temp = 0.9 if attempt == 1 else 1.0
            raw = call_llm(WRITER_PROMPT.format(topic=topic),
                           temperature=temp, model=model, use_prefill=use_prefill)
            p = parse_json(raw)
            title = (p.get("title") or "").strip()
            body = (p.get("body") or "").strip()
            img = (p.get("image_prompt") or "").strip()

            title = auto_fix(title)
            body = auto_fix(body)

            ok, reason = validate(title, body, img)
            if not ok:
                print(f"[SKIP] {model.split('/')[-1]} #{attempt}: {reason}")
                time.sleep(1)
                continue

            print(f"[GENERATED] {model.split('/')[-1]} #{attempt}: body={len(body)}")
            return title, body, img
        except Exception as e:
            print(f"[ERROR] {model.split('/')[-1]} #{attempt}: {str(e)[:200]}")
            time.sleep(1)
    return None


def generate_one(topic):
    # Сначала основная модель с prefill
    result = try_generate(topic, LLM_MODEL, use_prefill=True, attempts=MAX_RETRIES)
    if not result:
        # Fallback: другая модель без prefill, с response_format
        print(f"[FALLBACK] переключаемся на {FALLBACK_MODEL}")
        result = try_generate(topic, FALLBACK_MODEL, use_prefill=False, attempts=2)
    if not result:
        return None

    title, body, img = result
    # Вычитка
    title_pr, body_pr, img_pr, applied = proofread(title, body, img)
    body_pr = auto_fix(body_pr)
    title_pr = auto_fix(title_pr)
    ok_pr, reason_pr = validate(title_pr, body_pr, img_pr)
    if ok_pr:
        print(f"[OK] после вычитки: body={len(body_pr)}")
        return title_pr, body_pr, img_pr
    print(f"[REJECT PROOFREAD] {reason_pr} — берём оригинал")
    return title, body, img


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

    selected_topics = random.sample(TOPICS, CANDIDATES_PER_DAY)
    print(f"[TOPICS] {selected_topics}")
    print(f"[MODEL] {LLM_MODEL}")
    print(f"[FALLBACK] {FALLBACK_MODEL}")

    created = []
    failed_topics = []
    for i, topic in enumerate(selected_topics, 1):
        print(f"--- Generating {i}/{CANDIDATES_PER_DAY}: {topic} ---")
        result = generate_one(topic)
        if not result:
            print(f"[FAILED] не удалось сгенерировать пост {i}")
            failed_topics.append(topic)
            continue

        title, body, img = result
        cur.execute("""INSERT INTO ai_drafts (topic, title, content, image_prompt, status)
                       VALUES (%s, %s, %s, %s, 'pending') RETURNING id""",
                    (topic, title, body, img))
        did = cur.fetchone()["id"]
        conn.commit()
        created.append((did, title, body, img, topic))
        print(f"[OK] draft #{did}: {title}")

    cur.close()
    conn.close()

    if not created:
        send_tg(TG_ADMIN_ID, "⚠️ Writer ничего не сгенерил. Проверь лог.")
        return

    for idx, (did, title, body, img, topic) in enumerate(created, 1):
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

    topics_str = " · ".join(t[:40] for t in [c[4] for c in created])
    send_tg(TG_ADMIN_ID, f"📌 Темы дня ({len(created)}): <b>{esc(topics_str)}</b>")

    if failed_topics:
        failed_str = " · ".join(t[:40] for t in failed_topics)
        send_tg(TG_ADMIN_ID,
                f"⚠️ Не удалось сгенерировать {len(failed_topics)} тем:\n<i>{esc(failed_str)}</i>")


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

    cur.execute("""INSERT INTO bot_state (key, value) VALUES ('tg_offset', %s)
                   ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value""",
                (str(max_id + 1),))
    conn.commit()
    cur.close()
    conn.close()
    print(f"Обработано: {processed}, offset={max_id+1}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python agent.py [write|publish|stats|callbacks|all]")
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
    elif t == "all":
        task_callbacks()
        task_publish()
    else:
        print(f"Unknown: {t}")

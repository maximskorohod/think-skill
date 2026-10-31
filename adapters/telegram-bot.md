# Адаптер: Telegram-бот

Память — **уровень 1 (б)**: бот хранит журнал каждого пользователя у себя, подставляет его в контекст и сам применяет блок «ЖУРНАЛ — обнови». Пользователь блок не видит и ничего не копирует.

## Системный промт

`dist/think-single.md` + служебный блок на каждый ход (дата, уровень памяти, журнал). Формат служебного блока и функции `context_block`, `split_update`, `apply_update` — в `adapters/api.md` (файл `think_api.py`).

## Хранилище

Одна таблица SQLite на всех — ключ `user_id` из Telegram:

```sql
CREATE TABLE journals (
  user_id    INTEGER PRIMARY KEY,
  journal    TEXT    NOT NULL DEFAULT '',
  history    TEXT    NOT NULL DEFAULT '[]',  -- JSON последних ~30 сообщений
  updated_at TEXT    NOT NULL
);
```

- Журнал — личные данные. Храни на своём сервере, не логируй тексты, дай команду удаления.
- Историю обрезай до последних ~30 сообщений: журнал несёт долгую память, история — только текущий разговор.

## Команды

| Команда | Что делает |
|---|---|
| `/start` | Короткое приветствие: что умеет бот, что журнал хранится у бота, команды. Затем первый ход модели с пустым сообщением «Привет» → у нового пользователя начнётся онбординг. |
| `/journal` | Прислать текущий журнал текстом (длинный — частями по 4000 символов). |
| `/export` | Прислать журнал файлом `think-journal.md`. |
| `/import` | Следующее сообщение или .md-файл пользователя заменяет журнал (после подтверждения кнопкой). Для переноса с другой платформы. |
| `/new` | Очистить историю разговора, журнал оставить. |
| `/forget` | Удалить журнал и историю пользователя (после подтверждения кнопкой). |

## Обработчик сообщения (набросок, python-telegram-bot 21)

```python
import datetime as dt, json, os, sqlite3
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
from think_api import turn  # из adapters/api.md

db = sqlite3.connect("think.db")

def load(uid):
    row = db.execute("SELECT journal, history FROM journals WHERE user_id=?", (uid,)).fetchone()
    return (row[0] or None, json.loads(row[1])) if row else (None, [])

def save(uid, journal, history):
    db.execute(
        "INSERT INTO journals(user_id, journal, history, updated_at) VALUES(?,?,?,?) "
        "ON CONFLICT(user_id) DO UPDATE SET journal=excluded.journal, history=excluded.history, "
        "updated_at=excluded.updated_at",
        (uid, journal or "", json.dumps(history[-30:], ensure_ascii=False), dt.datetime.now().isoformat()))
    db.commit()

async def on_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    journal, history = load(uid)
    answer, new_journal, history = turn(journal, history, update.message.text)  # в проде — в отдельном потоке
    save(uid, new_journal if new_journal is not None else journal, history)
    await update.message.reply_text(answer)

app = Application.builder().token(os.environ["TELEGRAM_BOT_TOKEN"]).build()
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
# + CommandHandler для /start /journal /export /import /new /forget
app.run_polling()
```

Дата: `turn` подставляет сегодняшнюю дату сервера. Для пользователей в других часовых поясах храни их пояс и передавай `today` явно.

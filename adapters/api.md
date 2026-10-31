# Адаптер: любая модель через API

Подходит для своего бота, скрипта, внутреннего сервиса. Память — **уровень 1 с точки зрения модели**: твой код подставляет журнал в начало разговора и сам применяет блок «ЖУРНАЛ — обнови», который модель выдаёт в конце ответа (формат — `modules/memory.md`).

## Схема

1. Системный промт = `dist/think-single.md` (или `core/system-prompt.md` + нужные модули).
2. Вторым системным блоком — служебный контекст: дата, уровень памяти, текущий журнал.
3. Ответ модели → вырезать блок `journal`, применить к журналу, сохранить, человеку показать остальное.

Служебный блок, который понимает ядро:

```
Сегодня: 2026-03-14
Память: уровень 1 — журнал ниже подставляет система; в конце ответа выдай блок «ЖУРНАЛ — обнови», система применит его сама. Человеку блок не показывается.
ЖУРНАЛ ПОЛЬЗОВАТЕЛЯ:
<текст журнала или «(журнала нет)»>
```

## Пример: `think_api.py`

Ключей в коде нет: берутся из переменных окружения. Модель — тоже из переменной, чтобы не зашивать устаревшее имя.

```python
"""Минимальная обвязка think для любой модели. Python 3.10+."""
from __future__ import annotations

import datetime as dt
import os
import re
from pathlib import Path

PKG = Path(__file__).resolve().parent  # положи рядом с папкой dist/ или поправь путь
SYSTEM_PROMPT = (PKG / "dist" / "think-single.md").read_text(encoding="utf-8")

BLOCK_RE = re.compile(r"ЖУРНАЛ — обнови[^\n]*\n```journal\n(.*?)\n```", re.S)
MARK_RE = re.compile(r"^<!-- (replace: (.+?)|append|full) -->[ \t]*$", re.M)
HEAD_RE = re.compile(r"^(#{1,2} .+|---)\s*$")
TOP_SECTIONS = ("# Профиль", "# Действующие решения")


def context_block(journal: str | None, today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    return (
        f"Сегодня: {today.isoformat()}\n"
        "Память: уровень 1 — журнал ниже подставляет система; в конце ответа выдай блок "
        "«ЖУРНАЛ — обнови», система применит его сама. Человеку блок не показывается.\n"
        "ЖУРНАЛ ПОЛЬЗОВАТЕЛЯ:\n" + (journal.strip() if journal else "(журнала нет)")
    )


def split_update(reply: str) -> tuple[str, str | None]:
    """Возвращает (текст для человека, тело блока journal или None)."""
    m = BLOCK_RE.search(reply)
    if not m:
        return reply, None
    visible = (reply[: m.start()] + reply[m.end():]).strip()
    visible = re.sub(r"\n.*Сохрани блок в журнал.*$", "", visible).strip()  # подсказка для ручного режима
    return visible, m.group(1)


def _replace_section(journal: str, heading: str, body: str) -> str:
    lines = journal.split("\n")
    start = next((i for i, l in enumerate(lines) if l.strip().startswith(heading)), None)
    if start is None:
        if heading.startswith(TOP_SECTIONS):
            return body + "\n\n" + journal
        return journal.rstrip("\n") + "\n\n" + body + "\n"
    end = next((j for j in range(start + 1, len(lines)) if HEAD_RE.match(lines[j])), len(lines))
    return "\n".join(lines[:start] + body.split("\n") + [""] + lines[end:])


def apply_update(journal: str, update: str) -> str:
    marks = list(MARK_RE.finditer(update))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(update)
        body = update[m.end():end].strip("\n")
        if m.group(1) == "full":
            journal = body + "\n"
        elif m.group(1) == "append":
            journal = journal.rstrip("\n") + "\n\n" + body + "\n"
        else:
            journal = _replace_section(journal, m.group(2).strip(), body)
    return re.sub(r"\n{3,}", "\n\n", journal)


def call_llm(system: list[str], messages: list[dict]) -> str:
    """Подставь своего провайдера. Ниже — два варианта, нужный раскомментируй."""
    model = os.environ["THINK_MODEL"]
    # --- Anthropic (pip install anthropic; ключ в ANTHROPIC_API_KEY) ---
    # import anthropic
    # r = anthropic.Anthropic().messages.create(
    #     model=model, max_tokens=4000,
    #     system=[{"type": "text", "text": s} for s in system], messages=messages)
    # return "".join(b.text for b in r.content if b.type == "text")
    # --- OpenAI-совместимый API (pip install openai; ключ в OPENAI_API_KEY, OPENAI_BASE_URL при необходимости) ---
    # from openai import OpenAI
    # r = OpenAI().chat.completions.create(
    #     model=model, messages=[{"role": "system", "content": "\n\n".join(system)}, *messages])
    # return r.choices[0].message.content
    raise NotImplementedError("выбери провайдера в call_llm")


def turn(journal: str | None, history: list[dict], user_text: str) -> tuple[str, str | None, list[dict]]:
    """Один ход разговора. Возвращает (ответ человеку, новый журнал или None, новая история)."""
    history = history + [{"role": "user", "content": user_text}]
    reply = call_llm([SYSTEM_PROMPT, context_block(journal)], history)
    visible, update = split_update(reply)
    new_journal = apply_update(journal or "", update) if update else None
    return visible, new_journal, history + [{"role": "assistant", "content": reply}]


if __name__ == "__main__":  # консольный чат, журнал в ./think-journal.md
    jpath = Path("think-journal.md")
    journal = jpath.read_text(encoding="utf-8") if jpath.exists() else None
    history: list[dict] = []
    while (text := input("> ").strip()):
        answer, new_journal, history = turn(journal, history, text)
        print(answer)
        if new_journal is not None:
            journal = new_journal
            jpath.write_text(journal, encoding="utf-8")
            print("[журнал обновлён]")
```

## Заметки

- Историю храни целиком с блоками `journal` — модели полезно видеть, что она уже записала. Человеку показывай `visible`.
- Журнал в служебном блоке обновляй на каждом ходу: модель сверяется с актуальной версией.
- Длинный журнал (> ~300 строк): подставляй шапки (`# Профиль`, `# Действующие решения`, парковку) и записи без заполненного «Итога» или моложе 90 дней; полный архив храни отдельно.
- Слабая модель путает шаги — подставляй `core/system-prompt.md` + только модули текущего шага; ядро самодостаточно.

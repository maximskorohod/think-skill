#!/usr/bin/env python3
"""Сборка dist/ из core/ и modules/.

    python build.py

Создаёт:
  dist/think-single.md     ядро + все модули в одном файле (одно поле промта)
  dist/think-compact.md    сжатое ядро <= 7500 символов (Custom GPT Instructions); модули — в Knowledge
  dist/claude-code/think/  готовая папка навыка: SKILL.md + core/ + modules/

Маркеры в core/system-prompt.md:
  <!-- compact:drop --> ... <!-- /compact:drop -->   выбросить в compact, оставить в остальных
  <!-- compact:only ... -->                           показать только в compact

Падает (код 1), если compact > 7500 символов, если в нейтральных файлах есть
платформенные слова, или если ядро ссылается на несуществующий модуль.
"""
from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORE = ROOT / "core" / "system-prompt.md"
MODULES_DIR = ROOT / "modules"
DIST = ROOT / "dist"
ADAPTER_SKILL = ROOT / "adapters" / "claude-code" / "SKILL.md"

MODULE_ORDER = ["layers", "modes", "interview", "goals", "misses", "memory"]
COMPACT_LIMIT = 7500
FORBIDDEN = [r"~/\.claude", r"Claude Code", r"tool", r"скилл"]

DROP_RE = re.compile(r"<!-- compact:drop -->\n?(.*?)<!-- /compact:drop -->\n?", re.S)
ONLY_RE = re.compile(r"<!-- compact:only\n(.*?)-->\n?", re.S)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8").replace("\r\n", "\n")


def tidy(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"


def core_full(text: str) -> str:
    """Для single и навыка: compact:only убрать, compact:drop раскрыть."""
    return tidy(DROP_RE.sub(r"\1", ONLY_RE.sub("", text)))


def core_compact(text: str) -> str:
    return tidy(ONLY_RE.sub(r"\1", DROP_RE.sub("", text)))


def check(errors: list[str]) -> None:
    core = read(CORE)
    for name in MODULE_ORDER:
        path = MODULES_DIR / f"{name}.md"
        if not path.exists():
            errors.append(f"нет модуля modules/{name}.md")
            continue
        first = read(path).splitlines()[0]
        if not first.startswith(f"# think · {name} — "):
            errors.append(f"{name}.md: первая строка должна быть '# think · {name} — …'")
    for ref in set(re.findall(r"`([a-z]+)`", core)):
        if ref not in MODULE_ORDER:
            errors.append(f"ядро ссылается на неизвестный модуль `{ref}`")
    extra = {p.stem for p in MODULES_DIR.glob("*.md")} - set(MODULE_ORDER)
    if extra:
        errors.append(f"модули вне MODULE_ORDER: {sorted(extra)}")


def scan_neutral(paths: list[Path], errors: list[str]) -> None:
    for p in paths:
        text = read(p)
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text, re.I):
                line = text.count("\n", 0, m.start()) + 1
                errors.append(f"{p.relative_to(ROOT)}:{line}: платформенное слово '{m.group(0)}'")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errors: list[str] = []
    check(errors)
    if errors:
        print("\n".join("ОШИБКА: " + e for e in errors))
        return 1

    raw_core = read(CORE)
    modules = {n: read(MODULES_DIR / f"{n}.md") for n in MODULE_ORDER}

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    single = core_full(raw_core) + "".join("\n---\n\n" + tidy(modules[n]) for n in MODULE_ORDER)
    (DIST / "think-single.md").write_text(single, encoding="utf-8", newline="\n")

    compact = core_compact(raw_core)
    (DIST / "think-compact.md").write_text(compact, encoding="utf-8", newline="\n")

    skill = DIST / "claude-code" / "think"
    (skill / "core").mkdir(parents=True)
    (skill / "modules").mkdir()
    shutil.copyfile(ADAPTER_SKILL, skill / "SKILL.md")
    (skill / "core" / "system-prompt.md").write_text(core_full(raw_core), encoding="utf-8", newline="\n")
    for n in MODULE_ORDER:
        (skill / "modules" / f"{n}.md").write_text(tidy(modules[n]), encoding="utf-8", newline="\n")

    neutral = [CORE, *MODULES_DIR.glob("*.md"), DIST / "think-single.md", DIST / "think-compact.md",
               *(skill / "core").glob("*.md"), *(skill / "modules").glob("*.md")]
    scan_neutral(neutral, errors)

    print(f"{'файл':<44}{'символов':>10}{'байт':>9}{'строк':>7}")
    for p in sorted(DIST.rglob("*.md")):
        t = read(p)
        print(f"{str(p.relative_to(ROOT)).replace(chr(92), '/'):<44}{len(t):>10}{len(t.encode('utf-8')):>9}{t.count(chr(10)):>7}")

    if len(compact) > COMPACT_LIMIT:
        errors.append(f"think-compact.md: {len(compact)} символов > {COMPACT_LIMIT}")
    else:
        print(f"\ncompact: {len(compact)} / {COMPACT_LIMIT} символов — OK")

    if errors:
        print("\n".join("ОШИБКА: " + e for e in errors))
        return 1
    print("платформенных слов в core/, modules/, dist/ нет — OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

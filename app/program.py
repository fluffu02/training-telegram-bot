from datetime import date
import json
from pathlib import Path
import re
from typing import Any


def load_program(path: Path) -> dict[int | str, Any]:
    with path.open("r", encoding="utf-8") as file:
        raw = json.load(file)
    program: dict[int | str, Any] = {}
    for key, value in raw.items():
        if key.isdigit():
            program[int(key)] = value
        else:
            program[key] = value
    return program


def get_training_for_date(program: dict[int | str, Any], target_date: date) -> dict[str, Any]:
    return program[target_date.weekday()]


def _progress_text(text: str, progression_weeks: int) -> str:
    if progression_weeks <= 0:
        return text

    target_words = r"(повтор(?:ений|ения)?|касани(?:й|я)|подход(?:а|ов)?|круг(?:а|ов)?)"

    def add_range(match: re.Match[str]) -> str:
        start = int(match.group(1)) + progression_weeks
        end = int(match.group(2)) + progression_weeks
        return f"{start}–{end}{match.group(3)}"

    def add_single(match: re.Match[str]) -> str:
        value = int(match.group(1)) + progression_weeks
        return f"{value}{match.group(2)}"

    text = re.sub(rf"(\d+)\s*[–-]\s*(\d+)(\s+{target_words})", add_range, text)
    text = re.sub(rf"(?<![×\d–-])(\d+)(\s+{target_words})", add_single, text)
    text = re.sub(r"(?<![×\d–-])(\d+)(\s+на каждую)", add_single, text)
    text = re.sub(
        r"(—\s*)(\d+)(\s+(?:берпи|приседаний|отжиманий|скручиваний))",
        lambda match: f"{match.group(1)}{int(match.group(2)) + progression_weeks}{match.group(3)}",
        text,
    )
    return text


def render_training_message(training: dict[str, Any], target_date: date, progression_weeks: int = 0) -> str:
    items = "\n".join(
        f"{index}. {_progress_text(item, progression_weeks)}"
        for index, item in enumerate(training["items"], start=1)
    )
    return (
        f"Сегодня {target_date:%d.%m.%Y}: {training['day']} — {training['title']}\n"
        f"Время: {training['duration']}\n\n"
        f"Формат: {_progress_text(training['format'], progression_weeks)}\n\n"
        f"Упражнения:\n{items}"
    )


def render_week_message(program: dict[int | str, Any], progression_weeks: int = 0) -> str:
    parts = ["Тренировки на неделю:"]
    for weekday in range(7):
        training = program[weekday]
        items = "\n".join(
            f"  {index}. {_progress_text(item, progression_weeks)}"
            for index, item in enumerate(training["items"], start=1)
        )
        parts.append(
            f"\n{training['day']} — {training['title']} ({training['duration']})\n"
            f"Формат: {_progress_text(training['format'], progression_weeks)}\n"
            f"{items}"
        )
    return "\n".join(parts)

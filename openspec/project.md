# Тренировочный Telegram-бот

Источник требований: [1st_prompt.md](../1st_prompt.md). Язык интерфейса и документации — русский.

Закрытая группа, один разрешённый chat_id, владелец из env. Спортсмены сами
связывают Telegram user id с ключом athlete. Общая тренировка и упражнение,
индивидуальные подходы. Результаты сохраняются сразу в SQLite.

Стек: Python, aiogram 3, long polling, SQLAlchemy 2, Alembic, Pydantic,
PyYAML, pytest, Docker Compose. Без открытых портов и внешних сервисов.
Секреты только в env. Продакшен-окружение не задано: TARGET_UNRESOLVED.

Первоначальная реализация завершена: `changes/archive/2026-10-09-0001-training-bot-mvp/`.
CP-01–CP-07 приняты; 57 тестов, локальные Docker smoke и SIGTERM прошли.
Реальный Telegram ещё не проверялся; инструкция оператора — в README.md.

CP-08 завершён: `changes/archive/2026-10-09-0002-weight-in-grams/`.
Вес хранится в weight_g INTEGER (граммы); ввод и отображение — килограммы.
Миграция 0002 и числовые SQL-операции проверены; полная suite — 75 PASS.

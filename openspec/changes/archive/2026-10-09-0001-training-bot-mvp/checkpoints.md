# Состояние выполнения

## Recovery capsule

- Режим: DEEP для границ доступа/целостности; остальные этапы — узкие проверки.
- Текущий этап: CP-07 PASSED; локальный MVP завершён.
- Источник требований: `1st_prompt.md`; решение: `design.md`.
- Блокирующих замечаний нет. Обязательных локальных работ не осталось.
- Делегирование: researcher — только официальные контракты стека;
  reviewer — FULL итоговой реализации. Primary — единственный автор кода/состояния.
- Пользовательский gate: NOT_REQUIRED для локального MVP по явному запросу.
- Remote: TARGET_UNRESOLVED; реальные секреты/деплой не используются.

## CP-01 — PASSED

Цель: минимальная структура, env-конфигурация, зависимости, тестовый каркас,
Docker skeleton. Барьер: проверка каркаса до реализации всего бота.
Baseline: NOT_APPLICABLE, см. design.md. Проверки: 4 PASS, lock создан.
Ревью этапа: NOT_REQUIRED; итоговое FULL запланировано CP-07.
Приёмка: импорт приложения и тест конфигурации работают без сети/секретов.

## Принятые этапы

| Этап | Статус | Цель | Зависимость |
|---|---|---|---|
| CP-02 | PASSED | БД и миграции; 6 PASS | CP-01 |
| CP-03 | PASSED | Telegram и привязки; 4 PASS | CP-02 |
| CP-04 | PASSED | Импорт программы; 12 PASS | CP-03 |
| CP-05 | PASSED | Тренировочное ядро; 22 PASS | CP-04 |
| CP-06 | PASSED | Навигация и восстановление; 6 PASS | CP-05 |
| CP-07 | PASSED | Поставка и документация; 57 PASS, build/smoke/SIGTERM PASS | CP-06 |

## CP-07 — приёмка

Все локальные функции реализованы; suite и независимое FULL-ревью завершены.
Reviewer: mvp_review, только чтение. Пользовательский gate: NOT_REQUIRED.
Сборка и локальный smoke разрешены запросом; polling с настоящим токеном не запускается.
Проверки: PASS, см. итоговый журнал design.md. Блокеров нет. Primary принял этап:
тесты/сборка завершены, замечания ревью исправлены, документация соответствует реализации.

FULL: PASS_WITH_NOTES, CRITICAL/MAJOR нет. Два MINOR: старое меню участников
и адресация команд другому боту. Исправления проверены primary: focused 11 PASS,
итоговая suite 57 PASS. Дополнительный DELTA не требовался: блокирующих находок нет.
Build/smoke/Compose/SIGTERM: PASS. Реальный Telegram: NOT_RUN (нет секретов/группы).

## Файлы по этапам

| Этап | Основные добавленные/изменённые файлы |
|---|---|
| CP-01 | pyproject.toml, requirements.lock, app/config.py, app/__main__.py, Dockerfile, compose.yaml, .env.example, tests/test_config.py |
| CP-02 | app/db/models.py, app/db/database.py, alembic.ini, migrations/, tests/test_database.py, tests/conftest.py |
| CP-03 | app/bot.py, app/services/access.py, app/services/bindings.py, app/handlers/telegram.py, tests/test_bindings.py |
| CP-04 | app/parsers/program.py, app/services/programs.py, examples/program.example.yaml, tests/test_programs.py |
| CP-05 | app/parsers/result.py, app/services/training.py, app/handlers/views.py, tests/test_result_parser.py, tests/test_training.py |
| CP-06 | app/services/training.py, app/handlers/telegram.py, tests/test_navigation.py |
| CP-07 | README.md, app/logging_setup.py, tests/test_telegram.py, tests/test_concurrency.py, tests/container_smoke.py, tests/polling_shutdown.py, ignore-файлы, OpenSpec |

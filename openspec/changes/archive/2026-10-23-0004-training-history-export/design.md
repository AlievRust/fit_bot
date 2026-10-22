# Устройство экспорта

Режим STANDARD: реализация основным агентом, без отдельных checkpoint и
делегирования. Повторно используется require_owner; существующие проверки
тренировочной группы и привязки не изменяются.

## Контракт

`services/export.py` проверяет владельца и private-чат до чтения данных.
Доступ к SQLite — отдельное соединение `mode=ro`, `PRAGMA query_only=ON`,
явный `BEGIN` для согласованного снимка и закрытие в finally. Оно не использует
Database.transaction с BEGIN IMMEDIATE. Выборка не зависит от активной программы,
настроенной группы или Telegram chat_id (legacy использует синтетический chat_id).

42 дня — интервал `[generated_at - 42 суток, generated_at]` по finished_at,
только status=completed. Все времена UTC в ISO 8601 с Z; это соответствует
правилу utcnow в модели. В all фильтра даты/статуса нет; finished_at может быть null.
Порядок сессий: started_at, id; упражнений: order, id; подходов: created_at, id.
Порядок записи результата задаётся order внутри спортсмена/упражнения.

JSON schema_version=1: generated_at, period (mode/from/to/selection), units,
sessions. Сессия содержит id, started_at, finished_at, status, program(key/version),
day(key/name), athletes(athlete_key/display_name), exercises. Упражнение содержит
exercise_key/name/order/skipped/units и athletes, у каждого plans и results.
План: planned_set_number/reps_min/reps_max/target_rir. Факт: order/created_at/type/
planned_set_number/reps/weight_kg/subjective_rating. weight_kg — десятичная строка
из целых граммов без float. Отсутствующие оценки и RIR плана остаются null;
фактический RIR и комментарии не создаются. Поля выводятся по белому списку.

type: номер задан → planned; NULL в программе legacy_telegram_2026_10_03_05 →
legacy_unplanned; другой NULL → extra. Значение 1 кг не преобразуется в 0 кг.
Для exercise_key=farmer_carry: reps=m, weight=kg, weight_scope=per_dumbbell;
для остальных reps=count, weight=kg, weight_scope=external_load.

Markdown строится из того же снимка: дата → сессия → спортсмен → упражнения
по порядку программы; таблица ставит рядом номер/план/факт, отдельно помечает
extra и legacy. Пропуски общие для группы, сохранённые результаты не скрываются.
Динамический текст экранируется для Markdown-таблиц. Пустая история — валидный
JSON с sessions=[] или отчёт с сообщением об отсутствии тренировок.

Telegram-адаптер отправляет BufferedInputFile в ответ только на private-команду.
В группе не отправляет личных сообщений автоматически: владелец сам открывает
бота, нажимает «Начать» и повторяет команду. Без дополнительных изменений /start.
Поддерживаются ровно три формы команды. Документ больше 50 000 000 байт не
отправляется, выводится понятная ошибка без усечения истории. Ошибки Telegram
при отправке перехватываются; повтор команды формирует свежий снимок.

## Внешний контракт

Telegram, Bot API sendDocument и Bots FAQ, проверено 2026-10-22:
https://core.telegram.org/bots/api#senddocument и
https://core.telegram.org/bots/faq#how-do-i-upload-a-large-file
— облачный API принимает документы до 50 MB. Принят консервативный лимит
50 000 000 байт перед сетевой отправкой. Ошибки транспорта обрабатываются
через TelegramAPIError и TelegramNetworkError установленного aiogram 3.
Telegram, Bots: An introduction for developers,
https://core.telegram.org/bots#how-are-bots-different-from-users
— бот не начинает личный диалог первым; владелец сам открывает диалог.

## Проверки и ограничения

Baseline: `pytest tests/test_telegram.py tests/test_training.py -q
--basetemp=data/pytest-export-baseline-20261022` — PASS, 12 тестов за 28,04 с.

Проверки: оба формата, границы UTC, все статусы/legacy, точность весов и Unicode,
пропуски, отменённые результаты, порядок, авторизация до чтения, доставка/ошибки,
лимит файла; снимок всех таблиц и data_version до/после экспорта.
Полный pytest и git diff --check. Реальный Telegram без токена не проверяется.
Экспорт формируется в памяти; объём всех данных должен помещаться в память
процесса. Автоматическая разбивка и постоянное хранение не входят в задачу.

## Результаты

- Полный regression: `.venv/Scripts/python.exe -m pytest -q
  --basetemp=data/pytest-export-full-20261023` — **122 PASS за 81,02 с**,
  включая 36 новых параметризованных проверок в tests/test_export.py.
- `git -c core.autocrlf=false diff --check` — PASS.
- `python -m compileall -q app tests` — PASS.
- Учебный JSON в docs/history_export.md разобран json.loads; Markdown-фрагмент
  совпадает с результатом render_markdown для этого JSON — PASS.
- Read-only подтверждён запретом DELETE на экспортном соединении, сравнением
  iterdump всех таблиц и неизменностью data_version отдельного наблюдателя
  после всех трёх вариантов. В SQL-трассе нет DML/COMMIT.
- При первичном focused run один тест проверки read-only оставлял тестовую
  транзакцию после ожидаемого отказа DELETE. Исправлена очистка в самом тесте
  (rollback до чтения); повторная проверка и полный regression прошли.
- Основной агент проверил конечные изменения, контракт форматов и потребителей
  новых type/period/event значений. Существующих внешних потребителей нет;
  legacy-ключ и ограничения статусов совпадают с импортом и ORM-моделью.
  Независимый reviewer не запускался (STANDARD), пользовательских gates нет.
- Миграции и зависимости не менялись; Docker и реальный Telegram не проверялись.
  Ручная инструкция — docs/history_export.md. Коммит и развёртывание не выполнялись.

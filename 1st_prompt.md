# 1st_prompt.md — Telegram Gym Training Bot MVP

## 0. Роль и режим работы

Проект Telegram-бота для ведения силовых тренировок.

Цель — сделать **минимальный, надёжный пошаговый пульт тренировки**, а не фитнес-платформу, не AI-тренера и не аналитический центр.

Работай последовательно, небольшими проверяемыми шагами. Не расширяй scope без необходимости.

Если возникает развилка, которая:
- заметно меняет UX;
- меняет модель данных так, что потом будет трудно мигрировать;
- затрагивает безопасность/идентификацию пользователей;
- требует отказаться от требований ниже,

остановись и задай оператору вопрос.

Во всех остальных случаях выбирай самое простое решение, совместимое с требованиями.

После каждого checkpoint:
1. запусти релевантные тесты/проверки;
2. кратко зафиксируй, что сделано;
3. перечисли изменённые файлы;
4. укажи найденные ограничения/риски;
5. продолжай дальше, если нет критической развилки.

Не реализуй функции из раздела **Non-goals**.

---

# 1. Product goal

Есть небольшая закрытая Telegram-группа, в которой тренируются несколько зарегистрированных пользователей.

Основной сценарий должен быть предельно коротким:

1. пользователь запускает `/start_train`;
2. выбирает день из активной программы (содержит список упражнений для каждого участника по дням);
3. выбираются участники тренировки;
4. бот показывает текущее упражнение и подсказку для каждого участника:
   - название упражнения;
   - номер текущего подхода;
   - план повторов;
   - целевой RIR;
   - результат аналогичного подхода на прошлой тренировке, если он есть;
5. спортсмен выполняет подход и пишет обычным сообщением:
   `8*50`
6. бот по Telegram user id понимает, кто это;
7. сохраняет результат текущего упражнения в БД немедленно;
8. показывает этому спортсмену подсказку по следующему подходу;
9. после завершения упражнения пользователь переводит тренировку к следующему упражнению;
10. цикл повторяется до конца списка.

Ключевой принцип UX:

> В штатной тренировке пользователь почти ничего не вводит, кроме `повторы*вес комментарий`.

Пример:

```text
8*50
10*32.5
6*70 тяжело
10*30 легко
```

---

# 2. Non-goals для первой версии

НЕ делать сейчас:

- AI/LLM внутри runtime;
- автоматическое составление тренировочных программ;
- автоматическое изменение веса пользователю;
- RAG;
- веб-интерфейс;
- мобильное приложение;
- графики;
- сложную аналитику;
- PostgreSQL;
- Redis;
- Celery;
- FastAPI;
- webhook;
- Caddy/nginx;
- Mini App;
- распознавание фото;
- голосовой ввод;
- публичную регистрацию пользователей;
- роли/ACL сложнее минимального admin/member;
- поддержку произвольной естественной речи;
- сложный каталог синонимов упражнений;
- микросервисную архитектуру.

Если что-либо из этого кажется удобным — всё равно не добавлять без отдельного решения оператора.

---

# 3. Зафиксированный технический стек

Использовать:

- Python 3.x актуальной стабильной ветки;
- aiogram 3.x;
- Telegram Bot API;
- **long polling**, не webhook;
- SQLite;
- SQLAlchemy 2.x;
- Alembic для миграций;
- Pydantic для конфигурации/валидации;
- YAML как человекочитаемый формат импорта тренировочной программы;
- pytest;
- Docker;
- Docker Compose.

Зависимости должны быть закреплены воспроизводимым способом (`pyproject.toml` + lock-файл либо эквивалентный понятный вариант).

Не публиковать сетевые порты: при long polling они не нужны.

---

# 4. Telegram deployment model

Бот работает в одной закрытой Telegram-группе.

Для штатного сценария он должен видеть обычные сообщения вида `8*50`.

Для MVP принять следующий вариант:

- бот добавляется в тренировочную группу **администратором**;
- выдавать ему только минимально необходимые права;
- специально отключать Group Privacy Mode через BotFather не требуется, если бот является администратором группы;
- в README обязательно объяснить, что статус администратора нужен прежде всего для получения обычных сообщений группы.

Не выдавать боту административные права, которыми приложение не пользуется:
- удаление сообщений;
- блокировка пользователей;
- изменение информации группы;
- добавление администраторов;
- и другие лишние права.

Бот должен обрабатывать тренировочные результаты только:
- из разрешённой группы;
- от привязанных пользователей;
- при наличии активной тренировки;
- если этот пользователь входит в список участников активной тренировки.

---

# 5. Идентификация Telegram-пользователей

## 5.1. Важное правило

Никогда не использовать `@username`, first_name или display name как основной идентификатор.

Основной Telegram identity:

```text
telegram_user_id
```

Хранить как 64-bit integer / BIGINT.

В программе тренировок пользователи задаются стабильным внутренним ключом:

```text
xrust
tim
```

Пример:

```yaml
athletes:
  - key: xrust
    display_name: xRust
  - key: tim
    display_name: Tim
```

Связь:

```text
telegram_user_id -> athlete.key
```

хранится в БД.

Username/first_name можно сохранять только как справочные поля.

---

# 6. Bootstrap и привязка пользователей

Не хардкодить соответствие Telegram user -> athlete в исходниках.

В `.env` допускается только идентификатор владельца приложения:

```env
BOT_TOKEN=...
OWNER_TELEGRAM_ID=123456789
```

`OWNER_TELEGRAM_ID` — это не пользователь, который обязан регистрировать всех спортсменов вручную.
Это владелец/оператор конфигурации бота, которому доступны административные действия.

`BOT_TOKEN` не должен попадать в git.

## 6.1. Настройка группы

После первого запуска owner добавляет бота в нужную группу и выполняет:

```text
/setup_group
```

Бот сохраняет текущий `chat_id` как разрешённую тренировочную группу.

После настройки обычные training events из других чатов игнорируются.

## 6.2. Self-service привязка athlete

После загрузки программы в БД существуют athlete keys, например:

```text
xrust
tim
```

Каждый спортсмен привязывает **самого себя** к своему athlete key.

Пример:

```text
xRust: /bind xrust
Tim:   /bind tim
```

Семантика `/bind <athlete_key>`:

1. взять `telegram_user_id` автора команды;
2. убедиться, что команда пришла из allowed chat;
3. убедиться, что `athlete_key` существует;
4. убедиться, что athlete ещё не занят другим Telegram user;
5. убедиться, что Telegram user ещё не привязан к другому athlete;
6. создать binding.

Таким образом обычный спортсмен не может привязать другого человека через reply или произвольный Telegram ID.

Добавить команды:

```text
/whoami
/bind <athlete_key>
/bindings
/unbind
```

Поведение:

- `/bind <athlete_key>` — доступен обычным участникам allowed chat и привязывает только автора команды;
- `/whoami` — показывает текущую привязку автора;
- `/unbind` — снимает собственную привязку автора;
- `/bindings` — административная команда для owner, показывает все bindings;
- owner должен иметь отдельный административный способ исправить ошибочную/зависшую привязку другого пользователя.

Для owner реализовать минимальный recovery-механизм, например:

```text
/admin_unbind <athlete_key>
```

или эквивалентную простую команду.

Не делать полноценную систему регистрации/инвайтов в MVP.

Ограничения:

- один Telegram user id нельзя привязать к двум athlete;
- один athlete нельзя одновременно привязать к двум Telegram users;
- существующий binding нельзя тихо перезаписывать;
- конфликт должен приводить к понятному сообщению об ошибке.

---

# 7. Формат тренировочной программы

Использовать YAML с явной schema version.

Создай схему, близкую к следующей:

```yaml
schema_version: 1

program:
  key: strength_2026_10
  name: "Силовой блок 2026-10"
  version: 1

athletes:
  - key: xrust
    display_name: xRust

  - key: tim
    display_name: Tim

days:
  - key: tuesday
    name: "Вторник"

    exercises:
      - key: bench_press
        name: "Жим штанги лёжа"
        order: 1

        prescriptions:
          xrust:
            - reps: "8"
              rir: 3
            - reps: "6-8"
              rir: 3
            - reps: "6-8"
              rir: 3
            - reps: "6-8"
              rir: 3

          tim:
            - reps: "10"
              rir: 3
            - reps: "8-10"
              rir: 3
            - reps: "8-10"
              rir: 3
            - reps: "8-10"
              rir: 3
```

Требования:

- `schema_version` обязателен;
- `program.key + version` должны однозначно идентифицировать версию программы;
- `athlete.key` стабилен и не зависит от Telegram;
- `day.key` стабилен;
- `exercise.key` стабилен;
- `display name` можно менять без потери истории;
- количество подходов у разных athletes для одного упражнения может различаться;
- `reps` должен поддерживать точное значение (`"8"`) и диапазон (`"6-8"`);
- `rir` nullable, но если задан — integer в разумном диапазоне;
- импорт должен валидироваться до записи в БД;
- при ошибке импорт должен быть атомарно отклонён;
- существующая версия программы не должна тихо перезаписываться.

Для MVP достаточно импорта YAML-файла администратором через Telegram.

Сделай простой UX импорта, например документ с caption:

```text
/import_program
```

После успешной валидации вывести краткое summary:
- программа/version;
- дни;
- количество упражнений;
- athletes;
- результат импорта.

Не добавляй сложный wizard.

---

# 8. Модель данных

Спроектируй нормальную, но минимальную реляционную модель.

Нужны как минимум сущности:

## athletes

- id
- key UNIQUE
- display_name
- active
- created_at

## telegram_bindings

- id
- telegram_user_id BIGINT UNIQUE
- athlete_id UNIQUE FK
- telegram_username nullable
- telegram_first_name nullable
- bound_at

## app_settings / allowed_chat

Достаточно хранить:
- allowed_chat_id
- configured_at

Можно выбрать отдельную таблицу или простую settings-table.

## programs

- id
- key
- name
- version
- schema_version
- active/status
- created_at

Уникальность:
`(key, version)`.

## program_days

- id
- program_id
- key
- name
- order

## program_exercises

- id
- program_day_id
- exercise_key
- exercise_name
- order

## prescribed_sets

Одна строка = один плановый подход конкретного athlete:

- id
- program_exercise_id
- athlete_id
- set_number
- reps_min
- reps_max
- target_rir nullable

## training_sessions

- id
- chat_id
- program_id
- program_day_id
- status
- current_exercise_order
- started_at
- finished_at nullable
- started_by_athlete_id

Statuses минимум:
- active
- completed
- aborted

## session_participants

- session_id
- athlete_id

## set_results

Одна строка = один фактически выполненный подход:

- id
- training_session_id
- program_exercise_id
- athlete_id
- planned_set_number nullable
- reps
- weight_kg
- subjective_rating nullable
- telegram_message_id nullable
- created_at

`weight_kg` не хранить float с ошибками округления.
Использовать подходящий decimal/numeric representation.

Результат подхода должен записываться в БД **сразу после сообщения пользователя**, а не только при завершении упражнения.

---

# 9. Состояние тренировки

Одна training session общая для группы/участников.

Текущее упражнение — общее.

Прогресс по подходам — индивидуальный для каждого athlete.

Пример допустимого состояния:

```text
Жим штанги лёжа

xRust -> следующий подход 3/4
Tim   -> следующий подход 2/4
```

Нельзя использовать одну глобальную переменную `current_set=2` на всех.

Состояние должно восстанавливаться из БД после рестарта контейнера.

In-memory FSM aiogram можно использовать только как вспомогательный UX-механизм, но **не как источник истины** для активной тренировки.

---

# 10. `/start_train`

Команда доступна привязанным участникам внутри allowed chat.

Если активной тренировки нет:

1. показать доступные дни активной программы inline-кнопками;
2. после выбора дня предложить выбрать участников из привязанных athletes, для которых есть prescription в этом дне;
3. создать training session;
4. установить первое упражнение;
5. вывести карточку упражнения.

Если уже есть active session:
- не создавать вторую;
- предложить продолжить текущую либо явно завершить/отменить её.

Для MVP в одной группе допускается максимум одна active training session.

---

# 11. Карточка упражнения

Карточка должна быть короткой.

Пример:

```text
🏋️ Жим штанги лёжа
Упражнение 1/6

xRust — подход 1/4
План: 8 повторов · RIR 3
Прошлый раз: 10×50 кг

Tim — подход 1/4
План: 10 повторов · RIR 3
Прошлый раз: 10×30 кг

Результат: повторы*вес
Например: 8*50
```

Не перегружать карточку историей.

---

# 12. Подсказка «прошлый раз»

Для athlete + exercise + planned_set_number искать самый свежий предыдущий `set_result` из более ранней training session.

Приоритет:

1. то же упражнение + тот же planned set number;
2. если такого нет — последний известный результат этого упражнения;
3. если истории нет — вывести `нет истории`.

Не пытаться автоматически рекомендовать новый вес в первой версии.

---

# 13. Парсер результата

Основной канонический формат:

```text
reps*weight
```

Примеры:

```text
8*50
10*32.5
6*70
```

Также разрешить необязательную субъективную оценку:

```text
8*50 легко
8*50 норм
8*50 тяжело
```

Хранить субъективную оценку отдельно:

```text
easy
normal
hard
```

Не превращать её в точное числовое значение RIR.

Плановый RIR берётся из программы.

Парсер должен принимать только сообщение, которое **целиком** соответствует формату.

Не пытаться извлекать `8*50` из обычной фразы.

Разрешить:
- `*`
- при желании эквиваленты `x`, `х`, `×`, если это не создаёт неоднозначности.

Но семантика всегда:

```text
REPS * WEIGHT_KG
```

Не поддерживать обратный формат `weight x reps`.

Поддержать decimal separator:
- `.`
- `,`

Нормализовать к decimal.

Добавить разумные sanity limits, но не делать спортивных предположений:
например отрицательные/нулевые значения запрещены, явно абсурдный ввод отклоняется понятным сообщением.

---

# 14. Обработка результата

Когда bound athlete пишет `8*50`:

Проверить:

1. сообщение из allowed chat;
2. есть active session;
3. athlete входит в participants;
4. есть current exercise;
5. у athlete есть незаписанный плановый подход для этого упражнения.

После этого:

1. определить следующий `planned_set_number` этого athlete;
2. сохранить set_result;
3. commit;
4. отправить короткое подтверждение;
5. показать этому athlete его следующий подход.

Пример:

```text
✓ xRust: 8×50 кг

Следующий подход 2/4
6–8 повторов · RIR 3
Прошлый раз: 8×55 кг
```

Если все плановые подходы athlete выполнены:

```text
✓ xRust: упражнение выполнено 4/4
```

Не переводить автоматически всю группу на следующее упражнение только потому, что один athlete закончил.

---

# 15. Навигация

Штатная навигация должна быть простой.

Реализовать минимум:

```text
/next
/choose
/skip
/finish_train
/undo
/status
```

## `/next`

Переводит active session на следующее плановое упражнение.

Если не все участники закончили текущее упражнение — вывести предупреждение и потребовать явного подтверждения inline-кнопкой.

## `/choose`

Показать список упражнений текущего дня и позволить перейти к выбранному.

Это escape hatch на случай:
- занят тренажёр;
- сломано оборудование;
- изменили порядок.

## `/skip`

Пометить текущее упражнение пропущенным для session и перейти дальше.

Не нужно пока собирать structured reason.

## `/finish_train`

Завершить session после подтверждения.

## `/undo`

Отменить последний `set_result` автора команды в текущей active session.

Не удалять молча:
- либо soft-delete/audit-friendly решение,
- либо физическое удаление с понятным логированием.

Выбери простейший вариант, но тестом гарантируй, что `/undo` затрагивает только последнюю запись конкретного athlete.

## `/status`

Показать:
- программу;
- день;
- текущее упражнение;
- прогресс каждого участника.

---

# 16. Что делать после последнего планового подхода

В первой версии НЕ нужен сложный workflow дополнительного подхода.

Если athlete выполнил все плановые подходы:
- сообщить `упражнение выполнено N/N`;
- дальнейший обычный `reps*weight` для этого athlete и упражнения не принимать автоматически;
- подсказать использовать дальнейшую навигацию.

Поддержку extra/unplanned sets оставить на следующую итерацию.

---

# 17. Безопасность и границы доступа

Обязательно:

- BOT_TOKEN только через env/secrets;
- `.env` в `.gitignore`;
- `.env.example` без секретов;
- owner id из env;
- destructive/config commands только owner;
- training inputs только allowed chat;
- результат принимается только от bound athlete;
- SQL только через ORM/параметризованные запросы;
- YAML импорт валидировать;
- ограничить размер импортируемого файла разумным небольшим лимитом;
- не логировать BOT_TOKEN;
- не логировать полный raw update без необходимости.

---

# 18. Docker

Нужен `Dockerfile` и `compose.yaml`.

Для MVP Compose должен содержать только bot service.

SQLite хранить в persistent bind mount или named volume.

Предпочтительный вариант структуры:

```text
./data/
  gymbot.sqlite3
```

В контейнере, например:

```text
/app/data/gymbot.sqlite3
```

Требования:

- без опубликованных портов;
- `restart: unless-stopped`;
- приложение запускается не от root;
- writable только data dir и необходимые runtime paths;
- по возможности `read_only: true`;
- `/tmp` через tmpfs при необходимости;
- `cap_drop: ALL`;
- `security_opt: no-new-privileges:true`;
- корректный graceful shutdown long polling;
- миграции должны выполняться явным и предсказуемым способом.

Не усложнять отдельным migration-container, если это не нужно.
Допустим entrypoint:

```text
alembic upgrade head && python -m app
```

если это реализовано безопасно и повторяемо.

---

# 19. Логи

Логировать в stdout/stderr.

Нужны структурно понятные записи минимум для:

- startup/shutdown;
- Telegram polling start/stop;
- setup group;
- bind/unbind;
- program import success/failure;
- training session start/finish;
- set result saved;
- navigation actions;
- rejected action с безопасной причиной.

Не логировать секреты.

Для MVP отдельные log files внутри контейнера не нужны — использовать Docker logging.

---

# 20. Надёжность

Важные свойства:

- рестарт контейнера не должен терять:
  - imported program;
  - bindings;
  - allowed chat;
  - active training session;
  - уже записанные set results;
  - current exercise;
- повторный запуск не должен создавать дубли schema/data;
- один Telegram update/message не должен случайно записать один подход дважды;
- использовать `telegram_message_id`/уникальность или иной простой механизм идемпотентности;
- отсутствие истории не считается ошибкой.

---

# 21. Тесты

Написать unit/integration tests минимум на:

## Parser

- `8*50`
- `10*32.5`
- `10*32,5`
- `8*50 легко`
- invalid text
- embedded value inside sentence must not parse
- zero/negative values reject

## Bindings

- athlete can self-bind with `/bind <athlete_key>`;
- self-bind always binds the command author only;
- bind works only in allowed chat;
- unknown athlete key rejects;
- occupied athlete rejects;
- already-bound Telegram user rejects;
- owner can inspect bindings;
- owner can recover from an incorrect binding;
- Telegram user unique;
- athlete unique.

## Program import

- valid YAML imports;
- invalid schema rejects atomically;
- duplicate program key/version does not silently overwrite;
- reps exact/range validation;
- unknown athlete in prescriptions rejects.

## Training state

- create session;
- independent set counters for xRust and Tim;
- xRust can be on set 3 while Tim remains on set 2;
- set result saved immediately;
- restart/reload state from DB;
- `/next` does not corrupt incomplete participant progress;
- `/undo` affects only author;
- `/finish_train` closes session.

## Access boundaries

- wrong chat ignored/rejected;
- unbound user cannot write result;
- bound non-participant cannot write result;
- no active session => `8*50` is not persisted.

---

# 22. README / runbook

Создай README с краткими инструкциями:

1. создать бота через BotFather;
2. получить token;
3. заполнить `.env`, включая `OWNER_TELEGRAM_ID`;
4. `docker compose build`;
5. `docker compose up -d`;
6. посмотреть логи;
7. добавить бота в тренировочную группу администратором с минимально необходимыми правами;
8. `/setup_group`;
9. импортировать пример программы;
10. xRust выполняет `/bind xrust`;
11. Tim выполняет `/bind tim`;
12. `/start_train`;
13. остановка/обновление/backup SQLite.

Добавь команды backup:

```bash
cp ...
```

но учитывай корректность копирования живой SQLite-БД.
Выбери безопасный способ и объясни его в README.

---

# 23. Рекомендуемая структура проекта

Не обязана совпадать буквально, но должна оставаться простой:

```text
.
├── app/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── bot.py
│   ├── handlers/
│   ├── db/
│   ├── models/
│   ├── services/
│   └── parsers/
├── migrations/
├── tests/
├── examples/
│   └── program.example.yaml
├── data/
│   └── .gitkeep
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── .env.example
├── .gitignore
└── README.md
```

Не создавать слои/абстракции только ради архитектурной красоты.

---

# 24. Checkpoints

## CP-01 — architecture + scaffold

- изучить текущее состояние repo;
- если repo пустой — создать минимальный scaffold;
- описать выбранную структуру;
- конфигурация;
- dependency management;
- тестовый каркас;
- Docker skeleton.

Не реализовывать весь бот до проверки базовой структуры.

## CP-02 — DB + migrations

- модели;
- первая Alembic migration;
- tests для constraints;
- SQLite persistent path;
- restore state after process restart.

## CP-03 — Telegram bootstrap + bindings

- long polling;
- `/setup_group`;
- owner restriction for configuration actions;
- self-service `/bind`;
- self-service `/unbind`;
- `/whoami`;
- owner `/bindings`;
- owner recovery command for incorrect binding;
- tests.

## CP-04 — program import

- YAML schema;
- validation;
- atomic import;
- sample program;
- tests.

## CP-05 — training core

- `/start_train`;
- day selection;
- participants;
- current exercise;
- independent participant set progress;
- parser `reps*weight`;
- immediate persistence;
- previous-set hint;
- tests.

## CP-06 — navigation + recovery

- `/next`;
- `/choose`;
- `/skip`;
- `/undo`;
- `/status`;
- `/finish_train`;
- active session recovery;
- idempotency;
- tests.

## CP-07 — Docker + operator documentation

- production-like container;
- Compose;
- security hardening without overengineering;
- README/runbook;
- clean build;
- full test suite;
- smoke test.

---

# 25. Acceptance criteria

Проект MVP считается готовым, если на чистой машине можно:

1. клонировать repo;
2. создать `.env`;
3. выполнить:

```bash
docker compose up -d --build
```

4. настроить группу;
5. импортировать example YAML;
6. каждый из двух Telegram users самостоятельно выполняет `/bind` и привязывается к `xrust` и `tim`;
7. запустить тренировку;
8. выбрать день и обоих участников;
9. получить первое упражнение;
10. xRust отправляет:

```text
8*50
```

11. Tim отправляет:

```text
10*30
```

12. бот корректно сохраняет разные результаты и ведёт независимые номера подходов;
13. `/next` переводит группу к следующему упражнению;
14. рестарт:

```bash
docker compose restart
```

не уничтожает состояние;
15. тренировка продолжается;
16. `/finish_train` завершает session;
17. все данные остаются в SQLite.

---

# 26. Главный критерий качества

Не количество функций.

Главный критерий:

> Во время обычной тренировки бот не мешает тренироваться.

Штатный цикл должен оставаться:

```text
посмотрел подсказку
→ сделал подход
→ написал 8*50
→ получил следующий подход
```

Всё остальное — только обслуживает этот цикл.

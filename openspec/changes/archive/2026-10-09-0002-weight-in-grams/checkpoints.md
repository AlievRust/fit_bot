# CP-08

## Состояние восстановления

- Режим STANDARD: ограниченное изменение представления данных, без делегирования.
- Состояние PASSED. Источник: текущий запрос пользователя; решение: design.md.
- Барьер: миграция и проверки до приёмки. Пользовательский gate NOT_REQUIRED.
- Независимое ревью NOT_REQUIRED; primary проверяет ограниченный diff и данные.
- Блокеров нет. Обязательных работ CP-08 не осталось.
- Runtime/production не изменяются.

## Приёмка

Baseline PASS: 31 тест. Узкая suite PASS: 49 тестов. Полная suite PASS: 75 тестов.
Compileall/diff check PASS; проверка модели Alembic PASS. Вердикт primary: PASSED.
Риски: миграция отклоняет старые веса, не представимые в текущих целых граммах;
это сохраняет исходные данные. Рабочая БД не изменялась; миграция проверена на тестовых БД.
Docker/Telegram повторно не запускались. Зависимости и упаковка не менялись.

Файлы: app/db/models.py, app/services/training.py,
migrations/versions/0002_weight_in_grams.py, tests/test_database.py,
tests/test_result_parser.py, tests/test_weight_storage.py,
examples/program.example.yaml, README.md и OpenSpec.
История CP-01–CP-07 остаётся в предыдущем архиве.

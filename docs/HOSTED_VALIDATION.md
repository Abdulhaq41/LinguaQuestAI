# Дополнительная проверка варианта Render

- Добавлены render.yaml, объединённый Dockerfile, startup script и ASGI factory с API и Mini App на одном origin.
- 8 новых тестов прошли: преобразование PostgreSQL URL, статические ресурсы/API и изоляция контента, отсутствие сборки, настройка ожидаемого username и отказ перенастроить другой бот. Настройка Telegram проверялась только с подменой транспорта.
- Общий backend-прогон: 67 passed, 2 PostgreSQL concurrency tests skipped, 1 Starlette/TestClient deprecation warning. Два concurrency-теста ранее проверялись отдельно с PostgreSQL; в новом общем прогоне TEST_POSTGRES_URL не задавался.
- Docker-образ успешно собран с проверкой TLS и хешей зависимостей.
- Изолированный Docker smoke на реальном PostgreSQL 17 прошёл: root frontend и SVG, синтетическая HMAC Telegram auth, Secure session cookie, onboarding, 6 ответов, score 100%, 50 XP в DB, отказ платного урока (402), закрытая оплата (503), отсутствие dev-auth (404), отсутствие доступа к JSON с ответами (404), удаление учебных данных.
- Реальный токен из переписки не использовался, не сохранялся в код или конфигурацию. Звонков Telegram API в smoke не было.
- Blueprint не применялся к аккаунту Render и не проверялся API платформы. Публичный URL не создан. HTTPS на стороне Render, реальный Telegram webhook и платежи ещё требуют проверки после действий владельца.
- Минимальный тестовый blueprint не запускает worker, AI и продажи. Подготовка этого файла не открывает коммерческий доступ.

# Проверки текущей версии

Дата: 5 ноября 2026, пользовательский часовой пояс Asia/Tashkent. Проверена текущая облачная машина; восстановление в новой задаче и публикация среды не выполнялись.

| Проверка | Фактический результат |
|---|---|
| `pytest` с TEST_POSTGRES_URL | **61 passed**, ни одного skipped, 1 deprecation warning библиотеки Starlette/TestClient |
| PostgreSQL concurrency внутри этого прогона | 2 passed: 6 доставок одного charge дают 1 payment; 4 завершения дают 50 XP суммарно |
| Playwright Chromium | **6 passed**: три сценария на mobile viewport iPhone 13 и desktop 1440×1000 |
| TypeScript + Vite production build | Passed |
| `scripts/setup.sh` | Выполнен: frozen install, Alembic, npm ci, build; имеющийся `.env` не перезаписывается |
| Миграции SQLite/PostgreSQL 17 | Применены до 0005; повторный upgrade проходит без удаления данных |
| API Dockerfile | Собран с проверкой TLS и dependency hashes; исправлены права для runtime UID 10001 |
| Web Dockerfile | Собран; Nginx отдаёт JS/CSS, логотип и PNG Lexi без 403 |
| Container functional smoke | Nginx → FastAPI → PostgreSQL: регистрация, настройки, 6 ответов, 100%, 50 XP, отказ 402 для платного урока, сохранение после перезапуска API, удаление данных |
| Compose | `docker compose config --quiet` проходит |
| Caddy | `caddy validate` проходит; это проверка конфигурации, не получение публичного TLS-сертификата |
| CI | Конфигурация GitHub Actions сохранена; удалённый workflow не запускался |

## Что именно проверяют тесты

- Telegram HMAC: верная подпись, подмена, устаревшая/future-дата, дублирующие поля, неверные данные. HTTP-auth действительно использует подписанный ID.
- Session: отсутствие доступа без cookie, logout отзывает серверный token hash, dev-auth закрыт при production, CSRF и admin-denial.
- Lesson: все вопросы, объяснения, запрет завершения без ответов, восстановление, идемпотентный answer, конфликт изменения ответа, изоляция пользователей, отсутствие ранней выдачи ключей и повторных XP.
- Billing: сумма/валюта/пользователь, уникальность charge, renewal/out-of-order, истечение, refund, два checkout-окна, неоткрытые продажи PRO, поздний overlap без доступа, отмена после возврата/истечения.
- Provider integration: invoice/cancel/refund проходят через настоящий adapter-код с **подменённым транспортом**, без денежных операций. Доступ выдаётся только после внутреннего synthetic verified event, не browser callback.
- AI: неподключённый провайдер, tier gate, квота, согласие, transport timeout, учёт токенов, кеш UUID и входная moderation-block. Ответы тестового транспорта синтетические; качество реального AI не установлено.
- Game: 25 достижений и однократные награды, SRS и повтор answer, ежедневная награда, недостаток монет/повторная покупка, реферальная оплата/возврат, LifeQuest tier/сюжетные последствия, удаление расширенных данных, приватность worker.
- Admin: права, цена/аудит, version-conflict, сохранение прежних ответов в начатом lesson snapshot.
- aiogram: реальный Dispatcher обрабатывает `/start`; Telegram transport подменён, проверяются caption и Mini App keyboard.
- Browser: регистрация/урок/paywall/server persistence; страницы/настройки/язык/тема/admin denial; словарь/достижения/ежедневная награда/assessment. Проверяется отсутствие pageerror в главном сценарии и горизонтального переполнения на домашнем экране.

## Что не проверено

Реальный Telegram initData из WebView, публичный webhook, настоящий Stars-платёж/renewal/refund, AI quality/ценовой счёт/живой moderation provider, голос, iOS/Android Telegram, screen-reader аудит, Lighthouse/нагрузочное тестирование, disaster recovery из offsite backup, независимый security-аудит, публикация snapshot и fresh-task restoration. Синтетический success не является свидетельством успешной реальной оплаты.

Одна из промежуточных проверок выявила гонку сохранения языка; исправлено блокировкой формы и очисткой старого success-status. Container smoke выявил недоступные UID 10001 файлы; исправлено COPY --chown. После исправлений затронутые проверки повторены. Предупреждение Starlette о будущем переходе TestClient на httpx2 не означает пропуск тестов.

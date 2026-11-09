# Развёртывание и BotFather

## Необходимые доступы

Собственный VPS с Docker/Compose, DNS-домен, открытые 80/443, Telegram-бот, ключ AI (если включается), поддержка. Развёртывание из этого задания наружу не выполнялось. Цена Stars не означает гарантированную сумму вывода.

1. Создайте бота в официальном BotFather: `/newbot`. Сохраните токен в secret manager или приватном `.env` на хосте; права файла 600. Укажите `BOT_USERNAME` без `@`.
2. Настройте Main Mini App в BotFather для этого бота: HTTPS URL вашего приложения. Это нужно для `?startapp=ref_…` и открытия приложения через профиль. Настройте Menu Button / `setmenubutton` на тот же HTTPS URL. Названия пунктов BotFather могут меняться.
3. Зарегистрируйте команды через `/setcommands`: start, app, profile, subscription, referral, settings, help, paysupport, privacy, terms. Все обработчики есть. Укажите описания на нужных языках.
4. Установите аватар бота из `assets/mascots/lexi-generated.png`. Это оригинальная графика проекта; квадратный SVG-логотип используйте в продукте. Не публикуйте ключ в ссылке или screenshot.
5. Создайте DNS A/AAAA-запись домена на сервер. Оставляйте только реально работающий IPv6. Caddy запросит публичный TLS-сертификат.
6. Скопируйте `.env.example` в `.env` и безопасно заполните:

| Переменная | Назначение |
|---|---|
| APP_ENV | production |
| ENABLE_DEV_AUTH | false, Compose принудительно отключает |
| DOMAIN | только имя домена |
| WEBAPP_URL | https://тот-же-домен, без пути |
| POSTGRES_PASSWORD | длинный случайный URL-safe пароль |
| DATABASE_URL | Compose задаёт соединение с PostgreSQL; для внешней БД нужен отдельный override |
| BOT_TOKEN | токен BotFather |
| BOT_USERNAME | имя бота без @ |
| WEBHOOK_SECRET | случайная строка 32+ символов A-Z/a-z/0-9/_/- |
| ADMIN_TELEGRAM_IDS | числовые ID администраторов через запятую, не username |
| SUPPORT_CONTACT | работающий контакт поддержки |
| AI_API_KEY | приватный ключ OpenAI |
| AI_ENABLED | false до live-проверок; true только после подключения |
| AI_MODEL | доступная модель, по умолчанию gpt-4.1-mini |
| AI_DAILY_TOKEN_BUDGET | бюджет учтённых токенов приложения |
| AI_INPUT_USD_PER_MILLION / AI_OUTPUT_USD_PER_MILLION | текущие оценочные цены модели |
| COMMERCE_ENABLED | false до юридической проверки и реальных испытаний оплаты |

Redis в этой версии не используется и REDIS_URL не нужен.

7. Запустите `docker compose up --build -d`. Сначала готовится PostgreSQL, затем `migrate`, API, worker, web, Caddy. Bot handlers работают через API webhook; отдельный polling не запускайте одновременно.
8. Из корня репозитория с заполненной конфигурацией зарегистрируйте webhook: `docker compose exec api python -m scripts.register_webhook`. Скрипт использует переменные, не печатает URL с токеном, сохраняет pending updates. URL — WEBAPP_URL + `/api/telegram/webhook`, проверяется `X-Telegram-Bot-Api-Secret-Token`.
9. Проверьте `/api/health` через ваш HTTPS-домен, затем `/start`, кнопку Mini App и авторизацию в реальном Telegram. Внешнее API не должно иметь открытого порта 8000: Compose не публикует его.
10. Проверьте юридические документы, контакт поддержки и нужные возрастные ограничения. Локальная UI-копия условий в `main.tsx` тоже должна соответствовать утверждённым документам. Только затем открывайте START-продажи.

## Stars и сценарии приёмки

Цены: START 89, PRO 149, ULTRA 299 XTR, период `2592000` секунд. PRO/ULTRA принудительно не продаются, пока обещанный голос не готов. Админ может менять цену новых счетов через `PATCH /api/admin/plans/{id}`. Старые инвойсы и recurring-подписки сохраняют прежнюю цену.

`createInvoiceLink` создаёт счёт без provider token. Pre-checkout сверяет пользователя, валюту и сумму. Successful payment обрабатывается только серверным aiogram handler после webhook-secret проверки; browser paid callback — повод перечитать серверный профиль. Charge ID уникален. Одна активная подписка не допускает новый checkout; при запоздалом перекрывающемся платеже доступ не выдаётся и запускается возврат.

До коммерческого использования проверьте в поддерживаемом Telegram payment-test окружении и затем владельцем в реальной среде: первый платёж, отказ, повтор update, два окна, продление, отмена через initial charge ID, истечение, refund webhook, перезапуск и сверка выписки. **Эти реальные проверки ещё не выполнены.** Возвраты через админку совершают настоящее внешнее действие; нужны подтверждение в UI и права администратора. Нет автоматического prorating; смена после текущего периода.

## TLS/Proxy для сборки в managed cloud

Обычный сервер использует доверенные публичные CA. Облачная среда с session proxy требует передачу текущего объединённого CA bundle через BuildKit secret:

```bash
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f infrastructure/docker-api.Dockerfile -t linguaquest-api .
docker build --secret id=proxy_ca,src=/etc/ssl/certs/ca-certificates.crt -f infrastructure/docker-web.Dockerfile -t linguaquest-web .
```

Не отключайте TLS/signature/hash-проверки. В runtime облачного контейнера, обращающегося к внешним API, смонтируйте текущий CA bundle read-only и задайте `SSL_CERT_FILE` для httpx; для aiogram/aiohttp используйте системный доверенный CA согласно инфраструктуре. Не сохраняйте session CA в образ. Прокси должен быть доступен контейнеру по адресу, заданному платформой. Нельзя обходить запрет доменов прямым соединением.

## Бэкапы, логи и обновление

- `BACKUP_DIR=/private/backups bash scripts/backup.sh`: сжатый pg_dump, права 600/700, проверка gzip, `pipefail`. Установите cron отдельно; храните шифрованную offsite-копию и проверяйте восстановление.
- Для проверки восстановления используйте отдельную БД: `gunzip -c <backup> | psql <отдельное-соединение>`. Не направляйте restore в рабочую БД без согласованного плана.
- Миграции только вперёд; destructive downgrade запрещён. Перед обновлением — backup и проверка новой версии на staging.
- `docker compose logs --tail=100 api worker web caddy`: не публикуйте логи с персональными данными. Caddy фильтрует webhook-secret, cookies и Authorization; backend HTTP access log отключён в образе.
- Зафиксируйте digest Docker base images перед production-релизом и настройте регулярное обновление безопасности. Скрипты не заменяют мониторинг и on-call.
- Начальная конфигурация — один API-процесс и один worker. Для масштабирования нужны распределённые лимиты, очередь AI с резервированием квот, метрики задержек, PostgreSQL pool и отдельное хранилище статических ресурсов.

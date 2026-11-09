# API

Исчерпывающая OpenAPI-схема создаётся FastAPI по `/openapi.json`; interactive docs `/docs` непосредственно на API-порту. Публичный Nginx проксирует только `/api/`, поэтому служебные docs не открыты снаружи по умолчанию.

| Группа | Маршруты |
|---|---|
| Auth | POST /api/auth/telegram {init_data}; POST /api/auth/logout; dev-only POST /api/auth/dev |
| Account | GET /api/users/me; PATCH /api/users/me/settings; GET /api/users/me/export; DELETE /api/users/me |
| Learning | GET /api/learning-path; POST /api/lessons/{id}/start; POST /api/attempts/{id}/answer {index,value}; POST /api/attempts/{id}/complete |
| Assessment | GET/POST /api/assessment, submission {answers:[…]} |
| Vocabulary | GET /api/vocabulary; POST /api/vocabulary/review/start; POST /api/vocabulary/review/{id} {answer} |
| Game | GET /api/achievements; GET /api/daily-quest; POST /api/daily-quest/claim; GET /api/shop; POST /api/shop/{id}; GET /api/leaderboard |
| Subscription | GET /api/subscription/plans; POST /api/subscription/checkout {plan}; GET /api/subscription/history; POST /api/subscription/cancel |
| AI | GET /api/ai/history; POST /api/ai/tutor {request_id:UUID,message} |
| Referrals | GET /api/referrals/me |
| Analytics | POST /api/events {kind,plan?}, только app_opened/paywall_viewed/plan_selected |
| Admin | GET /api/admin/dashboard; GET /api/admin/payments; PATCH /api/admin/plans/{id} {stars}; POST /api/admin/refund {charge_id}; GET /api/admin/lessons; PUT /api/admin/lessons/{id} {expected_version,content} |
| Telegram | POST /api/telegram/webhook, только secret header, не cookie |
| Operations | GET /api/health; GET /api/config |

Приватные маршруты используют cookie `lq_session`. Сырые Telegram ID из браузера не авторизуют. В mutating-запросах используется тот же origin, что WEBAPP_URL. Вручную изменить XP/тариф/достижение нельзя. Errors: 401 сессия, 402 нужна подписка, 403 права/тариф/источник, 409 конфликт/неполный урок, 422 данные/небезопасная тема, 429 лимит, 502 внешний провайдер, 503 функция не подключена.

Правильные ответы не выдаются до отправки ответа на конкретный вопрос. Повтор отправки того же ответа идемпотентен; другой ответ на уже сохранённый индекс — 409. XP за идентификатор урока начисляются один раз при результате >=70%. Повторные уроки остаются доступны без дополнительной платы в рамках соответствующего доступа.

Платёжных browser-endpoints вида «активировать тариф» нет. Только authenticated Telegram webhook может записать подтверждённый charge. Тесты вызывают внутренний payment service с синтетическими событиями — это не публичный маршрут.

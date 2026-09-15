# panel

Управляет флотом AmneziaWG-нод и справочником OpenWrt/Keenetic роутеров. См. `docs/architecture.md` для общей схемы.

## Установка

```bash
sudo ./install.sh
```

См. `docs/deployment.md` для полного описания того, что делает скрипт, и как поставить перед панелью reverse-proxy с TLS.

## Локальная разработка (без Docker)

```bash
pip install -r requirements.txt
export DATABASE_URL="sqlite+aiosqlite:///./dev.db"
export JWT_SECRET="$(openssl rand -hex 32)"
export REDIS_URL="redis://localhost:6379/0"
export APP_ENV="development"

uvicorn src.main:app --reload --port 8000
```

SQLite годится для разработки интерфейса и логики без реального Postgres, но **не используйте её в проде** — Alembic-миграция написана под postgres-специфичные типы (`JSONB`, `ENUM`), и часть корректности (реальные constraint'ы, каскады) проверяется по-настоящему только на Postgres.

Создать первого админа в dev-режиме:
```bash
python3 scripts/create_admin.py
```

## Тесты

```bash
pytest tests/ -v
```

Тесты используют изолированный in-memory SQLite (см. `tests/conftest.py`) — не трогают ваш реальный `DATABASE_URL`, даже если он экспортирован в окружении.

## Debugging

**Логи с request-id**, как и у node-agent — каждый запрос помечен коротким id, можно грепать всю цепочку:
```bash
docker compose logs -f panel | grep a1b2c3d4
```

**Включить подробное логирование** без пересборки:
```bash
# в .env
LOG_LEVEL=DEBUG
```
```bash
docker compose up -d panel
```
На DEBUG видно SQL-запросы (через `sqlalchemy.engine`) и все вызовы к node-agent (через `httpx`).

**Частая проблема: "Node agent error: All connection attempts failed"**

Значит панель не может достучаться до agent'а на указанном `hostname:agent_port`. Проверьте:
```bash
# с сервера панели
curl -v http://<node-hostname>:<agent_port>/health
```
Если не отвечает — скорее всего, файрвол на ноде не пускает IP панели, или agent не поднялся (см. `node-agent/README.md`).

**Частая проблема: конфиг пира недоступен для повторного скачивания**

Это ожидаемое поведение после истечения TTL (48ч по умолчанию) — приватный ключ клиента никогда не хранился в Postgres, только в Redis с TTL. Единственный выход — создать нового пира. Проверить, жив ли ещё кэш:
```bash
docker compose exec redis redis-cli GET "config:<peer_id>"
docker compose exec redis redis-cli TTL "config:<peer_id>"
```

**Проверить состояние миграций:**
```bash
docker compose exec panel alembic current
docker compose exec panel alembic history
```

**Зайти в БД напрямую:**
```bash
docker compose exec postgres psql -U awgrt -d awgrt
```

## Безопасность (прочитать перед изменением auth/security.py или peer_service.py)

- `JWT_SECRET` защищает и Bearer-токены, и cookie-сессии — при компрометации нужно сгенерировать новый и перезапустить панель (это разлогинит всех админов, это ожидаемо)
- Приватные ключи клиентов **никогда** не попадают в Postgres — см. `docs/architecture.md`. Не добавляйте поле для их хранения без пересмотра всей модели безопасности
- Ошибка логина одинакова для "нет такого пользователя" и "неверный пароль" — не разделяйте эти случаи, это защита от enumeration

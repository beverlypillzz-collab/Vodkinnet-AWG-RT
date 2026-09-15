# Vodkinnet AWG-RT

Панель управления флотом AmneziaWG-нод и справочником OpenWrt/Keenetic роутеров VodkinNET — по образу Remnawave, но под AmneziaWG 2.0 и клиентские роутеры вместо серверных Xray-нод.

## Структура репозитория

```
panel/           — панель управления (FastAPI + Postgres + Redis + Jinja2/HTMX)
node-agent/      — агент на каждой AWG-ноде (FastAPI + docker-py)
docs/            — архитектура, API-контракт, схема БД, деплой
```

## Быстрый старт

**Панель** (один раз, на главном сервере) — скопировать и выполнить целиком:
```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/beverlypillzz-collab/Vodkinnet-AWG-RT.git && cd Vodkinnet-AWG-RT && git sparse-checkout set panel && cd panel && sudo ./install.sh && cd ../.. && rm -rf Vodkinnet-AWG-RT
```

**Каждая нода** (на каждом AWG-сервере) — скопировать и выполнить целиком:
```bash
git clone --filter=blob:none --sparse --depth 1 https://github.com/beverlypillzz-collab/Vodkinnet-AWG-RT.git && cd Vodkinnet-AWG-RT && git sparse-checkout set node-agent && cd node-agent && sudo ./install.sh && cd ../.. && rm -rf Vodkinnet-AWG-RT
```

Панель и каждая нода ставятся под отдельными сервисными аккаунтами (не под root) — `/opt/vodkinnet-awg-rt` и `/opt/vodkinnet-awg-agent` соответственно; подробности и честная оценка границ этой изоляции в `docs/deployment.md`. Каждая команда клонирует только нужную папку (не весь репозиторий), ставит Docker при необходимости, генерирует секреты и поднимает контейнеры — без ручных промежуточных шагов. Полная инструкция — `docs/deployment.md`.

## Почему AmneziaWG 2.0

OpenWrt и Keenetic/Netcraze пока не поддерживают протокол AmneziaWG 3.1 нативно — официальное приложение Amnezia, требующее 3.1, не работает с этими роутерами. Подробности и источники — `docs/deployment.md`.

## Документация

- [`docs/architecture.md`](docs/architecture.md) — общая схема, модель хранения ключей, мониторинг
- [`docs/api-contract.md`](docs/api-contract.md) — API между панелью и node-agent
- [`docs/db-schema.md`](docs/db-schema.md) — схема БД с пояснениями
- [`docs/deployment.md`](docs/deployment.md) — установка и эксплуатация
- [`panel/README.md`](panel/README.md) — дебаг и разработка панели
- [`node-agent/README.md`](node-agent/README.md) — дебаг и разработка агента

## Безопасность

Прежде чем менять что-то в `node-agent/src/docker_control/`, `node-agent/src/wg/`, или `panel/src/services/peer_service.py` — прочитайте раздел "Security notes" в соответствующем README. Ключевые принципы:

- Приватный ключ ноды никогда не покидает саму ноду
- Приватный ключ клиента транзитом через панель, кэш в Redis с TTL 48ч, никогда не в Postgres
- `AWG_CONTAINER_NAME` на агенте зашит при деплое, никогда не принимается из API-запроса

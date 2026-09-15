# API-контракт: панель ↔ node-agent

Полная спецификация того, что панель вызывает на каждой ноде. Все эндпоинты, кроме `/health`, требуют:

```
Authorization: Bearer {agent_token}
```

## `GET /health`

Без авторизации — используется для базового uptime-мониторинга, не раскрывает чувствительных данных.

```json
{
  "status": "ok",
  "agent_version": "1.0.0",
  "awg_container_running": true
}
```

## `POST /server/init`

Идемпотентен: если интерфейс уже поднят, возвращает существующий публичный ключ вместо генерации нового (иначе это сломало бы всех уже подключённых клиентов).

**Запрос:**
```json
{
  "listen_port": 55632,
  "awg_params": { "Jc": 4, "Jmin": 40, "Jmax": 70 }
}
```

**Ответ 200:**
```json
{ "public_key": "AbCdEf...=", "listen_port": 55632, "interface": "awg0" }
```

## `GET /server/status`

**Ответ 200:**
```json
{
  "interface_up": true,
  "public_key": "AbCdEf...=",
  "listen_port": 55632,
  "peers": [
    {
      "public_key": "XyZ...=",
      "endpoint": "203.0.113.5:41234",
      "allowed_ips": "10.8.0.7/32",
      "last_handshake": "2026-09-14T20:15:32+00:00",
      "rx_bytes": 184320,
      "tx_bytes": 92160
    }
  ]
}
```

**Ответ 503**, если контейнер `amnezia-awg2` недоступен на этой ноде.

## `POST /peers`

**Запрос:**
```json
{ "allowed_ips": "10.8.0.7/32", "awg_overrides": {} }
```

**Ответ 201:**
```json
{
  "public_key": "NewPub...=",
  "private_key": "NewPriv...=",
  "config_file": "[Interface]\nPrivateKey = ...\n..."
}
```

`config_file` может содержать плейсхолдер `__NEEDS_PANEL_SUBSTITUTION__` вместо хоста в `Endpoint =`, если на ноде не задан `AWG_PUBLIC_ENDPOINT`. Панель обязана подставить туда `nodes.hostname` перед выдачей конфига пользователю — см. `peer_service.create_peer`.

**Важно:** `private_key` и `config_file` — панель НЕ пишет их в Postgres, только в Redis с TTL. См. `docs/architecture.md`.

## `DELETE /peers/{public_key}`

**Ответ 200:** `{ "removed": true }`
**Ответ 404:** пир не найден на этой ноде.

## `PATCH /peers/{public_key}`

**Запрос:** `{ "allowed_ips": "10.8.0.7/32" }`
**Ответ 200:** `{ "updated": true }`

Примечание: `awg_overrides` на уровне отдельного пира принимается схемой API для совместимости с будущими версиями протокола, но текущая реализация AmneziaWG применяет параметры обфускации на уровне интерфейса целиком, не для отдельных пиров — переопределение пока не имеет эффекта.

## Формат ошибок

```json
{ "error": "peer_not_found", "message": "No peer with this public key on this node" }
```

Коды: `400` (некорректный запрос), `401` (неверный токен), `404`, `500`, `503` (нода/контейнер недоступны).

## Персистентность на ноде

`awg set` меняет интерфейс "на лету", но не переживает рестарт контейнера сам по себе. После каждого `add_peer`/`remove_peer`/`update_peer` агент **пересобирает** `/opt/amnezia/awg/awg0.conf` целиком из текущего состояния интерфейса (`wg show dump`) и применяет через `awg syncconf` — так что рестарт контейнера не роняет уже созданных пиров. См. `node-agent/src/wg/config_builder.py`.

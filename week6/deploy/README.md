# День 30 — деплой приватного питомца на VPS

Сервис держит локальную LLM (`qwen2.5:1.5b-instruct` через Ollama) за FastAPI,
раздаёт веб-чат и HTTP API. Работает 24/7 на VPS — ноут не нужен.

## Что нужно
- VPS Ubuntu 22.04/24.04, минимум **4 GB RAM**, 2 vCPU, 20+ GB диска.
- Открытый порт 80 (в панели провайдера / firewall).

## Установка (на VPS, из-под пользователя с sudo)
```bash
sudo mkdir -p /opt/advent && sudo chown "$USER" /opt/advent
git clone <URL-репозитория> /opt/advent
cd /opt/advent
bash week6/deploy/install.sh
```
Скрипт: ставит Ollama + модель, поднимает `pet.service` (systemd, автозапуск после
ребута) и nginx на 80 порт с rate-limit.

## Проверка
```bash
curl http://<IP-сервера>/pet
curl -X POST http://<IP-сервера>/chat -H 'Content-Type: application/json' -d '{"message":"привет"}'
```
В браузере: `http://<IP-сервера>/` — веб-чат с питомцем.

## Ограничения (защита CPU при публичном доступе)
- **Приложение:** rate limit по IP (token-bucket), глобальный потолок, макс. длина ввода
  500 символов, окно истории 6 сообщений, `num_ctx=2048`, `num_predict=220`.
- **nginx:** `limit_req` 30 req/min на IP, `client_max_body_size 8k`.
- Только одна генерация одновременно (семафор) — CPU не захлёбывается при N запросах.

## Управление
```bash
sudo systemctl status pet
sudo journalctl -u pet -f
sudo systemctl restart pet
```

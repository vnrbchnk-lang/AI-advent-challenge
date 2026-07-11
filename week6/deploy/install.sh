#!/usr/bin/env bash
set -euo pipefail

MODEL="qwen2.5:1.5b-instruct"
REPO_DIR="${REPO_DIR:-/opt/advent}"
APP_USER="${APP_USER:-$(whoami)}"
SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

echo "[1/7] Пакеты системы"
$SUDO apt-get update -y
$SUDO apt-get install -y python3-venv python3-pip nginx git curl

echo "[2/7] Установка Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
$SUDO systemctl enable --now ollama

echo "[3/7] Загрузка модели ${MODEL}"
ollama pull "${MODEL}"

echo "[4/7] Python-окружение и пакет"
cd "${REPO_DIR}"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e week6

echo "[5/7] systemd-сервис питомца"
$SUDO tee /etc/systemd/system/pet.service >/dev/null <<UNIT
[Unit]
Description=Advent day30 local LLM pet service
After=network.target ollama.service
Wants=ollama.service

[Service]
User=${APP_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/.venv/bin/agent30
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now pet.service

echo "[6/7] Cloudflare-туннель (публичный URL в обход блокировки входящих)"
if ! command -v cloudflared >/dev/null 2>&1; then
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /usr/local/bin/cloudflared
  chmod +x /usr/local/bin/cloudflared
fi
$SUDO cp "${REPO_DIR}/week6/deploy/tunnel.sh" /usr/local/bin/pet-tunnel.sh
$SUDO chmod +x /usr/local/bin/pet-tunnel.sh
$SUDO tee /etc/systemd/system/pettunnel.service >/dev/null <<UNIT
[Unit]
Description=Cloudflare quick tunnel for pet service
After=network.target pet.service
Wants=pet.service

[Service]
ExecStart=/usr/local/bin/pet-tunnel.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
$SUDO systemctl daemon-reload
$SUDO systemctl enable --now pettunnel.service

echo "[7/7] nginx на 80 порт (локально, необязательно)"
$SUDO cp "${REPO_DIR}/week6/deploy/nginx.conf" /etc/nginx/sites-available/pet || true
$SUDO ln -sf /etc/nginx/sites-available/pet /etc/nginx/sites-enabled/pet || true
$SUDO rm -f /etc/nginx/sites-enabled/default || true
$SUDO nginx -t && $SUDO systemctl restart nginx || true

echo
echo "Готово. Публичный адрес питомца появится через ~15 секунд в файле:"
echo "    /root/PET-URL.txt"
sleep 18
echo "URL: $(cat /root/PET-URL.txt 2>/dev/null || echo '(ещё создаётся, проверь файл /root/PET-URL.txt)')"

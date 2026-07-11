#!/usr/bin/env bash
set -euo pipefail

MODEL="qwen2.5:1.5b-instruct"
REPO_DIR="${REPO_DIR:-/opt/advent}"
APP_USER="${APP_USER:-$(whoami)}"

echo "[1/6] Пакеты системы"
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip nginx git curl

echo "[2/6] Установка Ollama"
if ! command -v ollama >/dev/null 2>&1; then
  curl -fsSL https://ollama.com/install.sh | sh
fi
sudo systemctl enable --now ollama

echo "[3/6] Загрузка модели ${MODEL}"
ollama pull "${MODEL}"

echo "[4/6] Python-окружение и пакет"
cd "${REPO_DIR}"
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -e week6

echo "[5/6] systemd-сервис питомца"
sudo tee /etc/systemd/system/pet.service >/dev/null <<UNIT
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
sudo systemctl daemon-reload
sudo systemctl enable --now pet.service

echo "[6/6] nginx на 80 порт"
sudo cp "${REPO_DIR}/week6/deploy/nginx.conf" /etc/nginx/sites-available/pet
sudo ln -sf /etc/nginx/sites-available/pet /etc/nginx/sites-enabled/pet
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "Готово. Открой http://<IP-сервера>/"

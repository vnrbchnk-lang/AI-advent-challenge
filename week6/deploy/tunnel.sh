#!/usr/bin/env bash
URLFILE=/root/PET-URL.txt
: > "$URLFILE"
/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8000 2>&1 | while IFS= read -r line; do
  echo "$line"
  u=$(printf '%s' "$line" | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | head -1)
  [ -n "$u" ] && printf '%s\n' "$u" > "$URLFILE"
done

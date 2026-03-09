#!/bin/sh
set -e

export DISPLAY=:99
export PROFILES_DIR=/profiles

echo "Starting CDP Chrome Pro..."
echo "Profiles directory: $PROFILES_DIR"

# 创建 profiles 目录
mkdir -p "$PROFILES_DIR"

# 清理锁文件
rm -f /tmp/.X99-lock || true
rm -f "$PROFILES_DIR"/*/SingletonLock "$PROFILES_DIR"/*/SingletonSocket "$PROFILES_DIR"/*/SingletonCookie || true

# Xvfb 虚拟显示
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1440x900x24 -ac -nolisten tcp &
sleep 2

# x11vnc
echo "Starting x11vnc..."
x11vnc -display :99 -forever -shared -nopw -rfbport 5900 &
sleep 1

# noVNC
echo "Starting noVNC on port 6080..."
websockify --web /usr/share/novnc 6080 localhost:5900 &
sleep 1

# socat CDP 转发
echo "Starting CDP proxy on port 9333..."
socat TCP-LISTEN:9333,fork,reuseaddr TCP:127.0.0.1:9222 &
sleep 1

# Context Manager API
echo "Starting Context Manager API on port 8000..."
python3 /opt/context-manager.py &
sleep 2

# Chrome
echo "Starting Chromium..."
exec chromium-browser \
  --no-sandbox \
  --disable-dev-shm-usage \
  --disable-gpu \
  --disable-blink-features=AutomationControlled \
  --remote-debugging-port=9222 \
  --remote-debugging-address=127.0.0.1 \
  --user-data-dir="$PROFILES_DIR/default" \
  --no-first-run \
  --window-size=1366,900 \
  about:blank
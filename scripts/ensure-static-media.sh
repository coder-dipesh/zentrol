#!/usr/bin/env sh
# Unpack demo slide PNGs + logos from static/media.zip when missing (safe to run multiple times).
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/static"
if [ ! -f media/slides/1.png ] && [ -f media.zip ]; then
  echo "Zentrol: extracting static/media from media.zip (slides + logo)…"
  unzip -o -q media.zip 'media/slides/*.png' 'media/logo/*.svg' || true
fi

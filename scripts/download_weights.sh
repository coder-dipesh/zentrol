#!/usr/bin/env bash
# Download pre-trained Lip2Speech weights (265 MB) from the official source.
#
# Reference: https://github.com/Chris10M/Lip2Speech
# Weights: https://www.mediafire.com/file/evktjxytts2t72c/lip2speech_final.pth/file
#
# Usage:
#   bash scripts/download_weights.sh
#
# The file is placed at lip2speech/weights/lip2speech_final.pth, which is the
# default path the inference pipeline looks for.  No .env change is needed.

set -euo pipefail

DEST="lip2speech/weights/lip2speech_final.pth"
EXPECTED_SIZE=277940167  # bytes (265 MB)

# MediaFire direct-download URL (resolved from the public share link)
MEDIAFIRE_URL="https://download2390.mediafire.com/evktjxytts2t72c/lip2speech_final.pth"

cd "$(dirname "$0")/.."

if [[ -f "$DEST" ]]; then
    actual=$(wc -c < "$DEST" | tr -d ' ')
    if [[ "$actual" -ge "$EXPECTED_SIZE" ]]; then
        echo "Weights already present at $DEST ($actual bytes). Nothing to do."
        exit 0
    fi
    echo "Existing file looks truncated ($actual bytes). Re-downloading…"
fi

mkdir -p "$(dirname "$DEST")"

echo "Downloading Lip2Speech weights to $DEST …"
echo "(265 MB — this may take a minute)"

if command -v curl &>/dev/null; then
    curl -L --progress-bar -o "$DEST" "$MEDIAFIRE_URL"
elif command -v wget &>/dev/null; then
    wget -q --show-progress -O "$DEST" "$MEDIAFIRE_URL"
else
    echo "Error: neither curl nor wget found. Install one and retry." >&2
    exit 1
fi

actual=$(wc -c < "$DEST" | tr -d ' ')
echo "Downloaded $actual bytes."

if [[ "$actual" -lt "$EXPECTED_SIZE" ]]; then
    echo "Warning: file is smaller than expected ($EXPECTED_SIZE bytes)." >&2
    echo "MediaFire may require a browser download. Visit:" >&2
    echo "  https://www.mediafire.com/file/evktjxytts2t72c/lip2speech_final.pth/file" >&2
    exit 1
fi

echo "Done. Weights ready at: $DEST"

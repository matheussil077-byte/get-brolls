#!/usr/bin/env bash
# Shared yt-dlp runtime for the Vedana B-Rolls YouTube helpers.
GB_RUNTIME_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
gb_ytdlp() {
  local exe="yt-dlp"
  if [ -x "$GB_RUNTIME_ROOT/.venv/bin/yt-dlp" ]; then exe="$GB_RUNTIME_ROOT/.venv/bin/yt-dlp"
  # Git Bash no Windows: a venv do install.ps1 usa Scripts\yt-dlp.exe.
  elif [ -f "$GB_RUNTIME_ROOT/.venv/Scripts/yt-dlp.exe" ]; then exe="$GB_RUNTIME_ROOT/.venv/Scripts/yt-dlp.exe"; fi
  if command -v deno >/dev/null 2>&1; then
    "$exe" --js-runtimes deno "$@"
  elif command -v node >/dev/null 2>&1; then
    "$exe" --js-runtimes node "$@"
  else
    "$exe" "$@"
  fi
}

#!/bin/sh
# Create the swapfile at $SWAPFILE_PATH (no-op when that variable is unset).
#
# Size is $SWAP_SIZE_MB mebibytes, default 384 (#1337). Set it in the
# container environment (fly.toml [env]); a Docker build ARG is not visible
# to this shell.
#
# fallocate -l does not shrink. The volume persists across boots and already
# holds a 768M swapfile, so a smaller request has to unlink that file first.
# A request over 512M (half of the 1GB volume) warns and still proceeds.
set -eu

if [ -z "${SWAPFILE_PATH:-}" ]; then
  exit 0
fi

# Unset means the image default. A blank value is a misconfiguration, not 384.
if [ -z "${SWAP_SIZE_MB+x}" ]; then
  mb=384
else
  mb=$SWAP_SIZE_MB
fi
case "$mb" in
  *[!0-9]*)
    echo "SWAP_SIZE_MB must be a positive integer (megabytes), got: ${mb}" >&2
    exit 1
    ;;
esac
# A leading zero is octal in $(( )), and dash rejects digits above 7.
mb=$(printf '%s' "$mb" | sed 's/^0*//')
if [ -z "$mb" ]; then
  echo "SWAP_SIZE_MB must be a positive integer (megabytes)" >&2
  exit 1
fi

if [ "$mb" -gt 512 ]; then
  echo "WARNING: SWAP_SIZE_MB=$mb is over half of a 1GB volume; see #1337" >&2
fi

mkdir -p "$(dirname "$SWAPFILE_PATH")"
# Unlink does not free blocks while the kernel still has the file swapped on.
swapoff "$SWAPFILE_PATH" 2>/dev/null || true

desired=$((mb * 1024 * 1024))
current=0
if [ -f "$SWAPFILE_PATH" ]; then
  current=$(stat -c %s "$SWAPFILE_PATH")
fi
if [ "$current" != "$desired" ]; then
  rm -f "$SWAPFILE_PATH"
  fallocate -l "${mb}M" "$SWAPFILE_PATH"
fi
chmod 600 "$SWAPFILE_PATH"
mkswap "$SWAPFILE_PATH"
swapon "$SWAPFILE_PATH"

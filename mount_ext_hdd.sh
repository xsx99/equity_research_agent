#!/usr/bin/env bash
set -euo pipefail

UUID="ADD YOUR UUID HERE"
MOUNTPOINT="/data"

sudo mkdir -p "$MOUNTPOINT"

# Add fstab entry if missing
if ! grep -q "$UUID" /etc/fstab; then
  echo "UUID=$UUID $MOUNTPOINT ext4 defaults,noatime 0 2" | sudo tee -a /etc/fstab >/dev/null
fi

# Mount now
sudo mount -a

# Ensure Postgres data directory exists on the mounted drive
sudo mkdir -p "$MOUNTPOINT/postgres_data"

# Verify
df -h | grep "$MOUNTPOINT" || true

---
name: inky-ssh
description: SSH access to the InkyPi Raspberry Pi (pi@192.168.18.24, hostname inky-pizero2w.local). Use for any Pi access — reading files, checking logs, inspecting services, running diagnostics, or deploying code to the Pi.
---

# InkyPi SSH

General-purpose SSH access to the InkyPi at `pi@192.168.18.24` (hostname `inky-pizero2w.local`). Use this skill for any Pi access: reading files, checking logs, inspecting services, running diagnostics, or deploying code.

## Safety rule
**NEVER run write, delete, or destructive commands** (file writes, rm, mv, systemctl stop/restart, git restore, pip install, etc.) **without first describing the command to the user and getting explicit approval.** Read-only commands (ls, cat, journalctl, systemctl status, git log, ps, df, etc.) may run freely.

## SSH connection
Always use IP directly with keepalive options to prevent hangs that block remote control sessions. Authenticate with the dedicated `pi_inky` key:
```
ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o IdentitiesOnly=yes -i ~/.ssh/pi_inky pi@192.168.18.24 "<command>"
```
**Never omit `ServerAliveInterval` and `ServerAliveCountMax`** — `ConnectTimeout` only covers the initial handshake; without keepalives, commands like `git pull` can hang indefinitely.

If the IP has changed (e.g. new router), rediscover it via mDNS: `getent hosts inky-pizero2w.local` (hostname stays `Inky-PiZero2W`).

## Deploy to Pi
When asked to deploy the current branch:
1. Confirm with the user before running (this is a write operation).
2. **Check for pending local changes** (`git status`). If there are uncommitted changes, commit them first. If the branch is ahead of remote, push it.
3. Run restore and pull: `ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o IdentitiesOnly=yes -i ~/.ssh/pi_inky pi@192.168.18.24 "cd /home/pi/InkyPi && git restore . && git pull 2>&1"`
4. Restart the service: `ssh -o ConnectTimeout=30 -o ServerAliveInterval=10 -o ServerAliveCountMax=3 -o IdentitiesOnly=yes -i ~/.ssh/pi_inky pi@192.168.18.24 "sudo systemctl restart inkypi.service && echo restarted"`
5. Report what files changed and confirm the service restarted.

## Battery reset
Script: `/home/pi/Documents/set_full_charge.py`
**Only run this when the user explicitly asks.** Command: `python3 /home/pi/Documents/set_full_charge.py`

## Common tasks
- **Check service logs:** `journalctl -u inkypi.service -n 50 --no-pager`
- **Service status:** `systemctl status inkypi.service`
- **Disk usage:** `df -h`
- **Running processes:** `ps aux | grep python`
- **InkyPi directory:** `/home/pi/InkyPi`

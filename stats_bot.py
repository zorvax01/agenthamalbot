#!/usr/bin/env python3
"""stats_bot: report MTProto proxy usage via @GideonGoddardbot.

Runs alongside agenthamalbot in the same Railway service. Every 5 minutes
it SSHes into the mtproto-proxy container (Railway SSH gateway) and reads
/proc/net/tcp + /proc/net/dev, then reports to the owner via the Gideon
bot token.

Env vars (set in Railway, never in code):
  GIDEON_TOKEN   - @GideonGoddardbot Bot API token.
  STATS_SSH_KEY  - SSH private key (PEM) whose public key is registered
                   with Railway, for the proxy container SSH user below.
  PROXY_SSH_USER - (optional) SSH user for the mtproto-proxy service
                   instance. Defaults to the stable value below (verified
                   stable across redeploys).

What it can (and cannot) tell:
- The proxy never sees a user's Telegram identity, and Railway's TCP
  proxy NATs every client connection, so individual users cannot be
  identified or counted exactly. This bot reports ACTIVE CONNECTIONS
  (one Telegram client opens many parallel connections) and notifies
  when that number jumps sharply, which usually means someone
  connected. It labels this as connection activity, not a confirmed
  new person.
"""
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

import paramiko

GIDEON_TOKEN = os.environ.get("GIDEON_TOKEN", "")
SSH_KEY = os.environ.get("STATS_SSH_KEY", "")
PROXY_SSH_USER = os.environ.get(
    "PROXY_SSH_USER", "79c909f5-0418-42d6-9a42-3df20c6fe544"
)
PROXY_SSH_HOST = "ssh.railway.com"
OWNER_CHAT_ID = 7258559129
TEHRAN = timezone(timedelta(hours=3, minutes=30))

CHECK_INTERVAL = 300          # seconds between checks
JUMP_THRESHOLD = 10           # jump in active connections that counts as new activity
NOTIFY_COOLDOWN = 1800        # min seconds between "new activity" notifications
SUMMARY_INTERVAL = 6 * 3600   # seconds between periodic summaries

API = f"https://api.telegram.org/bot{GIDEON_TOKEN}"
STATS_CMD = "cat /proc/net/tcp; echo ---DEV---; cat /proc/net/dev"


def log(msg):
    print(
        f"{datetime.now(TEHRAN).strftime('%Y-%m-%d %H:%M:%S')} {msg}",
        flush=True,
    )


def api(method, payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(API + "/" + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def send(chat_id, text):
    api("sendMessage", {"chat_id": chat_id, "text": text})


def load_ssh_key(key_str):
    for cls in (paramiko.Ed25519Key, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(key_str))
        except Exception:
            continue
    raise ValueError("could not parse STATS_SSH_KEY as an SSH private key")


def fetch_container_stats():
    """SSH into the proxy container, return (inbound_established, rx, tx)."""
    key = load_ssh_key(SSH_KEY)
    client = paramiko.SSHClient()
    # Railway's own SSH gateway; accepting its host key on first use.
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            PROXY_SSH_HOST, port=22, username=PROXY_SSH_USER,
            pkey=key, timeout=30, banner_timeout=30, auth_timeout=30,
        )
        _, stdout, _ = client.exec_command(STATS_CMD, timeout=60)
        out = stdout.read().decode()
    finally:
        client.close()
    tcp_part, _, dev_part = out.partition("---DEV---")
    inbound = 0
    for line in tcp_part.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].rstrip(":").isdigit():
            local, st = parts[1], parts[3]
            if local.endswith(":01BB") and st == "01":
                inbound += 1
    rx = tx = 0
    for line in dev_part.splitlines():
        if ":" not in line:
            continue
        name, rest = line.split(":", 1)
        name = name.strip()
        if name in ("lo", "Inter", "") or not name:
            continue
        nums = rest.split()
        if len(nums) >= 9:
            try:
                rx += int(nums[0])
                tx += int(nums[8])
            except ValueError:
                pass
    return inbound, rx, tx


def fmt_bytes(n):
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def main():
    if not GIDEON_TOKEN:
        print("GIDEON_TOKEN env var is missing — set it in Railway.", flush=True)
        return 1
    if not SSH_KEY:
        print("STATS_SSH_KEY env var is missing — set it in Railway.", flush=True)
        return 1

    log("stats_bot is running (checking proxy every 5 minutes)...")
    last_inbound = None
    last_rx = last_tx = None
    last_notify = 0
    last_summary = 0
    first = True

    while True:
        now = time.time()
        now_tehran = datetime.fromtimestamp(now, tz=TEHRAN).strftime("%H:%M")
        try:
            inbound, rx, tx = fetch_container_stats()
        except Exception as e:
            # Log only the error type; paramiko/requests errors can embed
            # hostnames and paths, never the token or key.
            log(f"fetch failed: {type(e).__name__}, retrying in 5 minutes")
            time.sleep(CHECK_INTERVAL)
            continue

        if first:
            text = (
                "📊 آمار پروکسی (dd) — اولین گزارش\n\n"
                f"🔌 اتصال‌های فعال: {inbound}\n"
                f"🕐 {now_tehran} به وقت تهران\n\n"
                "از این به بعد هر وقت اتصال‌ها یه جهش محسوس داشته باشن خبرت می‌کنم، "
                "و هر ۶ ساعت هم یه خلاصه می‌فرستم.\n"
                "یادآوری: پروکسی هویت کاربر رو نمی‌بینه، پس «اتصال» با «نفر» فرق داره — "
                "یه نفر معمولاً چندتا اتصال موازی باز می‌کنه."
            )
            try:
                send(OWNER_CHAT_ID, text)
                log(f"first summary sent (inbound={inbound})")
            except Exception as e:
                log(f"send failed: {type(e).__name__}")
            last_summary = now
            first = False
        else:
            jump = inbound - last_inbound
            rx_delta = max(0, rx - last_rx) if rx >= last_rx else rx
            tx_delta = max(0, tx - last_tx) if tx >= last_tx else tx
            interval_traffic = rx_delta + tx_delta

            if jump >= JUMP_THRESHOLD and (now - last_notify) >= NOTIFY_COOLDOWN:
                text = (
                    "📈 فعالیت جدید روی پروکسی\n\n"
                    f"🔌 اتصال‌های فعال: {last_inbound} ← {inbound} (+{jump})\n"
                    f"🕐 {now_tehran} به وقت تهران\n\n"
                    "یه موج اتصال تازه برقرار شد. این معمولاً یعنی کسی (تازه یا قبلی) "
                    "وصل شده — ولی چون پروکسی هویت کاربر رو نمی‌بینه، نمی‌شه با قطعیت "
                    "گفت کاربر جدیده یا همون کاربر قبلی دوباره وصل شده."
                )
                try:
                    send(OWNER_CHAT_ID, text)
                    log(f"activity notify sent (inbound {last_inbound}->{inbound})")
                except Exception as e:
                    log(f"send failed: {type(e).__name__}")
                last_notify = now

            if (now - last_summary) >= SUMMARY_INTERVAL:
                text = (
                    "📊 آمار پروکسی (dd)\n\n"
                    f"🔌 اتصال‌های فعال: {inbound}\n"
                    f"📥📤 ترافیک ۶ ساعت اخیر: {fmt_bytes(interval_traffic)}\n"
                    f"🕐 {now_tehran} به وقت تهران"
                )
                try:
                    send(OWNER_CHAT_ID, text)
                    log(f"summary sent (inbound={inbound})")
                except Exception as e:
                    log(f"send failed: {type(e).__name__}")
                last_summary = now
                last_rx, last_tx = rx, tx

            if jump < JUMP_THRESHOLD and (now - last_summary) < SUMMARY_INTERVAL:
                log(f"checked: inbound={inbound} (was {last_inbound}, jump {jump:+d})")

        last_inbound, last_rx, last_tx = inbound, rx, tx
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    sys.exit(main())

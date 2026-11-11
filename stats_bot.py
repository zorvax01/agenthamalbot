#!/usr/bin/env python3
"""stats_bot: report MTProto proxy usage via @GideonGoddardbot.

Runs alongside agenthamalbot in the same Railway service. Every 5 minutes
it fetches the proxy's stats over Railway's private network
(http://mtproto-proxy.railway.internal:8080/stats), served by a tiny
Perl server inside the mtproto-proxy container. No SSH is involved:
Railway blocks outbound SSH (port 22) from its services.

Env vars (set in Railway, never in code):
  GIDEON_TOKEN - @GideonGoddardbot Bot API token.
  STATS_URL    - (optional) stats endpoint; defaults to the private
                 address of the mtproto-proxy service.

What it can (and cannot) tell:
- The proxy never sees a user's Telegram identity, and Railway's TCP
  proxy NATs every client connection, so individual users cannot be
  identified or counted exactly. This bot reports ACTIVE CONNECTIONS
  (one Telegram client opens many parallel connections) and notifies
  when that number jumps sharply, which usually means someone
  connected. It labels this as connection activity, not a confirmed
  new person.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

GIDEON_TOKEN = os.environ.get("GIDEON_TOKEN", "")
STATS_URL = os.environ.get(
    "STATS_URL", "http://mtproto-proxy.railway.internal:8080/stats"
)
OWNER_CHAT_ID = 7258559129
TEHRAN = timezone(timedelta(hours=3, minutes=30))

CHECK_INTERVAL = 300          # seconds between checks
JUMP_THRESHOLD = 10           # jump in active connections that counts as new activity
NOTIFY_COOLDOWN = 1800        # min seconds between "new activity" notifications
SUMMARY_INTERVAL = 6 * 3600   # seconds between periodic summaries

API = f"https://api.telegram.org/bot{GIDEON_TOKEN}"


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


def fetch_stats():
    """GET the stats endpoint, return (inbound_established, rx, tx)."""
    req = urllib.request.Request(STATS_URL)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read())
    return int(data["inbound"]), int(data["rx"]), int(data["tx"])


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
            inbound, rx, tx = fetch_stats()
        except Exception as e:
            # Log only the error type; never the token or URL credentials.
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

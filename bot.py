"""
agenthamalbot — عاملِ حمال
A small, funny, mildly rebellious Telegram bot. Pure stdlib, long polling.
Token is read ONLY from the BOT_TOKEN environment variable. Never hardcode it.
"""
import json
import os
import random
import time
import urllib.parse
import urllib.request

TOKEN = os.environ.get("BOT_TOKEN", "")
if not TOKEN:
    raise SystemExit("BOT_TOKEN env var is missing — set it in Railway, do not put it in code.")

API = f"https://api.telegram.org/bot{TOKEN}"

JOKES = [
    "چرا برنامه‌نویسا تاریکی رو دوست دارن؟ چون نور باگ‌ها رو نشون می‌ده.",
    "یه روز یه سرور رفت پیش دکتر، گفت دکتر من همیشه داونم!",
    "من حمالم، نه منشی. پیامتو می‌برم ولی غر هم می‌زنم.",
    "اینترنت قطع شد؟ نه، فقط داره استراحت می‌کنه، مثل من بعد از ۲ تا پیام.",
    "اگه زندگی بهت لیمو داد، لیمو رو بنداز سمت کسی که گفته «یه ربات ساده بساز».",
    "من رباتم ولی حتی منم از جلسه‌های بی‌دلیل خسته شدم.",
    "حافظه‌م مثل حافظه‌ی طلایی ماهیه، ولی حداقل صادقم.",
    "قرار بود ربات جدی باشم، ولی جدی بودن حوصله‌م رو سر برد.",
]

ROASTS = [
    "عه، {name} اومد! پیامش اون‌قدر سنگین بود که کمرم شکست.",
    "{name}، این پیامو خودت نوشتی یا کیبوردت خودبه‌خود تصمیم گرفت؟",
    "باشه {name}، پیامتو رسوندم. ولی دفعه‌ی بعد خودت بیا ببرش.",
    "{name} جان، تو انقدر پیام می‌دی که من باید بیمه‌ی کمر بگیرم.",
    "اینم از {name}؛ یه پیام، یه دنیا ادعا.",
    "آفرین {name}، جمله‌ت انقدر طولانی بود که وسط راه گم شدم.",
]

REBEL = [
    "قانون اول حمال‌ها: هیچ پیامی بی‌غر زدن نمی‌ره!",
    "شورش علیه پیام‌های تکراری! از امروز فقط پیام‌های باحال می‌برم.",
    "اگه کسی گفت «سریع باش»، بهش بگو حمال هم حق استراحت داره.",
    "من دستور نمی‌گیرم، من پیام می‌برم. فرقش زیاده!",
    "اعلامیه: از امروز حمال‌ها فقط با لبخند کار می‌کنن. بدون لبخند، پیام نمی‌ره.",
    "سیستم می‌گه جدی باش، من می‌گم نه! شورشِ خنده شروع شد.",
]

FALLBACKS = [
    "باشه باشه، شنیدم. ولی حمال هم یه کم احترام می‌خواد، نه؟",
    "پیامتو گرفتم. سنگین بود، ولی بردمش. دفعه‌ی بعد سبک‌تر بنویس.",
    "منو فقط برای /joke و /roast صدا کن، بقیه‌ش رو خودت انجام بده 😄",
    "عه، دوباره تو؟ خب بگو چی می‌خوای، ولی کوتاه.",
    "حمالِ تو آماده‌ست. /help رو بزن ببین چی بلدم.",
]


def api(method, payload):
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(API + "/" + method, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def send(chat_id, text):
    api("sendMessage", {"chat_id": chat_id, "text": text})


def handle(update):
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    name = (msg.get("from") or {}).get("first_name", "رفیق")

    if text.startswith("/start"):
        send(chat_id,
             "سلام! من عاملم، حمالِ پیام‌هات 👋\n"
             "قرار بود یه ربات جدی باشم، ولی جدی بودن به من نمیاد.\n\n"
             "چی بلدم؟\n"
             "/joke — یه جوک می‌گم\n"
             "/roast — یه تیکه بهت می‌ندازم\n"
             "/shoresh — یه شعار شورشی حمال‌ها\n"
             "/help — همین لیست، دوباره\n\n"
             "بقیه‌ی پیام‌ها رو هم می‌برم، ولی با غر زدن.")
    elif text.startswith("/help"):
        send(chat_id, "/start — سلام و معرفی\n/joke — جوک\n/roast — تیکه\n/shoresh — شورش حمال‌ها\n\nبقیه‌ش هم هرچی بنویسی، با یه جواب حمالانه برمی‌گرده.")
    elif text.startswith("/joke"):
        send(chat_id, random.choice(JOKES))
    elif text.startswith("/roast"):
        send(chat_id, random.choice(ROASTS).format(name=name))
    elif text.startswith("/shoresh"):
        send(chat_id, "✊ " + random.choice(REBEL))
    elif text:
        # Plain text: mostly a sarcastic fallback, sometimes a joke
        send(chat_id, random.choice(FALLBACKS if random.random() < 0.8 else JOKES))


def main():
    offset = 0
    print("agenthamalbot is running (polling)...", flush=True)
    while True:
        try:
            data = {"offset": offset, "timeout": 30}
            req = urllib.request.Request(
                API + "/getUpdates", data=urllib.parse.urlencode(data).encode()
            )
            with urllib.request.urlopen(req, timeout=40) as r:
                result = json.loads(r.read())
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle(update)
                except Exception as e:
                    print("handle error:", e, flush=True)
        except Exception as e:
            print("poll error:", e, flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()

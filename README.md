# agenthamalbot — عاملِ حمال

A small, funny, mildly rebellious Telegram bot. Pure Python stdlib, long polling, no dependencies.

Commands: `/start`, `/help`, `/joke`, `/roast`, `/shoresh`

## Run locally

```bash
export BOT_TOKEN="your-token-here"
python bot.py
```

## Deploy on Railway

1. Push this repo to GitHub.
2. In Railway, create a new project from this GitHub repo.
3. Set the `BOT_TOKEN` environment variable in Railway (Variables tab). Never commit the token.
4. Deploy — the start command is `python bot.py`.

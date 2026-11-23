# YTcastsBot

1. don't forget to create such .env beside deploy.sh, the bot reads its settings from the environment:

```
# telegram ids white list - who can ask the bot to download, comma-separated
ALLOWED_IDS=123,456
# telegram bot api key
BOT_KEY=1234567890:ABCDEFGHIJKLMONPQRSTUWXYZ12345abcde
# audio compression settings (see ffmpeg man, compand section)
COMPAND=compand=attacks=0:points=-60/-900|-45/-20|-27/-6|0/0|9/0:gain=9
# optional: your own Bot API server, run with --local (files up to 2000 MB);
# Telegram's own when unset. Call logOut on api.telegram.org once before.
#BOT_API_URL=http://192.168.19.45:8081
```

2. run ./deploy.sh

the running bot is deployed by a GitLab pipeline on every push to master: it builds the image like deploy.sh and passes the same three settings to the container

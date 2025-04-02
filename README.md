# YTcastsBot

1. don't forget to create such bot_settings.py:

\# telegram ids white list - who can ask the bot to download
allowed_ids = [123, 456]
\# telegram bot api key
bot_key = '1234567890:ABCDEFGHIJKLMONPQRSTUWXYZ12345abcde'
\# audio compression settings (see ffmpeg man, compand section)
compand = "compand=attacks=0:points=-60/-900|-45/-20|-27/-6|0/0|9/0:gain=9"

2. run ./deploy.sh

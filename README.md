# YTcastsBot

don't forget to create such bot_settings.py:

allowed_ids = [123, 456]

bot_key = '1234567890:ABCDEFGHIJKLMONPQRSTUWXYZ12345abcde'

compand = "compand=attacks=0:points=-60/-900|-45/-20|-27/-6|0/0|9/0:gain=9"


## get yt-dlp
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp


##LOGIN FIX:

install the plugin (pip install 'telebot' 'https://github.com/coletdjnz/yt-dlp-youtube-oauth2/archive/refs/heads/master.zip')

pass --username oauth2 --password '' as options for yt-dlp

it gives you a code and asks to enter it at https://www.google.com/device

after entering the code google asks you to choose an account to sign in(I used a dummy account)
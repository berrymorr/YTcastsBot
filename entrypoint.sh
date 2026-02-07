#!/bin/sh
pip install --upgrade pip && pip install 'telebot' && apk add --no-cache ffmpeg curl && \
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp && \
  chmod 755 /usr/bin/yt-dlp && python3 /bot.py


pip install --upgrade pip && pip install 'telebot' && \
  apt-get clean all && apt-get update && apt-get -y install ffmpeg curl unzip && \
  apt-get clean all && \
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp && \
  curl -L https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /deno.zip && \
  unzip /deno.zip && mv -v /deno /usr/bin/deno && rm -vf /deno.zip && \
  chmod 755 /usr/bin/yt-dlp /usr/bin/deno && \
  python3 /bot.py

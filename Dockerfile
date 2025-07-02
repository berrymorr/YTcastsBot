FROM python:3.9.13-alpine3.16
ADD entrypoint.sh *.py /
RUN pip install --upgrade pip && pip install 'telebot' && apk add --no-cache ffmpeg curl && \
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp && \
  chmod 755 /usr/bin/yt-dlp
CMD [ "/bin/sh", "/entrypoint.sh" ]


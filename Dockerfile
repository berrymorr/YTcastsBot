FROM python:3.11.14-slim-bookworm
ADD entrypoint.sh *.py /
RUN pip install --upgrade pip && pip install 'telebot' && \
  apt-get clean all && apt-get update && apt-get -y install ffmpeg curl unzip && \
  apt-get clean all && \
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp && \
  curl -L https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /deno.zip && \
  unzip /deno.zip && mv -v /deno /usr/bin/deno && rm -vf /deno.zip && \
  chmod -v 755 /usr/bin/yt-dlp /usr/bin/deno

CMD [ "/bin/sh", "/entrypoint.sh" ]

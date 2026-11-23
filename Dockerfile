FROM python:3.11.14-slim-bookworm
ADD entrypoint.sh *.py /
RUN pip install --upgrade pip && pip install 'telebot' && \
  apt-get clean all && apt-get update && apt-get -y install ffmpeg curl unzip && \
  apt-get clean all && \
  curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/bin/yt-dlp && \
  curl -L https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip -o /deno.zip && \
  unzip /deno.zip && mv -v /deno /usr/bin/deno && rm -vf /deno.zip && \
  chmod -v 755 /usr/bin/yt-dlp /usr/bin/deno
# YAMNet, which tells speech from music for classify.py, and its runtime
RUN pip install 'ai-edge-litert==2.4.0' && \
  curl -fsSL https://storage.googleapis.com/mediapipe-models/audio_classifier/yamnet/float32/1/yamnet.tflite -o /yamnet.tflite && \
  echo '4d8b4a53282dc83ef04e3e7dbc4fbc98082e34e44ed798e16c3a0cdd4c584faf  /yamnet.tflite' | sha256sum -c -

CMD [ "/bin/sh", "/entrypoint.sh" ]

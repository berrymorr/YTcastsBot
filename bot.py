#!/usr/bin/python3

import telebot
from telebot import apihelper
from telebot.types import InputFile
import requests
import _thread
import json
import math
import subprocess
import time
import traceback
from datetime import timedelta
import os
import re
import sys

import classify

script_dir = os.path.dirname(os.path.realpath(__file__))

# settings come from the environment, see README.md
missing = [name for name in ['BOT_KEY', 'ALLOWED_IDS', 'COMPAND'] if not os.environ.get(name)]
if missing:
  sys.exit('not set in the environment: ' + ', '.join(missing))
bot_key = os.environ['BOT_KEY']
allowed_ids = [int(i) for i in re.split(r'[\s,]+', os.environ['ALLOWED_IDS'].strip())]
compand = os.environ['COMPAND']

# the Bot API server: Telegram's own, or ours when BOT_API_URL names it (a
# --local one, which fetches and sends files of up to 2000 MB; Telegram's
# own fetches 20 MB and sends 50). A bot is logged in on one server only.
bot_api_url = os.environ.get('BOT_API_URL', '').rstrip('/')
if bot_api_url:
  apihelper.API_URL = bot_api_url + '/bot{0}/{1}'
  apihelper.FILE_URL = bot_api_url + '/file/bot{0}/{1}'
  # getFile answers once the server has the whole file from Telegram
  apihelper.READ_TIMEOUT = 600
  max_fetch_mb, max_send_mb = 2000, 2000
else:
  max_fetch_mb, max_send_mb = 19.9, 50

bot = telebot.TeleBot(bot_key)


# a line to the log, which is the container's: the time in UTC, then the
# request it is about - a video id, or "audio" and the message's id. The
# bot's token, which a file's address and an error about it carry, is cut out.
def log(tag, msg):
  stamp = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
  lines = str(msg).replace(bot_key, '<token>').splitlines() or ['']
  sys.stdout.write(''.join(f"{stamp} [{tag}] {line}\n" for line in lines))
  sys.stdout.flush()


# a file the bot was sent, fetched into path piece by piece: a big one would
# not fit in the container's memory, as telebot's download_file would hold it
def fetch_file(file_path, path):
  url = (apihelper.FILE_URL or "https://api.telegram.org/file/bot{0}/{1}").format(bot_key, file_path)
  with requests.get(url, stream=True, timeout=(15, 600)) as r:
    r.raise_for_status()
    with open(path, 'wb') as f:
      for chunk in r.iter_content(1 << 20):
        f.write(chunk)


# who sent a message, for the log
def who(message):
  return f"{message.from_user.id} @{message.from_user.username}"


def size_mb(path):
  return f"{os.path.getsize(path) / 1048576:.1f} MB"


# runs a request in a thread of its own; what breaks it goes to the log
def start_request(tag, request, *args):
  def run():
    started = time.time()
    try:
      request(*args)
    except Exception:
      log(tag, "broke: " + traceback.format_exc())
    log(tag, f"over in {time.time() - started:.0f} s")
  _thread.start_new_thread(run, ())


# runs a program and puts into the log what it said on stderr (the last 20
# lines) and how it ended; returns the finished process
def run_logged(tag, args):
  started = time.time()
  p = subprocess.run(args, capture_output=True)
  for line in p.stderr.decode("utf-8", "replace").splitlines()[-20:]:
    log(tag, f"{args[0]}: {line}")
  ended = "done" if p.returncode == 0 else f"failed, exit code {p.returncode}"
  log(tag, f"{args[0]} {ended} in {time.time() - started:.0f} s")
  return p


# ffmpeg, saying nothing but its errors; returns its exit code
def ffmpeg(tag, args):
  return run_logged(tag, ["ffmpeg", "-hide_banner", "-loglevel", "error"] + args).returncode



# a podcast's pieces: 30 minutes each, so that piece n starts at (n - 1) * 30
PART = 30 * 60


# the file's length in seconds, or None if ffprobe cannot tell
def duration_of(path):
  p = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True)
  try:
    return float(p.stdout.strip())
  except ValueError:
    return None


# what the sender calls it, if anything: a word outside the link overrides
# the bot's own guess
def kind_named(text):
  words = set(re.findall(r'\w+', re.sub(r'\S*(?:://|youtu)\S*', ' ', text or '').lower()))
  if words & {'музыка', 'музыку', 'music'}:
    return 'music'
  if words & {'подкаст', 'podcast', 'лекция', 'лекцию', 'lecture'}:
    return 'podcast'
  return None


# podcast (a lecture is one too) or music, and why. By the sound itself
# (classify.py): over 65% of its frames speech is a podcast, under 35%
# music; in between, YouTube's category says, Music or not. YouTube's
# category alone is often wrong: an interview filed under Music, a live
# song under Comedy.
def kind_of(tag, path, duration, named, category=None):
  if named:
    return named, "так сказано в сообщении"
  try:
    speech, music = classify.speech_and_music(path, duration or 60)
  except Exception:
    log(tag, "sound: could not tell: " + traceback.format_exc())
    return 'podcast', "звук не разобрал"
  share = speech / max(speech + music, 1)
  log(tag, f"sound: {speech} frames of speech, {music} of music; YouTube's category: {category}")
  if share >= 0.65:
    return 'podcast', f"речи {share:.0%}"
  if share <= 0.35:
    return 'music', f"музыки {1 - share:.0%}"
  if category == 'Music':
    return 'music', f"речи {share:.0%}, а YouTube говорит Music"
  return 'podcast', f"речи {share:.0%}"


# a podcast: compressed (COMPAND, Vorbis 96k) and sent in pieces of PART; the
# last piece runs to the end, and an end of under 2 minutes goes with the
# piece before rather than alone
def send_podcast(chat_id, path, title, duration, tag):
  parts = max(1, math.ceil(((duration or 0) - 120) / PART))
  log(tag, f"podcast: {parts} part(s) of 30 minutes")
  if parts == 1:
    bot.send_message(chat_id, 'жмём целиком...')
  for n in range(parts):
    out = f"{path}_part{n + 1}.ogg"
    seek = ['-ss', str(n * PART)] if n else []
    length = ['-t', str(PART)] if n < parts - 1 else []
    if parts > 1:
      bot.send_message(chat_id, f'жму часть {n + 1} из {parts}...')
    try:
      rc = ffmpeg(tag, seek + ['-i', path] + length + ['-filter_complex', compand, '-c:a', 'libvorbis', '-b:a', '96k', '-ar', '44100', '-vn', out])
      if rc != 0:
        bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
        return
      cap = title
      if parts > 1:
        end = timedelta(seconds=round(duration)) if n == parts - 1 else timedelta(seconds=(n + 1) * PART)
        cap = f"{title} {n + 1}/{parts}, {timedelta(seconds=n * PART)}–{end}"
      bot.send_document(chat_id, document=InputFile(out), caption=cap, timeout=3600)
      log(tag, f"sent part {n + 1} of {parts}, {size_mb(out)}")
    finally:
      if os.path.exists(out):
        os.remove(out)


# music: sent as it came, neither compressed nor cut. Telegram's player
# takes m4a and mp3 (sendAudio); anything else goes as a file.
def send_music(chat_id, path, title, performer, duration, tag):
  if os.path.getsize(path) > max_send_mb * 1048576:
    log(tag, f"music: {size_mb(path)}, over the {max_send_mb} MB a bot may send")
    bot.send_message(chat_id, f"файл {size_mb(path)}, а боту можно слать до {max_send_mb} МБ")
    return
  bot.send_message(chat_id, 'заливаю как есть...')
  if path.endswith(('.m4a', '.mp3')):
    bot.send_audio(chat_id, InputFile(path), title=title, performer=performer, duration=round(duration) if duration else None, timeout=3600)
  else:
    bot.send_document(chat_id, document=InputFile(path), caption=title, timeout=3600)
  log(tag, f"music: sent as it came, {size_mb(path)}")


HINT = "(не так — пришли ещё раз со словом «музыка» или «подкаст»)"



# whether cookies.txt holds a YouTube login: yt-dlp counts one only while
# LOGIN_INFO is in it, and YouTube takes that out when it ends the session
def has_login():
  try:
    with open("cookies.txt") as f:
      return any(line.split("\t")[5:6] == ["LOGIN_INFO"] for line in f)
  except OSError:
    return False


# yt-dlp's output; a failure raises CalledProcessError
def run_yt_dlp(tag, args):
  p = run_logged(tag, ["yt-dlp"] + args)
  p.check_returncode()
  return p.stdout.decode("utf-8").rstrip("\n")


# the ERROR lines of a failed yt-dlp, or all it said if it said none
def yt_dlp_errors(e):
  lines = e.stderr.decode("utf-8", "replace").splitlines()
  return "\n".join([line for line in lines if line.startswith("ERROR")] or lines)


# runs yt-dlp with the YouTube cookies in cookies.txt, and once more without
# them if that fails: stale cookies can fail where none at all would work.
# The log says whether the cookies held a login, and when YouTube took it
# out: nothing fails for that, yt-dlp just goes on as with no login.
def yt_dlp(chat_id, tag, step, args):
  login = has_login()
  log(tag, f"{step}: yt-dlp with cookies.txt, " + ("logged in to YouTube" if login else "no YouTube login in it"))
  try:
    out = run_yt_dlp(tag, ["--cookies", "cookies.txt"] + args)
  except subprocess.CalledProcessError:
    out = None
  if login and not has_login():
    log(tag, "YouTube took the login out of cookies.txt: the session is over, new cookies are needed")
  if out is not None:
    return out
  bot.send_message(chat_id, "с куками не вышло, пробуем без них...")
  log(tag, f"{step}: yt-dlp once more, without cookies")
  return run_yt_dlp(tag, args)


def download_video(chat_id, url, tag, named):
  try:
    meta = json.loads(yt_dlp(chat_id, tag, "title", ["--skip-download", "--print", "%(.{title,channel,artist,track,categories,duration})j", url]))
  except subprocess.CalledProcessError as e:
    bot.send_message(chat_id, f"что-то не качается, можно попробовать позже:\n{yt_dlp_errors(e)}")
    return None
  video_title = meta.get('title') or tag
  category = (meta.get('categories') or [None])[0]
  log(tag, f"title: {video_title}")

  bot.send_message(chat_id, f"скачиваем {video_title} с youtube...")

  # the audio as YouTube has it, m4a when there is one: music goes out as it
  # came, and Telegram's player takes m4a
  try:
    fname_tmp = yt_dlp(chat_id, tag, "download", ["--ignore-config", "-f", "bestaudio[ext=m4a]/bestaudio", "--print", "after_move:filepath", "--output", f"{script_dir}/{time.time()}.%(ext)s", str(url)])
  except subprocess.CalledProcessError as e:
    bot.send_message(chat_id, f"yt-dlp can't download audio:\n{yt_dlp_errors(e)}")
    return None
  try:
    duration = duration_of(fname_tmp) or meta.get('duration')
    log(tag, f"download: {fname_tmp}, {size_mb(fname_tmp)}, {timedelta(seconds=round(duration or 0))}")
    kind, why = kind_of(tag, fname_tmp, duration, named, category)
    log(tag, f"kind: {kind} ({why})")
    if kind == 'music':
      bot.send_message(chat_id, f"похоже на музыку ({why}), шлю без обработки" + ("" if named else " " + HINT))
      send_music(chat_id, fname_tmp, meta.get('track') or video_title, meta.get('artist') or meta.get('channel'), duration, tag)
    else:
      bot.send_message(chat_id, f"похоже на подкаст ({why}), компрессим" + ("" if named else " " + HINT))
      send_podcast(chat_id, fname_tmp, video_title, duration, tag)
  finally:
    if os.path.exists(fname_tmp):
      os.remove(fname_tmp)



# a file sent to the bot: a podcast is compressed and cut like one from
# YouTube; music is already the sender's, so it gets only a word back
def take_audio(chat_id, file_id, audio_title, tag, named):
  fname_tmp = f"{script_dir}/{time.time()}.audio"

  bot.send_message(chat_id, "забираю файл...")

  try:
    fetch_file(bot.get_file(file_id).file_path, fname_tmp)
  except Exception as e:
    log(tag, f"fetching the file failed: {e}")
    bot.send_message(chat_id, "случилась какая-то херня, и я не смог сохранить файл...")
    return None
  try:
    duration = duration_of(fname_tmp)
    log(tag, f"received {fname_tmp}, {size_mb(fname_tmp)}, {timedelta(seconds=round(duration or 0))}")
    kind, why = kind_of(tag, fname_tmp, duration, named)
    log(tag, f"kind: {kind} ({why})")
    if kind == 'music':
      bot.send_message(chat_id, f"похоже на музыку ({why}): обрабатывать нечего. Если это подкаст, пришли его с подписью «подкаст»")
      return None
    bot.send_message(chat_id, f"похоже на подкаст ({why}), компрессим" + ("" if named else " " + HINT))
    send_podcast(chat_id, fname_tmp, audio_title, duration, tag)
  finally:
    if os.path.exists(fname_tmp):
      os.remove(fname_tmp)



@bot.message_handler(commands=['start'])
def start_message(message):
  bot.send_message(message.chat.id, 'Дратути, я люблю кочять и пожимать! Скинь мне либо ссылку на ютуб, либо аудиофайл, и я верну аудио с компрессией. Подкасты и лекции жму и режу по 30 минут, музыку шлю как есть; если я не угадал, добавь к ссылке слово «музыка» или «подкаст»')


@bot.message_handler(content_types=['text'])
def process_text(message):
  if message.from_user.id in allowed_ids:
    try:
      res = re.search(r'(?:youtube\.com\/\S*(?:(?:\/e(?:mbed))?\/|watch\?(?:\S*?&?v\=))|youtu\.be\/)([a-zA-Z0-9_-]{6,11})', message.text)
      video_name = res.group(1)
    except:
      log("bot", f"{who(message)}, not a YouTube link: {message.text[:200]!r}")
      bot.send_message(message.chat.id, f'дай мне ссылку на видос на ютубе, или кинь файл <{max_fetch_mb:g}МБ')
      return

    url = "https://www.youtube.com/watch?v=" + video_name
    log(video_name, f"{who(message)} asks for {message.text[:200]}")
    bot.send_message(message.chat.id, 'пробуем скачать, video id=' + video_name)
    start_request(video_name, download_video, message.chat.id, url, video_name, kind_named(message.text))

  else:
    log("bot", f"{who(message)}, not on the list: {message.text[:200]!r}")
    bot.send_message(message.chat.id, 'вас нет в VIP-списке, обратитесь к @berrymorr , приложив свой id: ' + str(message.from_user.id))


@bot.message_handler(content_types=['audio'])
def process_file(message):
  tag = f"audio {message.message_id}"
  if message.from_user.id in allowed_ids:
    log(tag, f"{who(message)} sends {message.audio.title!r}, {message.audio.file_size / 1048576:.1f} MB")
    if message.audio.file_size/1024/1024 > max_fetch_mb:
      log(tag, f"over {max_fetch_mb} MB, more than a bot may fetch")
      bot.send_message(message.chat.id, f'Паша Дуров мудак, курит табак, и ботам нельзя принимать файлы >{max_fetch_mb:g} Мб  https://core.telegram.org/bots/api#getfile')
      return

    title = message.audio.title or message.audio.file_name or 'audio'
    bot.send_message(message.chat.id, 'пробуем скачать  ' + title)
    start_request(tag, take_audio, message.chat.id, message.audio.file_id, title, tag, kind_named(message.caption))

  else:
    log(tag, f"{who(message)}, not on the list")
    bot.send_message(message.chat.id, 'вас нет в VIP-списке, обратитесь к @berrymorr , приложив свой id: ' + str(message.from_user.id))


@bot.message_handler(content_types=['location'])
def process_location(message):
  bot.send_message(message.chat.id, str(message))



#bot.polling()
log("bot", "Bot API: " + (bot_api_url or "https://api.telegram.org, Telegram's own"))
log("bot", "yt-dlp " + subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True).stdout.strip())
log("bot", "cookies.txt: " + ("logged in to YouTube" if has_login() else "no YouTube login in it" if os.path.exists("cookies.txt") else "none"))
print(f"polling as @{bot.get_me().username}", flush=True)
bot.infinity_polling(skip_pending=True)


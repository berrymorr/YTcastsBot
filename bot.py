#!/usr/bin/python3

import telebot
from telebot import apihelper
from telebot.types import InputFile
import requests
import _thread
import subprocess
import time
import traceback
from datetime import timedelta
import os
import re
import sys

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



def get_file_length(input_file):
  def get_sec(time_str):
    [h, m, s] = time_str.split(':')
    return int(h) * 3600 + int(m) * 60 + float(s)

  try:
    proc = subprocess.Popen(['ffmpeg', '-i', input_file], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
  except:
    print("can't run ffmpeg to get audio length")
    return None
  proc_stdout = proc.communicate()
  try:
    str_length = re.search('Duration: ((\d{2}:){2}\d{2}\.\d{2})', str(proc_stdout)).group(1)
  except:
    print("ffmpeg didn't return audio length")
    return None
  else:
    length = get_sec(str_length)
    return length


def upload_payload(chat_id,input_file,cap,tag):
  fsize = os.path.getsize(input_file)
#  _50MB = 52428800
  _50MB = 42428800
  fragments = ( fsize // _50MB ) + 1

  if fragments > 1:
    try:
      total_length = get_file_length(input_file)
    except:
      bot.send_message(chat_id, "can't get file length")
      return None

    fragment_length = total_length / fragments
    log(tag, f"{fragments} parts of {timedelta(seconds=round(fragment_length))}")

    bot.send_message(chat_id, 'файл большой, разобьём на ' + str(fragments) + ' частей по ' + str(timedelta(seconds=round(fragment_length))))
    for f in range(0,fragments,1):
      bot.send_message(chat_id, 'конвертим фрагмент #' + str(f + 1))
      fname_final = input_file + '_part' + str(f + 1) + '.ogg'
      rc = ffmpeg(tag, ['-i', input_file, '-ss', str(f * fragment_length), '-t', str(fragment_length), '-filter_complex', compand, '-c:a', 'libvorbis', '-b:a', '96k', '-ar', '44100', '-vn', fname_final])
      if rc != 0:
        bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
        return None
      bot.send_message(chat_id, 'удалось, заливаю его...')
      cpt = f"{cap} {str(f + 1)}"
      bot.send_document(chat_id, document=InputFile(fname_final), caption=cpt)
      log(tag, f"sent part {f + 1} of {fragments}, {size_mb(fname_final)}")
      if os.path.exists(fname_final):
        os.remove(fname_final)
    if os.path.exists(input_file):
      os.remove(input_file)


  else:
    bot.send_message(chat_id, 'файл норм, жмём целиком')
    fname_final = input_file + '.ogg'
    rc = ffmpeg(tag, ['-i', input_file, '-filter_complex', compand, '-c:a', 'libvorbis', '-b:a', '96k', '-ar', '44100', '-vn', fname_final])
    if rc != 0:
      bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
      return None
    bot.send_message(chat_id, 'удалось, сейчас залью файл...')
    bot.send_document(chat_id, document=InputFile(fname_final), caption=cap)
    log(tag, f"sent, {size_mb(fname_final)}")
    if os.path.exists(input_file):
      os.remove(input_file)
    if os.path.exists(fname_final):
      os.remove(fname_final)




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


def download_video(chat_id, url, tag):
  fname_tmp = f"{script_dir}/{str(time.time())}.opus"
  try:
    video_title = yt_dlp(chat_id, tag, "title", ["--skip-download", "--get-title", url])
  except subprocess.CalledProcessError as e:
    bot.send_message(chat_id, f"что-то не качается, можно попробовать позже:\n{yt_dlp_errors(e)}")
    return None
  log(tag, f"title: {video_title}")

  bot.send_message(chat_id, f"скачиваем {video_title} с youtube...")

  try:
    fname_tmp = yt_dlp(chat_id, tag, "download", ["--ignore-config", "--print", "after_move:filepath", "--extract-audio", "--audio-format", "opus", "--output", f"{fname_tmp}", str(url)])
  except subprocess.CalledProcessError as e:
    bot.send_message(chat_id, f"yt-dlp can't download audio:\n{yt_dlp_errors(e)}")
    return None
  log(tag, f"download: {fname_tmp}, {size_mb(fname_tmp)}")

  bot.send_message(chat_id, "удалось, теперь компрессим звук...")
  #here we must compress and upload
  upload_payload(chat_id,fname_tmp,video_title,tag)



def compress_audio(chat_id, file_id, audio_title, tag):
  fname_tmp = str(time.time()) + ".mp3"
  fname_final = "out" + str(time.time()) + ".ogg"

  bot.send_message(chat_id, "забираю файл...")

  try:
    fetch_file(bot.get_file(file_id).file_path, fname_tmp)
  except Exception as e:
    log(tag, f"fetching the file failed: {e}")
    bot.send_message(chat_id, "случилась какая-то херня, и я не смог сохранить файл...")
    return None
  log(tag, f"received {fname_tmp}, {size_mb(fname_tmp)}")

  bot.send_message(chat_id, "удалось, теперь компрессим звук...")

  rc = ffmpeg(tag, ["-i", fname_tmp, "-filter_complex", compand, "-c:a", "libvorbis", "-b:a", "96k", "-ar", "44100", "-vn", fname_final])

  if rc != 0:
    bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
    return None

  bot.send_message(chat_id, "удалось, сейчас залью файл...")

  bot.send_document(chat_id, document=InputFile(fname_final), caption=audio_title)
  log(tag, f"sent, {size_mb(fname_final)}")

  if os.path.exists(fname_tmp):
    os.remove(fname_tmp)
  if os.path.exists(fname_final):
    os.remove(fname_final)



@bot.message_handler(commands=['start'])
def start_message(message):
  bot.send_message(message.chat.id, 'Дратути, я люблю кочять и пожимать! Скинь мне либо ссылку на ютуб, либо аудиофайл, и я верну аудио с компрессией')


@bot.message_handler(content_types=['text'])
def process_text(message):
  if message.from_user.id in allowed_ids:
    try:
      res = re.search(r'(?:youtube\.com\/\S*(?:(?:\/e(?:mbed))?\/|watch\?(?:\S*?&?v\=))|youtu\.be\/)([a-zA-Z0-9_-]{6,11})', message.text)
      video_name = res.group(1)
    except:
      log("bot", f"{who(message)}, not a YouTube link: {message.text[:200]!r}")
      bot.send_message(message.chat.id, 'дай мне ссылку на видос на ютубе, или кинь файл <20МБ')
      return

    url = "https://www.youtube.com/watch?v=" + video_name
    log(video_name, f"{who(message)} asks for {message.text[:200]}")
    bot.send_message(message.chat.id, 'пробуем скачать, video id=' + video_name)
    start_request(video_name, download_video, message.chat.id, message.text, video_name)

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

    bot.send_message(message.chat.id, 'пробуем скачать  ' + str(message.audio.title))
    start_request(tag, compress_audio, message.chat.id, message.audio.file_id, message.audio.title, tag)

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


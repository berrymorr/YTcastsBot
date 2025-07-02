#!/usr/bin/python3

import telebot
from telebot.types import InputFile
import _thread
import subprocess
import time
from datetime import timedelta
import os
import re

script_dir = os.path.dirname(os.path.realpath(__file__))

from bot_settings import *
bot = telebot.TeleBot(bot_key)



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


def upload_payload(chat_id,input_file,cap):
  fsize = os.path.getsize(input_file)
  _50MB = 52428800
  fragments = ( fsize // _50MB ) + 1

  if fragments > 1:
    try:
      total_length = get_file_length(input_file)
    except:
      bot.send_message(chat_id, "can't get file length")
      return None

    fragment_length = total_length / fragments

    bot.send_message(chat_id, 'файл большой, разобьём на ' + str(fragments) + ' частей по ' + str(timedelta(seconds=round(fragment_length))))
    for f in range(0,fragments,1):
      bot.send_message(chat_id, 'конвертим фрагмент #' + str(f + 1))
      fname_final = input_file + '_part' + str(f + 1) + '.ogg'
      rc = subprocess.call(['ffmpeg', '-i', input_file, '-ss', str(f * fragment_length), '-t', str(fragment_length), '-filter_complex', compand, '-c:a', 'libvorbis', '-b:a', '96k', '-ar', '44100', '-vn', fname_final])
      if rc != 0:
        bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
        return None
      bot.send_message(chat_id, 'удалось, заливаю его...')
      cpt = f"{cap} {str(f + 1)}"
      bot.send_document(chat_id, document=InputFile(fname_final), caption=cpt)
      if os.path.exists(fname_final):
        os.remove(fname_final)
    if os.path.exists(input_file):
      os.remove(input_file)


  else:
    bot.send_message(chat_id, 'файл норм, жмём целиком')
    fname_final = input_file + '.ogg'
    rc = subprocess.call(['ffmpeg', '-i', input_file, '-filter_complex', compand, '-c:a', 'libvorbis', '-b:a', '96k', '-ar', '44100', '-vn', fname_final])
    if rc != 0:
      bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
      return None
    bot.send_message(chat_id, 'удалось, сейчас залью файл...')
    bot.send_document(chat_id, document=InputFile(fname_final), caption=cap)
    if os.path.exists(input_file):
      os.remove(input_file)
    if os.path.exists(fname_final):
      os.remove(fname_final)




def download_video(chat_id, url):
  fname_tmp = f"{script_dir}/{str(time.time())}.opus"
  print("output filename = {fname_tmp}")
  try:
    video_title = subprocess.check_output(["yt-dlp", "--skip-download", "--get-title", "--no-warnings", url],stderr=subprocess.STDOUT).decode("utf-8").rstrip('\n')
  except subprocess.CalledProcessError as e:
    err_msg = e.output.decode("utf-8").rstrip('\n')
    bot.send_message(chat_id, f"что-то не качается, можно попробовать позже:\n{err_msg}")
    return None

  bot.send_message(chat_id, f"скачиваем {video_title} с youtube...")

  try:
    fname_tmp = subprocess.check_output(["yt-dlp", "--no-warnings", "--ignore-config", "--print", "after_move:filepath", "--extract-audio", "--audio-format", "opus", "--output", f"{fname_tmp}", str(url)],stderr=subprocess.STDOUT).decode("utf-8").rstrip("\n")
  except:
    bot.send_message(chat_id, f"yt-dlp can't download audio with error {fname_tmp}")
    return None

  bot.send_message(chat_id, "удалось, теперь компрессим звук...")
  #here we must compress and upload
  upload_payload(chat_id,fname_tmp,video_title)



def compress_audio(chat_id, file_id_info, audio_title):
  fname_tmp = str(time.time()) + ".mp3"
  fname_final = "out" + str(time.time()) + ".ogg"

  bot.send_message(chat_id, "забираю файл...")

  file_contents = bot.download_file(file_id_info.file_path)
  try:
    with open(fname_tmp, 'wb') as fd:
      fd.write(file_contents)
      fd.close()
  except:
    bot.send_message(chat_id, "случилась какая-то херня, и я не смог сохранить файл...")
    return None

  bot.send_message(chat_id, "удалось, теперь компрессим звук...")

  rc = subprocess.call(["ffmpeg", "-i", fname_tmp, "-filter_complex", compand, "-c:a", "libvorbis", "-b:a", "96k", "-ar", "44100", "-vn", fname_final])

  if rc != 0:
    bot.send_message(chat_id, "ffmpeg can't compress audio, exitcode = " + str(rc))
    return None

  bot.send_message(chat_id, "удалось, сейчас залью файл...")

  bot.send_document(chat_id, document=InputFile(fname_final), caption=audio_title)

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
      bot.send_message(message.chat.id, 'дай мне ссылку на видос на ютубе, или кинь файл <20МБ')
      return

    url = "https://www.youtube.com/watch?v=" + video_name
    bot.send_message(message.chat.id, 'пробуем скачать, video id=' + video_name)
    _thread.start_new_thread(download_video, (message.chat.id, message.text))

  else:
    bot.send_message(message.chat.id, 'вас нет в VIP-списке, обратитесь к @berrymorr , приложив свой id: ' + str(message.from_user.id))


@bot.message_handler(content_types=['audio'])
def process_file(message):
  if message.from_user.id in allowed_ids:
    if message.audio.file_size/1024/1024 > 19.9:
      bot.send_message(message.chat.id, 'Паша Дуров мудак, курит табак, и ботам нельзя принимать файлы >20 Мб  https://core.telegram.org/bots/api#getfile')
      return

    file_id_info = bot.get_file(message.audio.file_id)
    bot.send_message(message.chat.id, 'пробуем скачать  ' + str(message.audio.title))
    _thread.start_new_thread(compress_audio, (message.chat.id, file_id_info, message.audio.title))

  else:
    bot.send_message(message.chat.id, 'вас нет в VIP-списке, обратитесь к @berrymorr , приложив свой id: ' + str(message.from_user.id))


@bot.message_handler(content_types=['location'])
def process_location(message):
  bot.send_message(message.chat.id, str(message))



bot.polling()

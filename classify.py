# Tells speech from music by the sound itself, with YAMNet: Google's
# classifier of AudioSet's 521 classes, which the Dockerfile puts into the
# image as /yamnet.tflite. It takes 0.975 s of 16 kHz mono at a time; for
# each such frame here, whichever of its scores for Speech and for Music is
# the higher wins the frame.

import subprocess

import numpy as np
from ai_edge_litert.interpreter import Interpreter

MODEL = '/yamnet.tflite'
SPEECH, MUSIC = 0, 132  # rows of yamnet_class_map.csv
RATE = 16000
FRAME = 15600


# seconds of the file's sound from start on, as 16 kHz mono samples
def sound(path, start, seconds):
  out = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(start), '-t', str(seconds), '-i', path,
                        '-ac', '1', '-ar', str(RATE), '-f', 'f32le', '-'], capture_output=True, check=True).stdout
  return np.frombuffer(out, dtype=np.float32)


# how many frames of speech and of music: windows of seconds each, spread
# evenly over the file, so an intro or an outro does not decide it
def speech_and_music(path, duration, windows=6, seconds=10):
  model = Interpreter(model_path=MODEL)
  model.allocate_tensors()
  given = model.get_input_details()[0]['index']
  scores = model.get_output_details()[0]['index']
  span = max(duration - seconds, 0)
  speech = music = 0
  for w in range(windows):
    wave = sound(path, span * (w + 0.5) / windows, seconds)
    for i in range(0, max(len(wave) - FRAME, 0) + 1, FRAME):
      frame = np.zeros(FRAME, dtype=np.float32)
      part = wave[i:i + FRAME]
      frame[:len(part)] = part
      model.set_tensor(given, frame)
      model.invoke()
      s = model.get_tensor(scores)[0]
      if s[SPEECH] > s[MUSIC]:
        speech += 1
      else:
        music += 1
  return speech, music

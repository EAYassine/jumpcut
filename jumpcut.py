# Python script
from pydub import AudioSegment, silence
import argparse
import os
import json
import sys
import subprocess
import logging

log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s (Line: %(lineno)d)'
logging.basicConfig(filename='jumpcutpy.log', format=log_format)
logging.getLogger().setLevel(logging.DEBUG)

logging.debug("Running Python executable.")

# On Mac, pydub can use the system's "avbin" or "ffmpeg" if installed, but if neither is available, it can use the built-in audio support for certain formats.
# To avoid ffmpeg dependency, ensure you use only formats natively supported by pydub (like WAV, AIFF, etc.).
# If you want to force pydub to use native support, do not set AudioSegment.converter.
# If you get errors, convert your audio files to WAV or AIFF before running this script.
# The script will now force WAV/AIFF usage on Mac to avoid ffmpeg issues.

parser = argparse.ArgumentParser()
parser.add_argument("path")
parser.add_argument("jumpcutparams", default=None)
args = parser.parse_args()

# Values in milliseconds
jumpcut_params = { # Default parameters based on the Premiere extension GUI sliders.
    'silenceCutoff': -80,
    'removeOver': 1000,
    'keepOver': 300,
    'padding': 500,
    'in': None, 
    'out': None,
    'start': None
}

if args.jumpcutparams: # If parameters are passed, overwrite the defaults.
    input = json.loads(args.jumpcutparams)
    jumpcut_params.update(input)
    # Convert to ms
    jumpcut_params = {k: float(v) * 1000 for k, v in jumpcut_params.items()}
    jumpcut_params['silenceCutoff'] = int(jumpcut_params['silenceCutoff']) / 1000 # dB

THRESHOLD = int(jumpcut_params['silenceCutoff'])
PADDING = int(jumpcut_params['padding'])
MIN_SILENCE_LENGTH = int(jumpcut_params['removeOver'])
KEEP_OVER = int(jumpcut_params['keepOver'])
INPOINT = int(jumpcut_params['in'])
OUTPOINT = int(jumpcut_params['out'])
START = int(jumpcut_params['start'])

# Other parameters not controlled by the GUI
SEEK_STEP = 50

# File path and format config

# On Mac, force WAV/AIFF usage to avoid ffmpeg dependency
FILE_PATH = args.path
file_extension = os.path.splitext(FILE_PATH)[1].replace('.', '').lower()
if sys.platform == "darwin":
    if file_extension not in ["wav", "aiff"]:
        print("Error: On Mac, only WAV and AIFF files are supported. Please convert your audio file.")
        sys.exit(1)
    FILE_TYPE = file_extension
    # (Yassine) On Mac, pydub will use native support for WAV/AIFF, so ffmpeg is NOT required.
else:
    FILE_TYPE = file_extension

try:
    # Load file
    audio = AudioSegment.from_file(FILE_PATH, FILE_TYPE)
    # Crop audio based on in and out points
    audio = audio[INPOINT:OUTPOINT]
    CLIP_LENGTH = len(audio)
except Exception as e:
    logging.debug(e)
    raise

silences = []
try:
    silences = silence.detect_silence(audio, min_silence_len=MIN_SILENCE_LENGTH, seek_step=SEEK_STEP, silence_thresh=THRESHOLD)
except Exception as e:
    logging.debug(e)
    raise

# Add padding
to_remove = []
for i in range(len(silences)):

    # Check that this silence is not at the beginning of the file
    if silences[i][0] > 0:
        silences[i][0] = silences[i][0] + PADDING

    # Check that this silence is not at the end of the file
    if silences[i][1] < CLIP_LENGTH:
        silences[i][1] = silences[i][1] - PADDING
        
    if silences[i][1] <= silences[i][0]:
        to_remove.append(i)

# Remove silences that were padded out of existence
silences = [s for idx, s in enumerate(silences) if idx not in to_remove]

# Implement 'keep over' functionality. If the kept space between two silences is smaller than the keep over value,
# combine them into one long silence.
cleaned_silences = []
for i in range(0, len(silences), 2):
    if i + 1 < len(silences):
        if silences[i+1][0] - silences[i][1] < KEEP_OVER:
            cleaned_silences.append([silences[i][0], silences[i+1][1]])
        else:
            cleaned_silences.append(silences[i])
            cleaned_silences.append(silences[i+1])
    else:
        cleaned_silences.append(silences[i])

silences = cleaned_silences

# Instead of deleting silent parts, output cut regions and mark silent regions as 'disabled'.
# Output a list of segments: {"start": ..., "end": ..., "enabled": True/False}
segments = []
last_end = 0
for s in silences:
    # Non-silent segment before this silence
    if s[0] > last_end:
        segments.append({
            "start": (last_end/1000) + (START/1000),
            "end": (s[0]/1000) + (START/1000),
            "enabled": True
        })
    # Silent segment
    segments.append({
        "start": (s[0]/1000) + (START/1000),
        "end": (s[1]/1000) + (START/1000),
        "enabled": False
    })
    last_end = s[1]
# Add final non-silent segment if any
clip_end = len(audio) + (START if START else 0)
if last_end < clip_end:
    segments.append({
        "start": (last_end/1000) + (START/1000),
        "end": (clip_end/1000),
        "enabled": True
    })

print(json.dumps({"segments": segments}))

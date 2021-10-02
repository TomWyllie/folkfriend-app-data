"""Slimmed down version of the full ff_config.py file of global config
    parameters, containing the few values needed by the index builder."""

import string

# These are the extreme-most midi values that we choose to sample from the
#   generate spectrogram. The spectrogram is resampled to be linear in
#   midi space. These extreme values are inclusive, ie [LOW_MIDI, HIGH_MIDI].
MIDI_HIGH = 95  # B6 (1975.5 Hz), just over two octaves above violin open A
MIDI_LOW = 48  # C2 (130.81 Hz), an octave below middle C
MIDI_NUM = MIDI_HIGH - MIDI_LOW + 1  # =48

# abc...ABC
MIDI_MAP = string.ascii_letters[:MIDI_NUM]

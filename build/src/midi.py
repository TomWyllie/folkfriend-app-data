import csv
import logging
import math
import os
import subprocess
import sys

# import numpy as np
import py_midicsv
import ff_config

logging.basicConfig(level=logging.DEBUG,
                    format='[%(name)s:%(lineno)s] %(message)s')
log = logging.getLogger(os.path.basename(__file__))


class CSVMidiNoteReader(csv.DictReader):
    # TODO re-work this class, it probably shouldn't subclass csv.DictReader
    def __init__(self, *posargs, **kwargs):
        kwargs['fieldnames'] = ['track', 'time', 'type', 'channel',
                                'note', 'velocity']
        super().__init__(*posargs, **kwargs)
        self._notes = self.to_notes()

    def to_notes(self):
        """Convert these midi instructions to a list of Note objects"""

        active_notes = {}
        notes = []

        for record in self:
            if not record['note'] or not record['note'].isdigit():
                continue
            note = int(record['note'])
            time = int(record['time'])

            if record['type'] == 'Note_on_c':
                if note not in active_notes:
                    active_notes[note] = time
            elif record['type'] == 'Note_off_c':
                if note not in active_notes:
                    continue

                note_end = time
                note_start = active_notes.pop(note)

                notes.append(Note(start=note_start,
                                  end=note_end,
                                  pitch=note))

        return notes

    def to_midi_contour(self, tempo=125, start_seconds=None, end_seconds=None):
        """Quantise an arbitrary sequence of MIDI notes into all quavers.

        This results in some distortion of the melody but it should closely
        resemble the original; if both the training data and the data file
        builder use this same function then tune query searching should
        be relatively unaffected. Tune query searching with variable note
        durations would be a whole different kettle of fish."""

        # TODO this NEEDS test cases as it's a pretty weird function.

        midi_contour = []

        music_time = 0
        output_time = 0

        # Dummy quaver to compute duration of a single quaver at this tempo
        #   Remember default midi quaver duration is 240 ms (TODO always?)
        n = Note(0, 240, None)
        n.set_tempo(tempo)
        quaver_duration = n.duration

        for _, note in enumerate(self._notes):
            note.set_tempo(tempo)

            # Note occurs outwith range specified
            if start_seconds and note.end < 1000 * start_seconds:
                music_time = note.end
                output_time = note.end
                continue
            if end_seconds and note.start > 1000 * end_seconds:
                break
            else:
                music_time += note.duration

            # If we're ahead, skip notes until we're back in sync
            if music_time <= output_time:
                continue

            rel_duration = (note.duration / quaver_duration)
            if rel_duration.is_integer():
                output_time += note.duration
                midi_contour.extend([note.rel_pitch()] * int(rel_duration))
            elif rel_duration < 1.0:
                # In the output label everything is a quaver
                output_time += quaver_duration
                midi_contour.append(note.rel_pitch())
            else:
                # If we've fallen behind, round up, else round down
                round_f = math.ceil if music_time > output_time else math.floor
                rounded_int = round_f(rel_duration)
                output_time += rounded_int * quaver_duration
                midi_contour.extend([note.rel_pitch()] * rounded_int)

        return ''.join(ff_config.MIDI_MAP[n] for n in midi_contour)



class Note:
    def __init__(self, start, end, pitch):
        """Store a single note.

        All times are in milliseconds unless otherwise stated."""
        self._midi_start = start
        self._midi_end = end
        self.pitch = pitch

        self.start = self._midi_start
        self.end = self._midi_end

    def set_tempo(self, tempo):
        # Tempo specified in crotchet beats per minute
        us_per_crotchet = 60000000. / tempo

        # Beware that abc2midi does not adjust tempo by changing the times at
        #   which notes start or end, but by (sensibly) passing the tempo to
        #   the midi file itself which has a command to set the tempo, which
        #   must be interpreted by whatever reads the midi file (eg fluidsynth
        #   and this script).

        # This 480,000 comes from 125 bpm being the default tempo with the hard
        #   coded midi times (240ms = 1 quaver => 480000us = 1 crotchet).
        ms_scale_factor = us_per_crotchet / 480000

        self.start = ms_scale_factor * self._midi_start
        self.end = ms_scale_factor * self._midi_end

    @property
    def duration(self):
        return self.end - self.start

    def rel_pitch(self):
        pitch = self.pitch

        # We use LTE / GTE here because we need an amount of frequency
        #   content on both sides of the relevant pitch bin. See
        #   comment on inclusive range in to_pseudo_spectrogram.
        while pitch <= ff_config.MIDI_LOW:
            pitch += 12

        while pitch >= ff_config.MIDI_HIGH:
            pitch -= 12

        return pitch - ff_config.MIDI_LOW


def abc_to_midi(abc, midi_path, clean=True):
    """Convert ABC text into a midi file."""

    # Generate MIDI file with chords and actual instruments
    captured = subprocess.run([
        './abc2midi', '-',
        '-quiet', '-silent',
        '-NGUI' if clean else '',
        '-o', midi_path
    ],
        input=abc.encode('utf-8'),
        capture_output=True)
    stderr = captured.stderr.decode('utf-8')
    if stderr:
        log.warning(stderr, file=sys.stderr)


def midi_as_csv(midi_path):
    midi_lines = py_midicsv.midi_to_csv(midi_path)
    return [line.strip().replace(', ', ',') for line in midi_lines]

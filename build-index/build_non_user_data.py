import argparse
import collections
import json
import logging
import os
import pathlib
import re
import shutil
import tempfile

import requests
import ff_config
import midi
import abc_notation

from tqdm.contrib.concurrent import process_map

logging.basicConfig(level=logging.DEBUG,
                    format='[%(name)s:%(lineno)s] %(message)s')
log = logging.getLogger(os.path.basename(__file__))

STOP_WORDS = {"a", "an", "the", "at", "by", "for", "in", "of", "on",
              "to", "up", "and", "as", "but", "or", "nor"}
NON_WORD_CHARS = re.compile('[^a-zA-Z ]')


def build_non_user_data(p_dir):

    # Set up paths and directories

    midis_dir = os.path.join(p_dir, 'midis')
    tunes_path = os.path.join(p_dir, 'thesession-data.json')
    aliases_path = os.path.join(p_dir, 'thesession-aliases.json')
    non_user_data_path = os.path.join(p_dir, 'folkfriend-non-user-data.json')

    pathlib.Path(p_dir).mkdir(parents=True, exist_ok=True)
    pathlib.Path(midis_dir).mkdir(parents=True, exist_ok=True)

    # Download raw thesession.org data dumps from github

    download_thesession_data(tunes_path)
    with open(tunes_path, 'r') as f:
        thesession_data = json.load(f)

    download_thesession_aliases(aliases_path)
    with open(aliases_path, 'r') as f:
        thesession_aliases = json.load(f)

    # We convert the ABC files to a form more directly usable by a search
    #   engine. ABC files contain non-trivial syntax that must be properly
    #   parsed and it is unsuitable to require this running on the edge
    #   before first use, so we do this once and distribute as part of the
    #   non-user data file.

    # But - we would still like the original ABC string as it is used to
    #   render the sheet music (and going back from our queryable
    #   representation into ABC is even harder than the reverse as that's
    #   a non-unique mapping). However there's some other information in the
    #   JSON file from thesession.org's GitHub that isn't useful for us,
    #   which we now get rid of.

    # One field we get rid of *for each setting* is the name, because it's
    #   identical for all settings of the same tune, so only needs stored
    #   once. We store this with the aliases, because that's where the names
    #   of tunes are kept.

    log.info('Gathering tune name aliases')
    gathered_aliases = gather_aliases(thesession_aliases, thesession_data)

    log.info('Creating cleaned version of input data file')
    cleaned_thesession_data = clean_thesession_data(thesession_data)

    multiprocessing_input = [(setting, midis_dir) for setting in cleaned_thesession_data]

    # The heavy lifting is done here
    contours = process_map(
        generate_midi_contour,
        multiprocessing_input,
        desc='Converting ABC text to contour string',
        chunksize=8)

    # Convert settings/contours into one dictionary of setting_id: setting
    settings = {}

    for setting in cleaned_thesession_data:
        settings[setting['setting_id']] = setting

        # Key doesn't need to be also stored on value
        del settings[setting['setting_id']]['setting_id']

    # It's possible that a contour doesn't exist for some setting, but
    #   in that case we still want to keep the setting because it might
    #   be useful to have the sheet music even if it isn't queryable.
    for setting_id, contour in contours:
        settings[setting_id]['contour'] = contour

    # Put everything together
    non_user_data = {
        'settings': settings,
        'aliases': gathered_aliases,
    }

    print(f'Writing {non_user_data_path}')
    with open(non_user_data_path, 'w') as f:
        json.dump(non_user_data, f)


def clean_thesession_data(tune_data):
    # Convert types and discard redundant data
    for i, _ in enumerate(tune_data):
        del tune_data[i]['date']
        del tune_data[i]['username']
        del tune_data[i]['name']
        # "type" is a common programming keyword, causes issues later.
        tune_data[i]['dance'] = tune_data[i]['type']
        del tune_data[i]['type']

        # The keys are still stored as strings because that's all JSON can do
        tune_data[i]['tune_id'] = int(tune_data[i]['tune_id'])

    return tune_data


def gather_aliases(alias_records, tune_data):
    # The aliases.json file is inefficiently structured for network
    #   distribution and we can condense it somewhat. We also merge
    #   the "name" field of each tune into aliases, so that all the
    #   names are stored in one place, and each name/alias is stored
    #   exactly once.

    aliases = collections.defaultdict(list)

    # Add 'name' fields so that the first alias is always the 'name'
    #   on the session. This is usually the most common name for the
    #   tune.
    for i, _ in enumerate(tune_data):
        tid = tune_data[i]['tune_id']
        alias = tune_data[i]['name']
        aliases[tid].append(alias.lower())

    # Add aliases from alias data proper
    for alias_record in sorted(alias_records, key=lambda r: int(r['tune_id'])):
        tid = alias_record['tune_id']
        alias = alias_record['alias']
        aliases[tid].append(alias.lower())

    for tid in aliases:
        aliases[tid] = deduplicate_aliases(aliases[tid])

    return aliases


def deduplicate_aliases(aliases):

    seen_aliases = set()
    deduped_aliases = []

    # Remove based on minor differences in punctuation / stopwords
    for alias in aliases:
        cleaned_alias = clean_alias(alias)
        if cleaned_alias not in seen_aliases:
            seen_aliases.add(cleaned_alias)
            deduped_aliases.append((cleaned_alias, alias))

    deduped_aliases = sorted(deduped_aliases, key=lambda c: len(c[0]))

    # Remove subsets. Requires sorting by length.
    deduped_aliases_no_subsets = []
    for i, (cleaned, alias) in enumerate(deduped_aliases):
        is_subset = (cleaned < c for (c, _) in deduped_aliases[i:])
        if not any(is_subset):
            deduped_aliases_no_subsets.append(alias)

    # Back to alphabetical at the end
    return sorted(deduped_aliases_no_subsets)


def clean_alias(alias):
    # Remove redundancy from each string
    alias = alias.lower()
    alias = NON_WORD_CHARS.sub('', alias)
    alias = alias.split()
    alias = (w for w in alias if w and w not in STOP_WORDS)
    alias = ((w[:-1] if w.endswith('s') else w)
             for w in alias)  # Ignore plurals

    # This American spelling pops up a lot. Retain the British spelling
    #   for alias purposes.
    alias = ((w if not w == 'favorite' else 'favourite') for w in alias)
    return frozenset(sorted(alias))


def generate_midi_contour(args):
    setting, midis_path = args

    abc_header = [
        'X:1',
        'T:',
        f'M:{setting["meter"].strip()}',
        f'K:{setting["mode"].strip()}'
    ]
    abc_body = setting['abc'].replace(
        '\\', '').replace(
        '\r', '').split('\n')
    abc = '\n'.join(abc_header + abc_body)

    midi_out_path = os.path.join(midis_path,
                                 f'{setting["setting_id"]}.midi')

    if not os.path.exists(midi_out_path):
        midi.abc_to_midi(abc, midi_out_path)

    midi_events = midi.midi_as_csv(midi_out_path)
    note_contour = midi.CSVMidiNoteReader(midi_events).to_midi_contour()

    return setting['setting_id'], note_contour


def download_thesession_aliases(aliases_path):
    aliases_url = ff_config.THESESSION_DATA_URL_.replace(
        'tunes.json', 'aliases.json'
    )
    download_thesession_data(aliases_path, aliases_url)


def download_thesession_data(tunes_path,
                             data_url=ff_config.THESESSION_DATA_URL_):
    if not os.path.exists(tunes_path):
        # In case we are running trial and error experiments we might be
        #   deleting and remaking many datasets in a short period.
        td = tempfile.gettempdir()
        temp_tunes_path = os.path.join(td, os.path.basename(tunes_path))
        if os.path.exists(temp_tunes_path):
            print(f'Found cached {temp_tunes_path}...')
            shutil.copy(temp_tunes_path, tunes_path)
            return

        # Otherwise download it fresh from the github repository.
        print(f'Downloading from {data_url}...')
        r = requests.get(data_url)
        with open(tunes_path, 'wb') as f:
            f.write(r.content)

        # Store to temp in case we need it later
        shutil.copy(tunes_path, temp_tunes_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir',
                        default='./index-data',
                        help='Directory to contain the dataset files in')
    args = parser.parse_args()
    build_non_user_data(args.dir)
import argparse
import os
import requests
import logging

logging.basicConfig(level=logging.DEBUG,
                    format='[%(name)s:%(lineno)s] %(message)s')
log = logging.getLogger(os.path.basename(__file__))


DATA_URL = 'https://raw.githubusercontent.com/adactio/TheSession-data/main/json/{}.json'


def download_data(parent_dir, data_type):
    data_url = DATA_URL.format(data_type)
    data_file_path = os.path.join(parent_dir, 'data', data_type + '.json')

    r = requests.get(data_url)
    with open(data_file_path, 'wb') as f:
        log.info(f'Writing {data_file_path}')
        f.write(r.content)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'dir', help='Parent directory for the `data` directory')
    args = parser.parse_args()
    download_data(args.dir, 'tunes')
    download_data(args.dir, 'aliases')

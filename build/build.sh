#!/bin/bash

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH

ABC_VER=`./abc2midi -ver`

if [[ "$ABC_VER" == "4.84 January 20 2023 abc2midi" ]]
then
    echo "Found abc2midi version 4.84"
else
	echo "Please ensure abc2midi version 4.84 (January 20 2023) is installed."
	echo "See https://github.com/sshlien/abcmidi"
	echo "Provide this executable as 'abc2midi' in the build directory."
    exit
fi

# Ensure file storing previous hashes existss
mkdir -p data/

OLD_HASH=data/old_hash.txt
NEW_HASH=data/new_hash.txt

touch $OLD_HASH
sha1sum data/*.json &> $NEW_HASH 

# Python virtualenv
. env.sh

python src/download_thesession_data.py $SCRIPTPATH

if cmp --silent -- "$OLD_HASH" "$NEW_HASH"
then
    echo ""
    echo "thesession.org data has not changed. Exiting."
    echo ""
    exit 1
else 
    cat $NEW_HASH > $OLD_HASH
    python src/build_non_user_data.py $SCRIPTPATH
    mv data/folkfriend-non-user-data.json ../public/
    mv data/nud-meta.json ../public/
    cd ..
    git add public/folkfriend-non-user-data.json
    git add public/nud-meta.json
    git commit -m "`cat public/nud-meta.json`"
    git push
    firebase deploy
    deactivate
fi

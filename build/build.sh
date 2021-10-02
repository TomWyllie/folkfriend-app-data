SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH

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
    mv data/folkfriend-non-user-data.json ..
    mv data/nud-meta.json ..
fi

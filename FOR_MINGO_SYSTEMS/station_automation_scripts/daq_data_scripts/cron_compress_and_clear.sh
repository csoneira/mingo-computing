#!/bin/bash
# Purpose: Cron compress and clear.

if [[ "$1" == "-h" ]];then
    echo "Usage:"
    echo "Function to compress every datafile that is not compressed already. It is called by join.sh"
    exit 0
fi

echo "**************************"
echo "**************************"
echo "Starting the compression of all uncompressed datafile"

# Specify the directory where your data files are located
data_dir="/media/externalDisk/gate/system/devices/TRB3/data/daqData/asci"

# Check if the directory exists
if [ ! -d "$data_dir" ]; then
  echo "Directory $data_dir does not exist."
  exit 1
fi

# Change to the data directory
cd "$data_dir" || exit 1

# Compress all data files that are not already compressed
echo "**************************"
echo "**************************"
j=1

for file in *.dat; do
    echo "Searching... ($j)"
    j=$((j + 1))

    for ext in dat; do
        for f in *.$ext; do
            if [ -f "$f" ] && [ "${f##*.}" != "gz" ]; then
                echo "Compressing:"
                tar -czvf "$f.tar.gz" "$f"
                rm "$f"
                echo "**************************"
            fi
        done
    done
done

echo "Compression complete."
echo "**************************"
echo "**************************"

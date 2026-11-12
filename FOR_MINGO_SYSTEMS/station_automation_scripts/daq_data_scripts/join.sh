#!/bin/bash
# Purpose: Join workflow for daq data scripts.

if [[ "$1" == '-h' ]]; then
  echo "Usage:"
  echo "A function that asks for a date range in YYMMDD YYMMDD and joins and compresses all data inside that range. It is called by cron_join_one_day.sh. It calls compress_and_clear.sh."
  exit 0
fi

cd /media/externalDisk/gate/system/devices/TRB3/data/daqData/asci
#pwd

function PrintBar() {
  local barWidth=70
  local progress="$1"
  local pos=$(( (barWidth * progress) / 100 ))
  local progressBar="["

  for ((i=0; i<barWidth; i++)); do
    if [ $i -lt $pos ]; then
      progressBar+="="
    elif [ $i -eq $pos ]; then
      progressBar+=">"
    else
      progressBar+=" "
    fi
  done

  if ((progress > 100)); then
    progress=100
  fi
  progressBar+="] $progress %"
  # Print carriage return to overwrite the line
  echo -ne "\r"
  # Print the progress bar
  echo -n "$progressBar"
  # Flush the output
  echo -ne "\033[0K"
}

# Function to convert YYMMDD to YYDDD
date_to_yyddd() {
    input_date="$1"
    year="${input_date:0:2}"
    month="${input_date:2:2}"
    day="${input_date:4:2}"
    # Use 'date' command to calculate day of the year
    day_of_year=$(date -d "$year-$month-$day" +%j)
    # Combine year and day of the year
    yyddd="${year}${day_of_year}"
    echo "$yyddd"
}

# Prompt the user for date range in YYDDD format
#read -p "Enter start date (YYMMDD): " start_date
#read -p "Enter end date (YYMMDD): " end_date
start_date=$1
end_date=$2

input_date_start="$start_date"  # YYMMDD format
start_date=$(date_to_yyddd "$input_date_start")

input_date_end="$end_date"  # YYMMDD format
end_date=$(date_to_yyddd "$input_date_end")

#echo "Start date: $start_date"

# Prompt the user for the Trigger type (0, 1, or 2)
#echo "Enter Trigger type (0, 1, or 2):"
#echo -e "\t - 0: all events"
#echo -e "\t - 1: only coincidence events"
#echo -e "\t - 2: only self-trigger events"
#read trigger_type
echo "***********************************"
#echo "Reading only coincidence events"
echo "Reading all kinds of events"
trigger_type=0

# Create an array to store matching files
matching_files=()

# Define the output file
output_file="merged-from-$input_date_start-to-$input_date_end.txt"

if [[ $input_date_start == $input_date_end ]]; then
    output_file="merged-$input_date_start.txt"
fi

echo "***********************************"
# Iterate through files in the directory
for file in *.dat*; do
  # Extract the date from the filename using regular expressions
  if [[ "$file" =~ ([0-9]{2}[0-9]{3})[0-9]{6}\.dat ]]; then
    file_date="${BASH_REMATCH[1]}"
    # Check if the file date is within the specified range
    if [[ "$file_date" -ge "$start_date" && "$file_date" -le "$end_date" ]]; then
      matching_files+=("$file")
    fi
  fi
done

# Check if any matching files were found
if [ ${#matching_files[@]} -eq 0 ]; then
  echo "No matching files found in the specified date range."
  exit 1
fi

# Create an empty output file
> "$output_file"
new_file="ancillary"
> "$new_file"

echo "***********************************"
# Iterate through matching files and append data to the output file
for file in "${matching_files[@]}"; do
  if [[ $file == *.tar.gz ]]; then
    base_name=$(basename "$file" .tar.gz)
    # Check if the base_name is already in matching_files
    if [[ ! " ${matching_files[@]} " =~ " ${base_name} " ]]; then
      # Extract the files from the tar.gz archive
      echo "Found and extracted"
      du -h "$file"
      tar -xzf "$file"
      matching_files+=("$file")
      matching_files+=("$base_name")
    else
      echo "$base_name is already uncompressed."
    fi
  fi
done

echo "***************************************************"
echo " Starting to create the merged datafile ***********"
echo "***************************************************"

#k=0
#total_number_of_files=${#matching_files[@]}
#for file in "${matching_files[@]}"; do
#  if [[ $file == *.dat ]]; then
#     #echo "$file"
#     # Copy the content of each .dat file to the new file
#     cp $file $new_file
#     # Display the size of the new file
#     du -h $file
#     # Start replacing specific patterns
#     echo "Starting to change zeroes"
#     sed -i 's/0000\.0000/0/g' $new_file
#     # Replace patterns like 0123 with 123
#     echo "Removing non significant digits"
#     sed -i -E 's/\b0+([0-9]+)/\1/g' $new_file
#     # Replace one or more spaces with a comma
#     echo "Replacing zeros with commas"
#     sed -i -E 's/ +/,/g' $new_file
#     # Print the first line of the new file
#     #head -n 1 $new_file
#     # Display the size of the new file again
#     du -h $new_file
#     cat $new_file >> $output_file
#     rm $new_file
#     du -h $output_file
#  fi
#  progress=$(($k*100))
#  progress=$(($progress/$total_number_of_files))
#  #echo "Progress="
#  #echo $progress
#  PrintBar $progress
#  printf "\n"
#  ((k++))
#  echo "***********************************************************************"
#done

k=0
total_number_of_files=${#matching_files[@]}
for file in "${matching_files[@]}"; do
  if [[ $file == *.dat ]]; then
     # Copy the content of each .dat file to the new file
     cp $file $new_file
     # Display the size of the new file
     du -h $file

     # Perform all sed operations in a single call
     echo "Starting to process file"
     sed -i -E '
       s/0000\.0000/0/g;
       s/\b0+([0-9]+)/\1/g;
       s/ +/ /g
       #s/([0-9]+)-([0-9]+)/\1,-\2/g
     ' $new_file

     #sed -i 's/0000\.0000/0/g' $new_file
     #sed -i -E 's/([0-9])2024/\1\n2024/g' $new_file

     # Display the size of the new file again
     du -h $new_file

     awk -v trigger="$trigger_type" '$7 == trigger || trigger == 0' $new_file >> $output_file
     rm $new_file
     du -h $output_file
  fi

  progress=$(($k * 100 / $total_number_of_files))
  PrintBar $progress
  printf "\n"
  ((k++))
  echo "***********************************************************************"
done

# Compress the output file and remove it
echo "***********************************"
echo "Merged and compressed file:"
du -h $output_file
tar -czf $output_file.tar.gz $output_file
du -h $output_file.tar.gz
echo "***********************************"
echo "***********************************"
#rm $output_file

# Compress and clear all datafiles that are not compressed
echo "Executing compress_and_clear.sh"
bash ~/caye_software/daq_data_scripts/compress_and_clear.sh

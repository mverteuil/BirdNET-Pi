#!/usr/bin/env bash
# Exit when any command fails
#set -x
set -e
# Keep track of the last executed command
trap 'last_command=$current_command; current_command=$BASH_COMMAND' DEBUG
# Echo an error message before exiting
trap 'echo "\"${last_command}\" command exited with code $?."' EXIT
# Remove temporary file
trap 'rm -f $TMPFILE' EXIT

source /etc/birdnet/birdnet.conf

# Set Variables
TMPFILE=$(mktemp)
# SCAN_DIRS are all directories marked "Analyzed"
SCAN_DIRS=($(find ${ANALYZED} -type d | sort ))

# This sets our while loop integer iterator 'a' -- it first checks whether
# there are any extractions, and if so, this instance of the extraction will
# start the 'a' value where the most recent instance left off.
# Ex: If the last extraction file is 189-%date%species.wav, 'a' will be 190.
# Else, 'a' starts at 1
if [ "$(find ${EXTRACTED} -name '*.wav' | wc -l)" -ge 1 ];then
  a=$(( $( find "${EXTRACTED}" -name '*.wav' \
    | awk -F "/" '{print $NF}' \
    | cut -d'-' -f1 \
    | sort -n \
    | tail -n1 ) + 1 ))
else
  a=1
fi

echo "Starting numbering at ${a}"

for h in "${SCAN_DIRS[@]}";do
  echo "Creating the TMPFILE"
  # The TMPFILE is created from each "Selection" txt file BirdNET creates
  # within each "Analyzed" directory
  #  Field 1: Original WAVE file name
  #  Field 2: Extraction start time in seconds
  #  Field 3: Extraction end time in seconds
  #  Field 4: New WAVE file name to use
  #  Field 5: The species name
  # Iterates over each "Analyzed" directory
  for i in $(find ${h} -name '*txt' | sort );do 
    # Iterates over each '.txt' file found in each "Analyzed" directory
    # to create the TMPFILE
    sort -k 6n "$i" \
    | awk '/Spect/ {print}' \
    >> $TMPFILE
  done

  # The extraction reads each line of the TMPFILE and sets the variables ffmpeg
  # will use.
  while read -r line;do
    a=$a
    DATE="$(echo "${line}" \
	   | awk '{print $5}' \
	   | awk -F- '{print $1"-"$2"-"$3}')"
    OLDFILE="$(echo "${line}" | awk '{print $5}')" 
    START="$(echo "${line}" | awk '{print $6}')" 
    END="$(echo "${line}" | awk '{print $7}')" 
    SPECIES=""$(echo ${line//\'} \
	      | awk '{for(i=11;i<=NF;++i)printf $i""FS ; print ""}' \
	      | cut -d'0' -f1 \
	      | xargs)""
    NEWFILE="${SPECIES// /_}-${OLDFILE}" 
    NEWSPECIES_BYDATE="${EXTRACTED}/By_Date/${DATE}/${SPECIES// /_}"
    NEWSPECIES_BYSPEC="${EXTRACTED}/By_Species/${SPECIES// /_}"

    # If the extracted file already exists, increment the 'a' variable once
    # but move onto the next line of the TMPFILE for extraction.
    if [[ -f "${NEWSPECIES_BYDATE}/${a}-${NEWFILE}" ]];then
      echo "Extraction exists. Moving on"
      a=$((a+1))
      continue
    fi


    echo "Checking for ${h}/${OLDFILE}"
    # Before extracting the "Selection," the script checks to be sure the
    # original WAVE file still exists.
    [[ -f "${h}/${OLDFILE}" ]] || continue


    echo "Checking for ${NEWSPECIES_BYDATE}"
    # If a directory does not already exist for the species (by date),
    # it is created
    [[ -d "${NEWSPECIES_BYDATE}" ]] || mkdir -p "${NEWSPECIES_BYDATE}"


    echo "Checking for ${NEWSPECIES_BYSPEC}"
    # If a directory does not already exist for the species (by-species),
    # it is created.
    [[ -d "${NEWSPECIES_BYSPEC}" ]] || mkdir -p "${NEWSPECIES_BYSPEC}"


    # If there are already 20 extracted entries for a given species
    # for today, remove the oldest file and create the new one.
    if [[ "$(find ${NEWSPECIES_BYDATE} | wc -l)" -ge 21 ]];then
      echo "20 ${SPECIES}s, already! Removing the oldest by-date and making a new one"
      cd ${NEWSPECIES_BYDATE} || exit 1
      ls -1t . | tail -n +21 | xargs -r rm -vv
    fi   

    echo "Extracting audio . . . "
    # If the above tests have passed, then the extraction happens.
    # After creating the extracted files by-date, and a directory tree 
    # structured by-species, symbolic links are made to populate the new 
    # directory.

    ffmpeg -hide_banner -loglevel error -nostdin -i "${h}/${OLDFILE}" \
      -acodec copy -ss "${START}" -to "${END}"\
        "${NEWSPECIES_BYDATE}/${a}-${NEWFILE}"
    if [[ "$(find ${NEWSPECIES_BYSPEC} | wc -l)" -ge 21 ]];then
      echo "20 ${SPECIES}s, already! Removing the oldest by-species and making a new one"
      cd ${NEWSPECIES_BYSPEC} || exit 1
      ls -1t . | tail -n +21 | xargs -r rm -vv
      ln -fs "${NEWSPECIES_BYDATE}/${a}-${NEWFILE}"\
        "${NEWSPECIES_BYSPEC}/${a}-${NEWFILE}"
      echo "Success! New extraction for ${SPECIES}"
    else
      ln -fs "${NEWSPECIES_BYDATE}/${a}-${NEWFILE}"\
        "${NEWSPECIES_BYSPEC}/${a}-${NEWFILE}"
    fi   


    # Finally, 'a' is incremented by one to allow multiple extractions per
    # species per minute.
    a=$((a + 1))

  done < "${TMPFILE}"
  
  echo -e "\n\n\nFINISHED!!! Processed extractions for ${h}"
  # Once each line of the TMPFILE has been processed, the TMPFILE is emptied
  # for the next iteration of the for loop.
  >"${TMPFILE}"

  # Rename files that have been processed so that they are not processed on the
  # next extraction.
  [[ -d "${PROCESSED}" ]] || mkdir "${PROCESSED}"
  echo "Moving processed files to ${PROCESSED}"
  mv -v ${h}/* ${PROCESSED} || continue
done

echo "Linking Processed files to "${EXTRACTED}/Processed" web directory"
# After all audio extractions have taken place, a directory is created to house
# the original WAVE and .txt files used for this extraction processs.
if [[ ! -L ${EXTRACTED}/Processed ]] || [[ ! -e ${EXTRACTED}/Processed ]];then
  ln -sf ${PROCESSED} ${EXTRACTED}/Processed
fi
  


# That's all!
echo "Finished -- the extracted sections are in:
$(find -L ${EXTRACTED} -maxdepth 1)"

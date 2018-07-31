#! /bin/bash

filename="T_MEMPRINT"
lines_read=0

for i in "1"
do
	if test -f "$filename$i.hex"
	then
		echo "$filename$i.hex"
		while IFS= read line
		do
			echo $line
			lines_read=$((lines_read + 1))
		done <"$filename$i.hex"
	else
		echo "Did not match!"
	fi
done

echo "Read a total of $lines_read lines"

#!/bin/sh

PYV=$(python -c 'import sys; print(sys.version_info[:1][0])')

if [ "$PYV" -eq "2" ]
then
    python3 script/cicd.py $*
else
    python script/cicd.py $*
fi

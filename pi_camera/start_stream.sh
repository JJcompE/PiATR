#!/bin/sh
# Run on Pi

echo "Starting stream ..."
# echo "Framerate: ${FRAMERATE},  Width: ${WIDTH}, Height: ${HEIGHT}"

rpicam-vid -t 0 \
  --width 1536 \
  --height 864 \
  --framerate 60 \
  --codec h264 \
  --inline \
  -o udp://10.50.12.12:8888 # laptop IP
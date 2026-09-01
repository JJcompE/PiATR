#!/bin/sh
# Run on Pi

echo "Starting stream ..."
# echo "Framerate: ${FRAMERATE},  Width: ${WIDTH}, Height: ${HEIGHT}"

# # Basic stream to laptop endpoint
# rpicam-vid -t 0 \
#   --width 1536 \
#   --height 864 \
#   --framerate 60 \
#   --codec h264 \
#   --inline \
#   -o udp://10.50.12.12:8888 # laptop IP

# Stream to ffmpeg for MediaMTX endpoint
rpicam-vid \
    -t 0 \
    --width 1536 \
    --height 864 \
    --framerate 60 \
    --codec h264 \
    --inline \
    -o - \
  | ffmpeg \
      -f h264 \
      -i pipe:0 \
      -c:v copy \
      -f mpegts \
      "udp://10.50.12.12:8888?pkt_size=1316"
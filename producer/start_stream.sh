#!/bin/sh

echo "Starting stream ..."
echo "Framerate: ${FRAMERATE},  Width: ${WIDTH}, Height: ${HEIGHT}"

rpicam-vid \
  -t 0 \
  --inline \
  --width ${WIDTH} \
  --height ${HEIGHT} \
  --framerate ${FRAMERATE} \
  --bitrate ${BITRATE} \
  -n \
  -o - \
| gst-launch-1.0 -v \
    fdsrc ! \
    h264parse ! \
    rtph264pay config-interval=1 pt=96 ! \
    udpsink host=${CLIENT_IP} port=${PORT} sync=false
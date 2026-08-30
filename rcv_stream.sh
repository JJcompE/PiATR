#!/bin/sh
# Run on laptop

ffplay -f h264 \
  -fflags nobuffer \
  -flags low_delay \
  -framedrop \
  udp://0.0.0.0:8888
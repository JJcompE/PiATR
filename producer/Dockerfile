FROM debian:bookworm

RUN apt-get update && apt-get install -y \
    streamer1.0-tools \
    gstreamer1.0-plugins-base \
    gstreamer1.0-plugins-good \
    gstreamer1.0-plugins-bad \
    gstreamer1.0-libav \
    libcamera-tools \
    && rm -rf /var/lib/apt/lists/*

COPY start_stream.sh /start_stream.sh
RUN chmod +x /start_stream.sh

ENTRYPOINT [ "/start_stream.sh" ]
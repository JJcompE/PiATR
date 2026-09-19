# PiATR

PiATR is a Raspberry Pi live-monitoring and object-detection system. It captures video from a Raspberry Pi camera, runs EfficientDet-Lite0 inference on a low-resolution stream, overlays detections on the main video, and publishes annotated H.264 video for browser playback over WebRTC.

The repository contains two parts:

- **`pi_camera`**: Raspberry Pi camera capture, inference, annotation, encoding, and MediaMTX publishing.
- **`video-streaming-interface`**: Next.js browser viewer plus optional Docker-based gateway configuration.

## Architecture

```text
Raspberry Pi camera
        |
        +-- Main stream: 1280x720 at 30 FPS
        +-- Lores stream: 320x320 YUV420 for inference
                    |
             EfficientDet-Lite0
                    |
       Detection overlay and statistics
                    |
       FFmpeg / H.264 / MPEG-TS over UDP
                    |
          MediaMTX on UDP port 9000
                    |
       WebRTC WHEP endpoint on port 8889
                    |
          Next.js Signal View browser
```

The detector runs inference in a worker thread so the camera and encoding loop can continue handling the main video stream. Detection output includes filtered labels, bounding boxes, centroids, and runtime statistics.

## Prerequisites

### Raspberry Pi

- Raspberry Pi 4B or newer
- Compatible Raspberry Pi camera
- Raspberry Pi OS or another compatible Debian-based distribution
- Python 3, Picamera2, OpenCV, NumPy, and FFmpeg
- LiteRT (`ai_edge_litert`)
- The EfficientDet-Lite0 INT8 model

The detector expects the model at:

```text
/home/pi/models/efficientdet_lite0_int8.tflite
```

The deployment script installs the model in the remote user's home directory, so the effective path follows that user's home directory.

### Streaming host

- Node.js 18 or newer
- npm or pnpm
- Docker and Docker Compose, if using `video-streaming-interface/gateway`

## Automated Raspberry Pi Deployment

`deploy_and_install.sh` deploys the checked-in MediaMTX binary and configuration, model, detector scripts, Python environment, and systemd services to a Raspberry Pi over SSH.

Before running it:

1. Ensure the destination Pi is reachable over SSH as user `pi`.
2. Ensure the repository contains `pi_camera/mtx/mediamtx`, the model, detector scripts, and service files.
3. Ensure `ssh-copy-id` can install the generated key on the destination.

Run from the repository root:

```bash
chmod +x deploy_and_install.sh
./deploy_and_install.sh -i <raspberry-pi-ip-or-hostname>
```

The script creates or uses `~/.ssh/id_rsa_pi`, copies the deployment artifacts, creates `~/vision-env` with system packages available, installs LiteRT and NumPy 1.26.4, and enables both services:

```text
piatr-mediamtx.service
piatr-detector.service
```

The installed services use these paths on the Pi:

```text
/usr/local/bin/mediamtx
/usr/local/etc/mediamtx.yml
/home/pi/vision-env/bin/python /home/pi/detector.py
```

Check the deployment with:

```bash
ssh pi@<raspberry-pi-ip-or-hostname> 'systemctl status piatr-mediamtx piatr-detector'
ssh pi@<raspberry-pi-ip-or-hostname> 'journalctl -u piatr-mediamtx -u piatr-detector -f'
```

To restart or stop the pipeline:

```bash
ssh pi@<raspberry-pi-ip-or-hostname> 'sudo systemctl restart piatr-mediamtx piatr-detector'
ssh pi@<raspberry-pi-ip-or-hostname> 'sudo systemctl stop piatr-detector piatr-mediamtx'
```

## Manual Raspberry Pi Setup

Install system dependencies on Raspberry Pi OS:

```bash
sudo apt update
sudo apt install -y \
  python3-picamera2 \
  python3-opencv \
  python3-venv \
  python3-pip \
  ffmpeg
```

Create the Python environment and install runtime packages:

```bash
python3 -m venv --system-site-packages ~/vision-env
source ~/vision-env/bin/activate
python -m pip install --upgrade pip
python -m pip install ai-edge-litert "numpy==1.26.4"
```

Install the model and detector files in the locations expected by the script:

```bash
mkdir -p ~/models
# Copy efficientdet_lite0_int8.tflite to ~/models/
# Copy pi_camera/scripts/detector.py and globals.py to ~/
```

For a manual run, start MediaMTX with the Pi configuration and then start the detector from the home directory:

```bash
sudo /usr/local/bin/mediamtx /usr/local/etc/mediamtx.yml
source ~/vision-env/bin/activate
python ~/detector.py
```

The detector publishes MPEG-TS to `udp://127.0.0.1:9000?pkt_size=1316`. The Pi MediaMTX configuration enables WebRTC on TCP port `8889`, with ICE/UDP on port `8189`.

## Web Viewer

Install and run the Next.js application:

```bash
cd video-streaming-interface
pnpm install
pnpm dev
```

npm is also supported:

```bash
npm install
npm run dev
```

Open `http://localhost:3000`. The Signal View page accepts a WHEP endpoint in the source configuration field. Its current default is:

```text
http://10.50.1.1:8889/camera/whep
```

Replace `10.50.1.1` with the reachable IP address of the Pi or gateway. The browser viewer establishes a receive-only WebRTC connection and supports mute/unmute, fullscreen, connection status, and gateway error reporting.

## Optional Docker Gateway

The files under `video-streaming-interface/gateway` contain the configuration for an optional Docker Compose stack with MediaMTX, Janus, and a proxy service. The Compose file exposes the proxy on port `8889` with the `/camera/whep` path, Janus HTTP/WebSocket ports `8088` and `8188`, and MediaMTX RTSP/RTMP ports `8554` and `8888`.

The checked-in proxy directory currently contains the image definition and dependency manifest; add the proxy runtime entrypoint and lockfile before building this stack with Docker Compose. Once the gateway is complete, start it with:

```bash
cd video-streaming-interface/gateway
docker compose up --build
```

Configure the viewer endpoint to match the host running the gateway, for example:

```text
http://<gateway-host>:8889/camera/whep
```

The Pi-side deployment and the Docker gateway are separate deployment options. Use the endpoint that corresponds to the component providing the WHEP handshake for your network.

## Repository Layout

```text
pi_camera/
  models/       EfficientDet-Lite0 INT8 model
  mtx/          MediaMTX binary and Raspberry Pi configuration
  scripts/      Detector and label configuration
  services/     systemd unit files
video-streaming-interface/
  app/          Next.js viewer
  gateway/      Optional MediaMTX, Janus, and proxy stack
  public/       Static assets
  package.json  Next.js scripts and dependencies
deploy_and_install.sh  Raspberry Pi deployment script
```
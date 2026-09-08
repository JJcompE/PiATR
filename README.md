# PiATR

PiATR is a Raspberry Pi-based live monitoring and object-detection system. It captures video from a Raspberry Pi camera, runs lightweight inference with a TensorFlow Lite EfficientDet model, overlays detections on the live feed, and streams the annotated video to a browser through a local media and WebRTC gateway stack.

The project is divided into two main components:

* **`pi_camera`** — Raspberry Pi-side camera capture, object detection, annotation, and video publishing.
* **`video-streaming-interface`** — Browser client and local media/WebRTC gateway stack for playback.

---

# Summary

PiATR is a compact edge-vision pipeline built around a Raspberry Pi camera and TensorFlow Lite EfficientDet inference.

It combines:

```text
Camera Capture
      +
Object Detection
      +
Detection Overlay
      +
H.264 Encoding
      +
Local Video Transport
      +
Media Gateway
      +
WebRTC Playback
```

The system is designed to capture, detect, annotate, relay, and display live video while keeping the computationally expensive inference stage separate from the real-time camera pipeline.

---

## Data Flow

The end-to-end flow is:

1. The Raspberry Pi camera captures video frames.
2. Picamera2 provides a main stream and a low-resolution inference stream.
3. `detector.py` runs EfficientDet-Lite0 against the low-resolution frames.
4. Detection results are filtered according to the configured target classes.
5. Bounding boxes, centroids, labels, and runtime statistics are drawn onto the main video frame.
6. FFmpeg encodes the annotated video as H.264.
7. The encoded stream is sent as MPEG-TS over UDP.
8. MediaMTX and the gateway stack receive and expose the stream.
9. The stream is made available through a WHEP/WebRTC endpoint.
10. The Next.js application establishes a WebRTC connection.
11. The live annotated video is displayed in the browser.

---

# Prerequisites

## Raspberry Pi

Recommended hardware and software:

* Raspberry Pi 4B or newer.
* Compatible Raspberry Pi camera.
* Raspberry Pi OS or another compatible Debian-based Linux distribution.
* Python 3.
* Picamera2.
* FFmpeg.
* OpenCV.
* NumPy.
* LiteRT / `ai_edge_litert`.
* EfficientDet-Lite0 INT8 TensorFlow Lite model.

The detector expects the model at:

```text
~/models/efficientdet_lite0_int8.tflite
```

---

## Streaming / Host Machine

The streaming host requires:

* Docker.
* Docker Compose.
* Node.js 18 or newer.
* npm or pnpm.

---

# Raspberry Pi Setup

## 1. Install System Dependencies

On Raspberry Pi OS:

```bash
sudo apt update

sudo apt install -y \
  python3-picamera2 \
  python3-opencv \
  python3-venv \
  python3-pip \
  ffmpeg
```

---

## 2. Create a Python Environment

```bash
python3 -m venv --system-site-packages ~/vision-env

source ~/vision-env/bin/activate
```

Install LiteRT:

```bash
python -m pip install --upgrade pip
python -m pip install ai-edge-litert
python -m pip install "numpy==1.26.4"
```

---

## 3. Install the EfficientDet Model

Create the model directory:

```bash
mkdir -p ~/models
```

Place the EfficientDet-Lite0 INT8 model at:

```text
~/models/efficientdet_lite0_int8.tflite
```

---

# Stream Configuration

## Example MediaMTX Configuration

A local MediaMTX MPEG-TS/UDP ingest path can be configured as:

```yaml
paths:
  camera:
    source: udp+mpegts://127.0.0.1:9000
```

The detector then publishes to:

```text
udp://127.0.0.1:9000
```

---

# Starting the Gateway

From the directory containing the gateway `docker-compose.yml`:

```bash
docker compose up
```

To run it in the background:

```bash
docker compose up -d
```

Check service state with:

```bash
docker compose ps
```

---

# Running the Web Viewer

From the Next.js application directory:

```bash
npm install
npm run dev
```

or, when using pnpm:

```bash
pnpm install
pnpm dev
```

---
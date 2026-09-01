import cv2
import torch
import time

STREAM_URL = "rtsp://127.0.0.1:8554/camera"

device = torch.device(
    "cuda" if torch.cuda.is_available() else "cpu"
)

# Example: your trained ATR model
model = torch.jit.load("atr_model.ts", map_location=device)
model.eval()

cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)

# Minimize queued old frames where supported
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

while True:
    ok, frame = cap.read()

    if not ok:
        time.sleep(0.01)
        continue

    # OpenCV BGR -> RGB
    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    tensor = (
        torch.from_numpy(frame_rgb)
        .permute(2, 0, 1)
        .unsqueeze(0)
        .to(device, non_blocking=True)
        .float()
        / 255.0
    )

    with torch.inference_mode():
        if device.type == "cuda":
            with torch.autocast(device_type="cuda"):
                output = model(tensor)
        else:
            output = model(tensor)

    detections = postprocess(output)

    publish_detections(detections)
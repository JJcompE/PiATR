#!/usr/bin/env python3

import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2" # Reduce TensorFlow's startup logging.

import subprocess
import cv2
import time
import numpy as np
import tensorflow as tf
import tensorflow_hub as hub


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

MODEL_URL = "https://tfhub.dev/tensorflow/efficientdet/d0/1"
CONFIDENCE_THRESHOLD = 0.40
STREAM_URL = os.environ.get("STREAM_URL", "rtsp://127.0.0.1:8554/camera")
OUT_RTSP = os.environ.get("OUT_RTSP", "rtsp://127.0.0.1:8554/detected")
WRITE_FPS = float(os.environ.get("WRITE_FPS", "5.0"))

COCO_CLASSES = {
    1: "person",
    2: "bicycle",
    3: "car",
    4: "motorcycle",
    5: "airplane",
    6: "bus",
    7: "train",
    8: "truck",
    9: "boat",
    10: "traffic light",
    11: "fire hydrant",
    13: "stop sign",
    14: "parking meter",
    15: "bench",
    16: "bird",
    17: "cat",
    18: "dog",
    19: "horse",
    20: "sheep",
    21: "cow",
    22: "elephant",
    23: "bear",
    24: "zebra",
    25: "giraffe",
    27: "backpack",
    28: "umbrella",
    31: "handbag",
    32: "tie",
    33: "suitcase",
    34: "frisbee",
    35: "skis",
    36: "snowboard",
    37: "sports ball",
    38: "kite",
    39: "baseball bat",
    40: "baseball glove",
    41: "skateboard",
    42: "surfboard",
    43: "tennis racket",
    44: "bottle",
    46: "wine glass",
    47: "cup",
    48: "fork",
    49: "knife",
    50: "spoon",
    51: "bowl",
    52: "banana",
    53: "apple",
    54: "sandwich",
    55: "orange",
    56: "broccoli",
    57: "carrot",
    58: "hot dog",
    59: "pizza",
    60: "donut",
    61: "cake",
    62: "chair",
    63: "couch",
    64: "potted plant",
    65: "bed",
    67: "dining table",
    70: "toilet",
    72: "tv",
    73: "laptop",
    74: "mouse",
    75: "remote",
    76: "keyboard",
    77: "cell phone",
    78: "microwave",
    79: "oven",
    80: "toaster",
    81: "sink",
    82: "refrigerator",
    84: "book",
    85: "clock",
    86: "vase",
    87: "scissors",
    88: "teddy bear",
    89: "hair drier",
    90: "toothbrush",
}

FILTERED_CLASSES = {
    1: "person",
    17: "cat",
    18: "dog",
}


# ---------------------------------------------------------------------
# Load model
# ---------------------------------------------------------------------

def load_detector():
    print("Loading EfficientDet D0...")

    detector = hub.load(MODEL_URL)

    print("Detector loaded!")

    return detector


def run_detection(detector, frame):
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    image_tensor = tf.convert_to_tensor(
        rgb[np.newaxis, ...],
        dtype=tf.uint8,
    )

    results = detector(image_tensor)

    return {
        key: value.numpy()
        for key, value in results.items()
    }

def draw_detections(frame, results):
    height, width = frame.shape[:2]

    boxes = results["detection_boxes"][0]
    scores = results["detection_scores"][0]
    classes = results["detection_classes"][0]

    if "num_detections" in results:
        count = int(results["num_detections"][0])
    else:
        count = len(scores)

    for i in range(count):
        score = float(scores[i])

        if score < CONFIDENCE_THRESHOLD:
            continue

        class_id = int(classes[i])
        
        if class_id not in FILTERED_CLASSES:
            continue

        name = COCO_CLASSES.get(
            class_id,
            f"class_{class_id}",
        )

        ymin, xmin, ymax, xmax = boxes[i]

        left = int(xmin * width)
        right = int(xmax * width)
        top = int(ymin * height)
        bottom = int(ymax * height)

        label = f"{name} {score * 100:.1f}%"

        # Bounding box
        cv2.rectangle(
            frame,
            (left, top),
            (right, bottom),
            (0, 255, 0),
            2,
        )

        # Text
        cv2.putText(
            frame,
            label,
            (left, max(top - 10, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2,
        )

    return frame


def start_publisher(width, height, fps):
    cmd = [
        "ffmpeg",
        "-y",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{int(width)}x{int(height)}",
        "-r", str(fps),
        "-i", "-",
        "-an",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-tune", "zerolatency",
        "-pix_fmt", "yuv420p",
        "-rtsp_transport", "tcp",
        "-f", "rtsp",
        OUT_RTSP,
    ]

    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    detector = load_detector()

    # -------------------------------------------------------
    # VIDEO SOURCE
    # -------------------------------------------------------
    cap = cv2.VideoCapture(STREAM_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)


    if not cap.isOpened():
        print("ERROR: Could not open video source.")
        return

    print("Video source opened.")
    print("Press Q to quit.")

    previous_time = time.time()
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = max(1.0, float(cap.get(cv2.CAP_PROP_FPS) or WRITE_FPS))

    publisher = start_publisher(width, height, fps)
    frame_counter = 0
    last_publish = 0

    while True:
        ret, frame = cap.read()

        if not ret:
            print("Could not read frame.")
            break

        frame_counter += 1
        if frame_counter % 4 !=0:
            continue

        results = run_detection(detector, frame)
        frame = draw_detections(frame, results)

        now = time.monotonic()
        if now - last_publish < 0.25: # max ~4 fps
            continue

        last_publish = now
        
        # send the processed frame to the browser-visible stream
        try:
            publisher.stdin.write(frame.tobytes())
        except BrokenPipeError:
            print("Detected stream publisher failed; MediaMTX path may be closed or misconfigured.")
            break

        # -----------------------------------------------
        # Calculate FPS
        # -----------------------------------------------

        current_time = time.time()

        elapsed = current_time - previous_time

        if elapsed > 0:
            fps = 1.0 / elapsed
        else:
            fps = 0.0

        previous_time = current_time

        cv2.putText(
            frame,
            f"FPS: {fps:.1f}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 255),
            2,
        )

        # -----------------------------------------------
        # Display
        # -----------------------------------------------

        # cv2.imshow(
        #     "TensorFlow Object Detection",
        #     frame,
        # )

        

        # Press Q to exit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # -------------------------------------------------------
    # Cleanup
    # -------------------------------------------------------

    cap.release()
    cv2.destroyAllWindows()
    publisher.stdin.close()
    publisher.wait()

if __name__ == "__main__":
    main()
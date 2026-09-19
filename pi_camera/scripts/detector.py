from pathlib import Path
import threading
import time
import cv2
import numpy as np
import subprocess

from globals import COCO_LABELS, FILTERED_LABELS
from picamera2 import Picamera2
from ai_edge_litert.interpreter import Interpreter


# ============================================================
# Configuration
# ============================================================

MODEL_PATH = Path.home() / "models" / "efficientdet_lite0_int8.tflite"
SCORE_THRESHOLD = 0.45
NUM_THREADS = 4

MY_SERVER_IP = "127.0.0.1"
STREAM_PORT = 9000
MAIN_WIDTH = 1280
MAIN_HEIGHT = 720
CAMERA_FPS = 30

# ============================================================
# Load EfficientDet-Lite0
# ============================================================

if not MODEL_PATH.exists():
    raise FileNotFoundError(f"Model not found: {MODEL_PATH}")

print(f"Loading model: {MODEL_PATH}")

interpreter = Interpreter(
    model_path=str(MODEL_PATH),
    num_threads=NUM_THREADS
)

interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

if len(input_details) != 1:
    raise RuntimeError(
        f"Expected one input tensor, got {len(input_details)}"
    )

input_info = input_details[0]

print("\nInput tensor:")
print(
    f"  shape={input_info['shape']} "
    f"dtype={input_info['dtype']} "
    f"index={input_info['index']}"
)

print("\nOutput tensors:")
for i, output in enumerate(output_details):
    print(
        f"  {i}: name={output['name']} "
        f"shape={output['shape']} "
        f"dtype={output['dtype']} "
        f"index={output['index']}"
    )


# Expected EfficientDet-Lite0 input:
#
# [1, 320, 320, 3] uint8

input_shape = input_info["shape"]

MODEL_HEIGHT = int(input_shape[1])
MODEL_WIDTH = int(input_shape[2])

if input_info["dtype"] != np.uint8:
    raise RuntimeError(
        f"This script expects an INT8/uint8 model, "
        f"but input dtype is {input_info['dtype']}"
    )

print(
    f"\nDetector resolution: "
    f"{MODEL_WIDTH}x{MODEL_HEIGHT}"
)

if len(output_details) != 4:
    raise RuntimeError(
        "Unexpected model output layout. "
        "Expected 4 EfficientDet detection tensors."
    )

BOXES_OUTPUT = output_details[0]["index"]
CLASSES_OUTPUT = output_details[1]["index"]
SCORES_OUTPUT = output_details[2]["index"]
COUNT_OUTPUT = output_details[3]["index"]


# ============================================================
# Shared frame / result state
# ============================================================

frame_condition = threading.Condition()

latest_lores = None
latest_frame_id = 0
latest_frame_time = 0.0

stop_event = threading.Event()


result_lock = threading.Lock()

latest_detections = []
latest_detection_frame_id = -1
latest_detection_frame_time = 0.0

latest_inference_ms = 0.0
latest_detector_fps = 0.0


# ============================================================
# Run one inference
# ============================================================

def run_detector(yuv_frame):
    """
    Convert Pi 4 lores YUV420 to RGB and run EfficientDet.
    """

    rgb = cv2.cvtColor(
        yuv_frame,
        cv2.COLOR_YUV2RGB_I420
    )

    input_tensor = np.expand_dims(rgb, axis=0)

    interpreter.set_tensor(
        input_info["index"],
        input_tensor
    )

    start = time.perf_counter()

    interpreter.invoke()

    inference_ms = (time.perf_counter() - start) * 1000.0

    boxes = interpreter.get_tensor(BOXES_OUTPUT)[0]
    classes = interpreter.get_tensor(CLASSES_OUTPUT)[0]
    scores = interpreter.get_tensor(SCORES_OUTPUT)[0]

    count_raw = interpreter.get_tensor(COUNT_OUTPUT)
    count = int(count_raw.reshape(-1)[0])

    detections = []

    count = min(count, len(boxes),len(classes), len(scores))

    for i in range(count):
        score = float(scores[i])

        if score < SCORE_THRESHOLD:
            continue

        class_id = int(classes[i])

        if 0 <= class_id < len(COCO_LABELS):
            label = COCO_LABELS[class_id]
        else:
            label = f"class_{class_id}"

        if label not in FILTERED_LABELS:
            continue

        ymin, xmin, ymax, xmax = [
            float(v) for v in boxes[i]
        ]

        detections.append(
            {
                "label": label,
                "class_id": class_id,
                "score": score,
                "box": (ymin, xmin, ymax, xmax),
            }
        )

    return detections, inference_ms


# ============================================================
# Inference thread
# ============================================================

def detector_worker():
    global latest_detection_frame_id
    global latest_detection_frame_time
    global latest_detections
    global latest_inference_ms
    global latest_detector_fps

    last_processed_id = -1

    while not stop_event.is_set():

        # Wait until there's a frame we haven't processed.
        with frame_condition:
            frame_condition.wait_for(
                lambda:
                    stop_event.is_set()
                    or latest_frame_id != last_processed_id
            )

            if stop_event.is_set():
                break

            # Grab a reference to the NEWEST frame.
            #
            # If five frames arrived while we were doing the
            # previous inference, those older frames are skipped.
            frame = latest_lores
            frame_id = latest_frame_id
            frame_time = latest_frame_time

        if frame is None:
            continue

        try:
            detections, inference_ms = run_detector(frame)

            detector_fps = (
                1000.0 / inference_ms
                if inference_ms > 0
                else 0.0
            )

            with result_lock:
                latest_detections = detections
                latest_detection_frame_id = frame_id
                latest_detection_frame_time = frame_time

                latest_inference_ms = inference_ms
                latest_detector_fps = detector_fps

        except Exception as exc:
            print(f"Detector error: {exc}")

        last_processed_id = frame_id


# ============================================================
# Draw detections
# ============================================================

def draw_detections(frame, detections):

    height, width = frame.shape[:2]

    for det in detections:

        ymin, xmin, ymax, xmax = det["box"]

        # Clamp normalized coordinates.
        xmin = max(0.0, min(1.0, xmin))
        xmax = max(0.0, min(1.0, xmax))
        ymin = max(0.0, min(1.0, ymin))
        ymax = max(0.0, min(1.0, ymax))

        x1 = int(xmin * width)
        y1 = int(ymin * height)
        x2 = int(xmax * width)
        y2 = int(ymax * height)

        label = (
            f"{det['label']} "
            f"{det['score'] * 100:.0f}%"
        )

        # Bounding box.
        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        # Target center.
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2

        cv2.circle(
            frame,
            (center_x, center_y),
            4,
            (0, 0, 255),
            -1
        )

        # Label.
        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
            cv2.LINE_AA
        )


# ============================================================
# Camera configuration
# ============================================================

picam2 = Picamera2()

camera_config = picam2.create_video_configuration(

    # RGB888 is counter-intuitively B,G,R when returned
    # as a Python array, which is exactly what OpenCV wants.
    main={
        "size": (MAIN_WIDTH, MAIN_HEIGHT),
        "format": "RGB888",
    },

    # Pi 4 lores stream.
    #
    # 320x320 YUV420 is inexpensive for the camera system
    # and we only convert frames that actually get inferred.
    lores={
        "size": (MODEL_WIDTH, MODEL_HEIGHT),
        "format": "YUV420",
    },

    controls={
        "FrameRate": CAMERA_FPS,
    },

    buffer_count=6,
)

picam2.configure(camera_config)

print("\nCamera configuration:")
print(picam2.camera_configuration())

ffmpeg = subprocess.Popen(
    [
        "ffmpeg",
        "-f", "rawvideo",
        "-pix_fmt", "bgr24",
        "-s", f"{MAIN_WIDTH}x{MAIN_HEIGHT}",
        "-r", str(CAMERA_FPS),
        "-i", "-",
        "-an",
        "-c:v", "h264_v4l2m2m",
        "-b:v", "4000k",
        "-f", "mpegts",
        f"udp://{MY_SERVER_IP}:{STREAM_PORT}?pkt_size=1316",
    ],
    stdin=subprocess.PIPE,
    bufsize=0,
)

# ============================================================
# Start detector thread
# ============================================================

worker = threading.Thread(target=detector_worker, daemon=True)
worker.start()


# ============================================================
# Main camera loop
# ============================================================

picam2.start()

# Let auto exposure / white balance settle.
time.sleep(2)

print("\nRunning.")

display_frame_counter = 0
display_fps = 0.0
fps_start_time = time.monotonic()

try:
    while True:
        # Capture main + lores from the SAME camera request.
        (main_frame, lores_frame), metadata = (picam2.capture_arrays(["main", "lores"])        )
        capture_time = time.monotonic()

        # ----------------------------------------------------
        # Publish newest lores frame to inference thread.
        # We don't queue frames.
        # We simply replace the previous frame.
        # ----------------------------------------------------

        with frame_condition:
            latest_lores = lores_frame
            latest_frame_id += 1
            latest_frame_time = capture_time

            frame_condition.notify()

        # ----------------------------------------------------
        # Get latest completed detection result.
        # ----------------------------------------------------

        with result_lock:
            detections = list(latest_detections)

            detection_frame_id = latest_detection_frame_id
            detection_frame_time = latest_detection_frame_time

            inference_ms = latest_inference_ms
            detector_fps = latest_detector_fps

        # ----------------------------------------------------
        # Draw detections onto 30 FPS main stream.
        # ----------------------------------------------------

        draw_detections(main_frame, detections)

        # ----------------------------------------------------
        # Display FPS measurement
        # ----------------------------------------------------

        display_frame_counter += 1

        now = time.monotonic()
        elapsed = now - fps_start_time

        if elapsed >= 1.0:
            display_fps = (display_frame_counter / elapsed)
            display_frame_counter = 0
            fps_start_time = now

        # ----------------------------------------------------
        # Detection age
        # ----------------------------------------------------

        if detection_frame_time > 0:
            detection_age_ms = (now - detection_frame_time) * 1000.0
        else:
            detection_age_ms = 0.0

        # ----------------------------------------------------
        # Status overlay
        # ----------------------------------------------------

        cv2.putText(
            main_frame,
            f"Camera: {display_fps:.1f} FPS",
            (15, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            main_frame,
            (f"Detector: {detector_fps:.1f} FPS " f"({inference_ms:.0f} ms)"),
            (15, 58),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            main_frame,
            f"Detection age: {detection_age_ms:.0f} ms",
            (15, 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        cv2.putText(
            main_frame,
            f"Objects: {len(detections)}",
            (15, 114),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA
        )

        # ----------------------------------------------------
        # Show output
        # ----------------------------------------------------
        try:
            ffmpeg.stdin.write(main_frame.tobytes())
        except BrokenPipeError:
            print("FFmpeg stream closed")
            break


finally:

    print("\nStopping...")

    stop_event.set()

    with frame_condition:
        frame_condition.notify_all()

    worker.join(timeout=2.0)

    picam2.stop()

    if ffmpeg.stdin:
        ffmpeg.stdin.close()

    ffmpeg.wait()

    print("Stopped.")
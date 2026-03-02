README - How to Run main.py and Configure YAML

What this script does:
- Performs scene/shot detection on a video using PySceneDetect.
- Writes shot results to a CSV file.
- Computes quality metrics and writes a QC decision JSON (accept/review/reject).

--------------------------------------------------
1) Prerequisites
--------------------------------------------------
1. Python 3.9+ installed.
2. Install Python packages:
   pip install scenedetect[pyav] pyyaml opencv-python
3. Strongly recommended: install FFmpeg (including ffprobe) and add it to PATH.
   Without ffprobe, some QC rules may produce review/reject depending on config.

Important:
- With current PySceneDetect builds, `cv2` is required at import time.
- If you see: "PySceneDetect is not installed" even after installing it,
  install OpenCV in the same environment:
  python -m pip install opencv-python

--------------------------------------------------
2) How to run
--------------------------------------------------
Run with default config file named config.yaml in current folder:
python main.py

Run with a custom config path:
python main.py path\to\my_config.yaml

Help:
python main.py --help

Exit codes:
- 0 = success (including review status).
- 2 = reject status based on QC rules.
- 1 = configuration/dependency/runtime error.

--------------------------------------------------
3) Full config.yaml example (recommended defaults)
--------------------------------------------------
input_video: trailer_1080p.mov
output_csv: trailer_1080p_shots.csv
decision_json: trailer_1080p_decision.json
include_scenes_in_json: false
save_scene_start_images: false
scene_start_images_dir: null

backend: pyav
detector: content
detector_params: {}

threshold: 27.0
min_scene_len: 15
luma_only: false
show_progress: false
start_in_scene: false

filter_rules:
  min_duration_seconds: 2.0
  max_duration_seconds: 21600.0
  min_width: 320
  min_height: 240
  min_fps: 10.0
  max_fps: 120.0
  min_shots: 1
  max_shots: 20000
  max_cuts_per_minute: 180.0
  min_avg_shot_duration_seconds: 0.2
  short_shot_seconds: 0.4
  max_short_shot_ratio: 0.6
  review_max_cuts_per_minute: 90.0
  review_min_avg_shot_duration_seconds: 1.0
  review_max_short_shot_ratio: 0.3
  require_ffprobe: false
  review_on_missing_metadata: true

Notes:
- You can write keys with hyphens instead of underscores (for example: min-scene-len).
- Relative paths in YAML are resolved relative to the YAML file location, not necessarily the folder where you ran the command.

--------------------------------------------------
4) Parameter reference + meaning + recommended default
--------------------------------------------------

Top-level parameters:

1) input_video
- Meaning: path to the input video file.
- Type: string (path).
- Recommended default: no automatic default, this key is required.

2) output_csv
- Meaning: output CSV path for shot list.
- Type: string (path) or null.
- Recommended default: null (or omit), then generated automatically as:
  <video_name>_shots.csv

3) decision_json
- Meaning: output JSON path for QC decision and metrics.
- Type: string (path) or null.
- Recommended default: null (or omit), then generated automatically as:
  <video_name>_decision.json

4) include_scenes_in_json
- Meaning: include the full scene list inside decision JSON.
- Type: boolean.
- Recommended default: false (smaller file; set true for debugging/auditing).

5) save_scene_start_images
- Meaning: save one image for the start frame of each detected scene.
- Type: boolean.
- Recommended default: false.

6) scene_start_images_dir
- Meaning: output folder for scene start images.
- Type: string (path) or null.
- Recommended default: null (or omit), then generated automatically as:
  <video_name>_scene_starts

7) backend
- Meaning: PySceneDetect video backend.
- Supported values: pyav, opencv.
- Recommended default: pyav.

8) detector
- Meaning: scene cut detection algorithm.
- Supported values: adaptive, content, hash, hist, threshold
  (aliases like detect-content are also supported).
- Recommended default: content (good balance for most footage).

9) detector_params
- Meaning: extra detector-specific parameters.
- Type: object (mapping).
- Recommended default: {}.

10) threshold
- Meaning: sensitivity threshold for cut detection (unless overridden in detector_params).
- Type: number.
- Recommended default: 27.0.

11) min_scene_len
- Meaning: minimum scene length in frames.
- Type: integer.
- Recommended default: 15.

12) luma_only
- Meaning: compare luma/brightness channel only (if detector supports it).
- Type: boolean.
- Recommended default: false.

13) show_progress
- Meaning: print progress during detection.
- Type: boolean.
- Recommended default: false (quieter and better for scripts/CI).

14) start_in_scene
- Meaning: if true, includes the initial scene from frame 0.
- Type: boolean.
- Recommended default: false (matches current code default).

15) filter_rules
- Meaning: quality gate validation rules.
- Type: object.
- Recommended default: use values listed below.

filter_rules parameters:

1) min_duration_seconds
- Meaning: reject if video duration is below this value.
- Recommended default: 2.0

2) max_duration_seconds
- Meaning: reject if video duration is above this value.
- Recommended default: 21600.0 (6 hours)

3) min_width
- Meaning: reject if width is below this value.
- Recommended default: 320

4) min_height
- Meaning: reject if height is below this value.
- Recommended default: 240

5) min_fps
- Meaning: reject if FPS is below this value.
- Recommended default: 10.0

6) max_fps
- Meaning: reject if FPS is above this value.
- Recommended default: 120.0

7) min_shots
- Meaning: reject if number of shots is below this value.
- Recommended default: 1

8) max_shots
- Meaning: reject if number of shots is above this value.
- Recommended default: 20000

9) max_cuts_per_minute
- Meaning: reject if cuts-per-minute exceeds this value.
- Recommended default: 180.0

10) min_avg_shot_duration_seconds
- Meaning: reject if average shot duration is below this value.
- Recommended default: 0.2

11) short_shot_seconds
- Meaning: threshold used to classify a shot as short.
- Recommended default: 0.4

12) max_short_shot_ratio
- Meaning: reject if ratio of short shots exceeds this value.
- Recommended default: 0.6

13) review_max_cuts_per_minute
- Meaning: review (not reject) if cuts-per-minute exceeds this value.
- Recommended default: 90.0

14) review_min_avg_shot_duration_seconds
- Meaning: review if average shot duration is below this value.
- Recommended default: 1.0

15) review_max_short_shot_ratio
- Meaning: review if short-shot ratio exceeds this value.
- Recommended default: 0.3

16) require_ffprobe
- Meaning: if true and ffprobe/metadata is missing => reject.
- Recommended default: false

17) review_on_missing_metadata
- Meaning: if true and metadata is missing => review (when require_ffprobe=false).
- Recommended default: true

--------------------------------------------------
5) Practical tuning tips
--------------------------------------------------
- Start with the recommended defaults.
- If too many cuts are detected: increase threshold or min_scene_len.
- If cuts are being missed: decrease threshold.

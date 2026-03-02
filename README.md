# ShotGate

ShotGate is a configurable video shot/scene detection pipeline built on top of PySceneDetect.  
It adds a practical **Quality Gate (QC layer)** before results are accepted, and produces structured outputs (CSV + JSON) for downstream processing.

## 🚀 Overview

ShotGate is designed for production workflows where simple scene detection is not enough.

It provides:

- YAML-based configuration (fully reproducible runs)
- Scene/shot detection using PySceneDetect
- Quality validation before accepting results
- Structured outputs for pipelines and analytics
- Optional scene thumbnail generation


## ✨ Features

### 🎬 Scene Detection
- Uses PySceneDetect
- Supports configurable detectors (e.g. content-based)
- Adjustable thresholds

### 📊 Structured Outputs
- CSV file with detected scenes
- JSON report with QC decision and metrics

### 🛡️ Quality Gate (QC)
Each video is classified as:

- `accept`
- `review`
- `reject`

Based on rules such as:
- Duration
- Resolution
- Cuts per minute
- Shot length distribution
- Metadata availability

### 🖼️ Scene Thumbnails (Optional)
- Export first frame of each scene
- Useful for quick validation


## 📁 Project Structure

```

shotgate/
│
├── main.py              # Main pipeline
├── config.py            # Config parsing + QC logic
├── config.yaml          # Example config
├── readme.txt           # Basic instructions
│
├── sintel_trailer-720p.mp4
├── trailer_1080p.mov

````


## ⚙️ Requirements

- Python 3.9+
- PySceneDetect
- PyYAML
- OpenCV
- FFmpeg (recommended, includes `ffprobe`)


## 🔧 Installation

Create a virtual environment:

```bash
python -m venv .venv
````

Activate it:

**Linux / macOS**

```bash
source .venv/bin/activate
```

**Windows (PowerShell)**

```bash
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install scenedetect[pyav] pyyaml opencv-python
```

## ▶️ Usage

Run with config file:

```bash
python main.py --config config.yaml
```

Override input video:

```bash
python main.py --config config.yaml --input path/to/video.mp4
```


## 🧾 Configuration (YAML)

Example:

```yaml
input: sintel_trailer-720p.mp4

detector:
  type: content
  threshold: 27.0

output:
  csv_path: output/scenes.csv
  json_path: output/report.json
  save_images: true
  images_dir: output/images

qc:
  min_duration_sec: 10
  min_resolution: [640, 360]
  max_cuts_per_minute: 120
  max_short_shot_ratio: 0.5
```


## 📤 Output

### 1. Scenes CSV

```csv
scene_id,start_time,end_time,duration_sec
0,00:00:00.000,00:00:02.134,2.134
1,00:00:02.134,00:00:05.900,3.766
```


### 2. JSON Decision Report

```json
{
  "status": "accept",
  "reasons": [],
  "metrics": {
    "cuts_per_minute": 32.1,
    "avg_shot_length": 2.8,
    "short_shot_ratio": 0.12
  },
  "video_metadata": {
    "width": 1280,
    "height": 720,
    "duration": 52.3
  },
  "config_used": {}
}
```


## 🚦 Exit Codes

* `0` → Accept
* `1` → Review
* `2` → Reject

Useful for automation and CI pipelines.


## ⚙️ How It Works

1. Load YAML configuration
2. Run scene detection (PySceneDetect)
3. Compute metrics:

   * Cuts per minute
   * Shot duration stats
4. Extract metadata (via ffprobe if available)
5. Apply QC rules
6. Export CSV + JSON (+ optional images)


## 🧠 Quality Gate Logic

Typical checks:

* Video too short → Reject
* Resolution too low → Reject
* Too many cuts → Review / Reject
* Too many short shots → Review
* Missing metadata → Review

All thresholds are configurable.


## 🧪 Example

```bash
python main.py \
  --config config.yaml \
  --input trailer_1080p.mov
```


## 📌 Notes

* FFmpeg is strongly recommended for accurate metadata extraction
* If `ffprobe` is missing, QC may downgrade to `review`
* Works best with standard formats (mp4, mov, etc.)


## 📬 Contact

If you have questions, feedback, or want to collaborate, feel free to reach out:

 📧 Email: [Avishai Weizman](mailto:wavishay@post.bgu.ac.il)  

 🔗 GitHub: [github.com/avishai111](https://github.com/avishai111)

 🎓 Google Scholar: [Avishai Weizman](https://scholar.google.com/citations?hl=iw&user=vWlnVpUAAAAJ)  
 
 💼 LinkedIn: [linkedin.com/in/avishai-weizman/](https://www.linkedin.com/in/avishai-weizman/)


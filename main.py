#!/usr/bin/env python3
"""PySceneDetect runner with YAML config + pre-DB quality gate."""

from __future__ import annotations

import csv
import inspect
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence, Tuple

from config import load_settings_from_argv


SceneBoundaries = Sequence[Tuple[Any, Any]]


def load_scenedetect():
    """
    Import PySceneDetect modules only when detection is needed.

    Inputs:
        None.

    Output:
        tuple: (SceneManager, open_video, detectors_map).

    Parameters:
        None.
    """
    try:
        from scenedetect import SceneManager, open_video
        from scenedetect.detectors import (
            AdaptiveDetector,
            ContentDetector,
            HashDetector,
            HistogramDetector,
            ThresholdDetector,
        )
    except ModuleNotFoundError as exc:
        missing_module = getattr(exc, "name", "") or ""
        if missing_module == "cv2":
            raise ModuleNotFoundError(
                "OpenCV (cv2) is missing.\n"
                "Install with: python -m pip install opencv-python\n"
                "Then run the script again in the same virtual environment."
            ) from exc
        raise ModuleNotFoundError(
            "PySceneDetect is not installed.\n"
            "Install with: pip install scenedetect[pyav] opencv-python\n"
            "If needed, also install FFmpeg and make sure it is in PATH."
        ) from exc

    detectors = {
        "adaptive": AdaptiveDetector,
        "content": ContentDetector,
        "hash": HashDetector,
        "hist": HistogramDetector,
        "threshold": ThresholdDetector,
    }
    return SceneManager, open_video, detectors


def validate_input_video(video_path: Path) -> None:
    """
    Validate that the input path exists and points to a file.

    Inputs:
        video_path: Path to the input video.

    Output:
        None. Raises an exception on invalid input.

    Parameters:
        video_path (Path): Input video location.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Input video does not exist: {video_path}")
    if not video_path.is_file():
        raise ValueError(f"Input path is not a file: {video_path}")


def parse_fraction(value: str | None) -> float | None:
    """
    Convert fraction-like strings (e.g., 30000/1001) into float.

    Inputs:
        value: Raw fraction or numeric string from metadata.

    Output:
        float | None: Parsed numeric value, or None when invalid.

    Parameters:
        value (str | None): Text value to parse.
    """
    if not value or value == "0/0":
        return None
    if "/" in value:
        num, den = value.split("/", 1)
        try:
            numerator = float(num)
            denominator = float(den)
        except ValueError:
            return None
        if denominator == 0:
            return None
        return numerator / denominator
    try:
        return float(value)
    except ValueError:
        return None


def run_ffprobe(video_path: Path) -> dict[str, Any]:
    """
    Run ffprobe and extract basic video metadata.

    Inputs:
        video_path: Path to the input video.

    Output:
        dict[str, Any]: Metadata map including availability/error info.

    Parameters:
        video_path (Path): Input video location.
    """
    command = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(video_path),
    ]

    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
    except FileNotFoundError:
        return {"available": False, "error": "ffprobe not found in PATH."}

    if proc.returncode != 0:
        return {
            "available": False,
            "error": proc.stderr.strip() or "ffprobe failed.",
        }

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"available": False, "error": "ffprobe returned non-JSON output."}

    streams = payload.get("streams", [])
    format_info = payload.get("format", {})
    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)

    width = None
    height = None
    fps = None
    codec_name = None
    pixel_format = None
    if isinstance(video_stream, dict):
        width = video_stream.get("width")
        height = video_stream.get("height")
        fps = parse_fraction(video_stream.get("avg_frame_rate")) or parse_fraction(
            video_stream.get("r_frame_rate")
        )
        codec_name = video_stream.get("codec_name")
        pixel_format = video_stream.get("pix_fmt")

    duration_seconds = None
    raw_duration = format_info.get("duration")
    if raw_duration is not None:
        try:
            duration_seconds = float(raw_duration)
        except (TypeError, ValueError):
            duration_seconds = None
    if duration_seconds is None and isinstance(video_stream, dict):
        stream_duration = video_stream.get("duration")
        if stream_duration is not None:
            try:
                duration_seconds = float(stream_duration)
            except (TypeError, ValueError):
                duration_seconds = None

    size_bytes = None
    raw_size = format_info.get("size")
    if raw_size is not None:
        try:
            size_bytes = int(raw_size)
        except (TypeError, ValueError):
            size_bytes = None

    bit_rate = None
    raw_bitrate = format_info.get("bit_rate")
    if raw_bitrate is not None:
        try:
            bit_rate = int(raw_bitrate)
        except (TypeError, ValueError):
            bit_rate = None

    return {
        "available": True,
        "error": None,
        "duration_seconds": duration_seconds,
        "width": width,
        "height": height,
        "fps": fps,
        "codec_name": codec_name,
        "pixel_format": pixel_format,
        "size_bytes": size_bytes,
        "bit_rate": bit_rate,
    }


def build_detector_kwargs(
    detector_name: str,
    detector_class: Any,
    threshold: float,
    min_scene_len: int,
    luma_only: bool,
    detector_params: dict[str, Any],
) -> dict[str, Any]:
    """
    Build detector constructor kwargs based on selected algorithm and settings.

    Inputs:
        detector_name: Canonical detector key.
        detector_class: PySceneDetect detector class.
        threshold: Global detection threshold.
        min_scene_len: Minimum frames between scene cuts.
        luma_only: Whether to use luma-only comparison when supported.
        detector_params: User-supplied detector-specific params.

    Output:
        dict[str, Any]: Validated kwargs for detector initialization.

    Parameters:
        detector_name (str): Detector id (e.g., content/adaptive).
        detector_class (Any): Detector class object.
        threshold (float): Global threshold value.
        min_scene_len (int): Minimum scene length in frames.
        luma_only (bool): Luma-only mode flag.
        detector_params (dict[str, Any]): Additional detector parameters.
    """
    accepted = set(inspect.signature(detector_class.__init__).parameters) - {"self"}
    kwargs = dict(detector_params)

    if "min_scene_len" in accepted and "min_scene_len" not in kwargs:
        kwargs["min_scene_len"] = min_scene_len
    if "luma_only" in accepted and "luma_only" not in kwargs:
        kwargs["luma_only"] = luma_only

    if detector_name == "adaptive":
        if "adaptive_threshold" in accepted:
            if "adaptive_threshold" not in kwargs and "threshold" not in kwargs:
                kwargs["adaptive_threshold"] = threshold
        elif "threshold" in accepted and "threshold" not in kwargs:
            kwargs["threshold"] = threshold
    else:
        if "threshold" in accepted and "threshold" not in kwargs:
            kwargs["threshold"] = threshold

    unknown = sorted(set(kwargs) - accepted)
    if unknown:
        supported = ", ".join(sorted(accepted))
        raise ValueError(
            f"Unsupported parameters for detector '{detector_name}': "
            f"{', '.join(unknown)}. Supported: {supported}"
        )

    return kwargs


def detect_shots(settings: dict[str, Any]) -> SceneBoundaries:
    """
    Run scene detection on the input video using configured detector settings.

    Inputs:
        settings: Parsed runtime configuration dictionary.

    Output:
        SceneBoundaries: Sequence of (start, end) scene boundaries.

    Parameters:
        settings (dict[str, Any]): Runtime settings map.
    """
    SceneManager, open_video, detector_classes = load_scenedetect()
    video = open_video(str(settings["input_video"]), backend=settings["backend"])

    detector_name = settings["detector"]
    detector_class = detector_classes[detector_name]
    detector_kwargs = build_detector_kwargs(
        detector_name=detector_name,
        detector_class=detector_class,
        threshold=settings["threshold"],
        min_scene_len=settings["min_scene_len"],
        luma_only=settings["luma_only"],
        detector_params=settings["detector_params"],
    )

    scene_manager = SceneManager()
    scene_manager.add_detector(detector_class(**detector_kwargs))
    scene_manager.detect_scenes(video=video, show_progress=settings["show_progress"])
    return scene_manager.get_scene_list(start_in_scene=settings["start_in_scene"])


def scene_records(scene_list: SceneBoundaries) -> list[dict[str, Any]]:
    """
    Convert raw scene boundaries to serializable shot dictionaries.

    Inputs:
        scene_list: Scene boundary objects returned by PySceneDetect.

    Output:
        list[dict[str, Any]]: Shot records with timecodes, frames, and durations.

    Parameters:
        scene_list (SceneBoundaries): Detected scene boundaries.
    """
    records: list[dict[str, Any]] = []
    for shot_number, (start, end) in enumerate(scene_list, start=1):
        start_seconds = start.get_seconds()
        end_seconds = end.get_seconds()
        start_frame = start.get_frames()
        end_frame = end.get_frames()
        records.append(
            {
                "shot_number": shot_number,
                "start_timecode": start.get_timecode(),
                "end_timecode": end.get_timecode(),
                "start_seconds": start_seconds,
                "end_seconds": end_seconds,
                "start_frame": start_frame,
                "end_frame_exclusive": end_frame,
                "duration_seconds": end_seconds - start_seconds,
                "duration_frames": end_frame - start_frame,
            }
        )
    return records


def write_shots_csv(records: list[dict[str, Any]], output_csv: Path) -> None:
    """
    Write shot records to a CSV file.

    Inputs:
        records: List of shot dictionaries.
        output_csv: Destination CSV path.

    Output:
        None. Writes the CSV file to disk.

    Parameters:
        records (list[dict[str, Any]]): Serialized shot records.
        output_csv (Path): Output CSV file path.
    """
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(
            [
                "shot_number",
                "start_timecode",
                "end_timecode",
                "start_seconds",
                "end_seconds",
                "start_frame",
                "end_frame_exclusive",
                "duration_seconds",
                "duration_frames",
            ]
        )
        for item in records:
            writer.writerow(
                [
                    item["shot_number"],
                    item["start_timecode"],
                    item["end_timecode"],
                    f"{item['start_seconds']:.6f}",
                    f"{item['end_seconds']:.6f}",
                    item["start_frame"],
                    item["end_frame_exclusive"],
                    f"{item['duration_seconds']:.6f}",
                    item["duration_frames"],
                ]
            )


def save_scene_start_images(
    scene_list: SceneBoundaries,
    input_video: Path,
    output_dir: Path,
) -> tuple[int, int]:
    """
    Save one image for the start frame of each detected scene.

    Inputs:
        scene_list: Scene boundary objects from PySceneDetect.
        input_video: Source video path.
        output_dir: Destination directory for saved images.

    Output:
        tuple[int, int]: (saved_count, skipped_count).

    Parameters:
        scene_list (SceneBoundaries): Detected scene boundaries.
        input_video (Path): Input video path.
        output_dir (Path): Output folder for scene start images.
    """
    try:
        import cv2
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "OpenCV (cv2) is required to save scene start images.\n"
            "Install with: python -m pip install opencv-python"
        ) from exc

    output_dir.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(input_video))
    if not capture.isOpened():
        raise ValueError(f"Failed to open video for image export: {input_video}")

    saved_count = 0
    skipped_count = 0
    try:
        for shot_number, (start, _end) in enumerate(scene_list, start=1):
            frame_number = max(int(start.get_frames()), 0)
            capture.set(cv2.CAP_PROP_POS_FRAMES, float(frame_number))
            success, frame = capture.read()

            if not success or frame is None:
                # Some backends may fail exact seeks, so retry one frame earlier.
                fallback_frame = max(frame_number - 1, 0)
                if fallback_frame != frame_number:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, float(fallback_frame))
                    success, frame = capture.read()
                    if success and frame is not None:
                        frame_number = fallback_frame

            if not success or frame is None:
                skipped_count += 1
                continue

            timecode_token = (
                start.get_timecode()
                .replace(":", "-")
                .replace(".", "_")
                .replace(";", "_")
            )
            output_path = output_dir / (
                f"scene_{shot_number:04d}_frame_{frame_number:08d}_{timecode_token}.jpg"
            )
            write_ok = cv2.imwrite(str(output_path), frame)
            if write_ok:
                saved_count += 1
            else:
                skipped_count += 1
    finally:
        capture.release()

    return saved_count, skipped_count


def compute_metrics(
    records: list[dict[str, Any]],
    duration_seconds: float | None,
    short_shot_seconds: float,
) -> dict[str, Any]:
    """
    Compute aggregate shot metrics used by the quality gate.

    Inputs:
        records: Shot records list.
        duration_seconds: Duration from metadata when available.
        short_shot_seconds: Threshold defining a short shot.

    Output:
        dict[str, Any]: Calculated metrics (cuts/minute, ratios, durations, etc.).

    Parameters:
        records (list[dict[str, Any]]): Shot records.
        duration_seconds (float | None): Metadata duration value.
        short_shot_seconds (float): Short-shot threshold in seconds.
    """
    shot_durations = [max(item["duration_seconds"], 0.0) for item in records]
    inferred_duration = sum(shot_durations)
    total_duration = duration_seconds if duration_seconds and duration_seconds > 0 else inferred_duration

    num_shots = len(records)
    num_cuts = max(num_shots - 1, 0)
    avg_shot_duration = (sum(shot_durations) / num_shots) if num_shots else 0.0
    short_shot_count = sum(1 for duration in shot_durations if duration < short_shot_seconds)
    short_shot_ratio = (short_shot_count / num_shots) if num_shots else 0.0
    cuts_per_minute = (num_cuts * 60.0 / total_duration) if total_duration > 0 else 0.0

    return {
        "num_shots": num_shots,
        "num_cuts": num_cuts,
        "total_duration_seconds": total_duration,
        "avg_shot_duration_seconds": avg_shot_duration,
        "short_shot_seconds_threshold": short_shot_seconds,
        "short_shot_count": short_shot_count,
        "short_shot_ratio": short_shot_ratio,
        "cuts_per_minute": cuts_per_minute,
    }


def evaluate_quality_gate(
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    rules: dict[str, Any],
) -> tuple[str, list[str]]:
    """
    Evaluate rules and return QC status with reasons.

    Inputs:
        metadata: ffprobe metadata map.
        metrics: Computed metrics map.
        rules: Filter rules map from config.

    Output:
        tuple[str, list[str]]: (status, reasons), where status is accept/review/reject.

    Parameters:
        metadata (dict[str, Any]): Video metadata.
        metrics (dict[str, Any]): Computed quality metrics.
        rules (dict[str, Any]): Quality gate rules.
    """
    reject_reasons: list[str] = []
    review_reasons: list[str] = []

    if not metadata.get("available", False):
        if rules["require_ffprobe"]:
            reject_reasons.append(
                f"ffprobe metadata is required but unavailable: {metadata.get('error')}"
            )
        elif rules["review_on_missing_metadata"]:
            review_reasons.append(f"ffprobe metadata unavailable: {metadata.get('error')}")
    else:
        duration = metadata.get("duration_seconds")
        width = metadata.get("width")
        height = metadata.get("height")
        fps = metadata.get("fps")

        if duration is None:
            if rules["require_ffprobe"]:
                reject_reasons.append("Video duration is missing from ffprobe output.")
            elif rules["review_on_missing_metadata"]:
                review_reasons.append("Video duration is missing from ffprobe output.")
        else:
            if duration < rules["min_duration_seconds"]:
                reject_reasons.append(
                    f"Duration {duration:.3f}s is below min_duration_seconds={rules['min_duration_seconds']}."
                )
            if duration > rules["max_duration_seconds"]:
                reject_reasons.append(
                    f"Duration {duration:.3f}s exceeds max_duration_seconds={rules['max_duration_seconds']}."
                )

        if width is None or height is None:
            if rules["require_ffprobe"]:
                reject_reasons.append("Video resolution is missing from ffprobe output.")
            elif rules["review_on_missing_metadata"]:
                review_reasons.append("Video resolution is missing from ffprobe output.")
        elif int(width) < rules["min_width"] or int(height) < rules["min_height"]:
            reject_reasons.append(
                f"Resolution {width}x{height} is below minimum {rules['min_width']}x{rules['min_height']}."
            )

        if fps is None:
            if rules["require_ffprobe"]:
                reject_reasons.append("Video FPS is missing from ffprobe output.")
            elif rules["review_on_missing_metadata"]:
                review_reasons.append("Video FPS is missing from ffprobe output.")
        else:
            if fps < rules["min_fps"]:
                reject_reasons.append(f"FPS {fps:.3f} is below min_fps={rules['min_fps']}.")
            if fps > rules["max_fps"]:
                reject_reasons.append(f"FPS {fps:.3f} exceeds max_fps={rules['max_fps']}.")

    num_shots = metrics["num_shots"]
    cuts_per_minute = metrics["cuts_per_minute"]
    avg_shot_duration = metrics["avg_shot_duration_seconds"]
    short_shot_ratio = metrics["short_shot_ratio"]

    if num_shots < rules["min_shots"]:
        reject_reasons.append(f"num_shots={num_shots} is below min_shots={rules['min_shots']}.")
    if num_shots > rules["max_shots"]:
        reject_reasons.append(f"num_shots={num_shots} exceeds max_shots={rules['max_shots']}.")
    if cuts_per_minute > rules["max_cuts_per_minute"]:
        reject_reasons.append(
            f"cuts_per_minute={cuts_per_minute:.3f} exceeds max_cuts_per_minute={rules['max_cuts_per_minute']}."
        )
    if avg_shot_duration < rules["min_avg_shot_duration_seconds"]:
        reject_reasons.append(
            "avg_shot_duration_seconds="
            f"{avg_shot_duration:.3f} is below min_avg_shot_duration_seconds={rules['min_avg_shot_duration_seconds']}."
        )
    if short_shot_ratio > rules["max_short_shot_ratio"]:
        reject_reasons.append(
            f"short_shot_ratio={short_shot_ratio:.3f} exceeds max_short_shot_ratio={rules['max_short_shot_ratio']}."
        )

    if cuts_per_minute > rules["review_max_cuts_per_minute"]:
        review_reasons.append(
            "High editing pace: "
            f"cuts_per_minute={cuts_per_minute:.3f} exceeds review_max_cuts_per_minute={rules['review_max_cuts_per_minute']}."
        )
    if avg_shot_duration < rules["review_min_avg_shot_duration_seconds"]:
        review_reasons.append(
            "Short average shot duration: "
            "avg_shot_duration_seconds="
            f"{avg_shot_duration:.3f} is below review_min_avg_shot_duration_seconds={rules['review_min_avg_shot_duration_seconds']}."
        )
    if short_shot_ratio > rules["review_max_short_shot_ratio"]:
        review_reasons.append(
            "Many very short shots: "
            f"short_shot_ratio={short_shot_ratio:.3f} exceeds review_max_short_shot_ratio={rules['review_max_short_shot_ratio']}."
        )

    if reject_reasons:
        return "reject", reject_reasons
    if review_reasons:
        return "review", review_reasons
    return "accept", ["Passed all configured filter rules."]


def build_decision_report(
    settings: dict[str, Any],
    metadata: dict[str, Any],
    metrics: dict[str, Any],
    status: str,
    reasons: list[str],
    output_csv: Path,
    decision_json: Path,
    records: list[dict[str, Any]],
    scene_start_images_dir: Path | None,
    scene_start_images_saved: int,
    scene_start_images_skipped: int,
) -> dict[str, Any]:
    """
    Build the final decision payload for storage/DB ingestion.

    Inputs:
        settings: Runtime settings.
        metadata: ffprobe metadata.
        metrics: Computed quality metrics.
        status: QC result status.
        reasons: Human-readable QC reasons.
        output_csv: CSV artifact path.
        decision_json: JSON artifact path.
        records: Shot record list.
        scene_start_images_dir: Output directory for saved scene start images.
        scene_start_images_saved: Number of saved scene start images.
        scene_start_images_skipped: Number of skipped scene start images.

    Output:
        dict[str, Any]: Complete decision payload.

    Parameters:
        settings (dict[str, Any]): Runtime settings map.
        metadata (dict[str, Any]): Video metadata map.
        metrics (dict[str, Any]): Quality metrics map.
        status (str): accept/review/reject.
        reasons (list[str]): Decision reason list.
        output_csv (Path): CSV output location.
        decision_json (Path): Decision JSON location.
        records (list[dict[str, Any]]): Shot records.
        scene_start_images_dir (Path | None): Scene image folder path.
        scene_start_images_saved (int): Saved image count.
        scene_start_images_skipped (int): Skipped image count.
    """
    report: dict[str, Any] = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "video_path": str(settings["input_video"]),
        "status": status,
        "reasons": reasons,
        "settings": {
            "backend": settings["backend"],
            "detector": settings["detector"],
            "detector_params": settings["detector_params"],
            "threshold": settings["threshold"],
            "min_scene_len": settings["min_scene_len"],
            "luma_only": settings["luma_only"],
            "show_progress": settings["show_progress"],
            "start_in_scene": settings["start_in_scene"],
            "include_scenes_in_json": settings["include_scenes_in_json"],
            "save_scene_start_images": settings["save_scene_start_images"],
            "scene_start_images_dir": (
                str(scene_start_images_dir) if scene_start_images_dir is not None else None
            ),
        },
        "filter_rules": settings["filter_rules"],
        "metadata": metadata,
        "metrics": metrics,
        "artifacts": {
            "shots_csv": str(output_csv),
            "decision_json": str(decision_json),
        },
    }

    if scene_start_images_dir is not None:
        report["artifacts"]["scene_start_images_dir"] = str(scene_start_images_dir)
        report["artifacts"]["scene_start_images_saved"] = scene_start_images_saved
        report["artifacts"]["scene_start_images_skipped"] = scene_start_images_skipped

    if settings["include_scenes_in_json"]:
        report["scenes"] = records

    return report


def write_json_file(payload: dict[str, Any], output_path: Path) -> None:
    """
    Write JSON payload to a file.

    Inputs:
        payload: JSON-serializable data.
        output_path: Destination JSON path.

    Output:
        None. Writes JSON to disk.

    Parameters:
        payload (dict[str, Any]): Data to serialize.
        output_path (Path): Output JSON file path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=True)
        file.write("\n")


def print_summary(
    records: list[dict[str, Any]],
    output_csv: Path,
    decision_json: Path,
    status: str,
    reasons: list[str],
    scene_start_images_dir: Path | None,
    scene_start_images_saved: int,
    scene_start_images_skipped: int,
) -> None:
    """
    Print a concise execution summary to stdout.

    Inputs:
        records: Shot records list.
        output_csv: CSV output path.
        decision_json: Decision JSON output path.
        status: QC status.
        reasons: QC reason list.
        scene_start_images_dir: Output directory for scene start images.
        scene_start_images_saved: Number of saved scene start images.
        scene_start_images_skipped: Number of skipped scene start images.

    Output:
        None. Prints text to terminal.

    Parameters:
        records (list[dict[str, Any]]): Shot records.
        output_csv (Path): CSV file path.
        decision_json (Path): Decision JSON file path.
        status (str): accept/review/reject.
        reasons (list[str]): Human-readable decision reasons.
        scene_start_images_dir (Path | None): Scene image output path.
        scene_start_images_saved (int): Saved image count.
        scene_start_images_skipped (int): Skipped image count.
    """
    print(f"Detected {len(records)} shot(s).")
    print(f"CSV written to: {output_csv}")
    print(f"Decision JSON written to: {decision_json}")
    if scene_start_images_dir is not None:
        print(
            "Scene start images: "
            f"{scene_start_images_saved} saved, {scene_start_images_skipped} skipped "
            f"({scene_start_images_dir})"
        )
    print(f"Quality gate status: {status}")
    for reason in reasons:
        print(f"  - {reason}")

    preview = 5
    if not records:
        return

    print("\nFirst shots:")
    for item in records[:preview]:
        print(
            f"  {item['shot_number']:>3}. "
            f"{item['start_timecode']} -> {item['end_timecode']}"
        )
    if len(records) > preview:
        print(f"  ... ({len(records) - preview} more)")


def main() -> int:
    """
    Orchestrate full processing flow: config, detection, QC, and outputs.

    Inputs:
        sys.argv command-line arguments.

    Output:
        int: Process exit code.

    Parameters:
        None.
    """
    try:
        settings = load_settings_from_argv(sys.argv)
        validate_input_video(settings["input_video"])
    except SystemExit as exc:
        return int(exc.code)
    except (FileNotFoundError, ValueError, TypeError, ModuleNotFoundError) as exc:
        print(exc)
        return 1

    try:
        scenes = detect_shots(settings)
    except (ModuleNotFoundError, ValueError) as exc:
        print(exc)
        return 1

    records = scene_records(scenes)

    scene_start_images_dir: Path | None = None
    scene_start_images_saved = 0
    scene_start_images_skipped = 0
    if settings["save_scene_start_images"]:
        scene_start_images_dir = settings["scene_start_images_dir"]
        if scene_start_images_dir is None:
            scene_start_images_dir = settings["input_video"].with_name(
                f"{settings['input_video'].stem}_scene_starts"
            )
        try:
            scene_start_images_saved, scene_start_images_skipped = save_scene_start_images(
                scene_list=scenes,
                input_video=settings["input_video"],
                output_dir=scene_start_images_dir,
            )
        except (ModuleNotFoundError, ValueError) as exc:
            print(exc)
            return 1

    output_csv = settings["output_csv"]
    if output_csv is None:
        output_csv = settings["input_video"].with_name(f"{settings['input_video'].stem}_shots.csv")
    write_shots_csv(records, output_csv)

    metadata = run_ffprobe(settings["input_video"])
    metrics = compute_metrics(
        records=records,
        duration_seconds=metadata.get("duration_seconds"),
        short_shot_seconds=settings["filter_rules"]["short_shot_seconds"],
    )
    status, reasons = evaluate_quality_gate(metadata, metrics, settings["filter_rules"])

    decision_json = settings["decision_json"]
    if decision_json is None:
        decision_json = settings["input_video"].with_name(f"{settings['input_video'].stem}_decision.json")

    report = build_decision_report(
        settings=settings,
        metadata=metadata,
        metrics=metrics,
        status=status,
        reasons=reasons,
        output_csv=output_csv,
        decision_json=decision_json,
        records=records,
        scene_start_images_dir=scene_start_images_dir,
        scene_start_images_saved=scene_start_images_saved,
        scene_start_images_skipped=scene_start_images_skipped,
    )
    write_json_file(report, decision_json)

    print_summary(
        records=records,
        output_csv=output_csv,
        decision_json=decision_json,
        status=status,
        reasons=reasons,
        scene_start_images_dir=scene_start_images_dir,
        scene_start_images_saved=scene_start_images_saved,
        scene_start_images_skipped=scene_start_images_skipped,
    )

    return 2 if status == "reject" else 0


if __name__ == "__main__":
    raise SystemExit(main())

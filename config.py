"""Configuration constants and YAML parsing for the shot-detection pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Default YAML config location.
DEFAULT_CONFIG_PATH = Path("config.yaml")

# Video backends supported by PySceneDetect open_video().
SUPPORTED_BACKENDS = {"pyav", "opencv"}

# Detector aliases accepted in YAML (maps to canonical detector ids).
DETECTOR_ALIASES = {
    "adaptive": "adaptive",
    "detect-adaptive": "adaptive",
    "content": "content",
    "detect-content": "content",
    "hash": "hash",
    "detect-hash": "hash",
    "hist": "hist",
    "detect-hist": "hist",
    "threshold": "threshold",
    "detect-threshold": "threshold",
}

# Default rules for the pre-DB quality gate.
DEFAULT_FILTER_RULES = {
    "min_duration_seconds": 2.0,
    "max_duration_seconds": 21600.0,
    "min_width": 320,
    "min_height": 240,
    "min_fps": 10.0,
    "max_fps": 120.0,
    "min_shots": 1,
    "max_shots": 20000,
    "max_cuts_per_minute": 180.0,
    "min_avg_shot_duration_seconds": 0.2,
    "short_shot_seconds": 0.4,
    "max_short_shot_ratio": 0.6,
    "review_max_cuts_per_minute": 90.0,
    "review_min_avg_shot_duration_seconds": 1.0,
    "review_max_short_shot_ratio": 0.3,
    "require_ffprobe": False,
    "review_on_missing_metadata": True,
}

INT_FILTER_RULE_KEYS = {"min_width", "min_height", "min_shots", "max_shots"}
BOOL_FILTER_RULE_KEYS = {"require_ffprobe", "review_on_missing_metadata"}


def print_usage() -> None:
    """
    Print usage instructions for running the script.

    Inputs:
        None.

    Output:
        None. Prints usage text to stdout.

    Parameters:
        None.
    """
    print("Usage:")
    print("  python main.py")
    print("  python main.py path/to/config.yaml")
    print("")
    print("Default config path: config.yaml")


def resolve_config_path(argv: list[str]) -> Path:
    """
    Resolve configuration file path from command-line arguments.

    Inputs:
        argv: Command-line argument list.

    Output:
        Path: Resolved YAML config path.

    Parameters:
        argv (list[str]): Raw CLI arguments.
    """
    if len(argv) > 2:
        raise ValueError("Too many arguments. Provide only one optional YAML path.")
    if len(argv) == 2:
        arg = argv[1].strip()
        if arg in {"-h", "--help"}:
            print_usage()
            raise SystemExit(0)
        return Path(arg)
    return DEFAULT_CONFIG_PATH


def parse_bool(value: Any, key_name: str) -> bool:
    """
    Parse a bool-like value from config.

    Inputs:
        value: Raw value from YAML.
        key_name: Config key name for error messages.

    Output:
        bool: Parsed boolean value.

    Parameters:
        value (Any): Input value to parse.
        key_name (str): Name of the related config key.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ValueError(f"Config key '{key_name}' must be a boolean value.")


def parse_int(value: Any, key_name: str) -> int:
    """
    Parse an integer value from config.

    Inputs:
        value: Raw value from YAML.
        key_name: Config key name for error messages.

    Output:
        int: Parsed integer value.

    Parameters:
        value (Any): Input value to parse.
        key_name (str): Name of the related config key.
    """
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key '{key_name}' must be an integer.") from exc


def parse_float(value: Any, key_name: str) -> float:
    """
    Parse a numeric value from config.

    Inputs:
        value: Raw value from YAML.
        key_name: Config key name for error messages.

    Output:
        float: Parsed float value.

    Parameters:
        value (Any): Input value to parse.
        key_name (str): Name of the related config key.
    """
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Config key '{key_name}' must be a number.") from exc


def normalize_keys(raw_map: dict[Any, Any], map_name: str) -> dict[str, Any]:
    """
    Normalize mapping keys by replacing '-' with '_'.

    Inputs:
        raw_map: Raw mapping object.
        map_name: Mapping name for error messages.

    Output:
        dict[str, Any]: Mapping with normalized keys.

    Parameters:
        raw_map (dict[Any, Any]): Input mapping to normalize.
        map_name (str): Name of the mapping being normalized.
    """
    normalized: dict[str, Any] = {}
    for key, value in raw_map.items():
        if not isinstance(key, str):
            raise ValueError(f"All keys in '{map_name}' must be strings.")
        normalized[key.replace("-", "_")] = value
    return normalized


def resolve_path(raw_value: Any, base_dir: Path) -> Path:
    """
    Resolve a path value, handling relative paths via config directory.

    Inputs:
        raw_value: Raw path-like config value.
        base_dir: Directory used to resolve relative paths.

    Output:
        Path: Absolute or original absolute path.

    Parameters:
        raw_value (Any): Config path value.
        base_dir (Path): Base directory for relative paths.
    """
    path = Path(str(raw_value))
    if not path.is_absolute():
        return (base_dir / path).absolute()
    return path


def normalize_detector_name(raw_value: Any) -> str:
    """
    Normalize detector alias/name to canonical detector id.

    Inputs:
        raw_value: Detector value from YAML.

    Output:
        str: Canonical detector key.

    Parameters:
        raw_value (Any): Detector name or alias.
    """
    detector_key = str(raw_value).strip().lower()
    if detector_key not in DETECTOR_ALIASES:
        supported = ", ".join(sorted(DETECTOR_ALIASES))
        raise ValueError(f"Invalid detector '{raw_value}'. Use one of: {supported}")
    return DETECTOR_ALIASES[detector_key]


def normalize_detector_params(raw_value: Any) -> dict[str, Any]:
    """
    Normalize detector parameter mapping.

    Inputs:
        raw_value: Raw detector_params value.

    Output:
        dict[str, Any]: Normalized detector params map.

    Parameters:
        raw_value (Any): Detector params object from config.
    """
    if raw_value is None:
        return {}
    if not isinstance(raw_value, dict):
        raise ValueError("Config key 'detector_params' must be a mapping/object.")
    return normalize_keys(raw_value, "detector_params")


def load_yaml_config(config_path: Path) -> dict[str, Any]:
    """
    Load YAML config file and normalize top-level keys.

    Inputs:
        config_path: Path to YAML config file.

    Output:
        dict[str, Any]: Normalized top-level config map.

    Parameters:
        config_path (Path): YAML file location.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file does not exist: {config_path}")
    if not config_path.is_file():
        raise ValueError(f"Config path is not a file: {config_path}")

    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyYAML is required for YAML config.\n"
            "Install with: pip install pyyaml"
        ) from exc

    with config_path.open("r", encoding="utf-8") as file:
        payload = yaml.safe_load(file)

    if payload is None:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("YAML config root must be a mapping/object.")
    return normalize_keys(payload, "config")


def parse_filter_rules(raw_value: Any) -> dict[str, Any]:
    """
    Parse, normalize, and validate filter_rules section.

    Inputs:
        raw_value: Raw filter_rules object from YAML.

    Output:
        dict[str, Any]: Validated filter rules map.

    Parameters:
        raw_value (Any): filter_rules input value.
    """
    if raw_value is None:
        rules = dict(DEFAULT_FILTER_RULES)
    else:
        if not isinstance(raw_value, dict):
            raise ValueError("Config key 'filter_rules' must be a mapping/object.")
        normalized = normalize_keys(raw_value, "filter_rules")
        unknown = sorted(set(normalized) - set(DEFAULT_FILTER_RULES))
        if unknown:
            raise ValueError(f"Unknown filter_rules keys: {', '.join(unknown)}")

        rules = dict(DEFAULT_FILTER_RULES)
        for key, value in normalized.items():
            if key in BOOL_FILTER_RULE_KEYS:
                rules[key] = parse_bool(value, f"filter_rules.{key}")
            elif key in INT_FILTER_RULE_KEYS:
                rules[key] = parse_int(value, f"filter_rules.{key}")
            else:
                rules[key] = parse_float(value, f"filter_rules.{key}")

    if rules["min_duration_seconds"] < 0 or rules["max_duration_seconds"] < 0:
        raise ValueError("filter_rules duration values must be >= 0.")
    if rules["min_duration_seconds"] > rules["max_duration_seconds"]:
        raise ValueError("filter_rules min_duration_seconds cannot be greater than max_duration_seconds.")

    if rules["min_width"] <= 0 or rules["min_height"] <= 0:
        raise ValueError("filter_rules min_width/min_height must be > 0.")
    if rules["min_fps"] <= 0 or rules["max_fps"] <= 0:
        raise ValueError("filter_rules min_fps/max_fps must be > 0.")
    if rules["min_fps"] > rules["max_fps"]:
        raise ValueError("filter_rules min_fps cannot be greater than max_fps.")

    if rules["min_shots"] < 0 or rules["max_shots"] < 0:
        raise ValueError("filter_rules min_shots/max_shots must be >= 0.")
    if rules["min_shots"] > rules["max_shots"]:
        raise ValueError("filter_rules min_shots cannot be greater than max_shots.")

    for ratio_key in {"max_short_shot_ratio", "review_max_short_shot_ratio"}:
        ratio = rules[ratio_key]
        if ratio < 0.0 or ratio > 1.0:
            raise ValueError(f"filter_rules.{ratio_key} must be between 0.0 and 1.0.")

    return rules


def parse_settings(config: dict[str, Any], config_path: Path) -> dict[str, Any]:
    """
    Validate top-level config and convert it to runtime settings.

    Inputs:
        config: Normalized top-level config map.
        config_path: Path of the source YAML file.

    Output:
        dict[str, Any]: Runtime settings dictionary.

    Parameters:
        config (dict[str, Any]): Parsed config content.
        config_path (Path): Source config path.
    """
    allowed_keys = {
        "input_video",
        "output_csv",
        "decision_json",
        "include_scenes_in_json",
        "save_scene_start_images",
        "scene_start_images_dir",
        "backend",
        "detector",
        "detector_params",
        "threshold",
        "min_scene_len",
        "luma_only",
        "show_progress",
        "start_in_scene",
        "filter_rules",
    }
    unknown = sorted(set(config) - allowed_keys)
    if unknown:
        raise ValueError(f"Unknown config keys: {', '.join(unknown)}")

    if "input_video" not in config:
        raise ValueError("Config must include 'input_video'.")

    base_dir = config_path.parent
    input_video = resolve_path(config["input_video"], base_dir)

    output_csv = None
    if config.get("output_csv") is not None:
        output_csv = resolve_path(config["output_csv"], base_dir)

    decision_json = None
    if config.get("decision_json") is not None:
        decision_json = resolve_path(config["decision_json"], base_dir)

    scene_start_images_dir = None
    if config.get("scene_start_images_dir") is not None:
        scene_start_images_dir = resolve_path(config["scene_start_images_dir"], base_dir)

    backend = str(config.get("backend", "pyav")).strip().lower()
    if backend not in SUPPORTED_BACKENDS:
        raise ValueError(
            f"Invalid backend '{backend}'. Use one of: {', '.join(sorted(SUPPORTED_BACKENDS))}"
        )

    detector = normalize_detector_name(config.get("detector", "content"))
    detector_params = normalize_detector_params(config.get("detector_params"))

    return {
        "input_video": input_video,
        "output_csv": output_csv,
        "decision_json": decision_json,
        "include_scenes_in_json": parse_bool(
            config.get("include_scenes_in_json", False),
            "include_scenes_in_json",
        ),
        "save_scene_start_images": parse_bool(
            config.get("save_scene_start_images", False),
            "save_scene_start_images",
        ),
        "scene_start_images_dir": scene_start_images_dir,
        "backend": backend,
        "detector": detector,
        "detector_params": detector_params,
        "threshold": parse_float(config.get("threshold", 27.0), "threshold"),
        "min_scene_len": parse_int(config.get("min_scene_len", 15), "min_scene_len"),
        "luma_only": parse_bool(config.get("luma_only", False), "luma_only"),
        "show_progress": parse_bool(config.get("show_progress", False), "show_progress"),
        "start_in_scene": parse_bool(config.get("start_in_scene", False), "start_in_scene"),
        "filter_rules": parse_filter_rules(config.get("filter_rules")),
    }


def load_settings_from_argv(argv: list[str]) -> dict[str, Any]:
    """
    Load settings end-to-end from CLI arguments.

    Inputs:
        argv: Command-line argument list.

    Output:
        dict[str, Any]: Fully parsed runtime settings.

    Parameters:
        argv (list[str]): Raw CLI arguments.
    """
    config_path = resolve_config_path(argv)
    config = load_yaml_config(config_path)
    return parse_settings(config, config_path)

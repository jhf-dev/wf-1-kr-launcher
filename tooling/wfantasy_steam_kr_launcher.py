#!/usr/bin/env python3
"""Apply and restore Korean WF1 data over the Steam Win10 client.

The Steam build is expected to launch through WindConfig.exe and then
WFantasy_win10.exe. This tool keeps executables intact and overlays only the
resource files that differ structurally between Korean retail data and the
Steam/TW data.
"""

from __future__ import annotations

import argparse
import ctypes
import dataclasses
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

try:
    import winreg
except ImportError:  # pragma: no cover - non-Windows developer host
    winreg = None


KR_DEFAULT = Path(r"C:\Users\early\Downloads\DGGL\Games\WFTact_Win95_230101\Store\WFantasy")
TW_DEFAULT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Wind Fantasy")

BACKUP_DIR_NAME = "_wfantasy_kr_patch_backup"
STATE_FILE_NAME = "wfantasy_kr_patch_state.json"

KR_OVERLAY_FILES = [
    "game.ini",
    "bmp",
    "man",
    "stage",
]

COMPATIBILITY_CHECK_FILES = [
    "face",
    "manani",
    "manbmp",
    "map",
    "mapbmp",
    "Wave",
]

PACK_CHECK_FILES = [
    "bmp",
    "man",
    "stage",
    *COMPATIBILITY_CHECK_FILES,
]

TARGET_EXECUTABLES = [
    "WFantasy_win10.exe",
    "WindConfig.exe",
]

STEAM_GAME_DIR_NAMES = [
    "Wind Fantasy",
]

STANDARD_4_3_RESOLUTIONS = [
    (640, 480),
    (800, 600),
    (1024, 768),
    (1152, 864),
    (1280, 960),
    (1400, 1050),
    (1600, 1200),
    (1920, 1440),
]

DDRAW_RUNTIME_FILES = ("ddraw.dll", "wfantasy_ddraw.ini")
DDRAW_CONFIG_SECTION = "wfantasy_ddraw"

PROCESS_NAMES = {
    "WFantasy",
    "WFantasy_win10",
    "WindConfig",
}


@dataclasses.dataclass(frozen=True)
class FileStatus:
    relative_path: str
    source_path: str | None
    target_path: str | None
    source_sha256: str | None
    target_sha256: str | None
    target_matches_source: bool | None
    size_source: int | None
    size_target: int | None


@dataclasses.dataclass(frozen=True)
class PackStatus:
    relative_path: str
    source_count: int | None
    target_count: int | None
    parse_ok: bool
    same_entry_order: bool | None
    differing_entry_hashes: int | None
    error: str | None = None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def repo_root_from_script() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def ddraw_payload_path() -> Path:
    return repo_root_from_script() / "payload" / "ddraw.dll"


def find_case_insensitive(root: Path, relative_path: str) -> Path | None:
    parts = Path(relative_path).parts
    current = root
    for part in parts:
        if not current.exists() or not current.is_dir():
            return None
        match = None
        for child in current.iterdir():
            if child.name.lower() == part.lower():
                match = child
                break
        if match is None:
            return None
        current = match
    return current if current.exists() else None


def target_path(tw_root: Path, relative_path: str) -> Path:
    existing = find_case_insensitive(tw_root, relative_path)
    if existing is not None:
        return existing
    return tw_root / relative_path


def backup_path_for(tw_root: Path, relative_path: str) -> Path:
    return tw_root / BACKUP_DIR_NAME / relative_path


def state_path(tw_root: Path) -> Path:
    return tw_root / BACKUP_DIR_NAME / STATE_FILE_NAME


def read_state(tw_root: Path) -> dict[str, object] | None:
    path = state_path(tw_root)
    if not path.exists():
        return None
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def has_target_layout(tw_root: Path) -> bool:
    return all(find_case_insensitive(tw_root, name) is not None for name in TARGET_EXECUTABLES)


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            key = str(path.expanduser().resolve()).lower()
        except OSError:
            key = str(path.expanduser().absolute()).lower()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def steam_roots_from_registry() -> list[Path]:
    if winreg is None:
        return []

    locations = [
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", ("SteamPath", "InstallPath")),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", ("InstallPath", "SteamPath")),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam", ("InstallPath", "SteamPath")),
    ]
    roots: list[Path] = []
    for hive, key_name, value_names in locations:
        try:
            with winreg.OpenKey(hive, key_name) as key:
                for value_name in value_names:
                    try:
                        value, _value_type = winreg.QueryValueEx(key, value_name)
                    except OSError:
                        continue
                    if isinstance(value, str) and value.strip():
                        roots.append(Path(value.replace("/", "\\")))
        except OSError:
            continue
    return _dedupe_paths(roots)


def default_steam_roots() -> list[Path]:
    roots = steam_roots_from_registry()
    for env_name in ("ProgramFiles(x86)", "ProgramFiles"):
        value = os.environ.get(env_name)
        if value:
            roots.append(Path(value) / "Steam")
    return _dedupe_paths(roots)


_VDF_PATH_RE = re.compile(r'"path"\s*"((?:\\.|[^"\\])*)"')


def _unescape_vdf_string(value: str) -> str:
    return value.replace(r"\\", "\\").replace(r"\"", '"')


def steam_library_roots(steam_root: Path) -> list[Path]:
    roots = [steam_root]
    libraryfolders = steam_root / "steamapps" / "libraryfolders.vdf"
    if libraryfolders.exists():
        text = libraryfolders.read_text(encoding="utf-8", errors="replace")
        for match in _VDF_PATH_RE.finditer(text):
            roots.append(Path(_unescape_vdf_string(match.group(1))))
    return _dedupe_paths(roots)


def candidate_wf1_roots(steam_root: Path) -> list[Path]:
    candidates: list[Path] = []
    if has_target_layout(steam_root):
        candidates.append(steam_root)
    for library_root in steam_library_roots(steam_root):
        for dirname in STEAM_GAME_DIR_NAMES:
            candidates.append(library_root / "steamapps" / "common" / dirname)
    return _dedupe_paths(candidates)


def detect_steam_wf1_root(steam_roots: list[Path] | None = None) -> Path | None:
    for steam_root in steam_roots if steam_roots is not None else default_steam_roots():
        for candidate in candidate_wf1_roots(steam_root):
            if has_target_layout(candidate):
                return candidate.resolve()
    return None


def file_status(kr_root: Path, tw_root: Path, relative_path: str) -> FileStatus:
    src = find_case_insensitive(kr_root, relative_path)
    dst = find_case_insensitive(tw_root, relative_path)
    src_hash = sha256_file(src) if src is not None and src.is_file() else None
    dst_hash = sha256_file(dst) if dst is not None and dst.is_file() else None
    return FileStatus(
        relative_path=relative_path,
        source_path=str(src) if src is not None else None,
        target_path=str(dst) if dst is not None else None,
        source_sha256=src_hash,
        target_sha256=dst_hash,
        target_matches_source=(src_hash == dst_hash) if src_hash and dst_hash else None,
        size_source=src.stat().st_size if src is not None and src.is_file() else None,
        size_target=dst.stat().st_size if dst is not None and dst.is_file() else None,
    )


def parse_pack(path: Path) -> list[tuple[str, bytes]]:
    data = path.read_bytes()
    if len(data) < 4:
        raise ValueError("pack is too short")
    count = struct.unpack_from("<I", data, 0)[0]
    table_end = 4 + count * 17
    if count <= 0 or count > 20000 or table_end > len(data):
        raise ValueError(f"invalid pack table: count={count}, size={len(data)}")

    rows: list[tuple[str, int]] = []
    for index in range(count):
        row = 4 + index * 17
        offset = struct.unpack_from("<I", data, row)[0]
        raw_name = data[row + 4 : row + 17]
        name = raw_name.split(b"\0", 1)[0].decode("ascii", errors="replace")
        rows.append((name, offset))

    entries: list[tuple[str, bytes]] = []
    for index, (name, offset) in enumerate(rows):
        next_offset = rows[index + 1][1] if index + 1 < len(rows) else len(data)
        if offset < table_end or next_offset < offset or next_offset > len(data):
            raise ValueError(f"invalid entry offset at {index}: {offset:#x}->{next_offset:#x}")
        entries.append((name, data[offset:next_offset]))
    return entries


def pack_status(kr_root: Path, tw_root: Path, relative_path: str) -> PackStatus:
    src = find_case_insensitive(kr_root, relative_path)
    dst = find_case_insensitive(tw_root, relative_path)
    if src is None or dst is None:
        return PackStatus(relative_path, None, None, False, None, None, "missing source or target")
    try:
        source_entries = parse_pack(src)
        target_entries = parse_pack(dst)
    except ValueError as exc:
        return PackStatus(relative_path, None, None, False, None, None, str(exc))

    source_names = [name for name, _payload in source_entries]
    target_names = [name for name, _payload in target_entries]
    same_entry_order = source_names == target_names
    differing_entry_hashes = None
    if same_entry_order:
        differing_entry_hashes = sum(
            1
            for (_source_name, source_payload), (_target_name, target_payload) in zip(
                source_entries, target_entries
            )
            if hashlib.sha256(source_payload).digest() != hashlib.sha256(target_payload).digest()
        )
    return PackStatus(
        relative_path=relative_path,
        source_count=len(source_entries),
        target_count=len(target_entries),
        parse_ok=True,
        same_entry_order=same_entry_order,
        differing_entry_hashes=differing_entry_hashes,
    )


def ensure_target_layout(tw_root: Path) -> None:
    missing = [name for name in TARGET_EXECUTABLES if find_case_insensitive(tw_root, name) is None]
    if missing:
        raise SystemExit("Steam target is missing required files: " + ", ".join(missing))


def ensure_sources(kr_root: Path) -> None:
    missing = [name for name in KR_OVERLAY_FILES if find_case_insensitive(kr_root, name) is None]
    if missing:
        raise SystemExit("KR source is missing overlay files: " + ", ".join(missing))


def running_processes() -> list[dict[str, object]]:
    command = [
        "powershell",
        "-NoProfile",
        "-Command",
        (
            "Get-Process | "
            "Where-Object { @('WFantasy','WFantasy_win10','WindConfig') -contains $_.ProcessName } | "
            "Select-Object Id,ProcessName,Path | ConvertTo-Json -Compress"
        ),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    parsed = json.loads(completed.stdout)
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return parsed
    return []


def ensure_not_running() -> None:
    running = running_processes()
    if running:
        names = ", ".join(f"{item.get('ProcessName')}({item.get('Id')})" for item in running)
        raise SystemExit("Close running WF1 processes before applying/restoring files: " + names)


def backup_file_once(tw_root: Path, relative_path: str) -> None:
    src = target_path(tw_root, relative_path)
    if not src.exists():
        return
    dst = backup_path_for(tw_root, relative_path)
    if dst.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def current_monitor_size() -> tuple[int, int]:
    try:
        user32 = ctypes.windll.user32
        return int(user32.GetSystemMetrics(0)), int(user32.GetSystemMetrics(1))
    except Exception:
        return (640, 480)


def available_4_3_resolutions(
    max_width: int | None = None,
    max_height: int | None = None,
) -> list[tuple[int, int]]:
    if max_width is None or max_height is None:
        max_width, max_height = current_monitor_size()
    available = [
        (width, height)
        for width, height in STANDARD_4_3_RESOLUTIONS
        if width <= max_width and height <= max_height
    ]
    return available or [(640, 480)]


def default_4_3_resolution(
    max_width: int | None = None,
    max_height: int | None = None,
) -> tuple[int, int]:
    available = available_4_3_resolutions(max_width, max_height)
    return (1280, 960) if (1280, 960) in available else available[-1]


def resolution_label(resolution: tuple[int, int]) -> str:
    return f"{resolution[0]} x {resolution[1]}"


def parse_resolution_label(value: str) -> tuple[int, int]:
    parts = value.lower().replace(" ", "").split("x", 1)
    if len(parts) != 2:
        raise ValueError(f"unsupported resolution preset: {value}")
    return int(parts[0]), int(parts[1])


def normalize_display_config(
    display_mode: str | None,
    width: int | None,
    height: int | None,
    left_click_lock: bool | None = None,
    right_click_lock: bool | None = None,
    base_config: dict[str, str] | None = None,
) -> dict[str, int | str]:
    if display_mode is None:
        if width is not None or height is not None:
            raise SystemExit("--width/--height require --display-mode")
        display_mode = base_config.get("mode", "fullscreen") if base_config else "fullscreen"
    if display_mode not in {"fullscreen", "windowed", "borderless"}:
        raise SystemExit(f"unsupported display mode: {display_mode}")

    if display_mode == "windowed":
        if width is None and height is None:
            if base_config:
                width = int(base_config.get("width", "0") or "0")
                height = int(base_config.get("height", "0") or "0")
            if not width or not height:
                width, height = default_4_3_resolution()
        elif width is None or height is None:
            raise SystemExit("windowed mode requires both --width and --height")
        if width <= 0 or height <= 0 or width * 3 != height * 4:
            raise SystemExit("windowed display size must be a positive 4:3 resolution")
    else:
        if width is not None or height is not None:
            raise SystemExit("--width/--height are only supported with --display-mode windowed")
        width, height = 640, 480

    if left_click_lock is None:
        left_click_lock = bool(int(base_config.get("left_click_lock", "1"))) if base_config else True
    if right_click_lock is None:
        right_click_lock = bool(int(base_config.get("right_click_lock", "1"))) if base_config else True

    return {
        "mode": display_mode,
        "width": width,
        "height": height,
        "debug": 0,
        "input_fix": 1,
        "left_click_lock": int(left_click_lock),
        "right_click_lock": int(right_click_lock),
        "audio_focus_fix": 1,
        "inactive_window_spoof": 1,
        "text_cp949": 1,
        "font_charset": "preserve",
        "font_face": "",
    }


def render_ddraw_config(config: dict[str, int | str]) -> bytes:
    ordered_keys = [
        "mode",
        "width",
        "height",
        "debug",
        "input_fix",
        "left_click_lock",
        "right_click_lock",
        "audio_focus_fix",
        "inactive_window_spoof",
        "text_cp949",
        "font_charset",
        "font_face",
    ]
    lines = [f"[{DDRAW_CONFIG_SECTION}]"]
    lines.extend(f"{key}={config[key]}" for key in ordered_keys)
    return ("\n".join(lines) + "\n").encode("ascii")


def read_ddraw_config(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="ascii", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("[") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def previous_launcher_created_runtime(
    previous_state: dict[str, object] | None,
    relative_path: str,
    before_hash: str | None,
) -> bool:
    if previous_state is None or before_hash is None:
        return False
    runtime_report = previous_state.get("directdraw_runtime")
    if not isinstance(runtime_report, dict):
        return False
    for item in runtime_report.get("files", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("path", "")).replace("\\", "/").lower() != relative_path.replace("\\", "/").lower():
            continue
        if item.get("target_exists_before"):
            return False
        expected_hashes = {
            value
            for value in (item.get("target_sha256_after"), item.get("desired_sha256"))
            if isinstance(value, str)
        }
        return before_hash in expected_hashes
    return False


def runtime_file_report(
    tw_root: Path,
    relative_path: str,
    desired_data: bytes,
    dry_run: bool,
    previous_state: dict[str, object] | None = None,
) -> dict[str, object]:
    target = target_path(tw_root, relative_path)
    before_hash = sha256_file(target) if target.exists() else None
    desired_hash = sha256_bytes(desired_data)
    changed = before_hash != desired_hash
    target_present_before = target.exists()
    launcher_created_before = previous_launcher_created_runtime(previous_state, relative_path, before_hash)
    target_exists_before = target_present_before and not launcher_created_before
    if changed and not dry_run:
        if target_present_before and not launcher_created_before:
            backup_file_once(tw_root, relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(desired_data)
    return {
        "path": relative_path,
        "changed": changed,
        "target_exists_before": target_exists_before,
        "target_present_before": target_present_before,
        "launcher_created_before": launcher_created_before,
        "replaced_launcher_created_file": launcher_created_before and changed and not dry_run,
        "target_sha256_before": before_hash,
        "target_sha256_after": desired_hash if changed and not dry_run else before_hash,
        "desired_sha256": desired_hash,
        "size": len(desired_data),
        "dry_run": dry_run,
    }


def install_directdraw_runtime(
    tw_root: Path,
    display_mode: str | None,
    width: int | None,
    height: int | None,
    left_click_lock: bool | None,
    right_click_lock: bool | None,
    dry_run: bool,
    install_when_unspecified: bool = True,
) -> dict[str, object]:
    payload = ddraw_payload_path()
    if not payload.exists():
        raise SystemExit(
            f"DirectDraw/CP949 runtime payload is missing: {payload}. "
            "Build it with tooling\\build_ddraw_proxy.py before applying the patch."
        )
    has_display_options = display_mode is not None or width is not None or height is not None
    has_click_lock_options = left_click_lock is not None or right_click_lock is not None
    if not install_when_unspecified and not has_display_options and not has_click_lock_options:
        return {
            "changed": False,
            "supported": True,
            "dry_run": dry_run,
            "payload": str(payload),
            "config": None,
            "files": [],
            "skipped": True,
            "reason": "display runtime unchanged",
        }

    base_config = read_ddraw_config(target_path(tw_root, "wfantasy_ddraw.ini")) if not install_when_unspecified else None
    config = normalize_display_config(display_mode, width, height, left_click_lock, right_click_lock, base_config)
    dll_data = payload.read_bytes()
    config_data = render_ddraw_config(config)
    previous_state = read_state(tw_root)
    files = [
        runtime_file_report(tw_root, "ddraw.dll", dll_data, dry_run, previous_state),
        runtime_file_report(tw_root, "wfantasy_ddraw.ini", config_data, dry_run, previous_state),
    ]
    return {
        "changed": any(bool(item["changed"]) for item in files),
        "supported": True,
        "dry_run": dry_run,
        "payload": str(payload),
        "config": config,
        "files": files,
    }


def directdraw_runtime_status(tw_root: Path) -> dict[str, object]:
    payload = ddraw_payload_path()
    target_dll = target_path(tw_root, "ddraw.dll")
    target_config = target_path(tw_root, "wfantasy_ddraw.ini")
    payload_hash = sha256_file(payload) if payload.exists() else None
    target_hash = sha256_file(target_dll) if target_dll.exists() else None
    return {
        "payload": str(payload),
        "payload_exists": payload.exists(),
        "payload_sha256": payload_hash,
        "ddraw_dll": {
            "exists": target_dll.exists(),
            "sha256": target_hash,
            "matches_payload": (payload_hash == target_hash) if payload_hash and target_hash else None,
        },
        "config": {
            "exists": target_config.exists(),
            "values": read_ddraw_config(target_config),
        },
    }


def copy_overlay_file(kr_root: Path, tw_root: Path, relative_path: str, dry_run: bool) -> dict[str, object]:
    src = find_case_insensitive(kr_root, relative_path)
    if src is None:
        raise SystemExit(f"missing KR source file: {relative_path}")
    dst = target_path(tw_root, relative_path)
    before_hash = sha256_file(dst) if dst.exists() else None
    source_hash = sha256_file(src)
    changed = before_hash != source_hash
    report = {
        "path": relative_path,
        "source": str(src),
        "target": str(dst),
        "target_exists_before": dst.exists(),
        "changed": changed,
        "target_sha256_before": before_hash,
        "source_sha256": source_hash,
        "size_source": src.stat().st_size,
        "size_target_before": dst.stat().st_size if dst.exists() else None,
        "dry_run": dry_run,
    }
    if changed and not dry_run:
        backup_file_once(tw_root, relative_path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    report["target_sha256_after"] = sha256_file(dst) if dst.exists() else None
    report["size_target_after"] = dst.stat().st_size if dst.exists() else None
    return report


def write_state(tw_root: Path, report: dict[str, object]) -> None:
    path = state_path(tw_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def status(args: argparse.Namespace) -> dict[str, object]:
    kr_root = args.kr_root.resolve()
    tw_root = args.tw_root.resolve()
    all_files = [*KR_OVERLAY_FILES, *COMPATIBILITY_CHECK_FILES]
    return {
        "action": "status",
        "kr_root": str(kr_root),
        "tw_root": str(tw_root),
        "target_layout_ok": all(find_case_insensitive(tw_root, name) is not None for name in TARGET_EXECUTABLES),
        "overlay": [dataclasses.asdict(file_status(kr_root, tw_root, name)) for name in KR_OVERLAY_FILES],
        "compatible_files": [
            dataclasses.asdict(file_status(kr_root, tw_root, name)) for name in COMPATIBILITY_CHECK_FILES
        ],
        "pack_status": [dataclasses.asdict(pack_status(kr_root, tw_root, name)) for name in PACK_CHECK_FILES],
        "directdraw_runtime": directdraw_runtime_status(tw_root),
        "backup_dir_exists": (tw_root / BACKUP_DIR_NAME).exists(),
        "running_processes": running_processes(),
    }


def apply_patch(args: argparse.Namespace) -> dict[str, object]:
    kr_root = args.kr_root.resolve()
    tw_root = args.tw_root.resolve()
    ensure_sources(kr_root)
    ensure_target_layout(tw_root)
    ensure_not_running()

    pack_reports = [pack_status(kr_root, tw_root, name) for name in PACK_CHECK_FILES]
    bad_packs = [item for item in pack_reports if not item.parse_ok or item.same_entry_order is False]
    if bad_packs:
        raise SystemExit("archive structure check failed: " + json.dumps([dataclasses.asdict(x) for x in bad_packs]))

    copied = [copy_overlay_file(kr_root, tw_root, name, dry_run=args.dry_run) for name in KR_OVERLAY_FILES]
    runtime_report = install_directdraw_runtime(
        tw_root,
        getattr(args, "display_mode", None),
        getattr(args, "width", None),
        getattr(args, "height", None),
        getattr(args, "left_click_lock", None),
        getattr(args, "right_click_lock", None),
        dry_run=args.dry_run,
    )
    report = {
        "action": "apply",
        "dry_run": args.dry_run,
        "kr_root": str(kr_root),
        "tw_root": str(tw_root),
        "copied": copied,
        "directdraw_runtime": runtime_report,
        "compatible_files": [
            dataclasses.asdict(file_status(kr_root, tw_root, name)) for name in COMPATIBILITY_CHECK_FILES
        ],
        "pack_status": [dataclasses.asdict(item) for item in pack_reports],
        "backup_dir": str(tw_root / BACKUP_DIR_NAME),
    }
    if not args.dry_run:
        write_state(tw_root, report)
    return report


def restore_patch(args: argparse.Namespace) -> dict[str, object]:
    _kr_root = args.kr_root.resolve()
    tw_root = args.tw_root.resolve()
    ensure_target_layout(tw_root)
    ensure_not_running()

    backup_root = tw_root / BACKUP_DIR_NAME
    if not backup_root.exists():
        raise SystemExit(f"backup directory does not exist: {backup_root}")

    restored: list[dict[str, object]] = []
    restored_paths: set[str] = set()
    for backup in sorted(backup_root.rglob("*")):
        if not backup.is_file() or backup.name == STATE_FILE_NAME:
            continue
        relative_path = str(backup.relative_to(backup_root))
        target = tw_root / relative_path
        before_hash = sha256_file(target) if target.exists() else None
        backup_hash = sha256_file(backup)
        if not args.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, target)
        restored.append(
            {
                "path": relative_path,
                "target": str(target),
                "target_sha256_before": before_hash,
                "backup_sha256": backup_hash,
                "dry_run": args.dry_run,
            }
        )
        restored_paths.add(relative_path.replace("\\", "/").lower())

    removed_created_runtime: list[str] = []
    skipped_created_runtime: list[dict[str, object]] = []
    state_file = state_path(tw_root)
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        runtime_report = state.get("directdraw_runtime") if isinstance(state, dict) else None
        if isinstance(runtime_report, dict):
            for item in runtime_report.get("files", []):
                if not isinstance(item, dict):
                    continue
                relative_path = str(item.get("path", ""))
                key = relative_path.replace("\\", "/").lower()
                if relative_path not in DDRAW_RUNTIME_FILES or key in restored_paths:
                    continue
                if item.get("target_exists_before"):
                    continue
                target = target_path(tw_root, relative_path)
                if not target.exists():
                    continue
                expected_hash = item.get("target_sha256_after") or item.get("desired_sha256")
                current_hash = sha256_file(target)
                if expected_hash and current_hash != expected_hash:
                    skipped_created_runtime.append(
                        {
                            "path": relative_path,
                            "reason": "current file differs from launcher-created runtime file",
                            "current_sha256": current_hash,
                            "expected_sha256": expected_hash,
                        }
                    )
                    continue
                if not args.dry_run:
                    target.unlink()
                removed_created_runtime.append(relative_path)
    report = {
        "action": "restore",
        "dry_run": args.dry_run,
        "tw_root": str(tw_root),
        "backup_dir": str(backup_root),
        "restored": restored,
        "removed_created_runtime": sorted(removed_created_runtime),
        "skipped_created_runtime": skipped_created_runtime,
    }
    if not args.dry_run:
        write_state(tw_root, report)
    return report


def launch_executable(args: argparse.Namespace, executable_name: str, action: str) -> dict[str, object]:
    tw_root = args.tw_root.resolve()
    ensure_target_layout(tw_root)
    exe = target_path(tw_root, executable_name)
    if not exe.exists():
        raise SystemExit(f"{executable_name} not found: {exe}")

    if not getattr(args, "no_apply", False):
        apply_report = apply_patch(args)
        runtime_report = apply_report.get("directdraw_runtime", {"changed": False})
    else:
        if not args.dry_run:
            ensure_not_running()
        runtime_report = install_directdraw_runtime(
            tw_root,
            getattr(args, "display_mode", None),
            getattr(args, "width", None),
            getattr(args, "height", None),
            getattr(args, "left_click_lock", None),
            getattr(args, "right_click_lock", None),
            dry_run=args.dry_run,
            install_when_unspecified=False,
        )
        apply_report = {"skipped": True}
        if runtime_report.get("changed") and not args.dry_run:
            write_state(
                tw_root,
                {
                    "action": "directdraw_runtime",
                    "dry_run": False,
                    "tw_root": str(tw_root),
                    "directdraw_runtime": runtime_report,
                },
            )

    if args.dry_run:
        return {
            "action": action,
            "dry_run": True,
            "would_run": str(exe),
            "apply": apply_report,
            "directdraw_runtime": runtime_report,
        }

    subprocess.Popen([str(exe)], cwd=str(tw_root))
    return {
        "action": action,
        "launched": str(exe),
        "apply": apply_report,
        "directdraw_runtime": runtime_report,
    }


def launch(args: argparse.Namespace) -> dict[str, object]:
    return launch_executable(args, "WindConfig.exe", "launch")


def launch_win10(args: argparse.Namespace) -> dict[str, object]:
    return launch_executable(args, "WFantasy_win10.exe", "launch_win10")


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kr-root", type=Path, default=KR_DEFAULT)
    parser.add_argument("--tw-root", type=Path, default=TW_DEFAULT)
    parser.add_argument(
        "--display-mode",
        choices=["fullscreen", "windowed", "borderless"],
        help="DirectDraw runtime mode; default installs fullscreen passthrough with CP949 text hooks",
    )
    parser.add_argument("--width", type=int, help="windowed 4:3 width")
    parser.add_argument("--height", type=int, help="windowed 4:3 height")
    left_click = parser.add_mutually_exclusive_group()
    left_click.add_argument("--left-click-lock", dest="left_click_lock", action="store_true")
    left_click.add_argument("--no-left-click-lock", dest="left_click_lock", action="store_false")
    right_click = parser.add_mutually_exclusive_group()
    right_click.add_argument("--right-click-lock", dest="right_click_lock", action="store_true")
    right_click.add_argument("--no-right-click-lock", dest="right_click_lock", action="store_false")
    parser.set_defaults(left_click_lock=None, right_click_lock=None)
    parser.add_argument("--dry-run", action="store_true")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_status = sub.add_parser("status", help="show overlay and compatibility state")
    add_common_args(p_status)

    p_apply = sub.add_parser("apply", help="apply KR overlay files")
    add_common_args(p_apply)

    p_restore = sub.add_parser("restore", help="restore files from backup")
    add_common_args(p_restore)

    p_launch = sub.add_parser("launch", help="apply if needed, then start WindConfig.exe")
    add_common_args(p_launch)
    p_launch.add_argument("--no-apply", action="store_true", help="launch without applying files first")

    p_launch_win10 = sub.add_parser("launch-win10", help="apply if needed, then start WFantasy_win10.exe directly")
    add_common_args(p_launch_win10)
    p_launch_win10.add_argument("--no-apply", action="store_true", help="launch without applying files first")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "status":
        report = status(args)
    elif args.command == "apply":
        report = apply_patch(args)
    elif args.command == "restore":
        report = restore_patch(args)
    elif args.command == "launch":
        report = launch(args)
    elif args.command == "launch-win10":
        report = launch_win10(args)
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

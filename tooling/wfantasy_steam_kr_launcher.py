#!/usr/bin/env python3
"""Apply and restore Korean WF1 data over the Steam Win10 client.

The Steam build is expected to launch through WindConfig.exe and then
WFantasy_win10.exe. This tool keeps executables intact and overlays only the
resource files that differ structurally between Korean retail data and the
Steam/TW data.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path


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
    report = {
        "action": "apply",
        "dry_run": args.dry_run,
        "kr_root": str(kr_root),
        "tw_root": str(tw_root),
        "copied": copied,
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
    report = {
        "action": "restore",
        "dry_run": args.dry_run,
        "tw_root": str(tw_root),
        "backup_dir": str(backup_root),
        "restored": restored,
    }
    if not args.dry_run:
        write_state(tw_root, report)
    return report


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kr-root", type=Path, default=KR_DEFAULT)
    parser.add_argument("--tw-root", type=Path, default=TW_DEFAULT)
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

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "status":
        report = status(args)
    elif args.command == "apply":
        report = apply_patch(args)
    elif args.command == "restore":
        report = restore_patch(args)
    else:  # pragma: no cover
        raise SystemExit(f"unknown command: {args.command}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

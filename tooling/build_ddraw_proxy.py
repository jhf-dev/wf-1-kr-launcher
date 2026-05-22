#!/usr/bin/env python3
"""Build the 32-bit WF1 DirectDraw and CP949 text proxy used by the launcher."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tooling" / "runtime" / "ddraw_proxy.cpp"
OUTPUT = ROOT / "payload" / "ddraw.dll"


def find_compiler() -> str:
    for name in ["i686-w64-mingw32-g++", "g++"]:
        path = shutil.which(name)
        if path:
            return path
    raise SystemExit("No MinGW C++ compiler found. Expected i686-w64-mingw32-g++.")


def build(output: Path = OUTPUT) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = find_compiler()
    command = [
        compiler,
        "-shared",
        "-m32",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Wno-dll-attribute-on-redeclaration",
        "-static-libgcc",
        "-static-libstdc++",
        "-Wl,--kill-at",
        "-o",
        str(output),
        str(SOURCE),
        "-luser32",
        "-lgdi32",
        "-lole32",
        "-ldxguid",
        "-luuid",
    ]
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    build(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

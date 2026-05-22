#!/usr/bin/env python3
"""Tkinter GUI for applying the Korean WF1 patch to the Taiwan Steam build."""

from __future__ import annotations

import argparse
import dataclasses
import json
import queue
import sys
import threading
import traceback
from pathlib import Path
from tkinter import BOTH, END, LEFT, X, filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import wfantasy_steam_kr_launcher as core


APP_TITLE = "Wind Fantasy KR -> Steam TW 패치 런처"
APP_RIGHTS_NOTICE = "Team-JHF 비공식 패치 런처 - 원본 게임 리소스의 권리는 각 원 권리자에게 있습니다."
LAUNCHER_ART_RELATIVE = Path("assets") / "launcher_art.gif"
LAUNCHER_ART_PANEL_WIDTH = 330
LAUNCHER_ART_FOCUS_X = 0.58
LAUNCHER_ART_FOCUS_Y = 0.50
DISPLAY_UNCHANGED = "건드리지 않음"
DISPLAY_WINDOWED = "창모드"
DISPLAY_BORDERLESS = "전체 창 모드"
DISPLAY_FULLSCREEN = "전체화면"


def default_kr_root() -> str:
    return ""


def default_tw_root() -> str:
    detected = core.detect_steam_wf1_root()
    return str(detected) if detected else ""


def make_args(
    kr_root: Path,
    tw_root: Path,
    *,
    dry_run: bool = False,
    display_mode: str | None = None,
    width: int | None = None,
    height: int | None = None,
    no_apply: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        kr_root=kr_root,
        tw_root=tw_root,
        dry_run=dry_run,
        display_mode=display_mode,
        width=width,
        height=height,
        no_apply=no_apply,
    )


def compact_apply_summary(report: dict[str, object]) -> dict[str, object]:
    copied = report.get("copied", [])
    changed_files = []
    if isinstance(copied, list):
        for item in copied:
            if isinstance(item, dict) and item.get("changed"):
                changed_files.append(item.get("path"))

    summary: dict[str, object] = {
        "changed_overlay_files": changed_files,
        "directdraw_runtime": report.get("directdraw_runtime"),
        "backup_dir": report.get("backup_dir"),
    }
    if "launch" in report:
        summary["launch"] = report["launch"]
    return summary


class PatchGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)

        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.launcher_art_source = self._load_launcher_art()
        self.launcher_art_rendered: tk.PhotoImage | None = None
        self.launcher_art_canvas: tk.Canvas | None = None

        self.geometry("1120x720")
        self.minsize(980, 620)

        self.kr_path = tk.StringVar(value=default_kr_root())
        self.tw_path = tk.StringVar(value=default_tw_root())
        self.display_mode = tk.StringVar(value=DISPLAY_UNCHANGED)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.resolution_presets = core.available_4_3_resolutions(screen_width, screen_height)
        self.resolution_value = tk.StringVar(
            value=core.resolution_label(core.default_4_3_resolution(screen_width, screen_height))
        )
        self.launch_after_apply = tk.BooleanVar(value=False)
        self.status_text = tk.StringVar(value="대기 중")

        self._build_ui()
        self.after(100, self._drain_events)

    def _build_ui(self) -> None:
        root = ttk.Frame(self)
        root.pack(fill=BOTH, expand=True)

        self._build_art_panel(root)

        main = ttk.Frame(root, padding=14)
        main.pack(side=LEFT, fill=BOTH, expand=True)

        title = ttk.Label(main, text=APP_TITLE, font=("", 15, "bold"))
        title.pack(anchor="w")

        subtitle = ttk.Label(
            main,
            text="기존 한국어판 파일을 읽어 Steam판 Win10 클라이언트에 적용하고, CP949 출력과 실행 표시 옵션을 함께 반영합니다.",
        )
        subtitle.pack(anchor="w", pady=(4, 4))

        notice = ttk.Label(
            main,
            text="패치에는 기존 한국어판의 리소스 파일이 필요합니다. 이 런처와 패치 파일은 게임 리소스를 포함하지 않습니다.",
            foreground="#8a3d00",
        )
        notice.pack(anchor="w", pady=(0, 14))

        self._path_row(main, "한국어판 폴더", self.kr_path, self._browse_kr)
        self._path_row(main, "Steam 대만판 폴더", self.tw_path, self._browse_tw)

        options = ttk.LabelFrame(main, text="실행 옵션", padding=10)
        options.pack(fill=X, pady=(8, 10))

        ttk.Label(options, text="화면 모드").pack(side=LEFT)
        display = ttk.Combobox(
            options,
            textvariable=self.display_mode,
            values=[DISPLAY_UNCHANGED, DISPLAY_WINDOWED, DISPLAY_BORDERLESS, DISPLAY_FULLSCREEN],
            state="readonly",
            width=14,
        )
        display.pack(side=LEFT, padx=(8, 16))
        display.bind("<<ComboboxSelected>>", lambda _event: self._sync_resolution_state())

        ttk.Label(options, text="해상도").pack(side=LEFT)
        self.resolution_combo = ttk.Combobox(
            options,
            textvariable=self.resolution_value,
            values=[core.resolution_label(item) for item in self.resolution_presets],
            state="disabled",
            width=12,
        )
        self.resolution_combo.pack(side=LEFT, padx=(8, 16))
        ttk.Checkbutton(options, text="적용 후 게임 실행", variable=self.launch_after_apply).pack(side=LEFT)

        buttons = ttk.Frame(main)
        buttons.pack(fill=X, pady=(0, 10))
        self.apply_button = ttk.Button(buttons, text="패치 적용", command=self.apply_patch)
        self.apply_button.pack(side=LEFT)
        self.status_button = ttk.Button(buttons, text="상태 확인", command=self.check_status)
        self.status_button.pack(side=LEFT, padx=(8, 0))
        self.restore_button = ttk.Button(buttons, text="TW 원본 복구", command=self.restore_patch)
        self.restore_button.pack(side=LEFT, padx=(8, 0))
        self.game_button = ttk.Button(buttons, text="게임 실행", command=self.launch_game)
        self.game_button.pack(side=LEFT, padx=(8, 0))
        self.config_button = ttk.Button(buttons, text="WindConfig 실행", command=self.launch_config)
        self.config_button.pack(side=LEFT, padx=(8, 0))

        ttk.Label(main, textvariable=self.status_text).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.Frame(main)
        log_frame.pack(fill=BOTH, expand=True)
        self.log = tk.Text(log_frame, wrap="word", height=18)
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        scrollbar.pack(side="right", fill="y")

        rights = ttk.Label(main, text=APP_RIGHTS_NOTICE, foreground="#666666")
        rights.pack(anchor="w", pady=(8, 0))

        if self.tw_path.get():
            self._log(f"Steam판 폴더를 자동으로 찾았습니다: {self.tw_path.get()}")
        else:
            self._log("Steam판 폴더를 자동으로 찾지 못했습니다. Steam 대만판 폴더를 직접 선택해 주세요.")
        self._log("한국어판 폴더는 사용자가 보유한 정식 한국어판 경로를 직접 선택해야 합니다.")
        self._log("화면 모드를 지정하지 않으면 패치 적용 시 CP949 런타임은 전체화면 통과 모드로 설치됩니다.")

    def _path_row(self, parent: ttk.Frame, label: str, variable: tk.StringVar, command) -> None:
        row = ttk.Frame(parent)
        row.pack(fill=X, pady=4)
        ttk.Label(row, text=label, width=18).pack(side=LEFT)
        ttk.Entry(row, textvariable=variable).pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        ttk.Button(row, text="찾기", command=command).pack(side=LEFT)

    def _build_art_panel(self, parent: ttk.Frame) -> None:
        panel = tk.Frame(parent, width=LAUNCHER_ART_PANEL_WIDTH, background="#f7f4f4")
        panel.pack(side="right", fill=BOTH)
        panel.pack_propagate(False)

        self.launcher_art_canvas = tk.Canvas(
            panel,
            highlightthickness=0,
            borderwidth=0,
            background="#f7f4f4",
        )
        self.launcher_art_canvas.pack(fill=BOTH, expand=True)
        if self.launcher_art_source:
            self.launcher_art_canvas.bind("<Configure>", self._redraw_launcher_art)
        else:
            self.launcher_art_canvas.bind("<Configure>", self._redraw_fallback_art)

    def _redraw_launcher_art(self, event: tk.Event) -> None:
        if self.launcher_art_canvas is None or self.launcher_art_source is None:
            return
        target_width = max(1, int(event.width))
        target_height = max(1, int(event.height))
        source_width = self.launcher_art_source.width()
        source_height = self.launcher_art_source.height()

        subsample = max(1, min(source_width // target_width, source_height // target_height))
        image = self.launcher_art_source.subsample(subsample, subsample)

        x = int((target_width / 2) - (image.width() * LAUNCHER_ART_FOCUS_X))
        y = int((target_height / 2) - (image.height() * LAUNCHER_ART_FOCUS_Y))
        self.launcher_art_rendered = image
        self.launcher_art_canvas.delete("all")
        self.launcher_art_canvas.create_image(x, y, anchor="nw", image=self.launcher_art_rendered)

    def _redraw_fallback_art(self, event: tk.Event) -> None:
        if self.launcher_art_canvas is None:
            return
        width = max(1, int(event.width))
        height = max(1, int(event.height))
        canvas = self.launcher_art_canvas
        canvas.delete("all")
        canvas.create_rectangle(0, 0, width, height, fill="#37436b", outline="")
        canvas.create_polygon(0, height, width, int(height * 0.42), width, height, fill="#b99a4e", outline="")
        canvas.create_oval(int(width * 0.58), -120, int(width * 1.45), int(height * 0.42), fill="#202839", outline="")
        canvas.create_oval(-180, int(height * 0.72), int(width * 0.75), int(height * 1.3), fill="#202839", outline="")
        for offset in range(-height, height + width, 42):
            canvas.create_line(0, offset, width, offset + int(width * 0.55), fill="#f3f0df", width=2)
        canvas.create_text(
            42,
            90,
            anchor="nw",
            text="Wind\nFantasy",
            fill="#ffffff",
            font=("Segoe UI", 32, "bold"),
        )
        canvas.create_text(
            46,
            205,
            anchor="nw",
            text="KR -> Steam TW",
            fill="#ffe49a",
            font=("Segoe UI", 15),
        )
        canvas.create_text(
            42,
            height - 72,
            anchor="nw",
            text="Team-JHF patch launcher",
            fill="#ffffff",
            font=("Segoe UI", 11),
        )

    def _launcher_art_candidates(self) -> list[Path]:
        candidates: list[Path] = []
        if getattr(sys, "frozen", False):
            exe_dir = Path(sys.executable).resolve().parent
            candidates.append(exe_dir / LAUNCHER_ART_RELATIVE)
            candidates.append(exe_dir / LAUNCHER_ART_RELATIVE.name)
            bundle_dir = getattr(sys, "_MEIPASS", None)
            if bundle_dir:
                candidates.append(Path(bundle_dir) / LAUNCHER_ART_RELATIVE)
        else:
            repo_root = Path(__file__).resolve().parents[1]
            candidates.append(repo_root / LAUNCHER_ART_RELATIVE)
        return candidates

    def _load_launcher_art(self) -> tk.PhotoImage | None:
        for candidate in self._launcher_art_candidates():
            if not candidate.is_file():
                continue
            try:
                return tk.PhotoImage(file=str(candidate))
            except tk.TclError:
                continue
        return None

    def _browse_kr(self) -> None:
        initialdir = self.kr_path.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(title="한국어판 폴더 선택", initialdir=initialdir)
        if selected:
            self.kr_path.set(selected)

    def _browse_tw(self) -> None:
        initialdir = self.tw_path.get().strip() or str(Path.home())
        selected = filedialog.askdirectory(title="Steam 대만판 폴더 선택", initialdir=initialdir)
        if selected:
            self.tw_path.set(selected)

    def _display_mode_arg(self) -> str | None:
        value = self.display_mode.get()
        if value == DISPLAY_WINDOWED:
            return "windowed"
        if value == DISPLAY_BORDERLESS:
            return "borderless"
        if value == DISPLAY_FULLSCREEN:
            return "fullscreen"
        return None

    def _sync_resolution_state(self) -> None:
        state = "readonly" if self.display_mode.get() == DISPLAY_WINDOWED else "disabled"
        self.resolution_combo.configure(state=state)

    def _resolution_args(self) -> tuple[int | None, int | None]:
        if self._display_mode_arg() != "windowed":
            return None, None
        try:
            width, height = core.parse_resolution_label(self.resolution_value.get())
        except ValueError as exc:
            raise ValueError("해상도는 목록에 있는 4:3 프리셋만 선택할 수 있습니다.") from exc
        if (width, height) not in self.resolution_presets:
            raise ValueError("현재 모니터 해상도 이하의 4:3 프리셋만 선택할 수 있습니다.")
        return width, height

    def _path_from_entry(self, variable: tk.StringVar, label: str, *, required: bool) -> Path:
        value = variable.get().strip()
        if value:
            return Path(value).expanduser()
        if required:
            raise ValueError(f"{label}를 선택해 주세요.")
        return Path.cwd()

    def _args(
        self,
        *,
        dry_run: bool = False,
        no_apply: bool = False,
        require_kr: bool = True,
    ) -> argparse.Namespace:
        kr_root = self._path_from_entry(self.kr_path, "한국어판 폴더", required=require_kr)
        tw_root = self._path_from_entry(self.tw_path, "Steam 대만판 폴더", required=True)
        width, height = self._resolution_args()
        return make_args(
            kr_root,
            tw_root,
            dry_run=dry_run,
            display_mode=self._display_mode_arg(),
            width=width,
            height=height,
            no_apply=no_apply,
        )

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for button in [
            self.apply_button,
            self.status_button,
            self.restore_button,
            self.game_button,
            self.config_button,
        ]:
            button.configure(state=state)

    def _run_worker(self, label: str, fn) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_TITLE, "이미 작업이 진행 중입니다.")
            return
        self._set_busy(True)
        self.status_text.set(label)
        self._log(f"\n[{label}] 시작")

        def target() -> None:
            try:
                result = fn()
            except SystemExit as exc:
                self.events.put(("error", str(exc)))
            except Exception:
                self.events.put(("error", traceback.format_exc()))
            else:
                self.events.put(("result", result))
            finally:
                self.events.put(("done", label))

        self.worker = threading.Thread(target=target, daemon=True)
        self.worker.start()

    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "result":
                    self._handle_result(payload)
                elif kind == "error":
                    self._log(str(payload))
                    messagebox.showerror(APP_TITLE, str(payload))
                elif kind == "done":
                    self.status_text.set("완료")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _handle_result(self, payload: object) -> None:
        if isinstance(payload, dict) and payload.get("action") == "apply":
            self._log(json.dumps(compact_apply_summary(payload), ensure_ascii=False, indent=2))
        else:
            self._log(json.dumps(payload, ensure_ascii=False, indent=2, default=self._json_default))

    @staticmethod
    def _json_default(value: object) -> object:
        if dataclasses.is_dataclass(value):
            return dataclasses.asdict(value)
        if isinstance(value, Path):
            return str(value)
        return repr(value)

    def _log(self, text: str) -> None:
        self.log.insert(END, text + "\n")
        self.log.see(END)

    def apply_patch(self) -> None:
        def work() -> dict[str, object]:
            args = self._args()
            report = core.apply_patch(args)
            if self.launch_after_apply.get():
                launch_args = self._args(no_apply=True, require_kr=False)
                launch_report = core.launch_win10(launch_args)
                report["launch"] = launch_report
            return report

        self._run_worker("패치 적용 중", work)

    def check_status(self) -> None:
        self._run_worker("상태 확인 중", lambda: core.status(self._args(dry_run=True)))

    def restore_patch(self) -> None:
        if not messagebox.askyesno(APP_TITLE, "백업된 TW 원본 파일로 복구할까요?"):
            return
        self._run_worker("원본 복구 중", lambda: core.restore_patch(self._args(require_kr=False)))

    def launch_game(self) -> None:
        self._run_worker(
            "게임 실행 중",
            lambda: core.launch_win10(self._args(no_apply=True, require_kr=False)),
        )

    def launch_config(self) -> None:
        self._run_worker(
            "WindConfig 실행 중",
            lambda: core.launch(self._args(no_apply=True, require_kr=False)),
        )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv == ["--self-test"]:
        _ = default_kr_root()
        _ = default_tw_root()
        payload = core.ddraw_payload_path()
        if not payload.exists():
            raise SystemExit(f"DirectDraw/CP949 runtime payload is missing: {payload}")
        return 0
    app = PatchGui()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

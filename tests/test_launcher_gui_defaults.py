import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
TOOLING = ROOT / "tooling"
if str(TOOLING) not in sys.path:
    sys.path.insert(0, str(TOOLING))

import wfantasy_steam_kr_launcher as core
import wfantasy_steam_kr_patch_gui as gui


def write_target_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in core.TARGET_EXECUTABLES:
        (root / name).write_bytes(b"placeholder")


def write_kr_layout(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for name in core.KR_OVERLAY_FILES:
        (root / name.upper()).write_bytes(b"placeholder")


class LauncherGuiDefaultsTest(unittest.TestCase):
    def test_detects_wind_fantasy_from_steam_libraryfolders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            steam_root = temp / "Steam"
            library = temp / "SteamLibrary"
            game_root = library / "steamapps" / "common" / "Wind Fantasy"
            write_target_layout(game_root)

            steamapps = steam_root / "steamapps"
            steamapps.mkdir(parents=True)
            escaped_path = str(library).replace("\\", "\\\\")
            (steamapps / "libraryfolders.vdf").write_text(
                f'"libraryfolders" {{ "0" {{ "path" "{escaped_path}" }} }}',
                encoding="utf-8",
            )

            detected = core.detect_steam_wf1_root(steam_roots=[steam_root])

            self.assertEqual(game_root.resolve(), detected)

    def test_gui_leaves_kr_blank_without_recent_path_and_prefills_detected_steam_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            detected_root = Path(r"C:\Steam\steamapps\common\Wind Fantasy")
            settings_path = Path(temp_dir) / "settings.json"
            env = {gui.core.SETTINGS_ENV_VAR: str(settings_path)}
            with mock.patch.dict(os.environ, env), mock.patch.object(
                gui.core, "detect_steam_wf1_root", return_value=detected_root
            ):
                self.assertEqual("", gui.default_kr_root())
                self.assertEqual(str(detected_root), gui.default_tw_root())

    def test_gui_prefills_recent_valid_kr_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            kr_root = temp / "KR"
            settings_path = temp / "settings.json"
            write_kr_layout(kr_root)
            gui.core.remember_kr_root(kr_root, settings_path)
            with mock.patch.dict(os.environ, {gui.core.SETTINGS_ENV_VAR: str(settings_path)}):
                self.assertEqual(str(kr_root.resolve()), gui.default_kr_root())

    def test_gui_ignores_recent_invalid_kr_path(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            kr_root = temp / "KR"
            settings_path = temp / "settings.json"
            kr_root.mkdir()
            gui.core.remember_kr_root(kr_root, settings_path)
            with mock.patch.dict(os.environ, {gui.core.SETTINGS_ENV_VAR: str(settings_path)}):
                self.assertEqual("", gui.default_kr_root())

    def test_direct_win10_launch_uses_wfantasy_win10_exe(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            tw_root = temp / "Wind Fantasy"
            write_target_layout(tw_root)
            args = argparse.Namespace(
                kr_root=temp / "KR",
                tw_root=tw_root,
                dry_run=True,
                display_mode=None,
                width=None,
                height=None,
                no_apply=True,
            )

            report = core.launch_win10(args)

            self.assertEqual("WFantasy_win10.exe", Path(report["would_run"]).name)
            self.assertEqual("launch_win10", report["action"])
            self.assertTrue(report["directdraw_runtime"]["skipped"])

    def test_gui_maps_borderless_display_mode_to_core_argument(self) -> None:
        app = gui.PatchGui.__new__(gui.PatchGui)
        app.display_mode = mock.Mock()
        app.display_mode.get.return_value = gui.DISPLAY_BORDERLESS

        self.assertEqual("borderless", app._display_mode_arg())

    def test_gui_uses_selected_4_by_3_resolution_for_windowed_mode(self) -> None:
        app = gui.PatchGui.__new__(gui.PatchGui)
        app.display_mode = mock.Mock()
        app.display_mode.get.return_value = gui.DISPLAY_WINDOWED
        app.resolution_value = mock.Mock()
        app.resolution_value.get.return_value = "1024 x 768"
        app.resolution_presets = [(640, 480), (800, 600), (1024, 768)]

        self.assertEqual((1024, 768), app._resolution_args())

    def test_gui_ignores_resolution_for_borderless_mode(self) -> None:
        app = gui.PatchGui.__new__(gui.PatchGui)
        app.display_mode = mock.Mock()
        app.display_mode.get.return_value = gui.DISPLAY_BORDERLESS

        self.assertEqual((None, None), app._resolution_args())

    def test_gui_passes_click_lock_toggles_to_core_arguments(self) -> None:
        app = gui.PatchGui.__new__(gui.PatchGui)
        app.kr_path = mock.Mock()
        app.kr_path.get.return_value = r"C:\KR"
        app.tw_path = mock.Mock()
        app.tw_path.get.return_value = r"C:\TW"
        app.display_mode = mock.Mock()
        app.display_mode.get.return_value = gui.DISPLAY_UNCHANGED
        app.left_click_lock = mock.Mock()
        app.left_click_lock.get.return_value = True
        app.right_click_lock = mock.Mock()
        app.right_click_lock.get.return_value = False

        args = app._args()

        self.assertTrue(args.left_click_lock)
        self.assertFalse(args.right_click_lock)


if __name__ == "__main__":
    unittest.main()

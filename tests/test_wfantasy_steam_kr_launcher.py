from __future__ import annotations

import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from tooling import wfantasy_steam_kr_launcher as launcher


def write_pack(path: Path, entries: list[tuple[str, bytes]]) -> None:
    table_size = 4 + len(entries) * 17
    offset = table_size
    table = bytearray(struct.pack("<I", len(entries)))
    payload = bytearray()
    for name, data in entries:
        table.extend(struct.pack("<I", offset))
        table.extend(name.encode("ascii")[:13].ljust(13, b"\0"))
        payload.extend(data)
        offset += len(data)
    path.write_bytes(bytes(table + payload))


class LauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp())
        self.kr = self.temp / "KR"
        self.tw = self.temp / "TW"
        self.kr.mkdir()
        self.tw.mkdir()
        (self.tw / "WFantasy_win10.exe").write_bytes(b"exe")
        (self.tw / "WindConfig.exe").write_bytes(b"config")

    def tearDown(self) -> None:
        shutil.rmtree(self.temp)

    def write_source_and_target(self, name: str, source: bytes, target: bytes) -> None:
        (self.kr / name.upper()).write_bytes(source)
        (self.tw / name.lower()).write_bytes(target)

    def test_case_insensitive_source_lookup_and_target_preserve_existing_name(self) -> None:
        self.write_source_and_target("game.ini", b"kr", b"tw")

        src = launcher.find_case_insensitive(self.kr, "game.ini")
        dst = launcher.target_path(self.tw, "game.ini")

        self.assertEqual(src, self.kr / "GAME.INI")
        self.assertEqual(dst, self.tw / "game.ini")

    def test_pack_status_requires_same_entry_order(self) -> None:
        write_pack(self.kr / "STAGE", [("A.BIN", b"kr-a"), ("B.BIN", b"kr-b")])
        write_pack(self.tw / "stage", [("B.BIN", b"tw-b"), ("A.BIN", b"tw-a")])

        status = launcher.pack_status(self.kr, self.tw, "stage")

        self.assertTrue(status.parse_ok)
        self.assertFalse(status.same_entry_order)

    def test_copy_overlay_backs_up_once_and_restores(self) -> None:
        for name in launcher.KR_OVERLAY_FILES:
            self.write_source_and_target(name, f"kr-{name}".encode(), f"tw-{name}".encode())
        for name in launcher.COMPATIBILITY_CHECK_FILES:
            self.write_source_and_target(name, b"same", b"same")
        for name in [*launcher.KR_OVERLAY_FILES, *launcher.COMPATIBILITY_CHECK_FILES]:
            if name != "game.ini":
                write_pack(self.kr / name.upper(), [("A.BIN", b"kr")])
                write_pack(self.tw / name.lower(), [("A.BIN", b"tw" if name in launcher.KR_OVERLAY_FILES else b"kr")])

        args = type("Args", (), {"kr_root": self.kr, "tw_root": self.tw, "dry_run": False})()
        report = launcher.apply_patch(args)
        self.assertFalse(report["dry_run"])
        self.assertEqual((self.tw / "stage").read_bytes(), (self.kr / "STAGE").read_bytes())
        self.assertTrue((self.tw / launcher.BACKUP_DIR_NAME / "stage").exists())
        self.assertEqual((launcher.ddraw_payload_path()).read_bytes(), (self.tw / "ddraw.dll").read_bytes())
        self.assertIn("text_cp949=1", (self.tw / "wfantasy_ddraw.ini").read_text(encoding="ascii"))

        launcher.restore_patch(args)
        self.assertNotEqual((self.tw / "stage").read_bytes(), (self.kr / "STAGE").read_bytes())
        self.assertFalse((self.tw / "ddraw.dll").exists())
        self.assertFalse((self.tw / "wfantasy_ddraw.ini").exists())

    def test_windowed_runtime_config_is_4_by_3_and_cp949_enabled(self) -> None:
        config = launcher.normalize_display_config("windowed", 1280, 960)
        rendered = launcher.render_ddraw_config(config).decode("ascii")

        self.assertEqual("windowed", config["mode"])
        self.assertIn("[wfantasy_ddraw]", rendered)
        self.assertIn("width=1280", rendered)
        self.assertIn("height=960", rendered)
        self.assertIn("text_cp949=1", rendered)

    def test_directdraw_proxy_contains_cp949_text_hooks(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "tooling" / "runtime" / "ddraw_proxy.cpp").read_text(
            encoding="utf-8"
        )

        self.assertIn("Hook_TextOutA", source)
        self.assertIn("Hook_CreateFontA", source)
        self.assertIn("Hook_MultiByteToWideChar", source)
        self.assertIn("Hook_WideCharToMultiByte", source)
        self.assertIn("Hook_GetACP", source)
        self.assertIn("HANGEUL_CHARSET", source)
        self.assertIn("effective_text_code_page", source)


if __name__ == "__main__":
    unittest.main()

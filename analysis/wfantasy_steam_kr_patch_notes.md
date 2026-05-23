# Wind Fantasy 1 KR -> Steam Win10 static analysis notes

## Goal

한국어판 `Wind Fantasy` 데이터를 Steam Win10 실행 구조에 이식할 수 있는지
먼저 정적 분석으로 확인한다.

이번 단계에서는 Steam판 파일을 패치하거나 덮어쓰지 않는다. `Wind Fantasy SP`
작업과 같은 방식으로, 실행 파일은 Steam Win10 스택을 유지하고 한국어판 데이터
overlay 가능성만 타진한다.

## Paths

- Steam target: `C:\Program Files (x86)\Steam\steamapps\common\Wind Fantasy`
- Korean source: `C:\Users\early\Downloads\DGGL\Games\WFTact_Win95_230101\Store\WFantasy`
- Korean folder's TW reference copy:
  `C:\Users\early\Downloads\DGGL\Games\WFTact_Win95_230101\Store\WFantasy\WFANTASY_TW`

## Confirmed Facts

- Steam 실행 경로는 `WindConfig.exe -> WFantasy_win10.exe` 기준으로 본다.
- Steam root와 한국어판 내부 `WFANTASY_TW`는 핵심 파일 해시가 일치한다.
  따라서 `WFANTASY_TW`는 현재 Steam 설치본과 같은 TW 기준본으로 취급할 수 있다.
- `WindConfig.exe` 문자열/디컴파일/디스어셈블 결과:
  - `WFantasy_win10.exe` 문자열을 보유한다.
  - `CreateProcessW`로 대상 실행 파일을 실행한다.
  - `HKCU\WFantasy` 아래 `IsFullscreen`, `CreationHeight`,
    `CreationWidth` 값을 읽고 쓴다.
  - `__COMPAT_LAYER`를 `WINXPSP3` 또는 `WINXPSP3 16BITCOLOR`로 설정한다.
- `WFantasy_win10.exe`는 PE x86 32-bit이며 다음 API를 직접 import한다.
  - `DDRAW.dll!DirectDrawCreate`
  - `WINMM.dll!mciSendStringA`
  - `GDI32.dll!TextOutA`
  - `KERNEL32.dll!MultiByteToWideChar`, `WideCharToMultiByte`, `GetACP`
  - `USER32.dll!CreateWindowExA`, `SetCursorPos`
- `WFantasy_win10.exe`와 `WindConfig.exe`에서 Steam API 또는 appid 의존 문자열은
  확인되지 않았다. `api-ms-win-crt-*` DLL 이름은 CRT runtime import이다.
- SP의 `wind.dll` CP936 -> CP949 패치 구조와 달리, 1편 Steam 폴더에는 별도
  `wind.dll` locale shim이 없다.
- `WFantasy_win10.exe` 안에는 리소스 archive 이름이 그대로 있다:
  `game.ini`, `bmp`, `face`, `manbmp`, `manani`, `man`, `stage`,
  `mapbmp`, `map`, `Wave`.
- 1편 한국어판의 기존 텍스트 추출 도구는 완전하지 않으므로 이 보고서의
  이식 가능성 판단 근거로 사용하지 않는다.

## File Comparison

Short hash values are the first 16 hex characters of SHA-256.

| File | Steam size/hash16 | KR size/hash16 | Initial role |
| --- | ---: | ---: | --- |
| `WFantasy_win10.exe` | 559360 / `AF490C8841FC47F7` | missing | keep Steam |
| `WindConfig.exe` | 27648 / `6B6F907BF7044847` | missing | keep Steam |
| `WFantasy.exe` | 559360 / `4328746943DE7DD9` | 398848 / `5D69F45A221D5FFA` | do not replace |
| `game.ini` | 72 / `54258E0C8F98861D` | 69 / `2FDAD67E16846215` | overlay candidate |
| `bmp` | 15938743 / `6021411690934CB4` | 15841889 / `22F71039DE230991` | overlay candidate |
| `face` | 3877553 / `E96FEDC0FF3FE659` | same | compatibility check only |
| `man` | 91739 / `2B6918DB57CAF1EB` | 85809 / `B4071DE0E20D9CCE` | overlay candidate |
| `manani` | 927352 / `05D8619E2BE53438` | same | compatibility check only |
| `manbmp` | 31707202 / `80EE08BEF733A4D5` | same | compatibility check only |
| `map` | 34638 / `1446D3AB6B0535F5` | same | compatibility check only |
| `mapbmp` | 23258953 / `2B2F8B086E07D1DE` | same | compatibility check only |
| `stage` | 206918 / `F819454FBF172D41` | 188926 / `91EF04AFDB8E0659` | overlay candidate |
| `Wave` | 9441225 / `793ED4436337EACB` | same | compatibility check only |

## Archive Structure Check

The extensionless resource files use a common pack shape:

- `uint32 count`
- repeated 17-byte entries: `uint32 offset` + 13-byte null-padded name
- payload entries follow in table order

Steam and Korean files parse cleanly with this structure.

| Archive | Steam entries | KR entries | Same entry order | Entry hash differences |
| --- | ---: | ---: | ---: | ---: |
| `bmp` | 181 | 181 | 181 | 76 |
| `face` | 197 | 197 | 197 | 0 |
| `man` | 319 | 319 | 319 | 44 |
| `manani` | 2393 | 2393 | 2393 | 0 |
| `manbmp` | 5607 | 5607 | 5607 | 0 |
| `map` | 78 | 78 | 78 | 0 |
| `mapbmp` | 596 | 596 | 596 | 0 |
| `stage` | 197 | 197 | 197 | 128 |
| `Wave` | 185 | 185 | 185 | 0 |

This is the strongest positive signal so far. The Korean and Steam/TW archives
keep the same entry names and order, so a file-level overlay for the differing
archives is structurally plausible.

## Ghidra / Disassembly Evidence

Ghidra headless analysis outputs were generated under `analysis/ghidra/`.
Those raw outputs are intentionally git-ignored.

Analyzed binaries:

- `steam_wfantasy_win10/WFantasy_win10.exe`
  - PE x86 32-bit
  - Ghidra summary: 5 functions, 280 strings
  - Import/string evidence confirms direct DirectDraw, GDI ANSI text, MCI audio,
    and archive-name usage.
- `steam_windconfig/WindConfig.exe`
  - PE x86 32-bit
  - Ghidra summary: 132 functions, 171 strings
  - `FUN_00402730` builds a command line, sets `__COMPAT_LAYER`, calls
    `GetEnvironmentStringsW`, then calls `CreateProcessW`.
  - `.rdata` contains both `WFantasy.exe` and `WFantasy_win10.exe`.
- `kr_wfantasy/WFantasy.exe`
  - PE x86 32-bit
  - Ghidra summary: 944 functions, 356 strings
  - Used only as a reference for original loader strings and resource names.

Representative `WindConfig.exe` disassembly around launch path:

```text
004027cd  push 0x405b94              ; "WINXPSP3 16BITCOLOR"
004027d9  push 0x405bbc              ; "__COMPAT_LAYER"
004027de  call SetEnvironmentVariableW
004027e4  call GetEnvironmentStringsW
00402811  call CreateProcessW
```

## Preliminary Porting Model

Likely first overlay candidate, mirroring the SP workflow:

- keep Steam `WindConfig.exe`
- keep Steam `WFantasy_win10.exe`
- do not copy Korean `WFantasy.exe`
- copy or generate patched versions of:
  - `game.ini`
  - `bmp`
  - `man`
  - `stage`
- only verify, not copy, the same-hash files:
  - `face`
  - `manani`
  - `manbmp`
  - `map`
  - `mapbmp`
  - `Wave`

## Strong Hypotheses

- The main data overlay is feasible at the archive-container level because the
  differing Korean archives retain the same entry counts, names, and order as
  Steam/TW.
- Steam `WFantasy_win10.exe` likely retains the original 1편 loader's archive
  naming and pack access conventions, despite being a different executable
  package.
- No SP-style `wind.dll` CP936 shim patch is required for 1편, because text
  rendering and codepage APIs are imported directly by `WFantasy_win10.exe`.

## Unknowns / Risks

- File-level overlay may still fail if Steam `WFantasy_win10.exe` expects
  TW-specific payload sizes, record values, or patched progression data inside
  `bmp`, `man`, or `stage`.
- Korean text rendering depends on the runtime ANSI codepage path. The current
  static evidence shows `TextOutA`, `GetACP`, `MultiByteToWideChar`, and
  `WideCharToMultiByte`, but does not prove the game will render CP949 correctly
  on every Windows locale.
- `game.ini` differs. Its Korean release values are English-looking CD prompts,
  while Steam/TW values are non-ASCII when viewed through the current console.
  It should be tested as an overlay candidate, not blindly assumed required.
- No runtime launch test or clean-restore apply test has been performed in this
  phase.

## SP Comparison / Verified Structural Differences

Reference points:

- SP work repo:
  `C:\Users\early\Downloads\DGGL\Games\WFTSP_Win`
- SP Steam target:
  `C:\Program Files (x86)\Steam\steamapps\common\Wind Fantasy SP`
- SP notes:
  `C:\Users\early\Downloads\DGGL\Games\WFTSP_Win\analysis\wftsp_steam_kr_patch_notes.md`
- SP launcher:
  `C:\Users\early\Downloads\DGGL\Games\WFTSP_Win\tooling\wftsp_steam_kr_launcher.py`

### 1. Win10 executable dependency model is different

Confirmed with `objdump -p`.

| Target | Imported DLLs |
| --- | --- |
| WF1 `WFantasy_win10.exe` | `DDRAW.dll`, `DSOUND.dll`, `WINMM.dll`, `KERNEL32.dll`, `USER32.dll`, `GDI32.dll` |
| SP `wf_sp_win10.exe` | `wind.dll` only |

SP's Win10 executable delegates through `wind.dll`. That DLL then imports:

- `KERNEL32.dll!GetACP`
- `KERNEL32.dll!MultiByteToWideChar`
- `KERNEL32.dll!WideCharToMultiByte`
- `GDI32.dll!TextOutA`
- `GDI32.dll!TextOutW`

WF1 does not have a `wind.dll` shim in the Steam folder. WF1 imports
`TextOutA`, `GetACP`, `MultiByteToWideChar`, `WideCharToMultiByte`,
`DirectDrawCreate`, and `SetCursorPos` directly from system DLLs.

Impact:

- SP's `wind.dll` CP936 -> CP949 patch cannot be ported directly to WF1.
- WF1 locale/text-output work, if needed, must target `WFantasy_win10.exe`
  itself or a different local shim/proxy strategy.
- WF1 DirectDraw/display work, if needed later, should be evaluated as a
  separate `ddraw.dll` proxy problem rather than as part of the data overlay.

### 2. Locale patch surface is different

SP launcher has hardcoded `wind.dll` patch offsets:

- `0x0410`
- `0x044B`
- `0x0490`
- `0x04DB`
- `0x0543`
- `0x058E`
- `0x0534` for the `TextOutA` length preservation patch

Those offsets are meaningful only in SP's `wind.dll`. WF1 has no corresponding
file. A blind port of those constants would be invalid.

Observed SP states:

- `WFTSP_Win\Wind Fantasy SP_TW\wind.dll` has CP949 bytes (`B5 03 00 00`) at
  the six codepage offsets.
- The current Steam SP folder observed during this check still has original
  CP936 bytes (`A8 03 00 00`) at those offsets, so the SP work repo/tooling is
  the better reference for intended patch logic than the live SP Steam folder
  alone.

### 3. WindConfig is same family, but not identical

Both WF1 and SP `WindConfig.exe` import the same launcher-side APIs:

- `CreateProcessW`
- `SetEnvironmentVariableW`
- `RegOpenKeyExW`
- `RegQueryValueExW`
- `RegSetValueExW`
- `EnumDisplaySettingsW`
- `ChangeDisplaySettingsW`

They are not byte-identical:

| Target | Size | SHA-256 hash16 |
| --- | ---: | --- |
| WF1 `WindConfig.exe` | 27648 | `6B6F907BF7044847` |
| SP `WindConfig.exe` | 39160 | `7B5F4F28D162DCAF` |

Verified registry-key string difference:

- WF1 `WindConfig.exe` contains ASCII key string `WFantasy`.
- SP `WindConfig.exe` contains ASCII key string `WindSP`.
- Current registry state also has `HKCU\WindSP`, while `HKCU\WFantasy` was not
  present during this check.

Impact:

- WF1 status tooling should read/write/report `HKCU\WFantasy`, not `HKCU\WindSP`.
- SP launcher code's `WINDSP_REGISTRY_KEY = "WindSP"` must not be reused
  unchanged.

### 4. Data overlay list is smaller for WF1

SP launcher overlay list:

- `game.ini`
- `setup.ini`
- `bmp`
- `manbmp`
- `manani`
- `man`
- `stage`

SP compatibility-check-only list:

- `map`
- `face`
- `mapbmp`
- `Wave`

WF1 does not have `setup.ini`, and WF1 Korean/source files show identical hashes
for more resource archives.

WF1 likely overlay list:

- `game.ini`
- `bmp`
- `man`
- `stage`

WF1 compatibility-check-only list:

- `face`
- `manani`
- `manbmp`
- `map`
- `mapbmp`
- `Wave`

Impact:

- Reusing SP's overlay list unchanged would copy unnecessary WF1 files.
- `manani` and `manbmp` were real SP overlay files but are identical between
  WF1 Korean and Steam/TW, so they should initially be checked, not copied.

### 5. WF1 archive structure is more regular than SP

Using the common 17-byte table parser:

| Game | Archive | Base entries | KR entries | Same order | Hash-different entries |
| --- | --- | ---: | ---: | ---: | ---: |
| WF1 | `bmp` | 181 | 181 | 181 | 76 |
| WF1 | `man` | 319 | 319 | 319 | 44 |
| WF1 | `stage` | 197 | 197 | 197 | 128 |
| SP | `bmp` | 263 | 263 | 263 | 85 |
| SP | `man` | 450 | 449 | 0 | n/a |
| SP | `manbmp` | 11444 | 11443 | 0 | n/a |
| SP | `stage` | 403 | 389 | 0 | n/a |

The SP numbers above compare the SP original backup files against the repaired
SP Korean work files. SP still needed file-specific repair logic for `stage` and
`man`. WF1's main differing archives currently keep matching entry counts and
order, which makes first-pass file-level overlay safer than it was for SP.

Impact:

- WF1 can start with a simpler dry-run overlay verifier.
- WF1 should still hash and parse archives before apply, but may not need
  SP-style decoded-entry repair logic in the first implementation pass.

### 6. Runtime add-ons differ

SP tooling installs runtime support files:

- `ddraw.dll`
- `wftsp_ddraw.ini`

WF1 now has a separate runtime pair:

- `payload/ddraw.dll`
- `wfantasy_ddraw.ini`

Impact:

- Do not copy SP `wftsp_ddraw.ini` into WF1.
- Keep WF1 runtime config/log names separate from SP:
  `wfantasy_ddraw.ini` and `wfantasy_ddraw.log`.
- The runtime keeps the DirectDraw scaling/offscreen RGB565 fix and adds WF1
  text hooks for CP949.

## Runtime Smoke Verification

Checked on 2026-05-22 against a clean smoke root:

`C:\Users\early\AppData\Local\Temp\wf1-kr-smoke-20260522-091229`

The first exclusive/fullscreen smoke capture with `RunAsInvoker WINXPSP3
16BITCOLOR` showed purple-tinted output and unreadable menu text. Restoring the
smoke root to TW original and capturing under the same condition produced the
same kind of purple/text distortion, so that failure is not evidence that the KR
overlay data is corrupt.

SP history check:

- Reference commit:
  `d266e439444e1c88b786331e7e7da7955445c0ab`
  (`DirectDraw 창모드 표면 포맷 보정`)
- The SP fix forces non-primary 640x480 offscreen DirectDraw surfaces to RGB565
  16bpp in scaled modes.
- The underlying issue was a mismatch between a desktop-format offscreen surface
  and game code that locks the surface and writes `ushort` pixels directly.

Smoke-only WF1 canary:

- Copied the fixed SP `payload/ddraw.dll` into the smoke root only.
- Added a temporary `wftsp_ddraw.ini` in the smoke root with
  `mode=windowed`, `width=1280`, and `height=960`.
- TW original title rendered with normal colors in the windowed proxy path.
- After applying the WF1 KR overlay (`game.ini`, `bmp`, `man`, `stage`), the
  title resource changed to `WIND FANTASY TACTICS` and rendered with normal
  colors.
- Menu/save-slot navigation reached an in-game UI screen. This earlier borrowed
  SP proxy smoke proved the screen path, but the visible slot text was still
  decoded as Chinese-codepage glyphs, not correct Korean.

Interpretation:

- Confirmed fact: the four-file KR overlay can be loaded by the Steam
  `WFantasy_win10.exe` stack in a smoke root.
- Confirmed fact: the exclusive/fullscreen screenshot artifact reproduces with
  TW original data, so it is not KR-data-specific.
- Strong hypothesis: WF1 has the same DirectDraw 16bpp/offscreen-surface
  sensitivity as SP when a windowed proxy is used.
- Resolved follow-up: the borrowed SP proxy was split into WF1-named runtime
  files and extended with CP949 text hooks.

## CP949 Text Runtime

Implemented after the smoke test showed CP949 bytes being interpreted as a
Chinese codepage in the save/load slot UI.

Runtime behavior:

- Local `ddraw.dll` is loaded by the Steam `WFantasy_win10.exe` import table.
- The proxy patches the main executable imports for:
  - `GDI32!TextOutA`
  - `GDI32!CreateFontA`
  - `KERNEL32!MultiByteToWideChar`
  - `KERNEL32!WideCharToMultiByte`
  - `KERNEL32!GetACP`
- `TextOutA` calls are converted from CP949 bytes to Unicode and then rendered
  through `TextOutW`, preserving the caller's `nCount`.
- `CreateFontA` is hooked for diagnostics and optional override, but the
  default runtime path now preserves the game's original font charset and
  face name. Static/dynamic checks show the Steam path creates the same font
  family pattern as the Korean executable reference: `height=16..54`,
  `charset=136`, `quality=3`, `pitch=2`, and `face=NULL`.
- Optional font overrides are available through `font_charset=hangul` and
  `font_face=...` if a later environment needs them.
- ACP, CP936, and CP950 conversion requests are mapped to CP949 while
  `text_cp949=1`.

Runtime files:

- `payload/ddraw.dll`
- target `ddraw.dll`
- target `wfantasy_ddraw.ini`

Default generated config:

```ini
[wfantasy_ddraw]
mode=fullscreen
width=640
height=480
debug=0
input_fix=1
audio_focus_fix=1
inactive_window_spoof=1
text_cp949=1
font_charset=preserve
font_face=
```

Windowed smoke verification:

- Fresh smoke root:
  `C:\Users\early\AppData\Local\Temp\wf1-cp949-smoke-20260522-102744`
- Applied with:
  `--display-mode windowed --width 1280 --height 960`
- Built payload SHA-256:
  `68586A39FD4E4F87D7C3CF67A6B687888A4A114505845EA117C061B69ECE7642`
- Visual result:
  save/load slot text that previously appeared as Chinese glyphs now renders as
  Korean, including repeated `빈 / 공 / 간` slot labels.

Font-size follow-up:

- The first CP949 runtime forced `HANGEUL_CHARSET` and could fall back to
  `Gulim`, which made the visible text feel slightly larger than expected.
- A follow-up comparison checked the Korean executable's `CreateFontA` callsite
  and the Steam runtime calls. Both use `charset=136`, `quality=3`, `pitch=2`,
  and `face=NULL` for the generated font sizes.
- The proxy now defaults to preserving those font parameters while still
  converting CP949 text through `TextOutW`.
- Smoke root and live Steam root both rendered Korean text with
  `font_charset=preserve`.

Real Steam folder state after this check:

- no root `ddraw.dll`
- no root `wfantasy_ddraw.ini`
- no `_wfantasy_kr_patch_backup`
- no running WF1 processes

## Live Steam Apply Verification

Applied to the real Steam folder on 2026-05-22:

`C:\Program Files (x86)\Steam\steamapps\common\Wind Fantasy`

Command:

```powershell
python tooling\wfantasy_steam_kr_launcher.py apply --display-mode windowed --width 1280 --height 960
```

Post-apply state:

- `game.ini`, `bmp`, `man`, and `stage` match the KR source hashes.
- Compatibility-check files still match between KR and Steam/TW:
  `face`, `manani`, `manbmp`, `map`, `mapbmp`, and `Wave`.
- All checked archive tables still parse and keep the same entry order.
- Root `ddraw.dll` matches `payload/ddraw.dll`.
- `wfantasy_ddraw.ini` has `mode=windowed`, `width=1280`, `height=960`, and
  `text_cp949=1`.
- Original Steam/TW overlay files were backed up under
  `_wfantasy_kr_patch_backup`.

Visual smoke results from the real Steam folder:

- `analysis\wf1_live_cp949_save_slots_windowed.png`
  - save/load slot text renders as Korean, including `빈 / 공 / 간`.
- `analysis\wf1_live_cp949_new_game_windowed.png`
  - new-game dialogue renders Korean text:
    `너.... 다시 한번 말해봐!!`
- `analysis\wf1_live_preserve_charset_windowed.png`
  - live runtime with preserved font charset/face renders Korean dialogue text.

After capture, the live game process was stopped. The real Steam folder remains
patched so the user can launch and continue manual play testing.

## GUI Launcher and Package

The patch flow now has a standalone Tk GUI launcher matching the SP launcher
shape:

- `tooling/wfantasy_steam_kr_patch_gui.py` provides the GUI.
- `WF1_KR_Steam_Patch_GUI.exe` is the root standalone build.
- `WF1_KR_Steam_Patch_GUI.cmd` is a convenience wrapper.
- `WF1_KR_Steam_Patch_GUI.spec` is the PyInstaller build recipe.
- `assets/launcher_art.png` is bundled into the frozen executable.
- `dist\WF1_KR_Steam_Patch\` is the local package folder.
- `dist\WF1_KR_Steam_Patch.zip` is the local distributable zip.

Launcher behavior:

- Korean source path starts blank and must be selected by the user.
- Steam/TW path is auto-detected from Steam registry/libraryfolders when
  possible.
- `패치 적용`, `상태 확인`, `TW 원본 복구`, `게임 실행`, and `WindConfig 실행`
  are available from the first screen.
- `게임 실행` starts `WFantasy_win10.exe` directly.
- `WindConfig 실행` starts `WindConfig.exe`.
- Display options are `건드리지 않음`, `창모드`, `전체 창 모드`, and
  `전체화면`.

Verification after packaging:

- `python -m py_compile tooling\wfantasy_steam_kr_launcher.py tooling\wfantasy_steam_kr_patch_gui.py tooling\build_ddraw_proxy.py`
- `python -m unittest discover -s tests`
- `python -m PyInstaller --noconfirm --clean WF1_KR_Steam_Patch_GUI.spec`
- root `WF1_KR_Steam_Patch_GUI.exe --self-test`
- package folder `dist\WF1_KR_Steam_Patch\WF1_KR_Steam_Patch_GUI.exe --self-test`
- clean-temp zip extraction self-test
- live restore/apply smoke:
  - `restore` restored four Steam/TW overlay files.
  - `restore` removed launcher-created `ddraw.dll` and `wfantasy_ddraw.ini`.
  - `apply --display-mode windowed --width 1280 --height 960` reapplied four
    KR overlay files and the runtime payload.
  - final root `ddraw.dll` SHA-256 matches `payload\ddraw.dll`:
    `E328371C3CC695FBDC6EC3B4C869CD00B9EF6672B65A8F585F130FF759B69B0B`.
  - final `wfantasy_ddraw.ini` uses `mode=windowed`, `width=1280`,
    `height=960`, `text_cp949=1`, `font_charset=preserve`, and blank
    `font_face`.

The real Steam folder remains patched with the package payload so the user can
continue manual play testing.

## Right-Click Drag Input Tweak

Reported on 2026-05-23:

- Holding right click and dragging in windowed/scaled mode repeatedly toggled
  the in-game menu.

Root-cause hypothesis:

- Windows attaches `MK_RBUTTON` to every `WM_MOUSEMOVE` while the right button
  is held.
- The proxy already rewrites mouse move coordinates for scaled window modes and
  previously forwarded `wParam` unchanged.
- If the game treats `MK_RBUTTON` on mouse move as another right-click command,
  dragging becomes repeated menu input.

Fix:

- Keep `WM_RBUTTONDOWN` and `WM_RBUTTONUP` unchanged.
- For scaled-mode `WM_MOUSEMOVE`, clear only the `MK_RBUTTON` state bit before
  forwarding to the original game WndProc.
- This keeps right-click as an edge event while avoiding repeated menu toggles
  during right-button drag.

## Next Safe Step

The next meaningful check is user-visible manual play testing through the new
GUI launcher, especially `게임 실행` and `WindConfig 실행` from the packaged
zip. Any further runtime changes should stay in small one-variable experiments
so visual/font differences remain attributable.

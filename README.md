# Wind Fantasy KR Steam Patch Launcher

`Wind Fantasy` 한국어판 데이터를 Steam 대만판 Windows 10 대응 클라이언트 위에 적용하는 패치 런처입니다.

이 저장소와 배포 패키지는 게임 리소스 파일을 직접 포함하지 않습니다. 패치를 적용하려면 사용자가 보유한 기존 한국어판 정식 발매본 폴더가 필요합니다.

이 도구는 Team-JHF가 작성/관리하는 비공식 패치 런처입니다. 이 표기는 런처와 패치 보조 코드에 대한 표시이며, 원본 게임에 대한 권리 주장이나 사용 허가를 의미하지 않습니다. 원본 게임의 명칭, 실행 파일, 데이터, 이미지, 음악 등 모든 게임 리소스의 권리는 각 원 권리자에게 있습니다.

## 주요 기능

- Steam 설치 정보를 읽어 `Wind Fantasy` Steam판 경로 자동 탐지
- 한국어판 폴더와 Steam 대만판 폴더를 GUI에서 직접 선택
- 한국어판 데이터 파일을 Steam 대만판 Win10 클라이언트에 적용
- Steam Win10판의 ANSI/CP949 텍스트 출력을 DirectDraw 프록시에서 보정
- KR 실행파일 기준에 맞춰 기본 폰트 charset/face를 보존
- Steam 대만판 원본 파일 자동 백업 및 복구
- `WFantasy_win10.exe` 직접 실행 버튼 제공
- 창모드/전체 창 모드(borderless) 및 해상도 설정을 DirectDraw 프록시로 반영
- 선택적으로 `WindConfig.exe` 실행

## 다운로드/실행

배포용 실행 파일:

```text
WF1_KR_Steam_Patch_GUI.exe
```

이 실행 파일은 Python/Tk 런타임을 포함한 standalone 빌드입니다. 사용자 PC에 Python을 따로 설치할 필요가 없습니다.

## 사용 방법

1. `WF1_KR_Steam_Patch_GUI.exe`를 실행합니다.
2. `한국어판 폴더`는 빈 값으로 시작합니다. 사용자가 보유한 Wind Fantasy 한국어판 폴더를 직접 선택합니다.
3. `Steam 대만판 폴더`는 Steam 설치 정보에서 자동으로 채워집니다. 자동 탐지에 실패하면 Steam의 `Wind Fantasy` 폴더를 직접 선택합니다.
4. `패치 적용`을 누릅니다.
5. 패치 후 `게임 실행`을 누르면 `WindConfig.exe`를 거치지 않고 `WFantasy_win10.exe`가 직접 실행됩니다.
6. 설정 프로그램이 필요하면 `WindConfig 실행`을 사용합니다.

패치 적용 전에는 게임과 `WindConfig.exe`를 종료하세요.

## 화면 설정

Steam Win10 실행 파일은 DirectDraw 기반 640x480 렌더링을 사용합니다. 런처의 화면 모드와 해상도 입력값은 대상 Steam 폴더에 다음 런타임 파일을 설치하는 방식으로 반영합니다.

- `ddraw.dll`: 32비트 DirectDraw/CP949 텍스트 프록시
- `wfantasy_ddraw.ini`: `windowed`, `borderless`, `fullscreen` 모드와 출력 크기 설정

지원 상태:

- `창모드`: 현재 모니터 해상도 이하의 4:3 프리셋 창 크기로 스케일링합니다.
- `전체 창 모드`: 현재 모니터 크기에 맞춘 borderless 창으로 전환하고, 게임 화면은 중앙 4:3 영역에 출력합니다. 남는 좌우 영역은 pillarbox로 비워 둡니다.
- `전체화면`: 프록시는 로드되지만 원본 DirectDraw 전체화면 경로를 그대로 통과시킵니다.

창모드/전체 창 모드에서는 원본 게임의 640x480 좌표계를 유지하기 위해 렌더링과 입력 기준을 항상 중앙 4:3 게임 영역으로 제한합니다. `SetCursorPos`/`ClipCursor`는 실제 창 좌표로 확장하고, WndProc 마우스 입력은 640x480 논리 좌표로 되돌립니다. 창모드에서는 원본의 전체 화면 커서 제한을 해제해 타이틀바 이동과 닫기 버튼 접근이 가능하도록 합니다.

WF1 한국어 데이터의 CP949 텍스트는 Steam Win10 실행 파일이 직접 import하는 `TextOutA`, `MultiByteToWideChar`, `WideCharToMultiByte`, `GetACP` 경로에서 보정합니다. 기본 설정은 KR 실행파일의 폰트 호출 패턴과 맞추기 위해 `font_charset=preserve`, `font_face=`를 사용합니다.

이 기능은 기존 게임 리소스를 포함하지 않는 런타임 보조 DLL 방식입니다. 문제가 있으면 GUI의 `TW 원본 복구`로 런처가 만든 `ddraw.dll`/`wfantasy_ddraw.ini`도 제거됩니다. 수동으로 끄고 싶을 때는 `wfantasy_ddraw.ini`의 `input_fix=0`, `audio_focus_fix=0`, `inactive_window_spoof=0`, `text_cp949=0`을 사용할 수 있습니다.

## 원본 보존

한국어판 폴더는 읽기 전용 소스로만 사용하며 수정하지 않습니다.

Steam 대만판 폴더의 기존 파일은 패치 적용 전에 다음 위치로 백업합니다.

```text
<Steam 대만판 폴더>\_wfantasy_kr_patch_backup
```

문제가 생기면 GUI의 `TW 원본 복구` 버튼으로 백업된 원본을 되돌릴 수 있습니다.

## 적용 파일

한국어판에서 읽어 Steam 대만판에 적용하는 파일:

- `game.ini`
- `bmp`
- `man`
- `stage`

다음 파일은 한국어판과 Steam 대만판이 동일한 규격/해시인지 확인만 하고 복사하지 않습니다.

- `face`
- `manani`
- `manbmp`
- `map`
- `mapbmp`
- `Wave`

## Windows 11 보안 안내

Windows 보안 또는 백신이 런처 실행을 막으면, 패치를 적용하는 동안만 차단을 해제한 뒤 다시 원래 설정으로 되돌리세요.

패치가 끝난 뒤 게임은 Steam판 `WFantasy_win10.exe`를 직접 실행합니다.

## 개발자용 명령

상태 확인:

```powershell
python tooling\wfantasy_steam_kr_launcher.py status --kr-root <KR폴더> --tw-root <TW폴더>
```

패치 적용:

```powershell
python tooling\wfantasy_steam_kr_launcher.py apply --kr-root <KR폴더> --tw-root <TW폴더>
```

Win10 실행 파일 직접 실행:

```powershell
python tooling\wfantasy_steam_kr_launcher.py launch-win10 --no-apply --tw-root <TW폴더>
```

해상도 지정 후 실행:

```powershell
python tooling\wfantasy_steam_kr_launcher.py launch-win10 --no-apply --tw-root <TW폴더> --display-mode windowed --width 1024 --height 768
```

전체 창 모드 실행:

```powershell
python tooling\wfantasy_steam_kr_launcher.py launch-win10 --no-apply --tw-root <TW폴더> --display-mode borderless
```

원본 복구:

```powershell
python tooling\wfantasy_steam_kr_launcher.py restore --tw-root <TW폴더>
```

standalone exe 빌드:

```powershell
python tooling\build_ddraw_proxy.py
python -m PyInstaller --noconfirm --clean WF1_KR_Steam_Patch_GUI.spec
```

빌드 결과는 `dist\WF1_KR_Steam_Patch_GUI.exe`에 생성됩니다. 배포 패키지에는 exe와 함께 `payload\ddraw.dll`, `README_WF1_KR_STEAM_PATCH.txt`, `THIRD_PARTY_NOTICES.txt`도 포함되어야 합니다.

## 포함 파일

- `WF1_KR_Steam_Patch_GUI.exe`: 배포용 standalone GUI 런처
- `WF1_KR_Steam_Patch_GUI.cmd`: exe 실행 편의 래퍼
- `tooling/wfantasy_steam_kr_patch_gui.py`: GUI 코드
- `tooling/wfantasy_steam_kr_launcher.py`: 패치 적용/복구/실행 핵심 로직
- `tooling/runtime/ddraw_proxy.cpp`: 창모드/전체 창 모드/CP949 출력용 DirectDraw 프록시
- `tooling/build_ddraw_proxy.py`: `payload/ddraw.dll` 빌드 스크립트
- `payload/ddraw.dll`: 런처가 Steam판 폴더에 복사하는 DirectDraw 프록시
- `analysis/wfantasy_steam_kr_patch_notes.md`: 분석 메모
- `THIRD_PARTY_NOTICES.txt`: standalone 빌드에 포함될 수 있는 제3자 구성 요소 및 빌드 도구 라이선스 고지

## 권리 및 라이선스 고지

이 런처와 패치 보조 코드는 Team-JHF가 작성/관리하는 비공식 도구입니다. 이 도구의 배포는 원본 게임에 대한 권리 주장, 사용 허가, 공식 지원 또는 원 권리자와의 제휴를 의미하지 않습니다.

`Wind Fantasy`, 원본 실행 파일, 원본 데이터, 이미지, 음악, 상표 및 관련 저작물은 각 원 권리자의 자산입니다. 본 도구는 원본 게임 파일을 대체하거나 원본 저작물을 재배포하기 위한 목적으로 제공되지 않습니다.

standalone 실행 파일은 PyInstaller로 빌드되며, 빌드 환경 및 포함된 기능에 따라 제3자 런타임 구성 요소를 포함할 수 있습니다. 배포물에 실제 포함될 수 있는 런타임 구성 요소와 소스 빌드 도구 라이선스 고지는 `THIRD_PARTY_NOTICES.txt`에 구분해 정리합니다.

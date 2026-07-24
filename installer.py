#!/usr/bin/env python3
"""Build NSIS installer for ZeroKeys. Auto-downloads NSIS if missing."""

import sys, os, subprocess, shutil, urllib.request, tempfile, zipfile, time
from pathlib import Path

DIST = Path(__file__).parent / 'dist'
EXE = DIST / 'ZeroKeys.exe'
NSIS_URL = 'https://sourceforge.net/projects/nsis/files/NSIS%203/3.10/nsis-3.10-setup.exe/download'
NSIS_ZIP_URL = 'https://sourceforge.net/projects/nsis/files/NSIS%203/3.10/nsis-3.10.zip/download'
NSIS_DIRS = [
    Path(os.environ.get('PROGRAMFILES', 'C:\\Program Files')) / 'NSIS',
    Path(os.environ.get('PROGRAMFILES(X86)', 'C:\\Program Files (x86)')) / 'NSIS',
]


def find_makensis():
    for p in os.environ.get('PATH', '').split(';'):
        mp = Path(p) / 'makensis.exe'
        if mp.exists():
            return mp
    for d in NSIS_DIRS:
        mp = d / 'makensis.exe'
        if mp.exists():
            return mp
    return None


def _dl_curl(url, out):
    subprocess.run(['curl.exe', '-L', '-s', '-o', str(out), url], check=True, timeout=120)

def download_nsis():
    print('Downloading NSIS...')
    tmp = Path(tempfile.gettempdir()) / 'nsis-setup.exe'
    try:
        _dl_curl(NSIS_URL, tmp)
    except: pass
    if tmp.exists() and tmp.stat().st_size > 1_000_000:
        print('Done.')
        return tmp
    print('Setup download failed, trying portable zip...')
    return None


NSIS_ZIP_DIR = Path(tempfile.gettempdir()) / 'nsis-portable'

def download_and_extract_zip():
    print('Downloading NSIS portable zip...')
    tmp = Path(tempfile.gettempdir()) / 'nsis.zip'
    try:
        _dl_curl(NSIS_ZIP_URL, tmp)
    except: pass
    if not tmp.exists() or tmp.stat().st_size < 1_000_000:
        print('Download failed.')
        return None
    print('Downloaded, extracting...')
    if NSIS_ZIP_DIR.exists():
        import shutil
        shutil.rmtree(NSIS_ZIP_DIR)
    with zipfile.ZipFile(tmp, 'r') as z:
        z.extractall(NSIS_ZIP_DIR)
    tmp.unlink(missing_ok=True)
    makensis = NSIS_ZIP_DIR / 'NSIS' / 'makensis.exe'
    if makensis.exists():
        os.environ['PATH'] = str(makensis.parent) + os.pathsep + os.environ.get('PATH', '')
        print(f'Extracted to {makensis.parent}')
        return makensis
    return None

def check_nsis():
    makensis = find_makensis()
    if makensis:
        return makensis

    print()
    print('*' * 58)
    print('  NSIS (Nullsoft Scriptable Install System) is required')
    print('  to build the installer.')
    print()
    print('  Download: https://nsis.sourceforge.io/Download')
    print('*' * 58)
    print()

    resp = input('Install NSIS automatically? (Y/N): ').strip().lower()
    if resp != 'y':
        print('Install NSIS manually, then re-run installer.py')
        sys.exit(1)

    setup = download_nsis()
    if setup and setup.exists():
        print(f'Running NSIS installer...')
        try:
            subprocess.run([str(setup), '/S'], check=True, timeout=120)
            setup.unlink(missing_ok=True)
            makensis = find_makensis()
        except Exception as e:
            print(f'Installer failed: {e}')
            setup.unlink(missing_ok=True)
            makensis = None

    if not makensis:
        print('Trying portable zip...')
        makensis = download_and_extract_zip()

    if not makensis:
        print('Failed to install NSIS.')
        print('Install manually from: https://nsis.sourceforge.io/Download')
        sys.exit(1)

    print(f'NSIS found at: {makensis}')
    return makensis


def build_installer(makensis):
    if not EXE.exists():
        print(f'Error: {EXE} not found. Run build.bat first.')
        sys.exit(1)

    outfile = str(DIST / 'ZeroKeys_Setup.exe')
    exe_path = str(EXE)

    o = outfile.replace('\\', '\\\\')
    e = exe_path.replace('\\', '\\\\')
    nsi_content = f'''!include "MUI2.nsh"

Name "ZeroKeys"
OutFile "{o}"
InstallDir "$PROGRAMFILES64\\ZeroKeys"
RequestExecutionLevel admin

!define MUI_ABORTWARNING
!define MUI_WELCOMEPAGE_TITLE "ZeroKeys Installer"
!define MUI_WELCOMEPAGE_TEXT "This will install ZeroKeys voice-to-text on your computer.$\\r$\\n$\\r$\\nPress Alt+X to start dictation anywhere."

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES

!define MUI_FINISHPAGE_RUN "$INSTDIR\\ZeroKeys.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Launch ZeroKeys"
!define MUI_FINISHPAGE_NOREBOOTSUPPORT
!insertmacro MUI_PAGE_FINISH

!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES

!insertmacro MUI_LANGUAGE "English"

Section "ZeroKeys (required)" SecMain
  SectionIn RO
  SetOutPath "$INSTDIR"
  File "{e}"

  WriteUninstaller "$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "DisplayName" "ZeroKeys"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "UninstallString" "$INSTDIR\\Uninstall.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "DisplayIcon" "$INSTDIR\\ZeroKeys.exe"
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "DisplayVersion" "1.0.0"
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "NoModify" 1
  WriteRegDWORD HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys" \\
                "NoRepair" 1
  WriteRegStr HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" \\
                "ZeroKeys" "$INSTDIR\\ZeroKeys.exe"
SectionEnd

Section "Desktop Shortcut" SecDesktop
  CreateShortCut "$DESKTOP\\ZeroKeys.lnk" "$INSTDIR\\ZeroKeys.exe"
SectionEnd

Section "Start Menu Shortcut" SecStartMenu
  CreateDirectory "$SMPROGRAMS\\ZeroKeys"
  CreateShortCut "$SMPROGRAMS\\ZeroKeys\\ZeroKeys.lnk" "$INSTDIR\\ZeroKeys.exe"
  CreateShortCut "$SMPROGRAMS\\ZeroKeys\\Uninstall.lnk" "$INSTDIR\\Uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$INSTDIR\\ZeroKeys.exe"
  Delete "$INSTDIR\\Uninstall.exe"
  RMDir "$INSTDIR"

  Delete "$DESKTOP\\ZeroKeys.lnk"
  RMDir /r "$SMPROGRAMS\\ZeroKeys"

  DeleteRegKey HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\ZeroKeys"
  DeleteRegValue HKCU "Software\\Microsoft\\Windows\\CurrentVersion\\Run" "ZeroKeys"

  RMDir /r "$INSTDIR"
SectionEnd
'''

    nsi_path = Path(tempfile.gettempdir()) / 'dictation_installer.nsi'
    nsi_path.write_text(nsi_content, encoding='utf-8')

    print('Compiling installer...')
    r = subprocess.run([str(makensis), str(nsi_path)], capture_output=True, text=True)
    # ponytail: keep .nsi for debugging, overwritten each run

    if r.returncode != 0:
        print('makensis failed:')
        print(r.stderr)
        sys.exit(1)

    if Path(outfile).exists():
        size_mb = Path(outfile).stat().st_size / (1024 * 1024)
        print(f'Installer created: {outfile} ({size_mb:.1f} MB)')
    else:
        print(f'Error: installer not found at {outfile}')
        sys.exit(1)


def main():
    if not EXE.exists():
        print('Step 1: Build ZeroKeys.exe with PyInstaller first.')
        print(f'Expected at: {EXE}')
        print('Run: pyinstaller --onefile --name ZeroKeys ... main.py')
        sys.exit(1)

    makensis = check_nsis()
    build_installer(makensis)


if __name__ == '__main__':
    main()

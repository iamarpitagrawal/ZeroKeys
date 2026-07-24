# ZeroKeys

ZeroKeys is a voice dictation overlay for Windows. Press a hotkey (Alt+X by default), speak naturally, and your words appear at the cursor — in any app. 100% offline, no cloud, no accounts.

## Features

- **Live Waveform** — real-time audio visualization
- **AI Text Polish** — removes "um", "uh", fixes punctuation (optional local LLM)
- **Auto-Paste** — text lands at your cursor automatically
- **99+ Languages** — English-only or multilingual models
- **Customizable Hotkeys** — change anytime, no restart needed
- **System Tray** — minimize to tray, toggle from anywhere
- **100% Offline** — your voice never leaves your machine

## Download

Grab the latest installer from the [Releases page](https://github.com/iamarpitagrawal/ZeroKeys/releases).

## Build from Source

```bash
pip install -r requirements.txt
python build.bat
```

The installer will be at `dist\ZeroKeys_Setup.exe`.

## Requirements

- Windows 10/11
- Python 3.10+
- ~2 GB RAM (varies by model size)

## License

MIT

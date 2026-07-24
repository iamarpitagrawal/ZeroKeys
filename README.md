<div align="center">
  <img src="zerokeys_tray.png" alt="ZeroKeys" width="80" />
  <h1 align="center">ZeroKeys</h1>
  <p align="center"><b>Don't Type. Just Speak.</b></p>

  <p align="center">
    <a href="https://github.com/iamarpitagrawal/ZeroKeys/releases">
      <img src="https://img.shields.io/badge/Download-Installer-%23079F91?style=for-the-badge&logo=windows" alt="Download" />
    </a>
    <a href="https://github.com/iamarpitagrawal/ZeroKeys/blob/main/LICENSE">
      <img src="https://img.shields.io/badge/License-MIT-%23052A94?style=for-the-badge" alt="MIT License" />
    </a>
    <a href="https://github.com/iamarpitagrawal/ZeroKeys">
      <img src="https://img.shields.io/badge/Python-3.10%2B-%233776AB?style=for-the-badge&logo=python" alt="Python" />
    </a>
  </p>

  <br />

  <p>
    A voice dictation overlay for <b>Windows</b>. Press a hotkey, speak naturally, and your words appear at the cursor — in any app. <b>100% offline. No cloud. No accounts.</b>
  </p>
</div>

<br />

---

<br />

## &#x2728; Features

| Feature | What it does |
|---|---|
| &#x1F3A4; **Live Waveform** | Real-time audio visualization — dances when you speak, flat when silent |
| &#x2728; **AI Text Polish** | Removes filler words ("um", "uh"), fixes punctuation & capitalization. Optionally runs through a local LLM |
| &#x1F4CB; **Auto-Paste** | Text lands at your cursor instantly via simulated keystrokes — or copy to clipboard, your choice |
| &#x1F310; **99+ Languages** | Choose a fast English-only model or a multilingual model that auto-detects the language |
| &#x2328;&#xFE0F; **Customizable Hotkeys** | Alt+X by default. Change anytime in Settings — takes effect immediately, no restart needed |
| &#x1FA9F; **System Tray** | Minimizes to tray. Left-click to toggle overlay, right-click for settings, mic toggle, or exit |
| &#x1F512; **100% Offline** | Your voice never leaves your machine. No internet required (except initial model download) |

<br />

## &#x1F4E5; Download

Grab the latest installer from the **[Releases page](https://github.com/iamarpitagrawal/ZeroKeys/releases)**.

| File | What it is |
|---|---|
| `ZeroKeys_Setup.exe` | &#x1F4E6; Full installer (recommended) |
| `ZeroKeys.exe` | &#x1F4E6; Portable executable (no install) |

<br />

## &#x1F6E0;&#xFE0F; Build from Source

### Prerequisites

- **OS:** Windows 10 or 11
- **Python:** 3.10 or higher
- **RAM:** ~2 GB (varies by model size)

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/iamarpitagrawal/ZeroKeys.git
cd ZeroKeys

# 2. Install dependencies
pip install -r requirements.txt

# 3. Build everything (EXE + installer)
python build.bat
```

The installer will be at `dist\ZeroKeys_Setup.exe`.

<br />

## &#x1F9EA; How It Works

```
1. Press Alt+X   &#x2192;   2. Speak naturally   &#x2192;   3. Press Alt+X again
                                      &#x2193;
                            Text appears at your cursor
```

The overlay shows a live waveform while you speak. Audio is captured in a background thread — no UI freezing.

<br />

## &#x1F46B; Tech Stack

| Component | Library |
|---|---|
| Speech-to-text | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) |
| UI | [customtkinter](https://github.com/TomSchimansky/CustomTkinter) |
| Audio capture | [sounddevice](https://python-sounddevice.readthedocs.io/) |
| System tray | [pystray](https://pypi.org/project/pystray/) |
| Hotkeys | `ctypes` / Windows API |
| Text polish | [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) (optional) |

<br />

## &#x1F4DC; License

[MIT](LICENSE) &mdash; free to use, modify, and distribute.

<br />

---

<div align="center">
  <sub>Built with &#x2764;&#xFE0F; by <a href="https://www.linkedin.com/in/arpit-kumar-agrawal/">Arpit Kumar Agrawal</a></sub>
  <br />
  <sub><a href="https://www.zerokeys.in">zerokeys.in</a></sub>
</div>

#!/usr/bin/env python3
"""ZeroKeys — overlay + tray dictation app. Backend untouched."""

import sys, os, json, time, ctypes, re, subprocess, threading, tkinter as tk, winreg
from tkinter import messagebox as mb
from pathlib import Path
import customtkinter as ctk
import pystray
from PIL import Image, ImageDraw, ImageTk

import sounddevice as sd
import numpy as np
import pyperclip
from faster_whisper import WhisperModel

IDLE_ICON = Path.home() / 'Desktop' / 'microphone-alt-svgrepo-com.png'
REC_ICON = Path.home() / 'Desktop' / 'microphone-slash-alt-svgrepo-com.png'

CFG = Path.home() / '.dictation'
CFG.mkdir(parents=True, exist_ok=True)
DICT_FILE = CFG / 'dict.json'
CONFIG_FILE = CFG / 'config.json'
MODELS_DIR = CFG / 'models'
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    'hotkey_mod': 0x0001, 'hotkey_vk': 0x58,
    'model': 'base.en', 'lang': 'en', 'auto_paste': True,
    'device': None, 'ontop': True, 'aggressive_clean': False,
    'polish_enabled': False, 'polish_mode': 'auto',
    'polish_model': 'phi3:mini', 'autostart': False,
    'overlay_x': None, 'overlay_y': None,
}

HOTKEY_PRESETS = {
    'Alt+X': (0x0001, 0x58),
    'Ctrl+Shift+V': (0x0002 | 0x0004, 0x56),
    'Ctrl+Win+V': (0x0002 | 0x0008, 0x56),
    'Ctrl+Alt+V': (0x0002 | 0x0001, 0x56),
    'Ctrl+Shift+Space': (0x0002 | 0x0004, 0x20),
    'Ctrl+Win+Space': (0x0002 | 0x0008, 0x20),
    'Win+Shift+V': (0x0008 | 0x0004, 0x56),
}

TRANSCRIPTION_MODELS = [
    'tiny.en', 'base.en', 'small.en', 'medium.en', 'large-v3',
    'tiny', 'base', 'small', 'medium', 'large-v3',
    'distil-small.en', 'distil-medium.en', 'distil-large-v3',
]

GGUF_MODELS = {
    'llama3.2:3b': ('Llama-3.2-3B-Instruct-Q4_K_M.gguf',
                     'https://huggingface.co/bartowski/Llama-3.2-3B-Instruct-GGUF/resolve/main/Llama-3.2-3B-Instruct-Q4_K_M.gguf'),
    'llama3.2:1b': ('Llama-3.2-1B-Instruct-Q4_K_M.gguf',
                     'https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF/resolve/main/Llama-3.2-1B-Instruct-Q4_K_M.gguf'),
    'phi3:mini': ('Phi-3-mini-4k-instruct-q4.gguf',
                   'https://huggingface.co/microsoft/Phi-3-mini-4k-instruct-gguf/resolve/main/Phi-3-mini-4k-instruct-q4.gguf'),
}
POLISH_MODEL_LABELS = {'phi3:mini': 'Phi-3 Mini', 'llama3.2:3b': 'Llama 3.2 3B', 'llama3.2:1b': 'Llama 3.2 1B', 'gemma2:2b': 'Gemma 2 2B'}

AUTOSTART_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'

def autostart_set(exe_path, enable):
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_SET_VALUE)
        if enable:
            winreg.SetValueEx(k, 'ZeroKeys', 0, winreg.REG_SZ, str(exe_path))
        else:
            try: winreg.DeleteValue(k, 'ZeroKeys')
            except: pass
        winreg.CloseKey(k)
    except: pass

def autostart_get():
    try:
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY, 0, winreg.KEY_READ)
        v, _ = winreg.QueryValueEx(k, 'ZeroKeys')
        winreg.CloseKey(k)
        return v and Path(v).exists()
    except: return False

def single_instance_check():
    kernel32 = ctypes.windll.kernel32
    kernel32.SetLastError(0)
    kernel32.CreateMutexW(None, False, 'ZeroKeysAppMutex')
    return kernel32.GetLastError() != 183


class Config:
    def __init__(self):
        self.data = dict(DEFAULT_CONFIG)
        if CONFIG_FILE.exists():
            try:
                d = json.loads(CONFIG_FILE.read_text())
                for k in DEFAULT_CONFIG:
                    if k in d:
                        self.data[k] = d[k]
            except:
                self.save()
        self._find_preset_name()

    def _find_preset_name(self):
        m, v = self.data['hotkey_mod'], self.data['hotkey_vk']
        for name, (pm, pv) in HOTKEY_PRESETS.items():
            if pm == m and pv == v:
                self.hotkey_name = name
                return
        self.hotkey_name = f'Custom (mod={m}, vk={v})'

    def save(self):
        CONFIG_FILE.write_text(json.dumps(self.data, indent=2))
        self._find_preset_name()

    def __getitem__(self, k):
        return self.data[k]

    def __setitem__(self, k, v):
        self.data[k] = v


class Recorder:
    def __init__(self, cfg):
        self.cfg = cfg
        self.buf, self.is_rec, self.stream = [], False, None
        self.wave_audio = []
        self._wave_lock = threading.Lock()

    def _cb(self, indata, frames, time_info, status):
        if self.is_rec:
            self.buf.append(indata.copy())
            with self._wave_lock:
                self.wave_audio.append(indata.copy())
                if len(self.wave_audio) > 60:
                    self.wave_audio.pop(0)

    def toggle(self):
        if self.is_rec:
            self.is_rec = False
            if self.stream:
                self.stream.stop(); self.stream.close(); self.stream = None
            if not self.buf:
                return None
            a = np.concatenate(self.buf, axis=0).flatten()
            self.buf = []
            return a
        self.buf, self.is_rec = [], True
        with self._wave_lock:
            self.wave_audio = []
        device = self.cfg['device']
        self.stream = sd.InputStream(samplerate=16000, channels=1, dtype='float32',
                                      callback=self._cb, device=device)
        self.stream.start()
        return True


class Transcriber:
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = None
        self.loaded = False

    def ensure(self):
        if self.model is None:
            self.model = WhisperModel(self.cfg['model'], device='cpu', compute_type='int8')
        self.loaded = True

    def transcribe(self, audio):
        if not self.loaded:
            return ''
        segs, _ = self.model.transcribe(audio, beam_size=1,
                                         language=self.cfg['lang'] if self.cfg['lang'] != 'auto' else None)
        return ''.join(s.text for s in segs).strip()


def rule_clean(text, aggressive=False):
    t = re.sub(r'\b(um+|uh+|like|you know|sort of|kind of|i mean|actually|basically|literally|honestly|right|so)\b', '', text, flags=re.I)
    if aggressive:
        t = re.sub(r'\b(supposed to|going to|want to|need to|have to|got to)\b',
                   lambda m: {'supposed to': 'supposed to', 'going to': 'gonna',
                              'want to': 'wanna', 'need to': 'need to',
                              'have to': 'have to', 'got to': 'gotta'}.get(m.group(), m.group()), t, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip()
    if t and t[-1] not in '.!?':
        t += '.'
    return t[0].upper() + t[1:] if t else t


class Polisher:
    def __init__(self, cfg, status_cb=None):
        self.cfg = cfg
        self.status = status_cb or (lambda x: None)
        self.ollama_ok = False
        self.llm = None
        self.model_path = None
        threading.Thread(target=self._ollama_init, daemon=True).start()

    def _ollama_init(self):
        try:
            r = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=5)
            self.ollama_ok = r.returncode == 0
        except: self.ollama_ok = False

    def ensure_ollama_model(self, name):
        if not self.ollama_ok:
            return False
        try:
            r = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=10)
            if name in r.stdout:
                return True
            self.status(f'Downloading {name} via Ollama...')
            subprocess.run(['ollama', 'pull', name], timeout=300)
            return True
        except: return False

    def _ollama_polish(self, text, model):
        import ollama
        prompt = f"""Polish this voice transcription for readability:
- Remove filler words (um, uh, like, you know)
- Fix punctuation and capitalization
- Restructure awkward sentences
- Keep all meaning and details
Output only the polished text.

Input: {text}
Polished:"""
        resp = ollama.generate(model=model, prompt=prompt, options={'num_predict': 512, 'temperature': 0.3})
        return resp['response'].strip().strip('"\'')

    def _ensure_bundled(self, model_name):
        if model_name not in GGUF_MODELS:
            return False
        fname, url = GGUF_MODELS[model_name]
        self.model_path = MODELS_DIR / fname
        if self.model_path.exists():
            return True
        self.status(f'Downloading {POLISH_MODEL_LABELS.get(model_name, model_name)} (~1.5-2.5GB)...')
        try:
            from huggingface_hub import hf_hub_download
            repo = '/'.join(url.split('/')[3:5])
            path = hf_hub_download(repo_id=repo, filename=fname, local_dir=MODELS_DIR)
            self.model_path = Path(path)
            return True
        except Exception as e:
            self.status(f'Download failed: {e}')
            return False

    def _bundled_polish(self, text):
        if self.llm is None:
            try:
                from llama_cpp import Llama
                self.llm = Llama(model_path=str(self.model_path), n_ctx=1024, verbose=False)
            except Exception as e:
                self.status(f'LLM load failed: {e}')
                return None
        prompt = f"""<|begin_of_text|><|start_header_id|>system<|end_header_id|>
You polish voice transcriptions: remove fillers, fix punctuation/capitalization, restructure for readability. Output only the polished text.<|eot_id|>
<|start_header_id|>user<|end_header_id|>
{text}<|eot_id|>
<|start_header_id|>assistant<|end_header_id|>"""
        resp = self.llm(prompt, max_tokens=512, temperature=0.3, stop=['<|eot_id|>'])
        return resp['choices'][0]['text'].strip().strip('"\'')

    def polish(self, text):
        if not text:
            return text
        if not self.cfg['polish_enabled']:
            return rule_clean(text, self.cfg['aggressive_clean'])

        mode = self.cfg['polish_mode']
        model = self.cfg['polish_model']

        if mode in ('auto', 'ollama') and self.ollama_ok:
            if self.ensure_ollama_model(model):
                try:
                    return self._ollama_polish(text, model)
                except: pass

        if mode in ('auto', 'bundled'):
            if self._ensure_bundled(model):
                try:
                    result = self._bundled_polish(text)
                    if result:
                        return result
                except: pass

        return rule_clean(text, self.cfg['aggressive_clean'])


def make_tray_icon():
    img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse([8, 8, 56, 56], fill='#1a1a1a')
    d.ellipse([18, 14, 46, 38], fill='#2ecc71')
    d.rectangle([28, 38, 36, 48], fill='#2ecc71')
    d.ellipse([30, 44, 34, 50], fill='#2ecc71')
    d.ellipse([22, 28, 42, 40], fill='#1a1a1a')
    return img


class ZeroKeysApp:
    def __init__(self):
        self.cfg = Config()
        self.rec = Recorder(self.cfg)
        self.trans = Transcriber(self.cfg)
        self.words = set()
        self._load_dict()
        self.root = None
        self.overlay = None
        self.settings_win = None
        self.tray_icon = None
        self.polisher = None
        self._gen = 0
        self._gen_lock = threading.Lock()
        self._ready = False
        self._hk_reload = threading.Event()
        self._hk_thread = None

    def _load_dict(self):
        if DICT_FILE.exists():
            self.words = set(json.loads(DICT_FILE.read_text()))

    def _save_dict(self, text):
        for w in re.findall(r"[a-zA-Z']+", text):
            w = w.lower()
            if len(w) > 2 and w not in self.words:
                self.words.add(w)
        DICT_FILE.write_text(json.dumps(sorted(self.words)))

    def inject(self, text):
        pyperclip.copy(text)
        ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
        ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
        time.sleep(0.05)
        ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
        ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)

    def on_hotkey(self):
        if not self._ready or not self.overlay:
            return
        with self._gen_lock:
            self._gen += 1
            gen = self._gen
        try:
            r = self.rec.toggle()
        except Exception as e:
            self.overlay.set_status(f'Mic error: {e}')
            return
        if r is True:
            self.overlay.set_status('recording')
            ctypes.windll.user32.MessageBeep(0x30)
            return
        ctypes.windll.user32.MessageBeep(0x40)
        self.overlay.set_status('transcribing')
        if r is None:
            self.overlay.set_status('No audio')
            return
        threading.Thread(target=self._do_transcribe, args=(r, gen), daemon=True).start()

    def _do_transcribe(self, audio, gen):
        try:
            text = self.trans.transcribe(audio)
            if not text:
                with self._gen_lock:
                    if gen == self._gen:
                        self.root.after(0, lambda: self.overlay.set_status('No speech detected'))
                ctypes.windll.user32.MessageBeep(0x10)
                return
            self.root.after(0, lambda g=gen: self._update_polish_status(g))
            cleaned = self.polisher.polish(text)
            self._save_dict(text)
            self.root.after(0, lambda g=gen, t=cleaned: self._finish_transcribe(g, t))
        except Exception as e:
            with self._gen_lock:
                if gen == self._gen:
                    self.root.after(0, lambda: self.overlay.set_status('Error'))
                    self.root.after(0, lambda: print(f'Transcribe error: {e}'))

    def _update_polish_status(self, gen):
        with self._gen_lock:
            if gen == self._gen:
                self.overlay.set_status('polishing' if self.cfg['polish_enabled'] else 'cleaning')

    def _finish_transcribe(self, gen, text):
        with self._gen_lock:
            if gen != self._gen:
                return
        if self.cfg['auto_paste']:
            self.inject(text)
        else:
            pyperclip.copy(text)
        self.overlay.set_status('Done')

    def _ensure_msg_queue(self):
        msg = ctypes.wintypes.MSG()
        ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001)

    def _try_register(self, mod, vk):
        return ctypes.windll.user32.RegisterHotKey(None, 1, mod, vk)

    def run_hotkey_pump(self):
        self._ensure_msg_queue()
        user32 = ctypes.windll.user32
        WM_USER = 0x0400
        mod, vk = self.cfg['hotkey_mod'], self.cfg['hotkey_vk']
        ok = self._try_register(mod, vk)
        if not ok:
            kernel32 = ctypes.windll.kernel32
            err = kernel32.GetLastError()
            self.root.after(0, lambda e=err: mb.showerror(
                'Hotkey Error',
                f'Failed to register hotkey (error {e}).\n\n'
                f'Change hotkey in Settings to a different combination.'))
            return
        msg = ctypes.wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == 0x0312:
                self.on_hotkey()
            elif msg.message == WM_USER and self._hk_reload.is_set():
                self._hk_reload.clear()
                user32.UnregisterHotKey(None, 1)
                mod, vk = self.cfg['hotkey_mod'], self.cfg['hotkey_vk']
                self._try_register(mod, vk)
        user32.UnregisterHotKey(None, 1)

    def create_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem('Settings', lambda: self.root.after(0, self.open_settings)),
            pystray.MenuItem('Toggle Mic', lambda: self.root.after(0, self.on_hotkey)),
            pystray.MenuItem('Exit', lambda: self.root.after(0, self._on_close)),
        )
        self.tray_icon = pystray.Icon('ZeroKeys', make_tray_icon(), 'ZeroKeys', menu)
        self.tray_icon.on_left_click = lambda: self.root.after(0, self.toggle_overlay)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def toggle_overlay(self):
        if self.overlay and self.overlay.window.winfo_viewable():
            self.overlay.hide()
        elif self.overlay:
            self.overlay.show()

    def create_overlay(self):
        self.overlay = ZeroKeysOverlay(self)

    def open_settings(self):
        if self.settings_win and self.settings_win.win.winfo_exists():
            self.settings_win.win.deiconify()
            self.settings_win.win.lift()
            return
        self.settings_win = SettingsWindow(self)
        self.settings_win.win.protocol('WM_DELETE_WINDOW', self._close_settings)

    def _close_settings(self):
        if self.settings_win:
            self.settings_win.win.withdraw()

    def start_ui(self):
        ctk.set_appearance_mode('dark')
        ctk.set_default_color_theme('green')
        self.root = ctk.CTk()
        self.root.withdraw()
        self.root.title('ZeroKeys')
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self.create_overlay()
        self.polisher = Polisher(self.cfg, lambda msg: self.root.after(0, lambda m=msg: self.overlay.set_status(m)))
        self.create_tray()
        self.root.after(0, self._start_bg)
        self.root.mainloop()

    def _start_bg(self):
        t = threading.Thread(target=self.run_hotkey_pump, daemon=True)
        t.start()
        self._hk_thread = t
        self.root.after(100, self.overlay.update_waveform)
        threading.Thread(target=self._bg_load, daemon=True).start()

    def _bg_load(self):
        if not self.trans.loaded:
            self.root.after(0, lambda: self.overlay.set_status('Downloading speech model (first run)...'))
            self.trans.ensure()
        self.root.after(0, lambda: self.overlay.set_status('Ready'))
        self.root.after(0, self.overlay.show)
        self.root.after(0, lambda: setattr(self, '_ready', True))

    def _on_close(self):
        try:
            if self.rec and self.rec.stream:
                self.rec.stream.stop(); self.rec.stream.close()
        except: pass
        try:
            if self.tray_icon:
                self.tray_icon.stop()
        except: pass
        self.root.destroy()
        os._exit(0)

    def reload(self):
        self.cfg = Config()
        self.rec.cfg = self.cfg
        self.trans.cfg = self.cfg
        self.polisher.cfg = self.cfg
        if self.overlay:
            self.overlay.window.attributes('-topmost', self.cfg['ontop'])
        if self._hk_thread and self._hk_thread.is_alive():
            self._hk_reload.set()
            ctypes.windll.user32.PostThreadMessageW(self._hk_thread.ident, 0x0400, 0, 0)

    def uninstall(self):
        sure = mb.askyesno('Uninstall', 'Remove ZeroKeys and all its data (models, config, learned words)?')
        if not sure:
            return
        try:
            import shutil
            if CFG.exists():
                shutil.rmtree(CFG)
        except: pass
        autostart_set(Path(sys.executable), False)
        try:
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                               r'Software\Microsoft\Windows\CurrentVersion\Uninstall', 0, winreg.KEY_SET_VALUE)
            winreg.DeleteKey(k, 'ZeroKeys')
            winreg.CloseKey(k)
        except: pass
        mb.showinfo('Uninstall', 'Data deleted. Use "Add or Remove Programs" to finish removal.')
        self._on_close()


class ZeroKeysOverlay:
    def __init__(self, app):
        self.app = app
        self.W, self.H = 200, 60
        self.window = tk.Toplevel(app.root)
        self.window.overrideredirect(True)
        self.window.attributes('-topmost', True)
        self.visible = False
        self._drag_data = {'x': 0, 'y': 0}
        self._build()
        self._enable_acrylic()
        self._set_shape()
        self._bind_drag()
        self.window.withdraw()

    def _hwnd(self):
        return ctypes.windll.user32.GetParent(self.window.winfo_id())

    def _enable_acrylic(self):
        hwnd = self._hwnd()
        try:
            ctypes.windll.user32.SetWindowLongW(hwnd, -20,
                ctypes.windll.user32.GetWindowLongW(hwnd, -20) | 0x80000)
        except: pass
        try:
            from ctypes import byref, c_int, c_size_t, POINTER, Structure
            class ACCENTPOLICY(Structure):
                _fields_ = [('AccentState', c_int), ('AccentFlags', c_int),
                            ('GradientColor', c_int), ('AnimationId', c_int)]
            class WINCOMPATTRDATA(Structure):
                _fields_ = [('Attribute', c_int), ('Data', POINTER(ACCENTPOLICY)),
                            ('SizeOfData', c_size_t)]
            accent = ACCENTPOLICY(AccentState=5, AccentFlags=0x20, GradientColor=0xCCF0F0F0, AnimationId=0)
            data = WINCOMPATTRDATA(Attribute=19, Data=byref(accent), SizeOfData=sizeof(accent))
            ctypes.windll.user32.SetWindowCompositionAttribute(hwnd, byref(data))
        except: pass
        try:
            cs_dropshadow = 0x00020000
            curr = ctypes.windll.user32.GetClassLongPtrW(hwnd, -26)
            ctypes.windll.user32.SetClassLongPtrW(hwnd, -26, curr | cs_dropshadow)
        except: pass
        self.window.attributes('-alpha', 0.88)

    def _set_shape(self):
        try:
            hwnd = self._hwnd()
            rgn = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, self.W, self.H, 30, 30)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)
        except: pass

    def _build(self):
        cfg = self.app.cfg.data
        x = cfg.get('overlay_x')
        y = cfg.get('overlay_y')
        if x is None:
            sw = self.window.winfo_screenwidth()
            sh = self.window.winfo_screenheight()
            x = sw // 2 - self.W // 2
            y = sh - self.H - 20
        self.window.geometry(f'{self.W}x{self.H}+{x}+{y}')
        self.window.configure(bg='#F8F9FA')

        self.canvas = tk.Canvas(self.window, width=self.W, height=self.H,
                                 bg='#F8F9FA', highlightthickness=0)
        self.canvas.pack()

        self.canvas.create_rectangle(1, 1, self.W-1, self.H-1, fill='#F8F9FA',
                                      outline='#000000', width=2)

        cx, cy = 32, 30
        cr = 16
        self._circle_size = cr * 2
        def _make_circle(color, glow=False):
            s = self._circle_size * 4
            img = Image.new('RGBA', (s, s), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse([4, 4, s-4, s-4], fill=color)
            if glow:
                draw.ellipse([1, 1, s-1, s-1], fill='#E74C3C')
            return ImageTk.PhotoImage(img.resize((self._circle_size, self._circle_size), Image.LANCZOS))
        self._circle_idle = _make_circle('#1A1A1A')
        self._circle_rec = _make_circle('#E74C3C', glow=True)
        self._circle_proc = _make_circle('#C0392B')
        self.mic_bg = self.canvas.create_image(cx, cy, image=self._circle_idle)
        def _load_icon(path):
            if path.exists():
                img = Image.open(str(path)).resize((22, 22), Image.LANCZOS)
                if img.mode == 'RGBA':
                    r, g, b, a = img.split()
                    r = r.point(lambda x: 255)
                    g = g.point(lambda x: 255)
                    b = b.point(lambda x: 255)
                    img = Image.merge('RGBA', (r, g, b, a))
                return ImageTk.PhotoImage(img)
            return None
        self._idle_img = _load_icon(IDLE_ICON)
        self._rec_img = _load_icon(REC_ICON)
        self.mic_icon = self.canvas.create_image(cx, cy, image=self._idle_img)
        self.canvas.addtag_withtag('mic', self.mic_bg)
        self.canvas.addtag_withtag('mic', self.mic_icon)
        self.canvas.tag_bind('mic', '<Button-1>', self._mic_handler)

        self.wave_canvas = tk.Canvas(self.canvas, width=130, height=46,
                                      bg='#F8F9FA', highlightthickness=0)
        self.canvas.create_window(130, 30, window=self.wave_canvas, anchor='center')

    def _bind_drag(self):
        self.window.bind('<Button-1>', self._drag_start)
        self.window.bind('<B1-Motion>', self._drag_move)
        self.window.bind('<ButtonRelease-1>', self._drag_end)

    def _drag_start(self, e):
        self._drag_data['x'] = e.x_root
        self._drag_data['y'] = e.y_root

    def _drag_move(self, e):
        dx = e.x_root - self._drag_data['x']
        dy = e.y_root - self._drag_data['y']
        x = self.window.winfo_x() + dx
        y = self.window.winfo_y() + dy
        self.window.geometry(f'+{x}+{y}')
        self._drag_data['x'] = e.x_root
        self._drag_data['y'] = e.y_root

    def _drag_end(self, e):
        cfg = self.app.cfg.data
        cfg['overlay_x'] = self.window.winfo_x()
        cfg['overlay_y'] = self.window.winfo_y()
        self.app.cfg.save()

    def _mic_handler(self, e):
        self.app.on_hotkey()
        return 'break'

    def show(self):
        self.visible = True
        self.window.deiconify()
        self.window.lift()

    def hide(self):
        self.visible = False
        self.window.withdraw()

    def set_status(self, s):
        if s == 'recording':
            self.canvas.itemconfig(self.mic_bg, image=self._circle_rec)
            self.canvas.itemconfig(self.mic_icon, image=self._rec_img)
        elif s in ('transcribing', 'polishing', 'cleaning', 'Downloading'):
            self.canvas.itemconfig(self.mic_bg, image=self._circle_proc)
        else:
            self.canvas.itemconfig(self.mic_bg, image=self._circle_idle)
            self.canvas.itemconfig(self.mic_icon, image=self._idle_img)

    def update_waveform(self):
        rec = self.app.rec
        if rec.is_rec:
            with rec._wave_lock:
                if rec.wave_audio:
                    try:
                        audio = np.concatenate([x.copy() for x in rec.wave_audio], axis=0).flatten()
                    except:
                        audio = None
                else:
                    audio = None
            if audio is not None:
                self._draw_wave(audio)
        else:
            self.wave_canvas.delete('wave')
        self.app.root.after(60, self.update_waveform)

    def _draw_wave(self, audio):
        self.wave_canvas.delete('wave')
        w = self.wave_canvas.winfo_width() or 130
        h = self.wave_canvas.winfo_height() or 46
        if len(audio) < 4: return

        rms = np.sqrt(np.mean(audio**2))
        if rms < 0.004:
            y = h / 2
            self.wave_canvas.create_line([0, y, w, y], fill='#000000', width=2, tags='wave')
            return

        step = max(1, len(audio) // w)
        samples = audio[::step][:w]
        env = np.abs(samples)
        env = np.convolve(env, np.ones(3)/3, mode='same')
        gain = min(1.0, (rms * 50) ** 0.75)
        cycles = 2.5
        t = np.linspace(0, 2 * np.pi * cycles, w)
        wave = np.sin(t + env * 2.0) * env * gain * 1.1
        coords = []
        for i, s in enumerate(wave):
            y = h / 2 - s * h / 2.5
            coords.extend([i, max(0, min(h, y))])
        self.wave_canvas.create_line(coords, fill='#000000', width=2, smooth=True, tags='wave')


class SettingsWindow:
    def __init__(self, app):
        self.app = app
        self.win = ctk.CTkToplevel(app.root)
        self.win.title('Settings')
        self.win.geometry('440x560')
        self.win.resizable(False, False)
        self.win.transient(app.root)
        self.win.protocol('WM_DELETE_WINDOW', self._on_close)
        self._build()

    def _on_close(self):
        self.win.withdraw()

    def _add_section(self, parent, title):
        f = ctk.CTkFrame(parent)
        f.pack(fill='x', pady=(0, 8))
        ctk.CTkLabel(f, text=title, font=('Segoe UI', 12, 'bold'),
                      anchor='w').pack(anchor='w', padx=12, pady=(8, 4))
        return f

    def _build(self):
        sf = ctk.CTkScrollableFrame(self.win, fg_color='transparent')
        sf.pack(fill='both', expand=True, padx=14, pady=10)

        f = self._add_section(sf, 'Transcription')
        g = ctk.CTkFrame(f, fg_color='transparent')
        g.pack(fill='x', padx=12, pady=(0, 8))
        g.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(g, text='Model:', width=80, anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        self.model_var = ctk.StringVar(value=self.app.cfg['model'])
        ctk.CTkComboBox(g, variable=self.model_var, values=TRANSCRIPTION_MODELS,
                         state='readonly', width=200).grid(row=0, column=1, sticky='ew', pady=2)
        ctk.CTkLabel(g, text='Language:', width=80, anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        self.lang_var = ctk.StringVar(value=self.app.cfg['lang'])
        def _on_lang(*_):
            if self.lang_var.get() not in ('en', 'auto') and self.model_var.get().endswith('.en'):
                mb.showinfo('Hindi Support',
                    f'For Hindi, switch Model to "small", "medium", or "large-v3".\n'
                    f'Current model "{self.model_var.get()}" only supports English.',
                    parent=self.win)
        self.lang_var.trace_add('write', _on_lang)
        ctk.CTkComboBox(g, variable=self.lang_var, values=['en', 'hi', 'auto'],
                         state='readonly', width=200).grid(row=1, column=1, sticky='ew', pady=2)

        f = self._add_section(sf, 'Input')
        g = ctk.CTkFrame(f, fg_color='transparent')
        g.pack(fill='x', padx=12, pady=(0, 8))
        g.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(g, text='Hotkey:', width=80, anchor='w').grid(row=0, column=0, sticky='w', pady=2)
        self.hotkey_var = ctk.StringVar(value=self.app.cfg.hotkey_name)
        ctk.CTkComboBox(g, variable=self.hotkey_var, values=list(HOTKEY_PRESETS.keys()),
                         state='readonly', width=200).grid(row=0, column=1, sticky='ew', pady=2)
        ctk.CTkLabel(g, text='Microphone:', width=80, anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        self.mic_var = ctk.StringVar()
        devices = []
        try:
            for i, d in enumerate(sd.query_devices()):
                s = f'{i}: {d["name"]}'
                devices.append(s)
                if self.app.cfg['device'] == i:
                    self.mic_var.set(s)
        except: pass
        if not self.mic_var.get() and devices:
            self.mic_var.set(devices[0])
        ctk.CTkComboBox(g, variable=self.mic_var, values=devices,
                         state='readonly', width=200).grid(row=1, column=1, sticky='ew', pady=2)

        f = self._add_section(sf, 'AI Text Polish')
        g = ctk.CTkFrame(f, fg_color='transparent')
        g.pack(fill='x', padx=12, pady=(0, 8))
        g.grid_columnconfigure(1, weight=1)
        self.polish_var = ctk.BooleanVar(value=self.app.cfg['polish_enabled'])
        ctk.CTkCheckBox(g, text='Enable AI polish', variable=self.polish_var,
                         onvalue=True, offvalue=False).grid(row=0, column=0, columnspan=2, sticky='w', pady=2)
        ctk.CTkLabel(g, text='Mode:', width=80, anchor='w').grid(row=1, column=0, sticky='w', pady=2)
        self.pmode_var = ctk.StringVar(value=self.app.cfg['polish_mode'])
        ctk.CTkComboBox(g, variable=self.pmode_var, values=['auto', 'ollama', 'bundled', 'off'],
                         state='readonly', width=200).grid(row=1, column=1, sticky='ew', pady=2)
        ctk.CTkLabel(g, text='Model:', width=80, anchor='w').grid(row=2, column=0, sticky='w', pady=2)
        self.pmodel_var = ctk.StringVar(value=self.app.cfg['polish_model'])
        ctk.CTkComboBox(g, variable=self.pmodel_var, values=list(POLISH_MODEL_LABELS.keys()),
                         state='readonly', width=200).grid(row=2, column=1, sticky='ew', pady=2)

        f = self._add_section(sf, 'Options')
        g = ctk.CTkFrame(f, fg_color='transparent')
        g.pack(fill='x', padx=12, pady=(0, 8))
        self.autopaste_var = ctk.BooleanVar(value=self.app.cfg['auto_paste'])
        ctk.CTkCheckBox(g, text='Auto-paste after transcription', variable=self.autopaste_var,
                         onvalue=True, offvalue=False).pack(anchor='w', pady=1)
        self.ontop_var = ctk.BooleanVar(value=self.app.cfg['ontop'])
        ctk.CTkCheckBox(g, text='Keep window on top', variable=self.ontop_var,
                         onvalue=True, offvalue=False).pack(anchor='w', pady=1)
        self.agg_var = ctk.BooleanVar(value=self.app.cfg['aggressive_clean'])
        ctk.CTkCheckBox(g, text='Aggressive filler removal (rule-based)', variable=self.agg_var,
                         onvalue=True, offvalue=False).pack(anchor='w', pady=1)
        self.auto_var = ctk.BooleanVar(value=autostart_get())
        ctk.CTkCheckBox(g, text='Launch on Windows startup', variable=self.auto_var,
                         onvalue=True, offvalue=False).pack(anchor='w', pady=1)

        bf = ctk.CTkFrame(sf, fg_color='transparent')
        bf.pack(pady=(4, 0))
        ctk.CTkButton(bf, text='Save', command=self.save, width=90).pack(side='left', padx=4)
        ctk.CTkButton(bf, text='Cancel', command=self._on_close, width=90).pack(side='left', padx=4)
        ctk.CTkButton(bf, text='🗑 Uninstall', command=self.app.uninstall,
                       fg_color='#c0392b', hover_color='#e74c3c', width=90).pack(side='right', padx=4)

    def save(self):
        cfg = self.app.cfg
        model = self.model_var.get()
        lang = self.lang_var.get()
        cfg['model'] = model
        cfg['lang'] = lang
        cfg['polish_enabled'] = self.polish_var.get()
        cfg['polish_mode'] = self.pmode_var.get()
        cfg['polish_model'] = self.pmodel_var.get()
        cfg['auto_paste'] = self.autopaste_var.get()
        cfg['ontop'] = self.ontop_var.get()
        cfg['aggressive_clean'] = self.agg_var.get()

        mic = self.mic_var.get()
        cfg['device'] = int(mic.split(':')[0]) if mic and ':' in mic else None

        hk = self.hotkey_var.get()
        if hk in HOTKEY_PRESETS:
            cfg['hotkey_mod'], cfg['hotkey_vk'] = HOTKEY_PRESETS[hk]

        exe = Path(sys.executable)
        autostart_set(exe, self.auto_var.get())

        cfg.save()
        self._on_close()
        self.app.reload()


def main():
    if not single_instance_check():
        mb.showerror('ZeroKeys', 'ZeroKeys is already running.')
        return

    try:
        sd.check_input_settings()
    except Exception as e:
        mb.showerror('Error', f'No microphone found: {e}')
        return

    app = ZeroKeysApp()
    app.start_ui()


if __name__ == '__main__':
    main()

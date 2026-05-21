"""
クイック翻訳 (Quick Translate)
- 機能1: 選択範囲のテキストをホットキーで日本語ポップアップ表示
- 機能2: 画面の選択範囲をスクショ→OCR→日本語ポップアップ表示
- システムトレイ常駐
- ホットキー / 翻訳先言語は config.json で変更可能 (トレイメニューからも変更可)
"""
import asyncio
import ctypes
import io
import json
import os
import sys
import time
import threading
import traceback
import tkinter as tk
from urllib.parse import quote

import keyboard
import pyperclip
import pystray
import requests
from PIL import Image, ImageDraw, ImageFont, ImageGrab

try:
    import winocr  # Windows 標準 OCR (winrt)
    WINOCR_AVAILABLE = True
except Exception:
    WINOCR_AVAILABLE = False

# Per-Monitor DPI Aware (V2) を有効化 — 仮想画面座標とtkinter座標のズレを防ぐ
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_virtual_screen_rect() -> tuple[int, int, int, int]:
    """Win32 から全モニタを含む仮想画面の (x, y, width, height) を取得"""
    SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN = 76, 77
    SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 78, 79
    u32 = ctypes.windll.user32
    return (
        u32.GetSystemMetrics(SM_XVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_YVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        u32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
LOG_PATH = os.path.join(APP_DIR, "quick-translate.log")

DEFAULT_CONFIG = {
    "hotkey": "ctrl+shift+t",            # 選択テキスト翻訳
    "screenshot_hotkey": "ctrl+shift+s", # 領域スクショ翻訳
    "target_lang": "ja",
    "source_lang": "auto",
    "ocr_lang": "en",                    # OCR の主言語 (en/ja/zh-Hans 等)
    "popup_timeout_ms": 12000,
    "max_width_px": 460,
    "font_family": "Yu Gothic UI",
    "translated_font_size": 12,
    "original_font_size": 9,
}


def log(msg: str) -> None:
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            cfg.update({k: v for k, v in user_cfg.items() if k in DEFAULT_CONFIG})
        except Exception as e:
            log(f"config 読み込み失敗: {e}")
    save_config(cfg)
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"config 保存失敗: {e}")


def translate(text: str, src: str = "auto", dst: str = "ja") -> str:
    text = text.strip()
    if not text:
        return ""
    url = (
        "https://translate.googleapis.com/translate_a/single"
        f"?client=gtx&sl={src}&tl={dst}&dt=t&q={quote(text)}"
    )
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        data = r.json()
        parts = [seg[0] for seg in data[0] if seg and seg[0]]
        return "".join(parts).strip() or "[翻訳結果が空でした]"
    except Exception as e:
        log(f"translate error: {e}")
        return f"[翻訳失敗: {e}]"


def _release_modifiers():
    """ホットキー押下中の修飾キーをすべて解放 (copy キー送信前の整地)"""
    for k in ("ctrl", "alt", "shift", "windows", "left ctrl", "right ctrl",
              "left alt", "right alt", "left shift", "right shift"):
        try:
            keyboard.release(k)
        except Exception:
            pass


def _try_copy_and_read(copy_keys: str, wait_ms: int = 500) -> str:
    """指定したキー組合せでクリップボードに取得を試みる"""
    try:
        pyperclip.copy("")
    except Exception:
        pass
    _release_modifiers()
    time.sleep(0.08)
    keyboard.send(copy_keys)
    deadline = time.time() + wait_ms / 1000.0
    while time.time() < deadline:
        time.sleep(0.03)
        try:
            current = pyperclip.paste()
        except Exception:
            current = ""
        if current:
            return current
    return ""


def get_selected_text() -> str:
    """選択範囲をクリップボード経由で取得。複数の手段でフォールバック"""
    try:
        original = pyperclip.paste()
    except Exception:
        original = ""

    text = ""
    # 1) 標準的なコピー
    text = _try_copy_and_read("ctrl+c", wait_ms=400)
    # 2) Windows Terminal などのターミナル系コピー
    if not text:
        log("get_selected_text: ctrl+c で取得できず ctrl+shift+c を試行")
        text = _try_copy_and_read("ctrl+shift+c", wait_ms=400)
    # 3) 古典的コピー (Edit > Copy 相当)
    if not text:
        log("get_selected_text: ctrl+shift+c も失敗 ctrl+insert を試行")
        text = _try_copy_and_read("ctrl+insert", wait_ms=400)

    # オリジナルのクリップボードを復元
    try:
        pyperclip.copy(original)
    except Exception:
        pass
    return text


def ocr_image(img: Image.Image, lang: str = "en") -> str:
    """Windows 標準 OCR でテキスト抽出"""
    if not WINOCR_AVAILABLE:
        return "[OCR ライブラリが利用できません]"
    try:
        # winocr は async API。同期で呼び出すラッパを用意
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(winocr.recognize_pil(img, lang))
            loop.close()
        except Exception as e:
            log(f"OCR lang={lang} 失敗: {e} — 既定ロケールで再試行")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(winocr.recognize_pil(img, "en"))
            loop.close()
        text = result.get("text", "") if isinstance(result, dict) else getattr(result, "text", "")
        return (text or "").strip()
    except Exception as e:
        log(f"OCR error: {e}")
        return f"[OCR 失敗: {e}]"


# ---------------- 領域選択オーバーレイ ----------------

class RegionSelector:
    """全画面 (マルチモニタ対応) の半透明オーバーレイで範囲指定。bbox を返す。"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.bbox = None
        self._done = threading.Event()
        self._ov = None
        self._finish = None  # UI スレッド経由で呼ぶキャンセル用クロージャ

    def cancel(self) -> None:
        """外部から (別スレッドからも) キャンセル可能。再ホットキー押下時に使用"""
        if self._finish is not None:
            try:
                self.root.after(0, lambda: self._finish(None))
            except Exception:
                # フォールバック: 直接 done をセット
                self._done.set()

    def select(self):
        """同期的に呼ぶと bbox(left,top,right,bottom)を返す。キャンセル時は None。"""
        self.bbox = None
        self._done.clear()

        def _open():
            vx, vy, vw, vh = get_virtual_screen_rect()

            ov = tk.Toplevel(self.root)
            ov.overrideredirect(True)            # タイトルバーなし
            ov.geometry(f"{vw}x{vh}+{vx}+{vy}")  # 仮想画面全体
            ov.attributes("-alpha", 0.25)
            ov.attributes("-topmost", True)
            ov.configure(bg="black")
            ov.config(cursor="crosshair")
            self._ov = ov

            canvas = tk.Canvas(ov, bg="black", highlightthickness=0)
            canvas.pack(fill="both", expand=True)

            # 視覚ヒント (仮想画面の中央付近)
            hint = (
                "ドラッグで範囲選択 ／ Esc・右クリック・再度ホットキーでキャンセル"
            )
            canvas.create_text(
                vw // 2, 40,
                text=hint,
                fill="#cccccc",
                font=("Yu Gothic UI", 14, "bold"),
            )

            state = {"start": None, "rect": None}

            def on_press(e):
                state["start"] = (e.x_root, e.y_root)
                if state["rect"]:
                    canvas.delete(state["rect"])
                state["rect"] = canvas.create_rectangle(
                    e.x, e.y, e.x, e.y, outline="#00aaff", width=2
                )
                state["start_canvas"] = (e.x, e.y)

            def on_drag(e):
                if not state.get("start_canvas"):
                    return
                x0, y0 = state["start_canvas"]
                canvas.coords(state["rect"], x0, y0, e.x, e.y)

            def on_release(e):
                if not state["start"]:
                    finish(None)
                    return
                x1, y1 = state["start"]
                x2, y2 = e.x_root, e.y_root
                left, right = sorted([x1, x2])
                top, bottom = sorted([y1, y2])
                if right - left < 5 or bottom - top < 5:
                    finish(None)
                    return
                finish((left, top, right, bottom))

            def on_cancel(_e=None):
                finish(None)

            def finish(bbox):
                self.bbox = bbox
                try:
                    ov.destroy()
                except Exception:
                    pass
                self._ov = None
                self._finish = None
                self._done.set()

            # キャンセル経路を一通り
            ov.bind("<ButtonPress-1>", on_press)
            ov.bind("<B1-Motion>", on_drag)
            ov.bind("<ButtonRelease-1>", on_release)
            ov.bind("<ButtonPress-3>", on_cancel)         # 右クリック
            ov.bind("<Escape>", on_cancel)
            canvas.bind("<ButtonPress-3>", on_cancel)
            canvas.bind("<Escape>", on_cancel)

            self._finish = finish
            ov.after(50, lambda: ov.focus_force())

        self.root.after(0, _open)
        # 30 秒で自動失効 (放置防止)
        self._done.wait(timeout=30)
        # タイムアウト後に残っていれば閉じる
        if not self.bbox and self._ov is not None:
            self.cancel()
        return self.bbox


# ---------------- ポップアップ ----------------

class PopupManager:
    def __init__(self, config: dict):
        self.config = config
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("Quick Translate")

    def show(self, original: str, translated: str) -> None:
        cfg = self.config
        win = tk.Toplevel(self.root)
        win.title("翻訳結果")
        win.attributes("-topmost", True)
        win.configure(bg="#1e1e1e")

        x = win.winfo_pointerx() + 12
        y = win.winfo_pointery() + 16
        win.geometry(f"+{x}+{y}")

        orig_text = original.strip()
        if len(orig_text) > 800:
            orig_text = orig_text[:800] + "..."

        orig = tk.Label(
            win,
            text=orig_text or "(原文なし)",
            bg="#2a2a2a",
            fg="#bbbbbb",
            wraplength=cfg["max_width_px"],
            justify="left",
            font=(cfg["font_family"], cfg["original_font_size"]),
            padx=10,
            pady=8,
        )
        orig.pack(fill="x", padx=8, pady=(8, 4))

        trans = tk.Label(
            win,
            text=translated,
            bg="#1e1e1e",
            fg="#ffffff",
            wraplength=cfg["max_width_px"],
            justify="left",
            font=(cfg["font_family"], cfg["translated_font_size"], "bold"),
            padx=10,
            pady=10,
        )
        trans.pack(fill="x", padx=8, pady=(0, 4))

        hint = tk.Label(
            win,
            text="クリック / Esc で閉じる  |  Ctrl+C で訳文コピー",
            bg="#1e1e1e",
            fg="#777777",
            font=(cfg["font_family"], 8),
            padx=10,
            pady=4,
        )
        hint.pack(fill="x", padx=8, pady=(0, 8))

        def close(_e=None):
            try:
                win.destroy()
            except Exception:
                pass

        def copy_translated(_e=None):
            try:
                pyperclip.copy(translated)
            except Exception as e:
                log(f"copy error: {e}")

        win.bind("<Escape>", close)
        for w in (win, orig, trans, hint):
            w.bind("<Button-1>", close)
        win.bind("<Control-c>", copy_translated)
        # popup_timeout_ms が 0 以下なら自動クローズしない (常時表示)
        if cfg.get("popup_timeout_ms", 0) > 0:
            win.after(cfg["popup_timeout_ms"], close)
        win.focus_force()

    def schedule(self, fn, *args):
        self.root.after(0, lambda: fn(*args))

    def run(self):
        self.root.mainloop()


# ---------------- メインアプリ ----------------

class App:
    def __init__(self):
        self.config = load_config()
        self.popup_manager = PopupManager(self.config)
        self.icon = None
        self._text_handle = None
        self._shot_handle = None
        self._busy_text = False
        self._busy_shot = False
        self._active_selector: "RegionSelector | None" = None

    # --- 選択テキスト翻訳 ---
    def on_text_hotkey(self):
        log(f"hotkey 発火: text ({self.config['hotkey']})")
        if self._busy_text:
            log("既に処理中のためスキップ")
            return
        self._busy_text = True
        threading.Thread(target=self._handle_text, daemon=True).start()

    def _handle_text(self):
        try:
            text = get_selected_text()
            log(f"取得テキスト長: {len(text)}")
            if not text or not text.strip():
                self.popup_manager.schedule(
                    self.popup_manager.show,
                    "（選択テキストを取得できませんでした）",
                    "・選択範囲を確実にハイライトしてからホットキーを押してください\n"
                    "・ターミナルでは Ctrl+Shift+C がコピー操作の場合があります\n"
                    "・どうしても取れない場合は Ctrl+Shift+S (範囲スクショ→OCR) を使ってください",
                )
                return
            translated = translate(text, self.config["source_lang"], self.config["target_lang"])
            log(f"翻訳完了: {translated[:50]}...")
            self.popup_manager.schedule(self.popup_manager.show, text, translated)
        except Exception as e:
            log("text handle error: " + traceback.format_exc())
            self.popup_manager.schedule(self.popup_manager.show, "(エラー)", f"処理中にエラー: {e}")
        finally:
            self._busy_text = False

    # --- 領域スクショ翻訳 ---
    def on_shot_hotkey(self):
        log(f"hotkey 発火: shot ({self.config['screenshot_hotkey']})")
        # 既にスクショモード中ならキャンセル扱い (再押下でモード解除)
        if self._busy_shot:
            if self._active_selector is not None:
                log("スクショモード中の再押下 → キャンセル")
                self._active_selector.cancel()
            return
        self._busy_shot = True
        threading.Thread(target=self._handle_shot, daemon=True).start()

    def _handle_shot(self):
        try:
            selector = RegionSelector(self.popup_manager.root)
            self._active_selector = selector
            bbox = selector.select()
            if not bbox:
                return
            # 少し待ってからキャプチャ（オーバーレイ閉じる猶予）
            time.sleep(0.12)
            img = ImageGrab.grab(bbox=bbox, all_screens=True)
            ocr_text = ocr_image(img, self.config["ocr_lang"])
            if not ocr_text or ocr_text.startswith("[OCR"):
                self.popup_manager.schedule(
                    self.popup_manager.show,
                    "(OCR失敗)",
                    ocr_text or "テキストが検出できませんでした。",
                )
                return
            translated = translate(ocr_text, self.config["source_lang"], self.config["target_lang"])
            self.popup_manager.schedule(self.popup_manager.show, ocr_text, translated)
        except Exception as e:
            log("shot handle error: " + traceback.format_exc())
            self.popup_manager.schedule(self.popup_manager.show, "(エラー)", f"スクショ翻訳中にエラー: {e}")
        finally:
            self._active_selector = None
            self._busy_shot = False

    # --- ホットキー登録 ---
    def _sanitize_hotkey(self, hk: str, fallback: str) -> str:
        """Ctrl/Alt/Win いずれかの修飾を持たないホットキーを安全なものに置換"""
        if not hk:
            return fallback
        parts = [p.strip() for p in hk.replace("-", "+").lower().split("+")]
        mods = {p for p in parts if p in ("ctrl", "alt", "win", "windows", "cmd")}
        if not mods:
            log(f"危険なホットキー '{hk}' を '{fallback}' に置換 (修飾キーなし)")
            return fallback
        return hk

    def register_hotkeys(self):
        for handle in (self._text_handle, self._shot_handle):
            if handle is not None:
                try:
                    keyboard.remove_hotkey(handle)
                except Exception:
                    pass
        self._text_handle = None
        self._shot_handle = None

        # 設定の危険値を救済
        safe_text = self._sanitize_hotkey(self.config.get("hotkey", ""), DEFAULT_CONFIG["hotkey"])
        safe_shot = self._sanitize_hotkey(self.config.get("screenshot_hotkey", ""), DEFAULT_CONFIG["screenshot_hotkey"])
        if safe_text != self.config.get("hotkey") or safe_shot != self.config.get("screenshot_hotkey"):
            self.config["hotkey"] = safe_text
            self.config["screenshot_hotkey"] = safe_shot
            save_config(self.config)

        try:
            self._text_handle = keyboard.add_hotkey(self.config["hotkey"], self.on_text_hotkey, suppress=False)
            log(f"text hotkey: {self.config['hotkey']}")
        except Exception as e:
            log(f"text hotkey 登録失敗: {e}")
        try:
            self._shot_handle = keyboard.add_hotkey(self.config["screenshot_hotkey"], self.on_shot_hotkey, suppress=False)
            log(f"shot hotkey: {self.config['screenshot_hotkey']}")
        except Exception as e:
            log(f"shot hotkey 登録失敗: {e}")

    # --- アイコン ---
    def make_icon_image(self) -> Image.Image:
        img = Image.new("RGB", (64, 64), color="#0078d4")
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 38)
        except Exception:
            font = ImageFont.load_default()
        d.text((14, 8), "訳", fill="white", font=font)
        return img

    # --- ホットキー変更ダイアログ ---
    def _hotkey_dialog(self, key_name: str, title: str):
        def _open():
            dlg = tk.Toplevel(self.popup_manager.root)
            dlg.title(title)
            dlg.attributes("-topmost", True)
            dlg.configure(bg="#1e1e1e")
            dlg.geometry("+400+300")

            tk.Label(
                dlg,
                text=f"{title}\n例: ctrl+shift+t, alt+q, ctrl+alt+space",
                bg="#1e1e1e",
                fg="#ffffff",
                font=(self.config["font_family"], 10),
                padx=12,
                pady=8,
                justify="left",
            ).pack()

            var = tk.StringVar(value=self.config[key_name])
            entry = tk.Entry(dlg, textvariable=var, font=(self.config["font_family"], 11), width=32)
            entry.pack(padx=12, pady=4)
            entry.focus_set()

            msg_var = tk.StringVar(value="")
            tk.Label(dlg, textvariable=msg_var, bg="#1e1e1e", fg="#ff8888",
                     font=(self.config["font_family"], 9)).pack(pady=(0, 4))

            def apply(_e=None):
                v = var.get().strip().lower()
                if not v:
                    msg_var.set("空にはできません")
                    return
                # 危険なホットキー (修飾なし or shift のみ) を弾く
                parts = [p.strip() for p in v.replace("-", "+").split("+")]
                mods = {p for p in parts if p in ("ctrl", "alt", "win", "windows", "cmd")}
                if not mods:
                    msg_var.set("Ctrl/Alt/Win いずれかの修飾キーを含めてください")
                    return
                try:
                    h = keyboard.add_hotkey(v, lambda: None)
                    keyboard.remove_hotkey(h)
                except Exception as e:
                    msg_var.set(f"無効な指定: {e}")
                    return
                self.config[key_name] = v
                save_config(self.config)
                self.register_hotkeys()
                dlg.destroy()

            btn = tk.Frame(dlg, bg="#1e1e1e")
            btn.pack(pady=8)
            tk.Button(btn, text="適用", width=10, command=apply).pack(side="left", padx=4)
            tk.Button(btn, text="キャンセル", width=10, command=dlg.destroy).pack(side="left", padx=4)
            dlg.bind("<Return>", apply)
            dlg.bind("<Escape>", lambda e: dlg.destroy())

        self.popup_manager.schedule(_open)

    def change_text_hotkey(self, _i=None, _it=None):
        self._hotkey_dialog("hotkey", "テキスト翻訳ホットキー")

    def change_shot_hotkey(self, _i=None, _it=None):
        self._hotkey_dialog("screenshot_hotkey", "スクショ翻訳ホットキー")

    def change_lang(self, _i=None, _it=None):
        def _open():
            dlg = tk.Toplevel(self.popup_manager.root)
            dlg.title("翻訳先言語")
            dlg.attributes("-topmost", True)
            dlg.configure(bg="#1e1e1e")
            dlg.geometry("+420+340")
            tk.Label(dlg, text="翻訳先言語コード (ja, en, ko, zh-CN, etc.)",
                     bg="#1e1e1e", fg="#ffffff",
                     font=(self.config["font_family"], 10), padx=12, pady=8).pack()
            var = tk.StringVar(value=self.config["target_lang"])
            entry = tk.Entry(dlg, textvariable=var, font=(self.config["font_family"], 11), width=16)
            entry.pack(padx=12, pady=6)
            entry.focus_set()

            def apply(_e=None):
                v = var.get().strip()
                if v:
                    self.config["target_lang"] = v
                    save_config(self.config)
                dlg.destroy()
            tk.Button(dlg, text="適用", command=apply).pack(pady=8)
            dlg.bind("<Return>", apply)
            dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.popup_manager.schedule(_open)

    def change_ocr_lang(self, _i=None, _it=None):
        def _open():
            dlg = tk.Toplevel(self.popup_manager.root)
            dlg.title("OCR 言語")
            dlg.attributes("-topmost", True)
            dlg.configure(bg="#1e1e1e")
            dlg.geometry("+420+340")
            tk.Label(dlg,
                     text="OCR 言語コード (en, ja, zh-Hans, ko, etc.)\nWindowsに該当言語パックが必要",
                     bg="#1e1e1e", fg="#ffffff",
                     font=(self.config["font_family"], 10), padx=12, pady=8, justify="left").pack()
            var = tk.StringVar(value=self.config["ocr_lang"])
            entry = tk.Entry(dlg, textvariable=var, font=(self.config["font_family"], 11), width=16)
            entry.pack(padx=12, pady=6)
            entry.focus_set()

            def apply(_e=None):
                v = var.get().strip()
                if v:
                    self.config["ocr_lang"] = v
                    save_config(self.config)
                dlg.destroy()
            tk.Button(dlg, text="適用", command=apply).pack(pady=8)
            dlg.bind("<Return>", apply)
            dlg.bind("<Escape>", lambda e: dlg.destroy())
        self.popup_manager.schedule(_open)

    def test_translate(self, _i=None, _it=None):
        sample = "This is a quick translation tool that shows Japanese popup."
        self.popup_manager.schedule(
            self.popup_manager.show,
            sample,
            translate(sample, dst=self.config["target_lang"]),
        )

    def open_config(self, _i=None, _it=None):
        try:
            os.startfile(CONFIG_PATH)
        except Exception as e:
            log(f"open config 失敗: {e}")

    def quit_app(self, _i=None, _it=None):
        log("終了")
        try:
            if self.icon:
                self.icon.stop()
        except Exception:
            pass
        try:
            self.popup_manager.root.after(0, self.popup_manager.root.destroy)
        except Exception:
            pass
        os._exit(0)

    def build_menu(self):
        return pystray.Menu(
            pystray.MenuItem(lambda _i: f"テキスト翻訳: {self.config['hotkey']}",
                             self.change_text_hotkey),
            pystray.MenuItem(lambda _i: f"スクショ翻訳: {self.config['screenshot_hotkey']}",
                             self.change_shot_hotkey),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(lambda _i: f"翻訳先言語: {self.config['target_lang']}",
                             self.change_lang),
            pystray.MenuItem(lambda _i: f"OCR言語: {self.config['ocr_lang']}",
                             self.change_ocr_lang),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("テスト翻訳", self.test_translate),
            pystray.MenuItem("設定ファイルを開く", self.open_config),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("終了", self.quit_app),
        )

    def run(self):
        log("起動")
        if not WINOCR_AVAILABLE:
            log("WARN: winocr 利用不可 — スクショ翻訳は無効です")
        self.register_hotkeys()
        self.icon = pystray.Icon(
            "quick_translate",
            self.make_icon_image(),
            "クイック翻訳",
            menu=self.build_menu(),
        )
        threading.Thread(target=self.icon.run, daemon=True).start()
        self.popup_manager.run()


def main():
    try:
        App().run()
    except Exception:
        log("fatal: " + traceback.format_exc())
        raise


if __name__ == "__main__":
    main()

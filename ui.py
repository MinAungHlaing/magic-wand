# ui.py — Magic Wand  |  KivyMD 1.2.0  |  Full rewrite v3
import json
import os
import threading

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.metrics import dp
from kivy.utils import platform, get_color_from_hex
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, Rectangle, RoundedRectangle

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.scrollview import MDScrollView
from kivymd.uix.button import MDRaisedButton, MDIconButton, MDFlatButton
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.fitimage import FitImage
from kivymd.uix.card import MDCard
from kivymd.uix.textfield import MDTextField
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.snackbar import MDSnackbar
from kivy.uix.recycleview import RecycleView
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.recycleboxlayout import RecycleBoxLayout

    
# ═══════════════════════════════════════════════════════════════
#  DESIGN TOKENS (Light Theme: White & Blue)
# ═══════════════════════════════════════════════════════════════
HEX_BG        = "#FFFFFF"  # Pure White Background
HEX_SURFACE   = "#F5F7FA"  # Light Grey-Blue for Cards
HEX_SURFACE2  = "#E1E8ED"  # Slightly darker for depth
HEX_SURFACE3  = "#D1D9E0"  # For active states
HEX_SIDEBAR   = "#FFFFFF"  # Sidebar matches main BG
HEX_BORDER    = "#D0D7DE"  # Soft border color
HEX_ACCENT    = "#007BFF"  # Primary Blue
HEX_ACCENT2   = "#0056B3"  # Darker Blue for hover/press
HEX_TEXT      = "#1F2328"  # Dark Charcoal for readability
HEX_DIM       = "#57606A"  # Muted grey for captions
HEX_KEY       = "#0969DA"  # Blue for keys
HEX_VAL       = "#1A7F37"  # Green for values (kept for success)
HEX_SUCCESS   = "#2DA44E"
HEX_ERROR     = "#CF222E"
HEX_CONSOLE   = "#F6F8FA"  # Light background for logs
HEX_ROW_ALT   = "#F0F3F6"  # Alternating row color
HEX_SCRIM     = "#00000066"

MAX_HISTORY   = 20
SIDEBAR_W     = 0.82   # fraction of screen width


# ═══════════════════════════════════════════════════════════════
#  HISTORY FILE  (persists across app restarts)
# ═══════════════════════════════════════════════════════════════
def _history_path():
    if platform == "android":
        from android.storage import app_storage_path  # type: ignore
        base = app_storage_path()
    else:
        base = os.path.expanduser("~")
    return os.path.join(base, ".magicwand_history.json")


def load_history():
    try:
        with open(_history_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        # data is a list of [label, params_dict]
        return [(item[0], item[1]) for item in data if len(item) == 2]
    except Exception:
        return []


def save_history(history):
    try:
        with open(_history_path(), "w", encoding="utf-8") as f:
            json.dump([[lbl, params] for lbl, params in history], f, indent=2)
    except Exception as e:
        print(f"[History] save error: {e}")


# ═══════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════
def haptic():
    if platform == "android":
        try:
            from plyer import vibrator
            vibrator.vibrate(0.04)
        except Exception:
            pass


def android_share(text):
    if platform == "android":
        try:
            from jnius import autoclass
            Intent = autoclass("android.content.Intent")
            Str    = autoclass("java.lang.String")
            i = Intent()
            i.setAction(Intent.ACTION_SEND)
            i.setType("text/plain")
            i.putExtra(Intent.EXTRA_TEXT, Str(text))
            chooser = Intent.createChooser(i, Str("Share via"))
            PA = autoclass("org.kivy.android.PythonActivity")
            PA.mActivity.startActivity(chooser)
        except Exception as e:
            print(f"Share error: {e}")
    else:
        Clipboard.copy(text)


def show_snackbar(msg):
    """KivyMD 1.2.0: must add MDLabel child, text= kwarg is invalid."""
    sb = MDSnackbar(
        snackbar_x=dp(12),
        snackbar_y=dp(24),
        size_hint_x=0.94,
        duration=2.0,
        radius=[dp(8), dp(8), dp(8), dp(8)],
    )
    sb.add_widget(MDLabel(
        text=msg,
        theme_text_color="Custom",
        text_color=get_color_from_hex(HEX_TEXT),
        font_style="Body2",
    ))
    sb.open()


# ═══════════════════════════════════════════════════════════════
#  PRIMITIVE WIDGETS
# ═══════════════════════════════════════════════════════════════
class Divider(Widget):
    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(1))
        super().__init__(**kw)
        with self.canvas:
            Color(*get_color_from_hex(HEX_BORDER))
            self._rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(pos=self._r, size=self._r)

    def _r(self, *_):
        self._rect.pos  = self.pos
        self._rect.size = self.size


class DragHandle(Widget):
    """Decorative pill — purely visual."""
    def __init__(self, **kw):
        kw.setdefault("size_hint_y", None)
        kw.setdefault("height", dp(16))
        super().__init__(**kw)
        with self.canvas:
            Color(*get_color_from_hex(HEX_BORDER))
            self._pill = RoundedRectangle(size=(dp(36), dp(4)), radius=[dp(2)])
        self.bind(pos=self._r, size=self._r)

    def _r(self, *_):
        cx = self.x + self.width / 2 - dp(18)
        cy = self.y + self.height / 2 - dp(2)
        self._pill.pos  = (cx, cy)
        self._pill.size = (dp(36), dp(4))



# ═══════════════════════════════════════════════════════════════
#  RECYCLE ROW  — one reusable widget instance per visible row
#  RecycleView swaps data in/out without creating new widgets
# ═══════════════════════════════════════════════════════════════
class ParamRecycleRow(RecycleDataViewBehavior, MDBoxLayout):
    """
    Single param row used by ParamRecycleView.
    RecycleView calls refresh_view_attrs() to populate data —
    no new widget objects are created per row, only reused.
    """
    def __init__(self, **kw):
        super().__init__(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(48),
            padding=[dp(14), dp(4), dp(8), dp(4)],
            spacing=dp(6),
            **kw,
        )
        self._key = ""
        self._val = ""

        with self.canvas.before:
            self._bg_color = Color(0, 0, 0, 0)
            self._bg_rect  = Rectangle(pos=self.pos, size=self.size)
        self.bind(
            pos=lambda *_: setattr(self._bg_rect, "pos", self.pos),
            size=lambda *_: setattr(self._bg_rect, "size", self.size),
        )

        self._k_lbl = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_KEY),
            font_style="Caption",
            bold=True,
            size_hint_x=0.38,
            halign="left",
            valign="center",
        )
        self._v_lbl = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_VAL),
            font_style="Caption",
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        self._cp_btn = MDIconButton(
            icon="content-copy",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_DIM),
            size_hint=(None, None),
            size=(dp(36), dp(36)),
        )
        self._cp_btn.bind(on_release=self._copy)
        self.add_widget(self._k_lbl)
        self.add_widget(self._v_lbl)
        self.add_widget(self._cp_btn)

    def refresh_view_attrs(self, rv, index, data):
        """Called by RecycleView to bind data to this widget instance."""
        self._key = data["key"]
        self._val = data["val"]
        self._k_lbl.text = self._key
        self._v_lbl.text = self._val
        # Alternating row tint
        c = get_color_from_hex(HEX_ROW_ALT) if data.get("alt") else (0, 0, 0, 0)
        self._bg_color.rgba = c
        return super().refresh_view_attrs(rv, index, data)

    def _copy(self, *_):
        Clipboard.copy(f"{self._key}={self._val}")
        haptic()
        show_snackbar(f"Copied  {self._key}")


class ParamRecycleView(RecycleView):
    """
    Thin wrapper around RecycleView pre-configured for param rows.
    Call .load(params_dict) to populate.
    """
    def __init__(self, **kw):
        super().__init__(**kw)
        layout = RecycleBoxLayout(
            default_size=(None, dp(48)),
            default_size_hint=(1, None),
            size_hint_y=None,
            orientation="vertical",
        )
        layout.bind(minimum_height=layout.setter("height"))
        self.add_widget(layout)
        self.viewclass = "ParamRecycleRow"
        self.data = []

    def load(self, params: dict):
        self.data = [
            {"key": k, "val": str(v), "alt": (i % 2 == 1)}
            for i, (k, v) in enumerate(params.items())
        ]



class ParamRow(MDBoxLayout):
    def __init__(self, key, value, alt=False, **kw):
        super().__init__(
            orientation="horizontal",
            adaptive_height=True,
            padding=[dp(14), dp(10), dp(8), dp(10)],
            spacing=dp(6),
            **kw,
        )
        self.key   = key
        self.value = value

        if alt:
            with self.canvas.before:
                Color(*get_color_from_hex(HEX_ROW_ALT))
                self._bg = Rectangle(pos=self.pos, size=self.size)
            self.bind(
                pos=lambda *_: setattr(self._bg, "pos", self.pos),
                size=lambda *_: setattr(self._bg, "size", self.size),
            )

        key_lbl = MDLabel(
            text=key,
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_KEY),
            font_style="Body2",
            bold=True,
            size_hint_x=0.32,
            halign="left",
            valign="middle",
            adaptive_height=True,
        )
        sep = MDLabel(
            text="=",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_BORDER),
            size_hint_x=None,
            width=dp(16),
            halign="center",
            valign="middle",
            adaptive_height=True,
        )
        val_lbl = MDLabel(
            text=value,
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_VAL),
            font_style="Caption",
            size_hint_x=1,
            halign="left",
            valign="middle",
            adaptive_height=True,
        )
        copy_btn = MDIconButton(
            icon="content-copy",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
            size_hint=(None, None),
            size=(dp(36), dp(36)),
        )
        copy_btn.bind(on_release=self._copy)

        self.add_widget(key_lbl)
        self.add_widget(sep)
        self.add_widget(val_lbl)
        self.add_widget(copy_btn)

    def _copy(self, *_):
        Clipboard.copy(f"{self.key}={self.value}")
        haptic()
        show_snackbar(f"Copied  {self.key}")


# ═══════════════════════════════════════════════════════════════
#  LOG WIDGET  (used inside sidebar)
# ═══════════════════════════════════════════════════════════════
class LogView(MDScrollView):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._lbl = MDLabel(
            text="[color=#1a2a1a]— ready —[/color]",
            markup=True,
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Caption",
            size_hint_y=None,
            halign="left",
            valign="top",
            adaptive_height=True,
            padding=[dp(12), dp(8)],
        )
        self._lbl.bind(texture_size=self._lbl.setter("size"))
        self.add_widget(self._lbl)

    def log(self, line):
        cur = self._lbl.text
        if "— ready —" in cur:
            cur = ""
        self._lbl.text = (cur + "\n" + line).strip()
        Clock.schedule_once(lambda dt: setattr(self, "scroll_y", 0), 0.05)

    def clear(self):
        self._lbl.text = "[color=#1a2a1a]— ready —[/color]"


# ═══════════════════════════════════════════════════════════════
#  SIDEBAR  (slides in from right)
# ═══════════════════════════════════════════════════════════════
class Sidebar(FloatLayout):
    """
    Fullscreen float that overlays the app.
    - Scrim on the left (tap to close)
    - Panel on the right with History / Log tabs
    """
    def __init__(self, log_view, **kw):
        super().__init__(**kw)
        self.log_view        = log_view
        self._history        = []
        self._visible        = False
        self._anim           = None
        self._active_tab     = "history"

        # Scrim — plain Widget with manual canvas + touch handling
        # Using a Button here blocks all touches even when sidebar is hidden.
        self._scrim = Widget(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
        )
        with self._scrim.canvas:
            self._scrim_color = Color(0, 0, 0, 0)
            self._scrim_rect  = Rectangle(
                pos=self._scrim.pos, size=self._scrim.size
            )
        self._scrim.bind(
            pos=lambda inst, v: setattr(self._scrim_rect, "pos", v),
            size=lambda inst, v: setattr(self._scrim_rect, "size", v),
        )
        self.add_widget(self._scrim)

        # Panel card — starts off-screen to the RIGHT (right:2 = beyond right edge)
        self._panel = MDCard(
            orientation="vertical",
            size_hint=(SIDEBAR_W, 1),
            pos_hint={"right": 2, "y": 0},   # off-screen right
            md_bg_color=get_color_from_hex(HEX_SIDEBAR),
            line_color=get_color_from_hex(HEX_BORDER),
            line_width=dp(1),
            radius=[dp(16), dp(0), dp(0), dp(16)],
            elevation=0,
            padding=[0, 0, 0, 0],
            spacing=0,
        )
        self.add_widget(self._panel)
        self._build_panel()

        # Hidden by default — opacity=0 and _visible=False means
        # on_touch_down returns False so no touches are consumed
        self.opacity = 0

    def _build_panel(self):
        # ── Panel header ─────────────────────────────────────────
        hdr = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(60),
            padding=[dp(16), dp(12), dp(8), dp(8)],
            spacing=dp(8),
            md_bg_color=get_color_from_hex(HEX_SURFACE),
        )
        title = MDLabel(
            text="Menu",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_TEXT),
            font_style="H6",
            bold=True,
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        close_btn = MDIconButton(
            icon="close",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_DIM),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        close_btn.bind(on_release=lambda *_: self.close())
        hdr.add_widget(title)
        hdr.add_widget(close_btn)
        self._panel.add_widget(hdr)
        self._panel.add_widget(Divider())

        # ── Tab bar ───────────────────────────────────────────────
        tab_bar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(8), dp(4), dp(8), dp(0)],
            spacing=dp(8),
        )
        self._tab_history = self._make_tab("history",    "History", active=True)
        self._tab_log     = self._make_tab("log",        "Log",     active=False)
        tab_bar.add_widget(self._tab_history["btn"])
        tab_bar.add_widget(self._tab_log["btn"])
        self._panel.add_widget(tab_bar)
        self._panel.add_widget(Divider())

        # ── Content area ──────────────────────────────────────────
        self._content = MDBoxLayout(
            orientation="vertical",
            size_hint_y=1,
            padding=[0, 0, 0, 0],
        )
        self._panel.add_widget(self._content)

        # Build all three panes once — never rebuilt again
        self._history_pane = self._build_history_pane()
        self._log_pane     = self._build_log_pane()
        self._detail_pane  = self._build_detail_pane()

        self._show_tab("history")

    def _make_tab(self, key, label, active):
        btn = MDRaisedButton(
            text=label,
            size_hint_x=1,
            size_hint_y=None,
            height=dp(36),
            md_bg_color=get_color_from_hex(
                HEX_ACCENT if active else HEX_SURFACE2
            ),
            elevation=0 if not active else 0,
        )
        btn.bind(on_release=lambda *_: self._show_tab(key))
        return {"btn": btn, "key": key}

    def _build_history_pane(self):
        pane = MDBoxLayout(
            orientation="vertical",
            size_hint_y=1,
        )
        # Toolbar: title + clear button
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(16), dp(4), dp(8), dp(4)],
        )
        hist_title = MDLabel(
            text="Recent fetches",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Caption",
            bold=True,
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        clear_btn = MDFlatButton(
            text="Clear all",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_ERROR),
            size_hint_x=None,
        )
        clear_btn.bind(on_release=self._clear_history)
        toolbar.add_widget(hist_title)
        toolbar.add_widget(clear_btn)
        pane.add_widget(toolbar)
        pane.add_widget(Divider())

        self._hist_scroll = MDScrollView(size_hint_y=1)
        self._hist_list   = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=0,
        )
        self._hist_list.bind(minimum_height=self._hist_list.setter("height"))
        self._hist_scroll.add_widget(self._hist_list)
        pane.add_widget(self._hist_scroll)
        return pane

    def _build_log_pane(self):
        pane = MDBoxLayout(
            orientation="vertical",
            size_hint_y=1,
            padding=[0, dp(4), 0, 0],
        )
        toolbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(16), dp(4), dp(8), dp(4)],
        )
        log_title = MDLabel(
            text="Fetch log",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Caption",
            bold=True,
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        clear_log_btn = MDFlatButton(
            text="Clear",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_ERROR),
            size_hint_x=None,
        )
        clear_log_btn.bind(on_release=lambda *_: self.log_view.clear())
        toolbar.add_widget(log_title)
        toolbar.add_widget(clear_log_btn)
        pane.add_widget(toolbar)
        pane.add_widget(Divider())
        self.log_view.size_hint = (1, 1)
        pane.add_widget(self.log_view)
        return pane

    def _build_detail_pane(self):
        """
        Pre-built detail view shell. Built exactly once at startup.
        _show_params_in_sidebar only updates labels and loads rv data —
        zero widget creation on tap, zero lag.
        """
        pane = MDBoxLayout(orientation="vertical", size_hint_y=1)

        hdr = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(44),
            padding=[dp(8), dp(4), dp(8), dp(4)],
            spacing=dp(4),
        )
        back_btn = MDIconButton(
            icon="arrow-left",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
            size_hint=(None, None),
            size=(dp(36), dp(36)),
        )
        back_btn.bind(on_release=lambda *_: self._show_tab("history"))

        self._detail_title = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_TEXT),
            font_style="Body2",
            bold=True,
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        self._detail_copy_btn = MDIconButton(
            icon="content-copy",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
            size_hint=(None, None),
            size=(dp(36), dp(36)),
        )
        # copy callback set dynamically in _show_params_in_sidebar
        hdr.add_widget(back_btn)
        hdr.add_widget(self._detail_title)
        hdr.add_widget(self._detail_copy_btn)
        pane.add_widget(hdr)
        pane.add_widget(Divider())

        self._detail_rv = ParamRecycleView(size_hint=(1, 1))
        pane.add_widget(self._detail_rv)
        return pane

    def _show_tab(self, key):
        self._active_tab = key
        self._content.clear_widgets()
        for tab in [self._tab_history, self._tab_log]:
            tab["btn"].md_bg_color = get_color_from_hex(
                HEX_ACCENT if tab["key"] == key else HEX_SURFACE2
            )
        if key == "history":
            self._content.add_widget(self._history_pane)
        elif key == "log":
            self._content.add_widget(self._log_pane)
        elif key == "detail":
            self._content.add_widget(self._detail_pane)

    # ── History management ────────────────────────────────────────
    def set_history(self, history):
        self._history = history
        self._rebuild_hist_list()

    def add_entry(self, label, params):
        # Auto-name: use ssid field if present, else use label
        ssid = params.get("ssid") or params.get("SSID") or params.get("Ssid")
        name = ssid if ssid else label
        self._history.insert(0, (name, params))
        if len(self._history) > MAX_HISTORY:
            self._history.pop()
        save_history(self._history)
        self._rebuild_hist_list()

    def _clear_history(self, *_):
        self._history.clear()
        save_history(self._history)
        self._rebuild_hist_list()
        show_snackbar("History cleared")

    def _rebuild_hist_list(self):
        self._hist_list.clear_widgets()
        if not self._history:
            empty = MDLabel(
                text="No history yet",
                theme_text_color="Custom",
                text_color=get_color_from_hex(HEX_DIM),
                font_style="Body2",
                halign="center",
                size_hint_y=None,
                height=dp(80),
            )
            self._hist_list.add_widget(empty)
            return

        for i, (lbl_text, params) in enumerate(self._history):
            row = self._make_hist_row(i, lbl_text, params)
            self._hist_list.add_widget(row)
            self._hist_list.add_widget(Divider())

    def _make_hist_row(self, idx, lbl_text, params):
        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(56),
            padding=[dp(14), dp(4), dp(4), dp(4)],
            spacing=dp(2),
        )
        num = MDLabel(
            text=str(idx + 1),
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_ACCENT),
            bold=True,
            font_style="Caption",
            size_hint_x=None,
            width=dp(24),
            halign="center",
            valign="center",
        )
        lbl = MDLabel(
            text=lbl_text,
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_TEXT),
            font_style="Caption",
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        copy_btn = MDIconButton(
            icon="content-copy",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        copy_btn.bind(on_release=lambda b, p=params: self._copy_params(p))

        view_btn = MDIconButton(
            icon="eye",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_SUCCESS),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        view_btn.bind(on_release=lambda b, n=lbl_text, p=params: self._show_params_in_sidebar(n, p))

        row.add_widget(num)
        row.add_widget(lbl)
        row.add_widget(copy_btn)
        row.add_widget(view_btn)
        return row

    def _show_params_in_sidebar(self, name, params):
        """Zero-lag: update pre-built shell with new data, no widget creation."""
        self._detail_title.text = name
        # Rebind copy button to current params
        if hasattr(self, "_detail_copy_cb"):
            self._detail_copy_btn.unbind(on_release=self._detail_copy_cb)
        self._detail_copy_cb = lambda *_: self._copy_params(params)
        self._detail_copy_btn.bind(on_release=self._detail_copy_cb)
        self._detail_rv.load(params)
        self._content.clear_widgets()
        self._content.add_widget(self._detail_pane)

    def _copy_params(self, params):
        Clipboard.copy("\n".join(f"{k}={v}" for k, v in params.items()))
        haptic()
        show_snackbar("Parameters copied")

    # ── Touch: only consume when visible ─────────────────────────
    def on_touch_down(self, touch):
        if not self._visible:
            return False   # pass through — sidebar is hidden
        # If touch is on the scrim (left of panel), close and consume
        if not self._panel.collide_point(*touch.pos):
            self.close()
            return True
        # Let panel children handle it
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if not self._visible:
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if not self._visible:
            return False
        return super().on_touch_up(touch)

    # ── Open / close animation ────────────────────────────────────
    def open(self):
        if self._visible:
            return
        self._visible = True
        self.opacity  = 1
        # Animate scrim alpha via canvas Color object
        Animation(a=0.55, duration=0.25).start(self._scrim_color)
        # Panel slides in from right
        if self._anim:
            self._anim.cancel(self._panel)
        self._anim = Animation(pos_hint={"right": 1, "y": 0}, duration=0.28, t="out_cubic")
        self._anim.start(self._panel)

    def close(self):
        if not self._visible:
            return
        self._visible = False
        Animation(a=0, duration=0.2).start(self._scrim_color)
        if self._anim:
            self._anim.cancel(self._panel)
        self._anim = Animation(pos_hint={"right": 2, "y": 0}, duration=0.22, t="in_cubic")
        self._anim.bind(on_complete=lambda *_: self._after_close())
        self._anim.start(self._panel)

    def _after_close(self):
        self.opacity = 0

    def switch_to_log(self):
        self._show_tab("log")


# ═══════════════════════════════════════════════════════════════
#  MAIN SCREEN
# ═══════════════════════════════════════════════════════════════
class MagicHandScreen(FloatLayout):
    def __init__(self, **kw):
        super().__init__(**kw)
        self._last_params      = {}
        self._prog_ev          = None
        self._build()

    def _build(self):
        # ── Root vertical stack ──────────────────────────────────
        root = MDBoxLayout(
            orientation="vertical",
            md_bg_color=get_color_from_hex(HEX_BG),
            size_hint=(1, 1),
        )
        self.add_widget(root)

        # ── Shared log view (lives in sidebar) ───────────────────
        self._log_view = LogView(
            size_hint_y=None,
            height=dp(200),
        )

        # ── Sidebar (overlaid above root) ─────────────────────────
        self._sidebar = Sidebar(
            log_view=self._log_view,
            size_hint=(1, 1),
        )

        # Load persisted history into sidebar
        history = load_history()
        self._sidebar.set_history(history)

        # ── Top bar ───────────────────────────────────────────────
        topbar = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(72),
            padding=[dp(20), dp(10), dp(16), dp(8)],
            spacing=dp(12),
            md_bg_color=get_color_from_hex(HEX_BG),
        )
        with topbar.canvas.after:
            Color(*get_color_from_hex(HEX_BORDER))
            self._topbar_line = Rectangle(pos=topbar.pos, size=(topbar.width, dp(1)))
        topbar.bind(
            pos=lambda inst, v: setattr(self._topbar_line, "pos", (v[0], v[1])),
            size=lambda inst, v: setattr(self._topbar_line, "size", (v[0], dp(1))),
        )

        # Logo: canvas-drawn circle with icon — avoids MDIcon glyph offset
        logo_badge = MDBoxLayout(
            size_hint=(None, None),
            size=(dp(44), dp(44)),
        )
        with logo_badge.canvas.before:
            Color(*get_color_from_hex(HEX_SURFACE2))
            RoundedRectangle(
                pos=logo_badge.pos,
                size=logo_badge.size,
                radius=[dp(22)],
            )
        # Bind so the circle follows the widget position
        def _update_circle(inst, *_):
            inst.canvas.before.clear()
            with inst.canvas.before:
                Color(*get_color_from_hex(HEX_SURFACE2))
                RoundedRectangle(
                    pos=inst.pos,
                    size=inst.size,
                    radius=[dp(22)],
                )
        logo_badge.bind(pos=_update_circle, size=_update_circle)
        # This replaces the old icon with your image
        logo_image = FitImage(
            source="wand_logo.png",  # Make sure your file is named exactly this
            size_hint=(None, None),
            size=(dp(32), dp(32)),   # A bit smaller than the circle for a clean look
            radius=[dp(16),],        # This keeps the image circular
        )
        
        # This centers the image inside the badge
        logo_badge.padding = [dp(6), dp(6), dp(6), dp(6)] 
        logo_badge.add_widget(logo_image)
        
        title_col = MDBoxLayout(
            orientation="vertical",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(52),
            spacing=0,
        )
        t1 = MDLabel(
            text="Magic Wand",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_TEXT),
            font_style="H6",
            bold=True,
            size_hint_y=None,
            height=dp(30),
            halign="left",
            valign="center",
        )
        t2 = MDLabel(
            text="Ruijie Router's Parameter Fetcher",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Caption",
            size_hint_y=None,
            height=dp(22),
            halign="left",
            valign="center",
        )
        title_col.add_widget(t1)
        title_col.add_widget(t2)

        # Menu icon (replaces History button)
        menu_btn = MDIconButton(
            icon="menu",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_TEXT),
            size_hint=(None, None),
            size=(dp(44), dp(44)),
        )
        menu_btn.bind(on_release=lambda *_: self._sidebar.open())

        topbar.add_widget(logo_badge)
        topbar.add_widget(title_col)
        topbar.add_widget(menu_btn)
        root.add_widget(topbar)

        # ── Scrollable body ───────────────────────────────────────
        body_scroll = MDScrollView(size_hint_y=1)
        body = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            padding=[dp(16), dp(16), dp(16), dp(24)],
            spacing=dp(14),
        )
        body_scroll.add_widget(body)
        root.add_widget(body_scroll)

        # ── Input card ────────────────────────────────────────────
        input_card = MDCard(
            orientation="vertical",
            padding=[dp(16), dp(16), dp(16), dp(16)],
            spacing=dp(12),
            adaptive_height=True,
            md_bg_color=get_color_from_hex(HEX_SURFACE),
            line_color=get_color_from_hex(HEX_BORDER),
            line_width=dp(1),
            radius=[dp(20), dp(20), dp(20), dp(20)],
            elevation=0,
        )

        self.url_input = MDTextField(
            text="http://neverssl.com/",
            hint_text="Enter URL",
            mode="rectangle",
            icon_left="web",
        )

        self.fetch_btn = MDRaisedButton(
            text="  Fetch Parameters",
            size_hint_x=1,
            size_hint_y=None,
            height=dp(52),
            md_bg_color=get_color_from_hex(HEX_ACCENT),
            elevation=0,
        )
        self.fetch_btn.bind(on_release=self._on_fetch)

        input_card.add_widget(self.url_input)
        input_card.add_widget(self.fetch_btn)
        body.add_widget(input_card)

        # ── Progress bar ──────────────────────────────────────────
        self.progress = MDProgressBar(
            size_hint_x=1,
            size_hint_y=None,
            height=dp(3),
            opacity=0,
            value=0,
        )
        body.add_widget(self.progress)

        # ── Placeholder card ──────────────────────────────────────
        self._placeholder = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(110),
            padding=[dp(16), dp(20)],
            md_bg_color=get_color_from_hex(HEX_SURFACE),
            line_color=get_color_from_hex(HEX_BORDER),
            line_width=dp(1),
            radius=[dp(20), dp(20), dp(20), dp(20)],
            elevation=0,
            opacity=0.45,
        )
        ph_inner = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=dp(8),
        )
        ph_icon = MDIcon(
            icon="text-search",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_size=dp(30),
            size_hint=(None, None),
            size=(dp(40), dp(40)),
        )
        ph_lbl = MDLabel(
            text="Results will appear here",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Body2",
            halign="center",
            adaptive_height=True,
        )
        ph_inner.add_widget(ph_icon)
        ph_inner.add_widget(ph_lbl)
        self._placeholder.add_widget(ph_inner)
        body.add_widget(self._placeholder)

        # ── Result card ───────────────────────────────────────────
        self.result_card = MDCard(
            orientation="vertical",
            padding=[dp(0), dp(0), dp(0), dp(4)],
            spacing=dp(0),
            adaptive_height=True,
            md_bg_color=get_color_from_hex(HEX_SURFACE),
            line_color=get_color_from_hex(HEX_BORDER),
            line_width=dp(1),
            radius=[dp(20), dp(20), dp(20), dp(20)],
            elevation=0,
            opacity=0,
            size_hint_y=None,
            height=0,
        )

        res_hdr = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            padding=[dp(16), dp(4), dp(8), dp(4)],
            spacing=dp(4),
        )
        res_title = MDLabel(
            text="Parameters",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_TEXT),
            font_style="H6",
            bold=True,
            size_hint_x=1,
            halign="left",
            valign="center",
        )
        self.count_lbl = MDLabel(
            text="",
            theme_text_color="Custom",
            text_color=get_color_from_hex(HEX_DIM),
            font_style="Caption",
            size_hint_x=None,
            width=dp(56),
            halign="right",
            valign="center",
        )
        copy_all_btn = MDIconButton(
            icon="content-copy",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
        )
        copy_all_btn.bind(on_release=self._copy_all)

        share_btn = MDIconButton(
            icon="share-variant",
            theme_icon_color="Custom",
            icon_color=get_color_from_hex(HEX_ACCENT),
        )
        share_btn.bind(on_release=self._share)

        res_hdr.add_widget(res_title)
        res_hdr.add_widget(self.count_lbl)
        res_hdr.add_widget(copy_all_btn)
        res_hdr.add_widget(share_btn)
        self.result_card.add_widget(res_hdr)
        self.result_card.add_widget(Divider())

        self._param_list = MDBoxLayout(
            orientation="vertical",
            adaptive_height=True,
            spacing=0,
        )
        self.result_card.add_widget(self._param_list)
        body.add_widget(self.result_card)

        # Sidebar is last — renders on top of everything
        self.add_widget(self._sidebar)

    # ── Fetch ─────────────────────────────────────────────────────
    def _on_fetch(self, *_):
        self.fetch_btn.disabled = True
        self._param_list.clear_widgets()
        self.result_card.opacity = 0
        self.result_card.height  = 0
        self._placeholder.opacity = 0.2
        self._placeholder.height  = dp(110)
        self._start_progress()
        url = self.url_input.text.strip() or "http://neverssl.com/"
        self._sidebar.switch_to_log()
        threading.Thread(
            target=self._fetch_thread, args=(url,), daemon=True
        ).start()

    def _start_progress(self):
        self.progress.opacity = 1
        self.progress.value   = 0
        self._prog_ev = Clock.schedule_interval(self._tick, 0.06)

    def _tick(self, dt):
        if self.progress.value < 88:
            self.progress.value += 1.8

    def _fetch_thread(self, url):
        import getparams as gp
        _orig = gp.requests.get

        def patched(u, **kw):
            r = _orig(u, **kw)
            loc  = r.headers.get("location", "-")
            line = (
                f"[color=#3a7a3a]>[/color] "
                f"[color=#aaaaaa]{r.status_code} {r.reason}[/color]  "
                f"[color=#558877]{loc[:55]}[/color]"
            )
            Clock.schedule_once(lambda dt: self._log_view.log(line))
            return r

        gp.requests.get = patched
        params = gp.get_params(initial_url=url)
        gp.requests.get = _orig
        Clock.schedule_once(lambda dt: self._update_ui(params, url))

    def _update_ui(self, params, url):
        if self._prog_ev:
            self._prog_ev.cancel()
        (Animation(value=100, duration=0.12) +
         Animation(opacity=0, duration=0.3)).start(self.progress)
        self.fetch_btn.disabled = False

        if not params:
            self._log_view.log(f"[color={HEX_ERROR}]✗ No params found.[/color]")
            # Restore placeholder
            self._placeholder.opacity = 0.45
            show_snackbar("No parameters found")
            return

        self._last_params = params
        self.count_lbl.text = f"{len(params)} keys"

        for i, (k, v) in enumerate(params.items()):
            self._param_list.add_widget(ParamRow(k, v, alt=(i % 2 == 1)))
            if i < len(params) - 1:
                self._param_list.add_widget(Divider())

        Clock.schedule_once(self._reveal_results, 0.05)

        label = (
            f"{url[:38]}{'…' if len(url) > 38 else ''}"
            f"  [{len(params)} params]"
        )
        self._sidebar.add_entry(label, dict(params))

        self._log_view.log(
            f"[color={HEX_SUCCESS}]✓ {len(params)} params extracted[/color]"
        )

    def _reveal_results(self, dt):
        # Collapse & hide placeholder, then reveal result card in same spot
        anim_ph = Animation(opacity=0, height=0, duration=0.2)
        anim_ph.start(self._placeholder)

        self.result_card.size_hint_y = None
        self.result_card.height = self.result_card.minimum_height
        Animation(opacity=1, duration=0.35).start(self.result_card)

    # ── Actions ───────────────────────────────────────────────────
    def _copy_all(self, *_):
        if not self._last_params:
            return
        Clipboard.copy("\n".join(f"{k}={v}" for k, v in self._last_params.items()))
        haptic()
        show_snackbar("All parameters copied")

    def _share(self, *_):
        if not self._last_params:
            return
        android_share("\n".join(f"{k}={v}" for k, v in self._last_params.items()))


# ═══════════════════════════════════════════════════════════════
#  APP
# ═══════════════════════════════════════════════════════════════
class MagicHandApp(MDApp):
    title = "Magic Wand"

    def build(self):
        self.theme_cls.theme_style     = "Light"
        self.theme_cls.primary_palette = "Blue"
        return MagicHandScreen()

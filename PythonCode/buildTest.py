# buildTest.py
import tkinter as tk
import tkinter.font as tkfont
import os
from decimal import Decimal, ROUND_HALF_UP
import time
from playsound import playsound
import simpleaudio as sa
import math
try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

# -------------------------
# Config / paths
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_INTER = os.path.join(ASSETS_DIR, "Inter", "static", "Inter_28pt-ExtraBold.ttf")
SCREEN_W, SCREEN_H = 1024, 600 

class AdminPanel(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#222", bd=4, relief="raised")
        self.controller = controller

        self.place(relx=0.5, rely=0.5, anchor="center")
        self.place_forget()  # hidden by default

        self.build_ui()

class OutlinedText:
    def __init__(self, canvas, x, y, text="", font=("Arial", 24), fill="#FFF",
                 stroke=1, stroke_fill="#000", shadow=None, mode="pillow",
                 anchor="center", tag=None, pillow_font_path=FONT_INTER):
        self.canvas = canvas
        self.x = x
        self.y = y
        self.text = str(text)
        self.font = font
        self.fill = fill
        self.stroke = int(stroke or 0)
        self.stroke_fill = stroke_fill
        self.shadow = shadow
        self.anchor = anchor
        self.tag = tag
        # choose mode (fall back to canvas if Pillow missing)
        if mode == "pillow" and not _HAS_PIL:
            mode = "canvas"
        self.mode = mode
        self.pillow_font_path = pillow_font_path
        self._ids = []      # canvas item ids (for canvas-mode) or [image_id] for pillow-mode
        self._photo = None  # hold PhotoImage for pillow mode
        self._pillow_font = None
        if self.mode == "pillow":
            self._prepare_pillow_font()
            self._render_pillow()
        else:
            self._render_canvas()

    # Pillow font loader
    def _prepare_pillow_font(self):
        if not _HAS_PIL:
            return

        # determine requested size
        size = int(self.font[1]) if isinstance(self.font, (list, tuple)) and len(self.font) >= 2 else 24

        # 1) If user provided a direct path, try that first and log
        if self.pillow_font_path:
            try:
                self._pillow_font = ImageFont.truetype(self.pillow_font_path, size)
                print(f"[OutlinedText] Loaded pillow font from explicit path: {self.pillow_font_path} size={size}")
                return
            except Exception as e:
                print(f"[OutlinedText] Failed to load pillow_font_path '{self.pillow_font_path}': {e}")
                # fallthrough to attempt to find similar filenames in same dir

        # 2) Try to resolve family name (e.g. "Inter") to some local file
        fam = None
        if isinstance(self.font, (list, tuple)) and len(self.font) >= 1:
            fam = str(self.font[0])

        # If family present, try a few predictable filenames or scan same folder as pillow_font_path
        if fam:
            # try simple family.ttf first
            candidates = [f"{fam}.ttf", f"{fam}.TTF", f"{fam}.otf"]
            for cand in candidates:
                try:
                    self._pillow_font = ImageFont.truetype(cand, size)
                    print(f"[OutlinedText] Loaded pillow font by candidate name: {cand} size={size}")
                    return
                except Exception:
                    pass

            # If user gave pillow_font_path earlier (but failed), search that directory for files containing fam
            if self.pillow_font_path:
                try:
                    d = os.path.dirname(self.pillow_font_path)
                    if d and os.path.isdir(d):
                        for fname in os.listdir(d):
                            if fam.lower() in fname.lower() and fname.lower().endswith((".ttf", ".otf")):
                                fp = os.path.join(d, fname)
                                try:
                                    self._pillow_font = ImageFont.truetype(fp, size)
                                    print(f"[OutlinedText] Loaded pillow font by scanning dir: {fp} size={size}")
                                    return
                                except Exception as e:
                                    print(f"[OutlinedText] Tried {fp} but failed: {e}")
                except Exception as e:
                    print(f"[OutlinedText] Dir-scan for family fonts failed: {e}")

        # 3) Last resort: try truetype by family (may or may not exist on system)
        try:
            if fam:
                self._pillow_font = ImageFont.truetype(fam, size)
                print(f"[OutlinedText] Loaded pillow font by family name: {fam} size={size}")
                return
        except Exception as e:
            print(f"[OutlinedText] truetype by family '{fam}' failed: {e}")

        # 4) fallback to default and log how bad it will look
        print("[OutlinedText] Falling back to ImageFont.load_default() (tiny font).")
        self._pillow_font = ImageFont.load_default()

    # Pillow render (makes PhotoImage and places on canvas)
    def _render_pillow(self):
        if not _HAS_PIL:
            return self._render_canvas()
        if self._pillow_font is None:
            self._prepare_pillow_font()

        font = self._pillow_font
        stroke_w = max(0, int(self.stroke or 0))
        # measure text
        dummy = Image.new("RGBA", (1,1), (0,0,0,0))
        draw = ImageDraw.Draw(dummy)
        try:
            bbox = draw.textbbox((0,0), self.text, font=font, stroke_width=stroke_w)
            w = bbox[2] - bbox[0]; h = bbox[3] - bbox[1]
        except Exception:
            w, h = draw.textsize(self.text, font=font)
        pad = stroke_w + 4
        sx = pad; sy = pad
        if self.shadow:
            sx += abs(self.shadow[0]); sy += abs(self.shadow[1])
        W = max(1, w + pad*2 + 2); H = max(1, h + pad*2 + 2)
        img = Image.new("RGBA", (W, H), (0,0,0,0))
        draw = ImageDraw.Draw(img)
        if self.shadow:
            dx, dy, scol = self.shadow
            draw.text((sx+dx, sy+dy), self.text, font=font, fill=scol)
        draw.text((sx, sy), self.text, font=font, fill=self.fill,
                  stroke_width=stroke_w, stroke_fill=self.stroke_fill)
        self._photo = ImageTk.PhotoImage(img)
        # anchor adjustments (center, nw, etc.)
        ax, ay = 0, 0
        if self.anchor == "center":
            ax = W//2; ay = H//2
        elif self.anchor == "n":
            ax = W//2; ay = 0
        elif self.anchor == "s":
            ax = W//2; ay = H
        elif self.anchor == "e":
            ax = W; ay = H//2
        elif self.anchor == "w":
            ax = 0; ay = H//2
        canvas_x = int(self.x - ax); canvas_y = int(self.y - ay)
        if not self._ids:
            img_id = self.canvas.create_image(canvas_x, canvas_y, anchor="nw", image=self._photo, tags=self.tag)
            self._ids = [img_id]
        else:
            self.canvas.coords(self._ids[0], canvas_x, canvas_y)
            self.canvas.itemconfigure(self._ids[0], image=self._photo)

    # Canvas-mode render (draw multiple text items to fake stroke)
    def _render_canvas(self):
        for cid in self._ids:
            try: self.canvas.delete(cid)
            except Exception: pass
        self._ids = []
        if self.shadow:
            dx, dy, scol = self.shadow
            sid = self.canvas.create_text(self.x+dx, self.y+dy, text=self.text, font=self.font, fill=scol, anchor=self.anchor, tags=self.tag)
            self._ids.append(sid)
        sw = max(1, int(self.stroke or 0))
        offsets = []
        r = sw
        for ox in range(-r, r+1):
            for oy in range(-r, r+1):
                if ox == 0 and oy == 0:
                    continue
                offsets.append((ox, oy))
        offsets = list({(ox, oy) for (ox, oy) in offsets})
        for ox, oy in offsets:
            iid = self.canvas.create_text(self.x+ox, self.y+oy, text=self.text, font=self.font, fill=self.stroke_fill, anchor=self.anchor, tags=self.tag)
            self._ids.append(iid)
        mid = self.canvas.create_text(self.x, self.y, text=self.text, font=self.font, fill=self.fill, anchor=self.anchor, tags=self.tag)
        self._ids.append(mid)

    # update API
    def update(self, text=None, fill=None, stroke=None, stroke_fill=None, shadow=None, font=None):
        changed = False
        if text is not None:
            self.text = str(text); changed = True
        if fill is not None:
            self.fill = fill; changed = True
        if stroke is not None:
            self.stroke = int(stroke); changed = True
        if stroke_fill is not None:
            self.stroke_fill = stroke_fill; changed = True
        if shadow is not None:
            self.shadow = shadow; changed = True
        if font is not None:
            self.font = font; self._pillow_font = None; changed = True
        if changed:
            if self.mode == "pillow":
                self._render_pillow()
            else:
                self._render_canvas()

    def destroy(self):
        for cid in self._ids:
            try: self.canvas.delete(cid)
            except Exception: pass
        self._ids = []
        self._photo = None

class TouchFeedbackManager:
    def __init__(self, app, sound_filename="tap.wav"):
        self.app = app
        self.assets_dir = os.path.join(BASE_DIR, "assets")
        self.sound_path = os.path.join(self.assets_dir, sound_filename)

        # preload simpleaudio WaveObject if file exists
        self.wave_obj = None
        try:
            if os.path.exists(self.sound_path):
                self.wave_obj = sa.WaveObject.from_wave_file(self.sound_path)
        except Exception as e:
            self.app.log(f"TouchFeedback: failed to load sound: {e}")

    def play_sound(self):
        """Non-blocking play."""
        try:
            if self.wave_obj:
                self.wave_obj.play()   # returns PlayObject; non-blocking
        except Exception as e:
            self.app.log(f"TouchFeedback: play_sound error: {e}")

    def ripple(self, canvas, x, y):
        r = 0
        circle = canvas.create_oval(x-r, y-r, x+r, y+r, outline="white", width=1)
        for i in range(10):
            canvas.after(
               i * 40,
               lambda c=circle, rr=r+i*2, w=max(1, 10-i):
               (
                   canvas.coords(c, x-rr, y-rr, x+rr, y+rr),
                   canvas.itemconfig(c, width=w)
               )
           )

            canvas.after(400, lambda: canvas.delete(circle))

    def flash_rect(self, canvas, rect_id, outline_color="yellow", width=4, ms=120):
        """Temporarily change rectangle outline to simulate button flash."""
        try:
            prev = canvas.itemcget(rect_id, "outline")
            prevw = canvas.itemcget(rect_id, "width")
            canvas.itemconfigure(rect_id, outline=outline_color, width=width)
            canvas.after(ms, lambda: canvas.itemconfigure(rect_id, outline=prev, width=prevw))
        except Exception:
            pass

    def on_tap(self, canvas, x, y, rect_id=None):
        """Convenience: ripple + sound + optional flash."""
        try:
            self.ripple(canvas, x, y)
            self.play_sound()
            if rect_id is not None:
                self.flash_rect(canvas, rect_id)
        except Exception as e:
            self.app.log(f"TouchFeedback.on_tap error: {e}")

# safe delete helper (to avoid exceptions if already removed)
def safe_delete(canvas, item):
    try:
        canvas.delete(item)
    except Exception:
        pass

def load_image_tk(name, resize_to=None):
    """Load an image from the assets folder and return ImageTk.PhotoImage (or raise)."""
    path = os.path.join(ASSETS_DIR, name)
    img = Image.open(path)
    if resize_to:
        img = img.resize(resize_to, Image.LANCZOS)
    return ImageTk.PhotoImage(img)

def file_exists(name):
    return os.path.exists(os.path.join(ASSETS_DIR, name))

def money_str(amount):
    return f"₱{amount:.2f}"
def amount_str(amount):
    return f"{amount:,.2f}"

# -------------------------
# SummaryBar widget
# -------------------------
class SummaryBar(tk.Frame):
    def __init__(
        self,
        parent,
        x: int | None = None,
        y: int | None = None,
        width: int = 800,
        height: int = 48,
        *,
        parent_canvas: tk.Canvas | None = None,
        font: tuple = ("Inter", 15),
        fill: str = "#FFC98B",
        stroke: int = 2,
        stroke_fill: str = "#FF1249",
        shadow: tuple | None = None,
        mode: str = "pillow",
        pillow_font_path=FONT_INTER,
        anchor: str = "center",
        **kwargs
    ):
        # keep frame size so existing .place(...) calls continue to work
        super().__init__(parent, width=width, height=height, **kwargs)

        # choose the canvas we'll draw on:
        # priority: explicit parent_canvas param -> parent's canvas attribute -> None
        self.parent = parent
        self.canvas = parent_canvas if parent_canvas is not None else getattr(parent, "canvas", None)

        # store placement and sizing
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.anchor = anchor

        # style args to forward to OutlinedText
        self._ot_kwargs = dict(
            font=font,
            fill=fill,
            stroke=stroke,
            stroke_fill=stroke_fill,
            shadow=shadow,
            mode=mode,
            pillow_font_path=pillow_font_path,
            anchor="center",
        )

        # decide which drawing mode to use
        self._use_parent_canvas = (self.canvas is not None and self.x is not None and self.y is not None)

        # internal references
        self._outlined_text = None
        self._inner_canvas = None
        self._tag = f"summarybar_{id(self)}"

        if self._use_parent_canvas:
            # draw directly on the provided canvas at (x,y) -> true transparency
            try:
                self._outlined_text = OutlinedText(
                    self.canvas,
                    self.x,
                    self.y,
                    text="",
                    tag=self._tag,
                    **self._ot_kwargs
                )
            except Exception as e:
                # fallback: create a tiny internal canvas
                print(f"[SummaryBar] Failed to initialize parent-canvas OutlinedText: {e}")
                self._use_parent_canvas = False

        if not self._use_parent_canvas:
            # create an internal canvas to render text (not truly transparent)
            bg = self.cget("bg")
            self._inner_canvas = tk.Canvas(self, width=self.width, height=self.height, highlightthickness=0, bg=bg)
            self._inner_canvas.pack(fill="both", expand=True)
            # center coords inside the inner canvas
            cx = self.width // 2
            cy = self.height // 2
            self._outlined_text = OutlinedText(
                self._inner_canvas,
                cx,
                cy,
                text="",
                tag=self._tag,
                **self._ot_kwargs
            )

    def set_text(self, text: str):
        """Update the displayed text (keeps the underlying OutlinedText instance)."""
        if not self._outlined_text:
            # defensive: create a simple label fallback
            for w in self.winfo_children():
                w.destroy()
            lbl = tk.Label(self, text=text, font=self._ot_kwargs.get("font", ("Arial", 12)), anchor="center", justify="center")
            lbl.pack(fill="both", expand=True)
            return

        try:
            # OutlinedText exposes update(...) — use it so we don't recreate images each update
            self._outlined_text.update(text=text)
        except Exception:
            # as a fallback, call update with the string
            try:
                self._outlined_text.update(text=str(text))
            except Exception as e:
                print(f"[SummaryBar] Failed to update outlined text: {e}")

    def clear(self):
        """Clear text."""
        self.set_text("")

    def set_parent_position(self, x: int, y: int):
        """If using parent-canvas mode, move the text position."""
        self.x = x
        self.y = y
        if self._use_parent_canvas and self._outlined_text:
            # OutlinedText stores its coordinates; update by re-rendering
            try:
                self._outlined_text.x = x
                self._outlined_text.y = y
                self._outlined_text.update(text=self._outlined_text.text)
            except Exception:
                pass

# -------------------------
# Application
# -------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fruit Shake Vending Machine")
        self.geometry(f"{SCREEN_W}x{SCREEN_H}")
        self.resizable(False, False)

        # debug / logging
        self.debug_mode = False
        self._debug_lines = []
        self.debug_widget = None
        self.bind_all("<Key-d>", lambda e: self.toggle_debug())
        self.bind_all("<Key-D>", lambda e: self.toggle_debug())
        self.touch_feedback = TouchFeedbackManager(self)

        # ---- Data model ----
        # stock: integer count; sales: integer count; best_seller (bool) computed from sales
        self.catalog = {
            "fruit1": {"name": "Watermelon", "price": 60.0, "stock": 5,  "sales": 0, "best_seller": False, "asset_name": "watermelon"},
            "fruit2": {"name": "Melon",     "price": 50.0, "stock": 5,  "sales": 0, "best_seller": False, "asset_name": "melon"},
            "fruit3": {"name": "Mango",     "price": 70.0, "stock": 5,  "sales": 1, "best_seller": False, "asset_name": "mango"},
            "fruit4": {"name": "Dragonfruit","price": 80.0,"stock": 0,  "sales": 1, "best_seller": False, "asset_name": "dragonfruit"},
            "fruit5": {"name": "Pineapple", "price": 75.0, "stock": 0,  "sales": 0, "best_seller": False, "asset_name": "pineapple"},
        }

        self.addons = {
            "pearls": {"name": "Black Pearls", "price": 15.0, "stock": 3, "sales": 0},
            "cheese": {"name": "Cheese", "price": 20.0, "stock": 3, "sales": 0},
        }

        # Ingredients (always consumed with orders): ice, milk, sugar (stock only)
        self.ingredients = {
            "ice": {"name": "Ice", "stock": 3},
            "milk": {"name": "Milk", "stock": 3},
            "sugar": {"name": "Sugar", "stock": 3},
        }

        # Track total income
        self.total_income = 0.0

        # user selections
        self.selected_fruits = []
        self.max_fruits = 3
        self.selected_addons = set()
        self.selected_ratio = None

        # inactivity timer
        self.default_timeout_ms = 10000
        self.active_timeout_ms = self.default_timeout_ms
        self.timer_id = None

        # UI container & frames
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        # create frames
        self.frames = {}
        for F in (WelcomeScreen,
                  FruitSelectionScreen,
                  AddOnScreen,
                  SummaryScreen,
                  PaymentSelectionScreen,
                  CashMethodScreen,
                  PaypalMethodScreen,
                  ProcessingScreen,
                  OrderCompleteScreen,
                  ErrorScreen):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # global input bindings to reset timer
        self.bind_all("<Key>", lambda e: self.reset_timer())
        self.bind_all("<Button-1>", lambda e: self.reset_timer())

        # ensure best-sellers are correct on start
        self.update_best_sellers()

        # show welcome
        self.show_frame(WelcomeScreen, pause=True)

    # -------------------------
    # logging / debug helpers
    # -------------------------
    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        self._debug_lines.append(line)
        if self.debug_widget:
            self.debug_widget.config(state="normal")
            self.debug_widget.insert("end", line + "\n")
            self.debug_widget.see("end")
            self.debug_widget.config(state="disabled")

    def toggle_debug(self):
        if self.debug_widget:
            self.debug_widget.place_forget()
            self.debug_widget = None
            self.debug_mode = False
        else:
            txt = tk.Text(self, width=40, height=12, bg="#111", fg="#0f0")
            txt.insert("end", "\n".join(self._debug_lines[-200:]) + ("\n" if self._debug_lines else ""))
            txt.config(state="disabled")
            txt.place(x=SCREEN_W - 420, y=20)
            self.debug_widget = txt
            self.debug_mode = True

    # -------------------------
    # best-seller / stock / sales helpers
    # -------------------------
    def update_best_sellers(self):
        """Set catalog[*]['best_seller'] True for fruit(s) with the highest sales (>0)."""
        sales_values = [f.get("sales", 0) for f in self.catalog.values()]
        if not sales_values:
            return
        max_sales = max(sales_values)
        for k, f in self.catalog.items():
            f["best_seller"] = (f.get("sales", 0) == max_sales and max_sales > 0)
        self.log(f"Best-seller updated (max sales={max_sales})")

    def record_sale(self):
        """
        Called when payment is confirmed. Decrement stock by 1 for each selected fruit (never negative).
        Increment sales for each selected fruit. Recompute best sellers and refresh overlays.
        """
        if not self.selected_fruits:
            self.log("record_sale called but no selected fruits")
            return

        self.log(f"Recording sale for: {self.selected_fruits}")
        for k in self.selected_fruits:
            item = self.catalog.get(k)
            if not item:
                continue
            # decrement stock safely
            stock = item.get("stock", 0)
            if stock > 0:
                item["stock"] = stock - 1
            else:
                item["stock"] = 0
            # increment sales
            item["sales"] = item.get("sales", 0) + 1
            self.log(f"Updated {k}: stock={item['stock']}, sales={item['sales']}")

        # update best sellers
        self.update_best_sellers()

        # refresh overlays on fruit screen (if exists)
        fs = self.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_overlays()
                fs.render_summary()
            except Exception as e:
                self.log(f"Failed to refresh FruitSelection overlays after sale: {e}")

    # -------------------------
    # frame switching & timer
    # -------------------------
    def show_frame(self, cls, timeout_ms=None, pause=False):
        frame = self.frames[cls]

        # BEFORE we raise the requested frame, check global error state
        if cls is not ErrorScreen and self.check_error_state():
            self.log("Error detected: switching to ErrorScreen")
            self.show_frame(ErrorScreen, pause=True)
            return

        frame = self.frames[cls]
        frame.tkraise()

        # configure active timeout
        if pause:
            self.active_timeout_ms = None
        else:
            self.active_timeout_ms = timeout_ms if timeout_ms is not None else self.default_timeout_ms

        # restart the timer according to active_timeout_ms
        self.reset_timer()

        # DEBUG: log the active timeout for this screen
        try:
            self.log(f"Navigating to {cls.__name__}, timeout_ms={self.active_timeout_ms}")
        except Exception:
            pass

    def reset_timer(self):
        if getattr(self, "timer_id", None):
            try:
                self.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None
        if isinstance(self.active_timeout_ms, int) and self.active_timeout_ms > 0:
            self.timer_id = self.after(self.active_timeout_ms, self.on_timeout)
        try:
            self.log(f"reset_timer: active_timeout_ms={self.active_timeout_ms}, timer_id={self.timer_id}")
        except Exception:
            pass

    def pause_inactivity(self):
        self.active_timeout_ms = None
        if getattr(self, "timer_id", None):
            try:
                self.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

    def resume_inactivity(self, timeout_ms=None):
        self.active_timeout_ms = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        self.reset_timer()

    def on_timeout(self):
        self.log("Inactivity timeout — returning to WelcomeScreen and clearing selections")
        self.selected_fruits.clear()
        self.selected_addons.clear()
        self.selected_ratio = None
        self.show_frame(WelcomeScreen, pause=True)

    def calculate_total(self):
        base = sum(self.catalog[k]["price"] for k in self.selected_fruits)
        addons = sum(self.addons[k]["price"] for k in self.selected_addons)
        return float(Decimal(base + addons).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        
    def check_error_state(self):
        """Return True if an error condition exists (ingredients out of stock OR all fruits out of stock)."""
        # any ingredient stock <= 0 -> error
        for k, v in getattr(self, "ingredients", {}).items():
            if v.get("stock", 0) <= 0:
                return True
        # all fruits out of stock?
        any_in_stock = False
        for k, v in getattr(self, "catalog", {}).items():
            # numeric stock supported
            if isinstance(v.get("stock", None), int):
                if v.get("stock", 0) > 0:
                    any_in_stock = True
                    break
            elif v.get("in_stock", False):
                any_in_stock = True
                break
        if not any_in_stock:
            return True
        return False

# -------------------------
# Screens (Frames)
# -------------------------
class WelcomeScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("welcomeScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # full-screen binding (tapping anywhere starts) — use a real handler
        self.canvas.bind("<Button-1>", self.on_screen_click)

        # --- Admin: hidden touch zone (top-right 100x100) ---
        x1, y1 = SCREEN_W - 100, 0
        x2, y2 = SCREEN_W, 100
        self.admin_zone = self.canvas.create_rectangle(x1, y1, x2, y2, outline="", fill="")

        # bind admin zone to a handler that RETURNS "break" to stop propagation
        self.canvas.tag_bind(self.admin_zone, "<Button-1>", self.on_admin_zone_click)

        # Admin panel frame (overlay) - initially hidden
        self.admin_panel = tk.Frame(self, width=700, height=575, bg="#222", bd=4, relief="raised")
        # center it
        self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self.admin_panel_visible = False
        self.admin_panel.place_forget()  # hide initially

        # build admin UI inside the panel
        self._build_admin_ui()
        self.admin_panel_visible = False

    def _build_admin_ui(self):
        """Populate the admin panel with stock/sales rows and admin controls."""
        panel = self.admin_panel

        # Clear any previous widgets (safe to call multiple times)
        for w in panel.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Title
        title = tk.Label(panel, text="ADMIN PANEL", font=("Arial", 18, "bold"), bg="#222", fg="white")
        title.place(relx=0.5, y=12, anchor="n")

        # Close button (hide admin)
        close_btn = tk.Button(panel, text="Close", command=self.toggle_admin)
        close_btn.place(x=panel.winfo_reqwidth() - 15, y=5, width=60, height=28, anchor="ne")
        # Exit button (closes app)
        exit_btn = tk.Button(panel, text="Exit", command=lambda: self.controller.destroy())
        exit_btn.place(x=panel.winfo_reqwidth() - 15, y=panel.winfo_reqheight() - 15, anchor="se")

        # Fullscreen toggle
        def _toggle_fullscreen():
            try:
                new_state = not getattr(self.controller, "is_fullscreen", False)
                try:
                    self.controller.attributes("-fullscreen", new_state)
                except Exception:
                    try:
                        self.controller.attributes("-zoomed", new_state)
                    except Exception:
                        pass
                self.controller.is_fullscreen = new_state
                self._fs_btn.config(text="Fullscreen: ON" if new_state else "Fullscreen: OFF")
            except Exception as e:
                self.controller.log(f"Failed to toggle fullscreen: {e}")

        self._fs_btn = tk.Button(panel, text=("Fullscreen: ON" if getattr(self.controller, "is_fullscreen", False) else "Fullscreen: OFF"), command=_toggle_fullscreen)
        self._fs_btn.place(x=5, y=5, anchor="nw")

        # Admin rows area (where each fruit/add-on row will be shown)
        rows_frame = tk.Frame(panel, bg="#222")
        rows_frame.place(relx=0.5, rely=0.12, anchor="n", relwidth=0.96, relheight=0.78)

        # store the parent so _refresh_admin_rows can populate into it
        self.admin_rows_parent = rows_frame

        # Try to populate rows using your existing helper (keeps single source of truth)
        if hasattr(self, "_refresh_admin_rows"):
            try:
                self._refresh_admin_rows()
            except Exception as e:
                self.controller.log(f"Welcome: _refresh_admin_rows() error: {e}")
                # fallback display if the helper exists but fails
                for w in rows_frame.winfo_children():
                    w.destroy()
                tk.Label(rows_frame, text="(admin refresh failed)", bg="#222", fg="white").pack()
        else:
            # No helper found: create a minimal interactive fallback
            for w in rows_frame.winfo_children():
                w.destroy()

            def make_row(parent, row_idx, label_text, stock_val_getter, change_fn):
                r = tk.Frame(parent, bg="#222")
                r.grid_rowconfigure(0, weight=1)
                r.grid_columnconfigure(0, weight=1)
                r.grid(row=row_idx, column=0, sticky="ew", pady=2)

                lbl = tk.Label(r, text=label_text, bg="#222", fg="white", anchor="w")
                lbl.pack(side="left", padx=6)

                stock_var = tk.StringVar(value=str(stock_val_getter()))
                stock_label = tk.Label(r, textvariable=stock_var, bg="#222", fg="white", width=6)
                stock_label.pack(side="left", padx=6)

                def on_change(delta):
                    try:
                        change_fn(delta)
                        stock_var.set(str(stock_val_getter()))
                    except Exception as e:
                        self.controller.log(f"Admin change error: {e}")

                minus = tk.Button(r, text="-", command=lambda: on_change(-1))
                minus.pack(side="left")
                plus = tk.Button(r, text="+", command=lambda: on_change(1))
                plus.pack(side="left")

            # populate fruits
            row = 0
            catalog = getattr(self.controller, "catalog", {})
            for k, info in catalog.items():
                name = info.get("name", k)
                make_row(rows_frame, row, f"{name} (fruit)", lambda info=info: int(info.get("stock", 0)),
                         lambda d, info=info: info.__setitem__("stock", max(0, int(info.get("stock", 0)) + d)))
                row += 1

            # populate addons
            addons = getattr(self.controller, "addons", {})
            for k, info in addons.items():
                name = info.get("name", k)
                make_row(rows_frame, row, f"{name} (add-on)", lambda info=info: int(info.get("stock", 0)),
                         lambda d, info=info: info.__setitem__("stock", max(0, int(info.get("stock", 0)) + d)))
                row += 1

    def on_admin_zone_click(self, event):
        # toggle admin panel and STOP further event propagation so the canvas-wide handler won't run
        self.toggle_admin()
        return "break"

    def _refresh_admin_rows(self):
        """Recreate the admin rows listing each fruit, its stock, sales, add-ons, ingredients, and controls."""
        parent = self.admin_rows_parent
        # clear children
        for w in parent.winfo_children():
            w.destroy()

        # heading row
        hdr = tk.Frame(parent, bg="#222")
        hdr.pack(fill="x", pady=(2,6))
        tk.Label(hdr, text="Item", width=20, anchor="w", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Stock", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Sales", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Best", width=6, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Controls", width=28, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)

        # rows for each fruit
        for key, meta in self.controller.catalog.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)

            stock_lbl = tk.Label(row, text=str(meta.get("stock", meta.get("in_stock", ""))), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)

            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)

            best_lbl = tk.Label(row, text="✓" if meta.get("best_seller", False) else "", width=6, anchor="center", bg="#222", fg="#0f0")
            best_lbl.pack(side="left", padx=4)

            # controls
            controls = tk.Frame(row, bg="#222")
            controls.pack(side="left", padx=4)

            def make_inc_stock(k):
                return lambda: self._admin_change_stock(k, +1)
            def make_dec_stock(k):
                return lambda: self._admin_change_stock(k, -1)
            def make_inc_sales(k):
                return lambda: self._admin_change_sales(k, +1)
            def make_dec_sales(k):
                return lambda: self._admin_change_sales(k, -1)

            btn_dec_stock = tk.Button(controls, text="-Stock", command=make_dec_stock(key), width=8)
            btn_dec_stock.pack(side="left", padx=2)
            btn_inc_stock = tk.Button(controls, text="+Stock", command=make_inc_stock(key), width=8)
            btn_inc_stock.pack(side="left", padx=2)
            btn_dec_sales = tk.Button(controls, text="-Sales", command=make_dec_sales(key), width=8)
            btn_dec_sales.pack(side="left", padx=6)
            btn_inc_sales = tk.Button(controls, text="+Sales", command=make_inc_sales(key), width=8)
            btn_inc_sales.pack(side="left", padx=2)

        # Separator for addons
        sep = tk.Label(parent, text="Add-Ons", bg="#222", fg="#fff", anchor="w")
        sep.pack(fill="x", pady=(8,4), padx=6)

        for key, meta in self.controller.addons.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)
            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)
            controls = tk.Frame(row, bg="#222"); controls.pack(side="left", padx=4)
            tk.Button(controls, text="-Stock", command=lambda k=key: self._admin_change_addon_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._admin_change_addon_stock(k, +1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="-Sales", command=lambda k=key: self._admin_change_addon_sales(k, -1), width=8).pack(side="left", padx=6)
            tk.Button(controls, text="+Sales", command=lambda k=key: self._admin_change_addon_sales(k, +1), width=8).pack(side="left", padx=2)

        # Separator for ingredients (stock only)
        sep2 = tk.Label(parent, text="Ingredients (stock only)", bg="#222", fg="#fff", anchor="w")
        sep2.pack(fill="x", pady=(8,4), padx=6)

        for key, meta in self.controller.ingredients.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)
            controls = tk.Frame(row, bg="#222"); controls.pack(side="left", padx=4)
            tk.Button(controls, text="-Stock", command=lambda k=key: self._admin_change_ingredient_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._admin_change_ingredient_stock(k, +1), width=8).pack(side="left", padx=2)

        # Income display and reset
        income_row = tk.Frame(parent, bg="#222")
        income_row.pack(fill="x", pady=(8,2))
        tk.Label(income_row, text="Total Income:", width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
        tk.Label(income_row, text=f"{self.controller.total_income:.2f}", width=12, anchor="w", bg="#222", fg="#FFD700").pack(side="left", padx=4)
        tk.Button(income_row, text="Reset Income", command=lambda: self._admin_reset_income(), width=12).pack(side="left", padx=6)

    def _admin_change_stock(self, key, delta):
        """Change stock safely and refresh UI; delta may be positive or negative."""
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_stock = max(0, item.get("stock", 0) + delta)
        item["stock"] = new_stock
        self.controller.log(f"Admin changed stock for {key}: {delta} -> new stock {new_stock}")
        # refresh overlays and admin rows and any summaries
        self.controller.update_best_sellers()
        fs = self.controller.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass
        self._refresh_admin_rows()

    def _admin_change_sales(self, key, delta):
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_sales = max(0, item.get("sales", 0) + delta)
        item["sales"] = new_sales
        self.controller.log(f"Admin changed sales for {key}: {delta} -> new sales {new_sales}")
        try:
            self.update_best_sellers()
        except Exception:
            pass
        self._refresh_admin_rows()

    def _admin_change_addon_stock(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["stock"] = max(0, item.get("stock", 0) + delta)
        self.controller.log(f"Admin changed addon stock for {key}: {delta} -> {item['stock']}")
        self._refresh_admin_rows()

    def _admin_change_addon_sales(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["sales"] = max(0, item.get("sales", 0) + delta)
        self.controller.log(f"Admin changed addon sales for {key}: {delta} -> {item['sales']}")
        self._refresh_admin_rows()

    def _admin_change_ingredient_stock(self, key, delta):
        item = self.controller.ingredients.get(key)
        if not item:
            return
        item["stock"] = max(0, item.get("stock", 0) + delta)
        self.controller.log(f"Admin changed ingredient stock for {key}: {delta} -> {item['stock']}")
        self._refresh_admin_rows()

    def _admin_reset_income(self):
        self.controller.total_income = 0.0
        self.controller.log("Admin reset total income")
        self._refresh_admin_rows()

    def _admin_change_sales(self, key, delta):
        """Change sales safely and refresh UI; delta may be positive or negative but sales clamped to >= 0."""
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_sales = max(0, item.get("sales", 0) + delta)
        item["sales"] = new_sales
        self.controller.log(f"Admin changed sales for {key}: {delta} -> new sales {new_sales}")
        # recompute best sellers and refresh overlays + admin rows
        self.controller.update_best_sellers()
        fs = self.controller.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass
        self._refresh_admin_rows()

    def toggle_admin(self):
        """Toggle admin panel visibility."""
        if self.admin_panel_visible:
            # hide
            self.admin_panel.place_forget()
            self.admin_panel_visible = False
            self.controller.log("Admin panel hidden")
        else:
            # refresh contents before showing
            self.controller.update_best_sellers()
            self._refresh_admin_rows()
            self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
            self.admin_panel_visible = True
            self.controller.log("Admin panel shown")

    def on_screen_click(self, event):
        # ignore taps while admin panel is visible (prevent accidental nav that hides admin)
        if getattr(self, "admin_panel_visible", False):
            self.controller.log("Screen tapped but admin panel visible — ignoring")
            return "break"
        else:
            self.controller.log("Screen tapped")
            # leaving welcome will let show_frame restore the standard inactivity timeout
            self.controller.show_frame(FruitSelectionScreen)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # hide admin when welcome shown by default
        if self.admin_panel_visible:
            self.admin_panel.place_forget()
            self.admin_panel_visible = False

        # Pause inactivity while on the welcome screen so admin won't be closed by the timer.
        # show_frame(...) will set/resume normal inactivity when another frame is shown.
        try:
            self.controller.pause_inactivity()
            self.controller.log("Welcome: inactivity paused while on Welcome screen")
        except Exception:
            pass

        # Clear selections when Welcome is shown (return-to-home behavior)
        self.controller.log("Welcome screen shown — clearing selections")
        self.controller.selected_fruits.clear()
        self.controller.selected_addons.clear()
        self.controller.selected_ratio = None

        # Refresh fruit screen overlays / summary so UI is consistent after clear
        fs = self.controller.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_fruit_states()
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass

class FruitSelectionScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # canvas + background
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("2_CLEAN_fruitSelectionScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # approximate touch zones for the fruit images (x1,y1,x2,y2)
        self.fruit_zones = {
            "fruit1": (50, 115, 225, 340),
            "fruit2": (225, 300, 400, 525),
            "fruit3": (425, 115, 600, 340),
            "fruit4": (625, 300, 800, 525),
            "fruit5": (800, 115, 975, 340),
        }

        # create invisible rectangles for each zone and bind click
        for key, (x1, y1, x2, y2) in self.fruit_zones.items():
            rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="", tags=(f"fruit_{key}",))
            self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key: self.on_fruit_click(k))

        # back & next zones (invisible touch)
        self.back_zone = (20, 520, 140, 580)
        self.next_zone = (880, 520, 1020, 580)
        back_rect = self.canvas.create_rectangle(*self.back_zone, outline="")
        next_rect = self.canvas.create_rectangle(*self.next_zone, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: controller.log("Back pressed on FruitSelection") or controller.show_frame(WelcomeScreen, pause=True))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: controller.log("Next pressed on FruitSelection") or self.on_next())

        # summary bar (use reusable SummaryBar, centered)
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)

        # overlay images (stock/bestseller) - keep references so PhotoImage doesn't GC
        self.overlay_refs = {}        # key -> list of PhotoImage refs
        self.overlay_items = {}       # key -> list of canvas item ids

        # selected highlight overlay tag
        self.sel_overlay_tag = "sel_overlay"

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # update overlays & selection visuals every time screen is shown
        self.update_fruit_states()
        self.update_overlays()
        self.render_summary()

    def on_fruit_click(self, key):
        self.controller.log(f"Clicked fruit zone: {key}")
        fruit = self.controller.catalog.get(key)
        if not fruit:
            self.controller.log(f"Unknown fruit key: {key}")
            return

        # check stock (integer)
        if fruit.get("stock", 0) <= 0:
            self.controller.log(f"{fruit['name']} is out of stock — ignoring selection")
            return

        if key in self.controller.selected_fruits:
            self.controller.selected_fruits.remove(key)
            self.controller.log(f"Unselected {fruit['name']}")
        else:
            if len(self.controller.selected_fruits) >= self.controller.max_fruits:
                self.controller.log("Max fruits already selected; ignoring additional selection")
                return
            self.controller.selected_fruits.append(key)
            self.controller.log(f"Selected {fruit['name']}")

        # update visuals & summary
        self.update_fruit_states()
        self.render_summary()

    def update_fruit_states(self):
        # selected highlight rectangles
        self.canvas.delete(self.sel_overlay_tag)
        for key, (x1, y1, x2, y2) in self.fruit_zones.items():
            if key in self.controller.selected_fruits:
                # draw a yellow rectangle inset to indicate selection
                self.canvas.create_rectangle(x1+4, y1+4, x2-4, y2-4, outline="yellow", width=4, tags=(self.sel_overlay_tag,))

    def update_overlays(self):
        """
        Draw (or remove) overlay PNGs for best-seller / out-of-stock items.
        """
        # delete previous overlays
        for items in self.overlay_items.values():
            for it in items:
                try:
                    self.canvas.delete(it)
                except Exception:
                    pass
        self.overlay_items.clear()
        self.overlay_refs.clear()

        for key, (x1, y1, x2, y2) in self.fruit_zones.items():
            meta = self.controller.catalog.get(key, {})
            asset_base = meta.get("asset_name")
            if not asset_base:
                continue
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            item_ids = []
            photo_refs = []

            # helper to load and place, with full-screen detection
            def place_overlay(filename):
                path = os.path.join(ASSETS_DIR, filename)
                try:
                    pil_img = Image.open(path)
                except Exception as e:
                    self.controller.log(f"Failed to open overlay image {filename}: {e}")
                    return None, None
                w, h = pil_img.size
                photo = ImageTk.PhotoImage(pil_img)
                # decide anchor/position
                if (w, h) == (SCREEN_W, SCREEN_H):
                    # full-screen overlay: place at top-left so PNG can include its own positioning
                    item = self.canvas.create_image(0, 0, anchor="nw", image=photo)
                else:
                    # smaller overlay -> center on fruit zone
                    item = self.canvas.create_image(center_x, center_y, anchor="center", image=photo)
                # Make overlay non-interactive so clicks pass through to zone rects underneath
                try:
                    self.canvas.itemconfigure(item, state="disabled")
                except Exception:
                    pass
                return item, photo

            # best seller (uses computed flag meta.get('best_seller'))
            if meta.get("best_seller", False):
                best_filename = f"{asset_base}BestSeller.png"
                if file_exists(best_filename):
                    item, photo = place_overlay(best_filename)
                    if item:
                        item_ids.append(item)
                        photo_refs.append(photo)

            # out of stock (draw on top of best seller when present) if stock <= 0
            if meta.get("stock", 0) <= 0:
                stock_filename = f"{asset_base}Stock.png"
                if file_exists(stock_filename):
                    item, photo = place_overlay(stock_filename)
                    if item:
                        item_ids.append(item)
                        photo_refs.append(photo)

            if item_ids:
                self.overlay_items[key] = item_ids
                self.overlay_refs[key] = photo_refs

    def render_summary(self):
        """Render summary into the SummaryBar (centered)."""
        parts = []
        if self.controller.selected_fruits:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self.controller.selected_fruits))
        if self.controller.selected_addons:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self.controller.selected_addons))
        parts.append("Total: " + money_str(self.controller.calculate_total()))
        summary_text = " | ".join(parts) if parts else "No items selected"
        # Update the reusable SummaryBar
        self.summary.set_text(summary_text)

    def on_next(self):
        if len(self.controller.selected_fruits) == 0:
            self.controller.log("Next pressed but no fruits selected -> ignored")
            return
        self.controller.log("Proceeding to AddOnScreen")
        self.controller.show_frame(AddOnScreen)

class AddOnScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("3_CLEAN_extraSelectionScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # addon zones and storage for rect ids (so we can keep highlights below them)
        self.addon_zones = {
            "pearls": (170, 179, 445, 454),
            "cheese": (588, 179, 863, 454),
        }
        self.addon_zone_items = {}   # key -> canvas rectangle id for touch zone

        for key, (x1, y1, x2, y2) in self.addon_zones.items():
            # create the touch rect (transparent) and keep the id so highlights can be lowered beneath it
            rect_id = self.canvas.create_rectangle(x1, y1, x2, y2, outline="")
            self.addon_zone_items[key] = rect_id
            # bind the touch
            self.canvas.tag_bind(rect_id, "<Button-1>", lambda e, k=key: self.toggle_addon(k))

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        next_rect = self.canvas.create_rectangle(880, 520, 1020, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: controller.log("Back pressed on AddOn") or controller.show_frame(FruitSelectionScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: controller.log("Next pressed on AddOn") or controller.show_frame(SummaryScreen, timeout_ms=self.controller.default_timeout_ms * 5))

        # SummaryBar for this screen
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)

        # tag name used for selection highlight overlays
        self.sel_overlay_tag = "addon_sel_overlay"

        # initial render
        self.update_addon_states()
        self.render_summary()

    def toggle_addon(self, key):
        self.controller.log(f"Clicked addon: {key}")
        if key in self.controller.selected_addons:
            self.controller.selected_addons.remove(key)
            self.controller.log(f"Removed addon {key}")
        else:
            self.controller.selected_addons.add(key)
            self.controller.log(f"Added addon {key}")

        # update visual state immediately
        self.update_addon_states()
        self.render_summary()

    def update_addon_states(self):
        """Draw or remove yellow selection outlines for selected add-ons.
        Selection outlines are created beneath the actual touch rects so they do not
        steal pointer events (we lower them under the touch rect item IDs).
        """
        # remove previous selection overlays
        try:
            self.canvas.delete(self.sel_overlay_tag)
        except Exception:
            pass

        for key, (x1, y1, x2, y2) in self.addon_zones.items():
            if key in self.controller.selected_addons:
                # inset the highlight slightly so it looks like your fruit selection highlights
                inset = 4
                sx1, sy1, sx2, sy2 = x1 + inset, y1 + inset, x2 - inset, y2 - inset
                sel_id = self.canvas.create_rectangle(sx1, sy1, sx2, sy2, outline="yellow", width=4, tags=(self.sel_overlay_tag,))
                # Lower the selection rectangle beneath the corresponding touch rect so the touch rect stays top-most
                # (this prevents the highlight from blocking clicks)
                try:
                    zone_id = self.addon_zone_items.get(key)
                    if zone_id:
                        self.canvas.tag_lower(sel_id, zone_id)
                except Exception:
                    # if lowering fails, ignore — selection still visible but may block clicks (unlikely)
                    pass

    def render_summary(self):
        parts = []
        if self.controller.selected_fruits:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self.controller.selected_fruits))
        if self.controller.selected_addons:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self.controller.selected_addons))
        parts.append("Total: " + money_str(self.controller.calculate_total()))
        summary_text = " | ".join(parts) if parts else "No items selected"
        self.summary.set_text(summary_text)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # keep visuals in sync when screen is shown
        self.update_addon_states()
        self.render_summary()

class SummaryScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Canvas + background image (same pattern as your other screens)
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("4_CLEAN_orderSummaryScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # Back / Next invisible zones (keeps existing behavior)
        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        next_rect = self.canvas.create_rectangle(880, 520, 1020, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back pressed on Summary") or self.controller.show_frame(AddOnScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: self.controller.log("Next pressed on Summary") or self.controller.show_frame(PaymentSelectionScreen, timeout_ms=self.controller.default_timeout_ms * 5))

        # choose font: use Inter if installed, otherwise fallback to Arial
        available_fonts = list(tkfont.families())
        if "Inter" in available_fonts:
            title_font_name = "Inter"
        else:
            title_font_name = "Arial"

        # Canvas text items for the summary (multi-line) and the price
        # width controls wrapping; anchor="n" places top-center at the given y
        self.items_text_id = OutlinedText(
            self.canvas,
            SCREEN_W // 2, 230,
            text="",
            font=("Inter", 20),
            fill="#FDDAB1",
            stroke=2,
            stroke_fill="#FF567D",
            mode="pillow",
            anchor="center",
            pillow_font_path=FONT_INTER
        )

        self.price_text_id = OutlinedText(
            self.canvas,
            SCREEN_W // 2, 400,
            text="",
            font=("Inter", 40),
            fill="#FFEA00",
            stroke=4,
            stroke_fill="#FF7B00",
            mode="pillow", 
            anchor="center",
            pillow_font_path=FONT_INTER
        )

    def tkraise(self, *args, **kwargs):
        """When shown, update summary and price (keeps text centered and justified)."""
        super().tkraise(*args, **kwargs)
        fruits = [self.controller.catalog[k]["name"] for k in self.controller.selected_fruits]
        addons = [self.controller.addons[k]["name"] for k in self.controller.selected_addons]
        parts = []
        if fruits:
            parts.append("Fruits:  " + ", ".join(fruits))
        if addons:
            parts.append("Add-ons:  " + ", ".join(addons))
        items_text = "\n".join(parts) if parts else "No items selected"

        total = self.controller.calculate_total()
        price_text = "Total:   " + money_str(total)

        # Update the canvas text items (keeps them centered)
        try:
            self.items_text_id.update(text=items_text)
            self.price_text_id.update(text=price_text)
        except Exception as e:
            self.controller.log(f"Failed to update summary canvas text: {e}")

        self.controller.log("Summary screen shown; total = " + money_str(total))

class PaymentSelectionScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5_CLEAN_paymentSelectionScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        cash_rect = self.canvas.create_rectangle(102, 147, 452, 468, outline="")
        pay_rect = self.canvas.create_rectangle(578, 147, 928, 468, outline="")
        self.canvas.tag_bind(cash_rect, "<Button-1>", lambda e: self.controller.log("Cash selected") or self.controller.show_frame(CashMethodScreen, timeout_ms=self.controller.default_timeout_ms * 10))
        self.canvas.tag_bind(pay_rect, "<Button-1>", lambda e: self.controller.log("PayPal selected") or self.controller.show_frame(PaypalMethodScreen, timeout_ms=self.controller.default_timeout_ms * 10))

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back on PaymentSelection") or self.controller.show_frame(SummaryScreen, timeout_ms=self.controller.default_timeout_ms * 5))

        # SummaryBar for this screen
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)
        self.render_summary()

    def render_summary(self):
        parts = []
        if self.controller.selected_fruits:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self.controller.selected_fruits))
        if self.controller.selected_addons:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self.controller.selected_addons))
        parts.append("Total: " + money_str(self.controller.calculate_total()))
        summary_text = " | ".join(parts) if parts else "No items selected"
        self.summary.set_text(summary_text)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # refresh summary when screen becomes visible
        try:
            self.render_summary()
        except Exception as e:
            self.controller.log(f"PaymentSelectionScreen: tkraise render_summary failed: {e}")

class CashMethodScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Canvas + background
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5A_CLEAN_cashMethodScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        # Global tap feedback binding
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # Back touch zone
        self.back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(self.back_rect, "<Button-1>", lambda e: (self.controller.log("Back on CashMethod"),self.controller.show_frame(PaymentSelectionScreen, timeout_ms=self.controller.default_timeout_ms * 5)))

        # Admin tap zone (top-right). This zone receives taps and uses a 3-tap unlock.
        x1, y1 = SCREEN_W - 100, 0
        x2, y2 = SCREEN_W, 100
        self.admin_zone = self.canvas.create_rectangle(x1, y1, x2, y2, outline="", fill="")
        try:
            self.canvas.tag_raise(self.admin_zone)
        except Exception:
            pass
        self._admin_tap_count = 0
        self._admin_tap_reset_job = None
        self.canvas.tag_bind(self.admin_zone, "<Button-1>", self._on_admin_zone_click)

        # Price display (canvas text so background stays transparent)
        self.price_text_id = OutlinedText(
            self.canvas,
            SCREEN_W // 1.1, 230,
            text="",
            font=("Inter", 40),
            fill="#FFEA00",
            stroke=3,
            stroke_fill="#FF7B00",
            mode="pillow", 
            anchor="e",
            pillow_font_path=FONT_INTER
        )

        # Entered amount display
        self.entered_text_id = OutlinedText(
            self.canvas,
            SCREEN_W // 1.1, 400,
            text="",
            font=("Inter", 40),
            fill="#FFEA00",
            stroke=3,
            stroke_fill="#FF7B00",
            mode="pillow", 
            anchor="e",
            pillow_font_path=FONT_INTER
        )

        # Internal state
        self.entered_amount = 0.0
        self._auto_proceed_job = None

        # Summary bar
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)

        # Build local admin panel (hidden by default)
        self.admin_panel = tk.Frame(self, width=620, height=340, bg="#222", bd=3, relief="raised")
        # center but hide initially
        self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self.admin_panel.place_forget()
        self.admin_visible = False
        self._build_local_admin_ui()

        # initial render
        self.render_summary()
        self._update_price_text()
        self._update_entered_text()

    # -------------------------
    # Admin tap / 3-tap unlock
    # -------------------------
    def _on_admin_zone_click(self, event):
        """Count taps for 3-tap unlock. Return 'break' to stop canvas-wide handlers."""
        self._admin_tap_count += 1
        self.controller.log(f"Cash admin zone tapped ({self._admin_tap_count}/3)")

        # cancel previous reset job
        if self._admin_tap_reset_job:
            try:
                self.after_cancel(self._admin_tap_reset_job)
            except Exception:
                pass
            self._admin_tap_reset_job = None

        if self._admin_tap_count >= 3:
            self._admin_tap_count = 0
            self._admin_tap_reset_job = None
            self.toggle_admin()
            return "break"

        # schedule reset
        self._admin_tap_reset_job = self.after(1000, self._reset_admin_tap_count)
        return "break"

    def _reset_admin_tap_count(self):
        self._admin_tap_count = 0
        self._admin_tap_reset_job = None
        self.controller.log("Cash admin tap count reset")

    def toggle_admin(self):
        """Show or hide the local admin panel on the Cash screen."""
        if self.admin_visible:
            self.admin_panel.place_forget()
            self.admin_visible = False
            self.controller.log("Cash admin panel hidden")
        else:
            # refresh labels before showing
            self._update_admin_labels()
            self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
            self.admin_visible = True
            self.controller.log("Cash admin panel shown")

    def _build_local_admin_ui(self):
        """Populate the admin overlay with simulator controls (keeps admin self-contained)."""
        panel = self.admin_panel
        # title & close
        title = tk.Label(panel, text="CASH ADMIN", font=("Arial", 16, "bold"), bg="#222", fg="white")
        title.place(relx=0.5, y=8, anchor="n")
        close_btn = tk.Button(panel, text="Close", command=self.toggle_admin)
        close_btn.place(relx=0.98, y=8, anchor="ne", width=60, height=28)

        # show price & current entered inside admin for convenience
        self._admin_price_var = tk.StringVar(value="Price: " + money_str(self.controller.calculate_total()))
        self._admin_entered_var = tk.StringVar(value="Entered: " + money_str(self.entered_amount))

        price_lbl = tk.Label(panel, textvariable=self._admin_price_var, font=("Arial", 14, "bold"), bg="#222", fg="white")
        entered_lbl = tk.Label(panel, textvariable=self._admin_entered_var, font=("Arial", 14), bg="#222", fg="white")

        price_lbl.place(relx=0.5, rely=0.18, anchor="center")
        entered_lbl.place(relx=0.5, rely=0.26, anchor="center")

        # Payment simulator label
        sim_label = tk.Label(panel, text="Payment Simulator", bg="#222", fg="white")
        sim_label.place(relx=0.02, rely=0.35, anchor="w")

        # Buttons: 1, 5, 10, 20, 50, 100
        btn_specs = [
            ("+1.00", 1.0, 0.10),
            ("+5.00", 5.0, 0.27),
            ("+10.00", 10.0, 0.44),
            ("+20.00", 20.0, 0.61),
            ("+50.00", 50.0, 0.78),
            ("+100.00", 100.0, 0.92),
        ]
        for text, val, relx in btn_specs:
            btn = tk.Button(panel, text=text, width=8, command=lambda v=val: self._admin_add_cash(v))
            btn.place(relx=relx, rely=0.45, anchor="center")

        # Reset button a bit lower
        btn_reset = tk.Button(panel, text="Reset", width=10, command=self.reset_payment)
        btn_reset.place(relx=0.5, rely=0.66, anchor="center")

        # small info label
        self._admin_info_label = tk.Label(panel, text="Simulator only (admin)", bg="#222", fg="#eee")
        self._admin_info_label.place(relx=0.5, rely=0.82, anchor="center")

    def _admin_add_cash(self, amount):
        """Admin helper — call add_cash and refresh admin labels."""
        self.add_cash(amount)
        # ensure admin labels update immediately
        self._update_admin_labels()

    def _update_admin_labels(self):
        """Refresh price/entered text inside admin panel."""
        try:
            total = self.controller.calculate_total()
            self._admin_price_var.set("Price: " + money_str(total))
            self._admin_entered_var.set("Entered: " + money_str(self.entered_amount))
        except Exception as e:
            self.controller.log(f"Cash admin: failed to update admin labels: {e}")

    # -------------------------
    # Standard screen lifecycle
    # -------------------------
    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self.cancel_auto_proceed()
        self.entered_amount = 0.0
        self._update_price_text()
        self._update_entered_text()
        self.render_summary()
        # ensure admin hidden when arriving
        if self.admin_visible:
            self.admin_panel.place_forget()
            self.admin_visible = False

    def _update_price_text(self):
        total = self.controller.calculate_total()
        try:
            self.price_text_id.update(text=amount_str(total))
        except Exception as e:
            self.controller.log(f"CashMethod: failed to update price text: {e}")

    def _update_entered_text(self):
        try:
            self.entered_text_id.update(text=amount_str(self.entered_amount))
        except Exception as e:
            self.controller.log(f"CashMethod: failed to update entered text: {e}")

    # -------------------------
    # Payment helpers (unchanged)
    # -------------------------
    def add_cash(self, amount):
        """Called to add money from hardware or admin simulator."""
        try:
            amount = float(amount)
        except Exception:
            self.controller.log(f"add_cash: invalid amount {amount}")
            return

        self.entered_amount = float(Decimal(self.entered_amount + amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        self.controller.log(f"CashMethod: added {amount:.2f} - total entered now {self.entered_amount:.2f}")
        self._update_entered_text()
        # update admin panel labels too (if visible)
        if getattr(self, "admin_visible", False):
            self._update_admin_labels()

        total = self.controller.calculate_total()
        if self.entered_amount + 0.0001 >= total:
            # record sale then auto-proceed after short delay
            self.controller.record_sale()
            self.cancel_auto_proceed()
            self._auto_proceed_job = self.after(1000, lambda: self.controller.show_frame(ProcessingScreen, pause=True))

    def reset_payment(self):
        """Reset the entered amount (used by admin 'Reset' button)."""
        self.cancel_auto_proceed()
        self.entered_amount = 0.0
        self._update_entered_text()
        if getattr(self, "admin_visible", False):
            self._update_admin_labels()
        self.controller.log("CashMethod: payment reset by admin")

    def cancel_auto_proceed(self):
        if getattr(self, "_auto_proceed_job", None):
            try:
                self.after_cancel(self._auto_proceed_job)
            except Exception:
                pass
            self._auto_proceed_job = None

    def render_summary(self):
        parts = []
        if self.controller.selected_fruits:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self.controller.selected_fruits))
        if self.controller.selected_addons:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self.controller.selected_addons))
        summary_text = " | ".join(parts) if parts else "No items selected"
        self.summary.set_text(summary_text)

class PaypalMethodScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5B_CLEAN_paypalMethodScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))
        # QR placeholder
        try:
            self.qr_img = load_image_tk("QRCodePlaceholder.png", resize_to=(350, 350))
            self.canvas.create_image(597, 174, anchor="nw", image=self.qr_img)
        except Exception:
            self.controller.log("QR image missing or load failed")
        # BACK BUTTON
        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(
            back_rect,
            "<Button-1>",
            lambda e: self.controller.log("Back on PayPal") or self.controller.show_frame(PaymentSelectionScreen, timeout_ms=self.controller.default_timeout_ms * 5)
        )
        total = self.controller.calculate_total()
        # PRICE LABEL
        self.price_text_id = OutlinedText(
            self.canvas,
            SCREEN_W // 1.95, 300,
            text="",
            font=("Inter", 40),
            fill="#00EEFF",
            stroke=3,
            stroke_fill="#0068DE",
            mode="pillow", 
            anchor="e",
            pillow_font_path=FONT_INTER
        )

        # PAY CONFIRM BUTTON
        btn = tk.Button(self, text="I PAID", command=self.confirm_paid)
        btn.place(x=950, y=550)
        # SUMMARY BAR
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)
        try:
            self.render_summary()
        except Exception as e:
            self.controller.log(f"PaypalMethodScreen: render_summary failed at init: {e}")

    def confirm_paid(self):
        self.controller.log("I PAID pressed (Paypal) — recording sale and proceeding to Processing")
        # record sale
        self.controller.record_sale()
        self.controller.show_frame(ProcessingScreen, pause=True)

    def render_summary(self):
        parts = []
        if self.controller.selected_fruits:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self.controller.selected_fruits))
        if self.controller.selected_addons:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self.controller.selected_addons))
        summary_text = " | ".join(parts) if parts else "No items selected"
        self.summary.set_text(summary_text)
        
    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # update price label and summary when shown
        try:
            total = self.controller.calculate_total()
            try:
                self.price_text_id.update(text=amount_str(total))
            except Exception as e:
                self.controller.log(f"PaypalMethodScreen: failed to update price_text_id: {e}")
            self.render_summary()
        except Exception as e:
            self.controller.log(f"PaypalMethodScreen: tkraise error: {e}")

class ProcessingScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Canvas background and image
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)

        # background image (full-screen)
        self.bg_img = load_image_tk("6_CLEAN_orderProgressScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        # touch feedback on tap
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # progress bar coordinates (kept as requested)
        self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2 = (137, 230, 887, 265)
        bar_w = self.bar_x2 - self.bar_x1
        bar_h = self.bar_y2 - self.bar_y1

        # empty progress bar image (background of the bar)
        self.empty_bar_img = None
        self.empty_bar_id = None
        try:
            self.empty_bar_img = load_image_tk("progressEmpty.png", resize_to=(bar_w, bar_h))
            self.empty_bar_id = self.canvas.create_image(self.bar_x1, self.bar_y1, anchor="nw", image=self.empty_bar_img)
        except Exception:
            self.empty_bar_img = None
            self.empty_bar_id = None

        # load full fill image (we will crop this each tick). If successful, we will NOT use the rectangle cover.
        self.fill_img_orig = None
        self.fill_photo = None
        self.fill_image_id = None
        try:
            full = Image.open(os.path.join(ASSETS_DIR, "progressBarFill.png")).convert("RGBA")
            # ensure same size as bar for cropping math
            full = full.resize((bar_w, bar_h), Image.LANCZOS)
            self.fill_img_orig = full
            # start with fully empty (0 width)
            empty_canvas = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
            self.fill_photo = ImageTk.PhotoImage(empty_canvas)
            # place the fill at the left of the bar area; update its PhotoImage each tick
            self.fill_image_id = self.canvas.create_image(self.bar_x1, self.bar_y1, anchor="nw", image=self.fill_photo)
        except Exception:
            # if load failed, fall back to rectangle cover technique later
            self.fill_img_orig = None
            self.fill_photo = None
            self.fill_image_id = None

        # a cover rectangle fallback (only created if image fill didn't load)
        self.cover = None
        if self.fill_img_orig is None:
            # create a cover rectangle above the empty/static fill (so it can reveal underlying fill)
            # Use the frame background color for the rectangle so it blends in
            self.cover = self.canvas.create_rectangle(self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2,
                                                      fill=self.cget("bg"), outline="")

        # percent and description canvas text (transparent background by design)
        self.percent_id = OutlinedText(
            self.canvas,
            SCREEN_W // 2, 383,
            text="0%",
            font=("Inter", 40),                # tuple: (family, size)
            fill="#FDDAB1",                    # your foreground color
            stroke=3,                          # default outline width
            stroke_fill="#FF567D",             # outline color (black)
            mode="pillow",                     # use Pillow rendering (exact stroke)
            anchor="center",
            pillow_font_path=FONT_INTER  # optional, if you bundle the .ttf
        )

        # description text (centered)
        self.desc_id = OutlinedText(
            self.canvas,
            SCREEN_W // 2, 442,
            text="Starting...",
            font=("Inter", 30),
            fill="#FDDAB1",
            stroke=3,
            stroke_fill="#FF567D",
            mode="pillow",
            anchor="center",
            pillow_font_path=FONT_INTER
        )

        # Summary bar (kept)
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)

        # Handle: support swapping handle images by process and snapping rotation
        self.handle_id = None
        self.handle_base_orig = None     # current base PIL image for the handle (unrotated)
        self.handle_rot_photo = None     # current rotated PhotoImage shown on canvas
        self.handle_imgs_by_segment = {}  # mapping segment_index -> PIL image (original)
        self.handle_size = (55, 60)

        # attempt to load a generic handle plus per-segment handle images if present
        try:
            # load a default generic handle if available
            default_path = os.path.join(ASSETS_DIR, "progressHandle.png")
            if os.path.exists(default_path):
                h_img = Image.open(default_path).convert("RGBA").resize(self.handle_size, Image.LANCZOS)
                self.handle_base_orig = h_img
            # load per-segment handle images (optional)
            # expected names you provided:
            seg_files = {
                1: "handle1Fruits.png",
                2: "handle2Ingredients.png",
                3: "handle3Blend.png",
                4: "handle4Pour.png",
                5: "handle5Cup.png"
            }
            for seg, fname in seg_files.items():
                p = os.path.join(ASSETS_DIR, fname)
                if os.path.exists(p):
                    img = Image.open(p).convert("RGBA").resize(self.handle_size, Image.LANCZOS)
                    self.handle_imgs_by_segment[seg] = img
            # if we have a segment-specific for segment 1, prefer that as base initially
            if 1 in self.handle_imgs_by_segment:
                self.handle_base_orig = self.handle_imgs_by_segment[1]
            if self.handle_base_orig:
                self.handle_rot_photo = ImageTk.PhotoImage(self.handle_base_orig)
                hx = (self.bar_x1 + self.bar_x2) // 2
                hy = (self.bar_y1 + self.bar_y2) // 2
                self.handle_id = self.canvas.create_image(hx, hy, image=self.handle_rot_photo)
        except Exception:
            self.handle_id = None
            self.handle_base_orig = None
            self.handle_rot_photo = None
            self.handle_imgs_by_segment = {}

        # handle sway state (snap left/right)
        self.handle_state = 1
        self.handle_sway_job = None
        # snap angle for rotation (degrees)
        self.handle_snap_angle = 10

        # internal progress and scheduling
        self.progress = 0
        self.progress_job = None

        # snapshots so clearing selection elsewhere doesn't blank this summary
        self._fruits_snapshot = []
        self._addons_snapshot = []

        # mapping of percentage ranges -> delay in seconds (lower delay = faster)
        self.segment_delays = [
            (0, 15, 0.12),    # Dispensing Fruit
            (16, 30, 0.12),   # Dispensing other ingredients
            (31, 70, 0.18),   # Blending (slower)
            (71, 90, 0.12),   # Pouring to cup
            (91, 99, 0.08),   # Sealing cup (faster)
            (100, 100, 0.0)
        ]

        # finish wait time (seconds) before moving to next screen
        self.finish_wait_s = 1.5

    def _get_delay_for_pct(self, pct):
        for lo, hi, delay in self.segment_delays:
            if lo <= pct <= hi:
                return delay
        return 0.12

    def render_summary(self):
        parts = []
        if self._fruits_snapshot:
            parts.append("Fruits: " + ", ".join(self.controller.catalog[k]["name"] for k in self._fruits_snapshot))
        if self._addons_snapshot:
            parts.append("Add-ons: " + ", ".join(self.controller.addons[k]["name"] for k in self._addons_snapshot))
        parts.append("Total: " + money_str(self.controller.calculate_total()))
        summary_text = " | ".join(parts) if parts else "No items selected"
        self.summary.set_text(summary_text)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)

        # TAKE SNAPSHOT of order BEFORE it may be cleared
        self._fruits_snapshot = list(self.controller.selected_fruits)
        self._addons_snapshot = list(self.controller.selected_addons)
        self.render_summary()

        self.controller.log("Processing screen shown — starting progress")

        # reset progress visuals
        self.progress = 0

        # if fallback cover exists, put it full-size
        if self.cover is not None:
            self.canvas.coords(self.cover, self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2)

        # cancel any existing jobs
        if self.progress_job:
            try:
                self.after_cancel(self.progress_job)
            except Exception:
                pass
            self.progress_job = None

        # (re)start handle sway if we have a handle
        if self.handle_id and not self.handle_sway_job:
            self._animate_handle()

        # start ticking
        self._tick_progress()

    def _tick_progress(self):
        if self.progress >= 100:
            self.progress = 100
            self._update_visuals()
            # wait finish_wait_s seconds and then finish
            self.progress_job = self.after(int(self.finish_wait_s * 1000), self._finish)
            return

        self.progress += 1
        self._update_visuals()

        delay_s = self._get_delay_for_pct(self.progress)
        self.progress_job = self.after(int(delay_s * 1000), self._tick_progress)

    def _current_segment_index(self, pct):
        if pct <= 15:
            return 1
        if pct <= 30:
            return 2
        if pct <= 70:
            return 3
        if pct <= 90:
            return 4
        return 5

    def _update_visuals(self):
        pct = self.progress
        reveal_ratio = pct / 100.0
        bar_w = self.bar_x2 - self.bar_x1
        bar_h = self.bar_y2 - self.bar_y1

        # update cropped fill image if available (preferred)
        if self.fill_img_orig is not None and self.fill_image_id is not None:
            full_w, full_h = self.fill_img_orig.size
            crop_w = int(full_w * reveal_ratio)
            if crop_w <= 0:
                canvas_img = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
            else:
                cropped = self.fill_img_orig.crop((0, 0, crop_w, full_h))
                canvas_img = Image.new("RGBA", (full_w, full_h), (0, 0, 0, 0))
                canvas_img.paste(cropped, (0, 0), cropped)
            self.fill_photo = ImageTk.PhotoImage(canvas_img)
            self.canvas.itemconfigure(self.fill_image_id, image=self.fill_photo)
            # no cover needed in this mode: reveal is by cropping the fill image (so no rectangle blocks empty)
        else:
            # fallback: move cover rect across to reveal an underlying static fill or empty background
            # keep cover on top of fill area
            if self.cover is not None:
                new_left = self.bar_x1 + int(reveal_ratio * (bar_w))
                self.canvas.coords(self.cover, new_left, self.bar_y1, self.bar_x2, self.bar_y2)

        # update labels
        if pct <= 15:
            desc = "Dispensing Fruit..."
        elif pct <= 30:
            desc = "Dispensing other Ingredients..."
        elif pct <= 70:
            desc = "Blending..."
        elif pct <= 90:
            desc = "Pouring to Cup..."
        elif pct < 100:
            desc = "Sealing Cup..."
        else:
            desc = "Done!"
        # Try updating OutlinedText instances; fall back to raw canvas text if something goes wrong
        try:
            # preferred: update our OutlinedText objects
            self.percent_id.update(text=f"{int(pct)}%")
            self.desc_id.update(text=desc)
        except Exception:
            # fallback: original canvas items (in case OutlinedText not present)
            try:
                self.canvas.itemconfigure(self.percent_id, text=f"{int(pct)}%")
                self.canvas.itemconfigure(self.desc_id, text=desc)
            except Exception:
                pass

        # determine which handle image to use for this segment (if provided)
        seg = self._current_segment_index(pct)
        if seg in self.handle_imgs_by_segment:
            # update base handle image if different
            if self.handle_base_orig is not self.handle_imgs_by_segment[seg]:
                self.handle_base_orig = self.handle_imgs_by_segment[seg]
                # update current rotated photo so it immediately reflects new base (no rotation here)
                try:
                    self.handle_rot_photo = ImageTk.PhotoImage(self.handle_base_orig)
                    if self.handle_id:
                        self.canvas.itemconfigure(self.handle_id, image=self.handle_rot_photo)
                except Exception:
                    pass

        # update handle x position (centered vertically on bar)
        if self.handle_id and self.handle_base_orig is not None:
            handle_x = self.bar_x1 + int(reveal_ratio * (self.bar_x2 - self.bar_x1))
            handle_y = (self.bar_y1 + self.bar_y2) // 2
            # reposition handle; actual rotation image is handled by the animate loop
            self.canvas.coords(self.handle_id, handle_x, handle_y-5)

    def _animate_handle(self):
        """Snap rotate left/right using the current handle base image.
        This function performs an instant rotate (no interpolation) and flips left/right every interval.
        """
        if not self.handle_id or self.handle_base_orig is None:
            return

        def _loop():
            if self.progress >= 100:
                self.handle_sway_job = None
                return
            # flip state
            self.handle_state *= -1
            angle = self.handle_snap_angle * self.handle_state
            try:
                rot = self.handle_base_orig.rotate(angle, resample=Image.BICUBIC, expand=True)
                self.handle_rot_photo = ImageTk.PhotoImage(rot)
                self.canvas.itemconfigure(self.handle_id, image=self.handle_rot_photo)
            except Exception:
                try:
                    self.handle_rot_photo = ImageTk.PhotoImage(self.handle_base_orig)
                    self.canvas.itemconfigure(self.handle_id, image=self.handle_rot_photo)
                except Exception:
                    pass
            self.handle_sway_job = self.after(1000, _loop)
        _loop()

    def _finish(self):
        if self.progress_job:
            try:
                self.after_cancel(self.progress_job)
            except Exception:
                pass
            self.progress_job = None
        if self.handle_sway_job:
            try:
                self.after_cancel(self.handle_sway_job)
            except Exception:
                pass
            self.handle_sway_job = None

        self.controller.log("Processing complete — moving to OrderCompleteScreen")
        try:
            self.controller.resume_inactivity()
        except Exception:
            pass
        self.controller.show_frame(OrderCompleteScreen, timeout_ms=self.controller.default_timeout_ms * 2)

class OrderCompleteScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("completeScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))
        self.canvas.bind("<Button-1>", lambda e: controller.log("OrderComplete tapped") or controller.show_frame(WelcomeScreen, pause=True))

class ErrorScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # Canvas / background (keep touch feedback binding)
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        try:
            self.bg_img = load_image_tk("errorScreen.png", resize_to=(SCREEN_W, SCREEN_H))
            self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        except Exception:
            # fallback visual
            self.canvas.create_rectangle(0, 0, SCREEN_W, SCREEN_H, fill="darkred")
            self.canvas.create_text(SCREEN_W // 2, SCREEN_H // 2,
                                    text="ERROR: Out of stock",
                                    fill="#000000", font=("Arial", 28, "bold"))

        # keep touch feedback binding (do not remove)
        self.canvas.bind("<Button-1>", lambda e: self.controller.touch_feedback.on_tap(self.canvas, e.x, e.y))

        # Hidden admin zone (top-right). Use same size as WelcomeScreen for consistency.
        x1, y1 = SCREEN_W - 250, 0
        x2, y2 = SCREEN_W, 250
        self.admin_zone = self.canvas.create_rectangle(x1, y1, x2, y2, outline="", fill="")
        # use the _on_admin_zone_tap handler which implements the 3-tap unlock and returns "break"
        self.canvas.tag_bind(self.admin_zone, "<Button-1>", self._on_admin_zone_tap)

        # admin state for tapping
        self._admin_tap_count = 0
        self._admin_tap_reset_job = None

        # Admin panel frame (overlay) - initially hidden
        self.admin_panel = tk.Frame(self, width=750, height=575, bg="#222", bd=4, relief="raised")
        self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self.admin_panel.place_forget()
        self.admin_panel_visible = False

        # Build admin UI inside panel (consistent with WelcomeScreen style)
        self._build_admin_ui()

    # -------------------------
    # Admin UI builder (same pattern as WelcomeScreen)
    # -------------------------
    def _build_admin_ui(self):
        """Populate the admin panel with stock/sales rows and admin controls."""
        panel = self.admin_panel

        # Clear any previous widgets (safe to call multiple times)
        for w in panel.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Title
        title = tk.Label(panel, text="ADMIN PANEL", font=("Arial", 18, "bold"), bg="#222", fg="white")
        title.place(relx=0.5, y=12, anchor="n")

        # Close button (hide admin)
        close_btn = tk.Button(panel, text="Close", command=self.toggle_admin)
        close_btn.place(x=panel.winfo_reqwidth() - 15, y=5, width=60, height=28, anchor="ne")
        # Exit button (closes app)
        exit_btn = tk.Button(panel, text="Exit", command=lambda: self.controller.destroy())
        exit_btn.place(x=panel.winfo_reqwidth() - 15, y=panel.winfo_reqheight() - 15, anchor="se")

        # Fullscreen toggle
        def _toggle_fullscreen():
            try:
                new_state = not getattr(self.controller, "is_fullscreen", False)
                try:
                    self.controller.attributes("-fullscreen", new_state)
                except Exception:
                    try:
                        self.controller.attributes("-zoomed", new_state)
                    except Exception:
                        pass
                self.controller.is_fullscreen = new_state
                self._fs_btn.config(text="Fullscreen: ON" if new_state else "Fullscreen: OFF")
            except Exception as e:
                self.controller.log(f"Failed to toggle fullscreen: {e}")

        self._fs_btn = tk.Button(panel, text=("Fullscreen: ON" if getattr(self.controller, "is_fullscreen", False) else "Fullscreen: OFF"), command=_toggle_fullscreen)
        self._fs_btn.place(x=5, y=5, anchor="nw")
        
        self.recheck_btn = tk.Button(
            self.admin_panel,
            text="Recheck Stock",
            command=self.recheck_stock
            )
        self.recheck_btn.place(x=5, y=panel.winfo_reqheight() - 15, anchor="sw")

        # Admin rows area (where each fruit/add-on row will be shown)
        rows_frame = tk.Frame(panel, bg="#222")
        rows_frame.place(relx=0.5, rely=0.12, anchor="n", relwidth=0.96, relheight=0.78)

        # store the parent so _refresh_admin_rows can populate into it
        self.admin_rows_parent = rows_frame

        # Try to populate rows using your existing helper (keeps single source of truth)
        if hasattr(self, "_refresh_admin_rows"):
            try:
                self._refresh_admin_rows()
            except Exception as e:
                self.controller.log(f"Welcome: _refresh_admin_rows() error: {e}")
                # fallback display if the helper exists but fails
                for w in rows_frame.winfo_children():
                    w.destroy()
                tk.Label(rows_frame, text="(admin refresh failed)", bg="#222", fg="white").pack()
        else:
            # No helper found: create a minimal interactive fallback
            for w in rows_frame.winfo_children():
                w.destroy()

            def make_row(parent, row_idx, label_text, stock_val_getter, change_fn):
                r = tk.Frame(parent, bg="#222")
                r.grid_rowconfigure(0, weight=1)
                r.grid_columnconfigure(0, weight=1)
                r.grid(row=row_idx, column=0, sticky="ew", pady=2)

                lbl = tk.Label(r, text=label_text, bg="#222", fg="white", anchor="w")
                lbl.pack(side="left", padx=6)

                stock_var = tk.StringVar(value=str(stock_val_getter()))
                stock_label = tk.Label(r, textvariable=stock_var, bg="#222", fg="white", width=6)
                stock_label.pack(side="left", padx=6)

                def on_change(delta):
                    try:
                        change_fn(delta)
                        stock_var.set(str(stock_val_getter()))
                    except Exception as e:
                        self.controller.log(f"Admin change error: {e}")

                minus = tk.Button(r, text="-", command=lambda: on_change(-1))
                minus.pack(side="left")
                plus = tk.Button(r, text="+", command=lambda: on_change(1))
                plus.pack(side="left")

            # populate fruits
            row = 0
            catalog = getattr(self.controller, "catalog", {})
            for k, info in catalog.items():
                name = info.get("name", k)
                make_row(rows_frame, row, f"{name} (fruit)", lambda info=info: int(info.get("stock", 0)),
                         lambda d, info=info: info.__setitem__("stock", max(0, int(info.get("stock", 0)) + d)))
                row += 1

            # populate addons
            addons = getattr(self.controller, "addons", {})
            for k, info in addons.items():
                name = info.get("name", k)
                make_row(rows_frame, row, f"{name} (add-on)", lambda info=info: int(info.get("stock", 0)),
                         lambda d, info=info: info.__setitem__("stock", max(0, int(info.get("stock", 0)) + d)))
                row += 1

    def _refresh_admin_rows(self):
        """Recreate the admin rows listing each fruit, its stock, sales, add-ons, ingredients, and controls."""
        parent = self.admin_rows_parent
        # clear children
        for w in parent.winfo_children():
            w.destroy()

        # heading row
        hdr = tk.Frame(parent, bg="#222")
        hdr.pack(fill="x", pady=(2,6))
        tk.Label(hdr, text="Item", width=20, anchor="w", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Stock", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Sales", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Best", width=6, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Controls", width=28, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)

        # rows for each fruit
        for key, meta in self.controller.catalog.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)

            stock_lbl = tk.Label(row, text=str(meta.get("stock", meta.get("in_stock", ""))), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)

            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)

            best_lbl = tk.Label(row, text="✓" if meta.get("best_seller", False) else "", width=6, anchor="center", bg="#222", fg="#0f0")
            best_lbl.pack(side="left", padx=4)

            # controls
            controls = tk.Frame(row, bg="#222")
            controls.pack(side="left", padx=4)

            def make_inc_stock(k):
                return lambda: self._admin_change_stock(k, +1)
            def make_dec_stock(k):
                return lambda: self._admin_change_stock(k, -1)
            def make_inc_sales(k):
                return lambda: self._admin_change_sales(k, +1)
            def make_dec_sales(k):
                return lambda: self._admin_change_sales(k, -1)

            btn_dec_stock = tk.Button(controls, text="-Stock", command=make_dec_stock(key), width=8)
            btn_dec_stock.pack(side="left", padx=2)
            btn_inc_stock = tk.Button(controls, text="+Stock", command=make_inc_stock(key), width=8)
            btn_inc_stock.pack(side="left", padx=2)
            btn_dec_sales = tk.Button(controls, text="-Sales", command=make_dec_sales(key), width=8)
            btn_dec_sales.pack(side="left", padx=6)
            btn_inc_sales = tk.Button(controls, text="+Sales", command=make_inc_sales(key), width=8)
            btn_inc_sales.pack(side="left", padx=2)

        # Separator for addons
        sep = tk.Label(parent, text="Add-Ons", bg="#222", fg="#fff", anchor="w")
        sep.pack(fill="x", pady=(8,4), padx=6)

        for key, meta in self.controller.addons.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)
            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)
            controls = tk.Frame(row, bg="#222"); controls.pack(side="left", padx=4)
            tk.Button(controls, text="-Stock", command=lambda k=key: self._admin_change_addon_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._admin_change_addon_stock(k, +1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="-Sales", command=lambda k=key: self._admin_change_addon_sales(k, -1), width=8).pack(side="left", padx=6)
            tk.Button(controls, text="+Sales", command=lambda k=key: self._admin_change_addon_sales(k, +1), width=8).pack(side="left", padx=2)

        # Separator for ingredients (stock only)
        sep2 = tk.Label(parent, text="Ingredients (stock only)", bg="#222", fg="#fff", anchor="w")
        sep2.pack(fill="x", pady=(8,4), padx=6)

        for key, meta in self.controller.ingredients.items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)
            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)
            controls = tk.Frame(row, bg="#222"); controls.pack(side="left", padx=4)
            tk.Button(controls, text="-Stock", command=lambda k=key: self._admin_change_ingredient_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._admin_change_ingredient_stock(k, +1), width=8).pack(side="left", padx=2)

        # Income display and reset
        income_row = tk.Frame(parent, bg="#222")
        income_row.pack(fill="x", pady=(8,2))
        tk.Label(income_row, text="Total Income:", width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
        tk.Label(income_row, text=f"{self.controller.total_income:.2f}", width=12, anchor="w", bg="#222", fg="#FFD700").pack(side="left", padx=4)
        tk.Button(income_row, text="Reset Income", command=lambda: self._admin_reset_income(), width=12).pack(side="left", padx=6)

    def recheck_stock(self):
        if not self.controller.check_error_state():
            self.controller.show_frame(WelcomeScreen, pause=True)

    def _admin_change_stock(self, key, delta):
        """Change stock safely and refresh UI; delta may be positive or negative."""
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_stock = max(0, item.get("stock", 0) + delta)
        item["stock"] = new_stock
        self.controller.log(f"Admin changed stock for {key}: {delta} -> new stock {new_stock}")
        # refresh overlays and admin rows and any summaries
        self.controller.update_best_sellers()
        fs = self.controller.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass
        self._refresh_admin_rows()

    def _admin_change_sales(self, key, delta):
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_sales = max(0, item.get("sales", 0) + delta)
        item["sales"] = new_sales
        self.controller.log(f"Admin changed sales for {key}: {delta} -> new sales {new_sales}")
        try:
            self.update_best_sellers()
        except Exception:
            pass
        self._refresh_admin_rows()

    def _admin_change_addon_stock(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["stock"] = max(0, item.get("stock", 0) + delta)
        self.controller.log(f"Admin changed addon stock for {key}: {delta} -> {item['stock']}")
        self._refresh_admin_rows()

    def _admin_change_addon_sales(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["sales"] = max(0, item.get("sales", 0) + delta)
        self.controller.log(f"Admin changed addon sales for {key}: {delta} -> {item['sales']}")
        self._refresh_admin_rows()

    def _admin_change_ingredient_stock(self, key, delta):
        item = self.controller.ingredients.get(key)
        if not item:
            return
        item["stock"] = max(0, item.get("stock", 0) + delta)
        self.controller.log(f"Admin changed ingredient stock for {key}: {delta} -> {item['stock']}")
        self._refresh_admin_rows()

    def _admin_reset_income(self):
        self.controller.total_income = 0.0
        self.controller.log("Admin reset total income")
        self._refresh_admin_rows()

    def _admin_change_sales(self, key, delta):
        """Change sales safely and refresh UI; delta may be positive or negative but sales clamped to >= 0."""
        item = self.controller.catalog.get(key)
        if not item:
            return
        new_sales = max(0, item.get("sales", 0) + delta)
        item["sales"] = new_sales
        self.controller.log(f"Admin changed sales for {key}: {delta} -> new sales {new_sales}")
        # recompute best sellers and refresh overlays + admin rows
        self.controller.update_best_sellers()
        fs = self.controller.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass
        self._refresh_admin_rows()

    # -------------------------
    # Admin zone tap / toggle
    # -------------------------
    def _on_admin_zone_tap(self, event):
        """Count taps for 3-tap unlock. Return 'break' to stop propagation."""
        self._admin_tap_count += 1
        self.controller.log(f"Error admin zone tapped ({self._admin_tap_count}/3)")

        # cancel previous reset job
        if self._admin_tap_reset_job:
            try:
                self.after_cancel(self._admin_tap_reset_job)
            except Exception:
                pass
            self._admin_tap_reset_job = None

        if self._admin_tap_count >= 3:
            self._admin_tap_count = 0
            self._admin_tap_reset_job = None
            self.toggle_admin()
            return "break"

        # schedule reset
        self._admin_tap_reset_job = self.after(1000, self._reset_admin_tap_count)
        return "break"

    def _reset_admin_tap_count(self):
        self._admin_tap_count = 0
        self._admin_tap_reset_job = None
        self.controller.log("Error admin tap count reset")

    def toggle_admin(self):
        """Show / hide the admin panel overlay."""
        if getattr(self, "admin_panel_visible", False):
            self.admin_panel.place_forget()
            self.admin_panel_visible = False
            self.controller.log("Error admin panel hidden")
            # resume inactivity timer when admin is hidden (if desired)
            try:
                self.controller.resume_inactivity()
            except Exception:
                pass
        else:
            # show and pause inactivity timer so admin can use controls safely
            self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
            self.admin_panel_visible = True
            self.controller.log("Error admin panel shown")
            try:
                self.controller.pause_inactivity()
            except Exception:
                pass
            # refresh rows (in case stock changed while panel hidden)
            try:
                self._refresh_admin_rows()
            except Exception:
                pass

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app = App()
    app.log("App started (updated with admin panel)")
    app.mainloop()
import os
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    _HAS_PIL = True
except Exception:
    _HAS_PIL = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_INTER = os.path.join(ASSETS_DIR, "Inter", "static", "Inter_28pt-ExtraBold.ttf")
SCREEN_W, SCREEN_H = 1024, 600 

def safe_delete(canvas, item):
    try:
        canvas.delete(item)
    except Exception:
        pass

def load_image_tk(name, resize_to=None):
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
        """ DELETE CHECKING & ENABLE IF CHECKING IS NOT NEEDED ON RPI
        self._pillow_font = ImageFont.truetype(self.pillow_font_path, size)
        print(f"[OutlinedText] Loaded pillow font from explicit path: {self.pillow_font_path} size={size}")
        """

        # 1) If user provided a direct path, try that first and log
        if self.pillow_font_path:
            try:
                self._pillow_font = ImageFont.truetype(self.pillow_font_path, size)
                print(f"[OutlinedText] Loaded pillow font from explicit path: {self.pillow_font_path} size={size}")
                return
            except Exception as e:
                print(f"[OutlinedText] Failed to load pillow_font_path '{self.pillow_font_path}': {e}")
        fam = None
        if isinstance(self.font, (list, tuple)) and len(self.font) >= 1:
            fam = str(self.font[0])
        if fam:
            candidates = [f"{fam}.ttf", f"{fam}.TTF", f"{fam}.otf"]
            for cand in candidates:
                try:
                    self._pillow_font = ImageFont.truetype(cand, size)
                    print(f"[OutlinedText] Loaded pillow font by candidate name: {cand} size={size}")
                    return
                except Exception:
                    pass
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
    def __init__(self, app):
        self.app = app
        self.assets_dir = os.path.join(BASE_DIR, "assets")

    def ripple(self, canvas, x, y):
        r = 0
        circle = canvas.create_oval(x-r, y-r, x+r, y+r, outline="#FF6F00", width=1)
        for i in range(10):
            canvas.after(
               i * 40,
               lambda c=circle, rr=r+i*2.5, w=max(1, 10-i):
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
        try:
            self.ripple(canvas, x, y)
            if rect_id is not None:
                self.flash_rect(canvas, rect_id)
        except Exception as e:
            self.app.log(f"TouchFeedback.on_tap error: {e}")

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

# buildTest.py  (updated)
import tkinter as tk
from PIL import Image, ImageTk
import os
from decimal import Decimal, ROUND_HALF_UP
import time

# -------------------------
# Config / paths
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")

SCREEN_W, SCREEN_H = 1024, 600

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

        self.attributes("-fullscreen", True)   # fullscreen mode
        # self.config(cursor="none")             # hide mouse cursor (remove comment when putting on RPi)

        # ---- Data model ----
        # note: each fruit has an asset_name used to find overlay PNGs like:
        #    {asset_name} + "BestSeller.png" and {asset_name} + "Stock.png"
        self.catalog = {
            "fruit1": {"name": "Watermelon", "price": 60.0, "in_stock": True, "best_seller": False, "asset_name": "watermelon"},
            "fruit2": {"name": "Melon", "price": 50.0, "in_stock": True, "best_seller": False, "asset_name": "melon"},
            "fruit3": {"name": "Mango", "price": 70.0, "in_stock": True, "best_seller": False, "asset_name": "mango"},
            "fruit4": {"name": "Dragonfruit", "price": 80.0, "in_stock": True, "best_seller": False, "asset_name": "dragonfruit"},
            "fruit5": {"name": "Pineapple", "price": 75.0, "in_stock": True, "best_seller": False, "asset_name": "pineapple"},
        }

        # sample addons
        self.addons = {
            "pearls": {"name": "Black Pearls", "price": 15.0},
            "cheese": {"name": "Cheese", "price": 20.0},
        }

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
                  OrderCompleteScreen):
            frame = F(container, self)
            self.frames[F] = frame
            frame.grid(row=0, column=0, sticky="nsew")

        # global input bindings to reset timer
        self.bind_all("<Key>", lambda e: self.reset_timer())
        self.bind_all("<Button-1>", lambda e: self.reset_timer())

        # show welcome
        self.show_frame(WelcomeScreen)

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
    # frame switching & timer
    # -------------------------
    def show_frame(self, cls, timeout_ms=None, pause=False):
        self.log(f"Navigating to {cls.__name__}")
        frame = self.frames[cls]
        frame.tkraise()

        # pause means disable inactivity while on this screen
        if pause:
            self.active_timeout_ms = None
        else:
            self.active_timeout_ms = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        self.reset_timer()

    def reset_timer(self):
        if getattr(self, "timer_id", None):
            try:
                self.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None
        if isinstance(self.active_timeout_ms, int) and self.active_timeout_ms > 0:
            self.timer_id = self.after(self.active_timeout_ms, self.on_timeout)

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
        self.show_frame(WelcomeScreen)

    def calculate_total(self):
        base = sum(self.catalog[k]["price"] for k in self.selected_fruits)
        addons = sum(self.addons[k]["price"] for k in self.selected_addons)
        return float(Decimal(base + addons).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

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
        # full-screen binding
        self.canvas.bind("<Button-1>", lambda e: controller.log("Welcome tapped") or controller.show_frame(FruitSelectionScreen))

    def tkraise(self, *args, **kwargs):
        """Override so welcome always resets selections when shown."""
        super().tkraise(*args, **kwargs)
        self.controller.log("Welcome screen shown — resetting selections")
        self.controller.selected_fruits.clear()
        self.controller.selected_addons.clear()
        self.controller.selected_ratio = None

class FruitSelectionScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller

        # canvas + background
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("2_CLEAN_fruitSelectionScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        # approximate touch zones for the fruit images (x1,y1,x2,y2)
        self.fruit_zones = {
            "fruit1": (62, 129, 212, 329),
            "fruit2": (237, 312, 387, 512),
            "fruit3": (437, 129, 587, 329),
            "fruit4": (637, 312, 787, 512),
            "fruit5": (812, 129, 962, 329),
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
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: controller.log("Back pressed on FruitSelection") or controller.show_frame(WelcomeScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: controller.log("Next pressed on FruitSelection") or self.on_next())

        # summary bar frame (shows small labels/icons for selected fruits)
        self.summary_frame = tk.Frame(self, width=500, height=48)
        self.summary_frame.place(x=262, y=514)

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

        if not fruit.get("in_stock", True):
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

        # If user selected 3 fruits, disable further selections by drawing a semi-transparent cover
        # (we simply log and ignore clicks in on_fruit_click, so no extra UI needed here)

    def update_overlays(self):
        """
        Draw (or remove) overlay PNGs for best-seller / out-of-stock items.
        Order: draw best-seller first, then out-of-stock on top if needed (as requested).
        Filenames are expected to be {asset_name} + "BestSeller.png" and {asset_name} + "Stock.png"
        (examples: mangoBestSeller.png, mangoStock.png)

        Behavior:
         - If an overlay PNG is full-screen (== SCREEN_W x SCREEN_H) it will be placed at (0,0) anchor='nw'
         - Otherwise it's placed centered on the fruit zone.
         - Overlay canvas items are set to state='disabled' so they do not intercept pointer events.
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
                    # fallback: try tagging and lowering (but state='disabled' should be sufficient)
                    pass
                return item, photo

            # best seller
            if meta.get("best_seller", False):
                best_filename = f"{asset_base}BestSeller.png"
                if file_exists(best_filename):
                    item, photo = place_overlay(best_filename)
                    if item:
                        item_ids.append(item)
                        photo_refs.append(photo)

            # out of stock (draw on top of best seller when present)
            if not meta.get("in_stock", True):
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
        # small text labels in the summary area (left-to-right)
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for k in self.controller.selected_fruits:
            name = self.controller.catalog.get(k, {}).get("name", k)
            tk.Label(self.summary_frame, text=name, font=("Arial", 12)).pack(side="left", padx=6)

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

        self.addon_zones = {
            "pearls": (180, 160, 420, 420),
            "cheese": (540, 160, 780, 420),
        }
        for key, (x1, y1, x2, y2) in self.addon_zones.items():
            rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="")
            self.canvas.tag_bind(rect, "<Button-1>", lambda e, k=key: self.toggle_addon(k))

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        next_rect = self.canvas.create_rectangle(880, 520, 1020, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: controller.log("Back pressed on AddOn") or controller.show_frame(FruitSelectionScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: controller.log("Next pressed on AddOn") or controller.show_frame(SummaryScreen))

        self.summary_frame = tk.Frame(self, width=500, height=48)
        self.summary_frame.place(x=262, y=500)
        self.render_summary()

    def toggle_addon(self, key):
        self.controller.log(f"Clicked addon: {key}")
        if key in self.controller.selected_addons:
            self.controller.selected_addons.remove(key)
            self.controller.log(f"Removed addon {key}")
        else:
            self.controller.selected_addons.add(key)
            self.controller.log(f"Added addon {key}")
        self.render_summary()

    def render_summary(self):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for k in self.controller.selected_fruits:
            tk.Label(self.summary_frame, text=self.controller.catalog[k]["name"], font=("Arial", 12)).pack(side="left", padx=6)
        for k in self.controller.selected_addons:
            tk.Label(self.summary_frame, text=self.controller.addons[k]["name"], font=("Arial", 12, "italic")).pack(side="left", padx=6)

class SummaryScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("4_CLEAN_orderSummaryScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        next_rect = self.canvas.create_rectangle(880, 520, 1020, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back pressed on Summary") or self.controller.show_frame(AddOnScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: self.controller.log("Next pressed on Summary") or self.controller.show_frame(PaymentSelectionScreen))

        # summary area (green)
        self.summary_box = tk.Frame(self, width=760, height=320, bg="#00FF00")
        self.summary_box.place(x=132, y=140)
        self.items_label = tk.Label(self.summary_box, text="", font=("Arial", 18), bg="#00FF00")
        self.items_label.pack(expand=True)
        self.price_label = tk.Label(self.summary_box, text="", font=("Arial", 24, "bold"), bg="#00FF00")
        self.price_label.pack()

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        fruits = [self.controller.catalog[k]["name"] for k in self.controller.selected_fruits]
        addons = [self.controller.addons[k]["name"] for k in self.controller.selected_addons]
        parts = []
        if fruits:
            parts.append("Fruits: " + ", ".join(fruits))
        if addons:
            parts.append("Add-ons: " + ", ".join(addons))
        self.items_label.config(text="\n".join(parts) if parts else "No items selected")
        total = self.controller.calculate_total()
        self.price_label.config(text="Total: " + money_str(total))
        self.controller.log("Summary screen shown; total = " + money_str(total))

class PaymentSelectionScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5_CLEAN_paymentSelectionScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        cash_rect = self.canvas.create_rectangle(80, 140, 420, 460, outline="")
        pay_rect = self.canvas.create_rectangle(600, 140, 940, 460, outline="")
        self.canvas.tag_bind(cash_rect, "<Button-1>", lambda e: self.controller.log("Cash selected") or self.controller.show_frame(CashMethodScreen))
        # PayPal gets a bigger timeout (5x default)
        self.canvas.tag_bind(pay_rect, "<Button-1>", lambda e: self.controller.log("PayPal selected") or self.controller.show_frame(PaypalMethodScreen, timeout_ms=self.controller.default_timeout_ms*5))

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back on PaymentSelection") or self.controller.show_frame(SummaryScreen))

        self.summary_frame = tk.Frame(self, width=500, height=48)
        self.summary_frame.place(x=262, y=500)
        self.render_summary()

    def render_summary(self):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for k in self.controller.selected_fruits:
            tk.Label(self.summary_frame, text=self.controller.catalog[k]["name"], font=("Arial", 12)).pack(side="left", padx=6)
        for k in self.controller.selected_addons:
            tk.Label(self.summary_frame, text=self.controller.addons[k]["name"], font=("Arial", 12, "italic")).pack(side="left", padx=6)
        tk.Label(self.summary_frame, text=money_str(self.controller.calculate_total()), font=("Arial", 14, "bold")).pack(side="left", padx=8)

class CashMethodScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5A_CLEAN_cashMethodScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back on CashMethod") or self.controller.show_frame(PaymentSelectionScreen))

        self.price_label = tk.Label(self, text="Price: " + money_str(controller.calculate_total()), font=("Arial", 26), bg="#000000", fg="#FFFFFF")
        self.price_label.place(x=260, y=120, width=520, height=60)

        tk.Label(self, text="Amount Entered (simulate):", font=("Arial", 14)).place(x=120, y=240)
        self.amount_entry = tk.Entry(self, font=("Arial", 22))
        self.amount_entry.place(x=360, y=240, width=420, height=50)

        btn = tk.Button(self, text="Submit Amount", command=self.check_amount)
        btn.place(x=440, y=320)

        self.summary_frame = tk.Frame(self, width=500, height=48)
        self.summary_frame.place(x=262, y=500)
        self.render_summary()

    def render_summary(self):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for k in self.controller.selected_fruits:
            tk.Label(self.summary_frame, text=self.controller.catalog[k]["name"], font=("Arial", 12)).pack(side="left", padx=6)
        for k in self.controller.selected_addons:
            tk.Label(self.summary_frame, text=self.controller.addons[k]["name"], font=("Arial", 12, "italic")).pack(side="left", padx=6)

    def check_amount(self):
        try:
            entered = float(self.amount_entry.get())
        except Exception:
            self.controller.log("Invalid amount entered")
            return
        total = self.controller.calculate_total()
        self.controller.log(f"Cash entered: {entered}, required: {total}")
        if abs(entered - total) < 0.001:
            self.controller.log("Exact cash received — proceeding to Processing")
            self.controller.show_frame(ProcessingScreen, pause=True)
        else:
            self.amount_entry.config(bg="red")
            self.after(400, lambda: self.amount_entry.config(bg="white"))
            self.controller.log("Cash does not match required amount")

class PaypalMethodScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("5B_CLEAN_paypalMethodScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        # QR placeholder: 350 x 350 at roughly the same spot as your design
        try:
            self.qr_img = load_image_tk("QRCodePlaceholder.png", resize_to=(350, 350))
            self.canvas.create_image(595, 120, anchor="nw", image=self.qr_img)
        except Exception:
            self.controller.log("QR image missing or load failed")

        back_rect = self.canvas.create_rectangle(20, 520, 140, 580, outline="")
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: self.controller.log("Back on PayPal") or self.controller.show_frame(PaymentSelectionScreen))

        btn = tk.Button(self, text="I PAID", command=lambda: self.controller.log("I PAID pressed (Paypal)") or self.controller.show_frame(ProcessingScreen, pause=True))
        btn.place(x=450, y=500)

class ProcessingScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("6_CLEAN_orderProgressScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

        # progress bar area
        self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2 = (120, 120, 904, 160)
        # load fill image and resize to bar
        try:
            fill_img = Image.open(os.path.join(ASSETS_DIR, "progressBarFill.png"))
            bar_w = self.bar_x2 - self.bar_x1
            bar_h = self.bar_y2 - self.bar_y1
            fill_img = fill_img.resize((bar_w, bar_h), Image.LANCZOS)
            self.fill_photo = ImageTk.PhotoImage(fill_img)
            self.fill_image_id = self.canvas.create_image(self.bar_x1, self.bar_y1, anchor="nw", image=self.fill_photo)
        except Exception:
            self.fill_photo = None
            self.fill_image_id = None

        # cover rectangle that hides the fill; will be moved left to reveal
        self.cover = self.canvas.create_rectangle(self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2, fill=self.cget("bg"), outline="")

        self.percent_label = tk.Label(self, text="0%", font=("Arial", 24), bg="black", fg="white")
        self.percent_label.place(x=430, y=220, width=160, height=48)
        self.desc_label = tk.Label(self, text="Starting...", font=("Arial", 20), bg="black", fg="white")
        self.desc_label.place(x=260, y=300, width=500, height=48)

        self.summary_frame = tk.Frame(self, width=500, height=48)
        self.summary_frame.place(x=262, y=500)
        self.render_summary()

        self.progress = 0
        self.progress_job = None

    def render_summary(self):
        for w in self.summary_frame.winfo_children():
            w.destroy()
        for k in self.controller.selected_fruits:
            tk.Label(self.summary_frame, text=self.controller.catalog[k]["name"], font=("Arial", 12)).pack(side="left", padx=6)
        for k in self.controller.selected_addons:
            tk.Label(self.summary_frame, text=self.controller.addons[k]["name"], font=("Arial", 12, "italic")).pack(side="left", padx=6)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        self.controller.log("Processing screen shown — starting progress")
        self.progress = 0
        self.canvas.coords(self.cover, self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2)
        if self.progress_job:
            try:
                self.after_cancel(self.progress_job)
            except Exception:
                pass
            self.progress_job = None
        self._tick_progress()

    def _tick_progress(self):
        if self.progress >= 100:
            self._finish()
            return
        self.progress += 1
        reveal_ratio = self.progress / 100.0
        new_left = int(self.bar_x1 + (1.0 - reveal_ratio) * (self.bar_x2 - self.bar_x1))
        self.canvas.coords(self.cover, new_left, self.bar_y1, self.bar_x2, self.bar_y2)
        pct = self.progress
        self.percent_label.config(text=f"{pct}%")
        if pct <= 15:
            desc = "Dispensing Fruit"
        elif pct <= 30:
            desc = "Dispensing other Ingredients"
        elif pct <= 70:
            desc = "Blending"
        elif pct <= 90:
            desc = "Pouring to Cup"
        elif pct < 100:
            desc = "Sealing Cup"
        else:
            desc = "Done"
        self.desc_label.config(text=desc)
        if pct % 10 == 0:
            self.controller.log(f"Processing progress {pct}% - {desc}")
        self.progress_job = self.after(120, self._tick_progress)

    def _finish(self):
        if self.progress_job:
            try:
                self.after_cancel(self.progress_job)
            except Exception:
                pass
            self.progress_job = None
        self.controller.log("Processing complete — moving to OrderCompleteScreen")
        self.controller.resume_inactivity()
        self.controller.show_frame(OrderCompleteScreen)

class OrderCompleteScreen(tk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent)
        self.controller = controller
        self.canvas = tk.Canvas(self, width=SCREEN_W, height=SCREEN_H, highlightthickness=0)
        self.canvas.place(x=0, y=0)
        self.bg_img = load_image_tk("completeScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)
        self.canvas.bind("<Button-1>", lambda e: controller.log("OrderComplete tapped") or controller.show_frame(WelcomeScreen))

# -------------------------
# Run
# -------------------------
if __name__ == "__main__":
    app = App()
    app.log("App started (updated buildTest)")
    app.mainloop()
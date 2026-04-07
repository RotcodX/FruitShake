import tkinter as tk
import time
import math
import uuid
import os
import tkinter.font as tkfont

from decimal import Decimal, ROUND_HALF_UP
from turtle import done
from PIL import Image, ImageTk
from admin import AdminPanel
from ui_common import ASSETS_DIR, OutlinedText, SCREEN_W, SCREEN_H
from ui_common import (
    FONT_INTER,
    load_image_tk,
    file_exists,
    safe_delete,
    money_str,
    amount_str,
    SummaryBar,
)

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

        self.admin_panel = AdminPanel(
            self,
            self.controller,
            fruit_screen_cls=FruitSelectionScreen,
            width=750,
            height=575,
            show_recheck_stock=True,
            return_to_cls=None,   # stays on WelcomeScreen; just refreshes
            )
        self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self.admin_panel.hide()

        self.canvas.tag_bind(self.admin_zone, "<Button-1>", self._open_admin_with_loading)

    def _open_admin_with_loading(self, event=None):
        if self.controller.busy:
            return "break"

        if self.admin_panel.visible:
            self.admin_panel.hide()
            return "break"

        self.controller.show_loading_gif(self.canvas)

        def done(err):
            self.controller.hide_loading_gif()
            if err:
                self.controller.log(f"Welcome admin open failed: {err}")
                return
            self.admin_panel.show(skip_refresh=True)
            self.admin_panel.refresh()

        self.controller.run_async(self.controller.update_best_sellers, on_done=done)
        return "break"

    def on_screen_click(self, event):
        # ignore taps while admin panel is visible but still show touch feedback cuz why not
        if self.admin_panel.visible:
            self.controller.log("Screen tapped but admin panel visible — ignoring")
            return "break"
        else:
            self.controller.log("Screen tapped")
            # leaving welcome will let show_frame restore the standard inactivity timeout 
            self.controller.show_frame(FruitSelectionScreen)

    def tkraise(self, *args, **kwargs):
        super().tkraise(*args, **kwargs)
        # hide admin when welcome shown by default
        if self.admin_panel.visible:
            self.admin_panel.place_forget()
            self.admin_panel.visible = False

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
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: controller.log("Back pressed on FruitSelection") or controller.show_frame(WelcomeScreen))
        self.canvas.tag_bind(next_rect, "<Button-1>", lambda e: controller.log("Next pressed on FruitSelection") or self.on_next())

        # summary bar (use reusable SummaryBar, centered)
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)

        # overlay images (stock/bestseller) - keep references so PhotoImage doesn't GC
        self.overlay_refs = {}        # key -> list of PhotoImage refs
        self.overlay_items = {}       # key -> list of canvas item ids

        # selected highlight overlay tag
        self.sel_overlay_tag = "sel_overlay"

        # -----------------------
        # PRELOAD small overlay images into a cache to avoid heavy Image.open / PhotoImage
        # -----------------------
        # cache keys: (fruit_key, "best") and (fruit_key, "stock")
        self._overlay_cache = {}
        # Optional quick disable if you want to check if overlays are the cause:
        self._disable_overlays = False

        try:
            for key, (x1, y1, x2, y2) in self.fruit_zones.items():
                meta = self.controller.catalog.get(key, {})
                asset_base = meta.get("asset_name")
                if not asset_base:
                    continue
                zone_w = max(1, x2 - x1)
                zone_h = max(1, y2 - y1)

                # filenames you use in update_overlays:
                for suffix, cache_tag in (("BestSeller.png", "best"), ("Stock.png", "stock")):
                    fname = f"{asset_base}{suffix}"
                    if file_exists(fname):
                        try:
                            # load once and resize to zone size where appropriate
                            pil = Image.open(os.path.join(ASSETS_DIR, fname))
                            # if overlay is full-screen we keep original size (it will be placed at 0,0)
                            if pil.size == (SCREEN_W, SCREEN_H):
                                photo = ImageTk.PhotoImage(pil)
                            else:
                                # resize down to the fruit zone - this saves memory on Pi
                                pil_r = pil.resize((zone_w, zone_h), Image.LANCZOS)
                                photo = ImageTk.PhotoImage(pil_r)
                            self._overlay_cache[(key, cache_tag)] = photo
                        except Exception as e:
                            # log but continue — if this fails, update_overlays will skip gracefully
                            self.controller.log(f"Preload overlay failed for {fname}: {e}")
        except Exception as e:
            # be defensive: if preload crashes, continue without cache
            self.controller.log(f"Overlay preload error: {e}")
            self._overlay_cache = {}

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
        Uses preloaded images when possible to avoid heavy allocations on each call.
        """
        # If overlays disabled, clear any existing and return
        if getattr(self, "_disable_overlays", False):
            for items in list(self.overlay_items.values()):
                for it in items:
                    safe_delete(self.canvas, it)
            self.overlay_items.clear()
            self.overlay_refs.clear()
            return

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

            def _place_from_photo(photo, full_screen=False):
                try:
                    if full_screen:
                        item = self.canvas.create_image(0, 0, anchor="nw", image=photo)
                    else:
                        item = self.canvas.create_image(center_x, center_y, anchor="center", image=photo)
                    # Make overlay non-interactive so clicks pass through to zone rects underneath
                    try:
                        self.canvas.itemconfigure(item, state="disabled")
                    except Exception:
                        pass
                    return item
                except Exception as e:
                    self.controller.log(f"Canvas create_image failed: {e}")
                    return None

            # best seller (uses computed flag meta.get('best_seller'))
            if meta.get("best_seller", False):
                # try cache first
                photo = self._overlay_cache.get((key, "best"))
                if photo is not None:
                    item = _place_from_photo(photo, full_screen=(photo.width() == SCREEN_W and photo.height() == SCREEN_H))
                    if item:
                        item_ids.append(item); photo_refs.append(photo)
                else:
                    # fallback: try load on demand but keep it safe
                    fname = f"{asset_base}BestSeller.png"
                    if file_exists(fname):
                        try:
                            img = Image.open(os.path.join(ASSETS_DIR, fname))
                            if img.size == (SCREEN_W, SCREEN_H):
                                photo = ImageTk.PhotoImage(img)
                                item = _place_from_photo(photo, full_screen=True)
                            else:
                                w = x2 - x1; h = y2 - y1
                                photo = ImageTk.PhotoImage(img.resize((w,h), Image.LANCZOS))
                                item = _place_from_photo(photo, full_screen=False)
                            if item:
                                item_ids.append(item); photo_refs.append(photo)
                        except Exception as e:
                            self.controller.log(f"Failed to load best-seller image {fname}: {e}")

            # out of stock (draw on top of best seller when present)
            if meta.get("stock", 0) <= 0:
                photo = self._overlay_cache.get((key, "stock"))
                if photo is not None:
                    item = _place_from_photo(photo, full_screen=(photo.width() == SCREEN_W and photo.height() == SCREEN_H))
                    if item:
                        item_ids.append(item); photo_refs.append(photo)
                else:
                    fname = f"{asset_base}Stock.png"
                    if file_exists(fname):
                        try:
                            img = Image.open(os.path.join(ASSETS_DIR, fname))
                            if img.size == (SCREEN_W, SCREEN_H):
                                photo = ImageTk.PhotoImage(img)
                                item = _place_from_photo(photo, full_screen=True)
                            else:
                                w = x2 - x1; h = y2 - y1
                                photo = ImageTk.PhotoImage(img.resize((w,h), Image.LANCZOS))
                                item = _place_from_photo(photo, full_screen=False)
                            if item:
                                item_ids.append(item); photo_refs.append(photo)
                        except Exception as e:
                            self.controller.log(f"Failed to load stock image {fname}: {e}")

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

        any_addon_in_stock = any(
            item.get("stock", 0) > 0
            for item in self.controller.addons.values()
        )

        if any_addon_in_stock:
            self.controller.log("Proceeding to AddOnScreen")
            self.controller.show_frame(AddOnScreen)
        else:
            self.controller.log("No add-ons in stock -> skipping AddOnScreen and going to SummaryScreen")
            self.controller.show_frame(SummaryScreen, timeout_ms=self.controller.default_timeout_ms * 5)

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
            "pearls": (177, 167, 477, 467),
            "cheese": (529, 167, 829, 467),
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

        self._addon_overlay_cache = {}
        self._addon_overlay_items = {}
        self.addon_stock_overlay_tag = "addon_stock_overlay"

        try:
            for key, asset_base in (("pearls", "pearls"), ("cheese", "cheese")):
                fname = f"{asset_base}Stock.png"
                if file_exists(fname):
                    img = Image.open(os.path.join(ASSETS_DIR, fname))
                    photo = ImageTk.PhotoImage(img)  # full-screen image, no resize needed
                    self._addon_overlay_cache[key] = photo
        except Exception as e:
            self.controller.log(f"Addon stock overlay preload error: {e}")
            self._addon_overlay_cache = {}

        # initial render
        self.update_addon_states()
        self.render_summary()

    def toggle_addon(self, key):
        self.controller.log(f"Clicked addon: {key}")

        item = self.controller.addons.get(key)
        if not item:
            self.controller.log(f"Unknown addon key: {key}")
            return

        if item.get("stock", 0) <= 0:
            self.controller.log(f"{item['name']} is out of stock — ignoring selection")
            return

        if key in self.controller.selected_addons:
            self.controller.selected_addons.remove(key)
            self.controller.log(f"Removed addon {key}")
        else:
            self.controller.selected_addons.add(key)
            self.controller.log(f"Added addon {key}")

        self.update_addon_states()
        self.render_summary()

    def update_addon_states(self):
        # remove previous selection overlays
        try:
            self.canvas.delete(self.sel_overlay_tag)
        except Exception:
            pass

        # remove previous stock overlays
        try:
            for items in getattr(self, "_addon_overlay_items", {}).values():
                for it in items:
                    safe_delete(self.canvas, it)
        except Exception:
            pass
        self._addon_overlay_items = {}

        for key, (x1, y1, x2, y2) in self.addon_zones.items():
            meta = self.controller.addons.get(key, {})
            zone_id = self.addon_zone_items.get(key)

            # out-of-stock overlay
            if meta.get("stock", 0) <= 0:
                photo = self._addon_overlay_cache.get(key)
                if photo is not None:
                    item = self.canvas.create_image(0, 0, anchor="nw", image=photo)
                    try:
                        self.canvas.itemconfigure(item, state="disabled")
                    except Exception:
                        pass
                    self._addon_overlay_items.setdefault(key, []).append(item)

            # selected outline
            if key in self.controller.selected_addons:
                inset = 4
                sx1, sy1, sx2, sy2 = x1 + inset, y1 + inset, x2 - inset, y2 - inset
                sel_id = self.canvas.create_rectangle(
                    sx1, sy1, sx2, sy2,
                    outline="yellow", width=4,
                    tags=(self.sel_overlay_tag,)
                )
                try:
                    if zone_id:
                        self.canvas.tag_lower(sel_id, zone_id)
                except Exception:
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
        # Back button should check if any add-ons are in stock to decide whether to go back to AddOnScreen or FruitSelectionScreen  
        self.canvas.tag_bind(back_rect, "<Button-1>", lambda e: (self.controller.log("Back pressed on Summary"),
            self.controller.show_frame(AddOnScreen)
            if any(item.get("stock", 0) > 0 for item in self.controller.addons.values())
            else self.controller.show_frame(FruitSelectionScreen)))
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
            if self.controller.busy:
                return

            self.controller.payment_method = "Cash"
            self.cancel_auto_proceed()
            if self.admin_visible:
                self.admin_panel.place_forget()
                self.admin_visible = False
            self.controller.show_loading_gif(self.canvas)

            def _on_success():
                self.controller.hide_loading_gif()
                self.controller.show_frame(ProcessingScreen, pause=True, skip_error_check=True)

            def _on_error(err):
                self.controller.hide_loading_gif()
                self.controller.log(f"CashMethod: sale failed: {err}")

            self.controller.start_sale_recording(
                on_success=_on_success,
                on_error=_on_error,
            )

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

    def _cash_sale_done(self, err):
        self.controller.hide_loading_gif()
        if err:
            self.controller.log(f"CashMethod: sale failed: {err}")
            return
        self.controller.refresh_after_sale()
        self.controller.show_frame(ProcessingScreen, pause=True, skip_error_check=True)

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
        if self.controller.busy:
            return

        self.controller.log("I PAID pressed (Paypal) — recording sale and proceeding to Processing")
        self.controller.payment_method = "PayPal"
        self.controller.show_loading_gif(self.canvas)

        def _on_success():
            self.controller.hide_loading_gif()
            self.controller.show_frame(ProcessingScreen, pause=True, skip_error_check=True)

        def _on_error(err):
            self.controller.hide_loading_gif()
            self.controller.log(f"PaypalMethod: sale failed: {err}")

        self.controller.start_sale_recording(
            on_success=_on_success,
            on_error=_on_error,
        )

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
        self.bar_x1, self.bar_y1, self.bar_x2, self.bar_y2 = (137, 156, 887, 315)
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
            stroke_fill="#FF3463",             # outline color (black)
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
            stroke_fill="#FF3463",
            mode="pillow",
            anchor="center",
            pillow_font_path=FONT_INTER
        )

        # Summary bar (kept)
        self.summary = SummaryBar(self, parent_canvas=self.canvas, x=SCREEN_W//2, y=560)
        # vertical progress line (behind handle)
        self.line_id = None
        self.line_photo = None
        try:
            line_path = os.path.join(ASSETS_DIR, "progressLine.png")
            if os.path.exists(line_path):
                line_img = Image.open(line_path).convert("RGBA")
                target_h = bar_h
                aspect = line_img.width / line_img.height
                new_w = int(target_h * aspect)
                line_img = line_img.resize((new_w, target_h), Image.LANCZOS)
                self.line_photo = ImageTk.PhotoImage(line_img)
                # initial placement (left edge of bar)
                lx = self.bar_x1
                ly = (self.bar_y1 + self.bar_y2) // 2
                self.line_id = self.canvas.create_image(lx, ly, image=self.line_photo)
        except Exception as e:
            self.controller.log(f"Couldn't load progressLine: {e}")
            self.line_id = None
            self.line_photo = None

        # Handle: support swapping handle images by process and snapping rotation
        self.handle_id = None
        self.handle_base_orig = None     # current base PIL image for the handle (unrotated)
        self.handle_rot_photo = None     # current rotated PhotoImage shown on canvas
        self.handle_imgs_by_segment = {}  # mapping segment_index -> PIL image (original)
        # attempt to load a generic handle plus per-segment handle images if present
        try:
            # load a default generic handle if available
            default_path = os.path.join(ASSETS_DIR, "progressHandle.png")
            if os.path.exists(default_path):
                h_img = Image.open(default_path).convert("RGBA")
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
                    img = Image.open(p).convert("RGBA")
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

            if self.line_id:
                line_x = self.bar_x1 + int(reveal_ratio * (self.bar_x2 - self.bar_x1))
                line_y = (self.bar_y1 + self.bar_y2) // 2
                self.canvas.coords(self.line_id, line_x, line_y)
                # ensure line is below handle (optional if created earlier):
                self.canvas.tag_lower(self.line_id, self.handle_id)

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
        self.controller.show_frame(OrderCompleteScreen, timeout_ms=self.controller.default_timeout_ms * 2, skip_error_check=True)

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

        self.bg_img = load_image_tk("errorScreen.png", resize_to=(SCREEN_W, SCREEN_H))
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_img)

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
        self.admin_panel.visible = False

        self.admin_panel = AdminPanel(
            self,
            self.controller,
            fruit_screen_cls=FruitSelectionScreen,
            width=750,
            height=575,
            show_recheck_stock=True,
            return_to_cls=WelcomeScreen,
        )
        self.admin_panel.place(relx=0.5, rely=0.5, anchor="center")
        self.admin_panel.hide()

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
            self.admin_panel.toggle()
            return "break"

        # schedule reset
        self._admin_tap_reset_job = self.after(1000, self._reset_admin_tap_count)
        return "break"

    def _reset_admin_tap_count(self):
        self._admin_tap_count = 0
        self._admin_tap_reset_job = None
        self.controller.log("Error admin tap count reset")
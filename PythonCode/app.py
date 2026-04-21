# app.py
import os
import time
import math
import uuid
import tkinter as tk
import queue
import threading
import requests

from PIL import Image, ImageTk
from dotenv import load_dotenv
from supabase import create_client
from supabase.client import ClientOptions
from ui_common import SCREEN_W, SCREEN_H, load_gif_frames
from local_db import LocalDB
# Enable for RPI GPIO support, comment out for testing on non-RPI platforms
from hardware import HardwareManager 
from hardware import MachineController

from ui_common import (
    money_str,
    amount_str,
    TouchFeedbackManager,
    OutlinedText,
    FONT_INTER,
    file_exists,
)
from screens import (
    WelcomeScreen,
    FruitSelectionScreen,
    AddOnScreen,
    SummaryScreen,
    PaymentSelectionScreen,
    CashMethodScreen,
    PaypalMethodScreen,
    ProcessingScreen,
    OrderCompleteScreen,
    ErrorScreen,
)

load_dotenv()
url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_KEY"]
supabase = create_client(url, key, options=ClientOptions(
        postgrest_client_timeout=20,
        storage_client_timeout=20,
        schema="public",
    ),)

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fruit Shake Vending Machine")
        self.geometry(f"{SCREEN_W}x{SCREEN_H}")
        self.resizable(False, False)
        # self.attributes('-fullscreen', True) # Enable for RPI

        # debug / logging
        self.debug_mode = False
        self._debug_lines = []
        self.debug_widget = None
        self._main_thread_ident = threading.get_ident()
        self.bind_all("<Key-d>", lambda e: self.toggle_debug())
        self.bind_all("<Key-D>", lambda e: self.toggle_debug())

        self.touch_feedback = TouchFeedbackManager(self)
        self.supabase = create_client(url, key)
        self.local_db = LocalDB()

        # data containers must exist before any online/offline load path
        self.catalog = {}
        self.addons = {}
        self.ingredients = {}

        # Load startup data before building the UI
        self.load_remote_data()
        self.sync_pending_sales()

        # Database Payment tracking
        self.payment_method = None

        # Track total income
        self.total_income = 0.0

        # user selections
        self.selected_fruits = []
        self.max_fruits = 3
        self.selected_addons = set()
        self.selected_ratio = None

        # inactivity timer
        self.default_timeout_ms = 30000 # 120000 (base value)
        self.timeout_warning_ms = 20000 # 60000 (base value, show warning when 1 minute remains)
        self.timeout_countdown_ms = 10000        # switch to countdown at 10 seconds remaining
        self.timeout_warning_poll_ms = 500       # warning state refresh interval
        self.active_timeout_ms = self.default_timeout_ms
        self.timer_id = None
        self.timeout_warning_job = None
        self.timeout_deadline_ms = None
        self.current_frame = None
        self.timeout_warning_visible = False
        self.timeout_warning_layers = {}

        # UI container & frames
        container = tk.Frame(self)
        container.pack(fill="both", expand=True)
        container.grid_rowconfigure(0, weight=1)
        container.grid_columnconfigure(0, weight=1)

        self.busy = False
        self.loading_frames, self.loading_delays = load_gif_frames("loading.gif", resize_to=(250, 250))
        self.loading_canvas = None
        self.loading_item = None
        self.loading_job = None
        self.loading_frame_index = 0

        overlay_img = Image.new("RGBA", (SCREEN_W, SCREEN_H), (0, 0, 0, 180))
        self.loading_overlay_photo = ImageTk.PhotoImage(overlay_img)
        self.loading_overlay_item = None

        # Timeout warning visuals
        timeout_dim_img = Image.new("RGBA", (SCREEN_W, SCREEN_H), (0, 0, 0, 120))
        self.timeout_dim_photo = ImageTk.PhotoImage(timeout_dim_img)

        self.timeout_border_photo = None
        if file_exists("timeoutBorder.png"):
            try:
                border = Image.open(os.path.join("assets", "timeoutBorder.png")).convert("RGBA")
                border = border.resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
                self.timeout_border_photo = ImageTk.PhotoImage(border)
            except Exception as e:
                self.log(f"Failed to load timeoutBorder.png: {e}")
                self.timeout_border_photo = None

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

        self.cash_queue = queue.Queue()
        # Enable for RPI GPIO support, comment out for testing on non-RPI platforms
        self.hardware = HardwareManager(self)
        self.machine = MachineController()
        self.after(50, self._poll_cash_queue)

        # global input bindings to reset timer
        self.bind_all("<Key>", lambda e: self.reset_timer())
        self.bind_all("<Button-1>", lambda e: self.reset_timer())

        # ensure best-sellers are correct on start
        self.update_best_sellers()

        # First Screen shown: Welcome Screen, change for testing
        self.show_frame(WelcomeScreen, pause=True)

    # Database
    def load_remote_data(self):
        self.log("Initializing inventory...")

        # Step 1: check if Supabase is reachable
        if not self.is_supabase_available():
            self.log("Supabase unavailable. Falling back to local database.")
            self.load_from_local_db()
            return
        self.log("Supabase available. Loading remote inventory...")
        # Fruits
        res = self.supabase.table("fruits").select("*").execute()
        fruit_rows = getattr(res, "data", []) or []
        self.log(f"fruits rows returned: {len(fruit_rows)}")

        self.catalog = {}
        for i, row in enumerate(sorted(fruit_rows, key=lambda r: r["id"]), start=1):
            self.log(f"fruit row {i}: {row}")
            try:
                key = f"fruit{i}"
                self.catalog[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "stock": row["stock"],
                    "sales": row["sales"],
                    "best_seller": row.get("best_seller", False),
                    "asset_name": row["asset_name"],
                }
                self.log(f"Loaded fruit key mapping: {key} -> {row['name']} / {row['asset_name']}")
            except Exception as e:
                self.log(f"fruit row {i} could not be loaded: {e}")

        # Add-ons
        res = self.supabase.table("addons").select("*").execute()
        addon_rows = getattr(res, "data", []) or []
        self.log(f"addons rows returned: {len(addon_rows)}")

        self.addons = {}
        for i, row in enumerate(addon_rows, start=1):
            self.log(f"addon row {i}: {row}")
            try:
                key = row["name"].lower().replace(" ", "")
                self.addons[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "stock": row["stock"],
                    "sales": row["sales"],
                }
            except Exception as e:
                self.log(f"addon row {i} could not be loaded: {e}")

        # Ingredients
        res = self.supabase.table("ingredients").select("*").execute()
        ingredient_rows = getattr(res, "data", []) or []
        self.log(f"ingredients rows returned: {len(ingredient_rows)}")

        self.ingredients = {}
        for i, row in enumerate(ingredient_rows, start=1):
            self.log(f"ingredient row {i}: {row}")
            try:
                key = row["name"].lower()
                self.ingredients[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "stock": row["stock"],
                }
            except Exception as e:
                self.log(f"ingredient row {i} could not be loaded: {e}")

        self.log(f"Loaded catalog count: {len(self.catalog)}")
        self.log(f"Loaded addons count: {len(self.addons)}")
        self.log(f"Loaded ingredients count: {len(self.ingredients)}")
        self.log("=== Finished loading remote inventory ===")
        try:
            self.local_db.replace_fruits(self.catalog)
            self.local_db.replace_addons(self.addons)
            self.local_db.replace_ingredients(self.ingredients)
            self.log("Local SQLite inventory snapshot updated.")
        except Exception as e:
            self.log(f"Failed to save startup data to local SQLite: {e}")

    # -------------------------
    # logging / debug helpers
    # -------------------------
    def _append_debug_line(self, line):
        self._debug_lines.append(line)
        if self.debug_widget:
            try:
                self.debug_widget.config(state="normal")
                self.debug_widget.insert("end", line + "\n")
                self.debug_widget.see("end")
                self.debug_widget.config(state="disabled")
            except Exception:
                pass

    def log(self, msg):
        ts = time.strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)

        if threading.get_ident() == getattr(self, "_main_thread_ident", None):
            self._append_debug_line(line)
        else:
            try:
                self.after(0, lambda l=line: self._append_debug_line(l))
            except Exception:
                pass

    def toggle_debug(self):
        if self.debug_widget:
            self.debug_widget.place_forget()
            self.debug_widget = None
            self.debug_mode = False
        else:
            txt = tk.Text(self, width=100, height=12, bg="#111", fg="#0f0")
            txt.insert("end", "\n".join(self._debug_lines[-200:]) + ("\n" if self._debug_lines else ""))
            txt.config(state="disabled")
            txt.place(x=50, y=15)
            self.debug_widget = txt
            self.debug_mode = True

    # -------------------------
    # timeout warning helpers
    # -------------------------
    def _ensure_timeout_warning_ui(self, frame):
        if frame in self.timeout_warning_layers:
            return self.timeout_warning_layers[frame]

        canvas = getattr(frame, "canvas", None)
        if canvas is None:
            return None

        dim_item = canvas.create_image(
            0, 0,
            anchor="nw",
            image=self.timeout_dim_photo
        )
        canvas.itemconfigure(dim_item, state="hidden")
        try:
            canvas.itemconfigure(dim_item, state="disabled")
        except Exception:
            pass

        border_item = None
        if self.timeout_border_photo is not None:
            border_item = canvas.create_image(
                0, 0,
                anchor="nw",
                image=self.timeout_border_photo
            )
            canvas.itemconfigure(border_item, state="hidden")
            try:
                canvas.itemconfigure(border_item, state="disabled")
            except Exception:
                pass

        text_obj = OutlinedText(
            canvas,
            SCREEN_W // 2,
            520,   # same general area as fruit error text
            text="",
            font=("Inter", 18),
            fill="#9E9E9E",
            stroke=2,
            stroke_fill="#000000",
            mode="pillow",
            anchor="center",
            pillow_font_path=FONT_INTER
        )
        try:
            if text_obj._ids:
                canvas.itemconfigure(text_obj._ids[0], state="hidden")
                try:
                    canvas.itemconfigure(text_obj._ids[0], state="disabled")
                except Exception:
                    pass
        except Exception:
            pass

        ui = {
            "canvas": canvas,
            "dim_item": dim_item,
            "border_item": border_item,
            "text_obj": text_obj,
        }
        self.timeout_warning_layers[frame] = ui
        return ui

    def _set_timeout_text_visible(self, ui, visible):
        try:
            text_obj = ui["text_obj"]
            if text_obj and text_obj._ids:
                ui["canvas"].itemconfigure(
                    text_obj._ids[0],
                    state="normal" if visible else "hidden"
                )
        except Exception:
            pass

    def show_timeout_warning(self, message):
        frame = self.current_frame
        if frame is None:
            return

        ui = self._ensure_timeout_warning_ui(frame)
        if ui is None:
            return

        try:
            ui["canvas"].itemconfigure(ui["dim_item"], state="normal")
            if ui["border_item"] is not None:
                ui["canvas"].itemconfigure(ui["border_item"], state="normal")

            ui["text_obj"].update(text=message)
            self._set_timeout_text_visible(ui, True)

            ui["canvas"].tag_raise(ui["dim_item"])
            if ui["border_item"] is not None:
                ui["canvas"].tag_raise(ui["border_item"])
            if ui["text_obj"]._ids:
                ui["canvas"].tag_raise(ui["text_obj"]._ids[0])

            self.timeout_warning_visible = True
        except Exception as e:
            self.log(f"show_timeout_warning failed: {e}")

    def hide_timeout_warning(self):
        for ui in self.timeout_warning_layers.values():
            try:
                ui["canvas"].itemconfigure(ui["dim_item"], state="hidden")
            except Exception:
                pass
            try:
                if ui["border_item"] is not None:
                    ui["canvas"].itemconfigure(ui["border_item"], state="hidden")
            except Exception:
                pass
            self._set_timeout_text_visible(ui, False)

        self.timeout_warning_visible = False

    def _cancel_timeout_warning_job(self):
        if self.timeout_warning_job:
            try:
                self.after_cancel(self.timeout_warning_job)
            except Exception:
                pass
            self.timeout_warning_job = None

    def _schedule_timeout_warning_poll(self):
        self._cancel_timeout_warning_job()

        if not (isinstance(self.active_timeout_ms, int) and self.active_timeout_ms > 0):
            return

        self.timeout_warning_job = self.after(
            self.timeout_warning_poll_ms,
            self._poll_timeout_warning
        )

    def _poll_timeout_warning(self):
        self.timeout_warning_job = None

        if not (isinstance(self.active_timeout_ms, int) and self.active_timeout_ms > 0):
            self.hide_timeout_warning()
            return

        if self.timeout_deadline_ms is None:
            self.hide_timeout_warning()
            return

        remaining_ms = max(0, int(self.timeout_deadline_ms - (time.monotonic() * 1000)))

        if remaining_ms <= 0:
            self.hide_timeout_warning()
            return

        if remaining_ms <= self.timeout_warning_ms:
            if remaining_ms <= self.timeout_countdown_ms:
                seconds_left = max(1, math.ceil(remaining_ms / 1000))
                message = f"Returning to home in {seconds_left}..."
            else:
                message = "Returning to home soon if no activity is detected."

            self.show_timeout_warning(message)
        else:
            self.hide_timeout_warning()

        self._schedule_timeout_warning_poll()

    # -------------------------
    # best-seller / stock / sales helpers
    # -------------------------
    def _compute_best_seller_flags(self, catalog_snapshot=None):
        catalog_snapshot = self.catalog if catalog_snapshot is None else catalog_snapshot
        sales_values = [item.get("sales", 0) for item in catalog_snapshot.values()]
        if not sales_values:
            return {}, 0

        max_sales = max(sales_values)
        flags = {
            key: (item.get("sales", 0) == max_sales and max_sales > 0)
            for key, item in catalog_snapshot.items()
        }
        return flags, max_sales

    def update_best_sellers(self, sync_remote=False):
        """Set catalog[*]['best_seller'] True for fruit(s) with the highest sales (>0)."""
        flags, max_sales = self._compute_best_seller_flags()
        if not flags:
            return

        for key, is_best in flags.items():
            self.catalog[key]["best_seller"] = is_best

        self.log(f"Best-seller updated (max sales={max_sales})")

        if not sync_remote:
            return

        if not self.is_supabase_available():
            self.log("Supabase unavailable; skipping best-seller sync.")
            return

        try:
            for key, fruit in self.catalog.items():
                self.supabase.table("fruits").update({
                    "best_seller": fruit["best_seller"]
                }).eq("id", fruit["id"]).execute()
        except Exception as e:
            self.log(f"Failed to sync best-seller flags to Supabase: {e}")

    def sync_pending_sales(self):
        if not self.is_supabase_available():
            self.log("Sync skipped: Supabase unavailable.")
            return

        rows = self.local_db.get_pending_sales()

        if not rows:
            self.log("No pending sales to sync.")
            return

        self.log(f"Syncing {len(rows)} pending sales...")

        for r in rows:
            try:
                fruits = r["selected_fruits"].split(",") if r["selected_fruits"] else []
                addons = r["selected_addons"].split(",") if r["selected_addons"] else []

                self.supabase.table("sales").insert({
                    "sale_id": r["sale_id"],
                    "total_price": r["total_price"],
                    "payment_method": r["payment_method"],
                    "selected_fruits": ", ".join(
                        self.catalog[k]["name"] for k in fruits if k in self.catalog
                    ),
                    "selected_addons": ", ".join(
                        self.addons[k]["name"] for k in addons if k in self.addons
                    ) if addons else None,
                }).execute()

                self.local_db.mark_sale_synced(r["sale_id"])
                self.log(f"Synced sale: {r['sale_id']}")

            except Exception as e:
                self.local_db.mark_sale_error(r["sale_id"], str(e))
                self.log(f"Sync failed for {r['sale_id']}: {e}")

        self.local_db.delete_old_synced(keep_latest=5)
        self.log("Sync complete.")

    def _build_sale_snapshot(self):
        return {
            "payment_method": self.payment_method or "Unknown",
            "selected_fruits": list(self.selected_fruits),
            "selected_addons": sorted(self.selected_addons),
        }

    def _record_sale_worker(self, snapshot):
        try:
            selected_fruits = snapshot["selected_fruits"]
            selected_addons = snapshot["selected_addons"]
            payment_method = snapshot["payment_method"]

            total = self.calculate_total_for_selection(
                selected_fruits,
                selected_addons,
                emit_log=False
            )

            self.log(f"Recording sale for: {selected_fruits}")
            self.log(f"Recording sale for add-ons: {selected_addons}")

            # -------------------------
            # STEP 1: BUILD SALE ROW
            # -------------------------
            sale_row = {
                "sale_id": str(uuid.uuid4()),
                "total_price": total,
                "payment_method": payment_method,
                "selected_fruits": selected_fruits,
                "selected_addons": selected_addons,
            }

            # -------------------------
            # STEP 2: SAVE LOCALLY FIRST
            # -------------------------
            try:
                self.local_db.insert_sale(sale_row)
                self.log(f"Sale saved locally: {sale_row['sale_id']}")
            except Exception as e:
                self.log(f"Local sale save FAILED: {e}")
                raise

            # -------------------------
            # STEP 3: UPDATE LOCAL MEMORY
            # -------------------------
            for key in selected_fruits:
                if key in self.catalog:
                    self.catalog[key]["stock"] = max(0, self.catalog[key]["stock"] - 1)
                    self.catalog[key]["sales"] += 1

            for key in selected_addons:
                if key in self.addons:
                    self.addons[key]["stock"] = max(0, self.addons[key]["stock"] - 1)
                    self.addons[key]["sales"] += 1

            for key in self.ingredients:
                self.ingredients[key]["stock"] = max(0, self.ingredients[key]["stock"] - 1)

            # persist updated inventory locally
            try:
                self.local_db.replace_fruits(self.catalog)
                self.local_db.replace_addons(self.addons)
                self.local_db.replace_ingredients(self.ingredients)
            except Exception as e:
                self.log(f"Local inventory save failed: {e}")

            # -------------------------
            # STEP 4: TRY SUPABASE (OPTIONAL)
            # -------------------------
            if not self.is_supabase_available():
                self.log("Offline mode: sale queued locally.")
                return {
                    "catalog": self.catalog,
                    "addons": self.addons,
                    "ingredients": self.ingredients,
                    "total_income_delta": total,
                    "payment_method": payment_method,
                }

            try:
                # insert sale to Supabase
                self.supabase.table("sales").insert({
                    "sale_id": sale_row["sale_id"],
                    "total_price": total,
                    "payment_method": payment_method,
                    "selected_fruits": ", ".join(self.catalog[k]["name"] for k in selected_fruits),
                    "selected_addons": ", ".join(self.addons[k]["name"] for k in selected_addons) if selected_addons else None,
                }).execute()

                self.log("Sale synced to Supabase.")

            except Exception as e:
                self.log(f"Supabase sync failed (kept local): {e}")

            return {
                "catalog": self.catalog,
                "addons": self.addons,
                "ingredients": self.ingredients,
                "total_income_delta": total,
                "payment_method": payment_method,
            }

        except Exception as e:
            self.log(f"_record_sale_worker crash: {e}")

    def apply_sale_result(self, result):
        self.catalog = result["catalog"]
        self.addons = result["addons"]
        self.ingredients = result["ingredients"]
        self.total_income += result["total_income_delta"]
        self.payment_method = result.get("payment_method")
        self.refresh_after_sale()

    def record_sale(self, refresh_ui=True):
        snapshot = self._build_sale_snapshot()

        if not refresh_ui:
            return self._record_sale_worker(snapshot)

        result = self._record_sale_worker(snapshot)
        self.apply_sale_result(result)
        return result

    def start_sale_recording(self, *, on_success=None, on_error=None):
        snapshot = self._build_sale_snapshot()

        def task():
            return self._record_sale_worker(snapshot)

        def done(err, result=None):
            if err:
                if on_error:
                    on_error(err)
                return

            self.apply_sale_result(result)
            if on_success:
                on_success()

        self.run_async(task, on_done=done)

    # -------------------------
    # frame switching & timer
    # -------------------------
    def show_frame(self, cls, timeout_ms=None, pause=False, skip_error_check=False):
        if self.busy and cls is not ProcessingScreen:
            return
        frame = self.frames[cls]

        # BEFORE we raise the requested frame, check global error state
        if not skip_error_check and cls is not ErrorScreen and self.check_error_state():
            self.log("Error detected: switching to ErrorScreen")
            self.show_frame(ErrorScreen, pause=True, skip_error_check=True)
            return

        frame = self.frames[cls]
        self.current_frame = frame
        self.hide_timeout_warning()
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

        self._cancel_timeout_warning_job()
        self.hide_timeout_warning()
        self.timeout_deadline_ms = None

        if isinstance(self.active_timeout_ms, int) and self.active_timeout_ms > 0:
            self.timeout_deadline_ms = (time.monotonic() * 1000) + self.active_timeout_ms
            self.timer_id = self.after(self.active_timeout_ms, self.on_timeout)
            self._schedule_timeout_warning_poll()

        try:
            self.log(f"reset_timer: active_timeout_ms={self.active_timeout_ms}, timer_id={self.timer_id}")
        except Exception:
            pass

    def pause_inactivity(self):
        self.active_timeout_ms = None
        self.timeout_deadline_ms = None

        if getattr(self, "timer_id", None):
            try:
                self.after_cancel(self.timer_id)
            except Exception:
                pass
            self.timer_id = None

        self._cancel_timeout_warning_job()
        self.hide_timeout_warning()

    def resume_inactivity(self, timeout_ms=None):
        self.active_timeout_ms = timeout_ms if timeout_ms is not None else self.default_timeout_ms
        self.reset_timer()

    def on_timeout(self):
        if self.busy:
            return

        self.hide_timeout_warning()
        self.log("Inactivity timeout — returning to WelcomeScreen and clearing selections")
        self.selected_fruits.clear()
        self.selected_addons.clear()
        self.selected_ratio = None
        self.show_frame(WelcomeScreen, pause=True)

    def calculate_total_for_selection(self, fruits=None, addons=None, *, emit_log=True):
        fruits = list(self.selected_fruits if fruits is None else fruits)
        addons = set(self.selected_addons if addons is None else addons)

        fruit_total = sum(self.catalog[k]["price"] for k in fruits)
        addon_total = sum(self.addons[k]["price"] for k in addons)
        base_total = 50

        fruit_count = len(fruits)

        # Reduce price based on amount of fruit selected
        fruit_discount = {
            1: 1.00,  # no discount
            2: 0.80,
            3: 0.60,
        }.get(fruit_count, 1.00)

        discounted_fruit_total = fruit_total * fruit_discount
        if emit_log:
            self.log(
                "Original Amount: "
                + money_str(base_total + fruit_total + addon_total)
                + "| Discounted Amount: "
                + money_str(base_total + discounted_fruit_total + addon_total)
            )
        # round up to peso dahil sino naman nagdadala ng centavos
        return math.ceil(base_total + discounted_fruit_total + addon_total)

    def calculate_total(self):
        return self.calculate_total_for_selection()
        
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
    
    def queue_cash(self, amount):
        self.log(f"queue_cash: received amount ₱{float(amount):.2f}")
        self.cash_queue.put(amount)

    def _poll_cash_queue(self):
        try:
            while True:
                amount = self.cash_queue.get_nowait()
                self.log(f"_poll_cash_queue: dequeued ₱{float(amount):.2f}")

                cash_screen = self.frames.get(CashMethodScreen)
                if cash_screen:
                    self.log("_poll_cash_queue: forwarding amount to CashMethodScreen.add_cash()")
                    cash_screen.add_cash(amount)
                else:
                    self.log("_poll_cash_queue: CashMethodScreen not found")
        except queue.Empty:
            pass
        except Exception as e:
            self.log(f"_poll_cash_queue error: {e}")

        self.after(50, self._poll_cash_queue)

    def show_loading_gif(self, canvas):
        self.busy = True
        self.pause_inactivity()
        self.loading_canvas = canvas
        self.loading_frame_index = 0

        if self.loading_overlay_photo is not None:
            self.loading_overlay_item = canvas.create_image(
                0,
                0,
                anchor="nw",
                image=self.loading_overlay_photo,
            )

        if not self.loading_frames:
            return

        self.loading_item = canvas.create_image(
            SCREEN_W // 2,
            SCREEN_H // 2,
            anchor="center",
            image=self.loading_frames[0],
        )
        self._animate_loading_gif()

    def _animate_loading_gif(self):
        if not self.busy or not self.loading_canvas or not self.loading_frames:
            return

        self.loading_frame_index = (self.loading_frame_index + 1) % len(self.loading_frames)
        frame = self.loading_frames[self.loading_frame_index]
        delay = self.loading_delays[self.loading_frame_index] if self.loading_delays else 80

        try:
            self.loading_canvas.itemconfigure(self.loading_item, image=frame)
        except Exception:
            return

        self.loading_job = self.loading_canvas.after(delay, self._animate_loading_gif)

    def hide_loading_gif(self):
        self.busy = False

        if self.loading_canvas and self.loading_job:
            try:
                self.loading_canvas.after_cancel(self.loading_job)
            except Exception:
                pass

        if self.loading_canvas and self.loading_item:
            try:
                self.loading_canvas.delete(self.loading_item)
            except Exception:
                pass

        if self.loading_canvas and self.loading_overlay_item:
            try:
                self.loading_canvas.delete(self.loading_overlay_item)
            except Exception:
                pass

        self.loading_canvas = None
        self.loading_item = None
        self.loading_overlay_item = None
        self.loading_job = None
        self.resume_inactivity()

    def run_async(self, task, on_done=None):
        def worker():
            err = None
            result = None
            try:
                result = task()
            except Exception as e:
                err = e

            def finish():
                if on_done:
                    try:
                        on_done(err, result)
                    except TypeError:
                        on_done(err)

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_after_sale(self):
        fs = self.frames.get(FruitSelectionScreen)
        if fs:
            try:
                fs.update_fruit_states()
                fs.update_overlays()
                fs.render_summary()
            except Exception:
                pass

        ads = self.frames.get(AddOnScreen)
        if ads:
            try:
                ads.update_addon_states()
                ads.render_summary()
            except Exception:
                pass

    def is_supabase_available(self) -> bool:
        try:
            # lightweight check (fast fail if offline)
            self.supabase.table("fruits").select("id").limit(1).execute()
            return True
        except Exception as e:
            self.log(f"Supabase not available: {e}")
            return False
        
    def load_from_local_db(self):
        self.log("Loading inventory from local SQLite...")

        try:
            # Fruits
            self.catalog.clear()
            fruit_rows = self.local_db.load_fruits()
            for i, row in enumerate(fruit_rows, start=1):
                key = f"fruit{i}"
                self.catalog[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "stock": row["stock"],
                    "sales": row["sales"],
                    "best_seller": bool(row["best_seller"]),
                    "asset_name": row["asset_name"],
                }

            # Add-ons
            self.addons.clear()
            addon_rows = self.local_db.load_addons()
            for row in addon_rows:
                key = row["name"].lower().replace(" ", "")
                self.addons[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "price": row["price"],
                    "stock": row["stock"],
                    "sales": row["sales"],
                }

            # Ingredients
            self.ingredients.clear()
            ingredient_rows = self.local_db.load_ingredients()
            for row in ingredient_rows:
                key = row["name"].lower()
                self.ingredients[key] = {
                    "id": row["id"],
                    "name": row["name"],
                    "stock": row["stock"],
                }

            self.log(f"Loaded local fruits count: {len(self.catalog)}")
            self.log(f"Loaded local addons count: {len(self.addons)}")
            self.log(f"Loaded local ingredients count: {len(self.ingredients)}")
            self.log("Loaded inventory from local SQLite successfully.")

        except Exception as e:
            self.log(f"Failed to load from local DB: {e}")

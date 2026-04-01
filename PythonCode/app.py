# app.py
import os
import time
import math
import uuid
import tkinter as tk
import queue

from dotenv import load_dotenv
from supabase import create_client
from supabase.client import ClientOptions
from ui_common import SCREEN_W, SCREEN_H
# from hardware import HardwareManager # Enable for RPI GPIO support, comment out for testing on non-RPI platforms

from ui_common import money_str, amount_str, TouchFeedbackManager
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
        self.bind_all("<Key-d>", lambda e: self.toggle_debug())
        self.bind_all("<Key-D>", lambda e: self.toggle_debug())

        self.touch_feedback = TouchFeedbackManager(self)
        self.supabase = create_client(url, key)

        # Load remote data before building the UI
        self.load_remote_data()

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

        self.cash_queue = queue.Queue()
        # self.hardware = HardwareManager(self) # Enable for RPI GPIO support, comment out for testing on non-RPI platforms
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
        self.log("=== Loading remote inventory from Supabase ===")

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
            txt = tk.Text(self, width=100, height=12, bg="#111", fg="#0f0")
            txt.insert("end", "\n".join(self._debug_lines[-200:]) + ("\n" if self._debug_lines else ""))
            txt.config(state="disabled")
            txt.place(x=50, y=15)
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

        for key, fruit in self.catalog.items():
            self.supabase.table("fruits").update({
                "best_seller": fruit["best_seller"]
            }).eq("id", fruit["id"]).execute()

    def record_sale(self):
        self.log(f"Recording sale for: {self.selected_fruits}")
        self.log(f"Recording sale for add-ons: {list(self.selected_addons)}")

        # Fruits
        for k in self.selected_fruits:
            item = self.catalog.get(k)
            if not item:
                continue

            item["stock"] = max(0, item.get("stock", 0) - 1)
            item["sales"] = item.get("sales", 0) + 1

            # SAVE TO SUPABASE
            self.supabase.table("fruits").update({
                "stock": item["stock"],
                "sales": item["sales"]
            }).eq("id", item["id"]).execute()
        # Add-ons
        for k in self.selected_addons:
            item = self.addons.get(k)
            if not item:
                continue

            item["stock"] = max(0, item.get("stock", 0) - 1)
            item["sales"] = item.get("sales", 0) + 1

            self.supabase.table("addons").update({
                "stock": item["stock"],
                "sales": item["sales"]
            }).eq("id", item["id"]).execute()
        # Ingredients
        for k, item in self.ingredients.items():
            item["stock"] = max(0, item.get("stock", 0) - 1)

            self.supabase.table("ingredients").update({
                "stock": item["stock"]
            }).eq("id", item["id"]).execute()
        # Income
        total = self.calculate_total()
        self.total_income += total
        self.log("Added Income: " + money_str(total))

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

        sale_row = {
        "sale_id": str(uuid.uuid4()),
        "total_price": total,
        "payment_method": self.payment_method or "Unknown",
        "selected_fruits": ", ".join(self.catalog[k]["name"] for k in self.selected_fruits),
        "selected_addons": ", ".join(self.addons[k]["name"] for k in self.selected_addons) if self.selected_addons else None,
        }

        self.supabase.table("sales").insert(sale_row).execute()

    # -------------------------
    # frame switching & timer
    # -------------------------
    def show_frame(self, cls, timeout_ms=None, pause=False, skip_error_check=False):
        frame = self.frames[cls]

        # BEFORE we raise the requested frame, check global error state
        if not skip_error_check and cls is not ErrorScreen and self.check_error_state():
            self.log("Error detected: switching to ErrorScreen")
            self.show_frame(ErrorScreen, pause=True, skip_error_check=True)
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
        fruit_total = sum(self.catalog[k]["price"] for k in self.selected_fruits)
        addon_total = sum(self.addons[k]["price"] for k in self.selected_addons)
        base_total = 50

        fruit_count = len(self.selected_fruits)

        # Reduce price based on amount of fruit selected
        fruit_discount = {
            1: 1.00,  # no discount
            2: 0.80,  
            3: 0.60,  
        }.get(fruit_count, 1.00)

        discounted_fruit_total = fruit_total * fruit_discount
        self.log("Original Amount: " + money_str(base_total + fruit_total + addon_total) + "| Discounted Amount: " + money_str(base_total + discounted_fruit_total + addon_total))
        # round up to peso dahil sino naman nagdadala ng centavos
        return math.ceil(base_total + discounted_fruit_total + addon_total)
        
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
        self.cash_queue.put(amount)

    def _poll_cash_queue(self):
        try:
            while True:
                amount = self.cash_queue.get_nowait()
                cash_screen = self.frames.get(CashMethodScreen)
                if cash_screen:
                    cash_screen.add_cash(amount)
        except Exception:
            pass

        self.after(50, self._poll_cash_queue)
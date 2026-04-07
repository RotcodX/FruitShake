import tkinter as tk

class AdminPanel(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        *,
        fruit_screen_cls=None,
        width=750,
        height=585,
        show_recheck_stock=True,
        return_to_cls=None,
        title_text="ADMIN PANEL",
        **kwargs
    ):
        super().__init__(
            parent,
            **kwargs,
            width=width,
            height=height,
            bg="#222",
            bd=4,
            relief="raised",
        )
        self.controller = controller
        self.fruit_screen_cls = fruit_screen_cls
        self.panel_width = width
        self.panel_height = height
        self.show_recheck_stock = show_recheck_stock
        self.return_to_cls = return_to_cls
        self.title_text = title_text

        self.visible = False
        self.admin_visible = False  # compatibility alias
        self._fs_btn = None
        self._recheck_btn = None
        self._upload_btn = None
        self._check_machine_btn = None
        self.admin_rows_parent = None

        self._build_ui()

    def _build_ui(self):
        # Clear any previous widgets
        for w in self.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Title
        title = tk.Label(
            self,
            text=self.title_text,
            font=("Arial", 15, "bold"),
            bg="#222",
            fg="white",
        )
        title.place(relx=0.5, y=2, anchor="n")

        # Close button
        close_btn = tk.Button(self, text="Close", command=self.hide)
        close_btn.place(x=self.panel_width - 10, y=0, anchor="ne")

        # Exit button
        exit_btn = tk.Button(self, text="Exit", command=lambda: self.controller.destroy())
        exit_btn.place(x=self.panel_width - 10, y=self.panel_height - 10, anchor="se")

        # Fullscreen toggle
        self._fs_btn = tk.Button(self, text="", command=self._toggle_fullscreen)
        self._fs_btn.place(x=0, y=0, anchor="nw")

        # Bottom-left action buttons
        if self.show_recheck_stock:
            # Recheck stock button, for refresh and exit ng admin panel if stock is OK
            self._recheck_btn = tk.Button(self, text="Recheck Stock", command=self._on_recheck_stock)
            self._recheck_btn.place(x=0, y=self.panel_height - 10, anchor="sw") 
            # Upload stock to database
            self._upload_btn = tk.Button(self, text="Upload Stock", command=self._on_upload_stock)
            self._upload_btn.place(x=120, y=self.panel_height - 10, anchor="sw")
            # Disabled for now since wala pang machine stock checker
            self._check_machine_btn = tk.Button(self, text="Check Machine Stock (test)", command=self._on_check_machine_stock)
            self._check_machine_btn.place(x=240, y=self.panel_height - 10, anchor="sw")
        else:
            self._recheck_btn = None
            self._upload_btn = None
            self._check_machine_btn = None

        # Rows area
        rows_top = 0.075 if self.show_recheck_stock else 0.03
        rows_height = 0.83 if self.show_recheck_stock else 0.90
        rows_frame = tk.Frame(self, bg="#222")
        rows_frame.place(relx=0.5, rely=rows_top, anchor="n", relwidth=0.98, relheight=rows_height)
        self.admin_rows_parent = rows_frame

        self.refresh()

    def show(self, skip_refresh=False):
        if not skip_refresh:
            self.refresh()
        self.place(relx=0.5, rely=0.5, anchor="center")
        self.visible = True
        self.admin_visible = True
        self._update_fs_button_text()

        try:
            self.controller.pause_inactivity()
            self.controller.log("AdminPanel: inactivity paused")
        except Exception:
            pass

    def hide(self):
        self.place_forget()
        self.visible = False
        self.admin_visible = False

        try:
            self.controller.resume_inactivity()
            self.controller.log("AdminPanel: inactivity resumed")
        except Exception:
            pass

    def toggle(self):
        if self.visible:
            self.hide()
        else:
            self.show()

    def refresh(self):
        # keep best-seller flags current before drawing
        try:
            self.controller.update_best_sellers()
        except Exception:
            pass

        self._update_fs_button_text()
        self._refresh_admin_rows()

    def _update_fs_button_text(self):
        if not self._fs_btn:
            return
        try:
            is_fullscreen = bool(getattr(self.controller, "is_fullscreen", False))
            self._fs_btn.config(text="Fullscreen: OFF" if is_fullscreen else "Fullscreen: ON")
        except Exception:
            pass

    def _toggle_fullscreen(self):
        try:
            new_state = not bool(getattr(self.controller, "is_fullscreen", False))
            try:
                self.controller.attributes("-fullscreen", new_state)
            except Exception:
                try:
                    self.controller.attributes("-zoomed", new_state)
                except Exception:
                    pass
            self.controller.is_fullscreen = new_state
            self._update_fs_button_text()
        except Exception as e:
            self.controller.log(f"Failed to toggle fullscreen: {e}")

    def _refresh_admin_rows(self):
        parent = self.admin_rows_parent
        if parent is None:
            return

        for w in parent.winfo_children():
            try:
                w.destroy()
            except Exception:
                pass

        # Header
        hdr = tk.Frame(parent, bg="#222")
        hdr.pack(fill="x", pady=(2, 6))

        tk.Label(hdr, text="Item", width=20, anchor="w", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Stock", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Sales", width=8, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Best", width=6, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)
        tk.Label(hdr, text="Controls", width=28, anchor="center", bg="#333", fg="white").pack(side="left", padx=4)

        # Fruits
        for key, meta in getattr(self.controller, "catalog", {}).items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)

            stock_lbl = tk.Label(row, text=str(meta.get("stock", meta.get("in_stock", ""))), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)

            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)

            best_lbl = tk.Label(row, text="✓" if meta.get("best_seller", False) else "", width=6, anchor="center", bg="#222", fg="#0f0")
            best_lbl.pack(side="left", padx=4)

            controls = tk.Frame(row, bg="#222")
            controls.pack(side="left", padx=4)

            tk.Button(controls, text="-Stock", command=lambda k=key: self._change_fruit_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._change_fruit_stock(k, +1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="-Sales", command=lambda k=key: self._change_fruit_sales(k, -1), width=8).pack(side="left", padx=6)
            tk.Button(controls, text="+Sales", command=lambda k=key: self._change_fruit_sales(k, +1), width=8).pack(side="left", padx=2)

        # Add-ons
        sep = tk.Label(parent, text="Add-Ons", bg="#222", fg="#fff", anchor="w")
        sep.pack(fill="x", pady=(8, 4), padx=6)

        for key, meta in getattr(self.controller, "addons", {}).items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)

            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)

            sales_lbl = tk.Label(row, text=str(meta.get("sales", 0)), width=8, anchor="center", bg="#222", fg="white")
            sales_lbl.pack(side="left", padx=4)

            controls = tk.Frame(row, bg="#222")
            controls.pack(side="left", padx=4)

            tk.Button(controls, text="-Stock", command=lambda k=key: self._change_addon_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._change_addon_stock(k, +1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="-Sales", command=lambda k=key: self._change_addon_sales(k, -1), width=8).pack(side="left", padx=6)
            tk.Button(controls, text="+Sales", command=lambda k=key: self._change_addon_sales(k, +1), width=8).pack(side="left", padx=2)

        # Ingredients
        sep2 = tk.Label(parent, text="Ingredients (stock only)", bg="#222", fg="#fff", anchor="w")
        sep2.pack(fill="x", pady=(8, 4), padx=6)

        for key, meta in getattr(self.controller, "ingredients", {}).items():
            row = tk.Frame(parent, bg="#222")
            row.pack(fill="x", pady=2)

            tk.Label(row, text=meta.get("name", key), width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)

            stock_lbl = tk.Label(row, text=str(meta.get("stock", 0)), width=8, anchor="center", bg="#222", fg="white")
            stock_lbl.pack(side="left", padx=4)

            controls = tk.Frame(row, bg="#222")
            controls.pack(side="left", padx=4)

            tk.Button(controls, text="-Stock", command=lambda k=key: self._change_ingredient_stock(k, -1), width=8).pack(side="left", padx=2)
            tk.Button(controls, text="+Stock", command=lambda k=key: self._change_ingredient_stock(k, +1), width=8).pack(side="left", padx=2)

        # Income
        income_row = tk.Frame(parent, bg="#222")
        income_row.pack(fill="x", pady=(8, 2))

        tk.Label(income_row, text="Total Income:", width=20, anchor="w", bg="#222", fg="white").pack(side="left", padx=4)
        tk.Label(
            income_row,
            text=f"{getattr(self.controller, 'total_income', 0.0):.2f}",
            width=12,
            anchor="w",
            bg="#222",
            fg="#FFD700",
        ).pack(side="left", padx=4)

        tk.Button(income_row, text="Reset Income", command=self._reset_income, width=12).pack(side="left", padx=6)

    def _refresh_fruit_screen(self):
        fs = self.controller.frames.get(self.fruit_screen_cls)
        if fs:
            try:
                fs.update_best_sellers() if hasattr(fs, "update_best_sellers") else None
            except Exception:
                pass
            try:
                fs.update_overlays()
            except Exception:
                pass
            try:
                fs.render_summary()
            except Exception:
                pass

    def _refresh_related_ui(self):
        self._refresh_fruit_screen()

        # Simpler fallback: scan frames for any visible admin_panel attribute
        try:
            for frame in getattr(self.controller, "frames", {}).values():
                panel = getattr(frame, "admin_panel", None)
                if panel is not None and panel is not self:
                    try:
                        panel.refresh()
                    except Exception:
                        pass
        except Exception:
            pass

    def _change_fruit_stock(self, key, delta):
        item = self.controller.catalog.get(key)
        if not item:
            return
        item["stock"] = max(0, int(item.get("stock", 0)) + delta)
        self.controller.log(f"Admin changed stock for {key}: {delta} -> {item['stock']}")
        self.controller.update_best_sellers()
        self._refresh_fruit_screen()
        self.refresh()

    def _change_fruit_sales(self, key, delta):
        item = self.controller.catalog.get(key)
        if not item:
            return
        item["sales"] = max(0, int(item.get("sales", 0)) + delta)
        self.controller.log(f"Admin changed sales for {key}: {delta} -> {item['sales']}")
        self.controller.update_best_sellers()
        self._refresh_fruit_screen()
        self.refresh()

    def _change_addon_stock(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["stock"] = max(0, int(item.get("stock", 0)) + delta)
        self.controller.log(f"Admin changed addon stock for {key}: {delta} -> {item['stock']}")
        self.refresh()

    def _change_addon_sales(self, key, delta):
        item = self.controller.addons.get(key)
        if not item:
            return
        item["sales"] = max(0, int(item.get("sales", 0)) + delta)
        self.controller.log(f"Admin changed addon sales for {key}: {delta} -> {item['sales']}")
        self.refresh()

    def _change_ingredient_stock(self, key, delta):
        item = self.controller.ingredients.get(key)
        if not item:
            return
        item["stock"] = max(0, int(item.get("stock", 0)) + delta)
        self.controller.log(f"Admin changed ingredient stock for {key}: {delta} -> {item['stock']}")
        self.refresh()

    def _reset_income(self):
        self.controller.total_income = 0.0
        self.controller.log("Admin reset total income")
        self.refresh()

    def _upload_stock_worker(self):
        self.controller.log("Admin: uploading panel stock to Supabase")

        # Fruits
        for key, item in self.controller.catalog.items():
            self.controller.supabase.table("fruits").update({
                "stock": item.get("stock", 0),
                "sales": item.get("sales", 0),
                "best_seller": item.get("best_seller", False),
            }).eq("id", item["id"]).execute()

        # Add-ons
        for key, item in self.controller.addons.items():
            self.controller.supabase.table("addons").update({
                "stock": item.get("stock", 0),
                "sales": item.get("sales", 0),
            }).eq("id", item["id"]).execute()

        # Ingredients
        for key, item in self.controller.ingredients.items():
            self.controller.supabase.table("ingredients").update({
                "stock": item.get("stock", 0),
            }).eq("id", item["id"]).execute()

        return True

    def _machine_stock_check_worker(self):
        """
        Placeholder machine-stock check.

        For now this does not read real hardware. It simply returns the current
        in-memory stock values as the "measured" machine stock so the full admin
        flow can be tested before physical stock sensing exists.
        """
        self.controller.log("Admin: checking machine stock (placeholder)")

        measured_catalog = {
            key: int(item.get("stock", 0))
            for key, item in self.controller.catalog.items()
        }
        measured_addons = {
            key: int(item.get("stock", 0))
            for key, item in self.controller.addons.items()
        }
        measured_ingredients = {
            key: int(item.get("stock", 0))
            for key, item in self.controller.ingredients.items()
        }

        return {
            "catalog_stock": measured_catalog,
            "addon_stock": measured_addons,
            "ingredient_stock": measured_ingredients,
        }

    def _apply_machine_stock_result(self, result):
        for key, stock in result.get("catalog_stock", {}).items():
            if key in self.controller.catalog:
                self.controller.catalog[key]["stock"] = max(0, int(stock))

        for key, stock in result.get("addon_stock", {}).items():
            if key in self.controller.addons:
                self.controller.addons[key]["stock"] = max(0, int(stock))

        for key, stock in result.get("ingredient_stock", {}).items():
            if key in self.controller.ingredients:
                self.controller.ingredients[key]["stock"] = max(0, int(stock))

    def _on_recheck_stock(self):
        if self.controller.busy:
            return

        parent_canvas = getattr(self.master, "canvas", None)

        # Hide admin first so the loading GIF is visible on the screen canvas
        was_visible = self.visible
        if was_visible:
            self.hide()

        if parent_canvas is not None:
            self.controller.show_loading_gif(parent_canvas)

        def task():
            self.controller.log("Admin: rechecking stock")
            self.controller.update_best_sellers()
            return True

        def done(err, result=None):
            if parent_canvas is not None:
                self.controller.hide_loading_gif()

            if err:
                self.controller.log(f"Admin recheck failed: {err}")
                if was_visible:
                    self.show(skip_refresh=True)
                    self.refresh()
                return

            self.refresh()

            if self.return_to_cls is not None and not self.controller.check_error_state():
                self.controller.log("Stock OK after recheck")
                try:
                    self.controller.show_frame(self.return_to_cls, pause=True, skip_error_check=True)
                except TypeError:
                    self.controller.show_frame(self.return_to_cls, pause=True)
            else:
                if self.controller.check_error_state():
                    self.controller.log("Stock still invalid — staying on admin panel")
                    self.show(skip_refresh=True)
                else:
                    self.controller.log("Recheck complete")
                    self.show(skip_refresh=True)

                self.refresh()

        self.controller.run_async(task, on_done=done)

    def _on_upload_stock(self):
        if self.controller.busy:
            return

        parent_canvas = getattr(self.master, "canvas", None)
        was_visible = self.visible

        if was_visible:
            self.hide()

        if parent_canvas is not None:
            self.controller.show_loading_gif(parent_canvas)

        def task():
            self.controller.log("Admin: upload stock started")
            self.controller.update_best_sellers()
            return self._upload_stock_worker()

        def done(err, result=None):
            if parent_canvas is not None:
                self.controller.hide_loading_gif()

            if err:
                self.controller.log(f"Admin upload stock failed: {err}")
            else:
                self.controller.log("Admin: upload stock complete")

            if was_visible:
                self.show(skip_refresh=True)
            self.refresh()
            self._refresh_related_ui()

        self.controller.run_async(task, on_done=done)

    def _on_check_machine_stock(self):
        if self.controller.busy:
            return

        parent_canvas = getattr(self.master, "canvas", None)
        was_visible = self.visible

        if was_visible:
            self.hide()

        if parent_canvas is not None:
            self.controller.show_loading_gif(parent_canvas)

        def task():
            result = self._machine_stock_check_worker()
            return result

        def done(err, result=None):
            if parent_canvas is not None:
                self.controller.hide_loading_gif()

            if err:
                self.controller.log(f"Admin machine stock check failed: {err}")
                if was_visible:
                    self.show(skip_refresh=True)
                    self.refresh()
                return

            # Apply the placeholder measured stock to the admin/controller state
            self._apply_machine_stock_result(result)
            self.controller.update_best_sellers()

            self.controller.log("Admin: machine stock check complete (placeholder)")
            self.controller.log("Admin: auto-uploading checked machine stock")

            # Re-show first so the user returns to a normal state after upload completes
            if was_visible:
                self.show(skip_refresh=True)

            # Chain into upload so checked stock is immediately pushed to Supabase
            self.refresh()
            self._refresh_related_ui()
            self._on_upload_stock()

        self.controller.run_async(task, on_done=done)

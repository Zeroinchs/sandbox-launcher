#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import os
import json
import shutil
import uuid

CONFIG_DIR = os.path.expanduser("~/.config/sandbox-launcher")
CONFIG_FILE = os.path.join(CONFIG_DIR, "apps.json")

BG = "#1a1b23"
CARD_BG = "#252732"
CARD_BG_HOVER = "#2e3040"
CARD_BORDER = "#3a3c4d"
CARD_BORDER_HOVER = "#7c5cff"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9179ff"
TEXT_PRIMARY = "#f2f2f5"
TEXT_SECONDARY = "#8a8ca0"
STATUS_OK = "#4ade80"
STATUS_ERR = "#f87171"
DIVIDER = "#2f3140"
DANGER = "#f87171"


def load_apps():
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if not os.path.isfile(CONFIG_FILE):
        return []
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def save_apps(apps):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(apps, f, indent=2)


def default_app():
    return {
        "id": str(uuid.uuid4())[:8],
        "name": "New App",
        "tag": "",
        "desc": "",
        "icon": "🧩",
        "exec_path": "",
        "working_dir": "",
        "net": False,           # True = allow network
        "private": True,        # True = --private=<working_dir>
        "extra_args": "",       # raw extra firejail flags, space separated
    }


class App:
    def __init__(self, root):
        self.root = root
        self.apps = load_apps()
        self.build_ui()

    # ---------- UI scaffolding ----------

    def build_ui(self):
        self.root.title("Sandbox Launcher")
        self.root.configure(bg=BG)
        self.center_window(440, 480)
        self.root.minsize(400, 380)

        header = tk.Frame(self.root, bg=BG)
        header.pack(fill="x", pady=(24, 4))

        tk.Label(
            header, text="Sandbox Launcher", font=("Sans", 17, "bold"),
            bg=BG, fg=TEXT_PRIMARY,
        ).pack()
        tk.Label(
            header, text="Run anything, fully isolated with Firejail",
            font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
        ).pack(pady=(3, 0))

        tk.Frame(self.root, bg=DIVIDER, height=1).pack(fill="x", padx=24, pady=(16, 0))

        # Scrollable card area
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.cards_frame = tk.Frame(self.canvas, bg=BG)

        self.cards_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.create_window((0, 0), window=self.cards_frame, anchor="nw", width=392)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=12)
        scrollbar.pack(side="right", fill="y", pady=12)

        # Footer
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", pady=(0, 18), padx=24)

        self.status_dot = tk.Label(footer, text="●", font=("Sans", 8), bg=BG, fg=TEXT_SECONDARY)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = tk.Label(
            footer, text="Ready", font=("Sans", 8), bg=BG, fg=TEXT_SECONDARY,
        )
        self.status_label.pack(side="left")

        add_btn = tk.Label(
            footer, text="+ Add App", font=("Sans", 9, "bold"),
            bg=BG, fg=ACCENT, cursor="hand2",
        )
        add_btn.pack(side="right")
        add_btn.bind("<Enter>", lambda e: add_btn.config(fg=ACCENT_HOVER))
        add_btn.bind("<Leave>", lambda e: add_btn.config(fg=ACCENT))
        add_btn.bind("<Button-1>", lambda e: self.open_editor(None))

        self.refresh_cards()

    def center_window(self, w, h):
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 3
        self.root.geometry(f"{w}x{h}+{x}+{y}")

    def set_status(self, text, ok=True):
        self.status_dot.config(fg=STATUS_OK if ok else STATUS_ERR)
        self.status_label.config(text=text)

    # ---------- Card rendering ----------

    def refresh_cards(self):
        for w in self.cards_frame.winfo_children():
            w.destroy()

        if not self.apps:
            tk.Label(
                self.cards_frame,
                text="No apps yet.\nClick “+ Add App” to sandbox your first program.",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY, justify="center",
            ).pack(pady=40)
            return

        for app in self.apps:
            card = RoundedCard(self.cards_frame, app, self)
            card.pack(fill="x", pady=6, padx=(0, 20))

    # ---------- Launch logic ----------

    def launch(self, app):
        if shutil.which("firejail") is None:
            self.set_status("firejail not found on PATH", ok=False)
            messagebox.showerror(
                "Missing dependency",
                "firejail is not installed or not on PATH.\n\nInstall it with: paru -S firejail",
            )
            return

        exec_path = app.get("exec_path", "").strip()
        if not exec_path or not os.path.isfile(exec_path):
            self.set_status(f"Executable not found for {app['name']}", ok=False)
            messagebox.showerror("Error", f"Executable not found:\n{exec_path}")
            return

        working_dir = app.get("working_dir", "").strip() or os.path.dirname(exec_path)

        try:
            os.chmod(exec_path, 0o755)
        except OSError:
            pass

        cmd = ["firejail"]
        if not app.get("net", False):
            cmd.append("--net=none")
        if app.get("private", True):
            cmd.append(f"--private={working_dir}")

        extra = app.get("extra_args", "").strip()
        if extra:
            cmd.extend(extra.split())

        # Relative path when using --private, since the sandbox remaps
        # the home dir to working_dir's contents.
        if app.get("private", True):
            rel = os.path.relpath(exec_path, working_dir)
            cmd.append(f"./{rel}")
        else:
            cmd.append(exec_path)

        try:
            subprocess.Popen(cmd, cwd=working_dir)
            self.set_status(f"Launched {app['name']}", ok=True)
        except Exception as e:
            self.set_status(f"Launch failed: {e}", ok=False)
            messagebox.showerror("Launch failed", str(e))

    # ---------- Editor dialog ----------

    def open_editor(self, app):
        is_new = app is None
        data = default_app() if is_new else dict(app)

        win = tk.Toplevel(self.root)
        win.title("Add App" if is_new else "Edit App")
        win.configure(bg=BG)
        win.geometry("380x520")
        win.transient(self.root)
        win.grab_set()

        def field(label_text, key, is_path=False):
            tk.Label(win, text=label_text, font=("Sans", 9), bg=BG, fg=TEXT_SECONDARY, anchor="w").pack(
                fill="x", padx=20, pady=(12, 2)
            )
            row = tk.Frame(win, bg=BG)
            row.pack(fill="x", padx=20)
            var = tk.StringVar(value=str(data.get(key, "")))
            entry = tk.Entry(row, textvariable=var, font=("Sans", 10), bg=CARD_BG, fg=TEXT_PRIMARY,
                              insertbackground=TEXT_PRIMARY, relief="flat")
            entry.pack(side="left", fill="x", expand=True, ipady=4)
            if is_path:
                def browse():
                    path = filedialog.askopenfilename()
                    if path:
                        var.set(path)
                btn = tk.Label(row, text="…", font=("Sans", 10, "bold"), bg=CARD_BG, fg=ACCENT, cursor="hand2")
                btn.pack(side="left", padx=(6, 0), ipadx=8, ipady=4)
                btn.bind("<Button-1>", lambda e: browse())
            return var

        name_var = field("Name", "name")
        tag_var = field("Tag / version (optional)", "tag")
        desc_var = field("Description (optional)", "desc")
        icon_var = field("Icon (single emoji)", "icon")
        exec_var = field("Executable path", "exec_path", is_path=True)
        dir_var = field("Working directory (optional, defaults to exe's folder)", "working_dir")
        extra_var = field("Extra firejail args (optional)", "extra_args")

        # Checkboxes
        cb_frame = tk.Frame(win, bg=BG)
        cb_frame.pack(fill="x", padx=20, pady=(14, 0))

        net_var = tk.BooleanVar(value=data.get("net", False))
        tk.Checkbutton(
            cb_frame, text="Allow network access", variable=net_var,
            bg=BG, fg=TEXT_PRIMARY, selectcolor=CARD_BG, activebackground=BG,
            activeforeground=TEXT_PRIMARY, font=("Sans", 9),
        ).pack(anchor="w")

        private_var = tk.BooleanVar(value=data.get("private", True))
        tk.Checkbutton(
            cb_frame, text="Isolate filesystem to working directory (--private)", variable=private_var,
            bg=BG, fg=TEXT_PRIMARY, selectcolor=CARD_BG, activebackground=BG,
            activeforeground=TEXT_PRIMARY, font=("Sans", 9),
        ).pack(anchor="w")

        # Buttons
        btn_row = tk.Frame(win, bg=BG)
        btn_row.pack(fill="x", padx=20, pady=20, side="bottom")

        def do_save():
            name = name_var.get().strip()
            exec_path = exec_var.get().strip()
            if not name or not exec_path:
                messagebox.showerror("Missing info", "Name and executable path are required.")
                return

            data.update({
                "name": name,
                "tag": tag_var.get().strip(),
                "desc": desc_var.get().strip(),
                "icon": icon_var.get().strip() or "🧩",
                "exec_path": exec_path,
                "working_dir": dir_var.get().strip(),
                "extra_args": extra_var.get().strip(),
                "net": net_var.get(),
                "private": private_var.get(),
            })

            if is_new:
                self.apps.append(data)
            else:
                for i, a in enumerate(self.apps):
                    if a["id"] == data["id"]:
                        self.apps[i] = data
                        break

            save_apps(self.apps)
            self.refresh_cards()
            win.destroy()

        def do_delete():
            if messagebox.askyesno("Delete app", f"Remove '{data['name']}' from the launcher?"):
                self.apps = [a for a in self.apps if a["id"] != data["id"]]
                save_apps(self.apps)
                self.refresh_cards()
                win.destroy()

        save_btn = tk.Label(
            btn_row, text="Save", font=("Sans", 10, "bold"), bg=ACCENT, fg="white",
            cursor="hand2", padx=18, pady=8,
        )
        save_btn.pack(side="right")
        save_btn.bind("<Button-1>", lambda e: do_save())

        if not is_new:
            del_btn = tk.Label(
                btn_row, text="Delete", font=("Sans", 10), bg=BG, fg=DANGER,
                cursor="hand2", padx=10, pady=8,
            )
            del_btn.pack(side="left")
            del_btn.bind("<Button-1>", lambda e: do_delete())


class RoundedCard(tk.Canvas):
    def __init__(self, parent, app, controller, radius=14, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, cursor="hand2", height=92, **kwargs)
        self.app = app
        self.controller = controller
        self.radius = radius
        self.hovered = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self.bind("<Button-3>", self._on_right_click)  # right-click = edit

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 2 or h < 2:
            return

        fill = CARD_BG_HOVER if self.hovered else CARD_BG
        border = CARD_BORDER_HOVER if self.hovered else CARD_BORDER
        self._round_rect(2, 2, w - 2, h - 2, self.radius, fill=fill, outline=border, width=1.5)

        pad = 18
        a = self.app

        self.create_text(pad, pad, text=a.get("icon", "🧩"), font=("Sans", 22), anchor="nw")
        self.create_text(pad + 38, pad + 2, text=a["name"], font=("Sans", 13, "bold"),
                          fill=TEXT_PRIMARY, anchor="nw")
        tag = a.get("tag", "")
        if tag:
            self.create_text(pad + 38, pad + 24, text=tag, font=("Sans", 9),
                              fill=ACCENT_HOVER if self.hovered else ACCENT, anchor="nw")

        badges = []
        badges.append("net" if a.get("net") else "no-net")
        badges.append("isolated" if a.get("private", True) else "shared fs")
        desc = a.get("desc", "") or " · ".join(badges)
        self.create_text(pad, h - pad, text=desc, font=("Sans", 9),
                          fill=TEXT_SECONDARY, anchor="sw")

        arrow_color = ACCENT_HOVER if self.hovered else TEXT_SECONDARY
        self.create_text(w - pad, h - pad, text="Launch  ▶", font=("Sans", 10, "bold"),
                          fill=arrow_color, anchor="se")
        self.create_text(w - pad, pad, text="✎", font=("Sans", 11),
                          fill=TEXT_SECONDARY, anchor="ne")

    def _on_enter(self, _e=None):
        self.hovered = True
        self._redraw()

    def _on_leave(self, _e=None):
        self.hovered = False
        self._redraw()

    def _on_click(self, e=None):
        # Click near the top-right pencil icon = edit, otherwise launch
        w = self.winfo_width()
        if e and e.x > w - 40 and e.y < 40:
            self.controller.open_editor(self.app)
        else:
            self.controller.launch(self.app)

    def _on_right_click(self, _e=None):
        self.controller.open_editor(self.app)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()
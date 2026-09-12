#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import subprocess
import os
import json
import shutil
import uuid
import glob
import webbrowser
import time

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
TAB_ACTIVE = "#7c5cff"
TAB_INACTIVE = "#8a8ca0"

DESKTOP_DIRS = [
    "/usr/share/applications",
    "/usr/local/share/applications",
    os.path.expanduser("~/.local/share/applications"),
]

# Curated catalog of popular apps worth sandboxing.
# We only link to official sites -- we never auto-download or run
# anything from the internet on your behalf.
DISCOVER_CATALOG = [
    {"name": "Firefox", "icon": "🦊", "desc": "Web browser", "url": "https://www.mozilla.org/firefox/"},
    {"name": "Chromium", "icon": "🌐", "desc": "Web browser", "url": "https://www.chromium.org/getting-involved/download-chromium/"},
    {"name": "VLC", "icon": "🎬", "desc": "Media player", "url": "https://www.videolan.org/vlc/"},
    {"name": "OBS Studio", "icon": "🎥", "desc": "Screen recording / streaming", "url": "https://obsproject.com/"},
    {"name": "GIMP", "icon": "🖌️", "desc": "Image editor", "url": "https://www.gimp.org/downloads/"},
    {"name": "Inkscape", "icon": "✏️", "desc": "Vector graphics editor", "url": "https://inkscape.org/release/"},
    {"name": "Discord", "icon": "💬", "desc": "Chat / voice", "url": "https://discord.com/download"},
    {"name": "Telegram", "icon": "✈️", "desc": "Messaging", "url": "https://desktop.telegram.org/"},
    {"name": "Signal", "icon": "🔒", "desc": "Private messaging", "url": "https://signal.org/download/"},
    {"name": "qBittorrent", "icon": "⬇️", "desc": "Torrent client", "url": "https://www.qbittorrent.org/download"},
    {"name": "LibreOffice", "icon": "📄", "desc": "Office suite", "url": "https://www.libreoffice.org/download/download/"},
    {"name": "Blender", "icon": "🧊", "desc": "3D creation suite", "url": "https://www.blender.org/download/"},
    {"name": "VS Code", "icon": "🧑‍💻", "desc": "Code editor", "url": "https://code.visualstudio.com/download"},
    {"name": "Steam", "icon": "🎮", "desc": "Game platform", "url": "https://store.steampowered.com/about/"},
]


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
        "net": False,
        "private": True,
        "extra_args": "",
        "last_launched": 0,
    }


def parse_desktop_file(path):
    """Very small .desktop parser -- just pulls what we need."""
    entry = {"Name": None, "Exec": None, "Comment": "", "NoDisplay": False, "Icon": ""}
    try:
        with open(path, "r", errors="ignore") as f:
            in_main_section = False
            for line in f:
                line = line.strip()
                if line.startswith("[Desktop Entry]"):
                    in_main_section = True
                    continue
                if line.startswith("[") and line != "[Desktop Entry]":
                    in_main_section = False
                    continue
                if not in_main_section or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key == "Name" and entry["Name"] is None:
                    entry["Name"] = value
                elif key == "Exec" and entry["Exec"] is None:
                    entry["Exec"] = value
                elif key == "Comment" and not entry["Comment"]:
                    entry["Comment"] = value
                elif key == "NoDisplay":
                    entry["NoDisplay"] = value.lower() == "true"
                elif key == "Icon" and not entry["Icon"]:
                    entry["Icon"] = value
    except OSError:
        return None

    if not entry["Name"] or not entry["Exec"]:
        return None
    if entry["NoDisplay"]:
        return None

    # Strip desktop file field codes like %u %f %U %F etc.
    exec_clean = entry["Exec"]
    for code in ["%u", "%U", "%f", "%F", "%i", "%c", "%k"]:
        exec_clean = exec_clean.replace(code, "")
    exec_clean = exec_clean.strip()

    return {
        "name": entry["Name"],
        "exec_raw": exec_clean,
        "desc": entry["Comment"],
    }


IGNORE_DIR_NAMES = {"lib", "libs", "renpy", "python2.7", "python3", "site-packages", "__pycache__"}
PRIORITY_EXTENSIONS = [".sh", ".AppImage", ""]  # "" = no extension (common for compiled binaries)


def find_candidate_executables(folder, max_depth=2):
    """
    Scan a folder for the most likely 'this is the thing you run' file.
    Heuristics, not magic -- ranks candidates, lets the caller decide
    when there's more than one plausible answer.
    """
    folder = os.path.abspath(folder)
    candidates = []

    for root_dir, dirnames, filenames in os.walk(folder):
        depth = root_dir[len(folder):].count(os.sep)
        if depth >= max_depth:
            dirnames[:] = []  # don't descend further
        dirnames[:] = [d for d in dirnames if d.lower() not in IGNORE_DIR_NAMES and not d.startswith(".")]

        for fname in filenames:
            fpath = os.path.join(root_dir, fname)
            if not os.path.isfile(fpath):
                continue
            if not os.access(fpath, os.X_OK):
                # Still worth considering .sh files even if the bit isn't set yet
                if not fname.endswith(".sh"):
                    continue

            lower = fname.lower()
            if lower.endswith((".so", ".pyc", ".pyo", ".dll", ".dylib", ".txt", ".log", ".cfg", ".ini", ".json")):
                continue
            if lower in ("uninstall", "uninstall.sh", "updater", "update.sh"):
                continue

            score = 0
            base_no_ext = os.path.splitext(fname)[0].lower()
            folder_name = os.path.basename(folder).lower()

            if fname.endswith(".sh"):
                score += 30
            elif fname.endswith(".AppImage"):
                score += 25
            elif "." not in fname:
                score += 15  # extensionless compiled binary

            if base_no_ext in folder_name or folder_name in base_no_ext:
                score += 20

            # Shallower files are more likely to be the "real" launcher
            score += max(0, 10 - depth * 5)

            if score > 0:
                candidates.append({"path": fpath, "score": score, "rel": os.path.relpath(fpath, folder)})

    candidates.sort(key=lambda c: c["score"], reverse=True)
    return candidates


def scan_installed_apps():
    """Scan standard .desktop dirs and resolve each Exec's binary path."""
    seen_names = set()
    results = []
    for d in DESKTOP_DIRS:
        if not os.path.isdir(d):
            continue
        for path in sorted(glob.glob(os.path.join(d, "*.desktop"))):
            parsed = parse_desktop_file(path)
            if not parsed:
                continue
            if parsed["name"] in seen_names:
                continue

            # Resolve the first token of Exec to a real binary path.
            first_token = parsed["exec_raw"].split()[0] if parsed["exec_raw"] else ""
            first_token = first_token.strip('"')
            resolved = shutil.which(first_token) or (first_token if os.path.isfile(first_token) else None)
            if not resolved:
                continue

            seen_names.add(parsed["name"])
            results.append({
                "name": parsed["name"],
                "desc": parsed["desc"],
                "exec_path": resolved,
                "working_dir": os.path.dirname(resolved),
            })
    return results


class App:
    def __init__(self, root):
        self.root = root
        self.apps = load_apps()
        self.current_tab = "my_apps"
        self.installed_cache = None
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self.render_tab())
        self.build_ui()

    # ---------- window scaffolding ----------

    def build_ui(self):
        self.root.title("Sandbox Launcher")
        self.root.configure(bg=BG)
        self.center_window(480, 560)
        self.root.minsize(420, 420)

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

        # Tab bar + settings menu
        tab_bar = tk.Frame(self.root, bg=BG)
        tab_bar.pack(fill="x", pady=(18, 0), padx=24)

        self.tab_labels = {}
        for key, label in [("my_apps", "My Apps"), ("installed", "Installed"), ("discover", "Discover")]:
            lbl = tk.Label(
                tab_bar, text=label, font=("Sans", 10, "bold"),
                bg=BG, fg=TAB_ACTIVE if key == self.current_tab else TAB_INACTIVE,
                cursor="hand2", padx=10, pady=6,
            )
            lbl.pack(side="left")
            lbl.bind("<Button-1>", lambda e, k=key: self.switch_tab(k))
            self.tab_labels[key] = lbl

        settings_lbl = tk.Label(
            tab_bar, text="⚙", font=("Sans", 13), bg=BG, fg=TEXT_SECONDARY, cursor="hand2",
        )
        settings_lbl.pack(side="right")
        settings_lbl.bind("<Button-1>", lambda e: self.open_settings_menu(settings_lbl))

        # Search box
        search_row = tk.Frame(self.root, bg=BG)
        search_row.pack(fill="x", padx=24, pady=(10, 0))
        search_entry = tk.Entry(
            search_row, textvariable=self.search_var, font=("Sans", 10),
            bg=CARD_BG, fg=TEXT_PRIMARY, insertbackground=TEXT_PRIMARY, relief="flat",
        )
        search_entry.pack(fill="x", ipady=5)
        search_entry.insert(0, "")
        self._search_placeholder(search_entry)

        tk.Frame(self.root, bg=DIVIDER, height=1).pack(fill="x", padx=24, pady=(8, 0))

        # Scrollable content area (shared by all tabs)
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(outer, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=self.canvas.yview)
        self.content_frame = tk.Frame(self.canvas, bg=BG)

        self.content_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas_window = self.canvas.create_window((0, 0), window=self.content_frame, anchor="nw", width=432)
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(self.canvas_window, width=e.width))

        self.canvas.pack(side="left", fill="both", expand=True, padx=(24, 0), pady=12)
        scrollbar.pack(side="right", fill="y", pady=12)

        # Footer
        footer = tk.Frame(self.root, bg=BG)
        footer.pack(fill="x", pady=(0, 18), padx=24)

        self.status_dot = tk.Label(footer, text="●", font=("Sans", 8), bg=BG, fg=TEXT_SECONDARY)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.status_label = tk.Label(footer, text="Ready", font=("Sans", 8), bg=BG, fg=TEXT_SECONDARY)
        self.status_label.pack(side="left")

        self.add_btn = tk.Label(
            footer, text="+ Add App", font=("Sans", 9, "bold"),
            bg=BG, fg=ACCENT, cursor="hand2",
        )
        self.add_btn.pack(side="right")
        self.add_btn.bind("<Enter>", lambda e: self.add_btn.config(fg=ACCENT_HOVER))
        self.add_btn.bind("<Leave>", lambda e: self.add_btn.config(fg=ACCENT))
        self.add_btn.bind("<Button-1>", lambda e: self.open_editor(None))

        self.render_tab()

    def _search_placeholder(self, entry):
        placeholder = "Search…"
        entry.insert(0, placeholder)
        entry.config(fg=TEXT_SECONDARY)

        def on_focus_in(_e):
            if entry.get() == placeholder:
                entry.delete(0, "end")
                entry.config(fg=TEXT_PRIMARY)

        def on_focus_out(_e):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(fg=TEXT_SECONDARY)

        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)

    def get_search_query(self):
        q = self.search_var.get().strip().lower()
        return "" if q == "search…" else q

    def open_settings_menu(self, anchor_widget):
        menu = tk.Menu(self.root, tearoff=0, bg=CARD_BG, fg=TEXT_PRIMARY,
                        activebackground=ACCENT, activeforeground="white", bd=0)
        menu.add_command(label="Export config…", command=self.export_config)
        menu.add_command(label="Import config…", command=self.import_config)
        x = anchor_widget.winfo_rootx()
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height()
        menu.tk_popup(x, y)

    def export_config(self):
        path = filedialog.asksaveasfilename(
            title="Export config", defaultextension=".json",
            initialfile="sandbox-launcher-apps.json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(self.apps, f, indent=2)
            self.set_status(f"Exported {len(self.apps)} app(s)", ok=True)
        except OSError as e:
            messagebox.showerror("Export failed", str(e))

    def import_config(self):
        path = filedialog.askopenfilename(title="Import config", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r") as f:
                imported = json.load(f)
            if not isinstance(imported, list):
                raise ValueError("Expected a list of app entries")
        except (OSError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror("Import failed", str(e))
            return

        existing_ids = {a["id"] for a in self.apps}
        added = 0
        for entry in imported:
            if not isinstance(entry, dict) or "exec_path" not in entry:
                continue
            merged = default_app()
            merged.update(entry)
            if merged["id"] in existing_ids:
                merged["id"] = str(uuid.uuid4())[:8]
            self.apps.append(merged)
            added += 1

        save_apps(self.apps)
        self.set_status(f"Imported {added} app(s)", ok=True)
        self.render_tab()

    def open_containing_folder(self, app):
        target = app.get("working_dir") or os.path.dirname(app.get("exec_path", ""))
        if target and os.path.isdir(target):
            try:
                subprocess.Popen(["xdg-open", target])
            except Exception as e:
                messagebox.showerror("Couldn't open folder", str(e))

    def mark_launched(self, app):
        app["last_launched"] = int(time.time())
        save_apps(self.apps)

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

    def switch_tab(self, key):
        self.current_tab = key
        for k, lbl in self.tab_labels.items():
            lbl.config(fg=TAB_ACTIVE if k == key else TAB_INACTIVE)
        self.add_btn.config(text="+ Add App" if key == "my_apps" else "")
        self.render_tab()

    def clear_content(self):
        for w in self.content_frame.winfo_children():
            w.destroy()
        self.canvas.yview_moveto(0)

    def render_tab(self):
        self.clear_content()
        if self.current_tab == "my_apps":
            self.render_my_apps()
        elif self.current_tab == "installed":
            self.render_installed()
        elif self.current_tab == "discover":
            self.render_discover()

    # ---------- My Apps tab ----------

    def render_my_apps(self):
        if not self.apps:
            tk.Label(
                self.content_frame,
                text="No apps yet.\nClick “+ Add App”, or grab one from\nthe Installed or Discover tabs.",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY, justify="center",
            ).pack(pady=40)
            return

        query = self.get_search_query()
        apps_sorted = sorted(self.apps, key=lambda a: a.get("last_launched", 0), reverse=True)
        filtered = [a for a in apps_sorted if query in a["name"].lower() or query in a.get("desc", "").lower()]

        if not filtered:
            tk.Label(
                self.content_frame, text=f"No apps matching “{query}”",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
            ).pack(pady=30)
            return

        for app in filtered:
            card = RoundedCard(self.content_frame, app, self, mode="my_apps")
            card.pack(fill="x", pady=6, padx=(0, 20))

    # ---------- Installed tab ----------

    def render_installed(self):
        tk.Label(
            self.content_frame,
            text="Apps already on this system. Click one to sandbox it.",
            font=("Sans", 9), bg=BG, fg=TEXT_SECONDARY, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 10))

        if self.installed_cache is None:
            self.set_status("Scanning installed apps…", ok=True)
            self.installed_cache = scan_installed_apps()
            self.set_status("Ready", ok=True)

        if not self.installed_cache:
            tk.Label(
                self.content_frame, text="No installed apps found.",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
            ).pack(pady=20)
            return

        query = self.get_search_query()
        filtered = [i for i in self.installed_cache if query in i["name"].lower() or query in i.get("desc", "").lower()]

        if not filtered:
            tk.Label(
                self.content_frame, text=f"No installed apps matching “{query}”",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
            ).pack(pady=30)
            return

        already = {a["exec_path"] for a in self.apps}

        for item in filtered:
            is_added = item["exec_path"] in already
            card = RoundedCard(self.content_frame, item, self, mode="installed", already_added=is_added)
            card.pack(fill="x", pady=6, padx=(0, 20))

    def add_from_installed(self, item):
        new_app = default_app()
        new_app.update({
            "name": item["name"],
            "desc": item.get("desc", ""),
            "exec_path": item["exec_path"],
            "working_dir": item["working_dir"],
            "icon": "🧩",
        })
        self.apps.append(new_app)
        save_apps(self.apps)
        self.set_status(f"Added {item['name']} to My Apps", ok=True)
        self.render_tab()

    # ---------- Discover tab ----------

    def render_discover(self):
        tk.Label(
            self.content_frame,
            text="Popular apps worth sandboxing. This opens the official\n"
                 "download page in your browser -- nothing is downloaded\n"
                 "or run automatically. Verify and grab it yourself, then\n"
                 "add it via “+ Add App”.",
            font=("Sans", 9), bg=BG, fg=TEXT_SECONDARY, justify="left", anchor="w",
        ).pack(fill="x", pady=(0, 10))

        query = self.get_search_query()
        filtered = [i for i in DISCOVER_CATALOG if query in i["name"].lower() or query in i.get("desc", "").lower()]

        if not filtered:
            tk.Label(
                self.content_frame, text=f"No catalog apps matching “{query}”",
                font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
            ).pack(pady=30)
            return

        for item in filtered:
            card = RoundedCard(self.content_frame, item, self, mode="discover")
            card.pack(fill="x", pady=6, padx=(0, 20))

    def open_discover_link(self, item):
        webbrowser.open(item["url"])
        self.set_status(f"Opened {item['name']} download page", ok=True)

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

        if app.get("private", True):
            rel = os.path.relpath(exec_path, working_dir)
            cmd.append(f"./{rel}")
        else:
            cmd.append(exec_path)

        try:
            subprocess.Popen(cmd, cwd=working_dir)
            self.mark_launched(app)
            self.set_status(f"Launched {app['name']}", ok=True)
        except Exception as e:
            self.set_status(f"Launch failed: {e}", ok=False)
            messagebox.showerror("Launch failed", str(e))

    def _pick_candidate(self, parent_win, candidates, folder, exec_var, dir_var, name_var):
        """Small popup listing multiple plausible executables; user picks one."""
        picker = tk.Toplevel(parent_win)
        picker.title("Multiple candidates found")
        picker.configure(bg=BG)
        picker.geometry("360x300")
        picker.transient(parent_win)
        picker.grab_set()

        tk.Label(
            picker, text="Found a few possible launchers.\nPick the right one:",
            font=("Sans", 10), bg=BG, fg=TEXT_PRIMARY, justify="left",
        ).pack(fill="x", padx=16, pady=(16, 8), anchor="w")

        list_frame = tk.Frame(picker, bg=BG)
        list_frame.pack(fill="both", expand=True, padx=16)

        def choose(cand):
            exec_var.set(cand["path"])
            dir_var.set(folder)
            if not name_var.get().strip() or name_var.get().strip() == "New App":
                name_var.set(os.path.basename(folder.rstrip("/")))
            picker.destroy()

        for cand in candidates[:8]:
            row = tk.Label(
                list_frame, text=cand["rel"], font=("Sans", 9), bg=CARD_BG, fg=TEXT_PRIMARY,
                anchor="w", cursor="hand2", padx=10, pady=8,
            )
            row.pack(fill="x", pady=3)
            row.bind("<Enter>", lambda e, r=row: r.config(bg=CARD_BG_HOVER))
            row.bind("<Leave>", lambda e, r=row: r.config(bg=CARD_BG))
            row.bind("<Button-1>", lambda e, c=cand: choose(c))

        cancel_lbl = tk.Label(
            picker, text="Cancel", font=("Sans", 9), bg=BG, fg=TEXT_SECONDARY, cursor="hand2",
        )
        cancel_lbl.pack(pady=12, side="bottom", anchor="e", padx=16)
        cancel_lbl.bind("<Button-1>", lambda e: picker.destroy())

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

        # Auto-detect row: pick a folder, we scan it for the likely launcher file
        detect_row = tk.Frame(win, bg=BG)
        detect_row.pack(fill="x", padx=20, pady=(4, 0))

        def do_detect():
            folder = filedialog.askdirectory(title="Pick the app's folder to scan")
            if not folder:
                return
            candidates = find_candidate_executables(folder)
            if not candidates:
                messagebox.showinfo("Nothing found", "No likely executable found in that folder.\nTry browsing manually instead.")
                return
            if len(candidates) == 1:
                exec_var.set(candidates[0]["path"])
                dir_var.set(folder)
                if not name_var.get().strip() or name_var.get().strip() == "New App":
                    name_var.set(os.path.basename(folder.rstrip("/")))
                return
            self._pick_candidate(win, candidates, folder, exec_var, dir_var, name_var)

        detect_btn = tk.Label(
            detect_row, text="🔍 Detect from folder", font=("Sans", 9, "bold"),
            bg=BG, fg=ACCENT, cursor="hand2",
        )
        detect_btn.pack(side="left")
        detect_btn.bind("<Enter>", lambda e: detect_btn.config(fg=ACCENT_HOVER))
        detect_btn.bind("<Leave>", lambda e: detect_btn.config(fg=ACCENT))
        detect_btn.bind("<Button-1>", lambda e: do_detect())

        dir_var = field("Working directory (optional, defaults to exe's folder)", "working_dir")
        extra_var = field("Extra firejail args (optional)", "extra_args")

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
            self.render_tab()
            win.destroy()

        def do_delete():
            if messagebox.askyesno("Delete app", f"Remove '{data['name']}' from the launcher?"):
                self.apps = [a for a in self.apps if a["id"] != data["id"]]
                save_apps(self.apps)
                self.render_tab()
                win.destroy()

        def do_duplicate():
            clone = dict(data)
            clone["id"] = str(uuid.uuid4())[:8]
            clone["name"] = f"{data['name']} (copy)"
            clone["last_launched"] = 0
            self.apps.append(clone)
            save_apps(self.apps)
            self.set_status(f"Duplicated {data['name']}", ok=True)
            self.render_tab()
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

            dup_btn = tk.Label(
                btn_row, text="Duplicate", font=("Sans", 10), bg=BG, fg=TEXT_SECONDARY,
                cursor="hand2", padx=10, pady=8,
            )
            dup_btn.pack(side="left")
            dup_btn.bind("<Button-1>", lambda e: do_duplicate())
            dup_btn.bind("<Enter>", lambda e: dup_btn.config(fg=ACCENT))
            dup_btn.bind("<Leave>", lambda e: dup_btn.config(fg=TEXT_SECONDARY))


class RoundedCard(tk.Canvas):
    """
    mode="my_apps"   -> click launches; ✎ edits; right-click edits
    mode="installed" -> click adds to My Apps (or shows "Added" if already there)
    mode="discover"  -> click opens the official download page in browser
    """

    def __init__(self, parent, data, controller, mode="my_apps", already_added=False, radius=14, **kwargs):
        super().__init__(parent, bg=BG, highlightthickness=0, cursor="hand2", height=92, **kwargs)
        self.data = data
        self.controller = controller
        self.mode = mode
        self.already_added = already_added
        self.radius = radius
        self.hovered = False
        self.bind("<Configure>", lambda e: self._redraw())
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        if mode == "my_apps":
            self.bind("<Button-3>", self._on_right_click)

    def _on_right_click(self, _e=None):
        menu = tk.Menu(self, tearoff=0, bg=CARD_BG, fg=TEXT_PRIMARY,
                        activebackground=ACCENT, activeforeground="white", bd=0)
        menu.add_command(label="Edit", command=lambda: self.controller.open_editor(self.data))
        menu.add_command(label="Open containing folder", command=lambda: self.controller.open_containing_folder(self.data))
        menu.tk_popup(self.winfo_pointerx(), self.winfo_pointery())

    @staticmethod
    def _format_relative_time(ts):
        diff = int(time.time()) - ts
        if diff < 60:
            return "just now"
        if diff < 3600:
            m = diff // 60
            return f"{m}m ago"
        if diff < 86400:
            h = diff // 3600
            return f"{h}h ago"
        d = diff // 86400
        return f"{d}d ago"

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
        d = self.data
        icon = d.get("icon", "🧩")

        self.create_text(pad, pad, text=icon, font=("Sans", 22), anchor="nw")
        self.create_text(pad + 38, pad + 2, text=d["name"], font=("Sans", 13, "bold"),
                          fill=TEXT_PRIMARY, anchor="nw")

        if self.mode == "my_apps":
            tag = d.get("tag", "")
            if tag:
                self.create_text(pad + 38, pad + 24, text=tag, font=("Sans", 9),
                                  fill=ACCENT_HOVER if self.hovered else ACCENT, anchor="nw")
            last_launched = d.get("last_launched", 0)
            if last_launched:
                desc = d.get("desc", "") or f"Last used {self._format_relative_time(last_launched)}"
            else:
                badges = ["net" if d.get("net") else "no-net", "isolated" if d.get("private", True) else "shared fs"]
                desc = d.get("desc", "") or " · ".join(badges)
            action_text = "Launch  ▶"
        elif self.mode == "installed":
            desc = d.get("desc", "") or d.get("exec_path", "")
            action_text = "Added ✓" if self.already_added else "+ Add"
        else:  # discover
            desc = d.get("desc", "")
            action_text = "Get  ↗"

        self.create_text(pad, h - pad, text=desc, font=("Sans", 9),
                          fill=TEXT_SECONDARY, anchor="sw", width=w - 2 * pad - 70)

        arrow_color = ACCENT_HOVER if self.hovered else TEXT_SECONDARY
        if self.mode == "installed" and self.already_added:
            arrow_color = STATUS_OK
        self.create_text(w - pad, h - pad, text=action_text, font=("Sans", 10, "bold"),
                          fill=arrow_color, anchor="se")

        if self.mode == "my_apps":
            self.create_text(w - pad, pad, text="✎", font=("Sans", 11),
                              fill=TEXT_SECONDARY, anchor="ne")

    def _on_enter(self, _e=None):
        self.hovered = True
        self._redraw()

    def _on_leave(self, _e=None):
        self.hovered = False
        self._redraw()

    def _on_click(self, e=None):
        if self.mode == "my_apps":
            w = self.winfo_width()
            if e and e.x > w - 40 and e.y < 40:
                self.controller.open_editor(self.data)
            else:
                self.controller.launch(self.data)
        elif self.mode == "installed":
            if not self.already_added:
                self.controller.add_from_installed(self.data)
        elif self.mode == "discover":
            self.controller.open_discover_link(self.data)


if __name__ == "__main__":
    root = tk.Tk()
    app = App(root)
    root.mainloop()

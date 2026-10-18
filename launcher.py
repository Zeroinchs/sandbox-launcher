#!/usr/bin/env python3
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import subprocess
import json
import os
import shutil
import threading
import urllib.request
import webbrowser

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

CURRENT_VERSION = "1.0.0"
GITHUB_REPO = "Zeroinchs/sandbox-launcher"
CONFIG_DIR = os.path.expanduser("~/.config/sandbox-launcher")
CONFIG_FILE = os.path.join(CONFIG_DIR, "apps.json")

class SandboxLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Sandbox Launcher v{CURRENT_VERSION}")
        self.root.geometry("700x550")
        
        self.apps = self.load_config()
        self.current_app = None
        self.check_dependencies()
        self.create_widgets()
        
        if HAS_DND:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind('<<Drop>>', self.handle_drop)
            self.root.title(f"Sandbox Launcher v{CURRENT_VERSION} [Drag & Drop Enabled]")
        
        threading.Thread(target=self.check_for_updates, daemon=True).start()

    def check_dependencies(self):
        if not shutil.which("firejail"):
            messagebox.showerror("Missing Dependency", "Firejail is not installed!\n\nPlease install it via your package manager.")
            self.root.quit()

    def handle_drop(self, event):
        filepath = event.data.strip('{}')
        if os.path.isfile(filepath):
            self.add_app()
            self.path_var.set(filepath)
            self.name_var.set(os.path.basename(filepath))
            self.save_app()

    def check_for_updates(self):
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'SandboxLauncher'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode())
                latest_version = data.get("tag_name", "").lstrip("v")
                release_url = data.get("html_url", "")
                if latest_version and latest_version != CURRENT_VERSION:
                    self.root.after(0, self.show_update_prompt, latest_version, release_url)
        except Exception:
            pass 

    def show_update_prompt(self, new_version, release_url):
        msg = f"Update Available!\n\nCurrent: v{CURRENT_VERSION}\nLatest: v{new_version}\n\nOpen download page?"
        if messagebox.askyesno("Update Available", msg):
            webbrowser.open(release_url)

    def create_widgets(self):
        left_frame = ttk.Frame(self.root, padding="10")
        left_frame.pack(side=tk.LEFT, fill=tk.Y)

        ttk.Label(left_frame, text="Sandboxed Applications").pack(anchor=tk.W)
        if HAS_DND:
            ttk.Label(left_frame, text="(Drag & drop executables here)", foreground="gray").pack(anchor=tk.W)

        self.app_listbox = tk.Listbox(left_frame, width=30, height=20)
        self.app_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self.app_listbox.bind("<<ListboxSelect>>", self.on_app_select)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="+ Add", command=self.add_app).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_frame, text="- Remove", command=self.remove_app).pack(side=tk.LEFT, expand=True, fill=tk.X)

        right_frame = ttk.Frame(self.root, padding="10")
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        ttk.Label(right_frame, text="App Name:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.name_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.name_var).grid(row=0, column=1, sticky=tk.EW, pady=2)

        ttk.Label(right_frame, text="Executable Path:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.path_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.path_var).grid(row=1, column=1, sticky=tk.EW, pady=2)
        ttk.Button(right_frame, text="Browse", command=self.browse_file).grid(row=1, column=2, padx=5)

        self.net_var = tk.BooleanVar()
        ttk.Checkbutton(right_frame, text="Isolate Network (--net=none)", variable=self.net_var).grid(row=2, column=1, sticky=tk.W, pady=5)
        
        self.home_var = tk.BooleanVar()
        ttk.Checkbutton(right_frame, text="Private Home (--private)", variable=self.home_var).grid(row=3, column=1, sticky=tk.W, pady=5)

        ttk.Label(right_frame, text="Custom Flags:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.flags_var = tk.StringVar()
        ttk.Entry(right_frame, textvariable=self.flags_var).grid(row=4, column=1, sticky=tk.EW, pady=2)

        ttk.Button(right_frame, text="Save Configuration", command=self.save_app).grid(row=5, column=1, sticky=tk.E, pady=10)

        action_frame = ttk.Frame(right_frame)
        action_frame.grid(row=6, column=0, columnspan=3, sticky=tk.EW, pady=10)
        ttk.Button(action_frame, text="▶ LAUNCH", command=self.launch_app).pack(side=tk.LEFT, fill=tk.X, expand=True)

        ttk.Label(right_frame, text="Firejail Output Log:").grid(row=7, column=0, sticky=tk.W)
        self.log_text = tk.Text(right_frame, height=8, state=tk.DISABLED, bg="black", fg="lime")
        self.log_text.grid(row=8, column=0, columnspan=3, sticky=tk.NSEW)

        right_frame.rowconfigure(8, weight=1)
        right_frame.columnconfigure(1, weight=1)
        self.refresh_list()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        return {}

    def save_config(self):
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.apps, f, indent=4)

    def refresh_list(self):
        self.app_listbox.delete(0, tk.END)
        for app_name in self.apps.keys():
            self.app_listbox.insert(tk.END, app_name)

    def on_app_select(self, event):
        selection = self.app_listbox.curselection()
        if selection:
            self.current_app = self.app_listbox.get(selection[0])
            data = self.apps[self.current_app]
            self.name_var.set(self.current_app)
            self.path_var.set(data.get("path", ""))
            self.net_var.set(data.get("net_isolate", False))
            self.home_var.set(data.get("private_home", False))
            self.flags_var.set(data.get("custom_flags", ""))

    def browse_file(self):
        filepath = filedialog.askopenfilename()
        if filepath:
            self.path_var.set(filepath)

    def add_app(self):
        self.app_listbox.selection_clear(0, tk.END)
        self.current_app = None
        self.name_var.set("New App")
        self.path_var.set("")
        self.net_var.set(False)
        self.home_var.set(False)
        self.flags_var.set("")

    def remove_app(self):
        if self.current_app and self.current_app in self.apps:
            del self.apps[self.current_app]
            self.save_config()
            self.refresh_list()
            self.add_app()

    def save_app(self):
        name = self.name_var.get().strip()
        path = self.path_var.get().strip()
        if not name or not path:
            messagebox.showwarning("Warning", "Name and Path are required.")
            return
        self.apps[name] = {
            "path": path,
            "net_isolate": self.net_var.get(),
            "private_home": self.home_var.get(),
            "custom_flags": self.flags_var.get()
        }
        if self.current_app and self.current_app != name:
            del self.apps[self.current_app]
        self.current_app = name
        self.save_config()
        self.refresh_list()

    def log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def launch_app(self):
        path = self.path_var.get().strip()
        if not path or not os.path.exists(path):
            messagebox.showerror("Error", "Executable path does not exist!")
            return
        cmd = ["firejail"]
        if self.net_var.get(): cmd.append("--net=none")
        if self.home_var.get(): cmd.append("--private")
        custom = self.flags_var.get().strip()
        if custom: cmd.extend(custom.split())
        cmd.append(path)
        
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.log(f"Executing: {' '.join(cmd)}")
        threading.Thread(target=self.run_process, args=(cmd,), daemon=True).start()

    def run_process(self, cmd):
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                self.root.after(0, self.log, line.strip())
            process.wait()
            self.root.after(0, self.log, f"\n--- Process finished with exit code {process.returncode} ---")
        except Exception as e:
            self.root.after(0, self.log, f"ERROR: {str(e)}")

if __name__ == "__main__":
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    app = SandboxLauncher(root)
    root.mainloop()

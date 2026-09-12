# Sandbox Launcher

A GUI launcher for running any application fully isolated via [Firejail](https://firejail.wordpress.com/).

Add any executable through the GUI — no code editing required. Each app can be configured with its own network access, filesystem isolation, and custom Firejail flags.

## Requirements

- Python 3 with tkinter
- Firejail

Install on Arch/CachyOS:
```bash
sudo pacman -S firejail tk
```

## Usage

```bash
git clone https://github.com/YOUR_USERNAME/sandbox-launcher.git
cd sandbox-launcher
python3 launcher.py
```

Click **+ Add App**, point it at any executable, and configure isolation settings. Right-click (or click the ✎ icon) on a card to edit an existing entry.

Config is stored at `~/.config/sandbox-launcher/apps.json`.

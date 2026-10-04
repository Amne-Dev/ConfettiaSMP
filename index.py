import os
import sys
import platform
import threading
import urllib.request
import zipfile
import shutil
import json
from datetime import datetime, timezone
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --- CONFIGURATION ---
MODPACK_URL = "https://your-domain.com/path/to/modpack.zip"
APP_TITLE = "Server Modpack Installer"
PROFILE_NAME = "My Server Modpack (1.21.1)"
PROFILE_ID = "MyServerModpack_1_21_1"  # Unique key for launcher_profiles.json
DEFAULT_FABRIC_VERSION = "fabric-loader-0.16.5-1.21.1"  # Fallback if auto-detect fails
WINDOW_SIZE = "480x310"

def get_default_mc_dir() -> Path:
    """Detects default .minecraft folder across operating systems."""
    system = platform.system()
    if system == "Windows":
        return Path(os.getenv("APPDATA", "")) / ".minecraft"
    elif system == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / "minecraft"
    else:  # Linux
        return Path.home() / ".minecraft"

def detect_fabric_version(mc_dir: Path) -> str:
    """Scans .minecraft/versions to auto-detect an installed Fabric 1.21.1 version."""
    versions_dir = mc_dir / "versions"
    if versions_dir.exists():
        for folder in versions_dir.iterdir():
            if folder.is_dir() and "fabric-loader" in folder.name.lower() and "1.21.1" in folder.name:
                return folder.name
    return DEFAULT_FABRIC_VERSION

def register_launcher_profile(mc_dir: Path, instance_dir: Path, version_id: str):
    """Creates or updates a profile in launcher_profiles.json pointing to the isolated gameDir."""
    profiles_file = mc_dir / "launcher_profiles.json"
    data = {"profiles": {}}

    if profiles_file.exists():
        try:
            with open(profiles_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {"profiles": {}}

    if "profiles" not in data:
        data["profiles"] = {}

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    data["profiles"][PROFILE_ID] = {
        "name": PROFILE_NAME,
        "type": "custom",
        "created": now_iso,
        "lastUsed": now_iso,
        "icon": "Crafting_Table",
        "gameDir": str(instance_dir.resolve()),
        "lastVersionId": version_id
    }

    with open(profiles_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

class ModpackInstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)

        self.mc_dir = get_default_mc_dir()
        self.setup_ui()

    def setup_ui(self):
        padding = {'padx': 15, 'pady': 5}

        ttk.Label(self.root, text=APP_TITLE, font=("Helvetica", 14, "bold")).pack(pady=12)

        # Path Selector Frame
        path_frame = ttk.Frame(self.root)
        path_frame.pack(fill="x", **padding)

        ttk.Label(path_frame, text="Minecraft Path:").pack(anchor="w")
        
        path_input_frame = ttk.Frame(path_frame)
        path_input_frame.pack(fill="x", pady=4)

        self.path_entry = ttk.Entry(path_input_frame)
        self.path_entry.insert(0, str(self.mc_dir))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))

        browse_btn = ttk.Button(path_input_frame, text="Browse...", command=self.browse_path)
        browse_btn.pack(side="right")

        # Options
        self.clean_install_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root, 
            text="Clean instance mods folder before extraction", 
            variable=self.clean_install_var
        ).pack(anchor="w", padx=15, pady=2)

        # Status & Progress
        self.status_label = ttk.Label(self.root, text="Ready to install profile", font=("Helvetica", 9))
        self.status_label.pack(anchor="w", padx=15, pady=(8, 2))

        self.progress_bar = ttk.Progressbar(self.root, mode="determinate")
        self.progress_bar.pack(fill="x", padx=15, pady=2)

        # Install Button
        self.install_btn = ttk.Button(self.root, text="Install Standalone Modpack", command=self.start_installation)
        self.install_btn.pack(pady=12, ipadx=10)

    def browse_path(self):
        selected = filedialog.askdirectory(initialdir=self.path_entry.get())
        if selected:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, selected)

    def start_installation(self):
        mc_path = Path(self.path_entry.get().strip())
        if not mc_path.exists():
            messagebox.showerror("Error", "The specified Minecraft folder does not exist.")
            return

        self.install_btn.config(state="disabled")
        threading.Thread(target=self.run_install, args=(mc_path,), daemon=True).start()

    def update_status(self, text: str, progress: float = None):
        def _update():
            self.status_label.config(text=text)
            if progress is not None:
                self.progress_bar['value'] = progress
        self.root.after(0, _update)

    def run_install(self, mc_path: Path):
        # Create isolated instance directory
        instance_dir = mc_path / "instances" / PROFILE_ID
        instance_dir.mkdir(parents=True, exist_ok=True)
        temp_zip = instance_dir / "temp_modpack.zip"

        try:
            self.update_status("Downloading modpack...", 0)

            def progress_hook(block_num, block_size, total_size):
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(100, (downloaded / total_size) * 75)
                    self.update_status(f"Downloading: {int((downloaded / total_size) * 100)}%", percent)

            urllib.request.urlretrieve(MODPACK_URL, temp_zip, reporthook=progress_hook)

            # Clean instance mods folder if requested
            mods_dir = instance_dir / "mods"
            if self.clean_install_var.get() and mods_dir.exists():
                self.update_status("Cleaning existing instance mods...", 80)
                shutil.rmtree(mods_dir)

            # Extract directly into instance directory
            self.update_status("Extracting modpack into isolated folder...", 85)
            with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
                zip_ref.extractall(instance_dir)

            # Auto-detect installed Fabric version for 1.21.1
            self.update_status("Configuring launcher profile...", 95)
            fabric_version = detect_fabric_version(mc_path)

            # Register profile in launcher_profiles.json
            register_launcher_profile(mc_path, instance_dir, fabric_version)

            self.update_status("Installation complete!", 100)
            self.root.after(0, lambda: messagebox.showinfo(
                "Success", 
                f"Modpack installed successfully!\n\n"
                f"Profile Name: {PROFILE_NAME}\n"
                f"Instance Directory: .minecraft/instances/{PROFILE_ID}\n\n"
                "Restart your Minecraft Launcher to select the new profile."
            ))

        except Exception as e:
            self.update_status("Installation failed!", 0)
            self.root.after(0, lambda: messagebox.showerror("Error", f"Failed to install modpack:\n{str(e)}"))

        finally:
            if temp_zip.exists():
                try:
                    os.remove(temp_zip)
                except Exception:
                    pass
            self.root.after(0, lambda: self.install_btn.config(state="normal"))

if __name__ == "__main__":
    root = tk.Tk()
    app = ModpackInstallerApp(root)
    root.mainloop()
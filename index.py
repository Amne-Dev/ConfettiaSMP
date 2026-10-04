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
GITHUB_USER = "Amne-Dev"
GITHUB_REPO = "ConfettiaSMP"
GITHUB_BRANCH = "master"

MODPACK_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/archive/refs/heads/{GITHUB_BRANCH}.zip"
MOJANG_MANIFEST_URL = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
FABRIC_PROFILE_URL = "https://meta.fabricmc.net/v2/versions/loader/1.21.1/profile/json"
FABRIC_LOADERS_URL = "https://meta.fabricmc.net/v2/versions/loader/1.21.1"

APP_TITLE = "ConfettiaSMP Modpack Installer"
CUSTOM_VERSION_ID = "ConfettiaSMP-1.21.1"
PROFILE_NAME = "ConfettiaSMP (1.21.1)"
WINDOW_SIZE = "520x400"

# --- COLOR PALETTE (Minecraft Dark Theme) ---
COLOR_BG = "#1E1E1E"
COLOR_PANEL = "#252526"
COLOR_TEXT = "#FFFFFF"
COLOR_SUBTEXT = "#AAAAAA"
COLOR_GREEN = "#2E7D32"
COLOR_GREEN_HOVER = "#388E3C"
COLOR_BORDER = "#3E3E42"


def get_default_mc_dir() -> Path:
    """Detects standard .minecraft directory across OS platforms."""
    system = platform.system()
    if system == "Windows":
        return Path(os.getenv("APPDATA", "")) / ".minecraft"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "minecraft"
    else:
        return Path.home() / ".minecraft"


def get_default_prism_dir() -> Path:
    """Detects standard Prism Launcher instances directory across OS platforms."""
    system = platform.system()
    if system == "Windows":
        appdata = Path(os.getenv("APPDATA", "")) / "PrismLauncher" / "instances"
        localappdata = Path(os.getenv("LOCALAPPDATA", "")) / "PrismLauncher" / "instances"
        return appdata if appdata.exists() else localappdata
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "PrismLauncher" / "instances"
    else:
        # Linux Native or Flatpak
        flatpak_path = Path.home() / ".var" / "app" / "org.prismlauncher.PrismLauncher" / "data" / "PrismLauncher" / "instances"
        native_path = Path.home() / ".local" / "share" / "PrismLauncher" / "instances"
        return flatpak_path if flatpak_path.exists() else native_path


def ensure_vanilla_1_21_1(target_root: Path, status_callback=None):
    """Downloads Minecraft 1.21.1 manifest and client JAR if missing from versions/1.21.1."""
    v_dir = target_root / "versions" / "1.21.1"
    v_json = v_dir / "1.21.1.json"
    v_jar = v_dir / "1.21.1.jar"

    if v_json.exists() and v_jar.exists():
        return

    v_dir.mkdir(parents=True, exist_ok=True)

    if status_callback:
        status_callback("Fetching Minecraft 1.21.1 from Mojang API...")

    req = urllib.request.Request(MOJANG_MANIFEST_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        manifest = json.loads(resp.read().decode('utf-8'))

    v_info = next((v for v in manifest.get("versions", []) if v.get("id") == "1.21.1"), None)
    if not v_info:
        raise RuntimeError("Could not locate Minecraft 1.21.1 in Mojang version manifest.")

    if not v_json.exists():
        req_json = urllib.request.Request(v_info["url"], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_json) as resp, open(v_json, "wb") as f:
            f.write(resp.read())

    if not v_jar.exists():
        if status_callback:
            status_callback("Downloading base Minecraft 1.21.1 client JAR...")
        with open(v_json, "r", encoding="utf-8") as f:
            vdata = json.load(f)
        client_url = vdata.get("downloads", {}).get("client", {}).get("url")
        if not client_url:
            raise RuntimeError("Client download URL missing from 1.21.1 version definition.")

        req_jar = urllib.request.Request(client_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req_jar) as resp, open(v_jar, "wb") as f:
            shutil.copyfileobj(resp, f)


def fetch_fabric_version_data(target_root: Path) -> dict:
    """Reads local Fabric 1.21.1 profile if present, or fetches it directly from Fabric Meta API."""
    v_dir = target_root / "versions"
    if v_dir.exists():
        for folder in v_dir.iterdir():
            if folder.is_dir() and "fabric" in folder.name.lower() and "1.21.1" in folder.name:
                local_json = folder / f"{folder.name}.json"
                if local_json.exists():
                    try:
                        with open(local_json, "r", encoding="utf-8") as f:
                            return json.load(f)
                    except Exception:
                        pass

    req = urllib.request.Request(FABRIC_PROFILE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))


def fetch_latest_fabric_loader_version() -> str:
    """Queries Fabric Meta API for the latest stable loader version for 1.21.1."""
    try:
        req = urllib.request.Request(FABRIC_LOADERS_URL, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode('utf-8'))
            if data and len(data) > 0:
                return data[0].get("loader", {}).get("version", "0.16.9")
    except Exception:
        pass
    return "0.16.9"


def register_version_profile(target_dir: Path, version_id: str):
    """Registers the custom version profile in launcher_profiles.json."""
    if not target_dir.exists():
        target_dir.mkdir(parents=True, exist_ok=True)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    profile_data = {
        "name": PROFILE_NAME,
        "type": "custom",
        "created": now_iso,
        "lastUsed": now_iso,
        "icon": "Crafting_Table",
        "lastVersionId": version_id
    }

    for filename in ["launcher_profiles.json", "profiles.json"]:
        file_path = target_dir / filename
        data = {"profiles": {}}

        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                data = {"profiles": {}}

        if not isinstance(data, dict):
            data = {"profiles": {}}

        if "profiles" not in data or not isinstance(data["profiles"], dict):
            data["profiles"] = {}

        data["profiles"][version_id] = profile_data

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def extract_modpack_zip(temp_zip: Path, target_mods_dir: Path, target_root_dir: Path):
    """Extracts zip content mapping 'mods' to target_mods_dir and root configs to target_root_dir."""
    with zipfile.ZipFile(temp_zip, 'r') as zip_ref:
        for member in zip_ref.infolist():
            path_parts = Path(member.filename).parts
            if len(path_parts) <= 1:
                continue

            rel_path = Path(*path_parts[1:])
            first_folder = rel_path.parts[0].lower()

            if first_folder == "mods":
                target_path = target_mods_dir / rel_path.relative_to("mods")
            elif first_folder in {"config", "resourcepacks", "shaderpacks", "options.txt"}:
                target_path = target_root_dir / rel_path
            else:
                continue

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zip_ref.open(member) as src, open(target_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def build_official_version_package(target_root: Path, temp_zip: Path, clean_mods: bool, status_callback=None):
    """Compiles versions/ConfettiaSMP-1.21.1 for standard Minecraft Launcher."""
    ensure_vanilla_1_21_1(target_root, status_callback)

    if status_callback:
        status_callback("Fetching Fabric loader definition...")

    vdata = fetch_fabric_version_data(target_root)

    version_dir = target_root / "versions" / CUSTOM_VERSION_ID
    version_mods_dir = version_dir / "mods"

    version_dir.mkdir(parents=True, exist_ok=True)
    version_mods_dir.mkdir(parents=True, exist_ok=True)

    if clean_mods and version_mods_dir.exists():
        for item in version_mods_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    vdata["id"] = CUSTOM_VERSION_ID
    vdata["inheritsFrom"] = "1.21.1"
    vdata["jar"] = "1.21.1"

    add_mods_arg = f"-Dfabric.addMods={version_mods_dir.resolve()}"

    if "arguments" in vdata and "jvm" in vdata["arguments"]:
        vdata["arguments"]["jvm"].append(add_mods_arg)
    elif "arguments" in vdata:
        vdata["arguments"]["jvm"] = [add_mods_arg]
    else:
        vdata["arguments"] = {"jvm": [add_mods_arg]}

    custom_json = version_dir / f"{CUSTOM_VERSION_ID}.json"
    with open(custom_json, "w", encoding="utf-8") as f:
        json.dump(vdata, f, indent=2)

    if status_callback:
        status_callback("Extracting modpack assets for Official Launcher...")

    extract_modpack_zip(temp_zip, version_mods_dir, version_dir)
    register_version_profile(target_root, CUSTOM_VERSION_ID)


def build_prism_instance(instances_dir: Path, temp_zip: Path, clean_mods: bool, status_callback=None):
    """Creates a standalone Prism Launcher instance under instances/ConfettiaSMP."""
    instance_dir = instances_dir / "ConfettiaSMP"
    mc_dir = instance_dir / ".minecraft"
    mods_dir = mc_dir / "mods"

    instance_dir.mkdir(parents=True, exist_ok=True)
    mc_dir.mkdir(parents=True, exist_ok=True)
    mods_dir.mkdir(parents=True, exist_ok=True)

    if clean_mods and mods_dir.exists():
        for item in mods_dir.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    if status_callback:
        status_callback("Configuring Prism Launcher instance...")

    loader_version = fetch_latest_fabric_loader_version()

    mmc_pack = {
        "components": [
            {
                "cachedName": "Minecraft",
                "cachedRequires": [],
                "cachedVersion": "1.21.1",
                "important": True,
                "uid": "net.minecraft",
                "version": "1.21.1"
            },
            {
                "cachedName": "Fabric Loader",
                "cachedRequires": [
                    {
                        "equals": "1.21.1",
                        "uid": "net.minecraft"
                    }
                ],
                "cachedVersion": loader_version,
                "uid": "net.fabricmc.fabric-loader",
                "version": loader_version
            }
        ],
        "formatVersion": 1
    }

    with open(instance_dir / "mmc-pack.json", "w", encoding="utf-8") as f:
        json.dump(mmc_pack, f, indent=4)

    cfg_content = (
        "InstanceType=OneSix\n"
        f"Name={PROFILE_NAME}\n"
        "iconKey=default\n"
        "overrideMemory=false\n"
    )
    with open(instance_dir / "instance.cfg", "w", encoding="utf-8") as f:
        f.write(cfg_content)

    if status_callback:
        status_callback("Extracting modpack assets for Prism Launcher...")

    extract_modpack_zip(temp_zip, mods_dir, mc_dir)


class ModpackInstallerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)
        self.root.configure(bg=COLOR_BG)

        self.target_dir = get_default_mc_dir()

        self.setup_styles()
        self.setup_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        style.configure(".", background=COLOR_BG, foreground=COLOR_TEXT)
        style.configure("TFrame", background=COLOR_BG)
        style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)

        style.configure("TCheckbutton", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", COLOR_BG)])

        style.configure("TEntry", fieldbackground=COLOR_PANEL, foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)

        style.configure("Accent.TButton", background=COLOR_GREEN, foreground=COLOR_TEXT, font=("Segoe UI", 10, "bold"), borderwidth=0)
        style.map("Accent.TButton", background=[("active", COLOR_GREEN_HOVER), ("disabled", "#333333")])

        style.configure("Secondary.TButton", background=COLOR_PANEL, foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.map("Secondary.TButton", background=[("active", "#3E3E42")])

        style.configure("Green.Horizontal.TProgressbar", troughcolor=COLOR_PANEL, bordercolor=COLOR_BORDER, background=COLOR_GREEN)

    def setup_ui(self):
        header_frame = tk.Frame(self.root, bg=COLOR_BG)
        header_frame.pack(fill="x", padx=20, pady=(18, 10))

        ttk.Label(header_frame, text="ConfettiaSMP Installer", font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(header_frame, text="By Amne-Dev (Ev)", font=("Segoe UI", 9), foreground=COLOR_SUBTEXT).pack(anchor="w")

        panel = tk.Frame(self.root, bg=COLOR_PANEL, highlightbackground=COLOR_BORDER, highlightthickness=1)
        panel.pack(fill="x", padx=20, pady=8, ipady=8)

        ttk.Label(panel, text="Minecraft Directory (.minecraft):", font=("Segoe UI", 9, "bold"), background=COLOR_PANEL).pack(anchor="w", padx=12, pady=(4, 2))

        path_input_frame = tk.Frame(panel, bg=COLOR_PANEL)
        path_input_frame.pack(fill="x", padx=12, pady=4)

        self.path_entry = ttk.Entry(path_input_frame)
        self.path_entry.insert(0, str(self.target_dir))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))

        browse_btn = ttk.Button(path_input_frame, text="Browse", style="Secondary.TButton", command=self.browse_path)
        browse_btn.pack(side="right")

        self.clean_install_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            self.root,
            text="Wipe old mod files before compiling",
            variable=self.clean_install_var
        ).pack(anchor="w", padx=20, pady=6)

        self.status_label = ttk.Label(self.root, text="Ready to compile standalone version", font=("Segoe UI", 9), foreground=COLOR_SUBTEXT)
        self.status_label.pack(anchor="w", padx=20, pady=(10, 2))

        self.progress_bar = ttk.Progressbar(self.root, mode="determinate", style="Green.Horizontal.TProgressbar")
        self.progress_bar.pack(fill="x", padx=20, pady=2)

        self.install_btn = ttk.Button(self.root, text="Auto-Install Modpack", style="Accent.TButton", command=self.start_installation)
        self.install_btn.pack(pady=16, ipadx=12, ipady=4)

    def browse_path(self):
        selected = filedialog.askdirectory(initialdir=self.path_entry.get())
        if selected:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, selected)

    def start_installation(self):
        mc_path = Path(self.path_entry.get().strip())
        self.install_btn.config(state="disabled")
        threading.Thread(target=self.run_install, args=(mc_path,), daemon=True).start()

    def update_status(self, text: str, progress: float = None):
        def _update():
            self.status_label.config(text=text)
            if progress is not None:
                self.progress_bar['value'] = progress
        self.root.after(0, _update)

    def run_install(self, mc_path: Path):
        temp_zip = mc_path / "temp_modpack.zip"
        installed_launchers = []

        try:
            mc_path.mkdir(parents=True, exist_ok=True)

            # 1. Download modpack archive
            self.update_status("Downloading modpack from GitHub...", 10)
            req = urllib.request.Request(MODPACK_URL, headers={'User-Agent': 'Mozilla/5.0'})

            with urllib.request.urlopen(req) as response, open(temp_zip, 'wb') as out_file:
                total_length = response.headers.get('content-length')
                if total_length is not None:
                    total_size = int(total_length)
                    downloaded = 0
                    block_size = 8192
                    while True:
                        buffer = response.read(block_size)
                        if not buffer:
                            break
                        downloaded += len(buffer)
                        out_file.write(buffer)
                        percent = 10 + min(30, (downloaded / total_size) * 30)
                        self.update_status(f"Downloading modpack: {int((downloaded / total_size) * 100)}%", percent)
                else:
                    out_file.write(response.read())

            # 2. Build for Official Minecraft Launcher
            self.update_status("Installing to Official Minecraft Launcher...", 50)
            build_official_version_package(
                mc_path,
                temp_zip,
                self.clean_install_var.get(),
                status_callback=lambda msg: self.update_status(msg)
            )
            installed_launchers.append("Official Minecraft Launcher")

            # 3. Auto-detect and build for Prism Launcher if present
            prism_dir = get_default_prism_dir()
            if prism_dir and prism_dir.parent.exists():
                self.update_status("Installing to Prism Launcher...", 80)
                build_prism_instance(
                    prism_dir,
                    temp_zip,
                    self.clean_install_var.get(),
                    status_callback=lambda msg: self.update_status(msg)
                )
                installed_launchers.append("Prism Launcher")

            self.update_status("Installation completed successfully!", 100)

            installed_summary = "\n• " + "\n• ".join(installed_launchers)
            self.root.after(0, lambda: messagebox.showinfo(
                "Success",
                f"Modpack compiled and installed successfully!\n\nTarget Launchers Updated:{installed_summary}"
            ))

        except Exception as e:
            self.update_status("Installation failed!", 0)
            self.root.after(0, lambda err=e: messagebox.showerror("Error", f"Failed to install modpack:\n{str(err)}"))

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
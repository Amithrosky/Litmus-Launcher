import concurrent.futures
import configparser
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import zipfile
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# Application Metadata
APP_TITLE = "Litmus Launcher"
APP_DEVELOPER = "Amithrosky"
APP_VERSION = "1.9.27 Stable with Modrinth Fix"

# Application Central Directory
APPDATA_DIR = os.environ.get("APPDATA", os.path.expanduser("~"))
BASE_DIR = os.path.join(APPDATA_DIR, ".minecraft")

CONFIG_FILE = os.path.join(BASE_DIR, "litmus_launcher.conf")
TEMP_DIR = os.path.join(BASE_DIR, ".vlauncher_temp")

DEFAULT_JAVA_ARGS = "-Xss1M -XX:+UnlockExperimentalVMOptions -XX:+UseG1GC -XX:G1NewSizePercent=20 -XX:G1ReservePercent=20 -XX:MaxGCPauseMillis=50 -XX:G1HeapRegionSize=32M"


def create_directory_recursive(path):
    if path and not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


create_directory_recursive(BASE_DIR)
create_directory_recursive(TEMP_DIR)
create_directory_recursive(os.path.join(BASE_DIR, "versions"))
create_directory_recursive(os.path.join(BASE_DIR, "assets"))
create_directory_recursive(os.path.join(BASE_DIR, "libraries"))
create_directory_recursive(os.path.join(BASE_DIR, "mods"))
create_directory_recursive(os.path.join(BASE_DIR, "logs"))


def open_folder_in_explorer(path):
    """Safely open a folder across Windows, macOS, and Linux."""
    create_directory_recursive(path)
    if hasattr(os, "startfile"):
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


class LauncherConfig:
    def __init__(self, filename=CONFIG_FILE):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.load()

    def load(self):
        if os.path.exists(self.filename):
            self.config.read(self.filename, encoding="utf-8")
        if "Settings" not in self.config:
            self.config["Settings"] = {}

    def get(self, key, default=""):
        return self.config["Settings"].get(key, str(default))

    def getint(self, key, default=0):
        try:
            return self.config["Settings"].getint(key, fallback=default)
        except ValueError:
            return default

    def set(self, key, value):
        self.config["Settings"][key] = str(value)
        with open(self.filename, "w", encoding="utf-8") as f:
            self.config.write(f)


cfg = LauncherConfig()


def file_read(path):
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def download_file_http(url, dest, cancel_event=None):
    if cancel_event and cancel_event.is_set():
        return False
    try:
        create_directory_recursive(os.path.dirname(dest))
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "LitmusLauncher/1.9.27 (contact@litmuslauncher.org)"}
        )
        with urllib.request.urlopen(req, timeout=15) as response, open(dest, "wb") as out_file:
            while True:
                if cancel_event and cancel_event.is_set():
                    return False
                chunk = response.read(8192)
                if not chunk:
                    break
                out_file.write(chunk)
        return True
    except Exception:
        return False


def generate_offline_uuid(player_name):
    md5_hash = hashlib.md5(f"OfflinePlayer:{player_name}".encode("utf-8")).hexdigest()
    val13 = int(md5_hash[12:14], 16) & 0x0F | 0x30
    val17 = int(md5_hash[16:18], 16) & 0x3F | 0x80
    return (
        md5_hash[:12]
        + f"{val13:02x}"
        + md5_hash[14:16]
        + f"{val17:02x}"
        + md5_hash[18:]
    )


def is_library_allowed(lib):
    rules = lib.get("rules", [])
    if not rules:
        return True
    allowed = False
    for rule in rules:
        action = rule.get("action") == "allow"
        os_spec = rule.get("os", {})
        os_name = os_spec.get("name")
        if os_name is None or os_name == "windows":
            allowed = action
    return allowed


def find_java_paths():
    java_list = []
    searched_paths = set()

    program_files = [
        os.environ.get("ProgramW6432", "C:\\Program Files"),
        os.environ.get("PROGRAMFILES", "C:\\Program Files (x86)"),
        os.environ.get("LOCALAPPDATA", ""),
    ]

    for pf in program_files:
        if not pf or not os.path.exists(pf):
            continue
        search_dirs = [
            os.path.join(pf, "Java"),
            os.path.join(pf, "Eclipse Adoptium"),
            os.path.join(pf, "Zulu"),
            os.path.join(pf, "Minecraft Launcher", "runtime"),
        ]
        for sdir in search_dirs:
            if os.path.exists(sdir):
                for root, _, files in os.walk(sdir):
                    if "javaw.exe" in files or "java.exe" in files:
                        exe_name = "javaw.exe" if "javaw.exe" in files else "java.exe"
                        full_path = os.path.join(root, exe_name)
                        if full_path not in searched_paths:
                            searched_paths.add(full_path)
                            parent_folder = os.path.basename(os.path.dirname(os.path.dirname(full_path)))
                            label = f"{parent_folder} ({'x64' if 'x86' not in root else 'x86'})"
                            java_list.append((label, full_path))

    try:
        res = subprocess.run(["where", "javaw"], capture_output=True, text=True)
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if line and line not in searched_paths and os.path.exists(line):
                    searched_paths.add(line)
                    java_list.append(("System PATH (javaw.exe)", line))
    except Exception:
        pass

    return java_list


def get_resolved_version_data(version):
    """Recursively resolves version JSON data including Fabric/Forge inheritsFrom definitions."""
    v_json = os.path.join(BASE_DIR, "versions", version, f"{version}.json")
    if not os.path.exists(v_json):
        return None

    raw_content = file_read(v_json)
    if not raw_content:
        return None

    try:
        data = json.loads(raw_content)
    except Exception:
        return None

    if "inheritsFrom" in data:
        parent_ver = data["inheritsFrom"]
        parent_data = get_resolved_version_data(parent_ver)
        if parent_data:
            combined_libs = parent_data.get("libraries", []) + data.get("libraries", [])
            merged = dict(parent_data)
            merged.update(data)
            merged["libraries"] = combined_libs

            child_jar = os.path.join(BASE_DIR, "versions", version, f"{version}.jar")
            if os.path.exists(child_jar):
                merged["client_jar"] = child_jar
            else:
                merged["client_jar"] = os.path.join(BASE_DIR, "versions", parent_ver, f"{parent_ver}.jar")

            return merged

    child_jar = os.path.join(BASE_DIR, "versions", version, f"{version}.jar")
    data["client_jar"] = child_jar
    return data


def build_game_arguments(json_data, player_name, version, working_dir, assets_dir, uuid):
    assets_index = str(json_data.get("assets", json_data.get("assetIndex", {}).get("id", "legacy")))

    if "arguments" in json_data and "game" in json_data["arguments"]:
        raw_args = json_data["arguments"]["game"]
        parsed_args = []
        for arg in raw_args:
            if isinstance(arg, str):
                parsed_args.append(arg)
            elif isinstance(arg, dict):
                value = arg.get("value", "")
                if isinstance(value, str):
                    parsed_args.append(value)
                elif isinstance(value, list):
                    parsed_args.extend([v for v in value if isinstance(v, str)])
        game_args_str = " ".join(parsed_args)
    else:
        game_args_str = json_data.get(
            "minecraftArguments",
            "--username ${auth_player_name} --version ${version_name} --gameDir ${game_directory} --assetsDir ${assets_root} --assetIndex ${assets_index_name} --uuid ${auth_uuid} --accessToken ${auth_access_token} --userType ${user_type}",
        )

    clean_working_dir = os.path.abspath(working_dir).rstrip("\\/")
    clean_assets_dir = os.path.abspath(assets_dir).rstrip("\\/")

    replacements = {
        "${auth_player_name}": player_name,
        "${version_name}": version,
        "${game_directory}": f'"{clean_working_dir}"',
        "${assets_root}": f'"{clean_assets_dir}"',
        "${assets_index_name}": assets_index,
        "${auth_uuid}": uuid,
        "${auth_access_token}": "00000000000000000000000000000000",
        "${user_type}": "mojang",
        "${version_type}": json_data.get("type", "release"),
    }

    for key, val in replacements.items():
        game_args_str = game_args_str.replace(key, val)

    return game_args_str


class RoundedButton(tk.Canvas):
    """Custom Canvas widget offering smooth rounded corner buttons."""

    def __init__(
        self,
        parent,
        text,
        command=None,
        width=95,
        height=28,
        radius=10,
        bg_color="#e0e0e0",
        hover_color="#d0d0d0",
        fg_color="#000000",
        font=("Arial", 9),
        state="normal",
        **kwargs,
    ):
        canvas_bg = "#f0f0f0"
        for key in ("bg", "background"):
            try:
                canvas_bg = parent.cget(key)
                break
            except Exception:
                pass

        super().__init__(
            parent,
            borderwidth=0,
            highlightthickness=0,
            width=width,
            height=height,
            bg=canvas_bg,
            **kwargs,
        )
        self.command = command
        self.radius = radius
        self.bg_color = bg_color
        self.hover_color = hover_color
        self.fg_color = fg_color
        self.btn_state = state
        self.btn_width = width
        self.btn_height = height
        self.text_str = text
        self.font = font

        self.draw_button()
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def draw_button(self):
        self.delete("all")
        if self.btn_state == "disabled":
            fill_c = "#e6e6e6"
            text_c = "#a0a0a0"
            outline_c = "#cccccc"
        else:
            fill_c = self.bg_color
            text_c = self.fg_color
            outline_c = "#8f8f8f"

        r = self.radius
        w = self.btn_width - 1
        h = self.btn_height - 1

        points = [
            r, 0,
            w - r, 0,
            w, 0, w, r,
            w, h - r,
            w, h, w - r, h,
            r, h,
            0, h, 0, h - r,
            0, r,
            0, 0,
        ]

        self.poly = self.create_polygon(points, smooth=True, fill=fill_c, outline=outline_c, width=1)
        self.txt = self.create_text(w / 2, h / 2, text=self.text_str, fill=text_c, font=self.font)

    def config_state(self, state):
        self.btn_state = state
        self.draw_button()

    def _on_enter(self, event):
        if self.btn_state != "disabled":
            self.itemconfig(self.poly, fill=self.hover_color)

    def _on_leave(self, event):
        if self.btn_state != "disabled":
            self.itemconfig(self.poly, fill=self.bg_color)

    def _on_click(self, event):
        if self.btn_state != "disabled" and self.command:
            self.command()


class TaskProgressDialog:
    """Slim popup window containing progress status and cancel capability."""

    def __init__(self, parent, title="Task in Progress", cancel_callback=None):
        self.win = tk.Toplevel(parent)
        self.win.title(title)
        self.win.geometry("360x130")
        self.win.resizable(False, False)
        self.win.grab_set()

        self.cancel_callback = cancel_callback

        self.status_label = ttk.Label(self.win, text="Initializing...", anchor="center", font=("Arial", 9))
        self.status_label.pack(pady=(12, 6), fill="x", padx=15)

        self.progress_bar = ttk.Progressbar(self.win, length=320, mode="determinate")
        self.progress_bar.pack(pady=4)

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(pady=10)

        self.cancel_btn = RoundedButton(
            btn_frame,
            text="Cancel",
            command=self._on_cancel,
            width=85,
            height=26,
            radius=8,
        )
        self.cancel_btn.pack()

    def update_progress(self, current, max_val, text):
        self.progress_bar.config(maximum=max_val, value=current)
        self.status_label.config(text=text)

    def set_status(self, text):
        self.status_label.config(text=text)

    def _on_cancel(self):
        if self.cancel_callback:
            self.cancel_callback()
        self.cancel_btn.config_state("disabled")
        self.status_label.config(text="Cancelling task...")

    def close(self):
        try:
            self.win.grab_release()
            self.win.destroy()
        except Exception:
            pass


class HelpDialog:
    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("Help & Documentation")
        self.win.geometry("601x520")
        self.win.resizable(False, False)
        self.win.grab_set()

        ttk.Label(
            self.win,
            text="About",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=8)

        text_frame = ttk.Frame(self.win)
        text_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(text_frame)
        scrollbar.pack(side="right", fill="y")

        self.text_area = tk.Text(text_frame, yscrollcommand=scrollbar.set, wrap="word", font=("Consolas", 9))
        self.text_area.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.text_area.yview)

        self.populate_help_content()
        self.text_area.config(state="disabled")

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=10, pady=8)
        RoundedButton(btn_frame, text="Close", command=self.win.destroy, width=80, height=26, radius=8).pack(side="right")

    def populate_help_content(self):
        lines = [
            "================================================================================",
            "                        LITMUS LAUNCHER DOCUMENTATION",
            "================================================================================",
            "",
            "1. OVERVIEW",
            "--------------------------------------------------------------------------------",
            "> Litmus Launcher is an extremely lightweight Minecraft launcher.",
            "> Creator: Amithrosky",
            f"> Launcher version: {APP_VERSION}",
            "",
            "2. CONTROLS & SETTINGS",
            "--------------------------------------------------------------------------------",
            "> Username: Set in-game name (3+ chars)",
            "> RAM (MB): System memory allocation for JVM",
            "> Version: Select installed Minecraft version",
            "> Java Runtime: Pick Java binary path",
            "",
            "3. MODS MANAGEMENT & MODRINTH API",
            "--------------------------------------------------------------------------------",
            "> Add Mods: Click 'Add Mod...' to copy .jar files into .minecraft/mods",
            "> Explore Modrinth: Search and download mods directly from Modrinth within the launcher",
            "> Enable/Disable: Select a mod and click 'Toggle' to enable or disable it",
            "> Delete: Select a mod and click 'Delete' to permanently remove it",
            "",
        ]
        self.text_area.insert("1.0", "\n".join(lines))


class ModrinthBrowserDialog:
    """Robust built-in Modrinth API browser with correct facet and version query handling."""

    def __init__(self, parent, mods_dir, refresh_callback):
        self.mods_dir = mods_dir
        self.refresh_callback = refresh_callback

        self.win = tk.Toplevel(parent)
        self.win.title("Modrinth Mod Browser")
        self.win.geometry("640x440")
        self.win.resizable(False, False)
        self.win.grab_set()

        # Top Bar (Search & Version filter)
        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill="x", padx=10, pady=10)

        ttk.Label(top_frame, text="Search:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 5))
        self.search_entry = ttk.Entry(top_frame, width=22)
        self.search_entry.pack(side="left", padx=(0, 10))
        self.search_entry.bind("<Return>", lambda e: self.perform_search())

        ttk.Label(top_frame, text="MC Version:", font=("Arial", 9)).pack(side="left", padx=(0, 5))
        self.ver_entry = ttk.Entry(top_frame, width=10)
        self.ver_entry.insert(0, "1.20.1")
        self.ver_entry.pack(side="left", padx=(0, 10))

        RoundedButton(top_frame, text="Search", command=self.perform_search, width=70, height=26, radius=8).pack(side="left")

        # Main Body (Split into List and Details)
        body_frame = ttk.Frame(self.win)
        body_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Left Listbox
        list_container = ttk.Frame(body_frame)
        list_container.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(list_container)
        scrollbar.pack(side="right", fill="y")

        self.results_listbox = tk.Listbox(list_container, yscrollcommand=scrollbar.set, font=("Consolas", 9))
        self.results_listbox.pack(side="left", fill="both", expand=True)
        self.results_listbox.bind("<<ListboxSelect>>", self.on_select_mod)
        scrollbar.config(command=self.results_listbox.yview)

        # Right Details / Description area
        right_container = ttk.Frame(body_frame, width=260)
        right_container.pack(side="right", fill="both", padx=(10, 0))

        self.desc_text = tk.Text(right_container, wrap="word", width=32, height=16, font=("Arial", 9))
        self.desc_text.pack(fill="both", expand=True, pady=(0, 8))
        self.desc_text.config(state="disabled")

        self.install_btn = RoundedButton(right_container, text="Install Mod", command=self.install_selected_mod, width=110, height=28, radius=8, state="disabled")
        self.install_btn.pack(anchor="center")

        self.search_results = []
        self.selected_mod_data = None

        self.perform_search()

    def perform_search(self):
        query = self.search_entry.get().strip()
        mc_ver = self.ver_entry.get().strip()

        self.results_listbox.delete(0, tk.END)
        self.search_results.clear()
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", "Searching Modrinth API...")
        self.desc_text.config(state="disabled")
        self.install_btn.config_state("disabled")

        def fetch():
            try:
                facets = [["project_type:mod"]]
                if mc_ver:
                    facets.append([f"versions:{mc_ver}"])

                params = {
                    "query": query,
                    "facets": json.dumps(facets),
                    "limit": 25
                }
                encoded_params = urllib.parse.urlencode(params)
                url = f"https://api.modrinth.com/v2/search?{encoded_params}"

                req = urllib.request.Request(url, headers={"User-Agent": "LitmusLauncher/1.9.27 (contact@litmuslauncher.org)"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    hits = data.get("hits", [])
                    self.win.after(0, lambda: self._update_results(hits))
            except Exception as e:
                self.win.after(0, lambda: self._show_error(str(e)))

        threading.Thread(target=fetch, daemon=True).start()

    def _update_results(self, hits):
        self.search_results = hits
        self.results_listbox.delete(0, tk.END)
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", tk.END)
        if not hits:
            self.desc_text.insert("1.0", "No mods found matching criteria. Try clearing or changing the MC Version filter.")
        else:
            self.desc_text.insert("1.0", "Select a mod to view details.")
        self.desc_text.config(state="disabled")

        for hit in hits:
            title = hit.get("title", "Unknown")
            downloads = hit.get("downloads", 0)
            self.results_listbox.insert(tk.END, f"{title} ({downloads:,} dl)")

    def _show_error(self, err_msg):
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", f"Failed to fetch from Modrinth:\n{err_msg}")
        self.desc_text.config(state="disabled")

    def on_select_mod(self, event):
        sel = self.results_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.search_results):
            return

        mod = self.search_results[idx]
        self.selected_mod_data = mod

        title = mod.get("title", "")
        desc = mod.get("description", "")
        author = mod.get("author", "")
        downloads = mod.get("downloads", 0)

        details = f"Title: {title}\nAuthor: {author}\nDownloads: {downloads:,}\n\nDescription:\n{desc}"
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", details)
        self.desc_text.config(state="disabled")
        self.install_btn.config_state("normal")

    def install_selected_mod(self):
        if not self.selected_mod_data:
            return

        # Modrinth returns project_id or project_id via 'project_id' or 'slug'
        project_id = self.selected_mod_data.get("project_id") or self.selected_mod_data.get("slug")
        title = self.selected_mod_data.get("title", "Mod")
        mc_ver = self.ver_entry.get().strip()

        self.install_btn.config_state("disabled")
        self.desc_text.config(state="normal")
        self.desc_text.insert(tk.END, f"\n\nFetching versions for {title}...")
        self.desc_text.config(state="disabled")

        def fetch_versions():
            try:
                # Query version endpoint with filters to guarantee a compatible .jar file
                versions_url = f"https://api.modrinth.com/v2/project/{project_id}/version"
                if mc_ver:
                    query_params = urllib.parse.urlencode({"game_versions": json.dumps([mc_ver])})
                    versions_url += f"?{query_params}"

                req = urllib.request.Request(versions_url, headers={"User-Agent": "LitmusLauncher/1.9.27 (contact@litmuslauncher.org)"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    v_data = json.loads(resp.read().decode("utf-8"))

                if not v_data and mc_ver:
                    # Fallback: query without version filter if specific version returned empty
                    fallback_url = f"https://api.modrinth.com/v2/project/{project_id}/version"
                    req = urllib.request.Request(fallback_url, headers={"User-Agent": "LitmusLauncher/1.9.27"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        v_data = json.loads(resp.read().decode("utf-8"))

                target_file_url = None
                target_filename = None

                for ver_obj in v_data:
                    files = ver_obj.get("files", [])
                    for f in files:
                        if f.get("filename", "").endswith(".jar"):
                            if f.get("primary", False):
                                target_file_url = f.get("url")
                                target_filename = f.get("filename")
                                break
                            elif not target_file_url:
                                target_file_url = f.get("url")
                                target_filename = f.get("filename")
                    if target_file_url:
                        break

                if target_file_url and target_filename:
                    dest_path = os.path.join(self.mods_dir, target_filename)
                    success = download_file_http(target_file_url, dest_path)
                    if success:
                        self.win.after(0, lambda: messagebox.showinfo("Success", f"Successfully installed {target_filename}!"))
                        self.win.after(0, self.refresh_callback)
                    else:
                        self.win.after(0, lambda: messagebox.showerror("Error", "Failed to download the mod .jar file."))
                else:
                    self.win.after(0, lambda: messagebox.showwarning("Incompatible", f"No downloadable .jar file found for this mod."))

            except Exception as e:
                self.win.after(0, lambda err=e: messagebox.showerror("Error", f"Installation failed:\n{err}"))
            finally:
                self.win.after(0, lambda: self.install_btn.config_state("normal"))

        threading.Thread(target=fetch_versions, daemon=True).start()


class ModsDialog:
    """Enhanced Mods Manager with Toggle, Delete, Search, and Modrinth API integration."""

    def __init__(self, parent):
        self.win = tk.Toplevel(parent)
        self.win.title("Mods Manager")
        self.win.geometry("520x380")
        self.win.resizable(False, False)
        self.win.grab_set()

        self.mods_dir = os.path.join(BASE_DIR, "mods")
        create_directory_recursive(self.mods_dir)

        # Top Filter Frame
        top_frame = ttk.Frame(self.win)
        top_frame.pack(fill="x", padx=10, pady=(8, 2))

        ttk.Label(top_frame, text="Search Mods:", font=("Arial", 9, "bold")).pack(side="left", padx=(0, 5))
        self.search_entry = ttk.Entry(top_frame)
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<KeyRelease>", lambda e: self.refresh_mods())

        # Listbox Frame with Scrollbar
        list_frame = ttk.Frame(self.win)
        list_frame.pack(fill="both", expand=True, padx=10, pady=5)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, font=("Consolas", 9), selectmode=tk.SINGLE)
        self.listbox.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)

        # Status Label
        self.status_lbl = ttk.Label(self.win, text="Total Mods: 0", font=("Arial", 8, "italic"))
        self.status_lbl.pack(anchor="w", padx=10, pady=(0, 2))

        # Action Buttons
        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=10, pady=8)

        RoundedButton(btn_frame, text="Add Mod...", command=self.add_mod, width=75, height=26, radius=8).pack(side="left", padx=2)
        RoundedButton(btn_frame, text="Explore Modrinth", command=self.open_modrinth_browser, width=115, height=26, radius=8).pack(side="left", padx=2)
        RoundedButton(btn_frame, text="Toggle", command=self.toggle_mod, width=55, height=26, radius=8).pack(side="left", padx=2)
        RoundedButton(btn_frame, text="Delete", command=self.delete_mod, width=55, height=26, radius=8).pack(side="left", padx=2)
        RoundedButton(btn_frame, text="Folder", command=self.open_folder, width=55, height=26, radius=8).pack(side="left", padx=2)
        RoundedButton(btn_frame, text="Close", command=self.win.destroy, width=55, height=26, radius=8).pack(side="right", padx=2)

        self.mod_items = []
        self.refresh_mods()

    def refresh_mods(self):
        self.listbox.delete(0, tk.END)
        self.mod_items.clear()
        search_query = self.search_entry.get().strip().lower()

        enabled_count = 0
        disabled_count = 0

        if os.path.exists(self.mods_dir):
            for file in sorted(os.listdir(self.mods_dir)):
                if file.endswith(".jar"):
                    enabled_count += 1
                    status_str = f"[ENABLED]  {file}"
                    if not search_query or search_query in file.lower():
                        self.mod_items.append((file, True))
                        self.listbox.insert(tk.END, status_str)
                elif file.endswith(".jar.disabled"):
                    disabled_count += 1
                    status_str = f"[DISABLED] {file[:-9]}"
                    if not search_query or search_query in file.lower():
                        self.mod_items.append((file, False))
                        self.listbox.insert(tk.END, status_str)

        total = enabled_count + disabled_count
        self.status_lbl.config(text=f"Total Mods: {total} ({enabled_count} Active, {disabled_count} Disabled)")

    def add_mod(self):
        files = filedialog.askopenfilenames(filetypes=[("Minecraft Mods", "*.jar")])
        if not files:
            return
        added = 0
        for f in files:
            dest = os.path.join(self.mods_dir, os.path.basename(f))
            try:
                shutil.copy2(f, dest)
                added += 1
            except Exception as e:
                messagebox.showerror("Error", f"Failed to add mod {os.path.basename(f)}:\n{e}")
        if added > 0:
            self.refresh_mods()

    def open_modrinth_browser(self):
        ModrinthBrowserDialog(self.win, self.mods_dir, self.refresh_mods)

    def toggle_mod(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Selection", "Please select a mod from the list to toggle.")
            return
        idx = sel[0]
        filename, is_enabled = self.mod_items[idx]
        old_path = os.path.join(self.mods_dir, filename)

        if is_enabled:
            new_path = old_path + ".disabled"
        else:
            new_path = old_path[:-9] if old_path.endswith(".disabled") else old_path

        try:
            os.rename(old_path, new_path)
            self.refresh_mods()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to toggle mod:\n{e}")

    def delete_mod(self):
        sel = self.listbox.curselection()
        if not sel:
            messagebox.showwarning("Selection", "Please select a mod from the list to delete.")
            return
        idx = sel[0]
        filename, _ = self.mod_items[idx]
        target_path = os.path.join(self.mods_dir, filename)

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete:\n{filename}?"):
            try:
                os.remove(target_path)
                self.refresh_mods()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete mod:\n{e}")

    def open_folder(self):
        open_folder_in_explorer(self.mods_dir)


class SettingsDialog:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Litmus Launcher Settings")
        self.win.geometry("400x380")
        self.win.resizable(False, False)
        self.win.grab_set()

        ttk.Label(self.win, text="Launch Parameters:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        self.args_entry = ttk.Entry(self.win, width=32)
        self.args_entry.insert(0, cfg.get("LaunchArguments", DEFAULT_JAVA_ARGS))
        self.args_entry.grid(row=0, column=1, padx=10, pady=5, columnspan=2)

        ttk.Label(self.win, text="Custom Java Path:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        self.java_entry = ttk.Entry(self.win, width=22)
        self.java_entry.insert(0, cfg.get("JavaPath", "javaw.exe"))
        self.java_entry.grid(row=1, column=1, padx=(10, 2), pady=5, sticky="w")

        RoundedButton(self.win, text="Detect", command=self.detect_java, width=60, height=24, radius=6).grid(row=1, column=2, padx=(2, 10), pady=5)

        ttk.Label(self.win, text="Download Threads:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        self.threads_entry = ttk.Entry(self.win, width=32)
        self.threads_entry.insert(0, cfg.get("DownloadThreads", "20"))
        self.threads_entry.grid(row=2, column=1, padx=10, pady=5, columnspan=2)

        # Quick RAM Allocation Frame
        ram_frame = ttk.Frame(self.win)
        ram_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=2)
        ttk.Label(ram_frame, text="RAM Presets:").pack(side="left", padx=(0, 5))
        for ram_val in ["2048", "4096", "8192", "12288"]:
            RoundedButton(
                ram_frame,
                text=f"{int(ram_val)//1024}GB",
                command=lambda v=ram_val: self.set_ram_preset(v),
                width=45,
                height=22,
                radius=6,
            ).pack(side="left", padx=2)

        self.async_var = tk.IntVar(value=cfg.getint("AsyncDownload", 1))
        ttk.Checkbutton(self.win, text="Fast Multithreaded Downloading", variable=self.async_var).grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        self.missing_libs_var = tk.IntVar(value=cfg.getint("DownloadMissingLibs", 1))
        ttk.Checkbutton(self.win, text="Download Missing Libraries on Game Start", variable=self.missing_libs_var).grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        self.save_launch_var = tk.IntVar(value=cfg.getint("SaveLaunchString", 0))
        ttk.Checkbutton(self.win, text="Save Launch String to file (launch_string.txt)", variable=self.save_launch_var).grid(row=6, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        self.use_custom_java_var = tk.IntVar(value=cfg.getint("UseCustomJava", 0))
        ttk.Checkbutton(self.win, text="Use Custom Java Path", variable=self.use_custom_java_var).grid(row=7, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        self.use_custom_params_var = tk.IntVar(value=cfg.getint("UseCustomParameters", 0))
        ttk.Checkbutton(self.win, text="Use Custom Launch Parameters", variable=self.use_custom_params_var).grid(row=8, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        self.keep_open_var = tk.IntVar(value=cfg.getint("KeepLauncherOpen", 0))
        ttk.Checkbutton(self.win, text="Keep Launcher Open While Game Runs", variable=self.keep_open_var).grid(row=9, column=0, columnspan=3, sticky="w", padx=10, pady=2)

        btn_row = ttk.Frame(self.win)
        btn_row.grid(row=10, column=0, columnspan=3, pady=12)

        RoundedButton(btn_row, text="Save and Apply", command=self.save_settings, width=110, height=26, radius=8).pack(side="left", padx=3)
        RoundedButton(btn_row, text="Clear Cache", command=self.clear_cache, width=90, height=26, radius=8).pack(side="left", padx=3)
        RoundedButton(btn_row, text="Open Game Dir", command=lambda: open_folder_in_explorer(BASE_DIR), width=100, height=26, radius=8).pack(side="left", padx=3)

    def set_ram_preset(self, val):
        self.app.ram_entry.delete(0, tk.END)
        self.app.ram_entry.insert(0, val)
        messagebox.showinfo("RAM Preset", f"Memory allocation set to {val} MB ({int(val)//1024} GB).")

    def detect_java(self):
        javas = find_java_paths()
        if javas:
            path = javas[0][1]
            self.java_entry.delete(0, tk.END)
            self.java_entry.insert(0, path)
            messagebox.showinfo("Java Detected", f"Found Java Runtime:\n{path}")
        else:
            messagebox.showwarning("Java Search", "No installed Java runtime found automatically.")

    def clear_cache(self):
        if os.path.exists(TEMP_DIR):
            try:
                shutil.rmtree(TEMP_DIR)
                create_directory_recursive(TEMP_DIR)
                messagebox.showinfo("Cache Cleared", "Temporary download cache cleared successfully!")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear cache:\n{e}")

    def save_settings(self):
        cfg.set("LaunchArguments", self.args_entry.get().strip())
        cfg.set("JavaPath", self.java_entry.get().strip())
        cfg.set("DownloadThreads", self.threads_entry.get().strip() or "20")
        cfg.set("AsyncDownload", self.async_var.get())
        cfg.set("DownloadMissingLibs", self.missing_libs_var.get())
        cfg.set("SaveLaunchString", self.save_launch_var.get())
        cfg.set("UseCustomJava", self.use_custom_java_var.get())
        cfg.set("UseCustomParameters", self.use_custom_params_var.get())
        cfg.set("KeepLauncherOpen", self.keep_open_var.get())

        self.app.refresh_java_list()
        self.win.destroy()


class DownloaderDialog:
    def __init__(self, app):
        self.app = app
        self.win = tk.Toplevel(app.root)
        self.win.title("Version Downloader")
        self.win.geometry("380x160")
        self.win.resizable(False, False)
        self.win.grab_set()

        self.show_all_var = tk.IntVar(value=cfg.getint("ShowAllVersions", 0))
        self.redownload_var = tk.IntVar(value=cfg.getint("RedownloadFiles", 0))

        ttk.Checkbutton(self.win, text="Show Snapshots/Other Versions", variable=self.show_all_var, command=self.load_versions).pack(anchor="w", padx=10, pady=5)
        ttk.Checkbutton(self.win, text="Force Redownload All Files", variable=self.redownload_var).pack(anchor="w", padx=10, pady=5)

        self.versions_combo = ttk.Combobox(self.win, state="readonly")
        self.versions_combo.pack(fill="x", padx=10, pady=10)

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(pady=10)

        RoundedButton(btn_frame, text="Download", command=self.start_download, width=90, height=28, radius=8).pack(side="left", padx=5)
        RoundedButton(btn_frame, text="Close", command=self.win.destroy, width=80, height=28, radius=8).pack(side="left", padx=5)

        self.versions_manifest_data = None
        self.load_versions()

    def load_versions(self):
        def fetch():
            try:
                url = "https://launchermeta.mojang.com/mc/game/version_manifest.json"
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    self.versions_manifest_data = json.loads(resp.read().decode("utf-8"))

                versions_list = []
                for elem in self.versions_manifest_data.get("versions", []):
                    if not self.show_all_var.get() and elem.get("type") != "release":
                        continue
                    versions_list.append(elem.get("id"))

                self.win.after(0, lambda: self._update_combo(versions_list))
            except Exception:
                self.win.after(0, lambda: self._update_combo(["Error loading versions"]))

        threading.Thread(target=fetch, daemon=True).start()

    def _update_combo(self, versions):
        self.versions_combo["values"] = versions
        if versions:
            self.versions_combo.current(0)

    def start_download(self):
        version = self.versions_combo.get()
        if not version or version.startswith("Error"):
            return

        cfg.set("ShowAllVersions", self.show_all_var.get())
        cfg.set("RedownloadFiles", self.redownload_var.get())

        manifest_url = ""
        for elem in self.versions_manifest_data.get("versions", []):
            if elem.get("id") == version:
                manifest_url = elem.get("url")
                break

        if not manifest_url:
            messagebox.showerror("Error", "Could not resolve manifest URL.")
            return

        self.win.destroy()
        self.app.prepare_and_run_download(version, manifest_url, self.redownload_var.get())


class MainApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.geometry("420x260")
        self.root.resizable(False, False)

        self.cancel_event = threading.Event()
        self.active_progress_dialog = None

        ttk.Label(root, text=APP_TITLE, font=("Arial", 14, "bold")).pack(pady=8)

        frame = ttk.Frame(root)
        frame.pack(padx=15, pady=5, fill="x")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Username:").grid(row=0, column=0, sticky="w", pady=4, padx=(0, 10))
        self.name_entry = ttk.Entry(frame)
        self.name_entry.insert(0, cfg.get("Name", "Player"))
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="RAM (MB):").grid(row=1, column=0, sticky="w", pady=4, padx=(0, 10))
        self.ram_entry = ttk.Entry(frame)
        self.ram_entry.insert(0, cfg.get("Ram", "2048"))
        self.ram_entry.grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Version:").grid(row=2, column=0, sticky="w", pady=4, padx=(0, 10))
        self.version_combo = ttk.Combobox(frame, state="readonly")
        self.version_combo.grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text="Java Runtime:").grid(row=3, column=0, sticky="w", pady=4, padx=(0, 10))
        self.java_combo = ttk.Combobox(frame, state="readonly")
        self.java_combo.grid(row=3, column=1, sticky="ew", pady=4)

        btn_frame = ttk.Frame(root)
        btn_frame.pack(pady=12)

        RoundedButton(btn_frame, text="Start Playing", command=self.launch_minecraft, width=95, height=28, radius=8).grid(row=0, column=0, padx=4)
        RoundedButton(btn_frame, text="Downloader", command=lambda: DownloaderDialog(self), width=90, height=28, radius=8).grid(row=0, column=1, padx=4)
        RoundedButton(btn_frame, text="Mods", command=lambda: ModsDialog(self.root), width=70, height=28, radius=8).grid(row=0, column=2, padx=4)
        RoundedButton(btn_frame, text="Settings", command=lambda: SettingsDialog(self), width=75, height=28, radius=8).grid(row=0, column=3, padx=4)

        bottom_bar = ttk.Frame(root)
        bottom_bar.pack(side="bottom", fill="x", padx=10, pady=5)

        RoundedButton(bottom_bar, text="Help", command=lambda: HelpDialog(self.root), width=65, height=24, radius=6).pack(side="left")
        ttk.Label(bottom_bar, text=f"by {APP_DEVELOPER}", font=("Arial", 8, "italic")).pack(side="right")

        self.refresh_installed_versions()
        self.refresh_java_list()
        self.generate_profile_json()

    def cancel_task(self):
        self.cancel_event.set()

    def refresh_installed_versions(self):
        versions = []
        versions_dir = os.path.join(BASE_DIR, "versions")
        if os.path.exists(versions_dir):
            for entry in os.listdir(versions_dir):
                v_json = os.path.join(versions_dir, entry, f"{entry}.json")
                if os.path.exists(v_json):
                    versions.append(entry)

        self.version_combo["values"] = sorted(versions, reverse=True)
        chosen = cfg.get("ChosenVer", "")
        if chosen in versions:
            self.version_combo.set(chosen)
        elif versions:
            self.version_combo.current(0)
        else:
            self.version_combo["values"] = ["No versions found"]
            self.version_combo.current(0)

    def refresh_java_list(self):
        if cfg.getint("UseCustomJava", 0):
            self.java_combo["values"] = ["Custom Java Enabled"]
            self.java_combo.current(0)
            self.java_combo.config(state="disabled")
        else:
            self.java_combo.config(state="readonly")
            self.installed_javas = find_java_paths()
            labels = [j[0] for j in self.installed_javas]
            if labels:
                self.java_combo["values"] = labels
                self.java_combo.current(0)
            else:
                self.java_combo["values"] = ["Java Not Found (Will use PATH)"]
                self.java_combo.current(0)

    def generate_profile_json(self):
        pfile = os.path.join(BASE_DIR, "launcher_profiles.json")
        if not os.path.exists(pfile) or os.path.getsize(pfile) == 0:
            data = {"profiles": {"LitmusProfile": {"name": "LitmusProfile", "lastVersionId": "1.12.2"}}}
            try:
                with open(pfile, "w", encoding="utf-8") as f:
                    json.dump(data, f)
            except Exception:
                pass

    def prepare_and_run_download(self, version, manifest_url, force_redownload):
        self.cancel_event.clear()
        self.active_progress_dialog = TaskProgressDialog(
            self.root,
            title="Downloading Version",
            cancel_callback=self.cancel_task,
        )
        self.active_progress_dialog.set_status("Preparing file manifest...")

        def thread_target():
            try:
                v_dir = os.path.join(BASE_DIR, "versions", version)
                create_directory_recursive(v_dir)
                json_target = os.path.join(v_dir, f"{version}.json")

                if not download_file_http(manifest_url, json_target, self.cancel_event):
                    self.finish_download("Download Cancelled")
                    return

                download_list_path = os.path.join(TEMP_DIR, "vlauncher_download_list.txt")
                lines = []

                content = file_read(json_target)
                if content:
                    data = json.loads(content)
                    assets_index = str(data.get("assets", ""))

                    create_directory_recursive(os.path.join(BASE_DIR, "assets", "indexes"))
                    asset_url = data.get("assetIndex", {}).get("url")
                    if asset_url:
                        download_file_http(asset_url, os.path.join(BASE_DIR, "assets", "indexes", f"{assets_index}.json"), self.cancel_event)

                    logging_member = data.get("logging", {}).get("client", {}).get("file", {})
                    if logging_member and logging_member.get("url"):
                        lines.append(f"{logging_member.get('url')}::{os.path.join(BASE_DIR, 'assets', 'log_configs', logging_member.get('id', ''))}::{logging_member.get('size', 0)}")

                    dl_client = data.get("downloads", {}).get("client", {})
                    if dl_client and dl_client.get("url"):
                        lines.append(f"{dl_client.get('url')}::{os.path.join(BASE_DIR, 'versions', version, version + '.jar')}::{dl_client.get('size', 0)}")

                    index_path = os.path.join(BASE_DIR, "assets", "indexes", f"{assets_index}.json")
                    idx_content = file_read(index_path)
                    if idx_content:
                        idx_data = json.loads(idx_content)
                        for _, obj in idx_data.get("objects", {}).items():
                            file_hash = obj.get("hash", "")
                            file_size = obj.get("size", 0)
                            sub = file_hash[:2]
                            lines.append(f"https://resources.download.minecraft.net/{sub}/{file_hash}::{os.path.join(BASE_DIR, 'assets', 'objects', sub, file_hash)}::{file_size}")

                    for lib in data.get("libraries", []):
                        if not is_library_allowed(lib):
                            continue

                        downloads = lib.get("downloads", {})
                        artifact = downloads.get("artifact", {})
                        if artifact and artifact.get("url"):
                            path = os.path.join(BASE_DIR, "libraries", artifact.get("path", "").replace("/", os.sep))
                            lines.append(f"{artifact.get('url')}::{path}::{artifact.get('size', 0)}")

                        classifiers = downloads.get("classifiers", {})
                        natives_dict = lib.get("natives", {})
                        if "windows" in natives_dict:
                            native_key = natives_dict["windows"].replace("${arch}", "64" if sys.maxsize > 2**32 else "32")
                            if native_key in classifiers:
                                native_artifact = classifiers[native_key]
                                if native_artifact.get("url"):
                                    path = os.path.join(BASE_DIR, "libraries", native_artifact.get("path", "").replace("/", os.sep))
                                    lines.append(f"{native_artifact.get('url')}::{path}::{native_artifact.get('size', 0)}")

                with open(download_list_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))

                self.execute_file_downloads(force_redownload)

            except Exception as e:
                self.finish_download(f"Error: {e}")

        threading.Thread(target=thread_target, daemon=True).start()

    def execute_file_downloads(self, force_redownload):
        list_path = os.path.join(TEMP_DIR, "vlauncher_download_list.txt")
        if not os.path.exists(list_path):
            self.finish_download("Download failed: empty list")
            return

        with open(list_path, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]

        lines_total = len(lines)
        lines_remaining = [lines_total]
        threads_count = cfg.getint("DownloadThreads", 20)

        def process_item(line):
            if self.cancel_event.is_set():
                return False

            parts = line.split("::")
            if len(parts) < 2:
                return True

            url, dest = parts[0], parts[1]
            req_size = int(parts[2]) if len(parts) >= 3 and parts[2].isdigit() else 0
            file_size = os.path.getsize(dest) if os.path.exists(dest) else -1

            if force_redownload or file_size == -1 or (req_size != 0 and file_size != req_size):
                for _ in range(3):
                    if self.cancel_event.is_set():
                        return False
                    if download_file_http(url, dest, self.cancel_event):
                        break
                    time.sleep(0.2)

            lines_remaining[0] -= 1
            cur = lines_total - lines_remaining[0]
            if self.active_progress_dialog:
                self.root.after(
                    0,
                    lambda c=cur, r=lines_remaining[0]: self.active_progress_dialog.update_progress(
                        c, lines_total, f"Files remaining: {r}"
                    ),
                )
            return True

        if cfg.getint("AsyncDownload", 1):
            with concurrent.futures.ThreadPoolExecutor(max_workers=threads_count) as executor:
                futures = [executor.submit(process_item, line) for line in lines]
                for future in concurrent.futures.as_completed(futures):
                    if self.cancel_event.is_set():
                        break
        else:
            for line in lines:
                if self.cancel_event.is_set() or not process_item(line):
                    break

        if self.cancel_event.is_set():
            self.finish_download("Download Cancelled!")
        else:
            self.finish_download("Download Complete!")

    def finish_download(self, message):
        self.root.after(0, lambda: self._ui_finish_download(message))

    def _ui_finish_download(self, message):
        if self.active_progress_dialog:
            self.active_progress_dialog.close()
            self.active_progress_dialog = None

        if message not in ("Download Cancelled!", "Download Complete!"):
            messagebox.showinfo("Status", message)

        self.refresh_installed_versions()

    def parse_libraries_classpath(self, version_data, version):
        classpath = []
        nat_dir = os.path.join("versions", version, "natives")
        create_directory_recursive(os.path.join(BASE_DIR, nat_dir))

        for lib in version_data.get("libraries", []):
            if self.cancel_event.is_set():
                return "", ""
            if not is_library_allowed(lib):
                continue

            downloads = lib.get("downloads", {})
            artifact = downloads.get("artifact", {})
            if artifact and artifact.get("path"):
                lib_rel = os.path.join("libraries", artifact.get("path").replace("/", os.sep))
                lib_path = os.path.join(BASE_DIR, lib_rel)
                if os.path.exists(lib_path):
                    classpath.append(lib_rel)
            else:
                name = lib.get("name", "")
                parts = name.split(":")
                if len(parts) >= 3:
                    domain, lib_name, ver = parts[0].replace(".", os.sep), parts[1], parts[2]
                    classifier = f"-{parts[3]}" if len(parts) > 3 else ""
                    lib_rel = os.path.join("libraries", domain, lib_name, ver, f"{lib_name}-{ver}{classifier}.jar")
                    lib_path = os.path.join(BASE_DIR, lib_rel)
                    if os.path.exists(lib_path):
                        classpath.append(lib_rel)

            natives_dict = lib.get("natives", {})
            if "windows" in natives_dict:
                native_key = natives_dict["windows"].replace("${arch}", "64" if sys.maxsize > 2**32 else "32")
                classifiers = downloads.get("classifiers", {})
                native_path = None

                if native_key in classifiers and classifiers[native_key].get("path"):
                    native_rel = os.path.join("libraries", classifiers[native_key].get("path").replace("/", os.sep))
                    native_path = os.path.join(BASE_DIR, native_rel)
                else:
                    name = lib.get("name", "")
                    parts = name.split(":")
                    if len(parts) >= 3:
                        domain, lib_name, ver = parts[0].replace(".", os.sep), parts[1], parts[2]
                        native_rel = os.path.join("libraries", domain, lib_name, ver, f"{lib_name}-{ver}-{native_key}.jar")
                        native_path = os.path.join(BASE_DIR, native_rel)

                if native_path and os.path.exists(native_path):
                    try:
                        with zipfile.ZipFile(native_path, "r") as z:
                            for item in z.infolist():
                                if not item.filename.startswith("META-INF"):
                                    z.extract(item, os.path.join(BASE_DIR, nat_dir))
                    except Exception:
                        pass

        return ";".join(classpath), nat_dir

    def launch_minecraft(self):
        player_name = self.name_entry.get().strip()
        ram = self.ram_entry.get().strip()
        version = self.version_combo.get()

        if not player_name or len(player_name) < 3:
            messagebox.showerror("Error", "Name must be at least 3 characters long!")
            return

        if not ram.isdigit() or int(ram) < 350:
            ram = "350"
            self.ram_entry.delete(0, tk.END)
            self.ram_entry.insert(0, "350")
            messagebox.showwarning("Warning", "Allocated memory set to minimum 350 MB.")

        if version in ["No versions found", "", "Error loading versions"]:
            messagebox.showerror("Error", "Please download or select a valid Minecraft version.")
            return

        if cfg.getint("UseCustomJava", 0):
            java_path = cfg.get("JavaPath")
        else:
            idx = self.java_combo.current()
            if hasattr(self, "installed_javas") and 0 <= idx < len(self.installed_javas):
                java_path = self.installed_javas[idx][1]
            else:
                java_path = "javaw.exe"

        cfg.set("Name", player_name)
        cfg.set("Ram", ram)
        cfg.set("ChosenVer", version)

        resolved_data = get_resolved_version_data(version)
        if not resolved_data:
            messagebox.showerror("Error", f"Version metadata missing for {version}.\nPlease download it using Downloader.")
            return

        client_jar = resolved_data.get("client_jar", os.path.join("versions", version, f"{version}.jar"))

        if not os.path.exists(client_jar):
            messagebox.showerror("Error", f"Client JAR missing for {version}.\nPlease re-download the version.")
            return

        self.cancel_event.clear()
        self.active_progress_dialog = TaskProgressDialog(
            self.root,
            title="Initializing Game Launch",
            cancel_callback=self.cancel_task,
        )
        self.active_progress_dialog.update_progress(10, 100, "Reading version metadata...")

        def execute_launch_sequence():
            try:
                main_class = resolved_data.get("mainClass", "net.minecraft.client.main.Main")

                if self.cancel_event.is_set():
                    self._abort_launch("Launch cancelled.")
                    return

                self.root.after(0, lambda: self.active_progress_dialog and self.active_progress_dialog.update_progress(40, 100, "Extracting natives & classpaths..."))
                libraries_cp, natives_dir = self.parse_libraries_classpath(resolved_data, version)

                if self.cancel_event.is_set():
                    self._abort_launch("Launch cancelled.")
                    return

                full_classpath = f"{libraries_cp};{client_jar}" if libraries_cp else client_jar
                uuid = generate_offline_uuid(player_name)
                working_dir = BASE_DIR
                assets_dir = os.path.join(BASE_DIR, "assets")

                custom_args = cfg.get("LaunchArguments", DEFAULT_JAVA_ARGS) if cfg.getint("UseCustomParameters", 0) else DEFAULT_JAVA_ARGS
                game_args = build_game_arguments(resolved_data, player_name, version, working_dir, assets_dir, uuid)

                full_command = f'"{java_path}" -Xmx{ram}M {custom_args} "-Djava.library.path={natives_dir}" -cp "{full_classpath}" {main_class} {game_args}'

                if cfg.getint("SaveLaunchString", 0):
                    try:
                        with open(os.path.join(BASE_DIR, "launch_string.txt"), "w", encoding="utf-8") as f:
                            f.write(full_command)
                    except Exception:
                        pass

                if self.cancel_event.is_set():
                    self._abort_launch("Launch cancelled.")
                    return

                self.root.after(0, lambda: self.active_progress_dialog and self.active_progress_dialog.update_progress(100, 100, "Starting process..."))
                time.sleep(0.3)

                self.root.after(0, lambda: self.active_progress_dialog and self.active_progress_dialog.close())

                if not cfg.getint("KeepLauncherOpen", 0):
                    self.root.after(0, self.root.withdraw)

                proc = subprocess.Popen(full_command, cwd=working_dir, shell=True)
                proc.wait()

            except Exception as e:
                self.root.after(0, lambda err=e: messagebox.showerror("Game Crash", f"Error running game:\n{err}"))
            finally:
                if not cfg.getint("KeepLauncherOpen", 0):
                    self.root.after(0, self.root.deiconify)

        threading.Thread(target=execute_launch_sequence, daemon=True).start()

    def _abort_launch(self, reason):
        self.root.after(
            0,
            lambda: (
                self.active_progress_dialog.close() if self.active_progress_dialog else None,
                messagebox.showinfo("Game Launch", reason),
            ),
        )


if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()

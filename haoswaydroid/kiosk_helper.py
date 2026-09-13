#!/usr/bin/env python3
"""
Waydroid Kiosk Satellite Helper
Manages APK download, permissions, display resolution, audio/mic setup, port forwarding, and watchdog.
"""

import json
import os
import platform
import subprocess
import sys
import time
import urllib.request
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("kiosk_helper")

OPTIONS_PATH = "/data/options.json"
CACHE_DIR = "/data/apk_cache"
PACKAGE_NAME = "me.jxl.kiosk_satellite"
GITHUB_REPO = "jxlarrea/kiosk-satellite"

def load_options():
    if os.path.exists(OPTIONS_PATH):
        try:
            with open(OPTIONS_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read options.json: {e}")
    return {}

def run_cmd(cmd, check=False, shell=False):
    logger.debug(f"Running command: {cmd}")
    try:
        if isinstance(cmd, list) and not shell:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)
        else:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check)
        return res.returncode, res.stdout.strip(), res.stderr.strip()
    except Exception as e:
        logger.error(f"Command execution error ({cmd}): {e}")
        return 1, "", str(e)

def get_latest_release_apk_url(arch="aarch64"):
    api_url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "haos-kiosk-waydroid"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            assets = data.get("assets", [])
            tag = data.get("tag_name", "latest")
            
            target_arch_match = "arm64-v8a" if arch in ("aarch64", "arm64") else "x86_64"
            
            # Look for architecture-specific APK first
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".apk") and target_arch_match in name:
                    return asset.get("browser_download_url"), tag
            
            # Fallback to universal APK
            for asset in assets:
                name = asset.get("name", "")
                if name.endswith(".apk") and "armeabi" not in name:
                    return asset.get("browser_download_url"), tag
    except Exception as e:
        logger.error(f"Error checking GitHub releases: {e}")
    return None, None

def download_file(url, target_path):
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    temp_path = f"{target_path}.tmp"
    logger.info(f"Downloading {url} to {target_path}...")
    try:
        urllib.request.urlretrieve(url, temp_path)
        os.replace(temp_path, target_path)
        logger.info("Downloaded successfully.")
        return True
    except Exception as e:
        logger.error(f"Failed to download {url}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return False

def wait_for_waydroid_boot(timeout=120):
    logger.info("Waiting for Waydroid Android system to boot...")
    start_time = time.time()
    while time.time() - start_time < timeout:
        rc, out, _ = run_cmd(["waydroid", "shell", "getprop", "sys.boot_completed"])
        if rc == 0 and out.strip() == "1":
            logger.info("Waydroid boot completed!")
            return True
        time.sleep(2)
    logger.warning("Waydroid boot wait timed out, continuing anyway.")
    return False

def configure_display(options):
    width = options.get("display_width", 0)
    height = options.get("display_height", 0)
    dpi = options.get("display_dpi", 0)
    orientation = options.get("display_orientation", "auto")

    if width and width > 0:
        run_cmd(["waydroid", "prop", "set", "persist.waydroid.width", str(width)])
    if height and height > 0:
        run_cmd(["waydroid", "prop", "set", "persist.waydroid.height", str(height)])
    if dpi and dpi > 0:
        run_cmd(["waydroid", "prop", "set", "persist.waydroid.dpi", str(dpi)])
    if orientation and orientation != "auto":
        orientation_map = {
            "portrait": "0",
            "landscape": "90",
            "reverse-portrait": "180",
            "reverse-landscape": "270"
        }
        val = orientation_map.get(orientation, str(orientation))
        run_cmd(["waydroid", "prop", "set", "persist.waydroid.orientation", val])

def ensure_kiosk_satellite_installed(options):
    os.makedirs(CACHE_DIR, exist_ok=True)
    custom_url = options.get("apk_url", "").strip()
    auto_update = options.get("auto_update_apk", True)
    
    machine_arch = platform.machine()
    
    apk_path = os.path.join(CACHE_DIR, "kiosk-satellite.apk")
    version_file = os.path.join(CACHE_DIR, "version.txt")

    current_installed_ver = ""
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            current_installed_ver = f.read().strip()

    if custom_url:
        logger.info(f"Using custom APK URL: {custom_url}")
        if not os.path.exists(apk_path) or auto_update:
            if download_file(custom_url, apk_path):
                current_installed_ver = "custom"
    else:
        logger.info("Checking latest Kiosk Satellite release...")
        latest_url, latest_tag = get_latest_release_apk_url(machine_arch)
        if latest_url:
            if not os.path.exists(apk_path) or (auto_update and latest_tag != current_installed_ver):
                logger.info(f"Newer or missing APK detected (version: {latest_tag})")
                if download_file(latest_url, apk_path):
                    with open(version_file, "w") as f:
                        f.write(latest_tag)
        else:
            logger.warning("Could not check latest release on GitHub.")

    if os.path.exists(apk_path):
        logger.info(f"Installing APK ({apk_path}) into Waydroid...")
        rc, out, err = run_cmd(["waydroid", "app", "install", apk_path])
        if rc == 0:
            logger.info("Kiosk Satellite APK installed successfully.")
        else:
            logger.error(f"APK installation error: {err} {out}")
    else:
        logger.warning(f"No APK found at {apk_path}. Proceeding with existing installation if present.")

def grant_permissions():
    logger.info("Granting Android permissions to Kiosk Satellite...")
    permissions = [
        "android.permission.RECORD_AUDIO",
        "android.permission.CAMERA",
        "android.permission.POST_NOTIFICATIONS",
        "android.permission.SYSTEM_ALERT_WINDOW",
        "android.permission.WRITE_SETTINGS",
        "android.permission.ACCESS_FINE_LOCATION",
        "android.permission.ACCESS_COARSE_LOCATION",
        "android.permission.BLUETOOTH_SCAN",
        "android.permission.BLUETOOTH_CONNECT",
        "android.permission.READ_EXTERNAL_STORAGE",
        "android.permission.WRITE_EXTERNAL_STORAGE",
    ]
    for perm in permissions:
        run_cmd(["waydroid", "shell", "pm", "grant", PACKAGE_NAME, perm])
    
    # Disable battery optimization
    run_cmd(["waydroid", "shell", "dumpsys", "deviceidle", "whitelist", f"+{PACKAGE_NAME}"])

def setup_port_forwarding(options):
    remote_port = options.get("remote_admin_port", 2324)
    logger.info(f"Setting up port forward for Kiosk Satellite web admin on port {remote_port}")
    
    # Helper script to bridge into Waydroid Android container network namespace directly
    proxy_script = "/usr/local/bin/kiosk_proxy.sh"
    try:
        with open(proxy_script, "w") as f:
            f.write("#!/bin/sh\nPID=$(lxc-info -P /var/lib/waydroid/lxc -n waydroid -p -H 2>/dev/null)\nif [ -n \"$PID\" ]; then\n    exec nsenter -t \"$PID\" -n socat - TCP:127.0.0.1:2324\nfi\n")
        os.chmod(proxy_script, 0o755)
    except Exception as e:
        logger.error(f"Failed to create kiosk_proxy script: {e}")

    # Kill any existing socat on remote_port
    run_cmd(f"pkill -f 'socat.*{remote_port}'", shell=True)
    # Start socat background proxy
    subprocess.Popen(["socat", f"TCP-LISTEN:{remote_port},fork,reuseaddr", f"EXEC:{proxy_script}"])

def provision_android():
    logger.info("Configuring Android system settings (disabling lockscreen & sleep)...")
    run_cmd(["waydroid", "shell", "-u", "2000", "settings", "put", "global", "device_provisioned", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "settings", "put", "secure", "user_setup_complete", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "settings", "put", "secure", "lockscreen.disabled", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "settings", "put", "global", "stay_on_while_plugged_in", "3"])
    run_cmd(["waydroid", "shell", "-u", "2000", "settings", "put", "system", "screen_off_timeout", "2147483647"])
    run_cmd(["waydroid", "shell", "wm", "dismiss-keyguard"])
    run_cmd(["waydroid", "shell", "input", "keyevent", "KEYCODE_WAKEUP"])

def launch_app():
    logger.info(f"Launching {PACKAGE_NAME}...")
    run_cmd(["waydroid", "shell", "wm", "dismiss-keyguard"])
    run_cmd(["waydroid", "shell", "input", "keyevent", "KEYCODE_WAKEUP"])
    run_cmd(["waydroid", "shell", "--", "am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])

def is_app_running():
    rc, out, _ = run_cmd(["waydroid", "shell", "pidof", PACKAGE_NAME])
    return rc == 0 and bool(out.strip())

def main():
    options = load_options()
    
    # Configure display props before Waydroid session if needed
    configure_display(options)

    # Wait for Waydroid to finish booting
    wait_for_waydroid_boot()

    # Configure Android system settings
    provision_android()

    # Install / Update Kiosk-Satellite APK
    ensure_kiosk_satellite_installed(options)

    # Grant permissions (Mic, Camera, Notifications, etc.)
    grant_permissions()

    # Setup remote web admin port forwarding
    setup_port_forwarding(options)

    # Launch app
    launch_app()

    # Keep alive watchdog loop
    keep_alive = options.get("keep_alive", True)
    if keep_alive:
        logger.info("Watchdog loop started.")
        while True:
            time.sleep(10)
            if not is_app_running():
                logger.info(f"App {PACKAGE_NAME} not running, restarting...")
                launch_app()

if __name__ == "__main__":
    main()

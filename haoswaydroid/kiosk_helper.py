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

    # Auto-detect native resolution from DRM KMS if not configured
    if not width or not height or width <= 0 or height <= 0:
        try:
            import glob
            for mode_file in sorted(glob.glob("/sys/class/drm/card*-*/modes")):
                if os.path.exists(mode_file):
                    with open(mode_file, "r") as f:
                        line = f.readline().strip()
                        if "x" in line:
                            w, h = line.split("x")[:2]
                            width = int(w)
                            height = int(h)
                            logger.info(f"Auto-detected native display resolution: {width}x{height}")
                            break
        except Exception as e:
            logger.warning(f"Could not auto-detect screen resolution: {e}")

    # Set appropriate default DPI for Raspberry Pi screen sizes if not specified
    if not dpi or dpi <= 0:
        if width and width <= 1024:
            dpi = 160
        elif width and width <= 1920:
            dpi = 213
        elif width and width > 1920:
            dpi = 320

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

def is_package_installed_in_android():
    """Check if Kiosk Satellite is already installed in Android."""
    rc, out, _ = run_cmd(["waydroid", "shell", "pm", "list", "packages", PACKAGE_NAME])
    return rc == 0 and PACKAGE_NAME in out

def ensure_kiosk_satellite_installed(options):
    os.makedirs(CACHE_DIR, exist_ok=True)
    custom_url = options.get("apk_url", "").strip()
    auto_update = options.get("auto_update_apk", True)

    machine_arch = platform.machine()

    apk_path = os.path.join(CACHE_DIR, "kiosk-satellite.apk")
    version_file = os.path.join(CACHE_DIR, "version.txt")
    installed_version_file = os.path.join(CACHE_DIR, "installed_version.txt")

    # Version that was last downloaded
    downloaded_ver = ""
    if os.path.exists(version_file):
        with open(version_file, "r") as f:
            downloaded_ver = f.read().strip()

    # Version that was last installed into Android
    installed_ver = ""
    if os.path.exists(installed_version_file):
        with open(installed_version_file, "r") as f:
            installed_ver = f.read().strip()

    new_apk_downloaded = False

    if custom_url:
        logger.info(f"Using custom APK URL: {custom_url}")
        if not os.path.exists(apk_path) or auto_update:
            if download_file(custom_url, apk_path):
                downloaded_ver = "custom"
                new_apk_downloaded = (installed_ver != "custom")
                with open(version_file, "w") as f:
                    f.write(downloaded_ver)
    else:
        logger.info("Checking latest Kiosk Satellite release...")
        latest_url, latest_tag = get_latest_release_apk_url(machine_arch)
        if latest_url:
            if not os.path.exists(apk_path) or (auto_update and latest_tag != downloaded_ver):
                logger.info(f"Newer or missing APK detected (version: {latest_tag})")
                if download_file(latest_url, apk_path):
                    downloaded_ver = latest_tag
                    new_apk_downloaded = True
                    with open(version_file, "w") as f:
                        f.write(downloaded_ver)
            else:
                logger.info(f"APK already up to date (version: {downloaded_ver})")
        else:
            logger.warning("Could not check latest release on GitHub.")

    # Check if app is already installed in Android with the current version
    already_installed = is_package_installed_in_android()

    if not already_installed:
        logger.info("Kiosk Satellite not found in Android — installing for the first time.")
        need_install = True
    elif new_apk_downloaded:
        logger.info(f"New APK version downloaded ({downloaded_ver}) — updating Android installation.")
        need_install = True
    else:
        logger.info(f"Kiosk Satellite already installed (version: {installed_ver}) — skipping reinstall to preserve settings.")
        need_install = False

    if need_install and os.path.exists(apk_path):
        # Copy APK to Android's shared storage so pm can access it
        # /var/lib/waydroid/data/media/0/ maps to /sdcard/ inside Android
        sdcard_apk_host = "/var/lib/waydroid/data/media/0/kiosk-satellite-update.apk"
        sdcard_apk_android = "/sdcard/kiosk-satellite-update.apk"
        try:
            import shutil
            shutil.copy2(apk_path, sdcard_apk_host)
        except Exception as e:
            logger.warning(f"Could not copy APK to sdcard path: {e} — falling back to direct install")
            sdcard_apk_host = None

        if sdcard_apk_host and os.path.exists(sdcard_apk_host):
            # Use pm install -r: replaces the app but KEEPS all user data and settings
            if already_installed:
                logger.info("Updating APK with pm install -r (user data will be preserved)...")
                rc, out, err = run_cmd(["waydroid", "shell", "-u", "0", "--",
                                        "pm", "install", "-r", sdcard_apk_android])
            else:
                logger.info("Installing APK for the first time via pm install...")
                rc, out, err = run_cmd(["waydroid", "shell", "-u", "0", "--",
                                        "pm", "install", sdcard_apk_android])
            # Clean up temp file
            try:
                os.remove(sdcard_apk_host)
            except Exception:
                pass
        else:
            # Fallback: direct install (may wipe data on update)
            logger.warning("Falling back to waydroid app install (data may be reset on update)...")
            rc, out, err = run_cmd(["waydroid", "app", "install", apk_path])

        if rc == 0:
            logger.info("Kiosk Satellite APK installed/updated successfully — settings preserved.")
            with open(installed_version_file, "w") as f:
                f.write(downloaded_ver)
            return True  # signal: permissions need to be granted
        else:
            logger.error(f"APK installation error: {err} {out}")
            return False
    elif not os.path.exists(apk_path) and not already_installed:
        logger.warning(f"No APK found at {apk_path} and app not in Android. Cannot install.")
        return False

    return need_install  # True only when we actually installed

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
        "android.permission.FOREGROUND_SERVICE",
        "android.permission.FOREGROUND_SERVICE_SPECIAL_USE",
        "android.permission.FOREGROUND_SERVICE_MICROPHONE",
        "android.permission.FOREGROUND_SERVICE_CAMERA",
        "android.permission.FOREGROUND_SERVICE_CONNECTED_DEVICE",
    ]
    for perm in permissions:
        run_cmd(["waydroid", "shell", "pm", "grant", PACKAGE_NAME, perm])
    
    # Grant appops for alert window
    run_cmd(["waydroid", "shell", "appops", "set", PACKAGE_NAME, "SYSTEM_ALERT_WINDOW", "allow"])

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
    logger.info("Configuring Android system settings (disabling lockscreen, sleep & networking)...")
    run_cmd(["waydroid", "shell", "-u", "0", "--", "/system/bin/sh", "-c", "mount -o remount,rw /sys/fs/cgroup 2>/dev/null; echo 0 > /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || true"])
    run_cmd(["waydroid", "shell", "-u", "0", "--", "/system/bin/sh", "-c", "if ! pidof lmkd >/dev/null 2>&1; then /system/bin/lmkd & fi"])
    # Configure networking, default route & DNS
    run_cmd(["waydroid", "shell", "-u", "0", "--", "/system/bin/sh", "-c", "ip rule add pref 1 from all lookup main 2>/dev/null || true"])
    run_cmd(["waydroid", "shell", "-u", "0", "--", "/system/bin/sh", "-c", "ip route del default dev eth0 2>/dev/null; ip route add default via 192.168.240.1 dev eth0 2>/dev/null || true"])
    run_cmd(["waydroid", "shell", "-u", "0", "--", "setprop", "net.dns1", "1.1.1.1"])
    run_cmd(["waydroid", "shell", "-u", "0", "--", "setprop", "net.dns2", "8.8.8.8"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "global", "private_dns_mode", "off"])
    run_cmd("iptables -C FORWARD -i waydroid0 -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -i waydroid0 -j ACCEPT 2>/dev/null || true", shell=True)
    run_cmd("iptables -C FORWARD -o waydroid0 -j ACCEPT 2>/dev/null || iptables -I FORWARD 1 -o waydroid0 -j ACCEPT 2>/dev/null || true", shell=True)
    run_cmd("iptables -t nat -C POSTROUTING -s 192.168.240.0/24 -j MASQUERADE 2>/dev/null || iptables -t nat -A POSTROUTING -s 192.168.240.0/24 -j MASQUERADE 2>/dev/null || true", shell=True)
    run_cmd("iptables -t nat -C PREROUTING -i waydroid0 -p udp --dport 53 -j DNAT --to-destination 1.1.1.1:53 2>/dev/null || iptables -t nat -I PREROUTING 1 -i waydroid0 -p udp --dport 53 -j DNAT --to-destination 1.1.1.1:53 2>/dev/null || true", shell=True)
    run_cmd("iptables -t nat -C PREROUTING -i waydroid0 -p tcp --dport 53 -j DNAT --to-destination 1.1.1.1:53 2>/dev/null || iptables -t nat -I PREROUTING 1 -i waydroid0 -p tcp --dport 53 -j DNAT --to-destination 1.1.1.1:53 2>/dev/null || true", shell=True)
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "global", "device_provisioned", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "secure", "user_setup_complete", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "secure", "lockscreen.disabled", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "global", "stay_on_while_plugged_in", "3"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "system", "screen_off_timeout", "2147483647"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "global", "hide_error_dialogs", "1"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "global", "anr_show_background", "0"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "wm", "dismiss-keyguard"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "input", "keyevent", "KEYCODE_WAKEUP"])

def launch_app():
    logger.info(f"Launching {PACKAGE_NAME}...")
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "wm", "dismiss-keyguard"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "input", "keyevent", "KEYCODE_WAKEUP"])
    run_cmd(["waydroid", "shell", "-u", "2000", "--", "am", "start", "-n", f"{PACKAGE_NAME}/.MainActivity"])
    run_cmd(["waydroid", "app", "launch", PACKAGE_NAME])

def is_app_running():
    rc, out, _ = run_cmd(["waydroid", "shell", "pidof", PACKAGE_NAME])
    if rc == 0 and bool(out.strip()):
        return True
    rc, out, _ = run_cmd(["waydroid", "shell", "dumpsys", "window"])
    return PACKAGE_NAME in out

def main():
    options = load_options()
    
    # Configure display props before Waydroid session if needed
    configure_display(options)

    # Wait for Waydroid to finish booting
    wait_for_waydroid_boot()

    # Configure Android system settings
    provision_android()

    # Install / Update Kiosk-Satellite APK (returns True if a fresh install happened)
    just_installed = ensure_kiosk_satellite_installed(options)

    # Grant permissions only on fresh install/update — not on every boot
    # (reinstalling resets permissions, but if we didn't reinstall we don't need to re-grant)
    if just_installed:
        logger.info("Fresh install detected — granting permissions.")
        grant_permissions()
    else:
        logger.info("App already installed — skipping permission grant to preserve user settings.")

    # Setup remote web admin port forwarding
    setup_port_forwarding(options)

    # Launch app (only if auto_launch_kiosk is enabled)
    auto_launch = options.get("auto_launch_kiosk", True)
    if auto_launch:
        launch_app()
    else:
        logger.info("auto_launch_kiosk is disabled — skipping Kiosk Satellite launch.")

    # Keep alive watchdog loop
    keep_alive = options.get("keep_alive", True)
    if keep_alive and auto_launch:
        logger.info("Watchdog loop started.")
        while True:
            time.sleep(10)
            if not is_app_running():
                logger.info(f"App {PACKAGE_NAME} not running, restarting...")
                launch_app()

if __name__ == "__main__":
    main()

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
import re

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

def run_cmd(cmd, check=False, shell=False, env=None):
    logger.debug(f"Running command: {cmd}")
    try:
        exec_env = os.environ.copy()
        if env:
            exec_env.update(env)
        if isinstance(cmd, list) and not shell:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check, env=exec_env)
        else:
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=check, env=exec_env)
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
        "android.permission.MODIFY_AUDIO_SETTINGS",
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

    # Hidden-but-required appop for microphone capture. Without this entry
    # RECORD_AUDIO can be granted while capture is still silently refused,
    # which presents as "the microphone does not work" with no error anywhere.
    run_cmd(["waydroid", "shell", "appops", "set", PACKAGE_NAME, "RECORD_AUDIO", "allow"])

    # Make VOICE_COMMUNICATION the preferred capture profile. Android routes
    # AndroidMediaRecorder to VOICE_COMMUNICATION by default, which engages the
    # audio stack's voice-processing chain; on this container it can land on a
    # profile with no working source. MUSIC is the plain, unprocessed path.
    run_cmd(["waydroid", "shell", "-u", "0", "--", "settings", "put", "global", "voice_recognition_source", "default"])

    # Disable battery optimization
    run_cmd(["waydroid", "shell", "dumpsys", "deviceidle", "whitelist", f"+{PACKAGE_NAME}"])


def verify_mic_permission():
    """Re-grant microphone access if Android revoked it.

    Android auto-resets permissions for apps it considers unused. Because
    permissions were only ever granted on a fresh install, a single auto-reset
    permanently killed the microphone with nothing in the log to explain it.
    """
    rc, out, _ = run_cmd(["waydroid", "shell", "dumpsys", "package", PACKAGE_NAME])
    if rc != 0 or PACKAGE_NAME not in out:
        return True
    granted = "android.permission.RECORD_AUDIO: granted=true" in out
    if not granted:
        logger.warning("RECORD_AUDIO is no longer granted - re-granting microphone access.")
        grant_permissions()
    return granted


def android_audio_fallback():
    """Last-resort path: drive ALSA directly from inside Android.

    Only triggers when the PulseAudio socket is genuinely not reachable from
    inside the container. It is possible at all because the add-on now
    rbind-mounts /dev/snd and /proc/asound into the LXC container. On a normal
    boot this is a no-op.
    """
    rc, out, _ = run_cmd(["waydroid", "shell", "-u", "0", "--", "sh", "-c",
                          "test -S /run/audio/pulse.sock && echo PULSE_OK || echo PULSE_MISSING"])
    if rc == 0 and "PULSE_OK" in out:
        return False

    logger.warning("PulseAudio socket not reachable inside Android - trying ALSA fallback.")

    # Enumerate capture devices from /proc/asound (bind-mounted into the
    # container by run.sh). More reliable than relying on arecord being
    # present in the Android toybox build.
    dev = None
    rc, caps, _ = run_cmd(["waydroid", "shell", "-u", "0", "--", "cat", "/proc/asound/pcm"])
    if rc == 0:
        for line in caps.splitlines():
            if "capture" not in line.lower():
                continue
            m = re.match(r"\s*(\d+)-(\d+):", line)
            if m:
                dev = m.group(2)
                logger.info(f"ALSA fallback capture device: card {m.group(1)}, device {dev}")
                break
    if dev is None:
        logger.error("ALSA fallback found no capture device. Microphone unavailable.")
        return False

    logger.warning(f"Using ALSA fallback inside Android: card 0 device {dev} @ 48000 Hz.")
    settings = [
        ("ro.hardware.audio.primary", "0"),
        ("ro.hardware.audio.card", dev),
        ("ro.hardware.audio.device", "0"),
        ("ro.hardware.audio.in_device", "0"),
        ("ro.hardware.audio.out_device", "0"),
        ("ro.hardware.audio.sample_rate", "48000"),
        ("ro.hardware.audio.out_sample_rate", "48000"),
        ("ro.hardware.audio.in_sample_rate", "48000"),
        ("ro.hardware.audio.out_channels", "2"),
        ("ro.hardware.audio.in_channels", "1"),
        ("ro.hardware.audio.channels", "1"),
    ]
    for prop, val in settings:
        run_cmd(["waydroid", "shell", "-u", "0", "--", "setprop", prop, val])
    return True

def find_hdmi_sink(pulse_env):
    """Return the first HDMI sink name, or None."""
    rc, out, _ = run_cmd(["pactl", "list", "sinks", "short"], env=pulse_env)
    if rc != 0:
        return None
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and ("hdmi" in line.lower() or "vc4" in line.lower()):
            return parts[1]
    return None


def find_capture_source(pulse_env):
    """Pick the microphone source precisely.

    The previous implementation matched on a broad substring list including
    "sound", which could latch onto an unrelated card. Here we simply prefer
    any real capture (non-monitor) source and take the lowest-indexed one,
    which is deterministic and never picks a sink monitor by accident.
    """
    rc, out, _ = run_cmd(["pactl", "list", "sources", "short"], env=pulse_env)
    if rc != 0:
        return None
    real = []
    monitors = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        (monitors if "monitor" in parts[1].lower() else real).append(parts[1])
    if real:
        return real[0]
    if monitors:
        return monitors[0]
    return None


def configure_pulseaudio_routing(options):
    """Route HDMI output + microphone input through the shared HAOS server.

    This function never unloads or reloads PulseAudio modules. The server is
    shared with Home Assistant, so tearing down module-alsa-card also kills
    HA's own live streams.
    """
    pulse_env = {**os.environ, "PULSE_SERVER": "unix:/run/audio/pulse.sock"}
    sock = "/run/audio/pulse.sock"

    # 1. Make sure the host-side symlinks point at the live socket.
    if os.path.exists(sock):
        try:
            os.makedirs("/run/user/0/pulse", exist_ok=True)
            os.makedirs("/run/audio", exist_ok=True)
            for link in ["/run/audio/native", "/run/user/0/pulse/native"]:
                if not os.path.islink(link) or os.readlink(link) != sock:
                    run_cmd(["ln", "-sf", sock, link])
        except Exception as e:
            logger.debug(f"Host symlink setup notice: {e}")

    # 2. Container side. Waydroid bind-mounts
    #    <PULSE_RUNTIME_PATH>/native -> /run/xdg/pulse/native itself, so this
    #    is normally already in place. Only create it when genuinely missing:
    #    /run/xdg/pulse/native is a live bind mount point, and ln -f against
    #    one fails with EBUSY (the old code clobbered it on every boot).
    run_cmd(["waydroid", "shell", "-u", "0", "--", "sh", "-c",
             "mkdir -p /run/xdg/pulse /run/user/0/pulse; "
             "test -S /run/xdg/pulse/native || ln -sf /run/audio/pulse.sock /run/xdg/pulse/native || true; "
             "test -S /run/user/0/pulse/native || ln -sf /run/audio/pulse.sock /run/user/0/pulse/native || true; "
             "true"])

    # 3. Verify the server is actually reachable before doing anything else.
    rc, _, _ = run_cmd(["pactl", "info"], env=pulse_env)
    if rc != 0:
        logger.warning("PulseAudio server not reachable via pactl yet.")
        return False

    logger.info("Configuring PulseAudio routing (HDMI output & microphone input)...")

    # 4. Reduce per-stream fragmentation so the resampler has slack under load.
    #    Cheap and fully reversible: unlike reloading module-alsa-card it does
    #    not interrupt anything that is already playing.
    run_cmd(["pactl", "set-default-fragments", "4"], env=pulse_env)

    # 5. Default sink -> HDMI.
    hdmi_sink = find_hdmi_sink(pulse_env)
    if hdmi_sink:
        logger.info(f"Setting default audio sink to HDMI: {hdmi_sink}")
        run_cmd(["pactl", "set-default-sink", hdmi_sink], env=pulse_env)
        rc_si, si_out, _ = run_cmd(["pactl", "list", "sink-inputs", "short"], env=pulse_env)
        if rc_si == 0 and si_out.strip():
            for line in si_out.splitlines():
                parts = line.split()
                if parts:
                    run_cmd(["pactl", "move-sink-input", parts[0], hdmi_sink], env=pulse_env)
    else:
        logger.warning("No HDMI sink found on the PulseAudio server.")

    # 6. Default source -> microphone.
    mic_source = find_capture_source(pulse_env)
    if mic_source:
        logger.info(f"Setting default audio source to microphone: {mic_source}")
        run_cmd(["pactl", "set-default-source", mic_source], env=pulse_env)
        rc_so, so_out, _ = run_cmd(["pactl", "list", "source-outputs", "short"], env=pulse_env)
        if rc_so == 0 and so_out.strip():
            for line in so_out.splitlines():
                parts = line.split()
                if parts:
                    run_cmd(["pactl", "move-source-output", parts[0], mic_source], env=pulse_env)
    else:
        logger.warning("No capture source found on the PulseAudio server - microphone will not work.")

    # 7. Volumes.
    try:
        vol = max(0, min(100, int(options.get("audio_volume", 100))))
    except Exception:
        vol = 100
    try:
        mic_vol = max(0, min(100, int(options.get("mic_volume", 70))))
    except Exception:
        mic_vol = 70
    run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"], env=pulse_env)
    # The ReSpeaker array clips at 100%. Backing the capture gain off gives the
    # wake-word/STT pipeline usable headroom instead of a distorted signal.
    run_cmd(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{mic_vol}%"], env=pulse_env)

    try:
        level_15 = int(round((vol / 100.0) * 15))
        for stream in [1, 2, 3, 4, 5]:
            run_cmd(["waydroid", "shell", "-u", "2000", "--", "cmd", "media_session", "volume", "--stream", str(stream), "--set", str(level_15)])
        run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "system", "volume_music_speaker", str(level_15)])
        logger.info(f"Set Android media volume to {vol}% (level {level_15}/15)")
    except Exception as e:
        logger.debug(f"Error setting Android volume: {e}")

    return True

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
    # pidof only. The previous "dumpsys window" fallback dumps the entire
    # window-manager state over LXC+ADB, which is expensive enough to starve
    # the audio threads of CPU on a Raspberry Pi.
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

    # Configure PulseAudio routing (HDMI output & microphone input)
    configure_pulseaudio_routing(options)

    # If the shared PulseAudio socket turned out to be unreachable from inside
    # the container, fall back to talking to ALSA directly.
    android_audio_fallback()

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

    # Keep alive watchdog loop & audio reconnect watchdog
    keep_alive = options.get("keep_alive", True)
    logger.info("Watchdog loop started (app keep-alive and audio monitor).")

    last_sock_ino = None
    last_audio_retry = 0
    last_perm_check = 0
    last_app_check = 0
    try:
        if os.path.exists("/run/audio/pulse.sock"):
            last_sock_ino = os.stat("/run/audio/pulse.sock").st_ino
    except Exception:
        pass

    loop = 0
    while True:
        time.sleep(5)
        loop += 1

        # Cheap, every cycle: did the shared PulseAudio socket get recreated?
        # The supervisor restarts hassio_audio periodically, which replaces the
        # socket inode. PulseAudio clients reconnect on their own, so the correct
        # response is to re-assert routing - NOT to kill Android's audioserver.
        # The old code SIGKILLed audioserver here, producing a guaranteed audio
        # gap (and a dead mic) on every single socket recreation.
        try:
            current_ino = None
            if os.path.exists("/run/audio/pulse.sock"):
                current_ino = os.stat("/run/audio/pulse.sock").st_ino

            if current_ino is not None and current_ino != last_sock_ino:
                logger.info(f"PulseAudio socket recreated ({last_sock_ino} -> {current_ino}); re-asserting routing.")
                last_sock_ino = current_ino
                configure_pulseaudio_routing(options)
                # Give Android's audio HAL a bounded number of chances to
                # reconnect, then escalate to a real restart instead of an
                # unconditional SIGKILL on every single event.
                last_audio_retry = 0
            elif last_sock_ino is None and current_ino is not None:
                last_sock_ino = current_ino
                configure_pulseaudio_routing(options)
        except Exception as e:
            logger.debug(f"Audio socket check notice: {e}")

        # Android audio health: only if the socket actually changed.
        if last_audio_retry and time.time() - last_audio_retry > 60:
            last_audio_retry = 0
            logger.warning("Android audio services not responding after a PulseAudio reconnect; restarting them.")
            # pidof, not pkill -f: the pattern form can match this command's own
            # command line inside the container shell.
            for proc in ("audioserver", "android.hardware.audio.service"):
                rc, pid, _ = run_cmd(["waydroid", "shell", "-u", "0", "--", "pidof", proc])
                for p in pid.split():
                    run_cmd(["waydroid", "shell", "-u", "0", "--", "kill", "-9", p])

        # Microphone permission watchdog (every ~10 min). Cheap enough and it
        # prevents a silent, permanent microphone failure.
        if time.time() - last_perm_check > 600:
            last_perm_check = time.time()
            try:
                verify_mic_permission()
            except Exception as e:
                logger.debug(f"Permission check notice: {e}")

        # App keep-alive. Uses pidof only (the old code fell back to
        # "dumpsys window", which is very expensive over LXC+ADB and starved
        # the audio threads of CPU on an already-loaded device).
        if keep_alive and auto_launch and time.time() - last_app_check > 15:
            last_app_check = time.time()
            if not is_app_running():
                logger.info(f"App {PACKAGE_NAME} not running, restarting...")
                launch_app()

if __name__ == "__main__":
    main()

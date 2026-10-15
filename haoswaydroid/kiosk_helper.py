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
    
    # Grant appops for alert window and microphone capture
    run_cmd(["waydroid", "shell", "appops", "set", PACKAGE_NAME, "SYSTEM_ALERT_WINDOW", "allow"])
    run_cmd(["waydroid", "shell", "appops", "set", PACKAGE_NAME, "RECORD_AUDIO", "allow"])

    # Disable battery optimization
    run_cmd(["waydroid", "shell", "dumpsys", "deviceidle", "whitelist", f"+{PACKAGE_NAME}"])

def configure_pulseaudio_routing(options):
    """Configure PulseAudio routing (HDMI output, Seeed mic input), eliminate VC4 crackle, and set volumes."""
    pulse_env = {**os.environ, "PULSE_SERVER": "unix:/run/audio/pulse.sock"}

    # 1. Ensure host and Android symlinks point to live /run/audio/pulse.sock
    if os.path.exists("/run/audio/pulse.sock"):
        try:
            os.makedirs("/run/user/0/pulse", exist_ok=True)
            for link_target in ["/run/user/0/pulse/native", "/run/audio/native"]:
                if not os.path.islink(link_target) or os.readlink(link_target) != "/run/audio/pulse.sock":
                    run_cmd(["ln", "-sf", "/run/audio/pulse.sock", link_target])
        except Exception as e:
            logger.debug(f"Host symlink setup notice: {e}")

        # Ensure container has symlinks
        run_cmd(["waydroid", "shell", "-u", "0", "--", "sh", "-c",
                 "mkdir -p /run/xdg/pulse /run/user/0/pulse && "
                 "ln -sf /run/audio/pulse.sock /run/xdg/pulse/native 2>/dev/null && "
                 "ln -sf /run/audio/pulse.sock /run/user/0/pulse/native 2>/dev/null || true"])

    # Test pactl connectivity
    rc, _, _ = run_cmd(["pactl", "info"], env=pulse_env)
    if rc != 0:
        logger.warning("PulseAudio server not reachable via pactl yet.")
        return False

    logger.info("Configuring PulseAudio routing (HDMI output & Seeed microphone input)...")

    # 2. Structural parse of cards from pactl list cards
    cards = []
    current = {}
    rc_c, cards_out, _ = run_cmd(["pactl", "list", "cards"], env=pulse_env)
    if rc_c == 0:
        for line in cards_out.splitlines():
            if line.startswith("Card #"):
                if current:
                    cards.append(current)
                current = {"id": line.split()[1]}
            elif "Owner Module:" in line:
                current["owner_module"] = line.split(":")[1].strip()
            elif "alsa.card =" in line:
                current["alsa_card"] = line.split("=")[1].strip().strip('"')
            elif "alsa.card_name =" in line:
                current["alsa_name"] = line.split("=")[1].strip().strip('"')
            elif "alsa.driver_name =" in line:
                current["alsa_driver"] = line.split("=")[1].strip().strip('"')
        if current:
            cards.append(current)

    rc_m, mods_out, _ = run_cmd(["pactl", "list", "modules"], env=pulse_env)

    # 3. Fix VC4 HDMI crackle / 'crrg' and robotic sound by reloading module-alsa-card with tsched=no and tuned buffer fragments
    for c in cards:
        cname = (c.get("alsa_name") or "").lower()
        cdrv = (c.get("alsa_driver") or "").lower()
        if "vc4" in cname or "hdmi" in cname or "vc4" in cdrv:
            mod_id = c.get("owner_module")
            alsa_card = c.get("alsa_card") or "0"
            mod_block = ""
            if rc_m == 0 and mod_id:
                for block in mods_out.split("Module #"):
                    if block.strip().startswith(mod_id):
                        mod_block = block.lower()
                        break
            needs_reload = ("tsched=no" not in mod_block and "tsched=0" not in mod_block) or ("fragments=8" not in mod_block)
            if needs_reload and mod_id:
                logger.info(f"VC4 HDMI (card {alsa_card}, module #{mod_id}) needs buffer tuning; reloading with tsched=no fragments=8 fragment_size=8192 rate=48000...")
                run_cmd(["pactl", "unload-module", mod_id], env=pulse_env)
                time.sleep(0.5)
                run_cmd(["pactl", "load-module", "module-alsa-card", f"device_id={alsa_card}", "tsched=no", "fragments=8", "fragment_size=8192", "rate=48000"], env=pulse_env)
            break

    # 4. Tune or load Seeed / ReSpeaker card with low-latency buffer (rate=48000 tsched_buffer_size=16384)
    seeed_found = False
    for c in cards:
        cname = (c.get("alsa_name") or "").lower()
        cdrv = (c.get("alsa_driver") or "").lower()
        if any(k in cname for k in ["seeed", "respeaker", "voice", "sound"]) or "simple_card" in cdrv:
            seeed_found = True
            mod_id = c.get("owner_module")
            alsa_card = c.get("alsa_card") or "2"
            mod_block = ""
            if rc_m == 0 and mod_id:
                for block in mods_out.split("Module #"):
                    if block.strip().startswith(mod_id):
                        mod_block = block.lower()
                        break
            if "tsched_buffer_size" not in mod_block and mod_id:
                logger.info(f"ReSpeaker card (card {alsa_card}, module #{mod_id}) needs low-latency buffer; reloading with rate=48000 tsched_buffer_size=16384...")
                run_cmd(["pactl", "unload-module", mod_id], env=pulse_env)
                time.sleep(0.5)
                run_cmd(["pactl", "load-module", "module-alsa-card", f"device_id={alsa_card}", "rate=48000", "tsched_buffer_size=16384"], env=pulse_env)
            break

    if not seeed_found:
        try:
            if os.path.exists("/proc/asound/cards"):
                with open("/proc/asound/cards", "r") as f:
                    for line in f:
                        if any(k in line.lower() for k in ["seeed", "respeaker", "voice"]):
                            parts = line.split()
                            if parts and parts[0].isdigit():
                                c_idx = parts[0]
                                logger.info(f"Loading ReSpeaker card (ALSA card {c_idx}) into PulseAudio with rate=48000 tsched_buffer_size=16384...")
                                run_cmd(["pactl", "load-module", "module-alsa-card", f"device_id={c_idx}", "rate=48000", "tsched_buffer_size=16384"], env=pulse_env)
                                break
        except Exception as e:
            logger.debug(f"Notice inspecting /proc/asound/cards: {e}")

    # 5. Determine preferred sink and source from options and Home Assistant Supervisor API
    sink_pref = options.get("audio_output_device", "auto")
    source_pref = options.get("audio_input_device", "auto")

    ha_sink = ""
    ha_source = ""
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if token:
        try:
            req = urllib.request.Request("http://supervisor/addons/self/info", headers={"Authorization": f"Bearer {token}"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode())
                ha_sink = data.get("data", {}).get("audio_output") or ""
                ha_source = data.get("data", {}).get("audio_input") or ""
        except Exception:
            pass

    rc_s, sinks_out, _ = run_cmd(["pactl", "list", "sinks", "short"], env=pulse_env)
    all_sinks = [line.split()[1] for line in sinks_out.splitlines() if len(line.split()) >= 2] if rc_s == 0 else []

    target_sink = None
    if sink_pref == "hdmi":
        target_sink = next((s for s in all_sinks if "hdmi" in s.lower() or "vc4" in s.lower()), None)
    elif sink_pref == "respeaker":
        target_sink = next((s for s in all_sinks if any(k in s.lower() for k in ["seeed", "voice", "respeaker", "sound", ".2."])), None)
    elif sink_pref == "auto":
        if ha_sink and ha_sink in all_sinks:
            target_sink = ha_sink
        else:
            # Prefer ReSpeaker / Voice card if available, else HDMI
            target_sink = next((s for s in all_sinks if any(k in s.lower() for k in ["seeed", "voice", "respeaker", "sound", ".2."])), None)
            if not target_sink:
                target_sink = next((s for s in all_sinks if "hdmi" in s.lower() or "vc4" in s.lower()), None)

    if target_sink:
        logger.info(f"Setting default audio sink to: {target_sink}")
        run_cmd(["pactl", "set-default-sink", target_sink], env=pulse_env)
        # Move active playback streams to target sink
        rc_si, si_out, _ = run_cmd(["pactl", "list", "sink-inputs", "short"], env=pulse_env)
        if rc_si == 0 and si_out.strip():
            for line in si_out.splitlines():
                parts = line.split()
                if parts:
                    run_cmd(["pactl", "move-sink-input", parts[0], target_sink], env=pulse_env)

    # 6. Set default source (microphone)
    rc_src, sources_out, _ = run_cmd(["pactl", "list", "sources", "short"], env=pulse_env)
    all_sources = [line.split()[1] for line in sources_out.splitlines() if len(line.split()) >= 2 and "monitor" not in line.lower()] if rc_src == 0 else []

    target_source = None
    if source_pref == "respeaker":
        target_source = next((s for s in all_sources if any(k in s.lower() for k in ["seeed", "voice", "respeaker", "sound", ".2."])), None)
    elif source_pref == "default":
        target_source = all_sources[0] if all_sources else None
    elif source_pref == "auto":
        if ha_source and ha_source in all_sources:
            target_source = ha_source
        else:
            target_source = next((s for s in all_sources if any(k in s.lower() for k in ["seeed", "voice", "respeaker", "sound", ".2."])), None)
            if not target_source and all_sources:
                target_source = all_sources[0]

    if target_source:
        logger.info(f"Setting default audio source to microphone: {target_source}")
        run_cmd(["pactl", "set-default-source", target_source], env=pulse_env)
        # Move active recording streams to target source
        rc_so, so_out, _ = run_cmd(["pactl", "list", "source-outputs", "short"], env=pulse_env)
        if rc_so == 0 and so_out.strip():
            for line in so_out.splitlines():
                parts = line.split()
                if parts:
                    run_cmd(["pactl", "move-source-output", parts[0], target_source], env=pulse_env)

    # 5. Apply volume setting to PulseAudio and Android
    vol = options.get("audio_volume", 100)
    try:
        run_cmd(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{vol}%"], env=pulse_env)
        run_cmd(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", "100%"], env=pulse_env)
    except Exception as e:
        logger.debug(f"Error setting pactl volume: {e}")

    try:
        level_15 = int(round((max(0, min(100, int(vol))) / 100.0) * 15))
        for stream in [1, 2, 3, 4, 5]:
            run_cmd(["waydroid", "shell", "-u", "2000", "--", "cmd", "media_session", "volume", "--stream", str(stream), "--set", str(level_15)])
        run_cmd(["waydroid", "shell", "-u", "2000", "--", "settings", "put", "system", "volume_music_speaker", str(level_15)])
        logger.info(f"Set Android media volume to {vol}% (level {level_15}/15)")
    except Exception as e:
        logger.debug(f"Error setting Android volume: {e}")

    return True

def _get_waydroid_pid():
    rc, out, _ = run_cmd(["sh", "-c", "lxc-info -P /var/lib/waydroid/lxc -n waydroid -p -H 2>/dev/null || lxc-info -n waydroid -p -H 2>/dev/null"])
    pid = (out or "").strip().split()[0] if (out or "").strip() else ""
    return pid if pid.isdigit() else ""


def _get_waydroid_ips(pid):
    """Return list of IPv4s seen inside the container netns (eth0 etc)."""
    if not pid:
        return []
    rc, out, _ = run_cmd(["nsenter", "-t", pid, "-n", "ip", "-4", "-o", "addr", "show"])
    if rc != 0 or not out:
        return []
    ips = re.findall(r"inet\s+(\d+\.\d+\.\d+\.\d+)", out)
    # Prefer non-loopback, keep loopback last (127.0.0.1 is tried first anyway)
    ordered = [ip for ip in ips if not ip.startswith("127.")]
    if "127.0.0.1" in ips:
        ordered.append("127.0.0.1")
    return ordered


def _test_tcp(host, port, timeout=3, netns_pid=None):
    """True if TCP host:port accepts a connection (optionally inside container netns)."""
    import socket
    if netns_pid:
        # Same filesystem, different netns: re-exec python inside netns via nsenter
        code = (
            "import socket,sys; s=socket.socket(); s.settimeout(%d); "
            "s.connect(('%s',%d)); s.close()" % (timeout, host, int(port))
        )
        rc, _, _ = run_cmd(["nsenter", "-t", str(netns_pid), "-n", "python3", "-c", code])
        return rc == 0
    try:
        s = socket.create_connection((host, int(port)), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def _write_proxy_script(container_port):
    """Create /usr/local/bin/kiosk_proxy_<port>.sh that bridges into Waydroid netns.

    The app may bind 0.0.0.0 (reachable via 127.0.0.1) or only its eth0 IP
    (e.g. 192.168.240.x). The script probes candidate targets and internal candidate
    ports (such as 6055 and 6053 for ESPHome) so that any host port forwards to
    whichever port the Android app is actually listening on.
    """
    proxy_script = f"/usr/local/bin/kiosk_proxy_{container_port}.sh"
    try:
        with open(proxy_script, "w") as f:
            f.write(
                "#!/bin/bash\n"
                f"PORT={int(container_port)}\n"
                "PID=$(lxc-info -P /var/lib/waydroid/lxc -n waydroid -p -H 2>/dev/null)\n"
                "[ -n \"$PID\" ] || PID=$(lxc-info -n waydroid -p -H 2>/dev/null)\n"
                "[ -n \"$PID\" ] || exit 1\n"
                "# Candidate targets inside the container netns\n"
                "CANDS=\"127.0.0.1\"\n"
                "ETHIP=$(nsenter -t \"$PID\" -n ip -4 -o addr show eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | head -n1)\n"
                "[ -n \"$ETHIP\" ] && CANDS=\"$CANDS $ETHIP\"\n"
                "ALLIPS=$(nsenter -t \"$PID\" -n ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -v '^127\\.' | head -n5)\n"
                "[ -n \"$ALLIPS\" ] && CANDS=\"$CANDS $ALLIPS\"\n"
                "# Candidate internal ports: requested port first, then common Kiosk Satellite app ports (6055, 6053)\n"
                "CAND_PORTS=\"$PORT\"\n"
                "if [ \"$PORT\" != \"6055\" ] && [ \"$PORT\" != \"6053\" ] && [ \"$PORT\" -gt 6000 ] && [ \"$PORT\" -lt 6100 ]; then\n"
                "  CAND_PORTS=\"$PORT 6055 6053\"\n"
                "fi\n"
                "for P in $CAND_PORTS; do\n"
                "  for H in $CANDS; do\n"
                "    if nsenter -t \"$PID\" -n python3 -c \"import socket;s=socket.socket();s.settimeout(1);s.connect(('$H',$P));s.close()\" 2>/dev/null; then\n"
                "      exec nsenter -t \"$PID\" -n socat - TCP:$H:$P\n"
                "    fi\n"
                "  done\n"
                "done\n"
                "# Fallback: loopback (lets socat surface the real error in logs)\n"
                "exec nsenter -t \"$PID\" -n socat - TCP:127.0.0.1:$PORT\n"
            )
        os.chmod(proxy_script, 0o755)
        return proxy_script
    except Exception as e:
        logger.error(f"Failed to create kiosk_proxy script for port {container_port}: {e}")
        return None


def _is_port_listening(port):
    """Check if something is already listening on TCP <port> on this host."""
    rc, out, _ = run_cmd(["sh", "-c", f"(ss -ltn 2>/dev/null || netstat -ltn 2>/dev/null) | grep -q ':{port} '"])
    return rc == 0


def _start_port_forward(host_port, container_port=None):
    """Start socat TCP-LISTEN:<host_port> -> Waydroid <container_port>, verify it stuck."""
    if not host_port or int(host_port) <= 0:
        return False
    host_port = int(host_port)
    container_port = int(container_port) if container_port else host_port
    proxy_script = _write_proxy_script(container_port)
    if not proxy_script:
        return False
    # Kill only our own previous forwarder for this port
    run_cmd(f"pkill -f 'socat.*TCP-LISTEN:{host_port}'", shell=True)
    time.sleep(0.5)
    try:
        subprocess.Popen(
            ["socat", f"TCP-LISTEN:{host_port},bind=0.0.0.0,fork,reuseaddr", f"EXEC:{proxy_script}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        time.sleep(1.0)
        # Verify that OUR socat process is alive
        rc, out, _ = run_cmd(["sh", "-c", f"ps aux 2>/dev/null | grep -v grep | grep 'socat.*TCP-LISTEN:{host_port}'"])
        if rc == 0 and out.strip():
            logger.info(f"Port forward started: 0.0.0.0:{host_port} -> Waydroid :{container_port}")
            return True
        # If socat did not stay up, another process owns the port or binary missing
        rc, ss_out, _ = run_cmd(["sh", "-c", f"ss -ltnp 2>/dev/null | grep ':{host_port} ' || true"])
        if ss_out.strip():
            logger.error(f"Port forward for {host_port} FAILED: port is already in use on host ({ss_out.strip()}). Please choose another port (e.g. 6056) in add-on options.")
        else:
            logger.error(f"Port forward for {host_port} failed to start socat.")
        return False
    except Exception as e:
        logger.error(f"Failed to start port forward for {host_port}: {e}")
        return False


def diagnose_port_forwarding(options):
    """Log everything needed to debug 'HA cannot add ESPHome': listeners, Waydroid IP, inner probes."""
    try:
        for key in ("remote_admin_port", "esphome_api_port"):
            try:
                port = int(options.get(key, 0) or 0)
            except (TypeError, ValueError):
                continue
            if port <= 0:
                continue
            listening = _is_port_listening(port)
            rc, ss_out, _ = run_cmd(["sh", "-c", f"ss -ltnp 2>/dev/null | grep ':{port} ' || ss -ltn 2>/dev/null | grep ':{port} ' || echo 'not-listening'"])
            logger.info(f"[diag] host TCP {port} ({key}): listening={listening} :: {ss_out[:500]}")
        pid = _get_waydroid_pid()
        logger.info(f"[diag] waydroid container PID: {pid or 'NOT-FOUND'}")
        if pid:
            rc, ip_out, _ = run_cmd(["nsenter", "-t", pid, "-n", "ip", "-4", "-o", "addr", "show"])
            logger.info(f"[diag] container addrs: {(ip_out or '').replace(chr(10), ' ')[:500]}")
            for key in ("remote_admin_port", "esphome_api_port"):
                try:
                    cport = int(options.get(key, 0) or 0)
                except (TypeError, ValueError):
                    continue
                if cport <= 0:
                    continue
                for target in ["127.0.0.1"] + _get_waydroid_ips(pid):
                    ok = _test_tcp(target, cport, timeout=2, netns_pid=pid)
                    logger.info(f"[diag] container {target}:{cport} ({key}) reachable={ok}")
                    if ok:
                        break
            # What does Android itself think is listening?
            rc, ls_out, _ = run_cmd(["waydroid", "shell", "netstat -ltn 2>/dev/null || ss -ltn 2>/dev/null || cat /proc/net/tcp 2>/dev/null"])
            if ls_out:
                hits = [l for l in ls_out.splitlines() if "2324" in l or "6053" in l]
                logger.info(f"[diag] android listeners (2324/6053): {' | '.join(hits)[:800] or ls_out[:800]}")
        # Host-side self-test: can HA Core reach us via HAOS IP / localhost?
        for key in ("remote_admin_port", "esphome_api_port"):
            try:
                port = int(options.get(key, 0) or 0)
            except (TypeError, ValueError):
                continue
            if port <= 0:
                continue
            ok = _test_tcp("127.0.0.1", port, timeout=2)
            logger.info(f"[diag] host 127.0.0.1:{port} ({key}) self-connect={ok}")
        # mDNS advertisement status (auto-discovery)
        try:
            adv = bool(options.get("esphome_advertise", True))
            rc, pub_out, _ = run_cmd(["sh", "-c", "ps aux 2>/dev/null | grep '[a]vahi-publish-service.*_esphomelib' || echo 'mdns-off'"])
            logger.info(f"[diag] mdns advertise={adv} name='{_mdns_instance_name(options)}' :: {(pub_out or '')[:300]}")
        except Exception:
            pass
    except Exception as e:
        logger.debug(f"[diag] diagnose error: {e}")


def setup_port_forwarding(options):
    # Remote admin web UI (default 2324, configurable)
    remote_port = options.get("remote_admin_port", 2324)
    try:
        remote_port = int(remote_port)
    except (TypeError, ValueError):
        remote_port = 2324
    if remote_port and remote_port > 0:
        logger.info(f"Setting up port forward for Kiosk Satellite web admin on port {remote_port}")
        _start_port_forward(remote_port)
    else:
        logger.info("Remote admin port forwarding disabled (remote_admin_port=0).")

    # ESPHome native API (default 6053, configurable).
    # The Kiosk Satellite app serves its ESPHome API *inside* the Waydroid
    # network namespace (192.168.240.x). Without this forward, Home Assistant
    # (which sees only the HAOS host IP, thanks to host_network: true) gets
    # "connection refused" when adding the ESPHome device, and mDNS discovery
    # never crosses the container NAT. Forwarding host TCP 6053 -> Waydroid
    # 127.0.0.1:6053 makes manual setup work:
    #   Settings -> Devices & services -> Add ESPHome -> host=<HAOS-IP>, port=6053
    #   + paste the encryption key shown in the kiosk Settings -> ESPHome page.
    # NOTE: the value here MUST match the "API port" configured inside the
    # Kiosk Satellite app (Settings -> ESPHome -> API port). Set to 0 to disable.
    esphome_port = options.get("esphome_api_port", 6053)
    try:
        esphome_port = int(esphome_port)
    except (TypeError, ValueError):
        esphome_port = 6053
    if esphome_port and esphome_port > 0:
        logger.info(f"Setting up port forward for Kiosk Satellite ESPHome API on port {esphome_port}")
        _start_port_forward(esphome_port)
    else:
        logger.info("ESPHome API port forwarding disabled (esphome_api_port=0).")


def ensure_port_forwarding(options):
    """Watchdog: restart any missing socat forwarder (remote admin + ESPHome)."""
    for key in ("remote_admin_port", "esphome_api_port"):
        try:
            port = int(options.get(key, 0) or 0)
        except (TypeError, ValueError):
            continue
        if port <= 0:
            continue
        if not _is_port_listening(port):
            logger.warning(f"Port forward for {port} ({key}) is down — restarting...")
            _start_port_forward(port)

_zeroconf_state = {
    "zc": None,
    "info": None,
    "port": 0,
    "name": "",
    "mac": "",
}


def _mdns_instance_name(options):
    """mDNS service instance name. Defaults to 'waydroid' (matching Kiosk Satellite default)."""
    raw = str(options.get("esphome_node_name", "") or "").strip()
    if not raw:
        raw = "waydroid"
    # Avahi/mDNS instance names: keep printable, max 63 chars
    raw = re.sub(r"\s+", " ", raw).strip()[:63] or "waydroid"
    return raw


def get_waydroid_mac():
    """Retrieve the unique MAC address of the Waydroid Android container."""
    pid = _get_waydroid_pid()
    if pid:
        # Extract eth0 link ether inside container netns
        rc, out, _ = run_cmd(["sh", "-c", f"nsenter -t {pid} -n ip -o link show eth0 2>/dev/null | awk '{{for(i=1;i<=NF;i++) if($i==\"link/ether\") print $(i+1)}}'"])
        if rc == 0 and out.strip() and ":" in out:
            return out.strip().replace(":", "").lower()
    # Check if avahi has already discovered the internal advertisement with mac=
    rc, out, _ = run_cmd(["sh", "-c", "avahi-browse -r -t _esphomelib._tcp 2>/dev/null | grep 'mac=' | head -n1"])
    if rc == 0 and out:
        m = re.search(r'mac=([0-9a-fA-F:]+)', out)
        if m:
            return m.group(1).replace(":", "").lower()
    # Fallback to deterministic pseudo-MAC from machine-id
    try:
        if os.path.exists("/etc/machine-id"):
            with open("/etc/machine-id") as f:
                mid = f.read().strip()[:8]
                return f"00163e{mid[:6]}".lower()
    except Exception:
        pass
    return "00163ef9d303"


def get_host_lan_ips():
    """Get host LAN IP addresses (excluding internal container NATs)."""
    ips = []
    try:
        rc, out, _ = run_cmd(["sh", "-c", "ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\") print $(i+1)}'"])
        if rc == 0 and out.strip():
            ips.append(out.strip())
    except Exception:
        pass
    try:
        rc, out, _ = run_cmd(["sh", "-c", "ip -4 -o addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1"])
        if rc == 0 and out.strip():
            for line in out.strip().splitlines():
                ip = line.strip()
                if ip and not ip.startswith("127.") and not ip.startswith("172.17.") and not ip.startswith("172.30.") and not ip.startswith("192.168.240."):
                    if ip not in ips:
                        ips.append(ip)
    except Exception:
        pass
    return ips or ["127.0.0.1"]


def ensure_avahi_daemon():
    """Start avahi-daemon if missing (needed for avahi-publish-service). Returns True if running."""
    rc, _, _ = run_cmd(["sh", "-c", "command -v avahi-daemon >/dev/null 2>&1"])
    if rc != 0:
        return False
    rc, _, _ = run_cmd(["avahi-daemon", "--check"])
    if rc == 0:
        return True
    run_cmd(["mkdir", "-p", "/run/avahi-daemon"])
    run_cmd(["rm", "-f", "/run/avahi-daemon/pid"])
    rc, out, err = run_cmd(["avahi-daemon", "-D"])
    time.sleep(1.0)
    rc2, _, _ = run_cmd(["avahi-daemon", "--check"])
    if rc2 == 0:
        logger.info("avahi-daemon started for ESPHome mDNS advertisement.")
        return True
    return False


def ensure_mdns_advertising(options):
    """Publish _esphomelib._tcp on host network so Home Assistant discovers the kiosk.

    Includes the strictly required 'mac' property (Home Assistant aborts discovery
    with 'mdns_missing_mac' if absent). Uses python-zeroconf when available for
    clean host socket binding without Avahi daemon conflicts, falling back to
    avahi-publish-service.
    """
    global _zeroconf_state
    try:
        advertise = bool(options.get("esphome_advertise", True))
        port = int(options.get("esphome_api_port", 0) or 0)
    except (TypeError, ValueError):
        return

    name = _mdns_instance_name(options)

    if not advertise or port <= 0:
        if _zeroconf_state["zc"]:
            try:
                _zeroconf_state["zc"].unregister_all_services()
                _zeroconf_state["zc"].close()
            except Exception:
                pass
            _zeroconf_state["zc"] = None
        run_cmd("pkill -f 'avahi-publish-service.*_esphomelib._tcp' 2>/dev/null", shell=True)
        return

    mac = get_waydroid_mac()

    # If already advertising with this exact configuration, nothing to do
    if (_zeroconf_state["zc"] and _zeroconf_state["port"] == port and 
        _zeroconf_state["name"] == name and _zeroconf_state["mac"] == mac):
        return

    # Clean up previous advertisement if configuration changed
    if _zeroconf_state["zc"]:
        try:
            _zeroconf_state["zc"].unregister_all_services()
            _zeroconf_state["zc"].close()
        except Exception:
            pass
        _zeroconf_state["zc"] = None
    run_cmd("pkill -f 'avahi-publish-service.*_esphomelib._tcp' 2>/dev/null", shell=True)

    host_ips = get_host_lan_ips()
    friendly_name = name.capitalize()

    # Try native Python zeroconf first
    try:
        import socket
        from zeroconf import Zeroconf, ServiceInfo

        desc = {
            "mac": mac,
            "friendly_name": friendly_name,
            "version": "2026.10.0",
            "platform": "ESP32",
            "board": "kiosk-satellite",
            "network": "wifi",
            "project_name": "kiosk_satellite.bluetooth_proxy",
            "project_version": "2026.10.26",
        }

        service_info = ServiceInfo(
            "_esphomelib._tcp.local.",
            f"{name}._esphomelib._tcp.local.",
            addresses=[socket.inet_aton(ip) for ip in host_ips if "." in ip],
            port=port,
            properties=desc,
            server=f"{name}.local.",
        )

        zc = Zeroconf(interfaces=host_ips)
        zc.register_service(service_info)
        _zeroconf_state["zc"] = zc
        _zeroconf_state["info"] = service_info
        _zeroconf_state["port"] = port
        _zeroconf_state["name"] = name
        _zeroconf_state["mac"] = mac
        logger.info(f"Advertising ESPHome via Python Zeroconf as '{name}' (_esphomelib._tcp:{port}, mac={mac}, ips={host_ips}).")
        return
    except Exception as e:
        logger.debug(f"Python Zeroconf registration skipped ({e}), falling back to Avahi...")

    # Fallback: avahi-publish-service with full TXT records including mac
    if not ensure_avahi_daemon():
        return
    try:
        subprocess.Popen(
            ["avahi-publish-service", name, "_esphomelib._tcp", str(port),
             f"mac={mac}", f"friendly_name={friendly_name}",
             "version=2026.10.0", "platform=ESP32", "board=kiosk-satellite", "network=wifi"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info(f"Advertising ESPHome via Avahi as '{name}' (_esphomelib._tcp:{port}, mac={mac}).")
    except Exception as e:
        logger.warning(f"Could not start Avahi mDNS advertisement: {e}")

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

    # Configure PulseAudio routing (HDMI output, Seeed mic input), eliminate crackle & set volume
    configure_pulseaudio_routing(options)

    # Install / Update Kiosk-Satellite APK (returns True if a fresh install happened)
    just_installed = ensure_kiosk_satellite_installed(options)

    # Grant permissions only on fresh install/update — not on every boot
    # (reinstalling resets permissions, but if we didn't reinstall we don't need to re-grant)
    if just_installed:
        logger.info("Fresh install detected — granting permissions.")
        grant_permissions()
    else:
        logger.info("App already installed — skipping permission grant to preserve user settings.")

    # Setup remote web admin + ESPHome API port forwarding
    setup_port_forwarding(options)
    # Advertise _esphomelib._tcp from the host so HA shows Discovered
    try:
        ensure_mdns_advertising(options)
    except Exception as e:
        logger.debug(f"mDNS advertise notice: {e}")
    # One-shot diagnostics so the add-on log tells us exactly why HA can't connect
    try:
        diagnose_port_forwarding(options)
    except Exception as e:
        logger.debug(f"Initial diagnose notice: {e}")

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
    try:
        if os.path.exists("/run/audio/pulse.sock"):
            last_sock_ino = os.stat("/run/audio/pulse.sock").st_ino
    except Exception:
        pass

    loop_count = 0
    while True:
        time.sleep(10)
        loop_count += 1

        # Supervise socat forwarders (remote admin + ESPHome API) — restart if dead
        try:
            ensure_port_forwarding(options)
            ensure_mdns_advertising(options)
        except Exception as e:
            logger.debug(f"Port forward watchdog notice: {e}")

        # Full diagnostics every ~60s (every 6th loop) — shows in add-on log
        if loop_count % 6 == 0:
            try:
                diagnose_port_forwarding(options)
            except Exception as e:
                logger.debug(f"Periodic diagnose notice: {e}")

        # Check PulseAudio socket inode for hassio_audio restart
        try:
            current_ino = None
            if os.path.exists("/run/audio/pulse.sock"):
                current_ino = os.stat("/run/audio/pulse.sock").st_ino

            if current_ino is not None and current_ino != last_sock_ino:
                logger.info(f"PulseAudio socket inode changed ({last_sock_ino} -> {current_ino}) - reconfiguring audio and restarting Android audio services...")
                last_sock_ino = current_ino
                configure_pulseaudio_routing(options)
                # Restart Android audio HAL and audioserver to reconnect cleanly
                run_cmd(["waydroid", "shell", "-u", "0", "--", "sh", "-c",
                         "pkill -9 -f android.hardware.audio.service || true; pkill -9 -f audioserver || true"])
            elif last_sock_ino is None and current_ino is not None:
                last_sock_ino = current_ino
                configure_pulseaudio_routing(options)
        except Exception as e:
            logger.debug(f"Audio watchdog check notice: {e}")

        # Check Kiosk Satellite application state
        if keep_alive and auto_launch:
            if not is_app_running():
                logger.info(f"App {PACKAGE_NAME} not running, restarting...")
                launch_app()

if __name__ == "__main__":
    main()

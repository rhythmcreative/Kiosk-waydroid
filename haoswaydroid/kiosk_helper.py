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

    # 2. Fix VC4 HDMI crackle / 'crrg' and robotic sound by reloading module-alsa-card with tsched=no and tuned buffer fragments
    rc_c, cards_out, _ = run_cmd(["pactl", "list", "cards"], env=pulse_env)
    if rc_c == 0 and ("vc4" in cards_out.lower() or "hdmi" in cards_out.lower()):
        rc_m, mods_out, _ = run_cmd(["pactl", "list", "modules"], env=pulse_env)
        if rc_m == 0:
            modules = mods_out.split("Module #")
            for mod in modules[1:]:
                lines = mod.strip().split("\n")
                mod_id = lines[0].strip()
                mod_text = mod.lower()
                if "module-alsa-card" in mod_text and ("vc4" in mod_text or "hdmi" in mod_text):
                    needs_reload = ("tsched=no" not in mod_text and "tsched=0" not in mod_text) or ("fragments=8" not in mod_text)
                    if needs_reload:
                        logger.info(f"VC4 HDMI module #{mod_id} needs buffer tuning; reloading with tsched=no fragments=8 fragment_size=8192...")
                        m = re.search(r'device_id="([^"]+)"', mod) or re.search(r'card_name="([^"]+)"', mod)
                        dev_id = m.group(1) if m else "vc4-hdmi-0"
                        run_cmd(["pactl", "unload-module", mod_id], env=pulse_env)
                        time.sleep(0.5)
                        run_cmd(["pactl", "load-module", "module-alsa-card", f"device_id={dev_id}", "tsched=no", "fragments=8", "fragment_size=8192"], env=pulse_env)
                        break

    # 3. Set default sink to HDMI
    rc_s, sinks_out, _ = run_cmd(["pactl", "list", "sinks", "short"], env=pulse_env)
    if rc_s == 0:
        hdmi_sinks = [
            line.split()[1] for line in sinks_out.splitlines()
            if len(line.split()) >= 2 and ("hdmi" in line.lower() or "vc4" in line.lower())
        ]
        if hdmi_sinks:
            hdmi_sink = hdmi_sinks[0]
            logger.info(f"Setting default audio sink to HDMI: {hdmi_sink}")
            run_cmd(["pactl", "set-default-sink", hdmi_sink], env=pulse_env)
            # Move active playback streams to HDMI sink
            rc_si, si_out, _ = run_cmd(["pactl", "list", "sink-inputs", "short"], env=pulse_env)
            if rc_si == 0 and si_out.strip():
                for line in si_out.splitlines():
                    parts = line.split()
                    if parts:
                        run_cmd(["pactl", "move-sink-input", parts[0], hdmi_sink], env=pulse_env)

    # 4. Set default source to Seeed ReSpeaker / microphone
    rc_src, sources_out, _ = run_cmd(["pactl", "list", "sources", "short"], env=pulse_env)
    if rc_src == 0:
        mic_sources = [
            line.split()[1] for line in sources_out.splitlines()
            if len(line.split()) >= 2 and any(k in line.lower() for k in ["seeed", "voice", "respeaker", "sound"]) and "monitor" not in line.lower()
        ]
        if mic_sources:
            mic_source = mic_sources[0]
            logger.info(f"Setting default audio source to microphone: {mic_source}")
            run_cmd(["pactl", "set-default-source", mic_source], env=pulse_env)
            # Move active recording streams to Seeed mic
            rc_so, so_out, _ = run_cmd(["pactl", "list", "source-outputs", "short"], env=pulse_env)
            if rc_so == 0 and so_out.strip():
                for line in so_out.splitlines():
                    parts = line.split()
                    if parts:
                        run_cmd(["pactl", "move-source-output", parts[0], mic_source], env=pulse_env)

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
    (e.g. 192.168.240.x). The script probes candidates in order and connects
    to the first one that accepts TCP, so a wrong guess never breaks forwarding.
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
                "for H in $CANDS; do\n"
                "  if nsenter -t \"$PID\" -n python3 -c \"import socket;s=socket.socket();s.settimeout(2);s.connect(('$H',$PORT));s.close()\" 2>/dev/null; then\n"
                "    exec nsenter -t \"$PID\" -n socat - TCP:$H:$PORT\n"
                "  fi\n"
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
        if _is_port_listening(host_port):
            logger.info(f"Port forward started: 0.0.0.0:{host_port} -> Waydroid :{container_port}")
            return True
        # Likely EADDRINUSE or missing binary — log the real cause
        rc, out, err = run_cmd(["sh", "-c", f"(ss -ltnp 2>/dev/null || netstat -ltnp 2>/dev/null); echo ---; ps aux 2>/dev/null | grep -i socat | grep -v grep || true"])
        logger.error(f"Port forward for {host_port} NOT listening after start. netstat/ps:\n{out}\n{err}")
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

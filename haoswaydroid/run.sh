#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting Waydroid Kiosk Satellite Add-on"
echo " Version: ${ADDON_VERSION:-1.0.0}"
echo "=========================================================="

# 1. Setup Persistent Storage
mkdir -p /data/waydroid /data/apk_cache /var/lib/waydroid
if [ ! -L /var/lib/waydroid ] && [ -d /data/waydroid ]; then
    mount --bind /data/waydroid /var/lib/waydroid 2>/dev/null || true
fi

# 2. Setup D-Bus
mkdir -p /run/dbus
rm -f /run/dbus/pid
dbus-daemon --system --fork || true
export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/dbus/system_bus_socket"

# 3. Setup Binder Nodes (BinderFS)
if [ ! -d /dev/binderfs ]; then
    mkdir -p /dev/binderfs
fi

if ! mountpoint -q /dev/binderfs; then
    mount -t binder binder /dev/binderfs 2>/dev/null || true
fi

for node in binder vndbinder hwbinder; do
    if [ -e "/dev/binderfs/$node" ] && [ ! -e "/dev/$node" ]; then
        ln -s "/dev/binderfs/$node" "/dev/$node" 2>/dev/null || true
    fi
done

# 4. Setup Audio & Microphone (PulseAudio)
mkdir -p /root/.config/pulse /run/user/0/pulse
chmod 0700 /run/user/0 /run/user/0/pulse 2>/dev/null || true

if [ -S /run/audio/pulse.sock ]; then
    export PULSE_SERVER="unix:/run/audio/pulse.sock"
    ln -sf /run/audio/pulse.sock /run/user/0/pulse/native 2>/dev/null || true
    echo "Connected to HAOS PulseAudio socket at /run/audio/pulse.sock"
elif [ -n "$PULSE_SERVER" ]; then
    echo "Using PULSE_SERVER=$PULSE_SERVER"
else
    # Start internal PulseAudio daemon if host socket is not mounted
    pulseaudio --start --exit-idle-time=-1 || true
    if [ -S /run/user/0/pulse/native ]; then
        export PULSE_SERVER="unix:/run/user/0/pulse/native"
    fi
fi

# Test audio/mic access
if command -v pactl >/dev/null 2>&1; then
    echo "Audio server status:"
    pactl info 2>/dev/null || echo "PulseAudio daemon active."
fi

# 5. Initialize Waydroid if not already initialized
if [ ! -f /var/lib/waydroid/images/system.img ]; then
    echo "Waydroid system image not found. Initializing Waydroid (VANILLA)..."
    waydroid init -s VANILLA -f || {
        echo "Initial init failed, retrying..."
        waydroid init -s VANILLA
    }
    echo "Waydroid initialized successfully."
fi

# 6. Start Seatd for Wayland DRM/KMS session
mkdir -p /run/seatd
rm -f /run/seatd/seatd.sock
seatd -g video &
SEATD_PID=$!
export LIBSEAT_BACKEND=seatd

# 7. Start Waydroid Container Service
echo "Starting Waydroid container service..."
waydroid container start &
CONTAINER_PID=$!

sleep 3

# 8. Start Waydroid Helper (Download & Install Kiosk Satellite, Grant Mic Permissions, Port Forward 2324)
python3 /kiosk_helper.py &
HELPER_PID=$!

# 9. Start Cage Wayland Compositor running Waydroid Session
export XDG_RUNTIME_DIR=/run/user/0
mkdir -p "$XDG_RUNTIME_DIR"
chmod 0700 "$XDG_RUNTIME_DIR"
export WAYLAND_DISPLAY=wayland-0

echo "Starting Cage Compositor with Waydroid Full UI..."
exec cage -s -- /cage-run.sh

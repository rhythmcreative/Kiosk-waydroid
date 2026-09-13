#!/usr/bin/env bash

echo "=========================================================="
echo " Starting Waydroid Kiosk Satellite Add-on"
echo " Version: ${ADDON_VERSION:-1.0.6}"
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

# 3. Setup / Check Binder Nodes
if [ -e "/dev/binderfs/binder" ]; then
    echo "Found /dev/binderfs/binder."
elif [ -e "/dev/binder" ]; then
    echo "Found /dev/binder."
else
    echo "Notice: Binder nodes not mounted in container. Attempting mount..."
    mkdir -p /dev/binderfs 2>/dev/null || true
    mount -t binder binder /dev/binderfs 2>/dev/null || true
fi

for node in binder vndbinder hwbinder; do
    if [ -e "/dev/binderfs/$node" ] && [ ! -e "/dev/$node" ]; then
        ln -sf "/dev/binderfs/$node" "/dev/$node" 2>/dev/null || true
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
    pulseaudio --start --exit-idle-time=-1 2>/dev/null || true
    if [ -S /run/user/0/pulse/native ]; then
        export PULSE_SERVER="unix:/run/user/0/pulse/native"
    fi
fi

if command -v pactl >/dev/null 2>&1; then
    echo "Audio server status:"
    pactl info 2>/dev/null || echo "PulseAudio daemon active."
fi

# 5. Initialize Waydroid if not already initialized
if [ ! -f /var/lib/waydroid/images/system.img ]; then
    echo "Waydroid system image not found. Initializing Waydroid (VANILLA)..."
    waydroid init -s VANILLA -f || waydroid init -s VANILLA || {
        echo "Warning: waydroid init encountered errors."
    }
    echo "Waydroid initialized."
fi

# 6. Start Seatd for Wayland DRM/KMS session in non-VT mode
rm -f /run/seatd.sock /run/seatd/seatd.sock
mkdir -p /run/seatd

# SEATD_VTBOUND=0 disables virtual terminal switching (required inside containers without physical VTs)
export SEATD_VTBOUND=0
seatd -g video &
SEATD_PID=$!
sleep 1

chmod 0777 /run/seatd.sock 2>/dev/null || true
ln -sf /run/seatd.sock /run/seatd/seatd.sock 2>/dev/null || true
export SEATD_SOCK=/run/seatd.sock
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

# Clean nested display variables
unset WAYLAND_DISPLAY
unset DISPLAY

# Configure hardware DRM/KMS backend
export WLR_BACKENDS=drm,libinput
export WLR_LIBINPUT_NO_DEVICES=1
export WLR_NO_HARDWARE_CURSORS=1
export WLR_RENDERER_ALLOW_SOFTWARE=1
if [ -e /dev/dri/card0 ]; then
    export WLR_DRM_DEVICES=/dev/dri/card0
fi

# Bypass Cage 0.1.4 root check inside container
if [ -f /usr/lib/libcage_root_bypass.so ]; then
    export LD_PRELOAD=/usr/lib/libcage_root_bypass.so
fi

echo "Starting Cage Compositor on native DRM/KMS..."
exec cage -s -- /cage-run.sh

#!/usr/bin/env bash

echo "=========================================================="
echo " Starting Waydroid Kiosk Satellite Add-on"
echo " Version: ${ADDON_VERSION:-1.0.11}"
echo "=========================================================="

# 1. Setup Persistent Storage
mkdir -p /data/waydroid /data/apk_cache /var/lib/waydroid
if [ ! -L /var/lib/waydroid ] && [ -d /data/waydroid ]; then
    mount --bind /data/waydroid /var/lib/waydroid 2>/dev/null || true
fi

# Remount cgroup and /dev as read-write
mount -o remount,rw /sys/fs/cgroup 2>/dev/null || true
mount -o remount,rw /dev 2>/dev/null || true

# Fix LXC post-stop hook and ensure cgroup v2 compatibility
sed -i 's|lxc.hook.post-stop = /dev/null|lxc.hook.post-stop = /bin/true|' /usr/lib/waydroid/data/configs/config_base 2>/dev/null || true
if [ -f /var/lib/waydroid/lxc/waydroid/config ]; then
    sed -i 's|lxc.hook.post-stop = /dev/null|lxc.hook.post-stop = /bin/true|' /var/lib/waydroid/lxc/waydroid/config 2>/dev/null || true
fi

# Overlay Android cgroups.json for cgroup v2 compatibility
mkdir -p /var/lib/waydroid/overlay_rw/system/etc
cat << 'EOF' > /var/lib/waydroid/overlay_rw/system/etc/cgroups.json
{
  "Cgroups": [
    {
      "Controller": "blkio",
      "Path": "/dev/blkio",
      "Mode": "0775",
      "UID": "system",
      "GID": "system",
      "Optional": true
    },
    {
      "Controller": "cpu",
      "Path": "/dev/cpuctl",
      "Mode": "0755",
      "UID": "system",
      "GID": "system",
      "Optional": true
    },
    {
      "Controller": "cpuset",
      "Path": "/dev/cpuset",
      "Mode": "0755",
      "UID": "system",
      "GID": "system",
      "Optional": true
    },
    {
      "Controller": "memory",
      "Path": "/dev/memcg",
      "Mode": "0700",
      "UID": "root",
      "GID": "system",
      "Optional": true
    }
  ],
  "Cgroups2": {
    "Path": "/sys/fs/cgroup",
    "Mode": "0775",
    "UID": "system",
    "GID": "system",
    "Controllers": [
      {
        "Controller": "freezer",
        "Path": "."
      }
    ]
  }
}
EOF

# 2. Setup D-Bus
mkdir -p /run/dbus /etc/dbus-1/system.d
cat << 'EOF' > /etc/dbus-1/system.d/id.waydro.Session.conf
<!DOCTYPE busconfig PUBLIC
 "-//freedesktop//DTD D-BUS Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
    <policy user="root">
        <allow own="id.waydro.Session"/>
    </policy>
    <policy context="default">
        <allow own="id.waydro.Session"/>
        <allow send_destination="id.waydro.Session"/>
        <allow receive_sender="id.waydro.Session"/>
    </policy>
</busconfig>
EOF
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
if [ -f /usr/lib/waydroid/data/scripts/waydroid-net.sh ]; then
    sed -i "s/dnsmasq \$LXC_DHCP_CONFILE_ARG/dnsmasq --port=0 --dhcp-option=6,1.1.1.1,8.8.8.8 \$LXC_DHCP_CONFILE_ARG/" /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i "s|echo 1 > /proc/sys/net/ipv4/ip_forward|echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null \|\| true|" /usr/lib/waydroid/data/scripts/waydroid-net.sh
fi
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

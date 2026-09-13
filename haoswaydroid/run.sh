#!/usr/bin/env bash

echo "=========================================================="
echo " Starting Waydroid Kiosk Satellite Add-on"
echo " Version: ${ADDON_VERSION:-1.0.12}"
echo "=========================================================="

# 1. Setup Persistent Storage
mkdir -p /data/waydroid /data/apk_cache /var/lib/waydroid
if [ ! -L /var/lib/waydroid ] && [ -d /data/waydroid ]; then
    mount --bind /data/waydroid /var/lib/waydroid 2>/dev/null || true
fi

# Remount cgroup, /proc/sys, and /dev as read-write
mount -o remount,rw /sys/fs/cgroup 2>/dev/null || true
mount -o remount,rw /proc/sys 2>/dev/null || true
mount -o remount,rw /dev 2>/dev/null || true

# Ensure unprivileged ports start at 0 for Android DHCP and network services
echo 0 > /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || sysctl -w net.ipv4.ip_unprivileged_port_start=0 2>/dev/null || true

# Fix LXC config for cgroup v2 read-write access and post-stop hook
sed -i 's|lxc.hook.post-stop = /dev/null|lxc.hook.post-stop = /bin/true|' /usr/lib/waydroid/data/configs/config_base 2>/dev/null || true
sed -i 's|cgroup:ro|cgroup:rw|g' /usr/lib/waydroid/data/configs/config_base 2>/dev/null || true
if [ -f /var/lib/waydroid/lxc/waydroid/config_base ]; then
    sed -i 's|lxc.hook.post-stop = /dev/null|lxc.hook.post-stop = /bin/true|' /var/lib/waydroid/lxc/waydroid/config_base 2>/dev/null || true
    sed -i 's|cgroup:ro|cgroup:rw|g' /var/lib/waydroid/lxc/waydroid/config_base 2>/dev/null || true
fi
if [ -f /var/lib/waydroid/lxc/waydroid/config ]; then
    sed -i 's|lxc.hook.post-stop = /dev/null|lxc.hook.post-stop = /bin/true|' /var/lib/waydroid/lxc/waydroid/config 2>/dev/null || true
    sed -i 's|cgroup:ro|cgroup:rw|g' /var/lib/waydroid/lxc/waydroid/config 2>/dev/null || true
fi

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
mkdir -p /etc/waydroid-extra
ln -sf /var/lib/waydroid/images /etc/waydroid-extra/images 2>/dev/null || true

if [ ! -f /var/lib/waydroid/lxc/waydroid/config ]; then
    if [ -f /var/lib/waydroid/images/system.img ]; then
        echo "Initializing Waydroid configuration from local images..."
        waydroid init || true
    else
        echo "Waydroid system image not found. Initializing Waydroid (VANILLA)..."
        waydroid init -s VANILLA || {
            echo "Warning: waydroid init encountered errors."
        }
    fi
    echo "Waydroid initialized."
fi

# 6. Apply Container Compatibility Overlays
if [ -f /var/lib/waydroid/images/system.img ]; then
    echo "Applying Waydroid container compatibility patches..."
    # Clean any legacy /etc directory that masked Android's /etc -> /system/etc symlink
    rm -rf /var/lib/waydroid/overlay_rw/system/etc 2>/dev/null || true

    mkdir -p /var/lib/waydroid/overlay_rw/system/system/etc/init/hw \
             /var/lib/waydroid/overlay_rw/system/system/lib64 \
             /var/lib/waydroid/overlay_rw/system/system/bin \
             /var/lib/waydroid/overlay_rw/vendor/etc/init

    # Install capability & priority shim library and dummy lmkd daemon
    if [ -f /usr/lib/libcap_shim.so ]; then
        cp /usr/lib/libcap_shim.so /var/lib/waydroid/overlay_rw/system/system/lib64/libcap_shim.so
        chmod 755 /var/lib/waydroid/overlay_rw/system/system/lib64/libcap_shim.so
    fi
    if [ -f /usr/bin/dummy_lmkd ]; then
        cp /usr/bin/dummy_lmkd /var/lib/waydroid/overlay_rw/system/system/bin/lmkd
        chmod 755 /var/lib/waydroid/overlay_rw/system/system/bin/lmkd
    fi

    TMP_SYS=/tmp/wd_sys
    mkdir -p "$TMP_SYS"
    mount -o ro /var/lib/waydroid/images/system.img "$TMP_SYS" 2>/dev/null || true

    if [ -d "$TMP_SYS/system" ]; then
        # Patch cgroups.json: ensure missing controllers are marked Optional on cgroup v2
        if [ -f "$TMP_SYS/system/etc/cgroups.json" ]; then
            jq 'walk(if type == "object" and has("Controller") then . + {"Optional": "true"} else . end)' \
                "$TMP_SYS/system/etc/cgroups.json" > /var/lib/waydroid/overlay_rw/system/system/etc/cgroups.json
        fi

        # Patch system rc files: comment out unsupported capabilities, critical flags, rtprio limits, and task_profiles
        for f in "$TMP_SYS"/system/etc/init/*.rc; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            sed -e "s/^    capabilities /    # capabilities /g" \
                -e "s/^    critical/# critical/g" \
                -e "s/^    rlimit rtprio/# rlimit rtprio/g" \
                -e "s/^    task_profiles/# task_profiles/g" \
                "$f" > "/var/lib/waydroid/overlay_rw/system/system/etc/init/$base"
        done

        # Patch bpfloader.rc: disable reboot_on_failure and force bpf.progs_loaded
        if [ -f /var/lib/waydroid/overlay_rw/system/system/etc/init/bpfloader.rc ]; then
            sed -i -e "s/reboot_on_failure/# reboot_on_failure/g" \
                   -e "/exec_start bpfloader/i \    setprop bpf.progs_loaded 1" \
                   /var/lib/waydroid/overlay_rw/system/system/etc/init/bpfloader.rc
        fi

        # Patch logd.rc: preload libcap_shim.so
        if [ -f /var/lib/waydroid/overlay_rw/system/system/etc/init/logd.rc ]; then
            sed -i '/service logd \/system\/bin\/logd/a \    setenv LD_PRELOAD \/system\/lib64\/libcap_shim.so' \
                /var/lib/waydroid/overlay_rw/system/system/etc/init/logd.rc
        fi

        # Patch zygote rc files: preload libcap_shim.so and clamp priority to 0
        for f in "$TMP_SYS"/system/etc/init/hw/init.zygote*.rc; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            sed -e "s/priority -20/priority 0/g" \
                -e "s/critical/# critical/g" \
                -e "s/^    task_profiles/# task_profiles/g" \
                "$f" > "/var/lib/waydroid/overlay_rw/system/system/etc/init/hw/$base"
        done
        if [ -f /var/lib/waydroid/overlay_rw/system/system/etc/init/hw/init.zygote64_32.rc ]; then
            sed -i '/service zygote \/system\/bin\/app_process64/a \    setenv LD_PRELOAD \/system\/lib64\/libcap_shim.so' \
                /var/lib/waydroid/overlay_rw/system/system/etc/init/hw/init.zygote64_32.rc
        fi
    fi

    umount "$TMP_SYS" 2>/dev/null || true
    rmdir "$TMP_SYS" 2>/dev/null || true

    # Patch vendor rc files
    if [ -f /var/lib/waydroid/images/vendor.img ]; then
        TMP_VND=/tmp/wd_vnd
        mkdir -p "$TMP_VND"
        mount -o ro /var/lib/waydroid/images/vendor.img "$TMP_VND" 2>/dev/null || true
        for f in "$TMP_VND"/etc/init/*.rc; do
            [ -f "$f" ] || continue
            base=$(basename "$f")
            sed -e "s/^    capabilities /    # capabilities /g" \
                -e "s/^    critical/# critical/g" \
                -e "s/^    rlimit rtprio/# rlimit rtprio/g" \
                -e "s/^    task_profiles/# task_profiles/g" \
                "$f" > "/var/lib/waydroid/overlay_rw/vendor/etc/init/$base"
        done
        umount "$TMP_VND" 2>/dev/null || true
        rmdir "$TMP_VND" 2>/dev/null || true
    fi
fi

# 7. Configure Input Devices & Host Udev for Cage / Libinput
echo "Configuring input devices and udev for touchscreen/mouse/keyboard..."
chmod -R a+rw /dev/input 2>/dev/null || true
chmod 0666 /dev/uinput 2>/dev/null || true

# Initialize udev if host udev database not mounted
if [ ! -d /run/udev/data ]; then
    if [ -x /usr/lib/systemd/systemd-udevd ]; then
        echo "Starting systemd-udevd..."
        /usr/lib/systemd/systemd-udevd --daemon || true
        udevadm trigger || true
        udevadm settle --timeout=5 || true
    fi
fi

# 8. Start Seatd for Wayland DRM/KMS session in non-VT mode
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

# 9. Start Waydroid Container Service
echo "Starting Waydroid container service..."
if [ -f /usr/lib/waydroid/data/scripts/waydroid-net.sh ]; then
    sed -i "s/dnsmasq \$LXC_DHCP_CONFILE_ARG/dnsmasq --port=0 --dhcp-option=6,1.1.1.1,8.8.8.8 \$LXC_DHCP_CONFILE_ARG/" /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i "s|echo 1 > /proc/sys/net/ipv4/ip_forward|echo 1 > /proc/sys/net/ipv4/ip_forward 2>/dev/null \|\| true|" /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i 's/LXC_USE_NFT="false"/LXC_USE_NFT="true"/' /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i 's/IPTABLES_BIN=".*"/IPTABLES_BIN="\/usr\/sbin\/iptables-nft"/' /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i 's/IP6TABLES_BIN=".*"/IP6TABLES_BIN="\/usr\/sbin\/ip6tables-nft"/' /usr/lib/waydroid/data/scripts/waydroid-net.sh
    sed -i 's/exit 1/exit 0/g' /usr/lib/waydroid/data/scripts/waydroid-net.sh
fi

# Ensure device permissions for Android non-root processes (surfaceflinger, graphics, input, binder)
chmod 666 /dev/dri/* 2>/dev/null || true
chmod 666 /dev/binder* /dev/binderfs/* 2>/dev/null || true
chmod 666 /dev/uinput /dev/input/* 2>/dev/null || true

# Pre-configure Waydroid hardware acceleration properties in waydroid.cfg
echo "Configuring Waydroid hardware acceleration properties..."
waydroid prop set ro.hardware.gralloc gbm 2>/dev/null || true
waydroid prop set ro.hardware.egl mesa 2>/dev/null || true
waydroid prop set debug.stagefright.ccodec 0 2>/dev/null || true
waydroid prop set persist.waydroid.fake_touch true 2>/dev/null || true

waydroid container start &
CONTAINER_PID=$!

sleep 3

# 9. Start Waydroid Helper (Download & Install Kiosk Satellite, Grant Mic Permissions, Port Forward 2324)
python3 /kiosk_helper.py &
HELPER_PID=$!

# 10. Start Cage Wayland Compositor running Waydroid Session
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
export WLR_RENDERER=gles2
unset WLR_RENDERER_ALLOW_SOFTWARE

# Auto-detect KMS scanout card (the card with connected outputs or connectors, e.g. card1 on RPi5)
KMS_CARD=""
for c in /sys/class/drm/card[0-9]*; do
    if ls "$c"/card*-* >/dev/null 2>&1; then
        card_name=$(basename "$c")
        KMS_CARD="/dev/dri/$card_name"
        break
    fi
done

if [ -n "$KMS_CARD" ]; then
    export WLR_DRM_DEVICES="$KMS_CARD"
    echo "Configured Cage KMS display output on $KMS_CARD"
fi

if [ -e /dev/dri/renderD128 ]; then
    export WLR_RENDER_DRM_DEVICE=/dev/dri/renderD128
    echo "Configured Cage 3D render node on /dev/dri/renderD128"
fi

# Bypass Cage 0.1.4 root check inside container
if [ -f /usr/lib/libcage_root_bypass.so ]; then
    export LD_PRELOAD=/usr/lib/libcage_root_bypass.so
fi

echo "Starting Cage Compositor on native DRM/KMS..."
exec cage -s -- /cage-run.sh

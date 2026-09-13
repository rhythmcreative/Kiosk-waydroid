#!/bin/sh
echo "Cage session initialized with WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"

# Ensure DBUS session bus is available for Waydroid session manager
if [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    if [ -S /run/dbus/system_bus_socket ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=/run/dbus/system_bus_socket"
    fi
fi

# Allow container service to settle
sleep 2

# Start Waydroid user session in background
echo "Starting Waydroid user session..."
if command -v dbus-run-session >/dev/null 2>&1 && [ -z "$DBUS_SESSION_BUS_ADDRESS" ]; then
    dbus-run-session waydroid session start &
else
    waydroid session start &
fi

echo "Waiting for Android boot..."
for i in $(seq 1 120); do
    STATUS=$(waydroid shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n')
    if [ "$STATUS" = "1" ]; then
        echo "Android boot completed!"
        waydroid shell -u 0 /system/bin/sh -c "mount -o remount,rw /sys/fs/cgroup 2>/dev/null; echo 0 > /proc/sys/net/ipv4/ip_unprivileged_port_start 2>/dev/null || true" 2>/dev/null || true
        waydroid shell -u 0 /system/bin/sh -c "if ! pidof lmkd >/dev/null 2>&1; then /system/bin/lmkd & fi" 2>/dev/null || true
        sleep 2
        echo "Activating Waydroid Full UI in Cage..."
        waydroid show-full-ui &
        break
    fi
    sleep 2
done

# Keep Cage compositor session running without high CPU usage
while true; do
    sleep 3600 &
    wait $!
done

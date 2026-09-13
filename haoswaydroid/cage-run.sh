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
        break
    fi
    sleep 2
done

# Display Waydroid Full UI under Cage and keep it running
while true; do
    echo "Launching Waydroid Full UI under Cage..."
    waydroid show-full-ui || true
    sleep 2
done

#!/bin/sh
echo "Cage session initialized with WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"

# Allow container service to settle
sleep 2

# Start Waydroid user session in background
echo "Starting Waydroid user session..."
waydroid session start &

echo "Waiting for Android boot..."
for i in $(seq 1 120); do
    STATUS=$(waydroid shell getprop sys.boot_completed 2>/dev/null | tr -d '\r\n')
    if [ "$STATUS" = "1" ]; then
        echo "Android boot completed!"
        break
    fi
    sleep 2
done

# Display Waydroid Full UI under Cage
echo "Launching Waydroid Full UI under Cage..."
waydroid show-full-ui || true

# Keep Cage session alive without burning CPU in a busy loop
while true; do
    sleep 3600 &
    wait $!
done

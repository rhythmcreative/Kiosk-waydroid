#!/bin/sh
echo "Cage session initialized with WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"

# Wait for Waydroid container service to be ready
echo "Waiting for Waydroid container..."
for i in $(seq 1 30); do
    if waydroid status 2>&1 | grep -q "RUNNING"; then
        echo "Waydroid container is RUNNING."
        break
    fi
    sleep 1
done

# Start Waydroid user session in background
echo "Starting Waydroid user session..."
waydroid session start &

sleep 3

# Display full Waydroid UI in fullscreen under Cage
echo "Launching Waydroid Full UI under Cage..."
exec waydroid show-full-ui

#!/bin/sh
echo "Cage session initialized with WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"

# Allow container service to settle
sleep 2

# Start Waydroid user session in background
echo "Starting Waydroid user session..."
waydroid session start &

sleep 3

# Display full Waydroid UI in fullscreen under Cage
echo "Launching Waydroid Full UI under Cage..."
exec waydroid show-full-ui

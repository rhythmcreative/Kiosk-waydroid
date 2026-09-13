#!/bin/sh
echo "Cage session initialized with WAYLAND_DISPLAY=${WAYLAND_DISPLAY}"

# Start waydroid user session in background
waydroid session start &

# Wait for session socket to initialize
sleep 3

# Display full Waydroid UI in fullscreen under Cage
exec waydroid show-full-ui

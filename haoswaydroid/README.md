# Home Assistant Add-on: Waydroid Kiosk Satellite

Run a dedicated **Waydroid** (Android) kiosk display directly on your Home Assistant OS machine's attached screen, running [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) with full microphone access for native voice assistants, wake-word detection, hardware acceleration, gesture control, and remote administration.

## Features

- 📱 **Full Waydroid Environment**: Complete Android container running natively on your hardware.
- 🎙️ **Microphone & Audio Passthrough**: Full access to microphones for wake-words with [Voice Satellite](https://github.com/jxlarrea/voice-satellite-card-integration) or Assist.
- 🖥️ **Wayland Kiosk (Cage)**: Hardware-accelerated fullscreen Wayland compositor outputting directly to HDMI/DisplayPort screens via DRM/KMS.
- ⚡ **Auto-installation & Updates**: Automatically fetches, installs, and keeps [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) up to date.
- 🔒 **Automatic Permissions**: Grants `RECORD_AUDIO`, `CAMERA`, and system permissions automatically upon launch.
- 🌐 **Remote Web Admin**: Access Kiosk Satellite's web management interface at `http://<homeassistant-ip>:2324` or via Ingress.
- 🛠️ **Display Adjustments**: Supports custom resolution, DPI, and screen orientation (portrait/landscape).

## Requirements

1. **Hardware / Kernel**:
   - Home Assistant OS running on x86_64 or aarch64 (Raspberry Pi 4/5, Intel NUC, Mini PC).
   - Linux kernel supporting `binder` / `binderfs`.
2. **Add-on Protection Mode**:
   - Turn **OFF** "Protection mode" in the add-on settings so Waydroid can access `/dev/dri`, `/dev/input`, and binder nodes.

## Configuration Options

```yaml
apk_url: ""               # Optional direct APK download link (empty = latest GitHub release)
auto_update_apk: true     # Automatically update Kiosk Satellite on startup
display_width: 0          # Custom width in pixels (0 for native)
display_height: 0         # Custom height in pixels (0 for native)
display_dpi: 0            # Screen density DPI (0 for auto)
display_orientation: auto # Rotation: auto, 0, 90, 180, 270
remote_admin_port: 2324   # Port for Kiosk Satellite Web Admin
enable_camera: true       # Allow camera for gestures & streaming
audio_volume: 100         # Volume level
keep_alive: true          # Auto-restart app if closed
```

## First-time Setup

1. Install and start the Add-on.
2. The add-on will initialize the Waydroid system image, start the Cage Wayland display server, and install Kiosk Satellite.
3. Open `http://<your-device-ip>:2324` in your browser to complete the Kiosk Satellite setup wizard and connect to Home Assistant!

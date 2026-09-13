# Waydroid Kiosk Satellite

Display [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) on your attached display with full microphone, audio, touch, and hardware acceleration on Home Assistant OS using Waydroid.

**Maintainer:** rhythmcreative · **Version:** 1.0.0 (September 2026) · See the [CHANGELOG](CHANGELOG.md).

Launches Waydroid + Cage Wayland Compositor running [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite). Microphone, sound, touchscreen, and keyboard work out of the box with auto-granted Android permissions and remote management interface on port 2324.

> **Before you start:** A display must be connected to HDMI/DisplayPort before starting. **Protection mode** MUST be toggled **OFF** in the Add-on settings so Waydroid can access `/dev/dri`, `/dev/binderfs`, and input devices.


---

## Install

1. [![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frhythmcreative%2FKiosk-waydroid)
   — or manually: **Add-on Store → ⋮ → Repositories** → add
   `https://github.com/rhythmcreative/Kiosk-waydroid`
2. Install **Waydroid Kiosk Satellite**.
3. Toggle **Protection mode** OFF under the Info tab.
4. **Start**.
5. Open `http://<your-ha-ip>:2324` in your browser to configure your dashboard and voice settings.

---

## Configuration options

| Option | Default | What it does |
|---|---|---|
| `apk_url` | `""` | Optional direct link to a custom Kiosk-Satellite APK. Leave empty to auto-download the latest official GitHub release. |
| `auto_update_apk` | `true` | Automatically checks and installs newer versions of Kiosk Satellite when the add-on boots. |
| `display_width` | `0` | Force a custom display width in pixels (0 for native resolution). |
| `display_height` | `0` | Force a custom display height in pixels (0 for native resolution). |
| `display_dpi` | `0` | Screen density DPI (0 for auto). Useful for high-DPI displays. |
| `display_orientation` | `auto` | Screen rotation: `auto`, `0`, `90`, `180`, `270`. |
| `remote_admin_port` | `2324` | Port for the Kiosk Satellite web management interface. |
| `enable_camera` | `true` | Enables camera input passthrough for hand gestures and streaming. |
| `audio_volume` | `100` | Default volume level (0-100). |
| `keep_alive` | `true` | Watchdog service to restart Kiosk Satellite if closed. |

---

## Voice Satellite & Microphone Access

Kiosk Satellite includes native voice control with [Voice Satellite](https://github.com/jxlarrea/voice-satellite-card-integration):
- PulseAudio microphone input is mapped directly into Android container.
- `android.permission.RECORD_AUDIO` is granted automatically at startup.
- Works out of the box with local wake words (openWakeWord, microWakeWord) and Home Assistant Assist pipelines.

---

## Troubleshooting

- **Black screen on boot**: Ensure your display was connected before starting the Add-on, and verify that **Protection mode** is disabled in the Add-on tab.
- **Microphone not detected**: Check Home Assistant OS audio settings and verify host pulse server is accessible (`/run/audio/pulse.sock`).
- **Cannot connect to port 2324**: Make sure port `2324` is not blocked by your firewall and the container has fully finished the first-time image initialization.

---

<div align="center">

<p>Made with ❤️ from rhythmcreative.</p>

</div>

# Kiosk Waydroid for Home Assistant

Repository containing the **Waydroid Kiosk Satellite** Add-on for Home Assistant OS.

Run Android applications (specifically [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite)) on your Home Assistant machine's connected HDMI/touch screen display with full hardware acceleration, microphone input (wake-word / Voice Satellite), speaker audio, touch/mouse gestures, and remote administration.

## Add-on Included

- [**Waydroid Kiosk Satellite**](haoswaydroid/): Full Waydroid container running Cage Wayland kiosk with automatic Kiosk Satellite APK installation, auto-granted microphone permissions, and remote web control.

## Installation in Home Assistant

1. In Home Assistant, navigate to **Settings** > **Add-ons** > **Add-on Store**.
2. Click the three dots (top right) > **Repositories**.
3. Add this repository URL:
   ```
   https://github.com/rhythmcreative/Kiosk-waydroid
   ```
4. Find **Waydroid Kiosk Satellite** in the list and click **Install**.
5. Disable **Protection mode** in the add-on panel (required for GPU/DRI and binder access).
6. Click **Start**.
7. Open `http://<homeassistant-ip>:2324` in your browser to configure Kiosk Satellite!

## License

MIT License.

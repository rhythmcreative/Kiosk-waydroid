# Changelog

## 1.0.2
- Fix: Unset WAYLAND_DISPLAY and DISPLAY before starting Cage compositor to prevent wlroots attempting nested Wayland backend instead of native DRM/KMS.
- Fix: Set WLR_BACKENDS=drm,libinput and WLR_LIBINPUT_NO_DEVICES=1.
- Updated Cage launch sequence to synchronize with Waydroid container status.

## 1.0.1
- Fix: Safe handling of binder nodes on read-only /dev filesystems.
- Fix: Host-level binderfs detection and integration.
- Fix: GitHub Actions multi-arch manifest publication workflow.
- Updated base dependencies and Cage session management.

## 1.0.0
- Initial release of Waydroid Kiosk Satellite Add-on for Home Assistant.
- Full Waydroid containerized Android environment running on Cage Wayland DRM/KMS compositor.
- Complete hardware acceleration with Mesa DRI/EGL/GLES.
- Full PulseAudio microphone and speaker passthrough.
- Automatic download, installation, and update of Kiosk Satellite APK.
- Auto-grant of permissions: Audio recording (Microphone / Wake Word), Camera (Gestures), Notifications, System Alert.
- Remote administration web interface accessible via port 2324 or Ingress.
- Display configuration options: width, height, DPI, and screen rotation.
- Watchdog keep-alive mechanism to maintain Kiosk Satellite running.

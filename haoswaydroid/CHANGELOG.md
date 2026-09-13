# Changelog

## 1.0.9
- Fix: Prevent `dnsmasq` port 53 collision on host network when DNS servers like Pi-hole or CoreDNS are active on the host. Configure internal bridge with `--port=0` (DHCP only) and direct public upstream DNS resolvers.

## 1.0.8
- Fix: Add D-Bus policy for `id.waydro.Session` in `/etc/dbus-1/system.d/id.waydro.Session.conf` allowing root to own the session service on the shared system bus.
- Fix: Optimize session launch in `cage-run.sh` to start Waydroid user session immediately without stalling on container status polling.

## 1.0.7
- Fix: Upgrade Mesa drivers to version 25 via Debian bookworm-backports for full Raspberry Pi 5 VideoCore VII (V3D 7.1) hardware acceleration.
- Fix: Install Xwayland binary required by Cage compositor.
- Fix: Add WLR_RENDERER_ALLOW_SOFTWARE=1 fallback for robust compositor initialization.

## 1.0.6
- Fix: Added `libcage_root_bypass.so` via `LD_PRELOAD`. Bypasses Cage 0.1.4's internal `drop_permissions()` check which refused to start when run inside a container as root.
- Fix: Combined with `SEATD_VTBOUND=0` for immediate DRM/KMS hardware display initialization.

## 1.0.5
- Fix: Set `SEATD_VTBOUND=0` in `seatd`. Disables VT/TTY switching at the seatd level so clients (Cage/wlroots) receive the active session signal immediately without requesting physical VT switching.
- Fix: Ensured `/run/seatd.sock` permissions and symlink.

## 1.0.4
- Fix: Added `WLR_NO_HARDWARE_CURSORS=1` for clean rendering on Raspberry Pi DRM KMS.

## 1.0.3
- Fix: Corrected seatd socket path to /run/seatd.sock with symlink to /run/seatd/seatd.sock.
- Fix: Added /dev/tty and /dev/tty0 to devices list for direct DRM/KMS session access.
- Fix: Explicitly point WLR_DRM_DEVICES to /dev/dri/card0 for HDMI output.

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

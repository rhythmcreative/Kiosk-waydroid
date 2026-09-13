# Changelog

## 1.0.13
- Fix: Enable host udev support (`udev: true`) in add-on configuration so Cage and libinput can detect and tag USB touchscreens, mice, and keyboards.
- Fix: Add `/dev/uinput`, `/dev/input/mice`, and `/dev/input/mouse0` to add-on device permissions.
- Fix: Automatically initialize fallback `systemd-udevd` daemon and run `udevadm trigger` if host udev database is not mounted.
- Fix: Ensure read/write access permissions on all `/dev/input/*` event nodes at container startup.
- Fix: Proxy web admin port 2324 directly into Waydroid container network namespace via `nsenter`.
- Performance: Eliminated 2-second busy loop calling `waydroid show-full-ui` in `cage-run.sh`, significantly reducing idle CPU usage.

## 1.0.12
- Fix: Resolved Android container reboot loop caused by bpfloader failure on Linux 6.12+ kernels by disabling `reboot_on_failure` and setting `bpf.progs_loaded 1`.
- Fix: Introduced `libcap_shim.so` to stub missing container capabilities (`capset`, `cap_set_proc`, `cap_get_flag`) and process priority (`setpriority`), preventing aborts in `lmkd`, `logd`, `audioserver`, and `zygote`.
- Fix: Resolved `EventHub` fatal abort in `system_server` ("Input must be able to block suspend") by mocking `cap_get_flag` for `CAP_BLOCK_SUSPEND` in `libcap_shim`.
- Fix: Resolved `SecurityException` in `SystemServer.run()` caused by `Process.setThreadPriority` on container environments.
- Fix: Clamped `zygote` priority to 0 and preloaded `libcap_shim.so` in 64-bit zygote init service.
- Fix: Added full Linux capability bounding set to `privileged` in add-on `config.yaml`.
- Fix: Automatic extraction and generation of compatibility overlays directly on container start.

## 1.0.11
- Fix: Overlay Android `cgroups.json` with `Optional: true` for cgroup v2 compatibility, preventing Android `/init` crash on `SetupCgroups`.
- Fix: Remount `/sys/fs/cgroup` and `/dev` as read-write.
- Fix: Replace `/dev/null` with `/bin/true` in `lxc.hook.post-stop`.
- Fix: Loop and wait for Android boot in `cage-run.sh` to prevent Cage compositor from prematurely terminating.

## 1.0.10
- Fix: Prevent `waydroid-net.sh` failure on read-only `/proc/sys/net/ipv4/ip_forward` inside Docker container.

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

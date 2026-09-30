# Changelog

## 1.0.32
- Fix: **Pin the ReSpeaker microphone card to its native 16 kHz.** The `seeed2micvoicec` card is a combined play/record codec whose DSP runs at 16 kHz, but PulseAudio was opening it at its 44.1 kHz default. Both consumers (Kiosk Satellite / Waydroid and Home Assistant's voice assistant) request 16 kHz, so every capture was served by resampling 44.1 → 16 kHz, which is what made the wake word and voice recognition unreliable. After this, the source runs at 16 kHz and neither consumer resamples. Verified on-device: 8 s of capture at 16 kHz with RMS ≈ 1400, peak ≈ 1700 and zero dropouts.
- Fix: **Probe for the PulseAudio socket instead of hard-coding one path.** The entire audio-routing block was gated on `/run/audio/pulse.sock` existing, which is the HAOS path. On Home Assistant Supervised the host server is at `/var/lib/homeassistant/audio/external/pulse.sock`, so on that deployment the whole block — including every audio and microphone fix — was silently skipped. Both paths are now probed, plus the default, and `pactl info` is used as the real reachability test.
- Fix: **Detect the PulseAudio server before starting a private daemon.** On deployments where the host socket lives elsewhere, the previous code fell through to `pulseaudio --start`, spawning a second hardware-less server that competes with the host one for the ALSA devices.
- Note: The HDMI sink still reports a large configured buffer (~341 ms; ~2 s on the seeed sink). `fragments` and `fragment_size` in `module-alsa-card` were measured to have **no effect** — five different combinations all yielded an identical ~2 s buffer, so the size is imposed by the ALSA driver, not by PulseAudio. There are **no underruns** (0 in 120 samples over 12 s); the remaining latency is a driver-level limit, not a tuning problem.

## 1.0.31
- Revert: Restore `run.sh`, `kiosk_helper.py` and `config.yaml` to their state prior to v1.0.29. The audio and microphone changes from v1.0.29 / v1.0.30 are withdrawn; the container failed to start with `OSError: container failed to start`.
- Fix: Strip any leftover `lxc.mount.entry` for `/proc/asound` or `/dev/snd` from the persisted LXC configs. This one change is deliberately kept from v1.0.30, because those entries were already written to `/var/lib/waydroid/lxc/waydroid/` before startup aborted and a plain code revert would leave them there, so the container would keep failing to start forever.
- Note: `/proc/asound` is a procfs subdirectory, so `create=dir` makes LXC attempt `mkdir()` inside the container's own procfs, which fails with `EPERM`. Do not re-add that mount.

## 1.0.30
- Fix: **Regression in 1.0.29 that prevented the container from starting** (`OSError: container failed to start`). The `/proc/asound` LXC bind mount added in 1.0.29 is invalid: `/proc/asound` is a subdirectory of procfs, so `create=dir` makes LXC attempt `mkdir()` inside the container's own procfs, which returns `EPERM`. The mount fails and LXC aborts. It was also unnecessary — `/proc/asound` is published by the kernel's ALSA subsystem and is already visible through the container's own `/proc`.
- Fix: Actively **remove** any `/proc/asound` entry already persisted in `/var/lib/waydroid/lxc/waydroid/`, since those files survive add-on reinstalls and simply not adding the line again would leave the broken entry in place.
- Fix: Make the `/dev/snd` bind mount conditional on the source existing and mark it `optional`, so a missing ALSA device can never block container startup.
- Fix: Re-apply the LXC mount entries after `waydroid init`, since a fresh init regenerates `config_base`/`config` from scratch and would otherwise drop them.

## 1.0.29
- Fix: **Remove the `module-alsa-card` unload/reload cycle.** It was tearing down the sink and every live stream on the *shared* HAOS PulseAudio server (including Home Assistant's own TTS). Stability is now achieved without touching a live module.
- Fix: **Correct the buffer-size miscalculation that caused the choppy audio.** `fragment_size` is expressed in *frames*, not bytes: `8192 frames x 2ch x 2 bytes = 32 KB` per fragment, so `fragments=8` requested a **256 KB / ~1.365 s** buffer at 48 kHz, not the "64 KB / ~370 ms" recorded in 1.0.27. Combined with `tsched=no` (which disables the ALSA timer scheduler) this produced the very crackling and latency it was intended to cure.
- Fix: **Stop `SIGKILL`ing Android's `audioserver` on every PulseAudio socket inode change.** The supervisor recreates `/run/audio/pulse.sock` whenever `hassio_audio` restarts, so playback was being cut and the microphone killed periodically. Clients now reconnect on their own; the audio HAL is only restarted after a bounded grace period if it fails to recover.
- Fix: **Set `PULSE_RUNTIME_PATH` correctly.** Waydroid reads this *environment variable* (`tools/config/__init__.py`), not an Android system property. The previous `waydroid prop set waydroid.pulse_runtime_path` calls were dead code, so the container silently fell back to binding `/run/user/0/pulse/native`.
- Fix: **Bind-mount `/dev/snd` and `/proc/asound` into the LXC container** so Android's audio HAL has a real ALSA codec (HDMI playback, ReSpeaker capture) to attach to. Without these, the microphone could not work reliably.
- Fix: **Wait for the HAOS PulseAudio socket at startup instead of racing it.** If the socket is absent, fail loudly rather than starting a second, hardware-less PulseAudio daemon that would shadow the host server and leave the container on a null sink with a dead microphone.
- Fix: **Microphone permissions are now re-verified periodically.** `RECORD_AUDIO` was only ever granted on a fresh install, so a single Android permission auto-reset killed the microphone permanently with nothing in the log.
- Fix: **Grant the `RECORD_AUDIO` appop**, so capture cannot be silently refused while the permission appears granted.
- Fix: **Precise microphone source selection.** The previous substring match (including `"sound"`) could latch onto an unrelated card.
- Fix: **Add `mic_volume` option (default 70%).** Capture gain was hardcoded to 100%, which clips on the ReSpeaker array and degrades wake-word/STT accuracy. `audio_volume` also no longer forces the shared server's microphone gain.
- Fix: **Reduce PulseAudio default fragmentation to 4** so the resampler has headroom under CPU load, and accept the recorder's native rate/format (`PULSE_LATENCY_MSEC=60`) so resampling happens once centrally instead of per client.
- Fix: **Drop the expensive `dumpsys window` call** from the 10-second keep-alive watchdog; it dumped the entire window-manager state over LXC+ADB and starved the audio threads of CPU.
- Feature: Add an ALSA fallback that drives audio directly from inside Android (using the newly bind-mounted `/proc/asound`) if the shared PulseAudio socket is unreachable from the container. No-op on a normal boot.

## 1.0.28
- Fix: Set default `audio_volume` to 80% to avoid speaker amplifier clipping and distortion on compact HDMI displays (e.g. MPI7002 7-inch LCDs).
- Fix: Maintain PulseAudio native 44.1kHz rate with tuned 64KB interrupt buffers (`fragments=8 fragment_size=8192`) to prevent fractional resampler phase drift and choppy playback.

## 1.0.27
- Fix: Eliminate robotic / metallic voice distortion and stuttering on Raspberry Pi 5 HDMI audio by tuning PulseAudio buffer fragments (`fragments=8 fragment_size=8192`, 64KB total buffer / ~370ms latency buffer) to prevent `vc4` driver interrupt spin loops (`POLLOUT` without available data).

## 1.0.26
- Fix: Eliminate Raspberry Pi 5 HDMI audio crackling, popping, and buffer underruns ("crrg") by automatically detecting Broadcom `vc4-hdmi` and reloading `module-alsa-card` with `tsched=no` (interrupt-driven scheduling).
- Fix: Bind mount `/run/audio` as a directory in LXC container configuration so Android PulseAudio clients survive `hassio_audio` restarts without stale socket inode disconnects.
- Fix: Add PulseAudio watchdog in `kiosk_helper.py` that monitors socket inode changes, re-establishes native symlinks, and automatically restarts Android audio services (`android.hardware.audio.service`, `audioserver`).
- Fix: Automatically configure default audio routing to HDMI output for playback/TTS and Seeed Voicecard / ReSpeaker Pi HAT for microphone input.
- Feature: Apply `audio_volume` configuration option to both host PulseAudio sink and Android internal media/system streams.
- Fix: Grant `android.permission.MODIFY_AUDIO_SETTINGS` to Kiosk Satellite on installation.

## 1.0.25
- Feature: Persist Android user data across reboots (`/root/.local/share/waydroid`).

## 1.0.24
- Fix: Preserve Kiosk Satellite settings on APK updates using `pm install -r`.

## 1.0.23
- Fix: Fix APK reinstall on every boot — preserve Kiosk Satellite settings across restarts.

## 1.0.22
- Feature: Add `auto_launch_kiosk` option to control Kiosk Satellite auto-start.

## 1.0.21
- Fix: Preserve nft in waydroid-net, add ip rule lookup main, and DNS redirect.

## 1.0.20
- Fix: Add default gateway, DNS, and host iptables NAT for Waydroid.

## 1.0.19
- Fix: Launch app using shell uid 2000.

## 1.0.18
- Fix: Add dummy_lmkd daemon to resolve system_server ANR hang and fix cage ui timing.
- Fix: Comment out `capabilities` in system/vendor rc files to prevent Android `init` from aborting `logd` with status 6 on unsupported capability sets.
- Fix: Launch `waydroid show-full-ui &` immediately in `cage-run.sh` to eliminate the black screen delay during boot.

## 1.0.16
- Fix: Remove `WLR_DRM_NO_MODIFIERS=1` to restore V3D 7.1 hardware accelerated surface modifiers required by wlroots `render.c` commit on Raspberry Pi 5.

## 1.0.15
- Fix: Add `WLR_DRM_NO_MODIFIERS=1` to fix wlroots `Basic output test failed for HDMI-A-1` atomic DRM plane test failure on Raspberry Pi 5.
- Fix: Resolve `lmkd` crashing and `system_server` 100% CPU busy loop by configuring `lxc.mount.auto = cgroup:rw` and commenting out incompatible `task_profiles` in Android rc files on pure cgroup v2 kernels.
- Fix: Fix `libcap_shim.c` to call real `SYS_capset` and `SYS_setpriority` syscalls with fallback, allowing network stack (`CAP_NET_RAW`, `CAP_NET_ADMIN`) and system services to receive capabilities.
- Fix: Set `net.ipv4.ip_unprivileged_port_start=0` inside the container and Android netns to allow DHCP client to bind to port 68.
- Fix: Grant `FOREGROUND_SERVICE` and `SYSTEM_ALERT_WINDOW` permissions/appops in `kiosk_helper.py` to prevent Kiosk Satellite ANR on service startup.
- Performance: Fix severe framerate degradation (< 1 FPS) by explicitly routing wlroots GLES2 hardware rendering to `/dev/dri/renderD128` (VideoCore VII / V3D) via `WLR_RENDER_DRM_DEVICE` while preserving `/dev/dri/card0` for KMS scanout, eliminating CPU llvmpipe software rasterization fallback.
- Fix: Configure `WLR_RENDERER=gles2` and remove `WLR_RENDERER_ALLOW_SOFTWARE` to prevent Cage from falling back to CPU rendering.
- Fix: Disable Android lockscreen, keyguard, and screen timeout (`stay_on_while_plugged_in 3`, `screen_off_timeout 2147483647`, `lockscreen.disabled 1`) at boot to ensure direct touch response.
- Fix: Launch Kiosk Satellite directly using `am start -n me.jxl.kiosk_satellite/.MainActivity` after dismissing keyguard to ensure immediate application presentation and touch focus.
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

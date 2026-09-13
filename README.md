<h1 align="center">Kiosk-waydroid </h1>

<div align="center">

<p><i> Waydroid & Kiosk-Satellite setup for Home Assistant. </i></p>

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-41BDF5?style=for-the-badge&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![Android](https://img.shields.io/badge/Android-3DDC84?style=for-the-badge&logo=android&logoColor=white)](https://www.android.com/)
[![Waydroid](https://img.shields.io/badge/Waydroid-00B0FF?style=for-the-badge&logo=linux&logoColor=white)](https://waydro.id/)
[![Linux](https://img.shields.io/badge/Linux-FCC624?style=for-the-badge&logo=linux&logoColor=black)](https://www.linux.org/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

</div>

[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=Fira+Code&size=23&pause=1000&color=F7F7F7&vCenter=true&width=435&height=30&lines=ABOUT)](https://git.io/typing-svg)

This project provides a complete Waydroid (Android container) kiosk for Home Assistant OS.

It runs a hardware-accelerated Wayland kiosk environment (Cage) running [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) with full microphone and speaker access for native Voice Satellite wake-word detection, cameras, music streaming, and screensavers.

It is designed for a simple, fast, and dedicated Home Assistant Android kiosk experience on your HAOS device screen.

______________________________________________________________________

[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=Fira+Code&size=23&pause=1000&color=F7F7F7&vCenter=true&width=435&height=30&lines=FEATURES)](https://git.io/typing-svg)

- **Full Android Container (Waydroid)**: Run native Android apps on Home Assistant OS
- **Microphone & Audio Passthrough**: Full access to microphones for wake-words with [Voice Satellite](https://github.com/jxlarrea/voice-satellite-card-integration)
- **Automatic APK Installation**: Auto-downloads and installs the latest [Kiosk Satellite](https://github.com/jxlarrea/kiosk-satellite) release on boot
- **Auto-granted Android Permissions**: Automatically grants `RECORD_AUDIO`, `CAMERA`, and system overlay permissions
- **Hardware Graphics Acceleration**: Native DRM/KMS output with Mesa DRI/EGL/GLES via Cage Wayland compositor
- **Remote Web Administration**: Built-in access to Kiosk Satellite web management at `http://<homeassistant-ip>:2324` or via Ingress
- **Display Customization**: Full control over screen resolution, DPI density, and orientation (portrait/landscape)
- **Watchdog Keep-Alive**: Automatically restores and relaunches Kiosk Satellite if interrupted

______________________________________________________________________

[![Typing SVG](https://readme-typing-svg.herokuapp.com?font=Fira+Code&size=23&pause=1000&color=F7F7F7&vCenter=true&width=435&height=30&lines=INSTALL)](https://git.io/typing-svg)

1. HA → **Settings → Add-ons → Add-on Store → ⋮ → Repositories**
2. Add `https://github.com/rhythmcreative/Kiosk-waydroid`
3. Install **Waydroid Kiosk Satellite**.
4. Disable **Protection mode** in the add-on page (required for `/dev/dri`, `/dev/binderfs`, and sound devices).
5. Click **Start**, then navigate to `http://<device-ip>:2324` to finish the setup wizard!

(Or use the button below for an easier install)

[![Add repository to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Frhythmcreative%2FKiosk-waydroid)

______________________________________________________________________

<div align="center">

<p>Made with ❤️ from rhythmcreative.</p>

</div>

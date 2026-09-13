################################################################################
# Add-on: Waydroid Kiosk Satellite (haoswaydroid)
# File: Dockerfile
################################################################################

ARG BUILD_FROM=ghcr.io/home-assistant/base-debian:bookworm
FROM $BUILD_FROM

ENV DEBIAN_FRONTEND=noninteractive

# Enable Debian bookworm-backports repository for modern Mesa (supports Raspberry Pi 5 VideoCore VII / V3D 7.1)
RUN echo "deb http://deb.debian.org/debian bookworm-backports main" >> /etc/apt/sources.list

# Install dependencies, repositories, Waydroid, Cage compositor, and audio tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    wget \
    gnupg \
    lsb-release \
    jq \
    unzip \
    procps \
    kmod \
    dbus \
    dbus-user-session \
    socat \
    gcc \
    libc6-dev \
    # Graphics and Wayland Compositor (Cage & XWayland)
    cage \
    xwayland \
    seatd \
    udev \
    libinput-bin \
    libinput10 \
    # LXC & Networking for Waydroid container
    lxc \
    dnsmasq \
    iptables \
    nftables \
    iproute2 \
    # Audio / Microphone Passthrough
    pulseaudio \
    pulseaudio-utils \
    alsa-utils \
    libpulse0 \
    # Android tools
    adb \
    # Python runtime
    python3 \
    python3-requests \
    python3-aiohttp \
    python3-pip \
    && apt-get install -y -t bookworm-backports --no-install-recommends \
    libdrm2 \
    libgl1-mesa-dri \
    libegl-mesa0 \
    libgbm1 \
    mesa-va-drivers \
    mesa-vulkan-drivers \
    && rm -rf /var/lib/apt/lists/*

# Add Waydroid repository and install Waydroid
RUN mkdir -p /usr/share/keyrings \
    && curl -fsSL https://repo.waydro.id/waydroid.gpg > /usr/share/keyrings/waydroid.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/waydroid.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends waydroid \
    && rm -rf /var/lib/apt/lists/*

# Compile root bypass library for Cage
COPY libcage_root_bypass.c /
RUN gcc -shared -fPIC /libcage_root_bypass.c -o /usr/lib/libcage_root_bypass.so \
    && rm -f /libcage_root_bypass.c

ARG BUILD_VERSION
ENV ADDON_VERSION=${BUILD_VERSION}

# Copy scripts, configs and translations
COPY id.waydro.Session.conf /etc/dbus-1/system.d/id.waydro.Session.conf
COPY translations/*.yaml /translations/
COPY cage-run.sh /
COPY kiosk_helper.py /
COPY run.sh /

RUN chmod a+x /run.sh /kiosk_helper.py /cage-run.sh

WORKDIR /

CMD [ "/run.sh" ]

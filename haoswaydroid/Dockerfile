################################################################################
# Add-on: Waydroid Kiosk Satellite (haoswaydroid)
# File: Dockerfile
################################################################################

ARG BUILD_FROM
FROM $BUILD_FROM

ENV DEBIAN_FRONTEND=noninteractive

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
    # Graphics and Wayland Compositor (Cage)
    cage \
    seatd \
    udev \
    libinput-bin \
    libinput10 \
    libdrm2 \
    libgl1-mesa-dri \
    libegl1-mesa \
    libgles2-mesa \
    mesa-va-drivers \
    mesa-vulkan-drivers \
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
    && rm -rf /var/lib/apt/lists/*

# Add Waydroid repository and install Waydroid
RUN mkdir -p /usr/share/keyrings \
    && curl -fsSL https://repo.waydro.id/waydroid.gpg > /usr/share/keyrings/waydroid.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/waydroid.gpg] https://repo.waydro.id/ $(lsb_release -cs) main" > /etc/apt/sources.list.d/waydroid.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends waydroid \
    && rm -rf /var/lib/apt/lists/*

ARG BUILD_VERSION
ENV ADDON_VERSION=${BUILD_VERSION}

# Copy scripts and translations
COPY translations/*.yaml /translations/
COPY kiosk_helper.py /
COPY run.sh /

RUN chmod a+x /run.sh /kiosk_helper.py

WORKDIR /

CMD [ "/run.sh" ]

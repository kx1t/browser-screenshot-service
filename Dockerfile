FROM ghcr.io/sdr-enthusiasts/docker-baseimage:python

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
# keep container env vars visible to the app (s6 strips them otherwise)
ENV S6_KEEP_ENV=1

# All Python deps come from apt; no pip needed.
COPY requirements.txt /opt/app/

RUN set -eux && \
KEPT_PACKAGES=() && \
KEPT_PACKAGES+=(python3-selenium) && \
KEPT_PACKAGES+=(chromium) && \
KEPT_PACKAGES+=(chromium-driver) && \
KEPT_PACKAGES+=(python3-uvloop) && \
KEPT_PACKAGES+=(python3-starlette) && \
KEPT_PACKAGES+=(python3-uvicorn) && \
KEPT_PACKAGES+=(python3-timeout-decorator) && \
#
    apt-get update -q && \
#
# Dummy provider for two virtual packages, to keep the GTK/portal/systemd
# stack out of the image:
#   - xdg-desktop-portal-backend: hard dep of `chromium`; all real providers
#     (xdg-desktop-portal-gtk/-gnome/-kde/-wlr) drag in GTK3, dconf, upower,
#     adwaita, and dbus-user-session -> libpam-systemd -> systemd + systemd-sysv.
#     Installing systemd breaks under qemu-user (multiarch builds) and is
#     pointless in an s6-based image anyway.
#   - dbus-session-bus: pulled by dconf/portal libs; nothing here needs a
#     session bus at runtime.
    mkdir -p /tmp/dummy/DEBIAN && \
    printf '%s\n' \
        'Package: snapapi-virtual-blockers' \
        'Version: 1.0' \
        'Section: misc' \
        'Priority: optional' \
        'Architecture: all' \
        'Provides: xdg-desktop-portal-backend, dbus-session-bus' \
        'Maintainer: snapapi' \
        'Description: Dummy provider to keep the GTK/portal/systemd stack out of this image' \
        > /tmp/dummy/DEBIAN/control && \
    dpkg-deb --build /tmp/dummy /tmp/snapapi-virtual-blockers.deb && \
    dpkg -i /tmp/snapapi-virtual-blockers.deb && \
#
# Install all these packages:
    apt-get install -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -o Dpkg::Options::="--force-confold" --allow-downgrades --allow-remove-essential --allow-change-held-packages -y --no-install-recommends  --no-install-suggests \
        ${KEPT_PACKAGES[@]} && \
#
# Safety net: systemd must never be present in this s6-based image. If a
# future base image or Debian dependency change reintroduces it, fail loudly
# instead of shipping a broken/bloated image.
    ! dpkg-query -W systemd >/dev/null 2>&1 && \
#
# Clean up:
    apt-get autoremove -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -y && \
    apt-get clean -q -y && \
    rm -rf /src/* /tmp/* /var/lib/apt/lists/*


COPY *.py /opt/app/

WORKDIR /opt/app/
CMD ["python3", "/opt/app/snapapi.py"]
EXPOSE 5042

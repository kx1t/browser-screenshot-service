FROM ghcr.io/sdr-enthusiasts/docker-baseimage:python

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
# keep container env vars visible to the app (s6 strips them otherwise)
ENV S6_KEEP_ENV=1

# All Python deps come from apt; no pip needed.
COPY requirements.txt /opt/app/

RUN set -x && \
KEPT_PACKAGES=() && \
KEPT_PACKAGES+=(python3-selenium) && \
KEPT_PACKAGES+=(chromium) && \
KEPT_PACKAGES+=(chromium-driver) && \
KEPT_PACKAGES+=(python3-uvloop) && \
KEPT_PACKAGES+=(python3-starlette) && \
KEPT_PACKAGES+=(python3-uvicorn) && \
KEPT_PACKAGES+=(python3-timeout-decorator) && \
#
# Install all these packages:
    apt-get update -q && \
    apt-get install -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -o Dpkg::Options::="--force-confold" --allow-downgrades --allow-remove-essential --allow-change-held-packages -y --no-install-recommends  --no-install-suggests \
        ${KEPT_PACKAGES[@]} && \
#
# Clean up:
    apt-get autoremove -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -y && \
    apt-get clean -q -y && \
    rm -rf /src/* /tmp/* /var/lib/apt/lists/*


COPY *.py /opt/app/

WORKDIR /opt/app/
CMD ["python3", "/opt/app/snapapi.py"]
EXPOSE 5042

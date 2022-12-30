FROM ghcr.io/sdr-enthusiasts/docker-baseimage@sha256:f0a386c3a166af7b8d329fa1a1d591c4338ac0105a3ffd6184e9a22617f60f22

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

COPY requirements.txt /opt/app/

RUN set -x && \
TEMP_PACKAGES=() && \
KEPT_PACKAGES=() && \
KEPT_PACKAGES+=(python3-selenium) && \
KEPT_PACKAGES+=(chromium-bsu) && \
KEPT_PACKAGES+=(chromium-driver) && \
TEMP_PACKAGES+=(gcc) &&\
TEMP_PACKAGES+=(python3-dev) && \
TEMP_PACKAGES+=(python3-distutils-extra) && \
#
# Install all these packages:
    apt-get update -q && \
    apt-get install -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -o Dpkg::Options::="--force-confold" --force-yes -y --no-install-recommends  --no-install-suggests\
        ${KEPT_PACKAGES[@]} \
        ${TEMP_PACKAGES[@]} && \
#
    pip install -U setuptools pip && \
    pip install uvloop && \
    pip3 install -r /opt/app/requirements.txt && \
#
# Clean up:
    apt-get remove -q -y ${TEMP_PACKAGES[@]} && \
    apt-get autoremove -q -o APT::Autoremove::RecommendsImportant=0 -o APT::Autoremove::SuggestsImportant=0 -y && \
    apt-get clean -q -y && \
    rm -rf /src/* /tmp/* /var/lib/apt/lists/*


COPY *.py /opt/app/

WORKDIR /opt/app/
CMD /opt/app/snapapi.py
EXPOSE 5042

#!/bin/bash
set -e

case ${TARGETARCH} in
    amd64|x86_64)
        UV_ARCH=x86_64-unknown-linux-gnu
        CADDY_ARCH=amd64
        ;;
    arm64)
        UV_ARCH=aarch64-unknown-linux-gnu
        CADDY_ARCH=arm64
        ;;
    *)
        echo "Unsupported architecture: ${TARGETARCH}"
        exit 1
        ;;
esac

curl -Lsf "https://github.com/astral-sh/uv/releases/download/0.7.20/uv-${UV_ARCH}.tar.gz" -o /tmp/uv.tar.gz
tar -xzf /tmp/uv.tar.gz -C /usr/local/bin --strip-components=1
rm /tmp/uv.tar.gz

curl -L "https://github.com/caddyserver/caddy/releases/download/v2.8.4/caddy_2.8.4_linux_${CADDY_ARCH}.deb" -o /tmp/caddy.deb
dpkg -i /tmp/caddy.deb
rm /tmp/caddy.deb

apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

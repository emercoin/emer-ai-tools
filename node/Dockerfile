# syntax=docker/dockerfile:1
#
# Emercoin wallet/node (emercoind). Multi-stage so the download/extract tooling
# and the tarball never reach the final image. Multi-arch: linux/amd64 and
# linux/arm64 (the release ships x86_64 and aarch64 tarballs). Since 0.8.6
# emercoind links only glibc + libgcc_s (libstdc++/boost/ssl/event are static),
# and both are already in debian-slim, so the runtime needs no extra packages.
#
#   docker buildx build --platform linux/amd64,linux/arm64 -t emercoin/core:0.8.6 node/
#
# Bump the node by editing EMER_DISTR_VERSION *and* EMER_SUMS_SHA256 (the sha256
# of that release's SHA256SUMS file: `curl -fsSL <release>/SHA256SUMS | sha256sum`).
# CI tags the image with EMER_DISTR_VERSION.
ARG EMER_DISTR_VERSION=0.8.6
ARG EMER_SUMS_SHA256=145532f9148efc2f5e3a71de81fdbdfb8f72c8faee2482452e2448ccc1933ce3
ARG EMER_RELEASE_URL=https://github.com/emercoin/emercoin/releases/download/v${EMER_DISTR_VERSION}emc

# --- download: one tarball per target arch (BuildKit builds only the one used) -
FROM scratch AS dl-amd64
ARG EMER_DISTR_VERSION EMER_RELEASE_URL
ADD ${EMER_RELEASE_URL}/emercoin-${EMER_DISTR_VERSION}-x86_64-linux-gnu.tar.gz /dl/

FROM scratch AS dl-arm64
ARG EMER_DISTR_VERSION EMER_RELEASE_URL
ADD ${EMER_RELEASE_URL}/emercoin-${EMER_DISTR_VERSION}-aarch64-linux-gnu.tar.gz /dl/

ARG TARGETARCH
FROM dl-${TARGETARCH} AS dl

# --- builder: verify + extract (runs natively on the build host, discarded) ----
FROM --platform=$BUILDPLATFORM debian:bookworm-slim AS build
ARG EMER_DISTR_VERSION EMER_SUMS_SHA256 EMER_RELEASE_URL
# SHA256SUMS is pinned by its own hash, so a tampered release asset (tarball or
# sums file) fails the build instead of silently shipping.
ADD --checksum=sha256:${EMER_SUMS_SHA256} ${EMER_RELEASE_URL}/SHA256SUMS /dl/
COPY --from=dl /dl/ /dl/
RUN set -eu; cd /dl \
 && tarball="$(ls emercoin-*-linux-gnu.tar.gz)" \
 && awk -v f="$tarball" '$2 == f' SHA256SUMS > sums \
 && test -s sums \
 && sha256sum -c sums \
 && tar xzf "$tarball" -C /tmp \
 && mkdir -p /out \
 && cp /tmp/emercoin-${EMER_DISTR_VERSION}/bin/emercoind \
       /tmp/emercoin-${EMER_DISTR_VERSION}/bin/emercoin-cli /out/

# --- runtime: minimal glibc base ----------------------------------------------
FROM debian:bookworm-slim
LABEL org.opencontainers.image.title="Emercoin Core" \
      org.opencontainers.image.description="Emercoin wallet/node (emercoind) in a minimal container" \
      org.opencontainers.image.source="https://github.com/emercoin/emer-ai-tools" \
      org.opencontainers.image.authors="Eugene Shumilov <mechnotech@ya.ru>"
COPY --from=build /out/emercoind /out/emercoin-cli /bin/
WORKDIR /srv/emercoind
# Ship the default config + helper here; a real deployment mounts its own
# emercoin.conf over /srv/emercoind/emercoin.conf (see deploy/docker-compose.yaml).
# COPY, not RUN cp: nothing executes in the target-arch image, so the arm64
# variant builds on an amd64 host without QEMU.
COPY emercoin.conf.example emercoin.pub changepass.sh ./
COPY emercoin.conf.example emercoin.conf
EXPOSE 6661 6662 5335
# Self-sufficient default (the old image defaulted to bash); compose still
# overrides `command:` with the same invocation.
CMD ["emercoind", "-datadir=/srv/emercoind", "-conf=/srv/emercoind/emercoin.conf", "-printtoconsole"]

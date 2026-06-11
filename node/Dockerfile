# syntax=docker/dockerfile:1
#
# Emercoin wallet/node (emercoind). Multi-stage so the download/extract tooling
# and the tarball never reach the final image. amd64 only — the emercoind release
# is x86_64. emercoind links only glibc + libstdc++6 (boost/ssl/event are static),
# so a minimal debian-slim base is enough.
#
# Bump the node by editing EMER_DISTR_VERSION; CI tags the image with this value.

# --- builder: fetch + extract the release (discarded) -------------------------
FROM debian:bookworm-slim AS build
ARG EMER_DISTR_VERSION=0.8.5
ADD https://github.com/emercoin/emercoin/releases/download/v${EMER_DISTR_VERSION}emc/emercoin-${EMER_DISTR_VERSION}-x86_64-linux-gnu.tar.xz /tmp/emer.tar.xz
RUN apt-get update \
 && apt-get install -y --no-install-recommends xz-utils \
 && tar xf /tmp/emer.tar.xz -C /tmp \
 && mkdir -p /out \
 && cp /tmp/emercoin-${EMER_DISTR_VERSION}-x86_64-linux-gnu/emercoind \
       /tmp/emercoin-${EMER_DISTR_VERSION}-x86_64-linux-gnu/emercoin-cli /out/

# --- runtime: minimal glibc base ----------------------------------------------
FROM debian:bookworm-slim
LABEL org.opencontainers.image.title="Emercoin Core" \
      org.opencontainers.image.description="Emercoin wallet/node (emercoind) in a minimal container" \
      org.opencontainers.image.source="https://github.com/emercoin/emer-ai-tools" \
      org.opencontainers.image.authors="Eugene Shumilov <mechnotech@ya.ru>"
RUN apt-get update \
 && apt-get install -y --no-install-recommends libstdc++6 \
 && rm -rf /var/lib/apt/lists/*
COPY --from=build /out/emercoind /out/emercoin-cli /bin/
WORKDIR /srv/emercoind
# Ship the default config + helper here; a real deployment mounts its own
# emercoin.conf over /srv/emercoind/emercoin.conf (see deploy/docker-compose.yaml).
COPY emercoin.conf.example emercoin.pub changepass.sh ./
RUN cp emercoin.conf.example emercoin.conf
EXPOSE 6661 6662 5335
# Self-sufficient default (the old image defaulted to bash); compose still
# overrides `command:` with the same invocation.
CMD ["emercoind", "-datadir=/srv/emercoind", "-conf=/srv/emercoind/emercoin.conf", "-printtoconsole"]

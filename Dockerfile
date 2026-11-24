ARG BASE_IMAGE=alpine:3.21
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.authors="Chris Romp NZ6F"
LABEL org.opencontainers.image.description="OpenHamClock in a Docker container"
LABEL org.opencontainers.image.source="https://github.com/ChrisRomp/hamclock-docker"

ARG HAMCLOCK_RESOLUTION=1600x960

RUN apk add --no-cache curl make g++ libx11-dev perl linux-headers
WORKDIR /hamclock
COPY ESPHamClock.zip /hamclock/
RUN unzip ESPHamClock.zip
WORKDIR /hamclock/ESPHamClock
RUN make -j4 hamclock-web-${HAMCLOCK_RESOLUTION} && make install

EXPOSE 8080/tcp 8081/tcp 8082/tcp
VOLUME /root/.hamclock
HEALTHCHECK --interval=30s --timeout=10s --start-period=2m --retries=3 CMD curl -f http://localhost:8080/get_sys.txt || exit 1

CMD ["/bin/sh", "-c", "exec /usr/local/bin/hamclock -o -b \"${BACKEND_HOST:-ohb.hamclock.app:80}\""]

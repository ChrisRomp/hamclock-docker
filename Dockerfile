ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.authors="Chris Romp NZ6F"
LABEL org.opencontainers.image.description="HamClock by WBØOEW in a Docker container"
LABEL org.opencontainers.image.source="https://github.com/ChrisRomp/hamclock-docker"

# HamClock supported resolutions are 800x480, 1600x960, 2400x1440 and 3200x1920 as of v3.02
ARG HAMCLOCK_RESOLUTION=1600x960

# Install updates and required packages
RUN apk update && apk upgrade
RUN apk add curl make g++ libx11-dev perl

RUN mkdir /hamclock
WORKDIR /hamclock

# Download HamClock source
# Sort-of following Desktop build steps from https://www.clearskyinstitute.com/ham/HamClock/
RUN curl -O https://www.clearskyinstitute.com/ham/HamClock/ESPHamClock.zip && \
    unzip ESPHamClock.zip
WORKDIR /hamclock/ESPHamClock

# Let's build it
RUN make -j 4 hamclock-web-${HAMCLOCK_RESOLUTION}
RUN make install

USER root

# HamClock REST API
EXPOSE 8080/tcp
# HamClock Web UI
EXPOSE 8081/tcp

# Persist HamClock settings outside of container
VOLUME /root/.hamclock

# Healtheck - call REST API, give it 2 mins to get through setup
HEALTHCHECK --interval=30s --timeout=10s --start-period=2m --retries=3 CMD curl -f http://localhost:8080/get_sys.txt || exit 1

# Start HamClock
WORKDIR /hamclock/ESPHamClock
CMD ["/usr/local/bin/hamclock", "-o"]

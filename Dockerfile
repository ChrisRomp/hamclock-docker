ARG BASE_IMAGE=alpine:3.19
FROM ${BASE_IMAGE}

LABEL org.opencontainers.image.authors="Chris Romp NZ6F"

# HamClock supported resolutions are 800x480, 1600x960, 2400x1440 and 3200x1920 as of v3.02
ARG HAMCLOCK_RESOLUTION=1600x960

# Install updates and required packages
RUN apk update && apk upgrade
RUN apk add curl make g++ libx11-dev perl

RUN mkdir /hamclock
WORKDIR /hamclock

# Download and build HamClock
# Following Desktop build steps from https://www.clearskyinstitute.com/ham/HamClock/
RUN rm -fr ESPHamClock
RUN curl -O https://www.clearskyinstitute.com/ham/HamClock/ESPHamClock.zip && \
    unzip ESPHamClock.zip && \
    cd ESPHamClock && \
    make -j 4 hamclock-web-${HAMCLOCK_RESOLUTION} && \
    make install

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

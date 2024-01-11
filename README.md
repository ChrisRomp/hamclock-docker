# HamClock Docker

A Dockerized build of [HamClock](https://www.clearskyinstitute.com/ham/HamClock/) by Elwood Downey, WB0OEW.

Thanks also to @zeidos for [thier work](https://github.com/zeidlos/hamclock-docker) on a Dockerized version of HamClock. I wanted to take some different approaches, so this is my take on it, but I ran HamClock initially from their image and I thank them for their work.

# Contents
- [Prerequisites](#prerequisites)
- [Running HamClock](#running-hamclock)
    - [Running from the Image](#running-from-the-image)
        - [Docker Compose](#docker-compose)
        - [Docker Run](#docker-run)
    - [Building from Source](#building-from-source)
    - [Display Size](#display-size)
- [Accessing HamClock](#accessing-hamclock)
    - [Web UI](#web-ui)
- [Updating HamClock](#updating-hamclock)

## Prerequisites

You will need to have a computer running [Docker](https://docs.docker.com/get-docker/).

If you're already lost, may I recommend buying a [prebulid HamClock](https://www.veritiumhfclock.com/)?

## Running HamClock

You can run this app by either by pulling the container from the prebuilt container in this repository, or pulling the source and building the container locally. Both approaches are documented here.

### Running from the Image

To run containers with Docker you can use the command line `docker run` argument, or use Docker Compose. I find for most users the Docker Compose option is easiest, as it encapuslates all of the arguments in one place in a nice, repeatable manner. This is also the version that some NAS devices expect, like QNAP.

```yaml
version: "3.8"
services:
  web:
    image: ghcr.io/chrisromp/hamclock-docker:latest
    ports:
      - "8080:8080/tcp"
      - "8081:8081/tcp"
    volumes:
      - data:/root/.hamclock
    restart: unless-stopped

volumes:
  data:
```

> **NOTE:** If your Docker host computer is already hosting an application which is using TCP ports `8080` (used by HamClock's API) or `8081` (used by the HamClock web UI), then you can modify them in the `Dockerfile` using the syntax `HOST:CONTAINER`.
>
> For example, to change the web UI from port `8081` to port `80`, you would change the `8081:8081/tcp` port to `80:8081/tcp`.
>
> See the [Docker Compose documentation](https://docs.docker.com/compose/compose-file/05-services/#ports) for more information.

To run, change to the folder with your `Dockerfile` and `docker-compose.yaml` and execute: `docker compose up -d`

#### Docker Run

If you prefer to use `docker run`, the equivalent commands to the above would be to first create a Docker volume if you have not already:

```sh
docker volume create hamclock
```

Then pass the appropriate arguments to run the container:

```sh
docker run --detach -p 8080:8080 -p 8081:8081 --name hamclock -v hamclock:/root/.hamclock ghcr.io/chrisromp/hamclock-docker:latest
```

### Building from Source

You can clone or download the source code to this repository, or just copy/paste the contents of the `Dockerfile` into a text file on your local machine called `Dockerfile`.

Then you can copy the contents from `docker-compose-source.yaml` into a file called `docker-compose.yaml` in the same directory as your `Dockerfile`.

```yaml
version: "3.8"
services:
  web:
    build:
      context: .
      dockerfile: Dockerfile
      args:
        # HamClock supported resolutions are 800x480, 1600x960, 2400x1440 and 3200x1920 as of v3.02
        HAMCLOCK_RESOLUTION: 1600x960
    ports:
      - "8080:8080/tcp"
      - "8081:8081/tcp"
    volumes:
      - data:/root/.hamclock
    restart: unless-stopped

volumes:
  data:
```

### Display Size

The default Docker image will build HamClock for a screen resolution of 1600x960. If you wish to use another resolution, the Dockerfile takes a build argument which you can specify in docker-compose.yaml. Note that HamClock only supports specific resolutions, so be sure to choose only a supported resolution.

## Accessing HamClock

To access the running HamClock, you will need to know the hostname or IP address of your Docker host computer. That may be in the format of `192.168.x.x` on some networks, or you may be able to access it by the computer name. I will use the hostname `dockerhost` for these examples.

### Web UI

Open a web browser to: `http://dockerhost:8081/live.html`

Likely you will see HamClock running but without your call sign, or if you were fast enough you may see it prompting for setup. If not, leave this browser window open and open another tab/window and enter: `http://dockerhost:8080/restart`. Switch back to the first tab and you should see HamClock prompting you to enter setup. Click your mouse anywhere and configure HamClock.

Please refer to the [HamClock User Guide](https://www.clearskyinstitute.com/ham/HamClock/HamClockKey.pdf) for detailed instructions.

## Updating HamClock

You should be able to update HamClock in place through the web UI. It will prompt you when there's an update available, and you can apply it.

I may occasionally build updated images here, but that will not be the primary way to keep your application up to date.

#!/bin/bash
docker container rm -f YTcastsBot
docker image rm -f ytcasts
docker build --no-cache -t ytcasts . && \
docker run --memory="512m" --cpus="2" --restart=always --detach --name YTcastsBot ytcasts:latest

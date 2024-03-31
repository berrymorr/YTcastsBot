#!/bin/bash
docker container rm -f YTcastsBot
docker image rm -f ytcasts
docker build --no-cache -t ytcasts . && \
docker run --restart=always --detach --name YTcastsBot ytcasts:latest

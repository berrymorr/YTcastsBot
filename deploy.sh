#!/bin/bash
docker container rm -f YTcastsBot
docker image rm -f ytcasts
docker build -t ytcasts . && \
docker run --restart=always --detach --name YTcastsBot ytcasts:latest

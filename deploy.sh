#!/bin/bash
docker container rm -f YTcastsBot
docker image rm -f ytcasts
docker build -t ytcasts . && \
docker run --detach --name YTcastsBot ytcasts:latest

#!/bin/bash
docker container rm -f YTcastsBot
docker image rm -f YTcastsImg
docker build -t YTcastsImg . && \
docker run --detach --name YTcastsBot YTcastsImg:latest

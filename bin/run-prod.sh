#!/bin/sh

exec docker compose -f docker-compose.yml \
    run -it --rm \
    jr-insc /home/runner/docker-run-prod.sh


# fantasy-edge, deployed.
#
# There is no build step and no package install, because there is nothing to
# install: this project is standard library only, Python 3.11+. That constraint
# stops being a slogan and starts paying rent here - the image is the official
# Python base plus a copy of the source, it builds in seconds, and there is no
# lockfile to drift, no wheel to fail to compile, and no transitive dependency
# to audit for a service that holds OAuth refresh tokens.
#
# Build:  docker build -f deploy/Dockerfile -t fantasy-edge .
# Run:    docker run --rm -p 8080:8080 --env-file <YOUR-ENV-FILE> fantasy-edge
#
# Never bake an env file into this image and never pass a secret with --build-arg:
# build args are recorded in the image history and survive in any registry it
# reaches.

FROM python:3.12-slim

# Run as a non-root user. The process holds the token encryption key in its
# environment, so anything that limits what a foothold in the container can
# reach is worth the two lines.
RUN useradd --create-home --uid 10001 fantasy
WORKDIR /app

COPY fantasyedge/ /app/fantasyedge/
COPY config/ /app/config/
COPY README.md /app/README.md

# The database file the read API answers from. Mount a volume here, or bake a
# pulled database in at build time for a read-only deployment.
RUN mkdir -p /app/data && chown -R fantasy:fantasy /app
USER fantasy

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FANTASYEDGE_DB=/app/data/fantasy.db \
    PORT=8080

EXPOSE 8080

# 0.0.0.0 inside a container is the container's own interface, not the host's.
# What is actually exposed is decided by the -p flag and by the platform in
# front of it. `api` holds no credential and calls no provider - see the
# docstring in fantasyedge/api.py - which is what makes it the process that
# faces the internet.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python3 -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:'+os.environ['PORT']+'/api').read()" || exit 1

CMD ["sh", "-c", "python3 -m fantasyedge --db \"$FANTASYEDGE_DB\" api --host 0.0.0.0 --port \"$PORT\""]

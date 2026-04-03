# syntax=docker/dockerfile:1
# Fast worker image — inherits heavy deps from agensus-extract-base.
# Build base first: bash infrastructure/deploy-lambdas.sh --build-base

FROM agensus-extract-base

WORKDIR /app

# Install shared package (lightweight, changes with code).
COPY shared/ /tmp/shared/
RUN --mount=type=cache,id=agensus-extract-uv,target=/root/.cache/uv \
    UV_LINK_MODE=copy uv pip install --system /tmp/shared/

COPY workers/extract/main.py /app/main.py

CMD ["python", "-u", "main.py"]

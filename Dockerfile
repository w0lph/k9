# dog-geroscience-mcp with its prebuilt database baked in (used by Glama's build-and-inspect
# pipeline and by anyone who prefers a container to `uvx`).
#
#   docker build -t dog-geroscience-mcp .
#   docker run -i --rm dog-geroscience-mcp            # MCP over stdio
#
# The database (~90 MB) is downloaded from the Hugging Face Hub at build time so the running
# container needs no network for its offline tools. Override the source with
# --build-arg DOG_GERO_DB_URL=... (any URL serving a SQLite file).
FROM python:3.12-slim

ARG DOG_GERO_DB_URL=https://huggingface.co/datasets/w0lph/dog-geroscience-mcp-data/resolve/main/dog_geroscience.sqlite
ENV DOG_GERO_DATA=/data \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app
COPY mcp/pyproject.toml mcp/README.md /app/mcp/
COPY mcp/src /app/mcp/src
RUN pip install --no-cache-dir /app/mcp

RUN dog-geroscience-mcp fetch-data --url "$DOG_GERO_DB_URL"

ENTRYPOINT ["dog-geroscience-mcp"]
CMD ["serve"]

# andon MCP server, containerised.
#
# The image runs `andon-mcp` over stdio, so any MCP-speaking runtime — Claude
# Desktop/Code, or Glama's in-browser inspector — can call run / inspect / diff
# without a local Python install. Mount the data you want verified read-only:
#
#   docker build -t andon .
#   docker run --rm -i -v "$PWD:/work:ro" -w /work andon
#
# (For the CLI instead of the server, override the entrypoint:
#   docker run --rm -v "$PWD:/work" -w /work --entrypoint andon andon run andon.yaml)
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY . /app

# Install the package with the MCP extra pinned in pyproject.
RUN pip install ".[mcp]"

# Drop privileges: the server only ever reads the files an agent points it at.
RUN useradd --create-home --uid 1000 andon
USER andon

# stdio transport — the runtime speaks MCP over stdin/stdout.
ENTRYPOINT ["andon-mcp"]

# Build in this directory with a minimal context; never COPY the research checkout.
# Record the final image ID and use sha256:<id> in the versioned run configuration.
FROM node:22-bookworm-slim AS codex
ARG CODEX_VERSION
RUN test -n "$CODEX_VERSION" && npm install -g "@openai/codex@$CODEX_VERSION"

FROM python:3.13-slim-bookworm
COPY --from=codex /usr/local/bin/node /usr/local/bin/node
COPY --from=codex /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
COPY requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock
# Runtime invokes explicit commands; no startup script, project files, secrets, or sessions.
WORKDIR /workspace

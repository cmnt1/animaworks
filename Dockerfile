# AnimaWorks Docker image.
#
# Ships the full toolchain needed by animas that act on behalf of a human:
#   * git  - clone/push repositories
#   * gh   - authenticate with GitHub and open pull requests
#   * Node.js 22 + Claude Code CLI - Mode S (Claude Agent SDK) execution
# The slim distro's bundled node is too old for the Claude Code CLI,
# so we install Node 22 from NodeSource, then the CLI via npm.

FROM python:3.12-slim

WORKDIR /app

# System toolchain: git (clone/push), curl, gnupg (keyrings), jq (JSON),
# procps (pgrep/ps) and ca-certificates (https to GitHub / NodeSource).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git curl ca-certificates gnupg jq procps \
    && rm -rf /var/lib/apt/lists/*

# Node.js 22 (NodeSource). The Debian distro node is too old for the
# Claude Code CLI, so use the vendor stream instead.
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# GitHub CLI from the official apt repository (the published keyring is
# already in binary format, so no dearmor step).
RUN mkdir -p -m 755 /etc/apt/keyrings \
    && curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y gh \
    && rm -rf /var/lib/apt/lists/*

# Claude Code CLI. The Python SDK (claude_agent_sdk) does not bundle the
# CLI; without it every Mode S session dies with "stream closed (3 times)".
RUN npm install -g @anthropic-ai/claude-code

# The container runs as root. The Claude Code CLI refuses bypassPermissions
# when run as root, so enable the official flag intended for sandboxed
# (isolated) environments: allows bypassPermissions and exits cleanly as root.
ENV IS_SANDBOX=1

COPY pyproject.toml README.md LICENSE main.py ./
COPY core/ core/
COPY cli/ cli/
COPY server/ server/
COPY templates/ templates/

RUN pip install --no-cache-dir ".[neo4j]"

COPY docker/entrypoint.sh /usr/local/bin/animaworks-entrypoint
RUN chmod +x /usr/local/bin/animaworks-entrypoint

EXPOSE 18500

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:18500/api/system/health')" || exit 1

# --foreground is required: daemonizing makes PID 1 exit, which causes
# Docker to restart the container in a loop.
ENTRYPOINT ["animaworks-entrypoint"]
CMD ["start", "--host", "0.0.0.0", "--port", "18500", "--foreground"]

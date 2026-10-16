# =============================================================================
# SWE-Skills-Bench Base Image: Node.js (ext batch, full rebuild)
# Source of truth: docker/base/Dockerfile.node (the enroot
# node-ext.sqsh was built from it). This copy adds the `dev` user that the
# docker/EKS execution path requires (claude proxy execs as user "dev";
# enroot ignored users via its user namespace, so the original file lacked it).
# =============================================================================
FROM ubuntu:24.04

LABEL maintainer="zhangyiiiiii"
LABEL description="SWE-Skills-Bench Node.js base image with Claude Code"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ---- System packages ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ca-certificates gnupg lsb-release \
    build-essential python3 python3-pip python3-dev \
    # tree-sitter needs gcc for external scanner compilation
    gcc g++ \
    unzip jq openssh-client \
    && rm -rf /var/lib/apt/lists/*

# ---- Node.js 20 LTS ----
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- Yarn (needed for some monorepos like facebook/react) ----
RUN npm install -g yarn

# ---- Python testing essentials ----
RUN pip install --break-system-packages --no-cache-dir \
    pytest pytest-timeout

# ---- Claude Code 2.1.168 (>=2.1.145 required for headless skill loading) ----
RUN npm install -g @anthropic-ai/claude-code@2.1.168

# ---- dev user (uid 1001 matches the other swe-skills-bench bases) ----
RUN useradd -m -u 1001 -s /bin/bash dev \
    && mkdir -p /workspace \
    && chown -R dev:dev /workspace /home/dev

# ---- Workspace ----
WORKDIR /workspace

CMD ["/bin/bash"]

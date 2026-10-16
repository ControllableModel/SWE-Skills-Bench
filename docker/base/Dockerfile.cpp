# =============================================================================
# SWE-Skills-Bench Base Image: C++
# Covers: googletest, catch2 (2 skills)
# =============================================================================
FROM ubuntu:24.04

LABEL maintainer="zhangyiiiiii"
LABEL description="SWE-Skills-Bench C++ base image with Claude Code"

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# ---- System packages ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl wget ca-certificates gnupg lsb-release \
    build-essential cmake g++ \
    python3 python3-pip python3-dev \
    pkg-config \
    unzip jq openssh-client \
    && rm -rf /var/lib/apt/lists/*

# ---- Node.js 20 LTS (for Claude Code) ----
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# ---- Python testing essentials ----
RUN pip install --break-system-packages --no-cache-dir \
    pytest pytest-timeout

# ---- Claude Code 2.1.168 (>=2.1.145 required for headless skill loading) ----
RUN npm install -g @anthropic-ai/claude-code@2.1.168


# ---- Workspace ----
WORKDIR /workspace

CMD ["/bin/bash"]

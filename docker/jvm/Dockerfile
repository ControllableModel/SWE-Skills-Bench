# Thin layer over the published Docker Hub base: adds claude-cli 2.1.168
# (headless skill loading needs >=2.1.145). Mirrors scripts/bake_image.sbatch,
# which produced the local -cli2168.sqsh variants for the enroot path.
FROM zhangyiiiiii/swe-skills-bench-jvm:latest
USER root
RUN npm install -g @anthropic-ai/claude-code@2.1.168 && claude --version

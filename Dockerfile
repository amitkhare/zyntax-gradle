FROM debian:bookworm-slim@sha256:7b140f374b289a7c2befc338f42ebe6441b7ea838a042bbd5acbfca6ec875818

# Host tools only; Android binaries are compiled with the r29 NDK.
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake ninja-build pkg-config ca-certificates curl git \
    python3 unzip xz-utils patch util-linux openjdk-17-jdk-headless && \
    apt-get clean
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
WORKDIR /work
ENTRYPOINT ["bash"]

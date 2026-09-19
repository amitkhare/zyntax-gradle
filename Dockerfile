FROM ghcr.io/termux/package-builder@sha256:374fedda8d2ce7a8ab499735d39329301c4f2f18ea4411b3cf7c93d4668768ab

# Reuse the pinned package builder's GCC, Python and JDK 17/21. Host tools only;
# Android binaries are compiled with the external, checksum-pinned r29 NDK.
# Gradle 9.7.1's source build declares a JDK 25 daemon (not an Android app requirement).
USER root
SHELL ["/bin/bash", "-o", "pipefail", "-c"]
RUN apt-get update && apt-get install -y --no-install-recommends \
    cmake ninja-build openjdk-25-jdk-headless && \
    apt-get clean
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
WORKDIR /work
ENTRYPOINT ["bash"]

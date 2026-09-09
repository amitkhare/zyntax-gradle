FROM zyntax-ndk-r29-builder

# Host tools only; Android binaries are compiled with the r29 NDK.
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jdk-headless && apt-get clean
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64

# Android-host Gradle native components

Source ports of the core native-platform and file-events components used by Gradle 8.14.3. This is **not a Gradle distribution** and does not modify a Wrapper, installed Gradle, or its native extraction cache. The standalone Android component probe passed; integration into a Gradle distribution remains unverified.

## Inputs and build

| Component | Upstream source | Base version |
| --- | --- | --- |
| native-platform | [87f4647e90db6006bf357db0ba7fa29925dcc32e](https://github.com/gradle/native-platform/tree/87f4647e90db6006bf357db0ba7fa29925dcc32e) | 0.22-milestone-28 |
| file-events | [08be35d81f4d6336ce4666122c0c72a97b11a7e9](https://github.com/gradle/gradle-fileevents/tree/08be35d81f4d6336ce4666122c0c72a97b11a7e9) | 0.2.7 |

Prepare exact Git checkouts at `.work/gradle-native/native-platform` and `.work/gradle-native/file-events`. `build-native.sh` verifies both commits, clones fresh isolated working trees, and applies the checked-in patches. Existing source checkouts remain unchanged.

With the existing `zyntax-ndk-r29-builder` image and `zyntax-ndk-r29-work` volume prepared by the root toolchain recipe:

```bash
docker build -f gradle/Dockerfile -t zyntax-gradle-native-builder .
docker run --rm \
  -v zyntax-ndk-r29-work:/work \
  -v "$PWD:/repo:ro" \
  zyntax-gradle-native-builder bash /repo/gradle/build-native.sh
```

The builder adds a Linux host JDK 17. Android output uses official NDK r29 (`29.0.14206865`), Clang 21, `arm64-v8a`, API 24, static libc++, and 16 KB ELF segment alignment. The selected NDK's system JNI headers define the target JNI ABI. No glibc shim, binary rewriting, fake GNU library name, or disabled native check is involved.

Upstream wrappers perform only Java/header/version generation: file-events uses Gradle 8.10.2 `compileJava`; native-platform uses Gradle 7.5 `writeNativeVersionSources`, followed by host `javac --release 8 -h` over its complete Java sources. Java 8 bytecode is suitable for Gradle 8.14.3; this does not try to reproduce native-platform's historical Java 5/6 targets. These build-tool distributions/cache are isolated under `/work/gradle-native/gradle-home`. Builds use two workers, a 1536 MB Gradle heap, and `--no-scan` to prevent build-scan upload. Nothing is published.

Each build prints its fresh `/work/gradle-native/build-*/` directory. `artifacts/` contains the two shared libraries, paired source-built Java component JARs, generated version headers, notices, and a dedicated probe bundle. Those JARs are component outputs, not replacements to copy into stock Gradle.

## Source adaptations and identity

`native-platform-android.patch` limits the `sys/sysctl.h` include to its actual Apple caller and limits GNU `strerror_r` semantics to glibc. Android Bionic uses the existing POSIX branch. Other native code, including file-events' inotify implementation, is unchanged.

The native-platform Java companion is explicitly built for Android aarch64. It validates the JVM reports Linux/aarch64 and selects `android-aarch64`, reusing the existing POSIX/Linux kernel implementations. This is build-declared targeting, not a universal Bionic detector, and it never changes `os.name`. `file-events-android.patch` consumes that one identity and maps it to `aarch64-linux-android`. Native resources use exactly those Android names:

```text
net/rubygrapefruit/platform/android-aarch64/libnative-platform.so
net/rubygrapefruit/platform/aarch64-linux-android/libgradle-fileevents.so
```

Upstream extraction, loading and version checks remain intact. Native-platform's `NativeVersion` is a native-source/build-tool fingerprint, not its Maven version. The upstream generator produces both its C header and Java constant; all Java sources are rebuilt because the constant is inlined in callers. No prebuilt fingerprint is copied over changed sources. File-events likewise uses its upstream version generator for both sides. The probe bundle is intentionally Android-only; publishing a universal Java component or choosing a Gradle distribution remains separate work.

The optional native-platform curses library is outside this core-only build. This work does not claim all Gradle native features or arbitrary Gradle releases are Android-compatible.

## Verification and standalone probe

`verify-native.sh` checks AArch64 shared ELF output, Android-only dynamic dependencies, absence of runtime search paths, generated JNI exports, and the matching native/Java version values. It prints segment alignment and SHA-256 for review. It does not load Android binaries on the Linux build host.

The build on 2026-09-09 used host `javac 17.0.20.1`. Both shared libraries linked with no undefined symbols and needed only `libc.so`, `libm.so`, and `libdl.so`; every LOAD segment had `p_align=0x4000`. The Android ELF identification note records API 24, r29 and build 14206865. The source-generated native-platform fingerprint was `d9b662c5bbedb6418f2007170aa8ed97211391cd673d3d2a6be45c929c7f0dd6`; file-events' generator produced `0.2.7`.

The Android-identified build `build-mxQoeq` produced:

```text
11d8f124dc370a1ff39ce1b7a1d12b6bc1c9a8c8290848fff83bb39a2b22e738  libnative-platform.so
40d596867a25810af8a4d87ef9d7c4aac0e3fc64a3bf1caa2d8d648256ebfd70  libgradle-fileevents.so
```

These identify this build, not a claim of byte-for-byte reproducibility across fresh build paths. Upstream unused-parameter, deprecated-`readdir_r`, and formatting warnings were visible; they were not suppressed.

After explicit device approval, unpack `android-native-probe.tar.gz` into an app-private directory, set `JAVA_HOME` to the app-private JDK, and run:

```bash
bash ./run-probe.bash <app-private-probe-work-directory>
```

The standalone Java probe creates a fresh `run-*` child, uses upstream resource extraction/version checks, verifies native system/filesystem information and stat/readdir, then checks inotify create/remove events and orderly watcher shutdown. It retains its private extraction directory for inspection and never reads or changes a Gradle installation/cache. A `PASS` requires actual JNI calls and filesystem events, not merely a successful Java build.

On 2026-09-09 the explicitly approved USB probe passed in the app-private Android runtime (one test, 1.495 seconds). It loaded the genuine native-platform fingerprint above with identity `android-aarch64`, reported Linux/aarch64 and 220 native filesystem records, and verified file-events `0.2.7` with actual `CREATED`/`REMOVED` events and orderly shutdown. The private harness log is `run-6932603730786287426/output.log`. The tested probe archive SHA-256 is `9319fddd455ea5e9fdb8716196c7f939457b8120184936cc259cc5762be29cf6`. This proves the paired components' exercised JNI and inotify behavior, not Gradle daemon integration, distribution selection, or untested native services.

## Notices

Both component sources are Apache-2.0. Modified source files carry port notices. Artifacts include their original LICENSE files and the official NDK notices for linked runtime code. The dedicated probe includes SLF4J API 1.7.36 and its [MIT license](https://github.com/qos-ch/slf4j/blob/v_1.7.36/LICENSE.txt); its unconfigured logger can print the standard missing-binding notice. No logging binding is used to mask native failures. Review these component artifacts and device results before any distribution decision.

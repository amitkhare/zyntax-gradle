# Zyntax Gradle for Android

An optional, Android-aarch64 source port of **Gradle 8.14.3** and its native-platform, file-events and Jansi components. This standalone repository owns only Gradle tooling; it contains no app or extension SDK source and is not a mirror or support promise for all Gradle versions.

Stock Gradle already built the Android samples and the complete Zyntax APK/AABs with the separately adapted Android build tools. Its desktop native libraries could not load on Android. This port restores the exercised native process, filesystem and terminal services, plus default file watching and snapshot retention on F2FS; it does not replace Gradle's build engine or claim that stock Gradle cannot build APKs.

The [source-built distribution](distribution/README.md) records the exact verified ZIP, source changes and remaining limits. [Jansi](jansi/README.md) has separate source and probe evidence. Runtime selection is explicit: these recipes do not modify a project's Wrapper, installed Gradle, native extraction cache or JVM OS properties. The release destination is [amitkhare/zyntax-gradle](https://github.com/amitkhare/zyntax-gradle/releases).

## Repository and release history

The Gradle-only source history was moved out of the former combined toolchain repository. Current recipes live at this repository's root and use an independent Docker volume. The verified 2026-09-09 ZIP was built **before** that move: its embedded provenance and source companions retain their original `gradle/...` recipe paths. Those immutable bytes and hashes are not rewritten to describe the new layout. The relocated recipes have not been rebuilt or device-tested merely by moving them.

See [NOTICE.md](NOTICE.md) for component source and license coverage.

## Native components: inputs and build

| Component | Upstream source | Base version |
| --- | --- | --- |
| native-platform | [87f4647e90db6006bf357db0ba7fa29925dcc32e](https://github.com/gradle/native-platform/tree/87f4647e90db6006bf357db0ba7fa29925dcc32e) | 0.22-milestone-28 |
| file-events | [08be35d81f4d6336ce4666122c0c72a97b11a7e9](https://github.com/gradle/gradle-fileevents/tree/08be35d81f4d6336ce4666122c0c72a97b11a7e9) | 0.2.7 |

Prepare exact Git checkouts at `/work/gradle-native/native-platform` and `/work/gradle-native/file-events` inside the independent `zyntax-gradle-work` volume. `build-native.sh` verifies both commits, clones fresh isolated working trees, and applies the checked-in patches. Existing source checkouts remain unchanged.

Build the standalone host image from this repository. Supply an externally installed official Linux-host NDK r29 root through `HOST_NDK_R29`; it is mounted read-only at `/ndk`. `NDK_DIR` is required for native build and verification entry points. Neither the NDK source repository, its Docker image nor its work volume is required.

```bash
export HOST_NDK_R29=/absolute/path/to/android-ndk-r29
docker build -t zyntax-gradle-native-builder .
docker run --rm \
  -v zyntax-gradle-work:/work \
  -v "$PWD:/repo:ro" \
  -v "$HOST_NDK_R29:/ndk:ro" \
  -e NDK_DIR=/ndk -e SOURCE_DIR=/work/gradle-native \
  zyntax-gradle-native-builder /repo/build-native.sh
```

The standalone builder supplies Linux host JDK 17, CMake and Ninja. Android output uses the external official NDK r29 (`29.0.14206865`), Clang 21, `arm64-v8a`, API 24, static libc++, and 16 KB ELF segment alignment. The selected NDK's system JNI headers define the target JNI ABI. No glibc shim, binary rewriting, fake GNU library name, or disabled native check is involved.

Upstream wrappers perform only Java/header/version generation: file-events uses Gradle 8.10.2 `compileJava`; native-platform uses Gradle 7.5 `writeNativeVersionSources`, followed by host `javac --release 8 -h` over its complete Java sources. Java 8 bytecode is suitable for Gradle 8.14.3; this does not try to reproduce native-platform's historical Java 5/6 targets. These build-tool distributions/cache are isolated under `/work/gradle-native/gradle-home`. Builds use two workers, a 1536 MB Gradle heap, and `--no-scan` to prevent build-scan upload. The build recipes do not publish artifacts.

Each build prints its fresh `/work/gradle-native/build-*/` directory. `artifacts/` contains three shared libraries, paired source-built Java component JARs with their own Android native resources, Java source JARs, generated version headers, notices, and a dedicated probe bundle. Keeping resources in each component JAR also supports Gradle's isolated test-worker classloader. Those JARs are component outputs, not replacements to copy into stock Gradle.

## Source adaptations and identity

`native-platform-android.patch` limits the `sys/sysctl.h` include to its actual Apple caller and limits GNU `strerror_r` semantics to glibc. Android Bionic uses the existing POSIX branch. Other native code, including file-events' inotify implementation, is unchanged.

The native-platform Java companion is explicitly built for Android aarch64. It validates the JVM reports Linux/aarch64 and selects `android-aarch64`, reusing the existing POSIX/Linux kernel implementations. This is build-declared targeting, not a universal Bionic detector, and it never changes `os.name`. `file-events-android.patch` consumes that one identity and maps it to `aarch64-linux-android`. Native resources use exactly those Android names:

```text
net/rubygrapefruit/platform/android-aarch64/libnative-platform.so
net/rubygrapefruit/platform/android-aarch64/libnative-platform-curses.so
net/rubygrapefruit/platform/aarch64-linux-android/libgradle-fileevents.so
```

Upstream extraction, loading and version checks remain intact. Native-platform's `NativeVersion` is a native-source/build-tool fingerprint, not its Maven version. The upstream generator produces both its C header and Java constant; all Java sources are rebuilt because the constant is inlined in callers. No prebuilt fingerprint is copied over changed sources. File-events likewise uses its upstream version generator for both sides. The probe bundle is intentionally Android-only; the qualified distribution uses these same paired components rather than universal Java companions.

The curses component is also source-built for `android-aarch64`, using the official Android `ncurses` package checksum-pinned in [ncurses-input.tsv](ncurses-input.tsv). Its headers and library are extracted only as build inputs; the package is not modified or bundled. The resulting JNI library depends on the package's genuine `libncursesw.so.6` SONAME. Install `ncurses` in the same app-private terminal runtime and supply its terminfo directory through `TERMINFO` (normally `$PREFIX/share/terminfo`). This is an explicit terminal-package dependency, not a standalone managed-runtime bundle. No GNU ncurses5/6 candidate names or desktop terminfo paths are used by the Android selector. This work does not claim all Gradle native features or arbitrary Gradle releases are Android-compatible.

## Verification and standalone probe

`verify-native.sh` checks AArch64 shared ELF output, Android-only dynamic dependencies, absence of runtime search paths, generated JNI exports, and the matching native/Java version values. It prints segment alignment and SHA-256 for review. It does not load Android binaries on the Linux build host.

The build on 2026-09-09 used host `javac 17.0.20.1`. Both shared libraries linked with no undefined symbols and needed only `libc.so`, `libm.so`, and `libdl.so`; every LOAD segment had `p_align=0x4000`. The Android ELF identification note records API 24, r29 and build 14206865. The source-generated native-platform fingerprint was `d9b662c5bbedb6418f2007170aa8ed97211391cd673d3d2a6be45c929c7f0dd6`; file-events' generator produced `0.2.7`.

The initial core-only Android build `build-mxQoeq` produced:

```text
11d8f124dc370a1ff39ce1b7a1d12b6bc1c9a8c8290848fff83bb39a2b22e738  libnative-platform.so
40d596867a25810af8a4d87ef9d7c4aac0e3fc64a3bf1caa2d8d648256ebfd70  libgradle-fileevents.so
```

These identify this build, not a claim of byte-for-byte reproducibility across fresh build paths. Upstream unused-parameter, deprecated-`readdir_r`, and formatting warnings were visible; they were not suppressed.

The terminal build `build-C8tGz6` also passed host compilation, generated JNI/version checks and embedded-resource hash checks. Its `libnative-platform-curses.so` SHA-256 is `11d331a0a1430415d60a91aeaeb40ff662c794b0497ddd3bf45c061da76a7228`; its only non-system dependency is the declared `libncursesw.so.6`. All three JNI libraries have 16 KB LOAD alignment and no RPATH/RUNPATH. The terminal probe archive SHA-256 is `989f70ac9504a86545a5aa7c7effcb751fdd741fb03af884e9270d6af8f2186d`. This build consumes ncurses `6.6.20260307+really6.5.20250830`, package SHA-256 `f44bbfdc3d42ec0217bffa978309390e59cea5a48a9a83226d4a496c42ad0b99`; it preserves the source-generated native-platform/file-events versions above.

After explicit device approval, unpack `android-native-probe.tar.gz` into an app-private directory, set `JAVA_HOME` to the app-private JDK and `TERMINFO` to the installed app-private ncurses database, then run inside a PTY with a nonzero window size and matching `TERM` (such as `xterm-256color`):

```bash
bash ./run-probe.bash <app-private-probe-work-directory>
```

The standalone Java probe creates a fresh `run-*` child, uses upstream resource extraction/version checks, verifies curses/terminfo capabilities and PTY size, native system/filesystem information and stat/readdir, then checks inotify create/remove events and orderly watcher shutdown. It retains its private extraction directory for inspection and never reads or changes a Gradle installation/cache. A `PASS` requires actual JNI calls and filesystem events, not merely a successful Java build. A pipe-only harness cannot validate the terminal probe; use an app-private PTY provider.

On 2026-09-09 the terminal probe passed within an explicitly approved combined USB run (one instrumentation test, 4.154 seconds). It verified the genuine native-platform fingerprint and `android-aarch64` identity, 220 filesystem records, matching curses version, real `xterm-256color` terminfo capabilities (color, text attributes and cursor motion), an 80x24 PTY with terminal stdin, and inotify `CREATED`/`REMOVED` events plus watcher shutdown. The private harness log is `run-8565402705635806309/output.log`. Read-only mount inspection identified the app-private project filesystem as F2FS. This component result alone does **not** establish Gradle VFS retention; the subsequent two-build distribution result is recorded separately above.

On 2026-09-09 the initial core-only USB probe passed in the app-private Android runtime (one test, 1.495 seconds). It loaded the genuine native-platform fingerprint above with identity `android-aarch64`, reported Linux/aarch64 and 220 native filesystem records, and verified file-events `0.2.7` with actual `CREATED`/`REMOVED` events and orderly shutdown. The private harness log is `run-6932603730786287426/output.log`. The tested probe archive SHA-256 is `9319fddd455ea5e9fdb8716196c7f939457b8120184936cc259cc5762be29cf6`. This proves the paired components' exercised JNI and inotify behavior, not Gradle daemon integration, distribution selection, or untested native services.

## Notices

Both component sources are Apache-2.0. Modified source files carry port notices. Artifacts include their original LICENSE files and the official NDK notices for linked runtime code. The dedicated probe includes SLF4J API 1.7.36 and its [MIT license](https://github.com/qos-ch/slf4j/blob/v_1.7.36/LICENSE.txt); its unconfigured logger can print the standard missing-binding notice. No logging binding is used to mask native failures. Review these component artifacts and device results before any distribution decision.

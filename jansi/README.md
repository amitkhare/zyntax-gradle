# Android aarch64 Jansi

Source build of `app.zyntax.gradle:jansi:1.18-zyntax.1` for the Android-host Gradle
fork. All shipped Java classes are compiled from Jansi 1.18, Jansi Native 1.8 and
HawtJNI runtime 1.17 sources. One Java 8-compatible JAR embeds the Android aarch64
JNI library; it has no separate Maven runtime dependencies. No stock JAR is edited.

## Build

Use the standalone repository-root `zyntax-gradle-native-builder` image (JDK 17,
CMake, Ninja, Git and curl) and independent `zyntax-gradle-work` volume. Supply
an externally installed official Linux-host NDK r29 root, revision
`29.0.14206865`, mounted read-only at `/ndk` with `NDK_DIR=/ndk`. No NDK repository,
base image or shared NDK work volume is required.

Prepare the three upstream checkouts once, inside that volume:

```bash
mkdir -p /work/gradle-native/jansi
cd /work/gradle-native/jansi
git clone --branch jansi-project-1.18 --depth 1 https://github.com/fusesource/jansi.git source
git clone --branch jansi-native-1.8 --depth 1 https://github.com/fusesource/jansi-native.git native-source
git clone --branch hawtjni-project-1.17 --depth 1 https://github.com/fusesource/hawtjni.git hawtjni-source
```

The build validates each exact commit in `SOURCE-PROVENANCE.properties`, creates
a fresh isolated source/build directory, applies the checked-in source patches,
and verifies the pinned host-only HawtJNI generator's SHA-256. Generator classes
are not shipped. Run from the repository root in PowerShell, setting the external
NDK path explicitly:

```powershell
$env:HOST_NDK_R29 = 'D:/path/to/android-ndk-r29'
docker run --rm -v zyntax-gradle-work:/work -v "${PWD}:/repo:ro" -v "${env:HOST_NDK_R29}:/ndk:ro" -e NDK_DIR=/ndk zyntax-gradle-native-builder /repo/jansi/build.sh
```

The image already has a Bash entrypoint. `NDK_DIR` is mandatory for the build and
native verification scripts. `WORK_DIR`, `SOURCE_DIR`, `JAVA_HOME` and `BUILD_JOBS`
can be set explicitly; their defaults are in `build.sh`.
Keep checkouts and outputs in the volume or the ignored `.work/` directory.

Each successful build prints its fresh `/work/gradle-native/jansi/build-*/artifacts`
directory and SHA-256 hashes. Outputs are:

- `java/jansi-1.18-zyntax.1.jar`: complete source-built runtime and Android resource.
- `java/jansi-1.18-zyntax.1-sources.jar`: corresponding Java, JNI, C helper, recipes
  and notices.
- `lib/libjansi.so`: identical native library to the JAR resource.
- `probe/jansi-probe.jar`: separate verification programs, not a runtime dependency.
- `licenses/`, `PORT-NOTICE.txt`, `SOURCE-PROVENANCE.properties`: distribution notices
  and source/tool identity, also embedded in both runtime and source JARs.

## Android source adaptations

The component declares `android-aarch64`; incompatible OS/architecture/bitness
values are rejected. It does not change JVM system properties or detect every
possible Bionic installation. An absolute `-Dlibrary.jansi.path=<directory>` is
authoritative: only that directory's `libjansi.so` is loaded and failure propagates.
Without that property, the upstream extraction mechanism selects exactly
`META-INF/native/android-aarch64/libjansi.so` and the explicit JVM temporary
directory. It never searches `java.library.path`, other platforms or the user's
home. Native-file permissions use Java NIO without launching a subprocess.
Original extraction strategies and optional version naming remain intact.

The JNI declarations preserve Bionic's `c_line` and use POSIX speed accessors
instead of glibc-only struct members. HawtJNI 1.17, matching the bundled runtime,
supports these non-member accessors. JNI is regenerated, not hand-edited. The
original 32-byte Java control-character buffer is retained, while generated JNI
copies the target struct's actual 19-byte array; configure-time assertions check
both bounds. The upstream C runtime helper is compiled from its patched source
tree with Android's `AttachCurrentThread(JNIEnv**)` signature.

The native library targets Android API 24 / arm64-v8a and uses 16 KB ELF LOAD
alignment, target-sysroot feature checks, hidden internal symbols and no runtime
search path. The port retains upstream copyright headers, Apache-2.0 and EPL-1.0
texts, original HawtJNI notices and NDK notices.

## Verification boundary

`build.sh` runs only host checks: real Android-header compile/link checks, ELF
architecture/alignment/dependencies, generated CLibrary JNI exports, JAR resource
and version identity, pure Java ANSI behavior, and rejection of the actual
incompatible x86_64 build host. It does not change OS properties or execute the
Android library on the host. Compiler pointer-type mismatches are errors.

Android execution is a separate, explicitly authorized step. In an app-private
runtime and real PTY, with an app-private writable/executable `java.io.tmpdir`,
run `JansiProbe` with the runtime and probe JARs on the classpath. It checks actual
terminal dimensions, `isatty`, `openpty`, `ioctl`, `ttyname_r` and a complete
termios round trip. Its two PTY descriptors close on the short-lived JVM's exit.
Repeat in a fresh JVM with an explicit missing `library.jansi.path` to verify
failure does not fall back to the embedded resource. Device success is not
implied by a successful host build, nor does this component alone establish
complete Gradle compatibility.

### Verified Android execution

The following result predates the move to this standalone repository. Its
artifacts, source JAR and hashes remain unchanged; embedded historical recipe
paths are provenance, not a dependency on the former repository. Relocation alone
does not establish a new build or device result.

Build `build-SVCXGV` passed the combined USB native-platform/curses/Jansi probe
(`run-8565402705635806309/output.log`, `OK (1 test)`, 4.154 seconds). The exact
runtime/probe JAR pair loaded the embedded Android resource in a real 80x24 PTY;
`openpty` produced the requested 33x101 PTY, and `ioctl`, `ttyname` and the termios
round trip passed. Native `WinSize`/`Termios` sizes were 8/36 bytes.

A separate JVM with an absolute missing `library.jansi.path` failed with an
`UnsatisfiedLinkError` naming that missing library. Its empty temporary directory
confirmed no embedded-resource extraction fallback. No OS properties were spoofed.

Verified SHA-256 identities (artifacts remain in ignored build storage):

```text
runtime JAR  35afcbce406677c1cb9016be8b557193ff63ab5c828a99098b4d6e2f333dfb9f
probe JAR    a49d9eda17a082f8bc76fcc2ffab78668a567574de63d4e6dc043e89cfaafef2
libjansi.so  c48ce4e05798f610fee516c9861a141f7034d562d392bcfaaa9c051e2b1c270e
```

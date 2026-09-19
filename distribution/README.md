# Android-qualified Gradle distribution

The existing Gradle 8.14.3 release passed source compilation, archive checks and
focused Android client/daemon/worker/VFS integration; its immutable evidence is
below. Current recipes build the exact commits in `targets.json` with upstream's
`:distributions-full:binDistributionZip` task. The new release-identity contract
and additional versions are not qualified merely by preparing their recipes.
Nothing here modifies an installed Gradle, its extraction cache, a project's
wrapper, or app/SDK source.

## Additional exact source targets

`targets.json` also records exact source recipes for 8.11.1, 9.3.1,
9.4.1, 9.6.0 and 9.7.1. Select an exact target with `GRADLE_VERSION`; 8.14.3
remains the default. Gradle 9 targets use one shared file-watching patch plus a
small version-specific dependency/packaging patch. Upstream changes such as
9.7's probe-file cleanup are retained. The 8.11.1 recipe uses milestone 26's
original file-events module/API and retains its original watch-logging contract.
Its corrected native component and complete 8.11.1.1 distribution passed the
focused Android checks below, as did the 9.3.1.1, 9.4.1.1, 9.6.0.1 and 9.7.1.1 candidates. These
new versions are not published yet; matching AGP/APK qualification remains
pending. No version is substituted.

The recipe reads source/bootstrap pins and component versions from the manifest.
It combines only the declared patch series, validates the cached commit rather
than requiring that cache's HEAD to change, and records the exact target and
combined patch in the output notices. Source-input and strict dependency
verification remain enabled. New target names do not imply published support.
The shared Gradle 9 native components and Jansi 2.4.2 have passed source compilation
and host ELF/JNI checks. The 9.7.1 candidate passed complete source compilation,
upstream license generation and ZIP/receipt/component verification in 10m19s
(978 tasks). Its candidate SHA-256 is
`6fae884f92e9be48fc696a94ee308bad6fac0c88824455a2c31da2a107b0bfc4`
(151,523,711 bytes); it is not published. Android runtime checks and release
identity qualification were pending for that initial candidate. It used a
prerelease runtime qualifier and remains historical source-build evidence, not
a final release. The stable 9.7.1.1 candidate is qualified separately below.

### Additional qualified candidate: Gradle 8.11.1.1

The source build completed 837 tasks in 20m06s using its required cached JDK 11
and recipe commit `15d368f`. Its exact archive is
`gradle-8.11.1-android-1-20260919193417+0000-bin.zip`, 136,143,461 bytes, SHA-256
`0adb8575da81ffb372aec8980e0df91aa4e4d27a31691cdbb4ca1fb5faf2e4e6`.
Archive/component/provenance checks passed before device use.

On 2026-09-20 this unchanged archive passed the complete Android
client/daemon/worker/F2FS fixture in 67.309 seconds using Dev's already-installed
JDK 21. Both builds reused daemon PID 21318; two workers passed genuine JNI,
default-mode watching retained unchanged snapshots and invalidated changed
inputs, and the isolated daemon stopped normally. Cached test dependencies were
reused; no package installation, UI navigation, Full-app/project modification,
app/core/extension-SDK or bootstrap change occurred.

Private evidence: `gradle-native-integration-ta7xftvs/evidence/result.json` under
the Dev projects directory; harness `run-4182510064522401491/output.log`.
Matching AGP/APK qualification and publication remain pending. These checks
establish the exercised native services, not arbitrary project compatibility.

### Additional qualified candidate: Gradle 9.3.1.1

The source build completed 868 tasks in 19m37s using the required JDK 17 and
recipe commit `15d368f`. Its verified archive is
`gradle-9.3.1-android-1-20260919193458+0000-bin.zip`, 137,098,066 bytes, SHA-256
`df3b27b72f5411eb32f5141394ac812a7268ba0b2a87efde19fcb627996a062f`.

On 2026-09-20 this unchanged archive passed the complete Android
client/daemon/worker/F2FS fixture in 66.905 seconds using Dev's existing JDK 21.
Both builds reused daemon PID 24208; two workers passed genuine JNI and default
watching retained unchanged snapshots and invalidated changed inputs. All fixture
dependencies were reused from cache; no additional package installation or app
change was needed. Private evidence: `gradle-native-integration-c7tb79kj/evidence`
under Dev's projects directory; harness `run-7812940193724266485/output.log`.
Matching AGP/APK qualification and publication remain pending.

### Additional qualified candidate: Gradle 9.4.1.1

The original 6-GiB source-build container reached its aggregate memory limit;
the preserved attempt has a Docker OOM event, not a source or JVM-heap failure.
One normal resume at 7 GiB with the same source, JVM options and one worker
completed in 6m14s (692 tasks, including 336 up-to-date). No recipe, source
policy or compiled input was changed to accommodate the host resource limit.
Recipe commit `15d368f` produced
`gradle-9.4.1-android-1-20260919193529+0000-bin.zip`, 137,966,641 bytes, SHA-256
`bf1dad169d6e5931053c9ee9836da7a13898c94a543bbd5e8bf1b869081bf062`.

On 2026-09-20 the unchanged verified archive passed the complete Android
client/daemon/worker/F2FS fixture in 64.996 seconds with existing Dev JDK 21.
Both builds reused daemon PID 26362, both workers passed JNI, and default
watching retained unchanged snapshots and invalidated changed inputs.
Private evidence: `gradle-native-integration-plbm9ohd/evidence` under Dev's
projects directory; harness `run-864678833077280987/output.log`. No extra
packages, UI navigation, Full-app/project, app/core/SDK or bootstrap change.
Matching AGP/APK qualification and publication remain pending.

### Additional qualified candidate: Gradle 9.6.0.1

On 2026-09-20 the complete source-built 9.6.0.1 candidate passed the focused
Android client/daemon/worker/F2FS fixture (two builds, 58.285 seconds). Both builds
used daemon PID 12133; separate workers exercised paired native-platform JNI,
and default-mode file watching retained unchanged snapshots and detected changed
inputs. The exact archive is
`gradle-9.6.0-android-1-20260919181947+0000-bin.zip`, 140,772,538 bytes, SHA-256
`7d292b904753e09b9f3d840ab1265315aa54709deb3fe9253ee3812e9e41b8e4`.
Dev evidence: `gradle-native-integration-mxwvv9m0/evidence/result.json` under the
app-private projects directory; harness log `run-5488394577549155126/output.log`.
The fixture preserves upstream Gradle 9's NIO metadata/JDK permission services;
it does not substitute old native-backed metadata behavior. This candidate is
not yet published; matching AGP/native-build qualification remains separate.

The normal distribution task subsequently regenerated its unpublished archive
to include the native components' original source-provenance properties beside
their notice. The preserved, Android-tested ZIP was not modified. Comparing both
archives verified all 699 existing entries byte-for-byte with identical modes;
the only addition is that provenance file. The corrected candidate is
140,773,041 bytes, SHA-256
`6f208ff6debd4b9a36fc8a6b3b2c814edcd1f9e80aa27ad7d1434721f2f8885a`.
No runtime behavior changed or additional Android run was needed for this
notice-only packaging correction.

### Additional qualified candidate: Gradle 9.7.1.1

The exact source build passed in 9m32s (978 executed tasks), using required
cached JDK 25, one worker and a 7-GiB container. Recipe commit `15d368f` produced
`gradle-9.7.1-android-1-20260919193557+0000-bin.zip`, 151,526,232 bytes, SHA-256
`c6f309b1e21ca91a7620477b0c80dd80bbbadaa2ffab77aa6e00fd767324aa9b`.
Archive, runtime receipt, component and notice verification passed.

On 2026-09-20 the unchanged archive passed the complete Android
client/daemon/worker/F2FS fixture in 66.829 seconds using existing Dev JDK 21.
Both builds reused daemon PID 28307; both workers passed JNI and default
watching retained unchanged snapshots and invalidated changed inputs. Its
source-build JDK 25 requirement is not an Android runtime requirement.
Private evidence: `gradle-native-integration-83vnwfkw/evidence` under Dev's
projects directory; harness `run-3848025695997105904/output.log`.
No additional packages, UI navigation, Full-app/project, core/SDK or bootstrap
change. Matching AGP/APK qualification and publication remain pending.

### Runtime identity and archive identity

New stable ports use a fourth numeric component, for example `9.6.0.1` means
upstream `9.6.0`, Android port revision `1`. Gradle's native version parser supports
this format: it sorts above `9.6.0` and below `9.6.1`, passes an exact-minimum AGP
check, and keeps daemon/version caches distinct from stock Gradle and other ports.
The declared source patch changes `version.txt`; `finalRelease=true` produces a
non-snapshot receipt. No version-check override or runtime version spoof is used.
Archive/root labels retain `9.6.0-android-1-<timestamp>` independently, and notices
record both identities, source commit, complete patch and component checksums.

The qualified historical 8.14.3 port remains unchanged and reusable. Its future
source recipe is revision 2 (`8.14.3.2`); this does not relabel or republish the
existing revision-1 ZIP. A new recipe is not a new qualification result.
Explicit Wrapper generation for a custom port requires its published distribution
URL and checksum; an Android port is not hosted at `services.gradle.org`.
These build recipes and the launcher never invoke Wrapper generation in a user's
project or modify that project's distribution URL.

Build dependency caches are shared across these serial source builds at
`/work/gradle-native/gradle-home`; `BUILD_GRADLE_USER_HOME` can select another
explicit build cache. Per-target source/output directories and timestamps remain
separate. Already downloaded tools are reused, not downloaded per target.

The manifest also declares the exact upstream source-build JDK: 8.11.1 uses 11,
8.14.3, 9.3.1, 9.4.1 and 9.6.0 use 17, and 9.7.1 uses 25. The build validates
both `java` and `javac` before staging components or invoking Gradle. Set
`SOURCE_BUILD_JAVA_HOME` to an explicit complete JDK when `JAVA_HOME` or the
builder's JDK 17 default does not match. The recipe does not bypass upstream's
own Java-version check or silently select another installed JDK. Source-only
`prepare` mode does not require the target JDK.

Build the standalone `zyntax-gradle-native-builder` image from the repository-root
Dockerfile (Bash entrypoint, host JDK 17) and use the independent
`zyntax-gradle-work` volume. Supply completed, verified component artifact
directories from the root native recipe and `jansi/build.sh`. Those component
builds consume an externally supplied NDK r29; distribution assembly does not
require an NDK repository, image or filesystem.

Prepare the exact [upstream Gradle Git revision](https://github.com/gradle/gradle/tree/e5ee1df3d88b8ca3a8074787a94f373e3090e1db)
at `/work/gradle-native/gradle` inside that volume; the pinned Git objects are
the source input. `SOURCE_INPUT` selects that cache without changing its HEAD.
Set `NATIVE_ARTIFACTS` and `JANSI_ARTIFACTS` to the artifact directories printed
by your completed component builds, not historical build-directory names.

```bash
docker run --rm \
  -v zyntax-gradle-work:/work -v "$PWD:/repo:ro" \
  -e SOURCE_INPUT=/work/gradle-native/gradle \
  -e NATIVE_ARTIFACTS -e JANSI_ARTIFACTS \
  zyntax-gradle-native-builder /repo/distribution/build.sh
```

`prepare` as the script argument only clones and patches the source. A fresh
Linux checkout lives under
`/work/gradle-native/distribution/8.14.3-android.2/source`. Rerunning the command
resumes that stage with the shared build cache and its recorded timestamp. Changed
patch/component inputs require a fresh `WORK_DIR` under that distribution directory.
No old stage is deleted automatically.
Before compilation, a temporary Git index/object store reconstructs the pinned
patch, permitting modified files with unchanged modes and declared regular-file
additions. Exact file bytes and the two wrapper/verification additions are checked;
unrelated tracked, staged or nonignored untracked inputs, symlinks and mode changes
are rejected without mutating the source index/worktree. Run
`python3 distribution/test_stage.py` for the small disposable-repository
guard checks; these do not run Gradle or native/device tests.

Upstream's build wrapper is Gradle 8.14.2. Its binary ZIP SHA-256 is pinned to
`7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999`, verified from
the [official checksum](https://services.gradle.org/distributions/gradle-8.14.2-bin.zip.sha256).
The source wrapper receives that checksum before execution. Build limits default
to two workers and a 2 GB Gradle heap; use `BUILD_WORKERS=1` on memory-constrained
hosts. Build scans and build cache are disabled.
Configuration cache follows the exact upstream build's settings, including the
Isolated Projects requirement in 9.7. Resumes reuse locally compiled task outputs and the
shared downloaded dependencies. `RERUN_TASKS=true` requests a full local task rebuild when needed.
The restricted repository uses one required, recipe-exported
`ZYNTAX_GRADLE_COMPONENTS_REPOSITORY` environment provider, including in Gradle's
synthetic precompiled-plugin accessor projects, which do not inherit command-line
project properties.

The restricted local Maven group `app.zyntax.gradle` contains source-built
`native-platform:0.22-milestone-28-zyntax.1`,
`gradle-fileevents:0.2.7-zyntax.1`, and `jansi:1.18-zyntax.1`, with sources and
notices. File-events depends on that exact native-platform and SLF4J 1.7.36.
Generated component POMs declare their source licenses, including the EPL-1.0
notices on HawtJNI files bundled in Jansi 1.18. New Gradle license generation reads
this metadata directly; no upstream license check is disabled or overridden.
The native-platform artifact basename stays unchanged for Gradle worker lookup.
Android native resources stay inside their owning component JARs.
The existing dependency convention declares the original Jansi coordinates replaced
by the owned module, so transitive compile-only Zinc/JLine requests share Gradle's
single strict Jansi 1.18 selection rather than introducing a second implementation.

Staging records exact component hashes and adds only those local JAR/source/POM
SHA-256 entries to the pristine upstream verification XML. Existing metadata,
signature policy, keys and trust rules remain unchanged; strict verification is
explicitly retained. No unrelated dependency is automatically trusted.

The small source patch changes component coordinates/versions and the restricted
repository, resolves Jansi through the native component's declared Android identity,
and assigns a distinct branded ZIP/root through the source packaging API. Runtime
identity is the declared numeric downstream version, using the supported
`finalRelease` and recorded `buildTimestamp` inputs. This is not a stock ZIP with
replaced libraries or an OS spoof.

Default watching includes F2FS and resolves support at the nearest mounted file
system. Supported nested mounts remain eligible beneath unsupported ancestors;
unsupported or remote nested mounts do not inherit support. Ambiguous mount points
exclude their whole subtree without disabling unrelated locations. Mount changes
invalidate affected snapshots through the existing watcher lifecycle. Cleanup
retains original supported snapshots, not complete hashes of filtered directories,
and discards metadata that cannot be trusted. No application paths are hardcoded.

Native component notices, exact source patch, base revision, build inputs and
component hash manifest accompany the distribution through its source packaging
specification. The upstream commit identifies the base, not unmodified Gradle.
Native source-provenance properties are copied unchanged beside their port notice;
they retain the source and patch hashes from the actual component build.
The binary ZIP does not contain component source JARs; these are separate release
companions, with coverage described in [NOTICE.md](../NOTICE.md).
The reusable [headless qualification fixture](tests/android-native/README.md)
checks new ports' actual client/daemon/worker JNI and two-build VFS behavior.
Its host-only contract checks are not Android runtime qualification.
Ncurses remains an explicit app-private terminal dependency, not a
bundled system library. Combined native-component device probes passed, including
real Jansi PTY/termios operations.

## Verified pre-move release

The 2026-09-09 source build produced
`gradle-8.14.3-android-1-20260909081124+0000-bin.zip` (137,611,046 bytes), SHA-256
`8d36a689a31f571b04af9518e132ee5147f56920dd0d90a5e476e8f9b8abcc87`.
`verify.py` checked its qualified root/runtime receipt, all three exact component
JARs with no extra native variants, and every packaged notice/provenance file.
It emits `verification.json` with the exact version, ZIP name, size and hash.
The source build passed in 10m 2s, including 40 focused mount-policy, detector,
VFS and snapshot-retention cases. The source patch SHA-256 is
`e57f5c288fef371c8210f7e65367fb3c74ee1c53185da5fdf7a69e0be88a3b47`.
The corrected Scala compile-only graph also resolved its Zinc/JLine Jansi request
to the single owned 1.18 module. These checks do not claim reproducible ZIP bytes
across fresh build paths.

This immutable release was built before the Gradle-only history moved to
`amitkhare/zyntax-gradle`. Its receipt deliberately retains the original
`gradle/distribution/build.sh` recipe path; embedded patches, component sources
and checksums are not rewritten. The current root-layout recipes and independent
build environment are not claimed to have produced those already-verified bytes.
Releases belong to [this repository](https://github.com/amitkhare/zyntax-gradle/releases),
not the NDK repository.

The unchanged verified ZIP passed the focused USB integration check on 2026-09-09
(68.531 seconds; private log `run-7096449322066847556/output.log`). It exercised
the selected client's native core/curses under a real PTY, daemon native process
and file-metadata services, and ordinary worker JNI in both builds. In evaluated
`WatchMode.DEFAULT`, with no `--watch-fs` flag, the same daemon retained unchanged
snapshots and invalidated changed inputs across two builds on F2FS. The unchanged
task remained up-to-date and the changed output updated. This exercised the real
nested Android mount table, including unrelated duplicate mounts. The isolated
test daemon stopped normally; user projects, settings and daemons were untouched.
Gradle's Jansi runtime-wrapper invocation subsequently passed the focused check
below. The result covers
this qualified distribution and exercised services, not arbitrary Gradle releases
or all native features. The build recipe does not publish artifacts.

The unchanged distribution and source companions are published in the dedicated
[Gradle release](https://github.com/amitkhare/zyntax-gradle/releases/tag/gradle-8.14.3-android-1-20260909081124).
All seven uploaded assets match their verified local sizes and SHA-256 hashes.
The former NDK-repository release and tag were removed after verification.

### Jansi wrapper check

`GradleJansiProbe.java` calls the selected distribution's package-private console
wrapper directly from the same Java package. Compile it with `javac --release 17
-cp "$GRADLE_HOME/lib/*" -d "$PROBE_CLASSES" GradleJansiProbe.java`; only the probe
class is generated, and no Gradle library is replaced or added. In a fresh JVM
inside an app-private PTY with nonzero dimensions, run:

```bash
TERM=screen "$JAVA_HOME/bin/java" -cp "$PROBE_CLASSES:$GRADLE_HOME/lib/*" \
  org.gradle.internal.logging.sink.GradleJansiProbe "$PROBE_WORK"
```

`PROBE_WORK` must be an existing app-private directory; the probe creates one
fresh child and leaves ordinary Gradle caches untouched. `screen` exercises the
wrapper's native `isatty` branch rather than its xterm shortcut. The check covers
Gradle's Android resource selection/extraction, exact resource bytes, real JNI
PTY detection/window size, and preserved ANSI with reset on stream close.
It does not run a build or claim interactive rich-console rendering.

On 9 September 2026 this check passed using the release downloaded by the
official Wrapper into the normal app-home cache. It verified Android library
selection/extraction, real JNI and an 80x24 PTY, then the actual console wrapper's
ANSI preservation/reset behavior. The combined download/cache/local-selection
and Jansi invocation took 38.408 seconds, one USB instrumentation test.
Private evidence: `run-1004036333415454146/output.log`,
`gradle-delivery.zBzGur/jansi.log`. No build or app installation was repeated.

# Android-qualified Gradle distribution

This recipe source-builds exact Gradle 8.14.3 commit
`e5ee1df3d88b8ca3a8074787a94f373e3090e1db`, using the upstream
`:distributions-full:binDistributionZip` task. Host source compilation and archive
verification passed; full Android Gradle integration is not yet verified.
Nothing here modifies an installed Gradle, its extraction cache, a project's
wrapper, or app/SDK source.

Use the existing `zyntax-gradle-native-builder` Docker image (Bash entrypoint,
host JDK 17) and `zyntax-ndk-r29-work` volume. Supply completed, verified component
artifact directories from the adjacent native and Jansi recipes.

Prepare the exact [upstream Gradle Git revision](https://github.com/gradle/gradle/tree/e5ee1df3d88b8ca3a8074787a94f373e3090e1db)
at `.work/gradle-native/gradle`; its Git objects and HEAD are the source input.
`SOURCE_INPUT` can name another exact checkout inside the container.

```bash
docker run --rm \
  -v zyntax-ndk-r29-work:/work -v "$PWD:/repo:ro" \
  -e NATIVE_ARTIFACTS=/work/gradle-native/build-C8tGz6/artifacts \
  -e JANSI_ARTIFACTS=/work/gradle-native/jansi/build-SVCXGV/artifacts \
  zyntax-gradle-native-builder /repo/gradle/distribution/build.sh
```

`prepare` as the script argument only clones and patches the source. The incomplete
Windows checkout is an exact Git-object input; a fresh Linux checkout lives under
`/work/gradle-native/distribution/8.14.3-android.1/source`. Rerunning the command
resumes that stage with its own Gradle user home and recorded timestamp. Changed
patch/component inputs require a fresh `WORK_DIR` under that distribution directory.
No old stage is deleted automatically.
Before compilation, the source delta is reconstructed from the pinned patch and
the two declared wrapper/verification additions; unrelated tracked, staged or
nonignored untracked source inputs are rejected.

Upstream's build wrapper is Gradle 8.14.2. Its binary ZIP SHA-256 is pinned to
`7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999`, verified from
the [official checksum](https://services.gradle.org/distributions/gradle-8.14.2-bin.zip.sha256).
The source wrapper receives that checksum before execution. Build limits are two
workers and a 2 GB Gradle heap; build scans, configuration cache and build cache
are disabled. Resumes reuse only that stage's locally compiled task outputs and
downloads. `RERUN_TASKS=true` requests a full local task rebuild when needed.
The restricted repository uses one required, recipe-exported
`ZYNTAX_GRADLE_COMPONENTS_REPOSITORY` environment provider, including in Gradle's
synthetic precompiled-plugin accessor projects, which do not inherit command-line
project properties.

The restricted local Maven group `app.zyntax.gradle` contains source-built
`native-platform:0.22-milestone-28-zyntax.1`,
`gradle-fileevents:0.2.7-zyntax.1`, and `jansi:1.18-zyntax.1`, with sources and
notices. File-events depends on that exact native-platform and SLF4J 1.7.36.
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
and preserves upstream's qualified version in ZIP names/root folders. Runtime
identity uses the supported `versionQualifier=android-1` and recorded `buildTimestamp`
inputs. This is not a stock 8.14.3 ZIP with replaced libraries or an OS spoof.

Native component notices, exact source patch, base revision, build inputs and
component hash manifest accompany the distribution through its source packaging
specification. The upstream commit identifies the base, not unmodified Gradle.
Ncurses remains an explicit app-private terminal dependency, not a
bundled system library. Combined native-component device probes passed, including
real Jansi PTY/termios operations. Full Gradle daemon/watcher/terminal integration
and the release decision remain unfinished; f2fs VFS retention is not verified.

The 2026-09-09 source build produced
`gradle-8.14.3-android-1-20260909053352+0000-bin.zip` (137,589,545 bytes), SHA-256
`0e38a1e17fdab4d64eeab6c7f7c0088aef60551a45cce3bdef13c1e7ef229da4`.
`verify.py` checked its qualified root/runtime receipt, all three exact component
JARs with no extra native variants, and every packaged notice/provenance file.
It emits `verification.json` with the exact version, ZIP name, size and hash.
The corrected Scala compile-only graph also resolved its Zinc/JLine Jansi request
to the single owned 1.18 module. These checks do not claim reproducible ZIP bytes
across fresh build paths or replace Android integration validation.

# Explicit Gradle selection

This headless launcher selects the published Android Gradle 8.14.3 distribution
without editing a user's project or Wrapper. It is standalone optional tooling,
not app/SDK code or a Studio UI. A compatible app-private JDK (verified with Java
21), Bash, the standard terminal utilities and the distribution's ncurses
dependency must already be installed.

```bash
export JAVA_HOME="$PREFIX/lib/jvm/java-21-openjdk"
bash /path/to/launcher/gradle-android.bash --version
bash /path/to/launcher/gradle-android.bash --project-dir ../../my-app/android tasks
```

The unmodified official Gradle Wrapper downloads the pinned GitHub release,
verifies its SHA-256, locks and extracts it into its normal `wrapper/dists` cache.
`GRADLE_USER_HOME` defaults to `~/.gradle`; standard `-g` / `--gradle-user-home`
arguments override it. The upstream launch script runs explicitly through Bash
and preserves standard `JAVA_OPTS` and `GRADLE_OPTS` handling. There is no custom cache hash, archive extractor or
upstream ZIP replacement. Cache reuse follows Gradle's own validation; it does
not rehash the installed tree on every invocation. Project execution requires
trust and Gradle may write its ordinary project caches/build output.

Select a user-supplied extracted installation explicitly:

```bash
bash /path/to/launcher/gradle-android.bash --installation '~/tools/gradle-custom' \
  --project-dir ../../my-app/android tasks
```

`--installation` must be first. Relative paths and literal `~/` are supported.
The selected `bin/gradle` runs through Bash; an invalid selection fails without
downloading or choosing another installation. User-supplied installations are
not labelled verified. All other arguments are forwarded unchanged to Gradle.

This does not redirect `./gradlew`, choose a different version automatically,
install a JDK/SDK/NDK, accept SDK licences, or select an AGP fork. A project's
normal Wrapper still follows its own URL. Future optional tooling can package
this directory unchanged and reuse the shared evaluated project importer.

## Wrapper provenance

The separate [install-only adapter](bootstrap/README.md) reuses the pinned
unminified Wrapper internals to return an installation directory without running
Gradle or evaluating a project. It does not change this launcher's behavior.

`gradlew` and `gradle/wrapper/gradle-wrapper.jar` are the unmodified official Wrapper from
[Gradle 8.14.3 source](https://github.com/gradle/gradle/tree/e5ee1df3d88b8ca3a8074787a94f373e3090e1db/gradle/wrapper),
verified against Gradle's [published Wrapper checksum](https://services.gradle.org/distributions/gradle-8.14.3-wrapper.jar.sha256):

```text
7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172
```

The Wrapper is Apache-2.0; preserve its bundled notices and this repository's
`LICENSE` when distributing the launcher. The hosted distribution retains its
own component licences and notices. Wrapper configuration is the supported
checksum path; the public Tooling API's `useDistribution(URI)` has no checksum
parameter and is not used as an installer.

## Verification

One USB run on 9 September 2026 passed in 38.408 seconds: the real GitHub download
and checksum-verified installation landed in the app user's normal
`~/.gradle/wrapper/dists`, subsequent invocation reused that cache, explicit
local selection used the same installation, and an absent local selection failed
without a download. A sentinel project Wrapper remained unchanged. Java 21.0.12
reported the exact qualified distribution version. The same invocation completed
the distribution's Jansi runtime-wrapper check. No build task, APK installation,
UI navigation or app/SDK change was involved.

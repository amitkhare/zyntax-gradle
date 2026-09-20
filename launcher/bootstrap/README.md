# Install-only Gradle bootstrap

This launcher-owned adapter returns the absolute installation directory from
Gradle's own `Install.createDist`. It does not load the user's Wrapper, start a
Gradle runtime, evaluate project scripts, or build an APK. App/core/SDK contracts
are unchanged. Builder integration and Android qualification of this adapter
are separate; host checks alone do not establish either.

## Build offline

Use Python 3.11+ and a local JDK 17+ on Windows, Linux or macOS. Supply the existing
published archive identified in `inputs.json`; the script never downloads it.
The output directory must not exist.

```bash
python3 launcher/bootstrap/build.py \
  --distribution /cache/gradle-8.14.3-android-1-20260909081124+0000-bin.zip \
  --javac /path/to/jdk/bin/javac --output .work/bootstrap/build
```

`build-receipt.json` records compiler, classpath and hashes. The seven dependency
JARs are copied unchanged from the checksum-verified distribution. Their exact
complete runtime closure is checked against the embedded Gradle module metadata.
Only `GradleBootstrap.java` is compiled (`--release 17`); no Gradle build, source
port rebuild, resolution service, reflection or shaded replacement is involved.

## Invoke

The caller creates its own adjacent properties file from a verified catalogue;
never modify or pass the project's `gradle/wrapper/gradle-wrapper.properties`.
The required properties are:

```properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\://example.invalid/published-gradle.zip
distributionSha256Sum=<the exact catalogue SHA-256, 64 lowercase hex digits>
networkTimeout=60000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
```

```bash
"$JAVA_HOME/bin/java" -cp '/resources/bootstrap/lib/*' \
  app.zyntax.gradle.bootstrap.GradleBootstrap \
  --properties /owned/bootstrap/gradle-wrapper.properties \
  --gradle-user-home /shared/gradle-user-home \
  --result /owned/results/new-bootstrap-result.json
```

All three paths must be absolute. The result's parent must exist and the result
must not. Consume JSON only after exit zero. It contains `gradleHome`,
`gradleUserHome`, Wrapper version, URL and declared checksum. Pass `gradleHome`
directly to the existing model collector's `--gradle-home` option. Do not scrape
console output or compute a second cache key. Local `file:` URIs are supported
for offline qualification; network catalogue URLs must use HTTPS and contain no
credentials, query or fragment.

Use the receipt's isolated classpath. A consumer may share byte-identical JARs
with other resources instead of copying duplicates, but must not mix different
versions into this classpath. On Android use the existing app-private Java and
inherited execution environment; the upstream installer uses `chmod` through
that environment. The adapter does not change PATH, preload or routing variables.

## Cache and failure semantics

The unmodified upstream installer owns download timeouts, locks, extraction,
checksum verification and `.ok` markers in the explicit shared Gradle user home.
The mandatory checksum is verified on installation, not by rehashing a valid
installed tree on each cache hit. The result records a declared identity, not a
fresh extracted-tree attestation. Upstream may replace a corrupt installation
and has its own bounded corrupt-ZIP retry behavior; this adapter adds no retry.
It does not alter upstream `.part` handling or promise resumable HTTP downloads.
An invalid/missing checksum is rejected before installation; a mismatched archive
checksum fails without a result. A failed task may leave upstream partial cache
state. Never automatically loop a failed bootstrap or reinterpret it as Ready.

## Provenance and notices

The internal API unit is pinned to official Gradle **8.14.3**, source commit
`e5ee1df3d88b8ca3a8074787a94f373e3090e1db`. `Install`, `WrapperExecutor`, `Download`
and `PathAssembler` reside in `gradle-wrapper-shared`, not the minified executable
Wrapper JAR. Its Gradle `files`/`stdlib-java-extensions` modules and declared
Guava, failureaccess, SLF4J and jsr305 dependencies are included without changes.
The distribution's original LICENSE/NOTICE and all embedded JAR notices are
retained. Preserve them and this repository's Apache-2.0 license when packaging.
This is not a claim that every bundled dependency has the same license.

The fixed source references are
`platforms/core-runtime/wrapper-shared/{build.gradle.kts,src/main/java/org/gradle/wrapper/}`
and the distribution's `gradle-*-classpath.properties`. The executable Wrapper
and existing published distributions are untouched.

## Focused host check

```bash
python3 launcher/bootstrap/check.py --java /path/to/jdk/bin/java \
  --bundle .work/bootstrap/build \
  --distribution /cache/gradle-8.14.3-android-1-20260909081124+0000-bin.zip \
  --work .work/bootstrap/check
```

The new work directory retains logs/results. The check installs the real cached
qualified archive via a local URI, makes only its own copy unavailable, proves
the next invocation reuses the same installation, and rejects missing, malformed
and mismatched checksums. It has no network URLs or Gradle task invocation.

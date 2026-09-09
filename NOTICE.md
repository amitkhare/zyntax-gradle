# Source and distribution notices

Original build infrastructure is licensed under [Apache-2.0](LICENSE).
This repository contains the Android-host Gradle port and its build recipes,
not application or extension SDK source. Original upstream copyright headers,
license texts and component notices remain applicable; this notice does not
relicense upstream work or provide a legal-compliance guarantee.

## Components

- Gradle 8.14.3: upstream revision
  `e5ee1df3d88b8ca3a8074787a94f373e3090e1db`, with the exact Android changes in
  [distribution/source.patch](distribution/source.patch). Gradle's original
  license and third-party notices remain in the binary distribution.
- Native-platform `0.22-milestone-28`: upstream revision
  `87f4647e90db6006bf357db0ba7fa29925dcc32e`; file-events `0.2.7`: upstream revision
  `08be35d81f4d6336ce4666122c0c72a97b11a7e9`. Both are Apache-2.0. Their original
  source locations and Android changes are recorded in [PORT-NOTICE.txt](PORT-NOTICE.txt),
  [native-platform-android.patch](native-platform-android.patch) and
  [file-events-android.patch](file-events-android.patch).
- Jansi 1.18, Jansi Native 1.8 and HawtJNI runtime 1.17: exact repositories,
  revisions and generator identity are in
  [jansi/SOURCE-PROVENANCE.properties](jansi/SOURCE-PROVENANCE.properties).
  Jansi/Jansi Native are Apache-2.0; HawtJNI retains its original Apache-2.0 root
  license and EPL-1.0 headers/notices on the applicable runtime/native files.
  See [jansi/PORT-NOTICE.txt](jansi/PORT-NOTICE.txt) and
  [the EPL text](jansi/licenses/EPL-1.0.txt).
- NDK r29 is an external build input. Its original notices accompany artifacts
  for linked target runtime code. Ncurses and its terminfo database are external
  app-private terminal dependencies, not redistributed in the Gradle bundle.
  The separate native probe includes SLF4J 1.7.36 with its [MIT license](licenses/slf4j-LICENSE.txt).

## Source companions and history

The binary Gradle ZIP includes component licenses, port notices, source identities,
the exact Gradle patch and component hashes under `licenses/android-host/`.
It does **not** contain the component source JARs. Keep corresponding sources
available alongside the [release](https://github.com/amitkhare/zyntax-gradle/releases):

- `jansi-1.18-zyntax.1-sources.jar` contains the modified Jansi/Jansi Native/HawtJNI
  Java sources, native C/header sources including generated JNI, recipes,
  patches, provenance and notices.
- The native-platform and file-events source JARs contain their corresponding
  Java and generated version sources only. Their native C/C++ sources are the
  pinned upstream trees plus this repository's public patches and build recipe;
  these JARs must not be described as complete native-source archives.

The Gradle-only history was preserved when these files moved from a combined
toolchain repository to this one. Previously verified release bytes retain
historical `gradle/...` recipe paths, notices and hashes. The move does not rebuild
or relabel those artifacts, and GitHub's automatic repository source archive
contains these recipes/patches, not the full upstream Gradle/component trees.

# Source this after setting stage and file_events_layout. These are source
# layouts selected by the pinned component profile, not runtime fallbacks.
case "$file_events_layout" in
    integrated)
        fe="$stage/native-platform/file-events"
        fe_artifact=file-events
        fe_library=native-platform-file-events
        fe_resource_variant=android-aarch64
        fe_generated_java="$fe/build/generated/version/java"
        fe_version_header="$fe/build/generated/version/header/native_platform_version.h"
        fe_version_macro=NATIVE_VERSION
        fe_jni="$fe/build/generated/jni"
        fe_jni_package=net_rubygrapefruit_platform_internal_jni
        fe_version_class=net.rubygrapefruit.platform.internal.jni.FileEventsVersion
        ;;
    standalone)
        fe="$stage/file-events"
        fe_artifact=gradle-fileevents
        fe_library=gradle-fileevents
        fe_resource_variant=aarch64-linux-android
        fe_generated_java="$fe/build/generated/sources/java/version"
        fe_version_header="$fe/build/generated/sources/headers/version/fileevents_version.h"
        fe_version_macro=FILE_EVENTS_VERSION
        fe_jni="$fe/build/generated/sources/headers/java"
        fe_jni_package=org_gradle_fileevents_internal
        fe_version_class=org.gradle.fileevents.internal.FileEventsVersion
        ;;
    *) printf 'Unknown pinned file-events source layout: %s\n' "$file_events_layout" >&2; exit 1 ;;
esac

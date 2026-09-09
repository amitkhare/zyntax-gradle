cmake_minimum_required(VERSION 3.22)
project(gradle_android_native LANGUAGES CXX)

if(NOT ANDROID OR NOT ANDROID_ABI STREQUAL "arm64-v8a")
  message(FATAL_ERROR "This recipe targets Android arm64-v8a.")
endif()
foreach(input NATIVE_PLATFORM_SOURCE FILE_EVENTS_SOURCE NCURSES_PREFIX)
  if(NOT IS_DIRECTORY "${${input}}")
    message(FATAL_ERROR "${input} must name a prepared input directory.")
  endif()
endforeach()

set(np "${NATIVE_PLATFORM_SOURCE}/native-platform")
set(np_shared
  "${np}/src/shared/cpp/generic.cpp"
  "${np}/src/shared/cpp/generic_posix.cpp"
  "${np}/src/shared/cpp/unix_strings.cpp")
add_library(native-platform SHARED ${np_shared}
  "${np}/src/main/cpp/linux.cpp"
  "${np}/src/main/cpp/posix.cpp")
add_library(native-platform-curses SHARED ${np_shared}
  "${np}/src/curses/cpp/curses.cpp")
foreach(target native-platform native-platform-curses)
  target_include_directories(${target} PRIVATE
    "${np}/src/shared/headers"
    "${np}/build/generated/version/header"
    "${np}/build/generated/jni")
endforeach()
target_compile_definitions(native-platform PRIVATE _FILE_OFFSET_BITS=64)
add_library(ncurses SHARED IMPORTED)
set_target_properties(ncurses PROPERTIES
  IMPORTED_LOCATION "${NCURSES_PREFIX}/lib/libncursesw.so.6")
target_include_directories(native-platform-curses PRIVATE "${NCURSES_PREFIX}/include")
target_link_libraries(native-platform-curses PRIVATE ncurses)

add_library(gradle-fileevents SHARED
  "${FILE_EVENTS_SOURCE}/src/main/cpp/fileevents_version.cpp"
  "${FILE_EVENTS_SOURCE}/src/main/cpp/generic_fsnotifier.cpp"
  "${FILE_EVENTS_SOURCE}/src/main/cpp/jni_support.cpp"
  "${FILE_EVENTS_SOURCE}/src/main/cpp/linux_fsnotifier.cpp"
  "${FILE_EVENTS_SOURCE}/src/main/cpp/logging.cpp"
  "${FILE_EVENTS_SOURCE}/src/main/cpp/services.cpp")
target_include_directories(gradle-fileevents PRIVATE
  "${FILE_EVENTS_SOURCE}/src/main/headers"
  "${FILE_EVENTS_SOURCE}/build/generated/sources/headers/java"
  "${FILE_EVENTS_SOURCE}/build/generated/sources/headers/version")
target_link_libraries(gradle-fileevents PRIVATE dl)

foreach(target native-platform native-platform-curses gradle-fileevents)
  set_target_properties(${target} PROPERTIES SKIP_BUILD_RPATH TRUE INSTALL_RPATH "")
  target_compile_features(${target} PRIVATE cxx_std_17)
  target_compile_options(${target} PRIVATE -Wall -Wextra -Wformat=2 -fvisibility=hidden)
  target_link_options(${target} PRIVATE -Wl,--no-undefined -Wl,-z,max-page-size=16384 -Wl,--exclude-libs,ALL)
  install(TARGETS ${target} LIBRARY DESTINATION lib)
endforeach()

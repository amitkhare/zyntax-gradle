cmake_minimum_required(VERSION 3.22)
project(jansi_android LANGUAGES C)

if(NOT ANDROID OR NOT ANDROID_ABI STREQUAL "arm64-v8a")
  message(FATAL_ERROR "This recipe targets Android arm64-v8a.")
endif()
if(JANSI_API STREQUAL "2")
  set(source_inputs JANSI_NATIVE_SOURCE)
elseif(JANSI_API STREQUAL "1")
  set(source_inputs JANSI_NATIVE_SOURCE HAWTJNI_SOURCE GENERATED_JNI)
else()
  message(FATAL_ERROR "JANSI_API must explicitly select source API 1 or 2.")
endif()
foreach(input IN LISTS source_inputs)
  if(NOT IS_DIRECTORY "${${input}}")
    message(FATAL_ERROR "${input} must name its prepared source directory.")
  endif()
endforeach()

# Compile/link checks use the Android target sysroot, never the build host.
include(CheckIncludeFile)
include(CheckSymbolExists)
include(CheckCSourceCompiles)
foreach(header unistd.h stdlib.h string.h termios.h sys/ioctl.h pty.h)
  string(MAKE_C_IDENTIFIER "${header}" key)
  check_include_file("${header}" "target_has_${key}")
  if(NOT target_has_${key})
    message(FATAL_ERROR "Required Android header is missing: ${header}")
  endif()
endforeach()
foreach(function isatty ttyname_r tcgetattr tcsetattr openpty cfgetispeed cfgetospeed cfsetispeed cfsetospeed)
  check_symbol_exists("${function}" "unistd.h;termios.h;sys/ioctl.h;pty.h" "target_has_${function}")
  if(NOT target_has_${function})
    message(FATAL_ERROR "Required Android terminal function is missing: ${function}")
  endif()
endforeach()
# Bionic declares overloaded ioctl variants, so validate a real call rather than
# taking its ambiguous address. Also check the array bound used by generated JNI.
check_c_source_compiles("
#include <termios.h>
#include <sys/ioctl.h>
_Static_assert(sizeof(((struct termios *)0)->c_cc) == 19, \"Android NCCS\");
_Static_assert(sizeof(((struct termios *)0)->c_cc) <= 32, \"Java c_cc capacity\");
int main(void) { struct winsize value; return ioctl(-1, TIOCGWINSZ, &value); }
" target_has_ioctl_and_termios_layout)
if(NOT target_has_ioctl_and_termios_layout)
  message(FATAL_ERROR "Required Android ioctl/termios ABI is unavailable.")
endif()

if(JANSI_API STREQUAL "2")
  set(native "${JANSI_NATIVE_SOURCE}/src/main/native")
  add_library(jansi SHARED
    "${native}/jansi.c" "${native}/jansi_structs.c"
    "${native}/jansi_isatty.c" "${native}/jansi_ttyname.c")
  target_include_directories(jansi PRIVATE "${native}")
else()
  set(native "${JANSI_NATIVE_SOURCE}/src/main/native-package/src")
  add_library(jansi SHARED
  "${GENERATED_JNI}/jansi.c"
  "${GENERATED_JNI}/jansi_structs.c"
  "${GENERATED_JNI}/jansi_stats.c"
  "${HAWTJNI_SOURCE}/hawtjni-generator/src/main/resources/hawtjni.c"
  "${native}/jansi_isatty.c"
  "${native}/jansi_ttyname.c")
  target_include_directories(jansi PRIVATE "${GENERATED_JNI}" "${native}")
endif()
target_compile_definitions(jansi PRIVATE
  HAVE_UNISTD_H=1 HAVE_STDLIB_H=1 HAVE_STRINGS_H=1 HAVE_TERMIOS_H=1 HAVE_IOCTL_H=1 HAVE_PTY_H=1
  HAVE_ISATTY=1 HAVE_TTYNAME=1 HAVE_TCGETATTR=1 HAVE_TCSETATTR=1 HAVE_IOCTL=1 HAVE_OPENPTY=1
  HAVE_STDINT_H=1 HAWTJNI_DISABLE_CALLBACKS=1)
target_compile_options(jansi PRIVATE -Wall -Wextra -Wformat=2 -Werror=incompatible-pointer-types
  -fvisibility=hidden -fstack-protector-strong)
target_link_options(jansi PRIVATE -Wl,--no-undefined -Wl,-z,max-page-size=16384 -Wl,--exclude-libs,ALL)
install(TARGETS jansi LIBRARY DESTINATION lib)

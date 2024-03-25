cmake_minimum_required(VERSION 3.18...3.26)

project(${SKBUILD_PROJECT_NAME}
    VERSION ${SKBUILD_PROJECT_VERSION}
    LANGUAGES C
)


# Path to custom CMake functions
set(CMAKE_MODULE_PATH "${PROJECT_SOURCE_DIR}/cmake" ${CMAKE_MODULE_PATH})
include(UpdateVendoredLibraryOptions)

set(CFFI_INPUT_LIBRARY ${VENDORED_LIBRARY_PKG_CONFIG})  # Should be searchable by pkg-config


# THis is needed to define Python_add_library()
set(CFFI_C_CODE_DIR ${PROJECT_BINARY_DIR}/_gen_c_file)
set(CFFI_C_CODE "${CFFI_INPUT_LIBRARY}_cffi_bindings.c")
set(CFFI_HEADERS_DIR ${PROJECT_BINARY_DIR}/_gen_cffi_headers)


# Shared object that wraps the CFFI binding and the vendored library
set(CFFI_OUTPUT_LIBRARY "_lib${CFFI_INPUT_LIBRARY}")


# Define python
find_package(Python REQUIRED COMPONENTS Interpreter Development.Module)
set(Python_SOABI ${SKBUILD_SOABI})


# Verify CFFI python module is available
execute_process(
    COMMAND         ${Python3_EXECUTABLE} -c "import cffi"
    ERROR_VARIABLE  _cffi_error
    OUTPUT_QUIET
    ERROR_STRIP_TRAILING_WHITESPACE
)

if(_cffi_error)
    message(FATAL_ERROR "CFFI is required to build coincurve")
endif()


# Tweak SECP256K1 build, in particular for STATIC library that needs -fPIC
if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()


# Cross-compilation options: This is setup for Github/Actions runners
# For Linux, we use cibuildwheel to build the wheels, which uses Docker
if (CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    set(AUTOMATIC_OSX_TARGETS "armv7" "armv7s" "arm64" "arm64e" "x86_64")
    if (NOT "${PROJECT_CROSS_COMPILE_TARGET}" STREQUAL "" AND "${PROJECT_CROSS_COMPILE_TARGET}" IN_LIST AUTOMATIC_OSX_TARGETS)
        # Cross-compilation for Linux host system:
        set(CMAKE_SYSTEM_PROCESSOR ${PROJECT_CROSS_COMPILE_TARGET})
    else()
        message(FATAL_ERROR "Cross-compilation target not supported: ${PROJECT_CROSS_COMPILE_TARGET}")
    endif()
elseif (CMAKE_SYSTEM_NAME STREQUAL "Windows")
    set(AUTOMATIC_WINDOWS_TARGETS "AMD64" "x86" "arm64")
    if ("${PROJECT_CROSS_COMPILE_TARGET}" STREQUAL "" AND "${PROJECT_CROSS_COMPILE_TARGET}" IN_LIST AUTOMATIC_WINDOWS_TARGETS)
        # Cross-compilation for Windows host system:
        set(CMAKE_SYSTEM_PROCESSOR ${PROJECT_CROSS_COMPILE_TARGET})
    else()
        message(FATAL_ERROR "Cross-compilation target not supported: ${PROJECT_CROSS_COMPILE_TARGET}")
    endif()
endif()


# -fPIC is needed since we create a shared object to be loaded by Python
if (VENDORED_LIBRARY_STATIC_BUILD)
    set(CMAKE_POSITION_INDEPENDENT_CODE ON)
endif()


# Add the subdirectories. Append CONDA to the PKG_CONFIG_PATH
list(APPEND ENV{PKG_CONFIG_PATH} "$ENV{CONDA_PREFIX}/lib/pkgconfig")
find_package(PkgConfig REQUIRED)
pkg_check_modules(PKGCONFIG_INPUT_LIB IMPORTED_TARGET ${CFFI_INPUT_LIBRARY}>=2)

# Try to find the library in the system
find_library(_INPUT_LIBRARY ${CFFI_INPUT_LIBRARY})
if (COINCURVE_IGNORE_SYSTEM_LIB OR NOT _INPUT_LIBRARY)
    UpdateVendoredLibraryOptions("VENDORED_OPTION" ${VENDORED_LIBRARY_OPTION_PREFIX})
    add_subdirectory(cm_vendored_library)
    if (NOT VENDORED_HEADERS_DIR)
        message(FATAL_ERROR "Vendored library headers not found")
    endif()
    message(STATUS "The vendored library include located at: ${VENDORED_HEADERS_DIR}")
endif()
add_subdirectory(cm_library_cffi_headers)
add_subdirectory(cm_library_c_binding)


# Create the shared library from the CFFI binding and the static library from ${CFFI_INPUT_LIBRARY}_vendor
Python_add_library(${CFFI_OUTPUT_LIBRARY} MODULE WITH_SOABI "${CFFI_C_CODE_DIR}/${CFFI_C_CODE}")
set_source_files_properties("${CFFI_C_CODE_DIR}${CFFI_C_CODE}" PROPERTIES GENERATED 1)


if (PROJECT_IGNORE_SYSTEM_LIB OR NOT _INPUT_LIBRARY)
    # The build-type seems to be defined as 'MODULE', which creates issues with missing variables
    # for CMake: (This only happens on Windows though ...
    set(CMAKE_MODULE_LINKER_FLAGS_COVERAGE "")

    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE ${CFFI_INPUT_LIBRARY})
    add_dependencies(${CFFI_OUTPUT_LIBRARY} ${CFFI_INPUT_LIBRARY})
else()
    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE PkgConfig::PKGCONFIG_INPUT_LIB)
endif()

add_dependencies(${CFFI_OUTPUT_LIBRARY} cffi-c-binding)

target_include_directories(${CFFI_OUTPUT_LIBRARY} PUBLIC ${VENDORED_HEADERS_DIR})
target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PRIVATE Py_LIMITED_API)


# Add platform-specific definitions
if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_LINUX")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_MACOS")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "Windows")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_WINDOWS")
endif()


# Configure installation of the shared library ${CFFI_OUTPUT_LIBRARY} in the package
install(TARGETS ${CFFI_OUTPUT_LIBRARY} LIBRARY DESTINATION ${SKBUILD_PLATLIB_DIR}/${SKBUILD_PROJECT_NAME})

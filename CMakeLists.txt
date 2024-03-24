cmake_minimum_required(VERSION 3.15...3.26)

project(${SKBUILD_PROJECT_NAME}
    VERSION ${SKBUILD_PROJECT_VERSION}
    LANGUAGES C
)

set(CFFI_INPUT_LIBRARY secp256k1)  # Should be searchable by pkg-config

# THis is needed to define Python_add_library()
set(CFFI_C_CODE_DIR ${PROJECT_BINARY_DIR}/_gen_c_file)
set(CFFI_C_CODE "${CFFI_INPUT_LIBRARY}_cffi_bindings.c")
set(CFFI_HEADERS_DIR ${PROJECT_BINARY_DIR}/_gen_cffi_headers)

set(CFFI_OUTPUT_LIBRARY "_lib${CFFI_INPUT_LIBRARY}")  # Loaded by coincurve

find_package(Python REQUIRED Interpreter Development)
set(Python_SOABI ${SKBUILD_SOABI})

# Verify CFFI
execute_process(
    COMMAND         ${Python3_EXECUTABLE} -c "import cffi"
    ERROR_VARIABLE  _cffi_error
    OUTPUT_QUIET
    ERROR_STRIP_TRAILING_WHITESPACE
)

if(_cffi_error)
    message(FATAL_ERROR "CFFI is required to build coincurve")
endif()

if (NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

# Add the subdirectories
# Consider CONDA env (libsecp256k1 is available on conda-forge)
set(ENV{PKG_CONFIG_PATH} "$ENV{CONDA_PREFIX}/lib/pkgconfig")
find_package(PkgConfig REQUIRED)
pkg_check_modules(PKG_INPUT_LIB IMPORTED_TARGET ${CFFI_INPUT_LIBRARY}>=2)

find_library(_INPUT_LIBRARY ${CFFI_INPUT_LIBRARY})
if (COINCURVE_IGNORE_SYSTEM_LIB OR NOT _INPUT_LIBRARY)
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

if (COIINCURVE_IGNORE_SYSTEM_LIB OR NOT _INPUT_LIBRARY)
    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE ${CFFI_INPUT_LIBRARY})
    add_dependencies(${CFFI_OUTPUT_LIBRARY} ${CFFI_INPUT_LIBRARY})
else()
    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE PkgConfig::PKG_INPUT_LIB)
endif()

add_dependencies(${CFFI_OUTPUT_LIBRARY} cffi-c-binding)

target_include_directories(${CFFI_OUTPUT_LIBRARY} PUBLIC ${libsecp256k1_SOURCE_DIR}/include)
target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PRIVATE Py_LIMITED_API)

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_LINUX")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "Darwin")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_MACOS")
endif()
if(CMAKE_SYSTEM_NAME STREQUAL "Windows")
    target_compile_definitions(${CFFI_OUTPUT_LIBRARY} PUBLIC "IS_WINDOWS")
endif()


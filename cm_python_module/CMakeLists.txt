# Define python
find_package(Python3 REQUIRED COMPONENTS Interpreter Development.Module)
set(Python3_SOABI ${SKBUILD_SOABI})

# Try to fix odd issue with Python3.dll not found on windows.CMAKE_SYSTEM_NAME
# It seems to originated from the multi-config that generates a DEBUG config
# It also generate a Coverage config that requires setting an empty variable later
# set_target_properties(Python3::Module PROPERTIES MAP_IMPORTED_CONFIG_DEBUG RELEASE)
# set_target_properties(Python3::Module PROPERTIES MAP_IMPORTED_CONFIG_RELWITHDEBINFO RELEASE)

# Create the shared library from the CFFI binding and the static library from ${CFFI_INPUT_LIBRARY}_vendor
Python3_add_library(${CFFI_OUTPUT_LIBRARY} MODULE WITH_SOABI "${CFFI_C_CODE_DIR}/${CFFI_C_CODE}")
set_source_files_properties("${CFFI_C_CODE_DIR}${CFFI_C_CODE}" PROPERTIES GENERATED 1)

if (PROJECT_IGNORE_SYSTEM_LIB OR NOT LOCAL_INPUT_LIBRARY)
    # The build-type seems to be defined as 'MODULE', which creates issues with missing variables
    # for CMake: (This only happens on Windows though ...
    set(CMAKE_MODULE_LINKER_FLAGS_COVERAGE "")

    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE ${CFFI_INPUT_LIBRARY})
    add_dependencies(${CFFI_OUTPUT_LIBRARY} ${CFFI_INPUT_LIBRARY})
else()
    target_link_libraries(${CFFI_OUTPUT_LIBRARY} PRIVATE PkgConfig::PKGCONFIG_INPUT_LIB Python3::Python)
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

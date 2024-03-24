include(GNUInstallDirs)
include(FetchContent)

# Set ULR based upon CMake definitions
if (NOT UPSTREAM_URL)
    set(UPSTREAM_URL "https://github.com/bitcoin-core/secp256k1/archive")
endif()

if (NOT UPSTREAM_REF)
    set(UPSTREAM_REF "1ad5185cd42c0636104129fcc9f6a4bf9c67cc40")
endif()

if (NOT UPSTREAM_HASH)
    set(UPSTREAM_HASH "ba34be4319f505c5766aa80b99cfa696cbb2993bfecf7d7eb8696106c493cb8c")
endif()

FetchContent_Declare(
    vendored_library
    URL "${UPSTREAM_URL}/${UPSTREAM_REF}.tar.gz"
    URL_HASH "SHA256=${UPSTREAM_HASH}"
)
FetchContent_MakeAvailable(vendored_library)

if (NOT IS_DIRECTORY ${vendored_library_SOURCE_DIR}/include)
    message(FATAL_ERROR "The vendored library include files does not exist. Exiting")
else()
    set(VENDORED_HEADERS_DIR "${vendored_library_SOURCE_DIR}/include" CACHE PATH "Path to the vendored headers")
endif()

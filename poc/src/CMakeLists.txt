add_library(hammer_core STATIC
        allocation.cpp
        bit_flips.cpp
        dram_address.cpp
        jitted.cpp
        pattern.cpp
)

set_source_files_properties(
  jitted.cpp
  PROPERTIES
    COMPILE_FLAGS "-Wno-pedantic -Wno-extra-semi"
)

target_include_directories(hammer_core
        PUBLIC
        $<BUILD_INTERFACE:${PROJECT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
)

target_compile_options(hammer_core PRIVATE
        ${HAMMER_WARNINGS}
        ${HAMMER_MARCH_FLAGS}
)

target_link_libraries(hammer_core
        PUBLIC
        asmjit
        indicators::indicators
)

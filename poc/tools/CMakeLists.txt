add_executable(phoenix
        phoenix.cpp        # main() + CLI11
)

# allow  #include "phoenix_cli.hpp"
target_include_directories(phoenix PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(phoenix
        PRIVATE
        hammer_core
        CLI11::CLI11
)

target_compile_options(phoenix PRIVATE
        ${HAMMER_WARNINGS}
        ${HAMMER_MARCH_FLAGS}
)

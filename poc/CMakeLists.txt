cmake_minimum_required(VERSION 3.14)

project(
        hammer
        VERSION     1.0.0
        DESCRIPTION "Phoenix"
        LANGUAGES   CXX
)

# ───────────  Dependencies (FetchContent) ───────────
include(FetchContent)

FetchContent_Declare(
        CLI11 GIT_REPOSITORY https://github.com/CLIUtils/CLI11.git
        GIT_TAG v2.5.0
)
FetchContent_Declare(
        asmjit GIT_REPOSITORY https://github.com/asmjit/asmjit.git
        GIT_TAG 8315855c6432039eb39e541664f9df2f84be40b6
)
FetchContent_Declare(
        indicators GIT_REPOSITORY https://github.com/p-ranav/indicators.git
        GIT_TAG 3872f37abd90d7557bac5f834bfb45bd6c75259a
)
FetchContent_MakeAvailable(CLI11 asmjit indicators)

foreach(dep CLI11::CLI11 asmjit indicators::indicators)
    if(NOT TARGET ${dep})
        message(FATAL_ERROR "Dependency target '${dep}' not found")
    endif()
endforeach()

# ─── Quiet down AsmJit warnings ──────────────────────────────────────
if (TARGET asmjit)
  if (CMAKE_CXX_COMPILER_ID MATCHES "(GNU|Clang|AppleClang)")
    target_compile_options(asmjit PRIVATE
      -Wno-pedantic
      -Wno-extra-semi
    )
  elseif (CMAKE_CXX_COMPILER_ID STREQUAL "MSVC")
    target_compile_options(asmjit PRIVATE /W0)
  endif()
endif()

# ───────────  Global compile settings ───────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS  OFF)

find_package(Threads REQUIRED)

set(HAMMER_WARNINGS
        -Wall -Wextra -Wpedantic
        -Wno-unused-function -Wno-unused-variable -Wno-unused-parameter
        -Wno-comment -Wno-unused-value
)
set(HAMMER_MARCH_FLAGS -funroll-loops -march=native -masm=intel)

# ───────────  Sub-directories ───────────
add_subdirectory(src)
add_subdirectory(tools)

project(hammer CXX)

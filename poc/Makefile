# Makefile for building Phoenix project

# Variables
BUILD_DIR    ?= build
BUILD_TYPE   ?= Release
GENERATOR    ?=
JOBS         ?= $(shell nproc)
ARGS         ?=
CMAKE        ?= cmake
RESULTS_DIR  ?= results
TIMESTAMP    := $(shell date +%Y%m%d_%H%M%S)
CSV_PATH     := $(RESULTS_DIR)/bit_flips_$(TIMESTAMP).csv

.PHONY: all configure build run zip format clean help

all: build

help:
	@echo "Usage: make [target] [VARIABLE=value]"
	@echo ""
	@echo "Targets:"
	@echo "  configure    Configure the project with CMake (in $(BUILD_DIR))"
	@echo "  build        Build the project using $(JOBS) job(s)"
	@echo "  run          Build (if needed), prepare results/, and run Phoenix with --csv=$(CSV_PATH)"
	@echo "  zip          Create a zip of tracked files (excluding git) wrapped in 'phoenix/'"
	@echo "  format       Apply clang-format to tracked C/C++ files in parallel"
	@echo "  clean        Remove build directory"
	@echo "  help         Show this help message"
	@echo ""
	@echo "Variables:"
	@echo "  BUILD_DIR    Build directory (default: $(BUILD_DIR))"
	@echo "  BUILD_TYPE   CMake build type (default: $(BUILD_TYPE))"
	@echo "  GENERATOR    CMake generator (e.g., Ninja)"
	@echo "  JOBS         Parallel build jobs (default: $(JOBS))"
	@echo "  ARGS         Extra arguments to pass to Phoenix when running"
	@echo "  RESULTS_DIR  Where Phoenix will write its CSV (default: $(RESULTS_DIR))"
	@echo "  CMAKE        CMake executable (default: $(CMAKE))"

configure:
	@echo "Configuring in $(BUILD_DIR) (type=$(BUILD_TYPE))"
	@mkdir -p $(BUILD_DIR)
	@cd $(BUILD_DIR) && \
	if [ -n "$(GENERATOR)" ]; then \
	  $(CMAKE) -G "$(GENERATOR)" -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) ..; \
	else \
	  $(CMAKE) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) ..; \
	fi

build: configure
	@echo "Building in $(BUILD_DIR) with $(JOBS) job(s)"
	@cd $(BUILD_DIR) && $(CMAKE) --build . -- -j$(JOBS)

run: build
	@echo "Preparing results directory: $(RESULTS_DIR)"
	@mkdir -p $(RESULTS_DIR)
	@echo "Running Phoenix with args: $(ARGS) --csv=$(CSV_PATH)"
	@cd $(BUILD_DIR) && sudo ./tools/phoenix $(ARGS) --csv=$(CSV_PATH)

format:
	@echo "Formatting tracked C/C++ source files in parallel…"
	@git ls-files '*.cpp' '*.c' '*.h' '*.hpp' \
		| xargs -P$(JOBS) -n1 clang-format -i

zip:
	@echo "Creating phoenix.zip of tracked files (excluding .gitignore) wrapped in 'phoenix/'"
	@git archive HEAD \
	    --prefix=phoenix/ \
	    --format=zip \
	    -o phoenix.zip \
	    $(shell git ls-files | grep -v '^\.gitignore$$')

clean:
	@echo "Removing $(BUILD_DIR) directory"
	@rm -rf $(BUILD_DIR)

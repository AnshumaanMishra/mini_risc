CXX      ?= g++
CXXFLAGS ?= -Wall -std=c++14 -Iassembler -Iassembler/build
FLEX     ?= flex
BISON    ?= bison
IVERILOG ?= iverilog
VVP      ?= vvp

ASM_DIR   := assembler
ASM_BUILD := $(ASM_DIR)/build
SIM_DIR   := simulator
BUILD_DIR := build
INPUT_DIR := inputs

ASM_BIN   := $(ASM_DIR)/mini_asm
VVP_FILE  := $(BUILD_DIR)/mini_risc.vvp

ASM_YACC_SRC := $(ASM_BUILD)/parser.tab.cpp
ASM_YACC_HDR := $(ASM_BUILD)/parser.tab.hpp
ASM_LEX_SRC  := $(ASM_BUILD)/lex.yy.cpp
ASM_SRCS     := $(ASM_DIR)/main.cpp $(ASM_DIR)/symbol_table.cpp $(ASM_YACC_SRC) $(ASM_LEX_SRC)
ASM_HDRS     := $(ASM_DIR)/constants.hpp $(ASM_DIR)/symbol_table.hpp

VERILOG_SOURCES := $(shell find $(SIM_DIR) -type f -name '*.v' -print)

.PHONY: all
all: $(ASM_BIN) $(VVP_FILE)

.PHONY: assembler
assembler: $(ASM_BIN)

$(ASM_YACC_SRC) $(ASM_YACC_HDR) &: $(ASM_DIR)/parser.y
	@mkdir -p $(ASM_BUILD)
	$(BISON) -d -o $(ASM_YACC_SRC) $<

$(ASM_LEX_SRC): $(ASM_DIR)/lexer.l $(ASM_YACC_HDR)
	@mkdir -p $(ASM_BUILD)
	$(FLEX) -o $@ $<

$(ASM_BIN): $(ASM_SRCS) $(ASM_HDRS)
	$(CXX) $(CXXFLAGS) -o $@ $(ASM_DIR)/main.cpp $(ASM_DIR)/symbol_table.cpp $(ASM_YACC_SRC) $(ASM_LEX_SRC)

.PHONY: simulator
simulator: $(VVP_FILE)

$(VVP_FILE): $(VERILOG_SOURCES)
	@mkdir -p $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -s tb_mini_risc -o $@ $(VERILOG_SOURCES)

ASM_SRC ?= program.s

.PHONY: sim
sim: $(ASM_BIN) $(VVP_FILE)
	@mkdir -p $(INPUT_DIR)
	@echo "--- Assembling $(ASM_SRC) ---"
	./$(ASM_BIN) $(ASM_SRC) $(INPUT_DIR)/program.mem
	@echo "--- Running Simulation ---"
	$(VVP) $(VVP_FILE)

# Run the full regression: assemble -> simulate -> check registers/PC/control from the VCD.
# Extra arguments: make test ARGS="--group Memory -v"
.PHONY: test
test: $(ASM_BIN) $(VVP_FILE)
	python3 run_tests.py --no-build $(ARGS)

.PHONY: clean
clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR) $(ASM_BUILD)
	rm -f $(ASM_BIN) $(INPUT_DIR)/program.mem log.txt


# CXX      ?= g++
# CXXFLAGS ?= -Wall -std=c++14 -Iassembler
# FLEX     ?= flex
# BISON    ?= bison
# IVERILOG ?= iverilog
# VVP      ?= vvp
#
# ASM_DIR   := assembler
# SIM_DIR   := simulator
# BUILD_DIR := build
# INPUT_DIR := inputs
#
# ASM_BIN   := $(ASM_DIR)/mini_asm
# VVP_FILE  := $(BUILD_DIR)/mini_risc.vvp
#
# ASM_YACC_SRC := $(ASM_DIR)/parser.tab.cpp
# ASM_YACC_HDR := $(ASM_DIR)/parser.tab.hpp
# ASM_LEX_SRC  := $(ASM_DIR)/lex.yy.cpp
# ASM_SRCS     := $(ASM_DIR)/main.cpp $(ASM_DIR)/symbol_table.cpp $(ASM_YACC_SRC) $(ASM_LEX_SRC)
# ASM_HDRS     := $(ASM_DIR)/constants.hpp $(ASM_DIR)/symbol_table.hpp
#
# VERILOG_SOURCES := $(shell find $(SIM_DIR) -type f -name '*.v' -print)
#
# .PHONY: all
# all: $(ASM_BIN) $(VVP_FILE)
#
# .PHONY: assembler
# assembler: $(ASM_BIN)
#
# $(ASM_YACC_SRC) $(ASM_YACC_HDR): $(ASM_DIR)/parser.y
# 	$(BISON) -d -o $(ASM_YACC_SRC) $<
#
# $(ASM_LEX_SRC): $(ASM_DIR)/lexer.l $(ASM_YACC_HDR)
# 	$(FLEX) -o $@ $<
#
# $(ASM_BIN): $(ASM_SRCS) $(ASM_HDRS)
# 	$(CXX) $(CXXFLAGS) -o $@ $(ASM_DIR)/main.cpp $(ASM_DIR)/symbol_table.cpp $(ASM_YACC_SRC) $(ASM_LEX_SRC)
#
# .PHONY: simulator
# simulator: $(VVP_FILE)
#
# $(VVP_FILE): $(VERILOG_SOURCES)
# 	@mkdir -p $(BUILD_DIR)
# 	$(IVERILOG) -g2012 -Wall -s tb_mini_risc -o $@ $(VERILOG_SOURCES)
#
# ASM_SRC ?= program.s
#
# .PHONY: sim
# sim: $(ASM_BIN) $(VVP_FILE)
# 	@mkdir -p $(INPUT_DIR)
# 	@echo "--- Assembling $(ASM_SRC) ---"
# 	./$(ASM_BIN) $(ASM_SRC) $(INPUT_DIR)/program.mem
# 	@echo "--- Running Simulation ---"
# 	$(VVP) $(VVP_FILE)
#
# # Run the full regression: assemble -> simulate -> check registers/PC/control from the VCD.
# # Extra arguments:  make test ARGS="--group Memory -v"
# .PHONY: test
# test: $(ASM_BIN) $(VVP_FILE)
# 	python3 run_tests.py --no-build $(ARGS)
#
# .PHONY: clean
# clean:
# 	@echo "Cleaning build artifacts..."
# 	rm -rf $(BUILD_DIR)
# 	rm -f $(ASM_BIN) $(ASM_YACC_SRC) $(ASM_YACC_HDR) $(ASM_LEX_SRC)
# 	rm -f $(INPUT_DIR)/program.mem log.txt

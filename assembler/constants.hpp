#pragma once
#ifndef CONSTANTS_HPP
#define CONSTANTS_HPP

#include <cstdint>

namespace MiniRISC {

constexpr uint32_t OP_NOP = 0b000000 << 26;
constexpr uint32_t OP_HALT = 0b111111 << 26;
constexpr uint32_t OP_RTYPE = 0b100000 << 26;

constexpr uint32_t OP_ADDI = 0b110000 << 26;
constexpr uint32_t OP_SUBI = 0b110001 << 26;
constexpr uint32_t OP_ANDI = 0b110010 << 26;
constexpr uint32_t OP_ORI = 0b110011 << 26;
constexpr uint32_t OP_NORI = 0b110100 << 26;
constexpr uint32_t OP_XORI = 0b110101 << 26;
constexpr uint32_t OP_SLLI = 0b110110 << 26;
constexpr uint32_t OP_SRLI = 0b110111 << 26;
constexpr uint32_t OP_SRAI = 0b111000 << 26;
constexpr uint32_t OP_SLTI = 0b111001 << 26;
constexpr uint32_t OP_SGTI = 0b111010 << 26;
constexpr uint32_t OP_SLEI = 0b111011 << 26;
constexpr uint32_t OP_SGEI = 0b111100 << 26;
constexpr uint32_t OP_SEQI = 0b111101 << 26;
constexpr uint32_t OP_SNEI = 0b111110 << 26;

constexpr uint32_t OP_LI = 0b100010 << 26;
constexpr uint32_t OP_LUI = 0b100011 << 26;
constexpr uint32_t OP_MOVE = 0b100100 << 26;
constexpr uint32_t OP_LD = 0b100101 << 26;
constexpr uint32_t OP_ST = 0b100110 << 26;
constexpr uint32_t OP_MFHI = 0b100001 << 26;
constexpr uint32_t OP_MFLO = 0b100111 << 26;

constexpr uint32_t OP_BEQ = 0b010000 << 26;
constexpr uint32_t OP_BNE = 0b010010 << 26;
constexpr uint32_t OP_BLT = 0b010011 << 26;
constexpr uint32_t OP_BLE = 0b010100 << 26;
constexpr uint32_t OP_BGT = 0b010101 << 26;
constexpr uint32_t OP_BGE = 0b010110 << 26;
constexpr uint32_t OP_BZ = 0b010001 << 26;
constexpr uint32_t OP_BV = 0b010111 << 26;

constexpr uint32_t OP_J = 0b101000 << 26;
constexpr uint32_t OP_JAL = 0b101001 << 26;
constexpr uint32_t OP_JR = 0b101011 << 26;

constexpr uint32_t FN_ADD = 0b010000;
constexpr uint32_t FN_SUB = 0b010001;
constexpr uint32_t FN_MUL = 0b010010;
constexpr uint32_t FN_MULU = 0b010011;

constexpr uint32_t FN_AND = 0b011000;
constexpr uint32_t FN_OR = 0b011001;
constexpr uint32_t FN_NOT = 0b011010;
constexpr uint32_t FN_NOR = 0b011011;
constexpr uint32_t FN_XOR = 0b011100;

constexpr uint32_t FN_SLL = 0b100000;
constexpr uint32_t FN_SRL = 0b100001;
constexpr uint32_t FN_SRA = 0b100010;

constexpr uint32_t FN_SLT = 0b001000;
constexpr uint32_t FN_SGT = 0b001001;
constexpr uint32_t FN_SLE = 0b001010;
constexpr uint32_t FN_SGE = 0b001011;
constexpr uint32_t FN_SEQ = 0b001100;
constexpr uint32_t FN_SNE = 0b001101;

} // namespace MiniRISC

#endif

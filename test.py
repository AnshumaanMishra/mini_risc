# DISCLAIMER: AI GENERATED COZ I DONT LIKE PYTHON

import os
import sys
import subprocess

# Magic Halt: We write -1 to R0 using ADDI to trigger $finish in register_file.v
TEST_FOOTER = "\naddi $0, $0, -1\n"

def run_test(name, asm_code, check_reg, expected_val):
    print(f"Test: {name:<35}", end=" ")
    
    asm_file = "inputs/test_prog.s"
    with open(asm_file, "w") as f:
        f.write(asm_code + TEST_FOOTER)
        
    result = subprocess.run(
        ["make", "sim", f"ASM_SRC={asm_file}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    
    if result.returncode != 0:
        error_msg = f"❌ FAILED (Sim Error)\n{result.stderr}"
        print(error_msg)
        return False, error_msg

    registers = []
    mem_file = "inputs/data_ram.mem"
    if os.path.exists(mem_file):
        with open(mem_file, "r") as f:
            for line in f:
                line = line.split("//")[0]
                for token in line.split():
                    if token.startswith("//") or token.startswith("@"): continue
                    try:
                        registers.append(int(token, 16))
                    except ValueError:
                        pass
    
    while len(registers) < 32:
        registers.append(0)

    # Mask expected value to 32 bits to handle Python's infinite-precision negatives
    exp_val = expected_val & 0xFFFFFFFF
    act_val = registers[check_reg]
    
    if act_val != exp_val:
        error_msg = f"❌ FAILED. Reg[{check_reg}] Expected {exp_val:08X}, Got {act_val:08X}"
        print(error_msg)
        return False, error_msg
            
    print("✅ PASSED")
    return True, ""


tests = []

# ==========================================
# 1. R-Type ALUs (2+ Tests Per Opcode)
# ==========================================
R_ALU = [
    ("add", 10, 15, 25), ("add", -5, 10, 5),
    ("sub", 20, 5, 15),  ("sub", 5, 10, -5),
    ("and", 12, 10, 8),  ("and", 0xFFFF, 0x0000, 0),
    ("or",  12, 10, 14), ("or",  0x0000, 0xFFFF, -1),
    ("xor", 12, 10, 6),  ("xor", 0xFFFF, 0xFFFF, 0),
    ("nor", 0, 0, -1),   ("nor", -1, 0, 0),
    ("not", 0, 0, -1),   ("not", -1, 0, 0), # NOT uses 2 registers
    ("sll", 1, 3, 8),    ("sll", 0xFFFF, 16, 0xFFFF0000),
    ("srl", 8, 2, 2),    ("srl", -1, 16, 0x0000FFFF),
    ("sra", 8, 2, 2),    ("sra", -4, 1, -2),
    ("slt", 5, 10, 1),   ("slt", 10, 5, 0),
    ("sgt", 10, 5, 1),   ("sgt", 5, 10, 0),
    ("sle", 5, 5, 1),    ("sle", 10, 5, 0),
    ("sge", 5, 5, 1),    ("sge", 5, 10, 0),
    ("seq", 5, 5, 1),    ("seq", 5, 10, 0),
    ("sne", 5, 10, 1),   ("sne", 5, 5, 0),
]

for op, a, b, res in R_ALU:
    if op == "not":
        asm = f"li $1, {a}\nnot $3, $1"
    else:
        asm = f"li $1, {a}\nli $2, {b}\n{op} $3, $1, $2"
    tests.append({"name": f"R-Type {op.upper()} ({a}, {b})", "asm": asm, "reg": 3, "exp": res})

# ==========================================
# 2. I-Type ALUs (2+ Tests Per Opcode)
# ==========================================
I_ALU = [
    ("addi", 10, 15, 25), ("addi", -5, 10, 5),
    ("subi", 20, 5, 15),  ("subi", 5, 10, -5),
    ("andi", 12, 10, 8),  ("andi", -1, 0, 0),
    ("ori", 12, 10, 14),  ("ori", 0, -1, 0xFFFF),
    ("xori", 12, 10, 6),  ("xori", -1, -1, 0xFFFF0000),
    ("nori", 0, 0, -1),   ("nori", -1, 0, 0),
    ("slli", 1, 3, 8),    ("slli", -1, 16, 0xFFFF0000),
    ("srli", 8, 2, 2),    ("srli", -1, 16, 0x0000FFFF),
    ("srai", -4, 1, -2),  ("srai", 8, 2, 2),
    ("slti", 5, 10, 1),   ("slti", 10, 5, 0),
    ("sgti", 10, 5, 1),   ("sgti", 5, 10, 0),
    ("slei", 5, 5, 1),    ("slei", 10, 5, 0),
    ("sgei", 5, 5, 1),    ("sgei", 5, 10, 0),
    ("seqi", 5, 5, 1),    ("seqi", 5, 10, 0),
    ("snei", 5, 10, 1),   ("snei", 5, 5, 0)
]

for op, a, imm, res in I_ALU:
    tests.append({
        "name": f"I-Type {op.upper()} ({a}, {imm})",
        "asm": f"li $1, {a}\n{op} $3, $1, {imm}",
        "reg": 3, "exp": res
    })

# ==========================================
# 3. Memory & Moves (2+ Tests Per Opcode)
# ==========================================
tests.extend([
    {"name": "LI (Positive)", "asm": "li $3, 0x1234", "reg": 3, "exp": 0x1234},
    {"name": "LI (Negative)", "asm": "li $3, -5", "reg": 3, "exp": -5},
    {"name": "LUI (Positive)", "asm": "lui $3, 0x1234", "reg": 3, "exp": 0x12340000},
    {"name": "LUI (Negative)", "asm": "lui $3, 0xFFFF", "reg": 3, "exp": 0xFFFF0000},
    {"name": "MOVE (Pos)", "asm": "li $1, 99\nmove $3, $1", "reg": 3, "exp": 99},
    {"name": "MOVE (Neg)", "asm": "li $1, -1\nmove $3, $1", "reg": 3, "exp": -1},
    {"name": "LD / ST (Test 1)", "asm": "li $1, 42\nli $2, 0\nst $1, 8($2)\nld $3, 8($2)", "reg": 3, "exp": 42},
    {"name": "LD / ST (Test 2)", "asm": "li $1, -100\nli $2, 4\nst $1, 12($2)\nld $3, 12($2)", "reg": 3, "exp": -100},
])

# ==========================================
# 4. Branches (2+ Tests Per Opcode)
# ==========================================
BRANCHES = [
    ("beq", 5, 5, 1), ("beq", 5, 4, 0),
    ("bne", 5, 4, 1), ("bne", 5, 5, 0),
    ("blt", 4, 5, 1), ("blt", 5, 4, 0),
    ("ble", 5, 5, 1), ("ble", 6, 5, 0),
    ("bgt", 5, 4, 1), ("bgt", 4, 5, 0),
    ("bge", 5, 5, 1), ("bge", 4, 5, 0)
]

for op, a, b, taken in BRANCHES:
    tests.append({
        "name": f"Branch {op.upper()} ({a}, {b})",
        "asm": f"li $1, {a}\nli $2, {b}\nli $3, 0\n{op} $1, $2, taken\nj end\ntaken:\nli $3, 1\nend:\nnop",
        "reg": 3, "exp": taken
    })

tests.extend([
    {"name": "Branch BZ (taken)", "asm": "li $1, 0\nli $3, 0\nbz $1, taken\nj end\ntaken:\nli $3, 1\nend:\nnop", "reg": 3, "exp": 1},
    {"name": "Branch BZ (not taken)", "asm": "li $1, 5\nli $3, 0\nbz $1, taken\nj end\ntaken:\nli $3, 1\nend:\nnop", "reg": 3, "exp": 0},
    {"name": "Branch BV (overflow)", "asm": "lui $1, 0x7FFF\nori $1, $1, 0xFFFF\nli $2, -1\nli $3, 0\nbv $1, $2, taken\nj end\ntaken:\nli $3, 1\nend:\nnop", "reg": 3, "exp": 1},
    {"name": "Branch BV (no overflow)", "asm": "li $1, 10\nli $2, 5\nli $3, 0\nbv $1, $2, taken\nj end\ntaken:\nli $3, 1\nend:\nnop", "reg": 3, "exp": 0}
])

# ==========================================
# 5. Jumps & Multi-Cycle (2+ Tests Per Opcode)
# ==========================================
tests.extend([
    {"name": "J (Unconditional)", "asm": "li $3, 0\nj target\nli $3, 99\ntarget:\naddi $3, $3, 1", "reg": 3, "exp": 1},
    {"name": "J (Skip Back)", "asm": "li $3, 0\nj skip\nback:\naddi $3, $3, 5\nj end\nskip:\naddi $3, $3, 2\nj back\nend:\nnop", "reg": 3, "exp": 7},
    {"name": "JAL (Jump and Link)", "asm": "li $15, 0\njal target\nnop\ntarget:\nli $1, 1", "reg": 15, "exp": 8},
    {"name": "JAL (Nested)", "asm": "jal target\nnop\ntarget:\njal func\nnop\nfunc:\nli $1, 1", "reg": 15, "exp": 12},
    {"name": "JR (Jump Register)", "asm": "jal target\nnop\nreturn:\nli $3, 100\nj end\ntarget:\nli $3, 0\nj $15\nend:\nnop", "reg": 3, "exp": 100},
])


# ==========================================
# 5. MUL / MULU  (all operands are SIGNED 32-bit integers)
# ==========================================
#   MUL  rd, rs, rt : rd = low 32 bits of (rs * rt)
#   MULU rs, rt     : {HI, LO} = full signed 64-bit product of (rs * rt)
#                     (no GPR is written; read back with MFHI / MFLO)

def s32(v):
    v &= 0xFFFFFFFF
    return v - (1 << 32) if v & 0x80000000 else v

def load(reg, val):
    """Emit asm that puts a 32-bit value (signed or raw) into $reg (li only has a 16-bit imm)."""
    val = s32(val)
    if -0x8000 <= val <= 0x7FFF:
        return f"li ${reg}, {val}"
    u = val & 0xFFFFFFFF
    hi, lo = u >> 16, u & 0xFFFF
    asm = f"lui ${reg}, {hex(hi)}"
    if lo:
        asm += f"\nori ${reg}, ${reg}, {lo}"
    return asm

MUL_CASES = [
    ("0 * 5",              0,           5),
    ("10 * 5",             10,          5),
    ("-10 * 5",           -10,          5),
    ("10 * -5",            10,         -5),
    ("-10 * -5",          -10,         -5),
    ("-1 * -1",           -1,          -1),
    ("-1 * 2",            -1,           2),
    ("MAX * MAX",          0x7FFFFFFF,  0x7FFFFFFF),
    ("MIN * MIN",         -0x80000000, -0x80000000),
    ("MIN * -1",          -0x80000000, -1),
    ("MIN * 2",           -0x80000000,  2),
    ("MAX * MIN",          0x7FFFFFFF, -0x80000000),
    ("0x10000000 * 22",    0x10000000,  22),
    ("0x10000000 * 0x1000",0x10000000,  0x1000),
    ("0x12345678 * 0x10000", 0x12345678, 0x10000),
    ("0x10000 * 0x10000",  0x10000,     0x10000),
    ("-0x12345678 * 0x9ABC", -0x12345678, 0x9ABC),
]

for label, a, b in MUL_CASES:
    prod = a * b
    lo, hi = s32(prod), s32(prod >> 32)
    pre = f"{load(1, a)}\n{load(2, b)}\n"
    tests.append({"name": f"MUL ({label})",     "asm": pre + "mul $3, $1, $2",             "reg": 3, "exp": lo})
    tests.append({"name": f"MULU ({label}) LO", "asm": pre + "mulu $1, $2\nmflo $3",      "reg": 3, "exp": lo})
    tests.append({"name": f"MULU ({label}) HI", "asm": pre + "mulu $1, $2\nmfhi $3",      "reg": 3, "exp": hi})

# --- Side-effect / routing checks ---
tests.extend([
    # MULU must not write a general-purpose register (only HI/LO)
    {"name": "MULU leaves GPRs alone",
     "asm": "li $1, 6\nli $2, 7\nli $3, 77\nmulu $1, $2\n", "reg": 3, "exp": 77},
    {"name": "MULU leaves rs alone",
     "asm": "li $1, 6\nli $2, 7\nmulu $1, $2\nmove $3, $1", "reg": 3, "exp": 6},
    # MUL must not disturb HI/LO
    {"name": "MUL leaves HI alone",
     "asm": "li $1, -1\nli $2, 2\nmulu $1, $2\nli $4, 3\nmul $5, $4, $4\nmfhi $3", "reg": 3, "exp": -1},
    {"name": "MUL leaves LO alone",
     "asm": "li $1, -1\nli $2, 2\nmulu $1, $2\nli $4, 3\nmul $5, $4, $4\nmflo $3", "reg": 3, "exp": -2},
    # HI/LO are overwritten by each MULU
    {"name": "MULU overwrites HI",
     "asm": "li $1, -1\nli $2, 2\nmulu $1, $2\nli $1, 3\nmulu $1, $2\nmfhi $3", "reg": 3, "exp": 0},
    {"name": "MULU overwrites LO",
     "asm": "li $1, -1\nli $2, 2\nmulu $1, $2\nli $1, 3\nmulu $1, $2\nmflo $3", "reg": 3, "exp": 6},
    # MUL with rd == rs and rd == rt
    {"name": "MUL rd == rs", "asm": "li $1, -7\nli $2, 6\nmul $1, $1, $2", "reg": 1, "exp": -42},
    {"name": "MUL rd == rt", "asm": "li $1, -7\nli $2, 6\nmul $2, $1, $2", "reg": 2, "exp": -42},
])

# --- Execute Suite ---
if __name__ == "__main__":
    print(f"Starting MiniRISC Test Suite ({len(tests)} Tests)\n" + "="*50)
    
    subprocess.run(["make", "assembler"], stdout=subprocess.PIPE)
    
    passed = 0
    for t in tests:
        success, err_msg = run_test(t["name"], t["asm"], t["reg"], t["exp"])
        if success:
            passed += 1
        else:
            with open("log.txt", "w") as log_file:
                log_file.write(f"Test Failed: {t['name']}\n")
                log_file.write(err_msg + "\n")
            print("\n🚨 Testing stopped early due to an error. Check log.txt for details.")
            sys.exit(1)
            
    print("="*50 + f"\nResults: {passed}/{len(tests)} Tests Passed")

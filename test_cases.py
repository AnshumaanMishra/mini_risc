"""
test_cases.py - test definitions for run_tests.py (MiniRISC).

Everything here is expressed against the ISA PDF (Assignment 1A) and the way the
RTL/assembler in this repository actually behave where the PDF is silent:

  * PC is a BYTE address in the RTL (+4 per instruction), JAL saves PC+4,
    JR takes a byte address.  (The PDF text says "PC counts words, +1".)
  * Data memory is indexed with address[11:2], so LD/ST use byte addresses that
    are multiples of 4.
  * `li` takes a 16-bit sign-extended immediate; bigger constants use lui+ori.
  * Assembler: registers are $0..$15, JR is written `j $reg`, labels sit on a
    line of their own, no comments (run_tests.py strips comments for you).

Test dictionary keys
  name      test name
  group     group heading
  asm       assembly text. `{@label}` is replaced by the byte address of label.
            `.word 0xXXXXXXXX` emits a raw word (used for illegal opcodes).
  regs      {reg_index: expected}; value int (masked to 32 bit) or "@label"
            (byte address of a label).  All other registers must be 0 unless the
            program writes them.
  hi, lo    expected HI / LO (default: 0 when the program has no MULU)
  final_pc  label where execution must stop (default "__end", the footer HALT)
  visits    labels that MUST be executed          (checked from the VCD)
  skips     labels that must NEVER be executed    (checked from the VCD)
  cycles    watchdog for this test
  check     callable(ctx) -> list[str] of problems (extra VCD-based checks)
  kind      "encode": only assemble and compare words (key "words")
            "ctrl"  : control-word sweep against Appendix A of the PDF
"""

M = 0xFFFFFFFF
MIN, MAX = -0x80000000, 0x7FFFFFFF


def s32(v):
    v &= M
    return v - (1 << 32) if v & 0x80000000 else v


def sx16(v):
    v &= 0xFFFF
    return v - 0x10000 if v & 0x8000 else v


def ld32(reg, val):
    """asm that puts a 32 bit constant in $reg (li is only a 16 bit immediate)."""
    v = s32(val)
    if -0x8000 <= v <= 0x7FFF:
        return f"li ${reg}, {v}"
    u = v & M
    hi, lo = u >> 16, u & 0xFFFF
    out = f"lui ${reg}, {hex(hi)}"
    if lo:
        out += f"\nori ${reg}, ${reg}, {hex(lo)}"
    return out


def T(name, group, asm, regs=None, **kw):
    return {"name": name, "group": group, "asm": asm.strip("\n"),
            "regs": dict(regs or {}), **kw}


# ---------------------------------------------------------------------------
# reference semantics (independent of the RTL)
# ---------------------------------------------------------------------------
R_OPS = {
    "add": lambda a, b: a + b,
    "sub": lambda a, b: a - b,
    "and": lambda a, b: (a & b),
    "or": lambda a, b: (a | b),
    "xor": lambda a, b: (a ^ b),
    "nor": lambda a, b: ~(a | b),
    "sll": lambda a, b: (a & M) << (b & 31),
    "srl": lambda a, b: (a & M) >> (b & 31),
    "sra": lambda a, b: s32(a) >> (b & 31),
    "slt": lambda a, b: int(s32(a) < s32(b)),
    "sgt": lambda a, b: int(s32(a) > s32(b)),
    "sle": lambda a, b: int(s32(a) <= s32(b)),
    "sge": lambda a, b: int(s32(a) >= s32(b)),
    "seq": lambda a, b: int(s32(a) == s32(b)),
    "sne": lambda a, b: int(s32(a) != s32(b)),
}

COMMON_PAIRS = [(0, 0), (1, 1), (5, 10), (10, 5), (-1, 1), (1, -1), (MAX, 1),
                (MIN, 1), (MIN, MAX), (0x12345678, 0x0F0F0F0F),
                (0xAAAAAAAA, 0x55555555), (-7, -7)]
SHIFT_PAIRS = [(1, 0), (1, 1), (1, 31), (1, 32), (1, 33), (0xFFFFFFFF, 1),
               (0x80000000, 31), (0x80000000, 4), (0x12345678, 8), (-8, 2),
               (5, 0x100003), (0x0F0F0F0F, 12)]
CMP_PAIRS = COMMON_PAIRS

I_SEXT = {  # immediate sign-extended
    "addi": R_OPS["add"], "subi": R_OPS["sub"], "slti": R_OPS["slt"],
    "sgti": R_OPS["sgt"], "slei": R_OPS["sle"], "sgei": R_OPS["sge"],
    "seqi": R_OPS["seq"], "snei": R_OPS["sne"],
}
I_ZEXT = {  # immediate zero-extended
    "andi": R_OPS["and"], "ori": R_OPS["or"], "xori": R_OPS["xor"],
    "nori": R_OPS["nor"],
}
I_SHIFT = {"slli": R_OPS["sll"], "srli": R_OPS["srl"], "srai": R_OPS["sra"]}
I_PAIRS = [(0, 0), (5, 10), (5, -10), (-5, 10), (MAX, 1), (MIN, -1),
           (-1, 32767), (1, -32768), (0x12345678, -1), (100, 100),
           (-100, -100), (0xFFFF0000, 0x7FFF)]
I_SHIFT_PAIRS = [(1, 0), (1, 1), (1, 31), (0x80000000, 31), (0x80000000, 1),
                 (-1, 16), (0x12345678, 4), (0x12345678, 28), (-8, 2), (5, 3),
                 (0xFFFFFFFF, 31), (0x0F0F0F0F, 12)]


def build(mulu="signed"):
    t = []

    # =====================================================================
    # R-type ALU (12 vectors per op, one destination register per vector)
    # =====================================================================
    for op, fn in R_OPS.items():
        pairs = SHIFT_PAIRS if op in ("sll", "srl", "sra") else COMMON_PAIRS
        lines, regs = [], {}
        for k, (a, b) in enumerate(pairs):
            lines += [ld32(1, a), ld32(2, b), f"{op} ${3 + k}, $1, $2"]
            regs[3 + k] = fn(a, b) & M
        regs[1], regs[2] = pairs[-1][0] & M, pairs[-1][1] & M
        t.append(T(f"{op.upper()} 12 vectors", "R-type ALU", "\n".join(lines), regs))

    lines, regs = [], {}
    vals = [0, -1, 1, 0x0F0F0F0F, 0xAAAAAAAA, MIN, MAX, 0x12345678]
    for k, a in enumerate(vals):
        lines += [ld32(1, a), f"not ${3 + k}, $1"]
        regs[3 + k] = ~a & M
    regs[1] = vals[-1] & M
    t.append(T("NOT 8 vectors", "R-type ALU", "\n".join(lines), regs))
    t.append(T("NOT rd == rs", "R-type ALU", "li $1, 0x0F0F\nnot $1, $1", {1: ~0x0F0F}))

    # operand aliasing
    t += [
        T("ADD rd == rs == rt", "R-type ALU", "li $1, 5\nadd $1, $1, $1\nadd $1, $1, $1", {1: 20}),
        T("SUB rs == rt gives 0", "R-type ALU", "li $1, 77\nsub $3, $1, $1", {1: 77, 3: 0}),
        T("SUB rd == rt", "R-type ALU", "li $1, 10\nli $2, 3\nsub $2, $1, $2", {1: 10, 2: 7}),
        T("XOR rs == rt gives 0", "R-type ALU", "li $1, 0x1234\nxor $3, $1, $1", {1: 0x1234, 3: 0}),
        T("Use $15 as operand and destination", "R-type ALU",
          "li $15, 3\nli $14, 4\nadd $15, $15, $14\nmove $13, $15", {15: 7, 14: 4, 13: 7}),
    ]

    # =====================================================================
    # I-type ALU
    # =====================================================================
    for op, fn in I_SEXT.items():
        lines, regs = [], {}
        for k, (a, imm) in enumerate(I_PAIRS):
            lines += [ld32(1, a), f"{op} ${3 + k}, $1, {imm}"]
            regs[3 + k] = fn(a, sx16(imm)) & M
        regs[1] = I_PAIRS[-1][0] & M
        t.append(T(f"{op.upper()} 12 vectors (imm sign-ext)", "I-type ALU", "\n".join(lines), regs))
    for op, fn in I_ZEXT.items():
        lines, regs = [], {}
        for k, (a, imm) in enumerate(I_PAIRS):
            imm16 = imm & 0xFFFF
            lines += [ld32(1, a), f"{op} ${3 + k}, $1, {hex(imm16)}"]
            regs[3 + k] = fn(a, imm16) & M
        regs[1] = I_PAIRS[-1][0] & M
        t.append(T(f"{op.upper()} 12 vectors (imm zero-ext)", "I-type ALU", "\n".join(lines), regs))
    for op, fn in I_SHIFT.items():
        lines, regs = [], {}
        for k, (a, amt) in enumerate(I_SHIFT_PAIRS):
            lines += [ld32(1, a), f"{op} ${3 + k}, $1, {amt}"]
            regs[3 + k] = fn(a, amt) & M
        regs[1] = I_SHIFT_PAIRS[-1][0] & M
        t.append(T(f"{op.upper()} 12 vectors", "I-type ALU", "\n".join(lines), regs))
    t += [
        T("ADDI rd == rs (counter)", "I-type ALU", "li $1, 0\naddi $1, $1, 1\naddi $1, $1, 1\naddi $1, $1, 1", {1: 3}),
        T("ADDI $0 source", "I-type ALU", "addi $3, $0, 1234\naddi $4, $0, -1234", {3: 1234, 4: -1234}),
        T("ANDI 0xFFFF does not sign-extend", "I-type ALU", "li $1, -1\nandi $3, $1, 0xFFFF", {1: M, 3: 0xFFFF}),
        T("ORI 0x8000 does not sign-extend", "I-type ALU", "ori $3, $0, 0x8000", {3: 0x8000}),
        T("SLTI sign-extended imm", "I-type ALU", "li $1, -3\nslti $3, $1, -2", {1: -3, 3: 1}),
        T("INC / DEC idioms", "I-type ALU", "li $1, 9\naddi $1, $1, 1\nli $2, 9\nsubi $2, $2, 1", {1: 10, 2: 8}),
    ]

    # =====================================================================
    # Constants / moves / HI-LO reads
    # =====================================================================
    lines, regs = [], {}
    for k, v in enumerate([0, 1, -1, 32767, -32768, 255, -256, 12345, -12345, 100, -100, 4096]):
        lines.append(f"li ${3 + k}, {v}")
        regs[3 + k] = v & M
    t.append(T("LI 12 vectors", "Constants / moves", "\n".join(lines), regs))
    lines, regs = [], {}
    for k, v in enumerate([0x0000, 0x0001, 0x8000, 0xFFFF, 0x1234, 0xABCD, 0x7FFF, 0x00FF]):
        lines.append(f"lui ${3 + k}, {hex(v)}")
        regs[3 + k] = (v << 16) & M
    t.append(T("LUI 8 vectors", "Constants / moves", "\n".join(lines), regs))
    t += [
        T("LUI clears low half", "Constants / moves", "li $3, -1\nlui $3, 1", {3: 0x10000}),
        T("LI overwrites upper half", "Constants / moves", "lui $3, 0xFFFF\nli $3, 5", {3: 5}),
        T("LUI + ORI builds 0xDEADBEEF", "Constants / moves", "lui $1, 0xDEAD\nori $1, $1, 0xBEEF", {1: 0xDEADBEEF}),
        T("LUI + ORI builds 0x80000000 / 0x7FFFFFFF", "Constants / moves",
          "lui $1, 0x8000\nlui $2, 0x7FFF\nori $2, $2, 0xFFFF", {1: 0x80000000, 2: 0x7FFFFFFF}),
        T("MOVE 5 vectors", "Constants / moves",
          "\n".join(f"{ld32(1, v)}\nmove ${3 + k}, $1" for k, v in enumerate([0, 1, -1, MIN, 0x12345678]))
          , {1: 0x12345678, 3: 0, 4: 1, 5: M, 6: 0x80000000, 7: 0x12345678}),
        T("MOVE rd == rs", "Constants / moves", "li $1, 42\nmove $1, $1", {1: 42}),
        T("MOVE from $0 clears a register", "Constants / moves", "li $1, 42\nmove $1, $0", {1: 0}),
        T("MFHI / MFLO read 0 before any MULU", "Constants / moves", "li $3, 9\nli $4, 9\nmfhi $3\nmflo $4", {3: 0, 4: 0}),
    ]

    # =====================================================================
    # Register file
    # =====================================================================
    t += [
        T("R1..R15 are independent", "Register file",
          "\n".join(f"li ${i}, {i * 1111}" for i in range(1, 16)), {i: i * 1111 for i in range(1, 16)}),
        T("Write to $0 ignored (LI)", "Register file", "li $0, 55\nmove $3, $0\nadd $4, $0, $0", {3: 0, 4: 0}),
        T("Write to $0 ignored (ADD)", "Register file", "li $1, 9\nadd $0, $1, $1\nadd $3, $0, $1", {1: 9, 3: 9}),
        T("Write to $0 ignored (LUI/ADDI/MOVE)", "Register file",
          "lui $0, 0x1234\naddi $0, $0, 7\nli $1, 3\nmove $0, $1\nadd $3, $0, $1", {1: 3, 3: 3}),
        T("Write to $0 ignored (LD / MFLO)", "Register file",
          "li $1, 8\nst $1, 0($0)\nld $0, 0($0)\nadd $3, $0, $1\nmflo $0\nadd $4, $0, $1",
          {1: 8, 3: 8, 4: 8}),
        T("Write to $0 ignored (JAL does not clobber it)", "Register file",
          "jal f\nf:\nadd $3, $0, $0", {3: 0, 15: "@f"}),
        T("Two read ports (rs != rt) at once", "Register file",
          "li $1, 3\nli $2, 4\nadd $3, $1, $2\nsub $4, $2, $1\nsub $5, $1, $2", {1: 3, 2: 4, 3: 7, 4: 1, 5: -1}),
        T("Writing one register leaves neighbours", "Register file",
          "li $7, 7\nli $8, 8\nli $9, 9\nli $8, 80", {7: 7, 8: 80, 9: 9}),
    ]

    # =====================================================================
    # Multiply
    # =====================================================================
    mpairs = [(0, 5), (10, 5), (-10, 5), (10, -5), (-10, -5), (-1, -1), (MAX, MAX),
              (MIN, MIN), (MIN, -1), (MAX, MIN), (0x10000, 0x10001), (0x12345678, 0x10000)]
    lines, regs = [], {}
    for k, (a, b) in enumerate(mpairs):
        lines += [ld32(1, a), ld32(2, b), f"mul ${3 + k}, $1, $2"]
        regs[3 + k] = (s32(a) * s32(b)) & M
    regs[1], regs[2] = mpairs[-1][0] & M, mpairs[-1][1] & M
    t.append(T("MUL 12 vectors (low 32 bits)", "Multiply", "\n".join(lines), regs))

    def prod(a, b):
        p = (s32(a) * s32(b)) if mulu == "signed" else ((a & M) * (b & M))
        return (p >> 32) & M, p & M

    upairs = [(6, 7), (-1, 2), (-1, -1), (MIN, MIN), (MAX, MAX), (MIN, 2),
              (0xFFFFFFFF, 0xFFFFFFFF), (0x80000000, 0x80000000), (0x12345678, 0x10000),
              (0xF0000000, 0x10), (0x00010000, 0x00010000), (0, 12345)]
    for a, b in upairs:
        hi, lo = prod(a, b)
        t.append(T(f"MULU {s32(a)} * {s32(b)} (HI:LO)", "Multiply",
                   f"{ld32(1, a)}\n{ld32(2, b)}\nmulu $1, $2\nmfhi $3\nmflo $4",
                   {1: a & M, 2: b & M, 3: hi, 4: lo}, hi=hi, lo=lo))
    hi, lo = prod(-1, 2)
    t += [
        T("MULU writes no general register", "Multiply",
          "li $1, 6\nli $2, 7\nli $3, 77\nmulu $1, $2", {1: 6, 2: 7, 3: 77}, hi=0, lo=42),
        T("MULU rd field is 0 (HI/LO still written)", "Multiply",
          "li $1, 3\nli $2, 4\nmulu $1, $2\nmflo $5", {1: 3, 2: 4, 5: 12}, hi=0, lo=12),
        T("MUL leaves HI/LO alone", "Multiply",
          "li $1, -1\nli $2, 2\nmulu $1, $2\nli $5, 3\nmul $6, $5, $5\nmfhi $3\nmflo $4",
          {1: M, 2: 2, 3: hi, 4: lo, 5: 3, 6: 9}, hi=hi, lo=lo),
        T("MULU overwrites both HI and LO", "Multiply",
          "li $1, -1\nli $2, 2\nmulu $1, $2\nli $1, 3\nmulu $1, $2\nmfhi $3\nmflo $4",
          {1: 3, 2: 2, 3: 0, 4: 6}, hi=0, lo=6),
        T("HI/LO survive ALU/mem ops and repeated reads", "Multiply",
          "li $1, 5\nli $2, 6\nmulu $1, $2\nadd $5, $1, $2\nst $5, 0($0)\nld $6, 0($0)\nmflo $3\nmflo $4\nmfhi $7",
          {1: 5, 2: 6, 3: 30, 4: 30, 5: 11, 6: 11, 7: 0}, hi=0, lo=30),
        T("MUL rd == rs", "Multiply", "li $1, -7\nli $2, 6\nmul $1, $1, $2", {1: -42, 2: 6}),
        T("MUL rd == rt", "Multiply", "li $1, -7\nli $2, 6\nmul $2, $1, $2", {1: -7, 2: -42}),
        T("MUL result usable by next instruction", "Multiply",
          "li $1, 6\nli $2, 7\nmul $3, $1, $2\nadd $4, $3, $3", {1: 6, 2: 7, 3: 42, 4: 84}),
        T("MUL back-to-back dependent", "Multiply",
          "li $1, 3\nli $2, 4\nmul $3, $1, $2\nmul $4, $3, $3\nmul $5, $4, $3",
          {1: 3, 2: 4, 3: 12, 4: 144, 5: 1728}),
        T("MUL neither skips nor repeats the next instruction", "Multiply",
          "li $3, 0\nli $1, 2\nmul $4, $1, $1\naddi $3, $3, 1", {1: 2, 3: 1, 4: 4}),
        T("MUL by zero / by one", "Multiply",
          "li $1, 1234\nmul $3, $1, $0\nli $2, 1\nmul $4, $1, $2", {1: 1234, 2: 1, 3: 0, 4: 1234}),
    ]

    # =====================================================================
    # Memory (byte addresses, multiples of 4)
    # =====================================================================
    lines, regs = [], {}
    for k in range(12):
        lines.append(f"li $1, {100 + k}\nst $1, {4 * k}($0)")
    for k in range(12):
        lines.append(f"ld ${3 + k}, {4 * (11 - k)}($0)")
        regs[3 + k] = 100 + 11 - k
    regs[1] = 111
    t.append(T("ST 12 words, LD back in reverse", "Memory", "\n".join(lines), regs))
    t += [
        T("LD/ST basic", "Memory", "li $1, 42\nst $1, 8($0)\nld $3, 8($0)", {1: 42, 3: 42}),
        T("LD/ST negative data", "Memory", "li $1, -100\nli $2, 4\nst $1, 12($2)\nld $3, 12($2)", {1: -100, 2: 4, 3: -100}),
        T("LD/ST full 32-bit word", "Memory",
          f"{ld32(1, 0xA5A5C3C3)}\nst $1, 8($0)\nld $3, 8($0)", {1: 0xA5A5C3C3, 3: 0xA5A5C3C3}),
        T("Base register + positive offset", "Memory",
          "li $1, 77\nli $2, 16\nst $1, 8($2)\nld $3, 24($0)", {1: 77, 2: 16, 3: 77}),
        T("Base register + negative offset", "Memory",
          "li $1, 77\nli $2, 40\nst $1, -8($2)\nld $3, 32($0)\nld $4, -8($2)", {1: 77, 2: 40, 3: 77, 4: 77}),
        T("Overwrite same address", "Memory",
          "li $1, 1\nli $2, 2\nst $1, 8($0)\nst $2, 8($0)\nld $3, 8($0)", {1: 1, 2: 2, 3: 2}),
        T("Unwritten memory reads 0", "Memory", "ld $3, 400($0)\nld $4, 0($0)", {3: 0, 4: 0}),
        T("Distinct words do not alias", "Memory",
          "li $1, 11\nli $2, 22\nst $1, 0($0)\nst $2, 4($0)\nld $5, 0($0)\nld $6, 4($0)",
          {1: 11, 2: 22, 5: 11, 6: 22}),
        T("Highest word of the 1K-word RAM", "Memory",
          "li $1, 321\nst $1, 4092($0)\nld $3, 4092($0)\nld $4, 0($0)", {1: 321, 3: 321, 4: 0}),
        T("LD result usable by next instruction", "Memory",
          "li $1, 21\nst $1, 0($0)\nld $3, 0($0)\nadd $4, $3, $3", {1: 21, 3: 21, 4: 42}),
        T("LD rd == base register", "Memory",
          "li $1, 5\nli $2, 12\nst $1, 12($0)\nld $2, 0($2)", {1: 5, 2: 5}),
        T("LD back-to-back", "Memory",
          "li $1, 1\nli $2, 2\nst $1, 0($0)\nst $2, 4($0)\nld $3, 0($0)\nld $4, 4($0)\nld $5, 0($0)",
          {1: 1, 2: 2, 3: 1, 4: 2, 5: 1}),
        T("ST does not write a register / no side effects", "Memory",
          "li $1, 9\nli $2, 8\nst $1, 0($2)", {1: 9, 2: 8}),
        T("ST value taken from rd field (all regs)", "Memory",
          "\n".join(f"li ${i}, {i * 7}\nst ${i}, {4 * i}($0)" for i in range(1, 16)) + "\nli $2, 0\n"
          + "\n".join(f"ld $1, {4 * i}($0)\nadd $2, $2, $1" for i in range(1, 16)),
          {**{i: i * 7 for i in range(3, 16)}, 1: 15 * 7, 2: sum(i * 7 for i in range(1, 16))}),
        T("LD uses a stall cycle (2 cycles) - PC held", "Memory",
          "li $1, 5\nst $1, 0($0)\nldi:\nld $3, 0($0)\nnop", {1: 5, 3: 5}, check="ld_timing"),
    ]

    # =====================================================================
    # Branches
    # =====================================================================
    def branch_vec(op, pairs, cond, one_reg=False):
        lines, regs = [], {}
        for k, (a, b) in enumerate(pairs):
            d = 3 + k
            lines.append(ld32(1, a))
            if not one_reg:
                lines.append(ld32(2, b))
            lines += [f"li ${d}, 0",
                      f"{op} $1, " + ("" if one_reg else "$2, ") + f"t{k}",
                      f"j n{k}", f"t{k}:", f"li ${d}, 1", f"n{k}:"]
            regs[d] = int(cond(a, b))
        regs[1] = pairs[-1][0] & M
        if not one_reg:
            regs[2] = pairs[-1][1] & M
        return "\n".join(lines), regs

    BP = [(5, 5), (4, 5), (5, 4), (0, 0), (-1, 1), (1, -1), (MIN, MAX), (MAX, MIN),
          (MIN, MIN), (-5, -5), (MAX, -1), (-1, MAX)]
    conds = {
        "beq": lambda a, b: s32(a) == s32(b), "bne": lambda a, b: s32(a) != s32(b),
        "blt": lambda a, b: s32(a) < s32(b), "ble": lambda a, b: s32(a) <= s32(b),
        "bgt": lambda a, b: s32(a) > s32(b), "bge": lambda a, b: s32(a) >= s32(b),
    }
    for op, c in conds.items():
        asm, regs = branch_vec(op, BP, c)
        t.append(T(f"{op.upper()} 12 vectors (taken / not taken)", "Branches", asm, regs))
    asm, regs = branch_vec("bz", [(v, 0) for v in [0, 1, -1, MIN, MAX, 0x10000, 0xFFFF, 2, 0, -2, 0x8000, 3]],
                           lambda a, b: s32(a) == 0, one_reg=True)
    t.append(T("BZ 12 vectors", "Branches", asm, regs))
    bvp = [(MIN, 1), (MAX, -1), (MAX, 1), (0, MIN), (5, 3), (MIN, MIN), (MIN, -1), (3, 5),
           (0, MAX), (-1, MIN), (MAX, MIN), (-5, 5)]
    asm, regs = branch_vec("bv", bvp, lambda a, b: not (-(1 << 31) <= s32(a) - s32(b) < (1 << 31)))
    t.append(T("BV 12 vectors (overflow of rs - rd)", "Branches", asm, regs))
    t += [
        T("BMI via BLT rs,$0 (negative)", "Branches",
          "li $1, -4\nli $3, 0\nblt $1, $0, t\nj e\nt:\nli $3, 1\ne:", {1: -4, 3: 1}),
        T("BPL via BGE rs,$0 (positive)", "Branches",
          "li $1, 4\nli $3, 0\nbge $1, $0, t\nj e\nt:\nli $3, 1\ne:", {1: 4, 3: 1}),
        T("BPL not taken for negative", "Branches",
          "li $1, -4\nli $3, 0\nbge $1, $0, t\nj e\nt:\nli $3, 1\ne:", {1: -4, 3: 0}),
        T("Taken branch skips several instructions", "Branches",
          "li $3, 0\nbeq $0, $0, t\nbad1:\nli $3, 1\nli $3, 2\nli $3, 3\nt:\nnop", {3: 0}, skips=["bad1"], visits=["t"]),
        T("Not-taken branch falls through", "Branches",
          "li $3, 0\nbne $0, $0, t\nok:\nli $3, 1\nt:\nnop", {3: 1}, visits=["ok"]),
        T("Branch to next instruction (offset 0)", "Branches",
          "li $3, 5\nbeq $0, $0, nx\nnx:\naddi $3, $3, 1", {3: 6}),
        T("Branch back-to-back taken", "Branches",
          "li $3, 0\nbeq $0, $0, la\nbad:\nli $3, 9\nla:\nbeq $0, $0, lb\nli $3, 9\nlb:\naddi $3, $3, 1", {3: 1}, skips=["bad"]),
        T("Backward branch loop (sum 1..5)", "Branches",
          "li $1, 5\nli $2, 0\nloop:\nadd $2, $2, $1\nsubi $1, $1, 1\nbne $1, $0, loop", {1: 0, 2: 15}),
        T("Far forward branch (200 NOPs)", "Branches",
          "li $3, 0\nbeq $0, $0, far\nbad:\nli $3, 1\n" + "nop\n" * 200 + "far:\naddi $3, $3, 7", {3: 7}, skips=["bad"]),
        T("Far backward branch (150 NOPs)", "Branches",
          "li $3, 0\nj skipbody\nbody:\naddi $3, $3, 1\nj out\nskipbody:\n" + "nop\n" * 150
          + "beq $0, $0, body\nbad:\nli $3, 99\nout:\nnop", {3: 1}, skips=["bad"]),
        T("Branch compares do not change registers", "Branches",
          "li $1, 3\nli $2, 4\nblt $1, $2, t\nt:\nbge $1, $2, u\nu:", {1: 3, 2: 4}),
    ]

    # =====================================================================
    # Jumps
    # =====================================================================
    t += [
        T("J forward skips instructions", "Jumps", "li $3, 0\nj t\nbad:\nli $3, 1\nli $3, 2\nt:\naddi $3, $3, 5", {3: 5}, skips=["bad"]),
        T("J backward", "Jumps",
          "li $3, 0\nj skip\nback:\naddi $3, $3, 5\nj end2\nskip:\naddi $3, $3, 2\nj back\nend2:\nnop", {3: 7}),
        T("`b` alias behaves like J", "Jumps", "li $3, 1\nb t\nbad:\nli $3, 2\nt:\nnop", {3: 1}, skips=["bad"]),
        T("J to the next instruction", "Jumps", "li $3, 4\nj nx\nnx:\naddi $3, $3, 1", {3: 5}),
        T("JAL link = address of next instruction", "Jumps",
          "jal f\nbad:\nnop\nf:\nnop", {15: "@bad"}),
        T("JAL link at a later address", "Jumps",
          "li $1, 0\nli $2, 0\njal f\nra:\nnop\nf:\nnop", {15: "@ra"}),
        T("JAL jumps to its target", "Jumps", "li $3, 1\njal f\nbad:\nli $3, 2\nf:\naddi $3, $3, 10", {3: 11, 15: "@bad"}, skips=["bad"]),
        T("JR returns through the link register", "Jumps",
          "li $3, 0\njal inc\nra1:\njal inc\nra2:\nj fin\ninc:\naddi $3, $3, 1\nj $15\nfin:\nnop",
          {3: 2, 15: "@ra2"}, visits=["ra1", "ra2"]),
        T("JR to a computed address", "Jumps",
          "li $5, {@t}\nli $3, 0\nj $5\nbad:\nli $3, 1\nt:\naddi $3, $3, 3", {5: "@t", 3: 3}, skips=["bad"]),
        T("JR with a register other than $15", "Jumps",
          "li $9, {@t}\nj $9\nbad:\nli $3, 1\nt:\nli $3, 8", {9: "@t", 3: 8}, skips=["bad"]),
        T("Nested JAL (inner overwrites $15)", "Jumps",
          "jal fa\nra0:\nj fin\nfa:\njal fb\nra1:\nj fin\nfb:\nnop\nfin:\nnop", {15: "@ra1"}),
        T("J chain forward and backward", "Jumps",
          "li $3, 0\nj la\nbad:\nli $3, 99\nlb:\naddi $3, $3, 2\nj lc\nla:\naddi $3, $3, 1\nj lb\nlc:\naddi $3, $3, 4", {3: 7}, skips=["bad"]),
    ]

    # =====================================================================
    # NOP / HALT / illegal opcodes
    # =====================================================================
    t += [
        T("NOP has no side effects", "NOP / HALT / illegal", "li $1, 5\nnop\nnop\naddi $3, $1, 1", {1: 5, 3: 6}),
        T("100 NOPs only advance the PC", "NOP / HALT / illegal", "nop\n" * 100 + "li $3, 4", {3: 4}),
        T("HALT: later instructions not executed", "NOP / HALT / illegal",
          "li $3, 1\nh:\nhalt\nbad:\nli $3, 2", {3: 1}, final_pc="h", skips=["bad"]),
        T("HALT after a multi-cycle LD", "NOP / HALT / illegal",
          "li $1, 7\nst $1, 0($0)\nld $3, 0($0)\nh:\nhalt\nbad:\nli $3, 0", {1: 7, 3: 7}, final_pc="h", skips=["bad"]),
        T("HALT after a MUL", "NOP / HALT / illegal",
          "li $1, 2\nmul $3, $1, $1\nh:\nhalt\nbad:\nli $3, 0", {1: 2, 3: 4}, final_pc="h", skips=["bad"]),
        T("HALT after a taken branch", "NOP / HALT / illegal",
          "li $3, 1\nbeq $0, $0, t\nbad:\nli $3, 2\nt:\nh:\nhalt\nbad2:\nli $3, 3", {3: 1}, final_pc="h", skips=["bad", "bad2"]),
        T("HALT as the first instruction", "NOP / HALT / illegal", "h:\nhalt\nbad:\nli $3, 1", {}, final_pc="h", skips=["bad"]),
        T("HALT freezes PC and FSM", "NOP / HALT / illegal", "li $3, 1\nh:\nhalt", {3: 1}, final_pc="h", check="halt_frozen"),
    ]
    illegal = [0b000001, 0b000111, 0b001111, 0b011000, 0b011111, 0b101010, 0b101100, 0b101111]
    for op in illegal:
        t.append(T(f"Illegal opcode {op:06b} stops the processor", "NOP / HALT / illegal",
                   f"li $3, 1\nbadop:\n.word {hex(op << 26)}\nafter:\nli $3, 2", {3: 1},
                   final_pc="badop", skips=["after"]))

    # =====================================================================
    # Sample programs
    # =====================================================================
    def fib(n):
        a, b, c = 0, 1, 0
        for _ in range(n):
            c = a + b
            a, b = b, c
        return a, b, c

    a, b, c = fib(10)
    t.append(T("Fibonacci(10)", "Sample programs",
               "li $1, 0\nli $2, 1\nli $4, 10\nloop:\nbz $4, done\nadd $3, $1, $2\nmove $1, $2\nmove $2, $3\n"
               "subi $4, $4, 1\nj loop\ndone:\nnop", {1: a, 2: b, 3: c, 4: 0}))
    t.append(T("Factorial(10) with MUL", "Sample programs",
               "li $1, 1\nli $2, 10\nloop:\nbz $2, done\nmul $1, $1, $2\nsubi $2, $2, 1\nj loop\ndone:\nnop",
               {1: 3628800, 2: 0}))
    t.append(T("Sum 1..100", "Sample programs",
               "li $1, 0\nli $2, 100\nl:\nadd $1, $1, $2\nsubi $2, $2, 1\nbne $2, $0, l", {1: 5050, 2: 0}))
    t.append(T("Sum of squares 1..10 (MUL in a loop)", "Sample programs",
               "li $1, 0\nli $2, 10\nl:\nmul $3, $2, $2\nadd $1, $1, $3\nsubi $2, $2, 1\nbne $2, $0, l",
               {1: 385, 2: 0, 3: 1}))
    data = [3, -1, 4, 1, -5, 9, 2, 6]
    st = "\n".join(f"li $1, {v}\nst $1, {4 * k}($0)" for k, v in enumerate(data))
    t.append(T("Array sum in memory", "Sample programs",
               st + "\nli $5, 0\nli $6, 32\nli $7, 0\nl:\nld $8, 0($5)\nadd $7, $7, $8\naddi $5, $5, 4\nbne $5, $6, l",
               {1: data[-1], 5: 32, 6: 32, 7: sum(data), 8: data[-1]}))
    # bubble sort (fixed 5 passes x 5 compares), with a python mirror for the last compare
    arr = [5, 2, 9, 1, 7, 3]
    mem = arr[:]
    la = lb = 0
    for _ in range(5):
        for j in range(5):
            la, lb = mem[j], mem[j + 1]
            if not la <= lb:
                mem[j], mem[j + 1] = lb, la
    st = "\n".join(f"li $1, {v}\nst $1, {4 * k}($0)" for k, v in enumerate(arr))
    t.append(T("Bubble sort 6 words", "Sample programs",
               st + "\nli $9, 5\nouter:\nli $5, 0\nli $6, 5\ninner:\nld $7, 0($5)\nld $8, 4($5)\nble $7, $8, noswap\n"
               "st $8, 0($5)\nst $7, 4($5)\nnoswap:\naddi $5, $5, 4\nsubi $6, $6, 1\nbne $6, $0, inner\n"
               "subi $9, $9, 1\nbne $9, $0, outer\n"
               "ld $10, 0($0)\nld $11, 4($0)\nld $12, 8($0)\nld $13, 12($0)\nld $14, 16($0)\nld $4, 20($0)",
               {1: arr[-1], 4: mem[5], 5: 20, 6: 0, 7: la, 8: lb, 9: 0,
                10: mem[0], 11: mem[1], 12: mem[2], 13: mem[3], 14: mem[4]}, cycles=8000))
    t.append(T("GCD(48,18) by subtraction", "Sample programs",
               "li $1, 48\nli $2, 18\nl:\nbeq $1, $2, d\nblt $1, $2, less\nsub $1, $1, $2\nj l\nless:\nsub $2, $2, $1\nj l\nd:\nnop",
               {1: 6, 2: 6}))
    t.append(T("Subroutine: square via JAL / JR", "Sample programs",
               "li $1, 7\njal sq\nra1:\nmove $4, $2\nli $1, 9\njal sq\nra2:\nmove $5, $2\nj fin\nsq:\nmul $2, $1, $1\nj $15\nfin:\nnop",
               {1: 9, 2: 81, 4: 49, 5: 81, 15: "@ra2"}, visits=["ra1", "ra2"]))
    t.append(T("Nested calls, link saved in memory", "Sample programs",
               "li $10, 1\njal outerf\nraA:\nj fin\nouterf:\nst $15, 0($0)\naddi $10, $10, 10\njal innerf\nld $15, 0($0)\nj $15\n"
               "innerf:\naddi $10, $10, 100\nj $15\nfin:\nnop", {10: 111, 15: "@raA"}))
    v = 0x80F00F01
    pop = bin(v).count("1")
    t.append(T("Population count of 0x80F00F01", "Sample programs",
               f"{ld32(1, v)}\nli $2, 0\nl:\nbz $1, d\nandi $3, $1, 1\nadd $2, $2, $3\nsrli $1, $1, 1\nj l\nd:\nnop",
               {1: 0, 2: pop, 3: 1}))
    n, steps, last5 = 27, 0, 0
    last3 = 0
    while n != 1:
        last3 = n & 1
        if n & 1:
            last5 = 2 * n
            n = last5 + n + 1
        else:
            n >>= 1
        steps += 1
    t.append(T("Collatz(27) = 111 steps", "Sample programs",
               "li $1, 27\nli $2, 0\nli $4, 1\nl:\nbeq $1, $4, d\nandi $3, $1, 1\nbz $3, even\nadd $5, $1, $1\nadd $1, $5, $1\n"
               "addi $1, $1, 1\nj cont\neven:\nsrli $1, $1, 1\ncont:\naddi $2, $2, 1\nj l\nd:\nnop",
               {1: 1, 2: steps, 3: last3, 4: 1, 5: last5}, cycles=6000))
    src = [10, 20, 30, 40, 50]
    st = "\n".join(f"li $1, {v}\nst $1, {4 * k}($0)" for k, v in enumerate(src))
    t.append(T("memcpy 5 words + checksum", "Sample programs",
               st + "\nli $5, 0\nli $6, 20\nc:\nld $8, 0($5)\nst $8, 64($5)\naddi $5, $5, 4\nbne $5, $6, c\n"
               "li $5, 0\nli $9, 0\ns:\nld $8, 64($5)\nadd $9, $9, $8\naddi $5, $5, 4\nbne $5, $6, s",
               {1: 50, 5: 20, 6: 20, 8: 50, 9: 150}))
    a64, b64 = 0x12345678, 0x0ABCDEF1
    p = a64 * b64
    t.append(T("64-bit product via MULU + MFHI/MFLO", "Sample programs",
               f"{ld32(1, a64)}\n{ld32(2, b64)}\nmulu $1, $2\nmfhi $3\nmflo $4\nmul $5, $1, $2",
               {1: a64, 2: b64, 3: p >> 32, 4: p & M, 5: p & M}, hi=p >> 32, lo=p & M))

    # =====================================================================
    # Structural / VCD-only checks
    # =====================================================================
    t.append({"name": "Control words of all 53 instructions (Appendix A)", "group": "Control words",
              "kind": "ctrl", "regs": {}, "asm": CTRL_SWEEP, "cycles": 4000})

    # =====================================================================
    # Assembler encodings (no simulation)
    # =====================================================================
    t += encoding_tests()
    return t


# Every instruction executed once; used for the Appendix A control-word check.
CTRL_SWEEP = """
li $1, 5
li $2, 3
add $3, $1, $2
sub $3, $1, $2
mul $3, $1, $2
mulu $1, $2
and $3, $1, $2
or $3, $1, $2
not $3, $1
nor $3, $1, $2
xor $3, $1, $2
sll $3, $1, $2
srl $3, $1, $2
sra $3, $1, $2
slt $3, $1, $2
sgt $3, $1, $2
sle $3, $1, $2
sge $3, $1, $2
seq $3, $1, $2
sne $3, $1, $2
addi $3, $1, 7
subi $3, $1, 7
andi $3, $1, 7
ori $3, $1, 7
nori $3, $1, 7
xori $3, $1, 7
slli $3, $1, 2
srli $3, $1, 2
srai $3, $1, 2
slti $3, $1, 7
sgti $3, $1, 7
slei $3, $1, 7
sgei $3, $1, 7
seqi $3, $1, 7
snei $3, $1, 7
li $4, 100
lui $4, 0x1234
move $4, $1
mfhi $4
mflo $4
st $1, 0($0)
ld $4, 0($0)
nop
beq $1, $1, b1
b1:
bz $0, b2
b2:
bne $1, $2, b3
b3:
blt $2, $1, b4
b4:
ble $2, $1, b5
b5:
bgt $1, $2, b6
b6:
bge $1, $2, b7
b7:
bv $1, $2, b8
b8:
j j1
j1:
jal j2
j2:
addi $15, $15, 8
j $15
nop
"""

# ---------------------------------------------------------------------------
# Assembler encoding tests, written independently from the PDF tables (3.1)
# ---------------------------------------------------------------------------
RFN = {"add": 0b010000, "sub": 0b010001, "mul": 0b010010, "mulu": 0b010011,
       "and": 0b011000, "or": 0b011001, "not": 0b011010, "nor": 0b011011,
       "xor": 0b011100, "sll": 0b100000, "srl": 0b100001, "sra": 0b100010,
       "slt": 0b001000, "sgt": 0b001001, "sle": 0b001010, "sge": 0b001011,
       "seq": 0b001100, "sne": 0b001101}
IOP = {"addi": 0b110000, "subi": 0b110001, "andi": 0b110010, "ori": 0b110011,
       "nori": 0b110100, "xori": 0b110101, "slli": 0b110110, "srli": 0b110111,
       "srai": 0b111000, "slti": 0b111001, "sgti": 0b111010, "slei": 0b111011,
       "sgei": 0b111100, "seqi": 0b111101, "snei": 0b111110}
BOP = {"beq": 0b010000, "bz": 0b010001, "bne": 0b010010, "blt": 0b010011,
       "ble": 0b010100, "bgt": 0b010101, "bge": 0b010110, "bv": 0b010111}


def encoding_tests():
    out = []

    def mk(name, items):
        asm, words = [], []
        for text, w in items:
            asm.append(text)
            words.append(w & M)
        return {"name": name, "group": "Assembler encodings", "kind": "encode",
                "asm": "\n".join(asm), "words": words, "regs": {}}

    # examples printed in section 3.2 of the PDF
    out.append(mk("PDF section 3.2 examples", [
        ("addi $1, $0, 5", 0xC0200005), ("addi $2, $0, 7", 0xC0400007),
        ("add $3, $1, $2", 0x80611010), ("mulu $2, $3", 0x80021813),
        ("lui $1, 0x1234", 0x8C201234), ("ld $4, 8($5)", 0x94850008),
        ("st $6, -4($7)", 0x98C7FFFC), ("beq $1, $2, 44", 0x40410003),
        ("j 64", 0xA0000010), ("nop", 0x00000000), ("halt", 0xFC000000)]))

    samples = [(1, 2, 3), (15, 14, 13), (7, 0, 9)]
    items = []
    for op, fn in RFN.items():
        for rd, rs, rt in samples:
            if op == "mulu":
                items.append((f"mulu ${rs}, ${rt}", 0x80000000 | rs << 16 | rt << 11 | fn))
            elif op == "not":
                items.append((f"not ${rd}, ${rs}", 0x80000000 | rd << 21 | rs << 16 | fn))
            else:
                items.append((f"{op} ${rd}, ${rs}, ${rt}", 0x80000000 | rd << 21 | rs << 16 | rt << 11 | fn))
    out.append(mk("R-type ALU instructions (fn field)", items))

    items = []
    for op, o in IOP.items():
        for rd, rs, imm in [(1, 2, 5), (15, 14, -1), (3, 0, 0x7FFF), (4, 5, -32768)]:
            items.append((f"{op} ${rd}, ${rs}, {imm}", o << 26 | rd << 21 | rs << 16 | (imm & 0xFFFF)))
    out.append(mk("I-type ALU instructions", items))

    items = []
    for rd, imm in [(1, 5), (15, -1), (3, 0x7FFF), (4, -32768)]:
        items.append((f"li ${rd}, {imm}", 0b100010 << 26 | rd << 21 | (imm & 0xFFFF)))
        items.append((f"lui ${rd}, {imm & 0xFFFF}", 0b100011 << 26 | rd << 21 | (imm & 0xFFFF)))
    for rd, rs in [(1, 2), (15, 14)]:
        items.append((f"move ${rd}, ${rs}", 0b100100 << 26 | rd << 21 | rs << 16))
    for rd in (1, 15):
        items.append((f"mfhi ${rd}", 0b100001 << 26 | rd << 21))
        items.append((f"mflo ${rd}", 0b100111 << 26 | rd << 21))
    for rd, rs, imm in [(1, 2, 8), (15, 14, -4), (3, 0, 0)]:
        items.append((f"ld ${rd}, {imm}(${rs})", 0b100101 << 26 | rd << 21 | rs << 16 | (imm & 0xFFFF)))
        items.append((f"st ${rd}, {imm}(${rs})", 0b100110 << 26 | rd << 21 | rs << 16 | (imm & 0xFFFF)))
    out.append(mk("LI / LUI / MOVE / MFHI / MFLO / LD / ST", items))

    # branches: pad with NOPs so that negative offsets stay >= 0
    items = [("nop", 0)] * 40
    for op, o in BOP.items():
        for off, a, b in [(3, 1, 2), (0, 15, 14), (-5, 7, 8), (100, 2, 1)]:
            idx = len(items)
            target = 4 * (idx + 1 + off)
            if op == "bz":
                items.append((f"bz ${a}, {target}", o << 26 | a << 16 | (off & 0xFFFF)))
            else:
                items.append((f"{op} ${a}, ${b}, {target}", o << 26 | b << 21 | a << 16 | (off & 0xFFFF)))
    out.append(mk("Branches (rs2 in 25:21, rs in 20:16, offset)", items[:40] + items[40:]))

    items = []
    for tgt in (0, 4, 64, 4 * 0x3FFFFFF):
        items.append((f"j {tgt}", 0b101000 << 26 | (tgt // 4)))
        items.append((f"jal {tgt}", 0b101001 << 26 | (tgt // 4)))
    for r in (1, 15, 9):
        items.append((f"j ${r}", 0b101011 << 26 | r << 16))
    items += [("nop", 0), ("halt", 0xFC000000)]
    out.append(mk("J / JAL / JR / NOP / HALT", items))
    return out

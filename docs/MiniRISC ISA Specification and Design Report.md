# MiniRISC: ISA Specification and Design Report

Architecture and instruction-set submission · 4 October 2026

## 1. Architecture overview

MiniRISC is a 32-bit, load/store, three-operand RISC processor. It has separate instruction and data memories (Harvard), a word-addressed program counter, a non-pipelined datapath, and a small 4-state control FSM. Almost every instruction completes in one clock; `LD` takes two.

**Programmer-visible state**

- **R0–R15**: 32-bit general registers. R0 must read as zero: `LI`, `MOVE`, `BZ`, `MFHI` and `MFLO` all depend on it. R15 is the link register, written implicitly by `JAL`.
- **HI, LO**: hold the 64-bit result of `MULU`. Inside the register file they sit at addresses 16 and 17, outside the R0–R15 range the assembler should expose. They are read only through `MFHI` / `MFLO`.
- **PC**: counts words, not bytes. Sequential flow is PC + 1.

**Figures submitted with this report** (hand-drawn): Fig. 1 data-path.jpeg, Fig. 2 ALU.jpeg, Fig. 3 NAD.jpeg, Fig. 4 control-path.jpeg.

### 1.1 Datapath walk-through (Fig. 1)

1. **Fetch.** The instruction ROM is addressed with `next_pc` (not `pc_out`), so the PC register and the ROM output both update on the same clock edge. `ic_enable` freezes the ROM output, which is how the current instruction is held during multi-cycle ops and `HALT`.
2. **Decode.** Fields are wired straight out of the instruction word (no decoder): `opcode` \[31:26\], `rd` \[25:21\], `rs` \[20:16\], `rt` \[15:11\], `shamt` \[10:6\], `fn` \[5:0\], `imm` \[15:0\], `jta` \[25:0\]. Only `opcode` and `fn` go to the control path.
3. **Register read.** Two read ports. The `rs` address passes through a 2:1 mux (`force_rs_zero`); the `rt` address passes through an 8:1 mux (`rt_sel`). Section 8.1 explains why.
4. **Immediate.** A 16→32 sign extender feeds a 2:1 mux that picks zero extension for logic immediates (`alu_src` and `alu_func[5:3] == 011`). A second mux (`alu_src`) chooses `rt_out` or the extended immediate as the ALU's **y** operand.
5. **ALU.** x = `rs_out` (no mux), y = `rt_out` or immediate. See 1.2.
6. **Data memory.** Address = `alu_out_lo`, store data = `rt_out`, controlled by `mem_read` / `mem_write`.
7. **Write-back.** `reg_in_src` chooses what is written: memory data, ALU result, PC + 1, or 0. `reg_dst` chooses the destination address. A second write port takes the ALU's high result for HI.
8. **Next PC.** The next-address decoder (1.3).

### 1.2 ALU (Fig. 2)

The ALU contains five units in parallel, and `alu_func[5:3]` selects which result leaves. `alu_func[2:0]` selects the operation inside the unit. Because the R-type `fn` field uses exactly this encoding, **fn is the ALU control word** and no ALU decoder is needed.

| alu\_func\[5:3\] | Unit | alu\_func\[2:0\] operations |
| --- | --- | --- |
| 000 | Load-upper | LUI (000) |
| 001 | Compare / set | SLT 000, SGT 001, SLE 010, SGE 011, SEQ 100, SNE 101 |
| 010 | Arithmetic | ADD 000, SUB 001, MUL 010, MULU 011 |
| 011 | Logic | AND 000, OR 001, NOT 010, NOR 011, XOR 100 |
| 100 | Shift | SLL 000, SRL 001, SRA 010 |

The arithmetic unit also produces `high` (upper 32 bits of a product) and the overflow flag `ovfl`. The compare unit produces the flags `lt gt le ge eq ne`, which go to the next-address decoder. The `high` output passes through a 2:1 mux (select = `hi_lo_enable`, other input = 0), so HI is written only by `MULU`.

### 1.3 Next-address decoder (Fig. 3)

A branch-condition checker combines the compare flags, `ovfl`, `br_type` and `is_branch` into `br_true`. `br_true` AND-gates the sign-extended offset, and one adder computes `PC + (br_true ? offset : 0) + 1` with carry-in = 1. So the same adder produces both the sequential PC + 1 and the branch target, and its output is also `inc_pc`, the return address stored by `JAL`. The final mux is controlled by `pc_src`:

| pc\_src | next\_pc |
| --- | --- |
| 00 | adder output: PC + 1 (+ offset if branch taken) |
| 01 | `jta` (J, JAL) |
| 10 | `rs` register value (JR) |
| 11 | 0 (start-up / system vector) |

### 1.4 Control path FSM (Fig. 4)

| State | Behaviour |
| --- | --- |
| IDLE | `pc_enable = ic_enable = 1`, `pc_src = 11`: PC is forced to 0 and instruction 0 is pre-fetched. Moves to RUN when `start` is asserted. |
| RUN | Decodes `opcode` and drives all control signals. Single-cycle instructions stay in RUN. Multi-cycle instructions go to WAIT. `HALT` or an illegal opcode goes to DONE. |
| WAIT | Holds the PC and ROM output for a multi-cycle instruction (`halt_period` counts down), then commits and returns to RUN. |
| DONE | Processor stopped. |

`reset` is asynchronous and returns to IDLE from any state. The sketch in Fig. 4 shows WAIT → DONE; the code actually goes WAIT → RUN, and DONE is entered from RUN on `HALT` / illegal opcode (see section 10).

## 2. Instruction formats

All instructions are 32 bits. Fields are at fixed positions in every format, and **the destination register is always in bits 25:21**.

| Format | 31:26 | 25:21 | 20:16 | 15:11 | 10:6 | 5:0 |
| --- | --- | --- | --- | --- | --- | --- |
| R | op | rd | rs | rt | shamt | fn |
| I (ALU, LI, LUI, LD, ST) | op | rd | rs | imm\[15:0\] (overlaps rt / shamt / fn) |  |  |
| Branch | op | rs2 (rd field) | rs | offset\[15:0\] |  |  |
| J | op | jta\[25:0\] |  |  |  |  |

- Only R-type (`op = 100000`) takes the ALU function from instruction bits 5:0. For every other format those bits belong to the immediate, so **each I-type instruction has its own opcode** and the control path generates `alu_func`.
- In the branch format the first register field is the second comparison register; it is not written.
- `shamt` exists in the R format but the datapath does not use it. Shift amounts come through the ALU's y operand (register or immediate).

## 3. Opcode allocation

6-bit opcode. The top two bits give the class, the rest identify the instruction.

| op range | Class | Opcodes |
| --- | --- | --- |
| 000000 | No-op | NOP |
| 010000–010111 | Conditional branches | BEQ 010000, BZ 010001, BNE 010010, BLT 010011, BLE 010100, BGT 010101, BGE 010110, BV 010111 |
| 100000–100111 | R-type, constants, moves, memory | R-type 100000, MFHI 100001, LI 100010, LUI 100011, MOVE 100100, LD 100101, ST 100110, MFLO 100111 |
| 101000–101011 | Jumps | J 101000, JAL 101001, JR 101011 (101010 reserved) |
| 110000–111110 | I-type ALU | ADDI 110000, SUBI 110001, ANDI 110010, ORI 110011, NORI 110100, XORI 110101, SLLI 110110, SRLI 110111, SRAI 111000, SLTI 111001, SGTI 111010, SLEI 111011, SGEI 111100, SEQI 111101, SNEI 111110 |
| 111111 | Stop | HALT |

Unassigned opcodes are treated as illegal and send the FSM to DONE. Rationale:

- **NOP = all zeros**: zero-filled (unprogrammed) memory executes harmlessly. **HALT = all ones**: a fetch from an erased or floating-high bus stops the machine instead of running garbage.
- Prefix `11` always means "ALU with immediate", `01` always means "conditional branch", so the class is visible from two bits.
- The I-type opcodes follow the same order as the R-type functions (ADD, SUB, AND, OR, NOR, XOR, shifts, compares). `MUL`, `MULU` and `NOT` have no immediate form because they are not useful with a constant.

## 4. Complete instruction list

| Group | Mnemonic | Syntax | Operation |
| --- | --- | --- | --- |
| Control | NOP | `NOP` | PC ← PC + 1 |
| Control | HALT | `HALT` | Stop; PC frozen until reset |
| Arithmetic | ADD, SUB | `ADD rd, rs, rt` | rd ← rs + rt, rd ← rs − rt |
| Arithmetic | MUL | `MUL rd, rs, rt` | rd ← low 32 bits of rs × rt |
| Arithmetic | MULU | `MULU rs, rt` | {HI, LO} ← rs × rt (64-bit, unsigned) |
| Logic | AND, OR, NOR, XOR | `AND rd, rs, rt` | bitwise on rs, rt |
| Logic | NOT | `NOT rd, rs` | rd ← \~rs (rt unused) |
| Shift | SLL, SRL, SRA | `SLL rd, rs, rt` | rd ← rs shifted by rt (left, logical right, arithmetic right) |
| Set | SLT, SGT, SLE, SGE, SEQ, SNE | `SLT rd, rs, rt` | rd ← 1 if the relation rs ? rt holds, else 0 |
| ALU immediate | ADDI, SUBI | `ADDI rd, rs, imm` | rd ← rs ± sext(imm) |
| ALU immediate | ANDI, ORI, NORI, XORI | `ORI rd, rs, imm` | rd ← rs op zext(imm) |
| ALU immediate | SLLI, SRLI, SRAI | `SLLI rd, rs, imm` | shift rs by imm |
| ALU immediate | SLTI, SGTI, SLEI, SGEI, SEQI, SNEI | `SLTI rd, rs, imm` | set on comparison with sext(imm) |
| Constants | LI | `LI rd, imm` | rd ← sext(imm) (implemented as 0 + imm) |
| Constants | LUI | `LUI rd, imm` | rd ← imm << 16 |
| Moves | MOVE | `MOVE rd, rs` | rd ← rs (implemented as rs + R0) |
| Moves | MFHI, MFLO | `MFHI rd` | rd ← HI, rd ← LO (implemented as R0 + HI / LO) |
| Memory | LD | `LD rd, imm(rs)` | rd ← MEM\[rs + sext(imm)\] |
| Memory | ST | `ST rd, imm(rs)` | MEM\[rs + sext(imm)\] ← rd |
| Jump | J | `J target` | PC ← jta |
| Jump | JAL | `JAL target` | R15 ← PC + 1; PC ← jta |
| Jump | JR | `JR rs` | PC ← rs |
| Branch | BEQ, BNE | `BEQ rs, rd, label` | if rs = rd (≠) then PC ← PC + 1 + sext(offset) |
| Branch | BLT, BLE, BGT, BGE | `BLT rs, rd, label` | same, on rs < rd, ≤, >, ≥ |
| Branch | BZ | `BZ rs, label` | branch if rs = 0 |
| Branch | BV | `BV rs, rd, label` | branch if rs − rd overflows |

Total: 53 instructions (counting each opcode/function once).

## 5. Immediate, branch, jump and memory conventions

**Immediates.** 16 bits. Sign extended for all instructions except the logic immediates (`ANDI ORI NORI XORI`), which are zero extended. Reason: `LUI rd, hi16` followed by `ORI rd, rd, lo16` builds any 32-bit constant, and this only works if `ORI` does not smear a sign bit over the upper half. `LUI` ignores the extension because it uses only imm\[15:0\]. Selection is done by `alu_src & (alu_func[5:3] == 011)`.

**Branches.** Compare-and-branch in one instruction, with no condition-code register. The two registers are `rs` and the `rd` field. The target is **PC-relative in words: PC + 1 + sext(offset16)**, a reach of about ±32K instructions. `BZ` compares `rs` with R0. `BV` tests overflow of rs − rd (it performs its own subtraction, it does not look at an earlier instruction). Not-taken branches fall through to PC + 1.

**Jumps.** `J` / `JAL` use a 26-bit absolute word address (`jta`). `JAL` saves PC + 1 in R15. `JR rs` jumps to a register, which is how a function returns (`JR R15`).

**Memory.** Base + displacement only: address = `rs + sext(imm)`, computed by the ALU's ADD. Loads and stores are word (32-bit) accesses; there are no byte or halfword instructions. For `ST`, the register named in the `rd` field is the value stored. `LD` takes two cycles (sections 1.4 and 8.4).

**No exceptions.** Arithmetic overflow does not trap; it is observable only through `BV`.

## 6. MUL and MULU semantics

The ISA provides MUL and MULU; there is no MAC instruction.

|  | MUL | MULU |
| --- | --- | --- |
| Encoding | R-type, fn = 010010 | R-type, fn = 010011 |
| Result | rd ← (rs × rt)\[31:0\] | {HI, LO} ← rs × rt, 64 bits, unsigned |
| Destination | `reg_dst = 01` (rd) | `reg_dst = 10` (address 17 = LO) |
| `hi_lo_enable` | 0 | 1 |
| Reading the result | directly in rd | `MFHI rd`, `MFLO rd` |

The low 32 bits of a product are the same for signed and unsigned operands, so `MUL` needs no signed/unsigned variant. `MULU` writes LO through the normal write port (the `reg_dst` mux supplies address 17) and HI through the dedicated second write port (`reg_in_hi`, enabled by `hi_lo_enable`), both in the same commit cycle. Because the 64-bit product is kept in HI:LO, a MAC (HI:LO += rs × rt) could be added later with only a new `fn` code and an adder on the accumulate path.

**Timing.** In the current `control_path.v` the multi-cycle hook for MUL/MULU is commented out, so they commit in one cycle. The planned iterative multiplier uses the same WAIT mechanism as `LD` with `multi_cycles = 32`, giving 33 WAIT cycles.

## 7. Justification of the ISA organisation

- **Load/store, 3-operand, fixed 32-bit format.** Simple decode, and each field is wired directly with no instruction-length logic.
- **Destination always at 25:21.** One write-address source for almost every instruction. This is why the I-type destination is `rd` and why `reg_dst = 00` (rt) is never needed.
- **16-bit immediate over rt/shamt/fn.** Gives practical constants and offsets. The cost is that I-type has no `fn`, so each I-type has its own opcode and the control path emits `alu_func`.
- **`fn` equals the ALU control code.** R-type needs no ALU decoder, and I-type reuses the same codes.
- **Compare-and-branch, set-on-compare.** No flags register, so no hidden state between instructions. Both forms are provided so compilers can choose.
- **Pseudo-instructions enforced in hardware.** `LI`, `MOVE`, `MFHI`, `MFLO`, `BZ` reuse ADD/SUB with an operand forced to R0, so correctness does not depend on the assembler filling unused fields with zero.
- **HI/LO for wide multiply.** Keeps the register file at two read ports and one main write port, and gives a path to MAC.
- **Word-addressed PC with PC + 1.** Removes the 2-bit alignment handling; one adder serves PC + 1, branch target and the `JAL` link.
- **Non-pipelined with a tiny FSM.** No hazards, forwarding or delay slots; the cost is lower throughput, acceptable for the course.

## 8. Design decisions explained (viva)

### 8.1 Why there are muxes on the RS and RT read addresses

**The root cause is the instruction format.** An R-type instruction has three register fields (rd, rs, rt). But I-type and branch formats use bits 15:0 as the immediate or offset, which **destroys the rt field**. Several instructions still need a second register operand or a constant, so the second read address cannot always come from `rt`. The register file has only two read ports, so instead of adding a third port, the `rt` port's address is steered by a mux (`rt_sel`):

| rt\_sel | Address sent to rt port | Used by | Why |
| --- | --- | --- | --- |
| 000 | `rt` field | R-type (and I-type, where the value is ignored) | Normal case. In I-type the port reads junk bits of the immediate; harmless because `alu_src = 1` ignores it and reads have no side effect. |
| 001 | `rd` field | `ST`, `BEQ BNE BLT BLE BGT BGE BV` | `ST` has no register destination, so the `rd` field is free to carry the **value to store**. Branches need a second comparison register and the offset consumed the `rt` field, so the free `rd` field supplies it. |
| 010 | R0 | `MOVE`, `BZ` | Need a constant 0 as the second operand: `MOVE` computes rs + 0, `BZ` compares rs with 0. |
| 011 | address 16 (HI) | `MFHI` | Reads HI into the ALU y operand. |
| 100 | address 17 (LO) | `MFLO` | Reads LO into the ALU y operand. |

The `rt_sel` mux replaced an earlier single `force_rt_zero` bit, which could express "R0" but not the HI/LO or `rd` cases.

**The RS mux (`force_rs_zero`)** is a 2:1 mux choosing `rs` or R0. The ALU's x operand is always `rs_out`, and an immediate can only reach the ALU as y. So any instruction that needs "nothing + something" must zero x:

- `LI rd, imm` = 0 + imm (y = immediate).
- `MFHI` / `MFLO` = 0 + HI / LO (y = HI or LO from the rt port).

Both reuse the existing ADD function, so no new ALU operation or datapath is needed. HI/LO selection was put on the already-existing `rt` mux (just two more inputs), while the `rs` side stays a cheap 2:1 mux.

The same logic explains the other small muxes: `reg_dst` selects rd (almost all), LO (`MULU` has no destination field) or R15 (`JAL` uses the whole word for `jta`, so has no rd field). `reg_in_src` selects memory (`LD`), ALU (most), or PC + 1 (`JAL`). The `alu_src` mux chooses register versus immediate for y.

### 8.2 Why LUI takes its input from y (the rt side), not x (rs)

- The ALU has two operand ports. **x is always `rs_out`** (no mux in front of it). **y goes through the `alu_src` mux**, so y is the only port where the immediate can enter. `LUI rd, imm` has exactly one operand, the immediate, so the load-upper unit is wired to y (Fig. 2).
- `LUI` has no source register, so the `rs` field is simply unused. No `force_rs_zero` is needed, unlike `LI`, where ADD uses both ports and x must be zeroed.
- Using x would need either a second immediate mux on the x side or a new path: extra hardware for no benefit.
- `LUI` uses only y\[15:0\], so it does not matter that the immediate extender sign-extends it (it only zero-extends when `alu_func[5:3] == 011`).

### 8.3 Why branches use alu\_func = SUB and alu\_src = 0

`alu_src = 0` makes y the second comparison register (not the offset in the immediate field). `SUB` is selected so the arithmetic unit produces `ovfl` for `BV`. The compare flags come from the compare unit on x and y regardless of `alu_func`.

### 8.4 Why LD takes two cycles and how the FSM does it

The data memory returns data one clock after the address is presented. In the first cycle (state RUN) `mem_read = 1` while `pc_enable = ic_enable = reg_write = 0`, so nothing is committed and the instruction word is held. The FSM moves to WAIT; with `halt_period = 0` it commits in that cycle (`reg_write`, `pc_enable`, `ic_enable` = 1, `reg_in_src = 00`) and returns to RUN. `ST` is single-cycle because a write needs no return data.

### 8.5 Why the ROM is addressed with next\_pc

If the ROM used `pc_out`, the instruction would arrive one cycle after the PC changed. Addressing it with `next_pc` makes the new PC and the new instruction appear on the same edge, so the control signals for instruction N are valid during the same cycle PC = N. This is also why IDLE forces `pc_src = 11` (PC = 0) with `ic_enable = 1`: instruction 0 is already waiting when `start` arrives.

### 8.6 Why HALT does not advance the PC but NOP does

`NOP` is a real instruction: `pc_enable = ic_enable = 1`, so execution continues. `HALT` clears both enables and sends the FSM to DONE, so the PC and instruction output freeze until `reset`.

## 9. Quick viva answers

- **Why separate opcodes for I-type?** The immediate overwrites the `fn` field, so the opcode must say which operation to perform.
- **Why is NOP all zeros?** Cleared memory is harmless.
- **Why sign extension for most and zero for logic?** Arithmetic and addresses need negative values; logic masks and `LUI`+`ORI` constant building need the upper half untouched.
- **How does JAL save the return address?** The next-address adder output with `br_true = 0` is PC + 1; `reg_in_src = 10` routes it to R15 (`reg_dst = 11`).
- **How does a function return?** `JR R15`.
- **How is MFHI done without an ALU op?** ADD with x forced to R0 and y read from address 16.
- **How are two registers compared for a branch if the offset takes the rt field?** The second register is read from the rd field via `rt_sel = 001`.
- **What happens on an illegal opcode?** Default decode case: all enables 0 and the FSM goes to DONE.
- **What leaves DONE?** Only `reset`, which returns to IDLE; then `start`.
- **Difference between MUL and MULU?** MUL writes 32 bits to rd. MULU writes the full 64-bit product to HI:LO.
- **Why does ST not write a register?** `reg_write = 0`; `reg_dst` and `reg_in_src` are don't-care.
- **Branch range?** 16-bit signed word offset from PC + 1.

## 10. Mismatches and items to verify before the viva

Checked against `data_path.v` and `control_path.v`. The `next_address_decoder`, `alu` and `register_file` sources were not supplied, so items marked \* rely on the sketches.

1. **Branch alu\_func.** The original control-word table listed `fn = XXXXXX` for branches; the code sets `SUB` (010001). This report uses the code. It is needed for `BV`.
2. **MUL/MULU timing.** The original notes said 33 wait cycles; the code has the multi-cycle block commented out, so they are single-cycle today.
3. **FSM sketch (Fig. 4).** It shows WAIT → DONE. In code, WAIT → RUN, and DONE is reached from RUN on `HALT` or an illegal opcode. Redraw before submitting.
4. **Branch offset width (\*).** Fig. 3 shows a 26 → 30 bit sign extender on `jta` feeding both the jump mux and the branch adder. For branches the offset must be `sext(jta[15:0])`; if the whole 26-bit field were extended, the `rd` and `rs` bits would corrupt the offset. Confirm in the NAD source.
5. **`shamt` unused.** It is decoded but never connected. Say it is reserved.
6. **`reg_dst = 00` (rt) is never used.** It is vestigial because the destination is always `rd`.
7. **R0 and registers 16/17 (\*).** Confirm the register file hard-wires R0 to zero and ignores writes to it. Because the fields are 5 bits, an instruction that encodes register 16 or 17 would read HI / LO directly; the assembler should only accept R0–R15.
8. **Unary and signedness details (\*).** Confirm that `NOT` ignores y, that `MULU` multiplies unsigned, and that the compare unit's signed/unsigned behaviour matches the set and branch descriptions.
9. **Signal names.** The original table abbreviations map to Verilog as: regdst → `reg_dst`, hi\_lo → `hi_lo_enable`, reg\_wr → `reg_write`, fn → `alu_func`, ld → `mem_read`, st → `mem_write`, reg\_in → `reg_in_src`, br\_t → `br_type`, pc\_en → `pc_enable`, ic\_en → `ic_enable`.

## Appendix A. Control words

Select encodings. **reg\_dst**: 00 rt (unused), 01 rd, 10 LO, 11 R15. **reg\_in**: 00 memory, 01 ALU, 10 PC + 1, 11 zero. **pc\_src**: 00 PC + 1 (+ offset), 01 jta, 10 rs, 11 zero. **br\_t**: 001 EQ, 010 NE, 011 LT, 100 LE, 101 GT, 110 GE, 111 overflow. **rt\_sel**: 000 rt, 001 rd, 010 R0, 011 HI, 100 LO.

`pc_en` and `ic_en` are 1 for every instruction except `HALT` (0). For `LD` they are 0 in its first cycle and 1 in the commit cycle; the table shows the commit cycle, except `ld` (mem\_read), which is 1 only in the first cycle. X = don't care. `frz` = `force_rs_zero`.

| Mnemonic | op | reg\_dst | hi\_lo | reg\_wr | alu\_src | fn | ld | st | reg\_in | pc\_src | is\_br | br\_t | frz | rt\_sel |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NOP | 000000 | XX | 0 | 0 | X | XXXXXX | 0 | 0 | XX | 00 | 0 | X | 0 | 000 |
| ADD | 100000 | 01 | 0 | 1 | 0 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SUB | 100000 | 01 | 0 | 1 | 0 | 010001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| MUL | 100000 | 01 | 0 | 1 | 0 | 010010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| MULU | 100000 | 10 | 1 | 1 | 0 | 010011 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| AND | 100000 | 01 | 0 | 1 | 0 | 011000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| OR | 100000 | 01 | 0 | 1 | 0 | 011001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| NOT | 100000 | 01 | 0 | 1 | 0 | 011010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| NOR | 100000 | 01 | 0 | 1 | 0 | 011011 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| XOR | 100000 | 01 | 0 | 1 | 0 | 011100 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLL | 100000 | 01 | 0 | 1 | 0 | 100000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SRL | 100000 | 01 | 0 | 1 | 0 | 100001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SRA | 100000 | 01 | 0 | 1 | 0 | 100010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLT | 100000 | 01 | 0 | 1 | 0 | 001000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SGT | 100000 | 01 | 0 | 1 | 0 | 001001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLE | 100000 | 01 | 0 | 1 | 0 | 001010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SGE | 100000 | 01 | 0 | 1 | 0 | 001011 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SEQ | 100000 | 01 | 0 | 1 | 0 | 001100 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SNE | 100000 | 01 | 0 | 1 | 0 | 001101 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| ADDI | 110000 | 01 | 0 | 1 | 1 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SUBI | 110001 | 01 | 0 | 1 | 1 | 010001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| ANDI | 110010 | 01 | 0 | 1 | 1 | 011000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| ORI | 110011 | 01 | 0 | 1 | 1 | 011001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| NORI | 110100 | 01 | 0 | 1 | 1 | 011011 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| XORI | 110101 | 01 | 0 | 1 | 1 | 011100 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLLI | 110110 | 01 | 0 | 1 | 1 | 100000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SRLI | 110111 | 01 | 0 | 1 | 1 | 100001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SRAI | 111000 | 01 | 0 | 1 | 1 | 100010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLTI | 111001 | 01 | 0 | 1 | 1 | 001000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SGTI | 111010 | 01 | 0 | 1 | 1 | 001001 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SLEI | 111011 | 01 | 0 | 1 | 1 | 001010 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SGEI | 111100 | 01 | 0 | 1 | 1 | 001011 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SEQI | 111101 | 01 | 0 | 1 | 1 | 001100 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| SNEI | 111110 | 01 | 0 | 1 | 1 | 001101 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| LI | 100010 | 01 | 0 | 1 | 1 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 1 | 000 |
| LUI | 100011 | 01 | 0 | 1 | 1 | 000000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 000 |
| MOVE | 100100 | 01 | 0 | 1 | 0 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 0 | 010 |
| MFHI | 100001 | 01 | 0 | 1 | 0 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 1 | 011 |
| MFLO | 100111 | 01 | 0 | 1 | 0 | 010000 | 0 | 0 | 01 | 00 | 0 | X | 1 | 100 |
| LD | 100101 | 01 | 0 | 1 | 1 | 010000 | 1 | 0 | 00 | 00 | 0 | X | 0 | 000 |
| ST | 100110 | XX | 0 | 0 | 1 | 010000 | 0 | 1 | XX | 00 | 0 | X | 0 | 001 |
| J | 101000 | XX | 0 | 0 | X | XXXXXX | 0 | 0 | XX | 01 | 0 | X | 0 | 000 |
| JAL | 101001 | 11 | 0 | 1 | X | XXXXXX | 0 | 0 | 10 | 01 | 0 | X | 0 | 000 |
| JR | 101011 | XX | 0 | 0 | X | XXXXXX | 0 | 0 | XX | 10 | 0 | X | 0 | 000 |
| BEQ | 010000 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 001 | 0 | 001 |
| BZ | 010001 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 001 | 0 | 010 |
| BNE | 010010 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 010 | 0 | 001 |
| BLT | 010011 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 011 | 0 | 001 |
| BLE | 010100 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 100 | 0 | 001 |
| BGT | 010101 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 101 | 0 | 001 |
| BGE | 010110 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 110 | 0 | 001 |
| BV | 010111 | XX | 0 | 0 | 0 | 010001 | 0 | 0 | XX | 00 | 1 | 111 | 0 | 001 |
| HALT | 111111 | XX | 0 | 0 | X | XXXXXX | 0 | 0 | XX | 00 | 0 | X | 0 | 000 |

#!/usr/bin/env python3
# AI Generated
"""
run_tests.py - assemble, simulate and check MiniRISC programs from the VCD.

Flow for every test (see test_cases.py for the test list):

  1. assembly text (+ a HALT footer) -> assembler/mini_asm -> program.mem
  2. vvp runs build/mini_risc.vvp; address_rom.v reads inputs/program.mem
  3. the VCD written by tb_mini_risc.v is parsed:
       * final value of R0..R15, HI, LO
       * pc / FSM state / control signals sampled once per clock edge
  4. registers, HI/LO, final PC, executed / skipped instructions, stall timing
     and (for the sweep test) the control word of all 53 instructions are
     compared with the expected values.

Nothing is read from any file the RTL writes: the testbench only drives the
clock and the VCD is the single source of truth.

Every test runs in its own directory build/tests/<name>/ (with its own
inputs/program.mem), so tests run in parallel (-j).

Usage:
    python3 run_tests.py                      # everything
    python3 run_tests.py mul branch           # tests whose name/group contains a word
    python3 run_tests.py --group "Memory"
    python3 run_tests.py -v --fail-fast -j 8
    python3 run_tests.py --list
    python3 run_tests.py --mulu unsigned      # only if you want HI from an unsigned product
"""
import argparse
import concurrent.futures as cf
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASM_BIN = ROOT / "assembler" / "mini_asm"
VVP_FILE = ROOT / "build" / "mini_risc.vvp"
OUT_DIR = ROOT / "build" / "tests"
ROM_WORDS = 1024            # address_rom is instantiated with ADDR = 10
HALT_WORD = 0xFC000000
M = 0xFFFFFFFF
FOOTER = "\n__end:\nhalt\n"
SIM_TIMEOUT_S = 180
DEFAULT_CYCLES = 3000

SCOPE = "tb_mini_risc."
CTRL = SCOPE + "dut.control."
RF = SCOPE + "dut.data.rf."
PC_SIG = SCOPE + "dut.data.pc.pc_out"
CLK_SIG = SCOPE + "clk"
REG_NAMES = [f"r{i}" for i in range(16)]
ST_IDLE, ST_RUN, ST_WAIT, ST_DONE = 0, 1, 2, 3


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def fmt(v):
    return "X" if v is None else f"0x{v:08X}"


def safe_name(name):
    return re.sub(r"[^\w.-]+", "_", name).strip("_")[:90]


def load_cases():
    spec = importlib.util.spec_from_file_location("test_cases", ROOT / "test_cases.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# assembly preparation
# ---------------------------------------------------------------------------
def prepare(asm):
    """strip comments, resolve {@label}, turn `.word X` into a nop to patch later.

    Returns (text, labels{name: byte address}, patches{index: word}, n_instr).
    """
    clean = []
    for raw in asm.splitlines():
        line = re.split(r"#|//", raw)[0].strip()
        if line:
            clean.append(line)

    labels, idx = {}, 0
    for line in clean:
        m = re.fullmatch(r"(\w+):", line)
        if m:
            labels[m.group(1)] = idx * 4
        else:
            idx += 1

    out, patches, idx = [], {}, 0
    for line in clean:
        if re.fullmatch(r"\w+:", line):
            out.append(line)
            continue
        line = re.sub(r"\{@(\w+)\}", lambda m: str(labels[m.group(1)]), line)
        m = re.fullmatch(r"\.word\s+(\S+)", line, re.I)
        if m:
            patches[idx] = int(m.group(1), 0) & M
            line = "nop"
        out.append(line)
        idx += 1
    return "\n".join(out) + "\n", labels, patches, idx


def run_assembler(src, dst):
    r = subprocess.run([str(ASM_BIN), str(src), str(dst)], cwd=ROOT,
                       capture_output=True, text=True)
    err = (r.stdout + r.stderr)
    bad = r.returncode != 0 or "Error" in r.stderr or "error" in r.stderr
    return not bad, err.strip()


def read_words(path):
    return [int(x, 16) for x in Path(path).read_text().split()]


# ---------------------------------------------------------------------------
# VCD parsing
# ---------------------------------------------------------------------------
def parse_vcd(path):
    """{full signal name: [(time, int|None), ...]} for the signals we care about."""
    def want(n):
        return (n == CLK_SIG or n == PC_SIG or n.startswith(CTRL)
                or (n.startswith(RF) and n[len(RF):] in REG_NAMES + ["hi", "lo"]))

    ids, hist, scope, time = {}, {}, [], 0
    in_defs = True

    def to_int(bits):
        return None if re.search(r"[xzXZ]", bits) else int(bits, 2)

    with open(path) as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            if in_defs:
                if line.startswith("$scope"):
                    scope.append(line.split()[2])
                elif line.startswith("$upscope"):
                    scope.pop()
                elif line.startswith("$var"):
                    p = line.split()
                    full = ".".join(scope + [p[4]])
                    if want(full):
                        ids.setdefault(p[3], []).append(full)
                        hist[full] = []
                elif line.startswith("$enddefinitions"):
                    in_defs = False
                continue
            c = line[0]
            if c == "#":
                time = int(line[1:])
            elif c in "bB":
                bits, vid = line[1:].split()
                for n in ids.get(vid, ()):
                    hist[n].append((time, to_int(bits)))
            elif c in "01xXzZ":
                for n in ids.get(line[1:], ()):
                    hist[n].append((time, to_int(c)))
    return hist


def sample(h, edges):
    """value of a signal just before each clock edge (None before the first change)."""
    out, i, cur = [], 0, None
    for e in edges:
        while i < len(h) and h[i][0] < e:
            cur = h[i][1]
            i += 1
        out.append(cur)
    return out


class Trace:
    def __init__(self, vcd):
        self.hist = parse_vcd(vcd)
        clk = self.hist.get(CLK_SIG, [])
        self.edges = [t for (t, v), (_, pv) in zip(clk[1:], clk) if v == 1 and pv == 0]
        self.n = len(self.edges)
        self.pc = sample(self.hist.get(PC_SIG, []), self.edges)
        self.state = sample(self.hist.get(CTRL + "state", []), self.edges)
        self._cache = {}

    def final(self, name):
        h = self.hist.get(name)
        return h[-1][1] if h else None

    def reg(self, i):
        return self.final(RF + f"r{i}")

    def sig(self, name):
        full = CTRL + name
        if full not in self._cache:
            self._cache[full] = sample(self.hist.get(full, []), self.edges)
        return self._cache[full]

    def missing(self):
        need = [CLK_SIG, PC_SIG, CTRL + "state"] + [RF + n for n in REG_NAMES + ["hi", "lo"]]
        return [n for n in need if n not in self.hist]

    def executed_pcs(self):
        return {p for p, s in zip(self.pc, self.state) if s in (ST_RUN, ST_WAIT) and p is not None}


# ---------------------------------------------------------------------------
# Appendix A of the ISA report: expected control words
# ---------------------------------------------------------------------------
FIELDS = ["reg_dst", "hi_lo_enable", "reg_write", "alu_src", "alu_func", "mem_read",
          "mem_write", "reg_in_src", "pc_src", "is_branch", "br_type", "force_rs_zero", "rt_sel"]


def _row(txt):
    toks = txt.split()
    assert len(toks) == len(FIELDS), txt
    return {f: (None if "X" in t else int(t, 2)) for f, t in zip(FIELDS, toks)}


def appendix_a():
    rows = {}
    NOP = "XX 0 0 X XXXXXX 0 0 XX 00 0 X 0 000"
    rows["nop"] = _row(NOP)
    rows["halt"] = _row("XX 0 0 X XXXXXX 0 0 XX 00 0 X 0 000")
    rfn = {"add": "010000", "sub": "010001", "mul": "010010", "and": "011000",
           "or": "011001", "not": "011010", "nor": "011011", "xor": "011100",
           "sll": "100000", "srl": "100001", "sra": "100010", "slt": "001000",
           "sgt": "001001", "sle": "001010", "sge": "001011", "seq": "001100",
           "sne": "001101"}
    for k, fn in rfn.items():
        rows[k] = _row(f"01 0 1 0 {fn} 0 0 01 00 0 X 0 000")
    rows["mulu"] = _row("10 1 1 0 010011 0 0 01 00 0 X 0 000")
    ifn = {"addi": "010000", "subi": "010001", "andi": "011000", "ori": "011001",
           "nori": "011011", "xori": "011100", "slli": "100000", "srli": "100001",
           "srai": "100010", "slti": "001000", "sgti": "001001", "slei": "001010",
           "sgei": "001011", "seqi": "001100", "snei": "001101"}
    for k, fn in ifn.items():
        rows[k] = _row(f"01 0 1 1 {fn} 0 0 01 00 0 X 0 000")
    rows["li"] = _row("01 0 1 1 010000 0 0 01 00 0 X 1 000")
    rows["lui"] = _row("01 0 1 1 000000 0 0 01 00 0 X 0 000")
    rows["move"] = _row("01 0 1 0 010000 0 0 01 00 0 X 0 010")
    rows["mfhi"] = _row("01 0 1 0 010000 0 0 01 00 0 X 1 011")
    rows["mflo"] = _row("01 0 1 0 010000 0 0 01 00 0 X 1 100")
    rows["ld"] = _row("01 0 1 1 010000 1 0 00 00 0 X 0 000")
    rows["st"] = _row("XX 0 0 1 010000 0 1 XX 00 0 X 0 001")
    rows["j"] = _row("XX 0 0 X XXXXXX 0 0 XX 01 0 X 0 000")
    rows["jal"] = _row("11 0 1 X XXXXXX 0 0 10 01 0 X 0 000")
    rows["jr"] = _row("XX 0 0 X XXXXXX 0 0 XX 10 0 X 0 000")
    brt = {"beq": ("001", "001"), "bz": ("001", "010"), "bne": ("010", "001"),
           "blt": ("011", "001"), "ble": ("100", "001"), "bgt": ("101", "001"),
           "bge": ("110", "001"), "bv": ("111", "001")}
    for k, (bt, rts) in brt.items():
        rows[k] = _row(f"XX 0 0 0 010001 0 0 XX 00 1 {bt} 0 {rts}")
    return rows


OPCODES = {  # opcode of every mnemonic (for the "right word was fetched" sanity check)
    "nop": 0b000000, "halt": 0b111111, "li": 0b100010, "lui": 0b100011, "move": 0b100100,
    "mfhi": 0b100001, "mflo": 0b100111, "ld": 0b100101, "st": 0b100110, "j": 0b101000,
    "jal": 0b101001, "jr": 0b101011, "beq": 0b010000, "bz": 0b010001, "bne": 0b010010,
    "blt": 0b010011, "ble": 0b010100, "bgt": 0b010101, "bge": 0b010110, "bv": 0b010111,
}
for _k, _o in {"addi": 0b110000, "subi": 0b110001, "andi": 0b110010, "ori": 0b110011,
               "nori": 0b110100, "xori": 0b110101, "slli": 0b110110, "srli": 0b110111,
               "srai": 0b111000, "slti": 0b111001, "sgti": 0b111010, "slei": 0b111011,
               "sgei": 0b111100, "seqi": 0b111101, "snei": 0b111110}.items():
    OPCODES[_k] = _o
for _k in ["add", "sub", "mul", "mulu", "and", "or", "not", "nor", "xor", "sll", "srl",
           "sra", "slt", "sgt", "sle", "sge", "seq", "sne"]:
    OPCODES[_k] = 0b100000


def check_control_words(tr, instrs):
    """instrs: [(byte address, mnemonic)] in program order."""
    problems = []
    rows = appendix_a()
    pcs, st = tr.pc, tr.state
    sigs = {f: tr.sig(f) for f in FIELDS + ["pc_enable", "ic_enable", "opcode"]}
    by_pc = {}
    for i, (p, s) in enumerate(zip(pcs, st)):
        if s in (ST_RUN, ST_WAIT) and p is not None:
            by_pc.setdefault(p, []).append(i)
    for addr, mn in instrs:
        if addr not in by_pc:
            problems.append(f"{mn.upper()} @0x{addr:X}: instruction never executed")
            continue
        idxs = by_pc[addr]
        commit = next((i for i in idxs if sigs["pc_enable"][i] == 1), idxs[-1])
        first = idxs[0]
        exp_op = OPCODES[mn]
        if sigs["opcode"][commit] != exp_op:
            problems.append(f"{mn.upper()} @0x{addr:X}: opcode seen by control = "
                            f"{sigs['opcode'][commit]!r}, expected {exp_op:06b}")
            continue
        want = rows[mn]
        for f in FIELDS:
            e = want[f]
            if e is None:
                continue
            i = first if (mn == "ld" and f == "mem_read") else commit
            g = sigs[f][i]
            if g != e:
                problems.append(f"{mn.upper()} @0x{addr:X}: {f} expected {e:b}, got "
                                f"{'X' if g is None else format(g, 'b')}")
        # pc / ic enable: 1 on the commit cycle for everything except HALT
        for f in ("pc_enable", "ic_enable"):
            e = 0 if mn == "halt" else 1
            g = sigs[f][commit]
            if g != e:
                problems.append(f"{mn.upper()} @0x{addr:X}: {f} expected {e}, got {g!r}")
        if mn == "ld":
            if len(idxs) != 2:
                problems.append(f"LD @0x{addr:X}: occupies {len(idxs)} cycles, expected 2")
            elif sigs["pc_enable"][idxs[0]] != 0 or sigs["reg_write"][idxs[0]] != 0:
                problems.append("LD: pc_enable / reg_write must be 0 in the first cycle")
    return problems


# ---------------------------------------------------------------------------
# extra named checks
# ---------------------------------------------------------------------------
def check_ld_timing(tr, labels):
    a = labels["ldi"]
    idx = [i for i, (p, s) in enumerate(zip(tr.pc, tr.state)) if p == a and s in (ST_RUN, ST_WAIT)]
    problems = []
    if len(idx) != 2:
        problems.append(f"LD occupies {len(idx)} cycles at PC, expected 2 (RUN then WAIT)")
    elif [tr.state[i] for i in idx] != [ST_RUN, ST_WAIT]:
        problems.append(f"LD cycle states {[tr.state[i] for i in idx]}, expected RUN, WAIT")
    else:
        rd = tr.sig("mem_read")
        if rd[idx[0]] != 1 or rd[idx[1]] != 0:
            problems.append("mem_read must be 1 in the first LD cycle and 0 in the second")
        nxt = tr.pc[idx[1] + 1] if idx[1] + 1 < len(tr.pc) else None
        if nxt != a + 4:
            problems.append(f"PC after LD is {nxt!r}, expected 0x{a + 4:X}")
    return problems


def check_halt_frozen(tr, labels, final_pc):
    a = labels[final_pc]
    tail = list(zip(tr.pc, tr.state))[-3:]
    problems = []
    if any(p != a or s != ST_DONE for p, s in tail):
        problems.append(f"PC/FSM not frozen at HALT: last cycles (pc,state) = {tail}")
    return problems


# ---------------------------------------------------------------------------
# one test (runs in a worker process)
# ---------------------------------------------------------------------------
def run_one(t, opts):
    name = t["name"]
    tdir = OUT_DIR / safe_name(name)
    (tdir / "inputs").mkdir(parents=True, exist_ok=True)
    res = {"name": name, "group": t["group"], "ok": False, "problems": [],
           "cycles": 0, "dir": str(tdir.relative_to(ROOT)), "regs": {}}
    kind = t.get("kind", "sim")
    src = tdir / "prog.s"

    # ---- assembler-only tests -------------------------------------------------
    if kind == "encode":
        text, _, _, _ = prepare(t["asm"])
        src.write_text(text)
        ok, msg = run_assembler(src, tdir / "out.mem")
        if not ok:
            res["problems"].append(f"assembler error: {msg}")
            return res
        got = read_words(tdir / "out.mem")
        exp = t["words"]
        if len(got) != len(exp):
            res["problems"].append(f"assembler produced {len(got)} words, expected {len(exp)}")
        for i, (g, e) in enumerate(zip(got, exp)):
            if g != e:
                line = text.splitlines()[i] if i < len(text.splitlines()) else "?"
                res["problems"].append(f"word {i} '{line}': got {g:08X}, expected {e:08X}")
        res["ok"] = not res["problems"]
        return res

    # ---- simulation tests ------------------------------------------------------
    text, labels, patches, n_instr = prepare(t["asm"] + FOOTER)
    src.write_text(text)
    mem = tdir / "inputs" / "program.mem"
    ok, msg = run_assembler(src, mem)
    if not ok:
        res["problems"].append(f"assembler error: {msg}")
        return res
    words = read_words(mem)
    if len(words) != n_instr:
        res["problems"].append(f"assembler emitted {len(words)} words for {n_instr} instructions "
                               f"(parse error?) {msg}")
        return res
    for i, w in patches.items():
        words[i] = w
    padded = words + [HALT_WORD] * (ROM_WORDS - len(words))
    if len(words) > ROM_WORDS:
        res["problems"].append(f"program has {len(words)} words, ROM holds {ROM_WORDS}")
        return res
    mem.write_text("\n".join(f"{w:08X}" for w in padded) + "\n")

    vcd = tdir / "wave.vcd"
    vcd.unlink(missing_ok=True)
    cycles = t.get("cycles", opts["cycles"])
    # the simulator runs inside tdir, so a short relative path keeps +VCD well under any limit
    cmd = ["vvp", "-n", str(VVP_FILE), f"+CYCLES={cycles}", "+VCD=wave.vcd"]
    if opts["full_vcd"]:
        cmd.append("+FULLVCD")
    try:
        r = subprocess.run(cmd, cwd=tdir, capture_output=True, text=True, timeout=SIM_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        res["problems"].append(f"vvp exceeded {SIM_TIMEOUT_S}s wall clock")
        return res
    out = r.stdout + r.stderr
    (tdir / "sim.log").write_text(out)
    if r.returncode != 0 or not vcd.exists():
        res["problems"].append(f"simulation failed: {out.strip()[:400]}")
        return res

    problems = res["problems"]
    if "TB_TIMEOUT" in out:
        problems.append("watchdog fired: processor never reached HALT/DONE (hang, bad jump, "
                        "or start/reset problem)")
    tr = Trace(vcd)
    miss = tr.missing()
    if miss:
        problems.append("signals missing from VCD: " + ", ".join(m.replace(SCOPE, "") for m in miss))
        return res
    res["cycles"] = tr.n
    if tr.state[-1] != ST_DONE and "TB_TIMEOUT" not in out:
        problems.append(f"FSM state at the end is {tr.state[-1]!r}, expected DONE (3)")

    # registers / HI / LO ---------------------------------------------------------
    def resolve(v):
        return (labels[v[1:]] if isinstance(v, str) else v) & M

    if kind != "ctrl":
        exp = {k: resolve(v) for k, v in t["regs"].items()}
        for i in range(16):
            got = tr.reg(i)
            want = exp.get(i, 0)
            res["regs"][i] = got
            if got != want:
                tag = "" if i in exp else "  (not expected to change)"
                problems.append(f"${i}: expected {fmt(want)}, got {fmt(got)}{tag}")
        for key in ("hi", "lo"):
            want = t.get(key, 0) & M
            got = tr.final(RF + key)
            if got != want:
                problems.append(f"{key.upper()}: expected {fmt(want)}, got {fmt(got)}")
    else:
        for i in range(16):
            res["regs"][i] = tr.reg(i)

    # final PC and flow ---------------------------------------------------------------
    fp = t.get("final_pc", "__end")
    want_pc = labels[fp]
    got_pc = tr.final(PC_SIG)
    if got_pc != want_pc:
        problems.append(f"final PC is {got_pc!r}, expected 0x{want_pc:X} ({fp})")
    ex = tr.executed_pcs()
    for lb in t.get("visits", []):
        if labels[lb] not in ex:
            problems.append(f"label '{lb}' (0x{labels[lb]:X}) was never executed")
    for lb in t.get("skips", []):
        if labels[lb] in ex:
            problems.append(f"label '{lb}' (0x{labels[lb]:X}) was executed but should be skipped")

    # named checks -----------------------------------------------------------------------
    chk = t.get("check")
    if chk == "ld_timing":
        problems += check_ld_timing(tr, labels)
    elif chk == "halt_frozen":
        problems += check_halt_frozen(tr, labels, fp)
    if kind == "ctrl":
        instrs, idx = [], 0
        for line in text.splitlines():
            if re.fullmatch(r"\w+:", line):
                continue
            mn = line.split()[0].lower()
            if mn == "j" and line.split()[1].startswith("$"):
                mn = "jr"
            if mn == "b":
                mn = "j"
            instrs.append((idx * 4, mn))
            idx += 1
        seen = {m for _, m in instrs}
        all_mn = set(appendix_a())
        if all_mn - seen:
            problems.append("sweep program misses: " + ", ".join(sorted(all_mn - seen)))
        problems += check_control_words(tr, instrs)

    res["ok"] = not problems
    return res


# ---------------------------------------------------------------------------
def sh(cmd):
    return subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("names", nargs="*", help="run tests whose name or group contains any of these words")
    ap.add_argument("--group", action="append", help="run a whole group (substring match)")
    ap.add_argument("--list", action="store_true", help="list tests and exit")
    ap.add_argument("--no-build", action="store_true", help="do not run make first")
    ap.add_argument("--fail-fast", action="store_true")
    ap.add_argument("-j", "--jobs", type=int, default=max(1, (os.cpu_count() or 2)))
    ap.add_argument("--cycles", type=int, default=DEFAULT_CYCLES, help="watchdog per test (clock cycles)")
    ap.add_argument("--mulu", choices=["signed", "unsigned"], default="signed",
                    help="MULU = 64-bit product of two's-complement operands in HI:LO "
                         "(default). 'unsigned' treats the operands as unsigned.")
    ap.add_argument("--full-vcd", action="store_true", help="dump every signal (big, for GTKWave)")
    ap.add_argument("-v", "--verbose", action="store_true", help="print non-zero registers of each test")
    a = ap.parse_args()

    cases = load_cases().build(a.mulu)
    sel = [t for t in cases
           if (not a.names or any(n.lower() in (t["name"] + " " + t["group"]).lower() for n in a.names))
           and (not a.group or any(g.lower() in t["group"].lower() for g in a.group))]
    if a.list:
        g = None
        for t in sel:
            if t["group"] != g:
                g = t["group"]
                print(f"\n[{g}]")
            print("  ", t["name"])
        print(f"\n{len(sel)} tests")
        return
    if not sel:
        sys.exit("no test matches")

    if not a.no_build:
        r = sh(["make", "all"])
        if r.returncode:
            sys.exit("build failed:\n" + r.stdout + r.stderr)
    for need in (ASM_BIN, VVP_FILE):
        if not need.exists():
            sys.exit(f"{need} missing - run `make all`")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    opts = {"cycles": a.cycles, "full_vcd": a.full_vcd}
    print(f"Running {len(sel)} tests (MULU={a.mulu}, -j{a.jobs})")
    print("=" * 78)

    results = {}
    with cf.ProcessPoolExecutor(max_workers=a.jobs) as ex:
        futs = {ex.submit(run_one, t, opts): i for i, t in enumerate(sel)}
        try:
            for f in cf.as_completed(futs):
                r = f.result()
                results[futs[f]] = r
                if a.fail_fast and not r["ok"]:
                    for g in futs:
                        g.cancel()
                    break
        except KeyboardInterrupt:
            for g in futs:
                g.cancel()
            raise

    failed, group = [], None
    for i in sorted(results):
        r = results[i]
        if r["group"] != group:
            group = r["group"]
            print(f"\n[{group}]")
        print(f"  [{'PASS' if r['ok'] else 'FAIL'}] {r['name']:<58} {r['cycles']:>5} cyc")
        if a.verbose and r["regs"]:
            for k, v in sorted(r["regs"].items()):
                if v:
                    print(f"        ${k:<2} = {fmt(v)}")
        if not r["ok"]:
            failed.append(r)
            for p in r["problems"][:12]:
                print(f"        - {p}")
            if len(r["problems"]) > 12:
                print(f"        ... {len(r['problems']) - 12} more")
            print(f"        files: {r['dir']}/ (prog.s, wave.vcd, sim.log)")

    ran = len(results)
    print("\n" + "=" * 78)
    print(f"{ran - len(failed)}/{ran} passed" + (f", {len(sel) - ran} not run" if ran < len(sel) else ""))
    if failed:
        lines = []
        for r in failed:
            lines.append(r["name"] + f"   [{r['dir']}]")
            lines += ["    " + p for p in r["problems"]]
            lines.append("")
        (ROOT / "log.txt").write_text("\n".join(lines))
        print("Failure details written to log.txt")
        sys.exit(1)


if __name__ == "__main__":
    main()

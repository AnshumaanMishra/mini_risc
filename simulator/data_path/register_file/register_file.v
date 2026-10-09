module register_file (
    clk,
    reg_write,
    hi_lo_enable,
    rs,
    rt,
    rd,
    reg_in_hi,
    reg_in_lo,
    rs_out,
    rt_out
);
  input [31:0] reg_in_hi, reg_in_lo;
  input [4:0] rs, rt, rd;
  input clk, reg_write, hi_lo_enable;
  output [31:0] rs_out;
  output reg [31:0] rt_out;

  integer reg_index;
  reg [31:0] registers[16];
  reg [31:0] hi, lo;

  initial begin
    for (reg_index = 0; reg_index < 16; reg_index = reg_index + 1) begin
      registers[reg_index] = 32'b0;
    end
    hi = 32'b0;
    lo = 32'b0;
  end

  // Read-only probes: Icarus does not dump unpacked arrays, so each register
  // is mirrored on its own wire. run_tests.py reads r0..r15, hi and lo from the VCD.
  wire [31:0] r0 = registers[0];
  wire [31:0] r1 = registers[1];
  wire [31:0] r2 = registers[2];
  wire [31:0] r3 = registers[3];
  wire [31:0] r4 = registers[4];
  wire [31:0] r5 = registers[5];
  wire [31:0] r6 = registers[6];
  wire [31:0] r7 = registers[7];
  wire [31:0] r8 = registers[8];
  wire [31:0] r9 = registers[9];
  wire [31:0] r10 = registers[10];
  wire [31:0] r11 = registers[11];
  wire [31:0] r12 = registers[12];
  wire [31:0] r13 = registers[13];
  wire [31:0] r14 = registers[14];
  wire [31:0] r15 = registers[15];

  wire [3:0] rs_clipped, rt_clipped, rd_clipped;
  assign rs_clipped = rs[3:0];
  assign rt_clipped = rt[3:0];
  assign rd_clipped = rd[3:0];

  assign rs_out = (rs_clipped != 4'b0 && rs[4] == 0) ? registers[rs_clipped] : 32'b0;

  always @(*) begin
    if (rt[4] == 0) begin
      if (rt_clipped != 4'b0) begin
        rt_out = registers[rt_clipped];
      end else begin
        rt_out = 32'b0;
      end
    end else begin
      if (rt_clipped == 4'b0000) begin
        rt_out = hi;
      end else if (rt_clipped == 4'b0001) begin
        rt_out = lo;
      end else begin
        rt_out = 32'b0;
      end
    end
  end

  always @(posedge clk) begin
    if (reg_write) begin
      if (rd == 5'b00000) begin
      end else if (hi_lo_enable) begin
        hi <= reg_in_hi;
        lo <= reg_in_lo;
      end else if (rd[4] == 0 && rd_clipped != 4'b0) begin
        registers[rd_clipped] <= reg_in_lo;
      end
    end
  end
endmodule

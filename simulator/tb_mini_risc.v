module tb_mini_risc;
  reg clk = 1'b0;
  reg reset = 1'b1;
  reg start = 1'b0;

  integer max_cycles;
  integer cycle_count;
  reg [8191:0] vcd_path;

  mini_risc dut (
      .clk(clk),
      .reset(reset),
      .start(start)
  );

  always #5 clk = ~clk;

  initial begin
    if (!$value$plusargs("CYCLES=%d", max_cycles)) max_cycles = 20000;
    if (!$value$plusargs("VCD=%s", vcd_path)) vcd_path = "build/mini_risc.vcd";
    $dumpfile(vcd_path);
    if ($test$plusargs("FULLVCD")) begin
      $dumpvars(0, tb_mini_risc);
    end else begin
      $dumpvars(1, tb_mini_risc);
      $dumpvars(0, dut.control);
      $dumpvars(0, dut.data.rf);
      $dumpvars(0, dut.data.pc);
    end

    repeat (3) @(posedge clk);
    #1 reset = 1'b0;
    repeat (2) @(posedge clk);
    #1 start = 1'b1;
    @(posedge clk);
    #1 start = 1'b0;
  end

  initial begin
    cycle_count = 0;
    forever begin
      @(posedge clk);
      cycle_count = cycle_count + 1;
      if (dut.control.state == 2'b11) begin
        repeat (4) @(posedge clk);
        $finish;
      end
      if (cycle_count >= max_cycles) begin
        $display("TB_TIMEOUT after %0d cycles", max_cycles);
        $finish;
      end
    end
  end
endmodule

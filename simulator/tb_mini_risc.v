`timescale 1ns / 1ps

module tb_mini_risc;
  reg clk;
  reg reset;
  reg start;

  mini_risc dut (
      .clk  (clk),
      .start(start),
      .reset(reset)
  );

  initial begin
    clk = 0;
    forever #5 clk = ~clk;
  end

  initial begin
    $dumpfile("build/mini_risc.vcd");
    $dumpvars(0, tb_mini_risc);

    reset = 1;
    start = 0;

    #20;
    reset = 0;

    #10;
    start = 1;
    #10;
    start = 0;

    #100000;
    $display("Timeout reached! Simulation halted forcefully.");
    $finish;
  end
endmodule

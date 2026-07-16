`timescale 1ns / 1ps

module tb;

// -- Parameters ----------------------------------------------------------------
parameter CSR_IN_WIDTH  = 16;
parameter CSR_OUT_WIDTH = 16;
parameter REG_WIDTH     = 32;

// -- Signals -------------------------------------------------------------------
reg clk;
reg arst_n;
reg  [CSR_IN_WIDTH-1:0]  csr_in;
reg  [REG_WIDTH-1:0]     data_reg_a;
reg  [REG_WIDTH-1:0]     data_reg_b;
wire [REG_WIDTH-1:0]     data_reg_c;
wire [CSR_OUT_WIDTH-1:0] csr_out;
wire                     csr_in_re;
wire                     csr_out_we;

// -- Clock ---------------------------------------------------------------------
always #5 clk = ~clk;

// -- DUT Instantiation ---------------------------------------------------------
/* DUT_MODULE */ DUT (
    .clk       (clk),
    .arst_n    (arst_n),
    .csr_in    (csr_in),
    .data_reg_a(data_reg_a),
    .data_reg_b(data_reg_b),
    .data_reg_c(data_reg_c),
    .csr_out   (csr_out),
    .csr_in_re (csr_in_re),
    .csr_out_we(csr_out_we)
);

// -- Waveform Dump -------------------------------------------------------------
initial begin
    $dumpfile("waves.vcd");
    $dumpvars(0, tb);
end

// -- Tasks ---------------------------------------------------------------------
task write_data_reg_a(input [31:0] data);
    begin
        @(posedge clk);
        data_reg_a = data;
    end
endtask

task write_data_reg_b(input [31:0] data);
    begin
        @(posedge clk);
        data_reg_b = data;
    end
endtask

task write_csr_in(input [15:0] data);
    begin
        csr_in = data;
        @(posedge clk);
    end
endtask

task reset_csr_in;
    begin
        csr_in[15:12] = 4'b0;
    end
endtask

task read_csr_out(output [15:0] data);
    begin
        data = csr_out;
        @(posedge clk);
    end
endtask

// -- Stimulus ------------------------------------------------------------------
initial begin
    clk        = 0;
    arst_n     = 0;
    csr_in     = 0;
    data_reg_a = 0;
    data_reg_b = 0;
    repeat(2) @(posedge clk);
    arst_n = 1;
    repeat(1) @(posedge clk);

    // -- USER STIMULUS BEGIN --------------------------------------------------
    // Add your test stimulus here.
    // Example:
    //   write_data_reg_a(32'hDEADBEEF);
    //   write_data_reg_b(32'h00000001);
    //   repeat(4) @(posedge clk);
    // -- USER STIMULUS END ----------------------------------------------------

    $finish;
end

endmodule

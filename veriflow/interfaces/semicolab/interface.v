module semicolab (
    input  wire        clk,
    input  wire        arst_n,
    input  wire [15:0] csr_in,
    input  wire [31:0] data_reg_a,
    input  wire [31:0] data_reg_b,
    output wire [31:0] data_reg_c,
    output wire [15:0] csr_out,
    output wire        csr_in_re,
    output wire        csr_out_we
);
endmodule

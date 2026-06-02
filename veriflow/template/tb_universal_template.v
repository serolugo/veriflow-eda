`timescale 1ns / 1ps

module tb;

// ── Declare your signals here ─────────────────────────────────────────────────

// ── Instantiate your DUT here ─────────────────────────────────────────────────

// ── Waveform Dump ─────────────────────────────────────────────────────────────
initial begin
    $dumpfile("waves.vcd");
    $dumpvars(0, tb);
end

// ── Write your test stimulus here ─────────────────────────────────────────────
initial begin
    $finish;
end

endmodule

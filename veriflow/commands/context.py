from __future__ import annotations

import argparse

from veriflow.llms_txt import generate_llms_txt


def cmd_context(args: argparse.Namespace) -> int:
    """Implement `veriflow context`: print the consolidated LLM context
    text to stdout, for pasting into a chat/agent that has no MCP setup
    (`veriflow context > contexto.txt`)."""
    print(generate_llms_txt(), end="")
    return 0

# See LICENSE.txt

import json
import re
from typing import List


def hex_fmt(hex_str: str) -> str:
    """remove leading zeros on a hex string 0x0000ab12 -> ab12"""
    assert hex_str.startswith("0x")
    shortened = hex(int(hex_str, 0))  # remove leading zeros
    return shortened[2:]  # skip 0x prefix


def hex_fmt_sized(hex_str: str) -> str:
    """
    Format an instruction in hex coming as 0x00abcd -> 00abcd
    we leave size of instruction as is variable and size can be useful
    """
    return hex_str[2:]  # skip 0x prefix


def diss_fmt(diss: str) -> str:
    """remove duplicate spaces on input dissasembly"""
    return re.sub(r"\s+", " ", diss)


def hexstr_to_int(hex_str: str) -> int:
    """'40' -> 65"""
    return int(hex_str, 16)


def dump_compact_json(filename: str, trace: List[dict]) -> None:
    """
    Dump a trace into a file as JSON. The trace is compacted
    to one line per record in the input trace for easy viewing
    """
    with open(filename, "w") as fout:
        # custom printing to make a single line per entry
        prefix = "["
        for entry in trace:
            print(prefix + json.dumps(entry), file=fout)
            prefix = ","
        print("]", file=fout)

# See LICENSE.txt

import logging
import re

from .trace_utils import hex_fmt, diss_fmt


def clean_reg_name(name: str) -> str:
    """given a register name like 'r 3' return 'x3'"""
    return re.sub("^r *", "x", name)


def read_sifive_rtl_trace(filaname: str, core: int = -1):
    """Trace example:
    S0C0:         41 [1] pc=[0000000048000000] W[r 0=0000000000000000][0] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[0000a801] c.j     pc + 16
    S0C0:         44 [1] pc=[0000000048000010] W[r 3=0000000048000010][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[00000197] auipc   gp, 0x0
    S0C0:         45 [1] pc=[0000000048000014] W[r 3=0000000048000008][1] R[r 3=0000000048000010] R[r 0=0000000000000000] inst=[ff818193] addi    gp, gp, -8
    S0C0:        124 [1] pc=[0000000048000018] W[r 3=0000000000000000][0] R[r 3=0000000048000008] R[r 0=0000000000000000] inst=[0001b183] ld      gp, 0(gp)
    S0C0:        131 [1] pc=[000000004800001c] W[r 0=0000000000000000][0] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[0000a031] c.j     pc + 12
    S0C0:        145 [1] pc=[0000000048000028] W[r 4=0000000048000028][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[00000217] auipc   tp, 0x0
    S0C0:        145 [1] pc=[000000004800002c] W[r 4=0000000048000020][1] R[r 4=0000000048000028] R[r 0=0000000000000000] inst=[ff820213] addi    tp, tp, -8
    S0C0:        146 [1] pc=[0000000048000030] W[r 4=0000000000000000][0] R[r 4=0000000048000020] R[r 0=0000000000000000] inst=[00023203] ld      tp, 0(tp)
    S0C0:        147 [1] pc=[0000000048000034] W[r 0=0000000000000000][0] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[74446073] csrsi   mnstatus, 8
    S0C0:        152 [1] pc=[0000000048000038] W[r13=ffffffffffffffff][1] R[r 0=0000000000000000] R[r 0=0000000000000000] inst=[000056fd] c.li    a3, -1
    S0C0:        153 [1] pc=[000000004800003a] W[r 0=0000000000000000][0] R[r13=ffffffffffffffff] R[r 0=0000000000000000] inst=[3046b073] csrc    mie, a3
    """

    def match_and_remove(pattern: str, line: str):
        """
        Return a match instance for a regex search and the input str with matching
        portion removed
        """
        if match := re.match("^" + pattern, line):
            # consume the pattern
            line = re.sub("^" + pattern, "", line, count=1)
        return match, line

    hex_number = r"[0-9a-fA-F]+"
    reg_name = r"[a-z]+[ _0-9a-zA-z]+"
    pattern_reg_wr = rf"W\[({reg_name})=({hex_number})\]"

    def decode_access(line: str, line_num: int) -> dict:
        """
        Given the suffix of a line, extract register write pattern reported. E.g.

            W[r 4=0000000000000002][0] R[r 1=0000000000000001] R[r 3=0000000000000003]

            should extract ['x4', 2]
        """
        line_in = line  # save for potential error message
        access = {
            "rw": [],
            "mw": [],
            "mr": [],
        }  # general format but this trace only has "rw"
        if (line := line.lstrip()) != "":
            # register write
            match, line = match_and_remove(pattern_reg_wr, line)
            if match:
                reg_written, reg_value = clean_reg_name(
                    match.group(1)
                ), match.group(2)
                access["rw"].append([reg_written, hex_fmt("0x" + reg_value)])
            else:
                raise RuntimeError(
                    f"{line_num}:{line_in} was reduced to {line} but could not go further"
                )
        # simplify output to get a more compact JSON
        return {key: value for key, value in access.items() if len(value) != 0}

    prefix_status_upd = rf"S\d+C\d+: +(\d+) \[\d+\] +pc=\[({hex_number})\] +"
    trace = []
    line_num = 0
    with open(filaname) as fin:
        for raw_line in fin:
            line_num += 1
            line = raw_line.strip()

            # line provides status update
            match, rest = match_and_remove(prefix_status_upd, line)
            if match:
                entry = {
                    "pc": hex_fmt("0x" + match.group(2)),
                    "ins": "",
                    "asm": "",
                }
                match_ins = re.match(rf".* inst=\[({hex_number})\] (.*)", rest)
                if match_ins:
                    entry["ins"] = match_ins.group(1)
                    entry["asm"] = diss_fmt(match_ins.group(2))
                # this type of trace doesn't change the size of 'ins' for compact
                # instructions, but the dissasembly seems to consistently report
                # it as c.xxx. In those cases shorten the instruction hex for consistency
                # with other trace formats where 'ins' has the real size
                if (
                    entry["asm"].startswith("c.")
                    and entry["ins"][:4] == "0000"
                ):
                    entry["ins"] = entry["ins"][4:]
                entry.update(decode_access(rest, line_num))
                trace.append(entry)
            else:
                if match := re.match(r"S\d+C\d+.*", line):
                    # some unexpected pattern
                    logging.warning("unexpected format: {line}")
                else:
                    print("skipped:", line)
    return trace

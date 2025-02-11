# See LICENSE.txt

import re

from .trace_utils import hex_fmt, hex_fmt_sized, diss_fmt


def read_spike_trace(filaname: str, core: int = -1):
    """trace example

    core   0: 0x0000000000001000 (0x00000297) auipc   t0, 0x0
    core   0: 3 0x0000000000001000 (0x00000297) x5  0x0000000000001000
    core   0: 0x0000000000001004 (0x02028593) addi    a1, t0, 32
    core   0: 3 0x0000000000001004 (0x02028593) x11 0x0000000000001020
    core   0: 0x0000000000001008 (0xf1402573) csrr    a0, mhartid
    core   0: 3 0x0000000000001008 (0xf1402573) x10 0x0000000000000000
    core   0: 0x000000000000100c (0x0182b283) ld      t0, 24(t0)
    core   0: 3 0x000000000000100c (0x0182b283) x5  0x0000000080000000 mem 0x0000000000001018
    core   0: 0x0000000000001010 (0x00028067) jr      t0
    core   0: 3 0x0000000000001010 (0x00028067)
    core   0: >>>>  MEM_START
    core   0: 0x0000000080000000 (0x1f80006f) j       pc + 0x1f8
    core   0: 3 0x0000000080000000 (0x1f80006f)
    core   0: >>>>  do_reset
    core   0: 0x00000000800001f8 (0x00000093) li      ra, 0
    core   0: 3 0x00000000800001f8 (0x00000093) x1  0x0000000000000000

    # case of register write
    core   0: 0x0000000080004626 (0x00008fd9) c.or    a5, a4
    core   0: 3 0x0000000080004626 (0x8fd9) x15 0x0000000000000002

    # example containing register write to a4/x14 and mem read
    core   0: 0x0000000080004482 (0x000c2703) lw      a4, 0(s8)
    core   0: 3 0x0000000080004482 (0x000c2703) x14 0x0000000003000000 mem 0x0000000000001070

    # example containing memory write
    core   0: 0x0000000080004628 (0x0000c8dc) c.sw    a5, 20(s1)
    core   0: 3 0x0000000080004628 (0xc8dc) mem 0x0000000080010dac 0x00000002
    """
    hex_number = r"0x[0-9a-fA-F]+"
    reg_name = r"[a-z]+[_0-9a-zA-z]+"
    prefix = rf"core +(\d+): ({hex_number}) \(({hex_number})\)"
    prefix_status_upd = rf"core +(\d+): \d+ ({hex_number}) \(({hex_number})\)"
    pattern_diss = rf"{prefix} (.*)$"
    pattern_reg_wr = rf"({reg_name}) +({hex_number})"
    pattern_mem_wr = rf"mem ({hex_number}) ({hex_number})"
    pattern_mem_rd = rf"mem ({hex_number})"

    def match_and_remove(pattern: str, line: str):
        if match := re.match("^" + pattern, line):
            # consume the pattern
            line = re.sub("^" + pattern, "", line, count=1)
        return match, line

    def decode_access(line: str, line_num: int) -> dict:
        """
        Given the suffix of a line, extract memory and register accesses reported
        """
        line_in = line  # save for potential error message
        access = {"rw": [], "mw": [], "mr": []}
        while (line := line.lstrip()) != "":
            # order of patterns is important (most to least specific pattern)

            # memory write
            match, line = match_and_remove(pattern_mem_wr, line)
            if match:
                mem_addr = match.group(1)
                mem_value = match.group(2)
                access["mw"].append(
                    [hex_fmt(mem_addr), hex_fmt_sized(mem_value)]
                )
                continue

            # memory read
            match, line = match_and_remove(pattern_mem_rd, line)
            if match:
                mem_addr = match.group(1)
                access["mr"].append(hex_fmt_sized(mem_addr))
                continue

            # register write
            match, line = match_and_remove(pattern_reg_wr, line)
            if match:
                reg_written, reg_value = match.group(1), match.group(2)
                access["rw"].append([reg_written, hex_fmt(reg_value)])
                continue

            raise RuntimeError(
                f"{line_num}:{line_in} was reduced to {line} but could not go further"
            )
        # simplify output to get a more compact JSON
        return {key: value for key, value in access.items() if len(value) != 0}

    trace = []
    line_num = 0
    last_pc = ""
    with open(filaname) as fin:
        for raw_line in fin:
            line_num += 1
            line = raw_line.strip()
            # line provides dissasembly
            if match := re.fullmatch(pattern_diss, line):
                last_pc, last_diss = hex_fmt(match.group(2)), match.group(4)
                continue

            # line provides status update
            match, rest = match_and_remove(prefix_status_upd, line)
            if match:
                entry = {
                    "pc": hex_fmt(match.group(2)),
                    "ins": hex_fmt_sized(match.group(3)),
                }
                if last_pc == entry["pc"]:
                    entry["asm"] = diss_fmt(last_diss)
                else:
                    print(
                        f"Warning: line without previous dissasembly: {line_num}:{line}"
                    )
                last_pc = ""
                entry.update(decode_access(rest, line_num))
                trace.append(entry)
            else:
                if match := re.match(r"core (\d+):", line):
                    # core   0: 1 0xffffffc00000381c (0xdf7d)
                    # some unexpected pattern
                    print("??:", line)
                else:
                    print("skipped:", line)
    return trace

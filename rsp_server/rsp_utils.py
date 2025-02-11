"""implement some common utilities"""

# See LICENSE.txt


def get_bytes_checksum(b: bytes) -> int:
    """compute check sum modulo 256 of a byte string as expected by RSP"""
    return sum(b) % 256


def get_checksum(data: str) -> int:
    """compute check sum modulo 256 of a string as expected by RSP"""
    return sum(data.encode("utf-8")) % 256


def swap_endianess(hex_str: str) -> str:
    """'ABCDEF' -> 'EFCDAB'"""
    assert len(hex_str) % 2 == 0
    return "".join(hex_str[i : i + 2] for i in range(len(hex_str) - 2, -2, -2))


def hexstr_to_int(hex_str: str) -> int:
    """'40' -> 65"""
    return int(hex_str, 16)

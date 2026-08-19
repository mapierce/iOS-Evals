"""Minimal LLVM bitstream reader.

Enough of the format to read clang/swift serialized diagnostics (.dia). The
container is a bitstream, not text, which is why diagnostics can be consumed
structurally instead of by regex over compiler output.

Format reference: https://llvm.org/docs/BitCodeFormat.html
"""

from __future__ import annotations

from dataclasses import dataclass

# Built-in abbreviation IDs, present in every block.
END_BLOCK = 0
ENTER_SUBBLOCK = 1
DEFINE_ABBREV = 2
UNABBREV_RECORD = 3
FIRST_APPLICATION_ABBREV = 4

BLOCKINFO_BLOCK_ID = 0
BLOCKINFO_SETBID = 1

# Abbreviation operand encodings.
ENC_FIXED = 1
ENC_VBR = 2
ENC_ARRAY = 3
ENC_CHAR6 = 4
ENC_BLOB = 5

_CHAR6 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._"


class BitstreamError(RuntimeError):
    pass


@dataclass
class AbbrevOp:
    is_literal: bool
    value: int = 0        # literal value, or width for Fixed/VBR
    encoding: int = 0


@dataclass
class Record:
    code: int
    values: list[int]
    blob: bytes = b""


class BitReader:
    """Reads LSB-first, the order LLVM bitstream uses."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0  # in bits

    @property
    def at_end(self) -> bool:
        return self.pos >= len(self.data) * 8

    def read(self, n: int) -> int:
        if n == 0:
            return 0
        if self.pos + n > len(self.data) * 8:
            raise BitstreamError("read past end of bitstream")
        out = 0
        got = 0
        while got < n:
            byte = self.data[self.pos >> 3]
            bit_off = self.pos & 7
            take = min(8 - bit_off, n - got)
            chunk = (byte >> bit_off) & ((1 << take) - 1)
            out |= chunk << got
            got += take
            self.pos += take
        return out

    def read_vbr(self, n: int) -> int:
        piece = self.read(n)
        hi = 1 << (n - 1)
        if not (piece & hi):
            return piece
        out, shift = piece & (hi - 1), n - 1
        while True:
            piece = self.read(n)
            out |= (piece & (hi - 1)) << shift
            if not (piece & hi):
                return out
            shift += n - 1

    def align32(self) -> None:
        self.pos = (self.pos + 31) & ~31

    def read_blob(self, length: int) -> bytes:
        self.align32()
        start = self.pos >> 3
        self.pos += length * 8
        self.align32()
        return self.data[start : start + length]


class BitstreamReader:
    """Walks blocks and records, yielding (block_id, Record) pairs."""

    def __init__(self, data: bytes):
        self.r = BitReader(data)
        # abbrevs defined in BLOCKINFO, keyed by the block they apply to
        self.blockinfo: dict[int, list[list[AbbrevOp]]] = {}

    def _read_abbrev_def(self) -> list[AbbrevOp]:
        numops = self.r.read_vbr(5)
        ops: list[AbbrevOp] = []
        for _ in range(numops):
            if self.r.read(1):
                ops.append(AbbrevOp(True, self.r.read_vbr(8)))
                continue
            enc = self.r.read(3)
            width = self.r.read_vbr(5) if enc in (ENC_FIXED, ENC_VBR) else 0
            ops.append(AbbrevOp(False, width, enc))
        return ops

    def _read_abbrev_record(self, ops: list[AbbrevOp]) -> Record:
        vals: list[int] = []
        blob = b""

        def read_scalar(op: AbbrevOp) -> int:
            if op.encoding == ENC_FIXED:
                return self.r.read(op.value)
            if op.encoding == ENC_VBR:
                return self.r.read_vbr(op.value)
            if op.encoding == ENC_CHAR6:
                return self.r.read(6)
            raise BitstreamError(f"unexpected scalar encoding {op.encoding}")

        i = 0
        while i < len(ops):
            op = ops[i]
            if op.is_literal:
                vals.append(op.value)
            elif op.encoding == ENC_ARRAY:
                count = self.r.read_vbr(6)
                elem = ops[i + 1]
                i += 1
                for _ in range(count):
                    vals.append(elem.value if elem.is_literal else read_scalar(elem))
            elif op.encoding == ENC_BLOB:
                blob = self.r.read_blob(self.r.read_vbr(6))
            else:
                vals.append(read_scalar(op))
            i += 1

        if not vals:
            raise BitstreamError("abbreviated record with no code")
        return Record(vals[0], vals[1:], blob)

    def records(self):
        """Yield (block_id, Record) for every record in the stream."""
        stack: list[tuple[int, list[list[AbbrevOp]]]] = []
        abbrev_len = 2
        cur_block = -1
        abbrevs: list[list[AbbrevOp]] = []
        len_stack: list[int] = []
        blockinfo_target = -1

        while not self.r.at_end:
            try:
                code = self.r.read(abbrev_len)
            except BitstreamError:
                return

            if code == END_BLOCK:
                self.r.align32()
                if not stack:
                    return
                cur_block, abbrevs = stack.pop()
                abbrev_len = len_stack.pop()
                continue

            if code == ENTER_SUBBLOCK:
                block_id = self.r.read_vbr(8)
                new_len = self.r.read_vbr(4)
                self.r.align32()
                self.r.read(32)  # block length in words, unused
                stack.append((cur_block, abbrevs))
                len_stack.append(abbrev_len)
                cur_block, abbrev_len = block_id, new_len
                abbrevs = list(self.blockinfo.get(block_id, []))
                continue

            if code == DEFINE_ABBREV:
                ops = self._read_abbrev_def()
                if cur_block == BLOCKINFO_BLOCK_ID:
                    self.blockinfo.setdefault(blockinfo_target, []).append(ops)
                else:
                    abbrevs.append(ops)
                continue

            if code == UNABBREV_RECORD:
                rec_code = self.r.read_vbr(6)
                numops = self.r.read_vbr(6)
                vals = [self.r.read_vbr(6) for _ in range(numops)]
                rec = Record(rec_code, vals)
            else:
                idx = code - FIRST_APPLICATION_ABBREV
                if idx < 0 or idx >= len(abbrevs):
                    raise BitstreamError(
                        f"undefined abbrev {code} in block {cur_block}"
                    )
                rec = self._read_abbrev_record(abbrevs[idx])

            if cur_block == BLOCKINFO_BLOCK_ID and rec.code == BLOCKINFO_SETBID:
                blockinfo_target = rec.values[0]
                continue

            yield cur_block, rec

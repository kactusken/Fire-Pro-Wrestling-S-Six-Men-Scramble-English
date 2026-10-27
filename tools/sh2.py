#!/usr/bin/env python3
"""SH-2 disassembler and small assembler for Sega Saturn code (SH7604; standard library only).

One opcode table drives both directions, so disassemble(assemble(x)) round-trips. It covers the
SH-1 set plus the SH-2 additions (mul.l, dmuls.l/dmulu.l, dt, mac.l, bf/s, bt/s, braf, bsrf);
no SH-3/SH-4, DSP or FPU instructions. Big-endian, 16-bit instructions.

Usage (<file> is a raw binary such as 1ST_READ.BIN; <base> its load address, default 0x06004000):
  sh2.py dis <file> [base [start [end]]]      list start..end (default: 64 instructions)
  sh2.py refs <file> <base> <addr> [end]      literal-pool loads, mova and data words equal to
                                              addr (or in addr..end)
  sh2.py calls <file> <base> [addr]           bsr/jsr/bsrf (and jumps) to addr; without addr,
                                              every resolvable call target with a count
  sh2.py asm <src> <addr> [-o out.bin] [-D NAME=0x...]   assemble and list (or write) the bytes
  sh2.py test                                 selftest

    code, symbols = assemble(source, base=0x06010000, symbols={"PRINT": 0x0600A000})

Listing: `06004000: d402       mov.l @(0x0600400C),r4 ; =0x060312A0`. A leading `_` marks a
delay-slot instruction. PC-relative loads show their pool address and the constant (and the pool
entry itself is listed as .long/.word once a load above it used it); jsr/jmp/braf/bsrf show
their target when a literal load (or mov/add #) into the register was seen earlier in the same
straight line (tracking resets after an unconditional jump; a call drops r0-r7).

PC-relative addressing (PC = instruction address):
  mov.l @(disp,PC),Rn / mova   (PC & ~3) + 4 + disp*4      (disp 0..255, unsigned)
  mov.w @(disp,PC),Rn          PC + 4 + disp*2, the word sign-extended
  bt/bf/bt/s/bf/s              PC + 4 + disp*2 (8-bit signed);  bra/bsr: 12-bit signed
  braf/bsrf Rn                 PC + 4 + Rn
Delay slots: bra, bsr, braf, bsrf, jmp, jsr, rts, rte, bt/s and bf/s run the next instruction
before the jump. A branch or trapa in a slot is illegal (slot illegal instruction exception). For a
PC-relative op in a slot, the Hitachi manuals (SH-2E/SH-3 wording: "PC points to the starting
address of the branch destination + 2") make the base the branch target, not the slot: this
tool computes such a pool as if the instruction sat at target-2 (for bt/s / bf/s: the taken
target), and shows `@(disp,pc)` when the target isn't known (rts, jmp...). Compilers never put
PC-relative ops in slots and it is untested on hardware, so the assembler refuses them there.

Assembler syntax: `label:`, `; comment` or `! comment`, registers r0-r15 (sp = r15), numbers
0x.. or decimal, symbol+N. `mov.l LABEL,rn` (or `@(LABEL),rn`) loads from an explicit `.long`;
`mov.l =EXPR,rn` puts EXPR in a literal pool emitted at the next `.pool` (place it where it is
never executed: after an rts and its slot). Data: .byte/.word (16-bit)/.long (32-bit),
.align N (to 2**N bytes), .pool. No slot scheduling: write the slot yourself.
"""
import re
import struct
import sys

BASE = 0x06004000  # usual Saturn 1ST_READ load address

# (mnemonic, operands, encoding). Encoding letters are fields: n = register in the encoding's n
# position, m = the m position, i = 8-bit immediate, d = displacement. Operand placeholders:
# {n}/{m} register, {s}/{u} signed/unsigned immediate, {d1}/{d2}/{d4} displacement in bytes (field
# scaled by 1/2/4), {pw}/{pl} PC-relative word/long address, {b} branch target (8 or 12 bits).
# The manual's "Rn" of mov.b r0,@(disp,Rn) sits in bits 7-4, so it is written {m} here.
TABLE = [
    ('clrt', '', '0000 0000 0000 1000'),
    ('clrmac', '', '0000 0000 0010 1000'),
    ('div0u', '', '0000 0000 0001 1001'),
    ('nop', '', '0000 0000 0000 1001'),
    ('rte', '', '0000 0000 0010 1011'),
    ('rts', '', '0000 0000 0000 1011'),
    ('sett', '', '0000 0000 0001 1000'),
    ('sleep', '', '0000 0000 0001 1011'),
    # one register
    ('movt', '{n}', '0000 nnnn 0010 1001'),
    ('dt', '{n}', '0100 nnnn 0001 0000'),
    ('cmp/pz', '{n}', '0100 nnnn 0001 0001'),
    ('cmp/pl', '{n}', '0100 nnnn 0001 0101'),
    ('rotl', '{n}', '0100 nnnn 0000 0100'),
    ('rotr', '{n}', '0100 nnnn 0000 0101'),
    ('rotcl', '{n}', '0100 nnnn 0010 0100'),
    ('rotcr', '{n}', '0100 nnnn 0010 0101'),
    ('shal', '{n}', '0100 nnnn 0010 0000'),
    ('shar', '{n}', '0100 nnnn 0010 0001'),
    ('shll', '{n}', '0100 nnnn 0000 0000'),
    ('shlr', '{n}', '0100 nnnn 0000 0001'),
    ('shll2', '{n}', '0100 nnnn 0000 1000'),
    ('shlr2', '{n}', '0100 nnnn 0000 1001'),
    ('shll8', '{n}', '0100 nnnn 0001 1000'),
    ('shlr8', '{n}', '0100 nnnn 0001 1001'),
    ('shll16', '{n}', '0100 nnnn 0010 1000'),
    ('shlr16', '{n}', '0100 nnnn 0010 1001'),
    ('tas.b', '@{n}', '0100 nnnn 0001 1011'),
    ('jmp', '@{n}', '0100 nnnn 0010 1011'),
    ('jsr', '@{n}', '0100 nnnn 0000 1011'),
    ('braf', '{n}', '0000 nnnn 0010 0011'),
    ('bsrf', '{n}', '0000 nnnn 0000 0011'),
    # control and system registers
    ('ldc', '{n},sr', '0100 nnnn 0000 1110'),
    ('ldc', '{n},gbr', '0100 nnnn 0001 1110'),
    ('ldc', '{n},vbr', '0100 nnnn 0010 1110'),
    ('ldc.l', '@{n}+,sr', '0100 nnnn 0000 0111'),
    ('ldc.l', '@{n}+,gbr', '0100 nnnn 0001 0111'),
    ('ldc.l', '@{n}+,vbr', '0100 nnnn 0010 0111'),
    ('lds', '{n},mach', '0100 nnnn 0000 1010'),
    ('lds', '{n},macl', '0100 nnnn 0001 1010'),
    ('lds', '{n},pr', '0100 nnnn 0010 1010'),
    ('lds.l', '@{n}+,mach', '0100 nnnn 0000 0110'),
    ('lds.l', '@{n}+,macl', '0100 nnnn 0001 0110'),
    ('lds.l', '@{n}+,pr', '0100 nnnn 0010 0110'),
    ('stc', 'sr,{n}', '0000 nnnn 0000 0010'),
    ('stc', 'gbr,{n}', '0000 nnnn 0001 0010'),
    ('stc', 'vbr,{n}', '0000 nnnn 0010 0010'),
    ('stc.l', 'sr,@-{n}', '0100 nnnn 0000 0011'),
    ('stc.l', 'gbr,@-{n}', '0100 nnnn 0001 0011'),
    ('stc.l', 'vbr,@-{n}', '0100 nnnn 0010 0011'),
    ('sts', 'mach,{n}', '0000 nnnn 0000 1010'),
    ('sts', 'macl,{n}', '0000 nnnn 0001 1010'),
    ('sts', 'pr,{n}', '0000 nnnn 0010 1010'),
    ('sts.l', 'mach,@-{n}', '0100 nnnn 0000 0010'),
    ('sts.l', 'macl,@-{n}', '0100 nnnn 0001 0010'),
    ('sts.l', 'pr,@-{n}', '0100 nnnn 0010 0010'),
    # two registers: data transfer
    ('mov', '{m},{n}', '0110 nnnn mmmm 0011'),
    ('mov.b', '{m},@{n}', '0010 nnnn mmmm 0000'),
    ('mov.w', '{m},@{n}', '0010 nnnn mmmm 0001'),
    ('mov.l', '{m},@{n}', '0010 nnnn mmmm 0010'),
    ('mov.b', '@{m},{n}', '0110 nnnn mmmm 0000'),
    ('mov.w', '@{m},{n}', '0110 nnnn mmmm 0001'),
    ('mov.l', '@{m},{n}', '0110 nnnn mmmm 0010'),
    ('mov.b', '{m},@-{n}', '0010 nnnn mmmm 0100'),
    ('mov.w', '{m},@-{n}', '0010 nnnn mmmm 0101'),
    ('mov.l', '{m},@-{n}', '0010 nnnn mmmm 0110'),
    ('mov.b', '@{m}+,{n}', '0110 nnnn mmmm 0100'),
    ('mov.w', '@{m}+,{n}', '0110 nnnn mmmm 0101'),
    ('mov.l', '@{m}+,{n}', '0110 nnnn mmmm 0110'),
    ('mov.b', '{m},@(r0,{n})', '0000 nnnn mmmm 0100'),
    ('mov.w', '{m},@(r0,{n})', '0000 nnnn mmmm 0101'),
    ('mov.l', '{m},@(r0,{n})', '0000 nnnn mmmm 0110'),
    ('mov.b', '@(r0,{m}),{n}', '0000 nnnn mmmm 1100'),
    ('mov.w', '@(r0,{m}),{n}', '0000 nnnn mmmm 1101'),
    ('mov.l', '@(r0,{m}),{n}', '0000 nnnn mmmm 1110'),
    ('swap.b', '{m},{n}', '0110 nnnn mmmm 1000'),
    ('swap.w', '{m},{n}', '0110 nnnn mmmm 1001'),
    ('xtrct', '{m},{n}', '0010 nnnn mmmm 1101'),
    # two registers: arithmetic and logic
    ('add', '{m},{n}', '0011 nnnn mmmm 1100'),
    ('addc', '{m},{n}', '0011 nnnn mmmm 1110'),
    ('addv', '{m},{n}', '0011 nnnn mmmm 1111'),
    ('cmp/eq', '{m},{n}', '0011 nnnn mmmm 0000'),
    ('cmp/hs', '{m},{n}', '0011 nnnn mmmm 0010'),
    ('cmp/ge', '{m},{n}', '0011 nnnn mmmm 0011'),
    ('cmp/hi', '{m},{n}', '0011 nnnn mmmm 0110'),
    ('cmp/gt', '{m},{n}', '0011 nnnn mmmm 0111'),
    ('cmp/str', '{m},{n}', '0010 nnnn mmmm 1100'),
    ('div1', '{m},{n}', '0011 nnnn mmmm 0100'),
    ('div0s', '{m},{n}', '0010 nnnn mmmm 0111'),
    ('dmuls.l', '{m},{n}', '0011 nnnn mmmm 1101'),
    ('dmulu.l', '{m},{n}', '0011 nnnn mmmm 0101'),
    ('exts.b', '{m},{n}', '0110 nnnn mmmm 1110'),
    ('exts.w', '{m},{n}', '0110 nnnn mmmm 1111'),
    ('extu.b', '{m},{n}', '0110 nnnn mmmm 1100'),
    ('extu.w', '{m},{n}', '0110 nnnn mmmm 1101'),
    ('mac.l', '@{m}+,@{n}+', '0000 nnnn mmmm 1111'),
    ('mac.w', '@{m}+,@{n}+', '0100 nnnn mmmm 1111'),
    ('mul.l', '{m},{n}', '0000 nnnn mmmm 0111'),
    ('muls.w', '{m},{n}', '0010 nnnn mmmm 1111'),
    ('mulu.w', '{m},{n}', '0010 nnnn mmmm 1110'),
    ('neg', '{m},{n}', '0110 nnnn mmmm 1011'),
    ('negc', '{m},{n}', '0110 nnnn mmmm 1010'),
    ('sub', '{m},{n}', '0011 nnnn mmmm 1000'),
    ('subc', '{m},{n}', '0011 nnnn mmmm 1010'),
    ('subv', '{m},{n}', '0011 nnnn mmmm 1011'),
    ('and', '{m},{n}', '0010 nnnn mmmm 1001'),
    ('not', '{m},{n}', '0110 nnnn mmmm 0111'),
    ('or', '{m},{n}', '0010 nnnn mmmm 1011'),
    ('tst', '{m},{n}', '0010 nnnn mmmm 1000'),
    ('xor', '{m},{n}', '0010 nnnn mmmm 1010'),
    # immediates (mov/add/cmp sign-extend, logic ops zero-extend)
    ('mov', '#{s},{n}', '1110 nnnn iiii iiii'),
    ('add', '#{s},{n}', '0111 nnnn iiii iiii'),
    ('cmp/eq', '#{s},r0', '1000 1000 iiii iiii'),
    ('and', '#{u},r0', '1100 1001 iiii iiii'),
    ('or', '#{u},r0', '1100 1011 iiii iiii'),
    ('tst', '#{u},r0', '1100 1000 iiii iiii'),
    ('xor', '#{u},r0', '1100 1010 iiii iiii'),
    ('and.b', '#{u},@(r0,gbr)', '1100 1101 iiii iiii'),
    ('or.b', '#{u},@(r0,gbr)', '1100 1111 iiii iiii'),
    ('tst.b', '#{u},@(r0,gbr)', '1100 1100 iiii iiii'),
    ('xor.b', '#{u},@(r0,gbr)', '1100 1110 iiii iiii'),
    ('trapa', '#{u}', '1100 0011 iiii iiii'),
    # displacements
    ('mov.b', 'r0,@({d1},{m})', '1000 0000 mmmm dddd'),
    ('mov.w', 'r0,@({d2},{m})', '1000 0001 mmmm dddd'),
    ('mov.l', '{m},@({d4},{n})', '0001 nnnn mmmm dddd'),
    ('mov.b', '@({d1},{m}),r0', '1000 0100 mmmm dddd'),
    ('mov.w', '@({d2},{m}),r0', '1000 0101 mmmm dddd'),
    ('mov.l', '@({d4},{m}),{n}', '0101 nnnn mmmm dddd'),
    ('mov.b', 'r0,@({d1},gbr)', '1100 0000 dddd dddd'),
    ('mov.w', 'r0,@({d2},gbr)', '1100 0001 dddd dddd'),
    ('mov.l', 'r0,@({d4},gbr)', '1100 0010 dddd dddd'),
    ('mov.b', '@({d1},gbr),r0', '1100 0100 dddd dddd'),
    ('mov.w', '@({d2},gbr),r0', '1100 0101 dddd dddd'),
    ('mov.l', '@({d4},gbr),r0', '1100 0110 dddd dddd'),
    # PC-relative
    ('mova', '@({pl}),r0', '1100 0111 dddd dddd'),
    ('mov.w', '@({pw}),{n}', '1001 nnnn dddd dddd'),
    ('mov.l', '@({pl}),{n}', '1101 nnnn dddd dddd'),
    ('bf', '{b}', '1000 1011 dddd dddd'),
    ('bt', '{b}', '1000 1001 dddd dddd'),
    ('bf/s', '{b}', '1000 1111 dddd dddd'),
    ('bt/s', '{b}', '1000 1101 dddd dddd'),
    ('bra', '{b}', '1010 dddd dddd dddd'),
    ('bsr', '{b}', '1011 dddd dddd dddd'),
]

DELAYED = {'bra', 'bsr', 'braf', 'bsrf', 'jmp', 'jsr', 'rts', 'rte', 'bt/s', 'bf/s'}
SLOT_ILLEGAL = DELAYED | {'bt', 'bf', 'trapa'}
CALLS = {'bsr', 'jsr', 'bsrf'}
JUMPS = {'bra', 'jmp', 'braf', 'bt', 'bf', 'bt/s', 'bf/s'}
ALIASES = {'bt.s': 'bt/s', 'bf.s': 'bf/s', 'muls': 'muls.w', 'mulu': 'mulu.w'}
# instructions whose last register operand is read, not written (they set T or MACH/MACL)
READ_ONLY = {'tst', 'div0s', 'mul.l', 'muls.w', 'mulu.w', 'dmuls.l', 'dmulu.l', 'braf', 'bsrf'}
FIELD = {'n': 'n', 'm': 'm', 's': 'i', 'u': 'i', 'd1': 'd', 'd2': 'd', 'd4': 'd',
         'pw': 'd', 'pl': 'd', 'b': 'd'}
REG_RE = r'(r1[0-5]|r[0-9]|sp)'


class AsmError(Exception):
    pass


def split_ops(s):
    """Split an operand string on commas outside parentheses."""
    out, depth, cur = [], 0, ''
    for c in s:
        depth += (c == '(') - (c == ')')
        if c == ',' and depth == 0:
            out.append(cur)
            cur = ''
        else:
            cur += c
    return out + [cur] if cur or out else []


class Op:
    """One table row: match/decode data plus the regex the assembler matches operands with."""

    def __init__(self, mnem, ops, enc):
        enc = enc.replace(' ', '')
        self.mnem, self.ops = mnem, ops
        self.mask = int(''.join('1' if c in '01' else '0' for c in enc), 2)
        self.value = int(''.join(c if c in '01' else '0' for c in enc), 2)
        self.fields = {}  # letter -> (shift, width)
        for c in set(enc) - set('01'):
            pos = [15 - i for i, x in enumerate(enc) if x == c]
            self.fields[c] = (min(pos), len(pos))
        parts = re.split(r'\{(\w+)\}', ops)
        self.names = parts[1::2]
        rx = ''.join(re.escape(p) if k % 2 == 0 else (REG_RE if p in 'nm' else '(.+?)')
                     for k, p in enumerate(parts))
        self.regex = re.compile(rx, re.I)
        self.pcrel = 'pl' in self.names or 'pw' in self.names
        # registers the instruction writes (for the listing's literal tracking)
        self.writes = []
        operands = split_ops(ops)
        for o in operands:
            mo = re.fullmatch(r'@-\{(\w)\}|@\{(\w)\}\+', o)
            if mo:
                self.writes.append(mo.group(1) or mo.group(2))
        if operands and not mnem.startswith('cmp/') and mnem not in READ_ONLY:
            if re.fullmatch(r'\{[nm]\}', operands[-1]):
                self.writes.append(operands[-1][1])
            elif operands[-1] == 'r0':
                self.writes.append('r0')

    def field(self, w, c):
        sh, wd = self.fields[c]
        return (w >> sh) & ((1 << wd) - 1)

    def encode(self, groups, pc, symbols):
        w = self.value
        for name, text in zip(self.names, groups):
            c = FIELD[name]
            sh, wd = self.fields[c]
            if name in 'nm':
                v = reg(text)
            elif name in ('s', 'u'):
                v = evaluate(text, symbols)
                if not -0x80 <= v <= 0xFF:
                    raise AsmError(f'immediate out of range: {text} = {v}')
            elif name in ('d1', 'd2', 'd4'):
                scale = int(name[1])
                v = evaluate(text, symbols)
                if v % scale or not 0 <= v // scale < 1 << wd:
                    raise AsmError(f'displacement {v} not a multiple of {scale} in 0..{scale * ((1 << wd) - 1)}')
                v //= scale
            else:
                t = evaluate(text, symbols) & 0xFFFFFFFF
                if name == 'pl':
                    if t % 4:
                        raise AsmError(f'pc-relative long target {t:#x} not 4-aligned')
                    v = (t - ((pc & ~3) + 4)) // 4
                    lo, hi = 0, 255
                else:
                    if t % 2:
                        raise AsmError(f'target {t:#x} is odd')
                    v = (t - (pc + 4)) // 2
                    lo, hi = (0, 255) if name == 'pw' else (-(1 << (wd - 1)), (1 << (wd - 1)) - 1)
                if not lo <= v <= hi:
                    raise AsmError(f'{self.mnem} target {t:#010x} out of range from {pc:#010x}')
            w |= (v & ((1 << wd) - 1)) << sh
        return w


OPS = [Op(*row) for row in TABLE]
BY_NIBBLE = [[op for op in OPS if op.value >> 12 == k] for k in range(16)]  # every row fixes bits 15-12
BY_MNEM = {}
for _op in OPS:
    BY_MNEM.setdefault(_op.mnem, []).append(_op)
_DECODED = None


def decode(w):
    """The table row for a 16-bit word, or None for an illegal word."""
    global _DECODED
    if _DECODED is None:
        _DECODED = [next((op for op in BY_NIBBLE[x >> 12] if x & op.mask == op.value), None)
                    for x in range(0x10000)]
    return _DECODED[w]


def sext(v, bits):
    return v - (1 << bits) if v & (1 << (bits - 1)) else v


def operands(op, w, pc, in_slot=False, dest=None):
    """Operand values by placeholder; a PC-relative address is None when it can't be known.
    In a delay slot the PC-relative base is the branch target + 2 (dest), see the docstring."""
    vals = {}
    for name in op.names:
        c = FIELD[name]
        f = op.field(w, c)
        if name in 'nm' or name == 'u':
            vals[name] = f
        elif name == 's':
            vals[name] = sext(f, 8)
        elif name in ('d1', 'd2', 'd4'):
            vals[name] = f * int(name[1])
        elif name == 'b':
            vals[name] = (pc + 4 + sext(f, op.fields['d'][1]) * 2) & 0xFFFFFFFF
        else:
            base = pc + 4 if not in_slot else (None if dest is None else dest + 2)
            vals['_d'] = f * (4 if name == 'pl' else 2)
            if base is None:
                vals[name] = None
            elif name == 'pl':
                vals[name] = ((base & ~3) + f * 4) & 0xFFFFFFFF
            else:
                vals[name] = (base + f * 2) & 0xFFFFFFFF
    return vals


def text_of(op, vals):
    def sub(mo):
        k = mo.group(1)
        v = vals[k]
        if k in 'nm':
            return f'r{v}'
        if k == 'u':
            return f'0x{v:02X}'
        if k in ('s', 'd1', 'd2', 'd4'):
            return str(v)
        if v is None:  # pc-relative in a slot whose branch target is unknown
            return f'{vals["_d"]},pc'
        return f'0x{v:08X}'
    ops = re.sub(r'\{(\w+)\}', sub, op.ops)
    return f'{op.mnem} {ops}' if ops else op.mnem


def disassemble(w, pc=BASE, in_slot=False, dest=None):
    """Text for one instruction word at pc (`.word 0x....` if illegal)."""
    op = decode(w)
    if op is None:
        return f'.word 0x{w:04X}'
    return text_of(op, operands(op, w, pc, in_slot, dest))


# ---------------------------------------------------------------- assembler

def reg(tok):
    tok = tok.strip().lower()
    if tok == 'sp':
        return 15
    if not re.fullmatch(r'r1[0-5]|r[0-9]', tok):
        raise AsmError(f'bad register {tok!r}')
    return int(tok[1:])


def evaluate(expr, symbols):
    tokens = re.findall(r'[+-]|[^+-]+', expr.replace(' ', ''))
    total, sign = 0, 1
    for t in tokens:
        if t == '+':
            continue
        if t == '-':
            sign = -sign
            continue
        if re.fullmatch(r'0x[0-9a-fA-F]+|\d+', t):
            val = int(t, 0)
        elif re.fullmatch(r'(?i)r1[0-5]|r[0-9]|sp|pc|gbr', t):
            raise AsmError(f'register {t!r} where a number was expected')
        elif t in symbols:
            val = symbols[t]
        else:
            raise AsmError(f'unknown symbol {t!r}')
        total += sign * val
        sign = 1
    if not tokens:
        raise AsmError('empty expression')
    return total


def encode(mnem, ops, pc, symbols):
    """One instruction word: tries each table row of the mnemonic whose operand shape matches."""
    mnem = ALIASES.get(mnem.lower(), mnem.lower())
    if mnem not in BY_MNEM:
        raise AsmError(f'unknown instruction {mnem!r}')
    s = re.sub(r'\s+', '', ops)
    # `mov.l LABEL,rn` / `mova LABEL,r0`: the bare-label form of a PC-relative load
    if mnem in ('mov.l', 'mov.w', 'mova') and s and s[0] not in '@#' \
            and not re.match(REG_RE + '(,|$)', s, re.I):
        left, _, right = s.rpartition(',')
        s = f'@({left}),{right}'
    err = None
    for op in BY_MNEM[mnem]:
        mo = op.regex.fullmatch(s)
        if not mo:
            continue
        try:
            return op.encode(mo.groups(), pc, symbols)
        except AsmError as e:
            err = err or e
    raise err or AsmError(f'bad operands for {mnem}: {ops!r}')


def lines_of(source):
    for no, raw in enumerate(source.splitlines(), 1):
        line = raw.split(';')[0].split('!')[0].strip()
        if line:
            yield no, line


def assemble(source, base, symbols=None):
    """Assemble source at base -> (big-endian bytes, symbols including labels)."""
    symbols = dict(symbols or {})
    pc = base
    items = []    # (pc, mnemonic, operand string, line number)
    pending = {}  # literal pool: expression -> label, waiting for .pool
    for no, line in lines_of(source):
        while re.match(r'[\w.]+:', line):
            label, _, line = line.partition(':')
            symbols[label.strip()] = pc
            line = line.strip()
        if not line:
            continue
        mnem, _, ops = line.partition(' ')
        mnem, ops = mnem.lower(), ops.strip()
        if mnem in ('.byte', '.word', '.long'):
            items.append((pc, mnem, ops, no))
            pc += {'.byte': 1, '.word': 2, '.long': 4}[mnem] * len(split_ops(ops))
            continue
        if mnem == '.align':
            pad = (-pc) % (1 << int(ops, 0))
            items.append((pc, '.byte', ','.join(['0'] * pad), no))
            pc += pad
            continue
        if mnem == '.pool':
            if pc % 4:
                items.append((pc, '.word', '0x0009', no))  # pad with a nop
                pc += 2
            for expr, label in pending.items():
                symbols[label] = pc
                items.append((pc, '.long', expr, no))
                pc += 4
            pending = {}
            continue
        if mnem == 'mov.l' and ops.startswith('='):
            expr, _, rn = ops[1:].rpartition(',')
            label = pending.setdefault(expr.strip(), f'__lit{len(symbols)}_{no}')
            ops = f'{label},{rn}'
        if pc % 2:
            raise AsmError(f'line {no}: instruction at odd address {pc:#x}')
        items.append((pc, mnem, ops, no))
        pc += 2
    if pending:
        raise AsmError(f'literals {", ".join(pending)} without a following .pool')
    out = bytearray()
    prev = None  # mnemonic of the previous instruction when it has a delay slot
    for pc, mnem, ops, no in items:
        if mnem.startswith('.'):
            if prev:
                raise AsmError(f'line {no}: data in the delay slot of {prev}')
            size = {'.byte': 1, '.word': 2, '.long': 4}[mnem]
            for o in split_ops(ops):
                v = evaluate(o, symbols) & ((1 << 8 * size) - 1) if ops else 0
                out += v.to_bytes(size, 'big')
            continue
        try:
            w = encode(mnem, ops, pc, symbols)
        except AsmError as e:
            raise AsmError(f'line {no}: {e}') from None
        op = decode(w)
        if prev and op.mnem in SLOT_ILLEGAL:
            raise AsmError(f'line {no}: {op.mnem} in the delay slot of {prev} (slot illegal)')
        if prev and op.pcrel:
            raise AsmError(f'line {no}: PC-relative {op.mnem} in the delay slot of {prev} '
                           '(its base would be the branch target)')
        out += struct.pack('>H', w)
        prev = op.mnem if op.mnem in DELAYED else None
    if prev:
        raise AsmError(f'{prev} at the end without its delay slot')
    return bytes(out), symbols


# ---------------------------------------------------------------- analysis

class Image:
    """A raw binary loaded at base (e.g. 1ST_READ.BIN at 0x06004000)."""

    def __init__(self, data, base=BASE):
        self.data = data if isinstance(data, bytes) else open(data, 'rb').read()
        self.base = base
        self.end = base + len(self.data)

    def contains(self, addr, size=2):
        return self.base <= addr and addr + size <= self.end

    def half(self, addr):
        return struct.unpack_from('>H', self.data, addr - self.base)[0]

    def long(self, addr):
        return struct.unpack_from('>I', self.data, addr - self.base)[0]


def walk(img, start, end):
    """Yield (pc, word, op, vals, in_slot, info) for start..end, following literal loads.
    info: 'pool_addr'/'pool' for PC-relative loads, 'addr' for mova, 'target' for branches,
    'data' (2 or 4, op None) for a pool entry an earlier load in this walk used."""
    known = {}    # register -> constant seen loaded into it
    prev = None   # (op, target) of the previous instruction when it has a delay slot
    if img.contains(start - 2):
        op = decode(img.half(start - 2))
        if op and op.mnem in DELAYED:
            prev = (op, operands(op, img.half(start - 2), start - 2).get('b'))
    pools = {}    # pool address -> size, for loads already seen: listed as data
    pc = start - 2
    while pc + 2 < min(end, img.end - 1):
        pc += 2
        in_slot = prev is not None
        if not in_slot and pools.get(pc) == 4 and img.contains(pc, 4):
            yield pc, img.long(pc), None, {}, False, {'data': 4}
            pc += 2
            continue
        if not in_slot and pc in pools:
            yield pc, img.half(pc), None, {}, False, {'data': 2}
            continue
        w = img.half(pc)
        op = decode(w)
        dest = prev[1] if in_slot else None
        if op is None:
            yield pc, w, None, {}, in_slot, {}
            prev = None
            continue
        vals = operands(op, w, pc, in_slot, dest)
        info = {}
        m = op.mnem
        if op.pcrel:
            a = vals.get('pl', vals.get('pw'))
            if m == 'mova':
                if a is not None:
                    info['addr'] = a
            elif a is not None:
                info['pool_addr'] = a
                pools[a] = 4 if 'pl' in vals else 2
                if 'pl' in vals and img.contains(a, 4):
                    info['pool'] = img.long(a)
                elif 'pw' in vals and img.contains(a, 2):
                    info['pool'] = sext(img.half(a), 16) & 0xFFFFFFFF
        if 'b' in vals:
            info['target'] = vals['b']
        elif m in ('jmp', 'jsr') and vals['n'] in known:
            info['target'] = known[vals['n']]
        elif m in ('braf', 'bsrf') and vals['n'] in known:
            info['target'] = (pc + 4 + known[vals['n']]) & 0xFFFFFFFF
        yield pc, w, op, vals, in_slot, info
        # follow constants through registers
        if m in ('mov.l', 'mov.w') and op.pcrel:
            if 'pool' in info:
                known[vals['n']] = info['pool']
            else:
                known.pop(vals['n'], None)
        elif m == 'mova':
            if 'addr' in info:
                known[0] = info['addr']
            else:
                known.pop(0, None)
        elif m == 'mov' and 's' in vals:
            known[vals['n']] = vals['s'] & 0xFFFFFFFF
        elif m == 'mov':
            if vals['m'] in known:
                known[vals['n']] = known[vals['m']]
            else:
                known.pop(vals['n'], None)
        elif m == 'add' and 's' in vals and vals['n'] in known:
            known[vals['n']] = (known[vals['n']] + vals['s']) & 0xFFFFFFFF
        else:
            for r in op.writes:
                known.pop(0 if r == 'r0' else vals[r], None)
        if in_slot:  # the branch takes effect after its slot
            if prev[0].mnem in ('bra', 'braf', 'jmp', 'rts', 'rte'):
                known.clear()
            elif prev[0].mnem in CALLS:
                for r in range(8):
                    known.pop(r, None)
        prev = (op, info.get('target')) if m in DELAYED else None


def describe(op, vals, w, in_slot, info):
    """Listing text with its comment."""
    if info.get('data') == 4:
        return f'.long 0x{w:08X}'
    if op is None:
        return f'.word 0x{w:04X}' + (' ; illegal' if not info else '')
    text = text_of(op, vals)
    notes = []
    if 'pool' in info:
        v = info['pool']
        notes.append(f'=0x{v:08X}' if 'pl' in vals else f'=0x{v & 0xFFFF:04X}' + (
            f' ({sext(v & 0xFFFF, 16)})' if v & 0x8000 else ''))
    if op.mnem in ('jmp', 'jsr', 'braf', 'bsrf') and 'target' in info:
        notes.append(f'-> 0x{info["target"]:08X}')
    if in_slot and op.mnem in SLOT_ILLEGAL:
        notes.append('slot illegal!')
    if in_slot and op.pcrel:
        notes.append('in a slot: base = branch target + 2')
    return text + (' ; ' + ', '.join(notes) if notes else '')


def listing(img, start, end):
    for pc, w, op, vals, in_slot, info in walk(img, start, end):
        hexw = f'{w:08x}' if info.get('data') == 4 else f'{w:04x}'
        print(f'{pc:08x}: {hexw:<8}  {"_" if in_slot else " "}{describe(op, vals, w, in_slot, info)}')


def find_refs(img, lo, hi=None):
    """PC-relative loads (mov.l/mov.w pools), mova and data longs whose value is lo (or in lo..hi)."""
    hi = lo + 1 if hi is None else hi
    loaded = set()
    for pc, w, op, vals, in_slot, info in walk(img, img.base, img.end):
        v = info.get('pool', info.get('addr'))
        if v is not None and lo <= v < hi:
            print(f'{pc:08x}: {describe(op, vals, w, in_slot, info)}')
        if 'pool_addr' in info:
            loaded.add(info['pool_addr'])
    for a in range(img.base + (-img.base) % 4, img.end - 3, 4):
        if a not in loaded and lo <= img.long(a) < hi:
            print(f'{a:08x}: .long 0x{img.long(a):08X} ; data (no pc-relative load seen)')


def find_calls(img, target=None):
    """Calls (and jumps) to target; without target, every resolvable call target with its count."""
    counts = {}
    for pc, w, op, vals, in_slot, info in walk(img, img.base, img.end):
        if op is None or 'target' not in info:
            continue
        t = info['target']
        if target is None and op.mnem in CALLS:
            counts[t] = counts.get(t, 0) + 1
        elif t == target and op.mnem in CALLS | JUMPS:
            print(f'{pc:08x}: {describe(op, vals, w, in_slot, info)}')
    for t in sorted(counts):
        print(f'{t:08x}  {counts[t]:4d} call{"s" if counts[t] > 1 else ""}')


# ---------------------------------------------------------------- selftest

KNOWN = [  # (text as listed, pc, word)
    ('rts', BASE, 0x000B), ('nop', BASE, 0x0009), ('clrmac', BASE, 0x0028),
    ('mov.l @r15+,r14', BASE, 0x6EF6), ('sts.l pr,@-r15', BASE, 0x4F22),
    ('lds.l @r15+,pr', BASE, 0x4F26), ('mov #-1,r0', BASE, 0xE0FF), ('jsr @r3', BASE, 0x430B),
    ('mov.l @(4,r5),r1', BASE, 0x5151), ('mov.l r1,@(8,r2)', BASE, 0x1212),
    ('mov r4,r5', BASE, 0x6543), ('add #4,r15', BASE, 0x7F04), ('cmp/eq #-1,r0', BASE, 0x88FF),
    ('mov.b r0,@(3,r4)', BASE, 0x8043), ('mov.w @(6,r4),r0', BASE, 0x8543),
    ('mov.w @(r0,r4),r1', BASE, 0x014D), ('mov.l r0,@(8,gbr)', BASE, 0xC202),
    ('dt r5', BASE, 0x4510), ('mul.l r2,r3', BASE, 0x0327), ('dmuls.l r4,r5', BASE, 0x354D),
    ('dmulu.l r4,r5', BASE, 0x3545), ('mac.l @r1+,@r2+', BASE, 0x021F),
    ('mac.w @r1+,@r2+', BASE, 0x421F), ('braf r3', BASE, 0x0323), ('bsrf r3', BASE, 0x0303),
    ('and #0xF0,r0', BASE, 0xC9F0), ('tst.b #0x01,@(r0,gbr)', BASE, 0xCC01),
    ('trapa #0x20', BASE, 0xC320), ('stc gbr,r2', BASE, 0x0212), ('ldc.l @r15+,sr', BASE, 0x4F07),
    ('tas.b @r1', BASE, 0x411B), ('xtrct r1,r2', BASE, 0x221D),
    ('bsr 0x06004100', BASE, 0xB07E),          # disp (0x100-4)/2 = 0x7E
    ('bra 0x06004000', BASE + 0x10, 0xAFF6),   # disp -10
    ('bra 0x06004004', BASE - 0x1000 + 2, 0xA7FF),   # largest forward: +2047
    ('bsr 0x06003004', BASE, 0xB800),          # largest backward: -2048
    ('bt 0x06004020', BASE, 0x890E), ('bf 0x06003F80', BASE, 0x8BBE),
    ('bt/s 0x06004004', BASE, 0x8D00), ('bf/s 0x06004002', BASE, 0x8FFF),
    ('mov.l @(0x0600400C),r4', BASE + 2, 0xD402),   # (pc & ~3) + 4 + 2*4
    ('mov.l @(0x06004008),r4', BASE, 0xD401),
    ('mov.w @(0x06004010),r1', BASE + 2, 0x9105),   # pc + 4 + 5*2
    ('mova @(0x06004008),r0', BASE, 0xC701),
]

DEMO = """
hook:   sts.l   pr,@-r15
        mov.l   =0x06031000,r4      ; literal pool entry
        mov.l   print_ptr,r3        ; explicit .long
        jsr     @r3
        mov     #-1,r5              ; delay slot
        bt/s    .done
        add     #1,r4
.done:  lds.l   @r15+,pr
        rts
        nop
        .align  2
print_ptr: .long PRINT
        .pool
table:  .word   hook-table, 0x1234
"""


def selftest():
    ok = True
    for text, pc, word in KNOWN:
        got = encode(*(text.split(' ', 1) + [''])[:2], pc, {})
        back = disassemble(word, pc)
        if got != word or back != text:
            print(f'FAIL {text!r} @ {pc:08x}: assembled {got:04x}, want {word:04x}; '
                  f'disassembled {back!r}')
            ok = False
    print(f'{len(KNOWN)} known encodings checked')
    if encode('mov.l', '@sp+,r14', BASE, {}) != 0x6EF6 or encode('bt.s', '0x06004004', BASE, {}) != 0x8D00:
        print('FAIL aliases (sp, bt.s)')
        ok = False
    # every word: decoded by at most one row, and re-encoded to itself
    illegal, bad, pc = 0, [], BASE + 2
    for w in range(0x10000):
        rows = [op for op in OPS if w & op.mask == op.value]
        if len(rows) > 1:
            bad.append(f'{w:04x} matches {len(rows)} rows')
        op = decode(w)
        if op is None:
            illegal += 1
            continue
        text = disassemble(w, pc)
        mnem, _, ops = text.partition(' ')
        try:
            w2 = encode(mnem, ops, pc, {})
        except AsmError as e:
            w2 = f'error {e}'
        if w2 != w:
            bad.append(f'{w:04x} {text!r} -> {w2}')
    for b in bad[:20]:
        print('FAIL round trip', b)
    ok &= not bad
    print(f'round trip: {0x10000 - illegal} words decode and re-encode, {illegal} illegal words, '
          f'{len(OPS)} table rows, {len(BY_MNEM)} mnemonics')
    # a small program with labels, a literal pool, a slot and data
    code, syms = assemble(DEMO, 0x06010000, {'PRINT': 0x0600A000})
    img = Image(code, 0x06010000)
    rows = list(walk(img, img.base, syms['print_ptr']))
    jsr = next(r for r in rows if r[2] and r[2].mnem == 'jsr')
    pool = next(r for r in rows if 'pool' in r[5])
    slots = [r[0] - img.base for r in rows if r[4]]
    if (jsr[5].get('target') != 0x0600A000 or pool[5]['pool'] != 0x06031000
            or slots != [0x8, 0xC, 0x12] or img.half(syms['table']) != (-syms['table'] + 0x06010000) & 0xFFFF
            or img.long(syms['print_ptr']) != 0x0600A000):
        print('FAIL demo program', code.hex(), syms)
        ok = False
    else:
        print(f'demo program: {len(code)} bytes, jsr resolved to 0x0600A000, slots marked')
    for src, why in (('bra x\nx: bra x\nnop', 'branch in slot'), ('rts', 'missing slot'),
                     ('rts\nmov.l y,r1\n.align 2\ny: .long 0', 'pc-relative in slot'),
                     ('bra x\nx: trapa #1', 'trapa in slot'), ('mov.l =1,r0', 'no .pool'),
                     ('mov #300,r0', 'immediate range'), ('mov.l @(3,r1),r2', 'unaligned disp')):
        try:
            assemble(src, BASE)
            print(f'FAIL accepted ({why}): {src!r}')
            ok = False
        except AsmError:
            pass
    print('selftest', 'OK' if ok else 'FAILED')
    return ok


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='SH-2 (Saturn) disassembler, reference/call search and assembler.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('dis', help='disassemble a raw binary')
    p.add_argument('file')
    p.add_argument('base', nargs='?', default=hex(BASE), help='load address (hex, default 0x06004000)')
    p.add_argument('start', nargs='?', help='hex address to list from (default: base)')
    p.add_argument('end', nargs='?', help='hex end address (default: start + 64 instructions)')
    p = sub.add_parser('refs', help='find pc-relative loads, mova and data words equal to an address')
    p.add_argument('file')
    p.add_argument('base')
    p.add_argument('addr')
    p.add_argument('end', nargs='?', help='hex: match any value in addr..end')
    p = sub.add_parser('calls', help='find calls to an address, or count all call targets')
    p.add_argument('file')
    p.add_argument('base')
    p.add_argument('addr', nargs='?')
    p = sub.add_parser('asm', help='assemble a source file at an address')
    p.add_argument('src')
    p.add_argument('addr')
    p.add_argument('-o', '--out', help='write the bytes here (default: list them)')
    p.add_argument('-D', dest='defs', action='append', default=[], metavar='NAME=VALUE')
    sub.add_parser('test', help='run the selftest')
    args = ap.parse_args()
    if args.cmd == 'test':
        sys.exit(0 if selftest() else 1)
    if args.cmd == 'asm':
        syms = {k: int(v, 0) for k, v in (d.split('=', 1) for d in args.defs)}
        try:
            code, syms = assemble(open(args.src).read(), int(args.addr, 16), syms)
        except AsmError as e:
            sys.exit(f'error: {e}')
        if args.out:
            open(args.out, 'wb').write(code)
        else:
            img = Image(code, int(args.addr, 16))
            listing(img, img.base, img.end)
        sys.exit(0)
    img = Image(args.file, int(args.base, 16))
    if args.cmd == 'dis':
        start = int(args.start, 16) if args.start else img.base
        listing(img, start, int(args.end, 16) if args.end else start + 128)
    elif args.cmd == 'refs':
        find_refs(img, int(args.addr, 16), int(args.end, 16) if args.end else None)
    else:
        find_calls(img, int(args.addr, 16) if args.addr else None)

"""

Copyright (c) 2017 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

from __future__ import print_function

import math
import struct
import sys
import traceback
import os

from binaryninja.architecture import Architecture
from binaryninja.lowlevelil import LowLevelILLabel, LLIL_TEMP
from binaryninja.function import RegisterInfo, InstructionInfo, InstructionTextToken
from binaryninja.binaryview import BinaryView
from binaryninja.plugin import PluginCommand
from binaryninja.interaction import AddressField, ChoiceField, get_form_input
from binaryninja.types import Symbol
from binaryninja.log import log_error
from binaryninja.enums import (Endianness, BranchType, InstructionTextTokenType,
        LowLevelILOperation, LowLevelILFlagCondition, FlagRole, SegmentFlag,
        ImplicitRegisterExtend, SymbolType)
from binaryninja import BinaryViewType

# Shift syles
SHIFT_SYLE_ARITHMETIC = 0,
SHIFT_SYLE_LOGICAL = 1,
SHIFT_SYLE_ROTATE_WITH_EXTEND = 2,
SHIFT_SYLE_ROTATE = 3,

ShiftStyle = [
    'as',  # SHIFT_SYLE_ARITHMETIC
    'ls',  # SHIFT_SYLE_LOGICAL
    'rox', # SHIFT_SYLE_ROTATE_WITH_EXTEND
    'ro'   # SHIFT_SYLE_ROTATE
]

BITFIELD_STYLE_TST = 0,
BITFIELD_STYLE_EXTU = 1,
BITFIELD_STYLE_CHG = 2,
BITFIELD_STYLE_EXTS = 3,
BITFIELD_STYLE_CLR = 4,
BITFIELD_STYLE_FFO = 5,
BITFIELD_STYLE_SET = 6,
BITFIELD_STYLE_INS = 7,

BitfieldStyle = [
    "tst", # BITFIELD_STYLE_TST
    "extu", # BITFIELD_STYLE_EXTU
    "chg", # BITFIELD_STYLE_CHG
    "exts", # BITFIELD_STYLE_EXTS
    "clr", # BITFIELD_STYLE_CLR
    "ffo", # BITFIELD_STYLE_FFO
    "set", # BITFIELD_STYLE_SET
    "ins", # BITFIELD_STYLE_INS
]


# Condition codes
CONDITION_TRUE = 0
CONDITION_FALSE = 1
CONDITION_HIGH = 2
CONDITION_LESS_OR_SAME = 3
CONDITION_CARRY_CLEAR = 4
CONDITION_CARRY_SET = 5
CONDITION_NOT_EQUAL = 6
CONDITION_EQUAL = 7
CONDITION_OVERFLOW_CLEAR = 8
CONDITION_OVERFLOW_SET = 9
CONDITION_PLUS = 10
CONDITION_MINUS = 11
CONDITION_GREATER_OR_EQUAL = 12
CONDITION_LESS_THAN = 13
CONDITION_GREATER_THAN = 14
CONDITION_LESS_OR_EQUAL = 15

Condition = [
    't',  # CONDITION_TRUE
    'f',  # CONDITION_FALSE
    'hi', # CONDITION_HIGH
    'ls', # CONDITION_LESS_OR_SAME
    'cc', # CONDITION_CARRY_CLEAR
    'cs', # CONDITION_CARRY_SET
    'ne', # CONDITION_NOT_EQUAL
    'eq', # CONDITION_EQUAL
    'vc', # CONDITION_OVERFLOW_CLEAR
    'vs', # CONDITION_OVERFLOW_SET
    'pl', # CONDITION_PLUS
    'mi', # CONDITION_MINUS
    'ge', # CONDITION_GREATER_OR_EQUAL
    'lt', # CONDITION_LESS_THAN
    'gt', # CONDITION_GREATER_THAN
    'le'  # CONDITION_LESS_OR_EQUAL
]


# Used by the 'FBcc', 'FScc', and 'FTRAPcc' instructions
FP_Condition = [
    'f',     # 000000
    'eq',    # 000001
    'ogt',   # 000010
    'oge',   # 000011
    'olt',   # 000100
    'ole',   # 000101
    'ogl',   # 000110
    'or',    # 000111
    'un',    # 001000
    'ueq',   # 001001
    'ugt',   # 001010
    'uge',   # 001011
    'ult',   # 001100
    'ule',   # 001101
    'ne',    # 001110
    't',     # 001111
    'sf',    # 010000
    'seq',   # 010001
    'gt',    # 010010
    'ge',    # 010011
    'lt',    # 010100
    'le',    # 010101
    'gl',    # 010110
    'gle',   # 010111
    'ngle',  # 011000
    'ngl',   # 011001
    'nle',   # 011010
    'nlt',   # 011011
    'nge',   # 011100
    'ngt',   # 011101
    'sne',   # 011110
    'st'     # 011111
]

FBcc_Instructions = tuple('fb'+x for x in FP_Condition)

# Registers
REGISTER_D0 = 0
REGISTER_D1 = 1
REGISTER_D2 = 2
REGISTER_D3 = 3
REGISTER_D4 = 4
REGISTER_D5 = 5
REGISTER_D6 = 6
REGISTER_D7 = 7
REGISTER_A0 = 8
REGISTER_A1 = 9
REGISTER_A2 = 10
REGISTER_A3 = 11
REGISTER_A4 = 12
REGISTER_A5 = 13
REGISTER_A6 = 14
REGISTER_A7 = 15

Registers = [
    'd0', # REGISTER_D0
    'd1', # REGISTER_D1
    'd2', # REGISTER_D2
    'd3', # REGISTER_D3
    'd4', # REGISTER_D4
    'd5', # REGISTER_D5
    'd6', # REGISTER_D6
    'd7', # REGISTER_D7
    'a0', # REGISTER_A0
    'a1', # REGISTER_A1
    'a2', # REGISTER_A2
    'a3', # REGISTER_A3
    'a4', # REGISTER_A4
    'a5', # REGISTER_A5
    'a6', # REGISTER_A6
    'sp'  # REGISTER_A7
]

# Integer data formats
DATA_BYTE = 0
DATA_WORD = 1
DATA_LONG = 2

ActualFormatSize = [1 << DATA_BYTE, 1 << DATA_WORD, 1 << DATA_LONG]  # actual size in bytes

SizeSuffix = [
    '.b', # DATA_BYTE
    '.w', # DATA_WORD
    '.l', # DATA_LONG
]

# FP registers
FP_Registers = [
    'fp0',
    'fp1',
    'fp2',
    'fp3',
    'fp4',
    'fp5',
    'fp6',
    'fp7',
]

# NOTE: Defined by hardware don't change
FP_SCREGISTER_FPIAR = 1
FP_SCREGISTER_FPSR = 2
FP_SCREGISTER_FPCR = 4

FP_SCRegisters = {
    FP_SCREGISTER_FPIAR: 'fpiar',
    FP_SCREGISTER_FPSR: 'fpsr',
    FP_SCREGISTER_FPCR: 'fpcr'
}

# FP data formats
FP_DATA_LONG = 0
FP_DATA_SINGLE_PRECISION = 1
FP_DATA_EXTENDED_PRECISION = 2
FP_DATA_PACKED = 3
FP_DATA_WORD = 4
FP_DATA_DOUBLE_PRECISION = 5
FP_DATA_BYTE = 6
FP_DATA_PACKED_DYNAMIC_K = 7
FP_DATA_REGISTER = 8  # not specified in H/W; for plugin convenience only
FP_DATA_SCREGISTER = 9  # not specified in H/W; for plugin convenience only

FP_ActualFormatSize = [4, 4, 12, 12, 2, 8, 1, 12, 10, 4]  # actual size in bytes

FP_SizeSuffix = [
    '.l',  # FP_DATA_LONG
    '.s',  # FP_DATA_SINGLE_PRECISION
    '.x',  # FP_DATA_EXTENDED_PRECISION
    '.p',  # FP_DATA_PACKED
    '.w',  # FP_DATA_WORD
    '.d',  # FP_DATA_DOUBLE_PRECISION
    '.b',  # FP_DATA_BYTE
    '.p',  # FP_DATA_PACKED_DYNAMIC_K
    '.x',  # FP_DATA_REGISTER
    '.l'   # FP_DATA_SCREGISTER
]


# Converts a m64k IEEE 754 64-bit extended precision formatted bytes object to a float
# NOTE: This function does NOT attempt to preserve the precision of the extended formatted float
#       but only converts it into a standard float for display purposes, etc
def m64k_extended_bytes2float(raw_bytes):
    exp_bias = 0x3fff
    int_bit = 63
    zero_pad_start_bit = 64
    exp_start_bit = 80
    sign_bit = 95

    exp_mask = ((1 << (sign_bit-exp_start_bit))-1) << exp_start_bit
    mantissa_mask = (1 << zero_pad_start_bit)-1

    raw_int = int.from_bytes(raw_bytes, 'big')

    mantissa = raw_int & mantissa_mask
    exp = ((raw_int & exp_mask) >> exp_start_bit)
    sign = raw_int >> sign_bit

    result = None
    if exp == 0x7fff:
        result = float('inf') if mantissa == 0 else float('nan')
    else:
        result = mantissa * 2**(-int_bit + exp - exp_bias)

        if result and isinstance(result, int):
            result_10_exp = math.log10(result)
            # Perform a lazy check to see if we have exceeded the float size
            # NOTE: Python automatically bounds checks against the minimal float size
            if result_10_exp >= sys.float_info.max_10_exp:
                result = float('inf')

    # TODO: Python currently ignores setting 'nan' negative
    return float((-1)**sign * result)


# Operands
class OpRegisterDirect:
    def __init__(self, size, reg):
        self.size = size
        self.reg = reg

    def __repr__(self):
        return "OpRegisterDirect(%d, %s)" % (self.size, self.reg)

    def format(self, addr):
        # a0, d0
        return [
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg)
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        if self.reg == 'ccr':
            c = il.flag_bit(1, 'c', 0)
            v = il.flag_bit(1, 'v', 1)
            z = il.flag_bit(1, 'z', 2)
            n = il.flag_bit(1, 'n', 3)
            x = il.flag_bit(1, 'x', 4)
            return il.or_expr(1, il.or_expr(1, il.or_expr(1, il.or_expr(1, c, v), z), n), x)
        else:
            return il.reg(self.size, self.reg)

    def get_dest_il(self, il, value, flags=0):
        if self.reg == 'ccr':
            return il.unimplemented()

        # return il.set_reg(self.size, self.reg, value)
        # if self.size == ActualFormatSize[DATA_BYTE]:
        #     if self.reg[0] == 'a' or self.reg == 'sp':
        #         return None
        #     else:
        #         return il.set_reg(1, self.reg+'.b', value, flags)
        # elif self.size == ActualFormatSize[DATA_WORD]:
        #     return il.set_reg(2, self.reg+'.w', value, flags)
        # else:
        #     return il.set_reg(4, self.reg, value, flags)
        if self.size == ActualFormatSize[DATA_BYTE]:
            if self.reg[0] == 'a' or self.reg == 'sp':
                return il.unimplemented()
            else:
                return il.set_reg(4, self.reg, il.or_expr(4, il.and_expr(4, il.const(4, 0xffffff00), il.reg(4, self.reg)), il.and_expr(4, il.const(4, 0xff), value)), flags)
        elif self.size == ActualFormatSize[DATA_WORD]:
            if self.reg[0] == 'a' or self.reg == 'sp':
                return il.set_reg(4, self.reg, il.sign_extend(4, value), flags)
            else:
                return il.set_reg(4, self.reg, il.or_expr(4, il.and_expr(4, il.const(4, 0xffff0000), il.reg(4, self.reg)), il.and_expr(4, il.const(4, 0xffff), value)), flags)
        else:
            if value:
                return il.set_reg(4, self.reg, value, flags)
            else:
                return il.unimplemented()


class FP_OpRegisterDirect(OpRegisterDirect):
    # TODO: Add support for fpcr/fpsr flags

    def __init__(self, size, reg):
        self.size = size
        self.reg = reg

    def __repr__(self):
        return "FP_OpRegisterDirect(%d, %s)" % (self.size, self.reg)

    def format(self, addr):
        # fp0
        return [
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg)
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return il.reg(self.size, self.reg)

    def get_dest_il(self, il, value, flags=0):
        if self.size == FP_ActualFormatSize[FP_DATA_REGISTER]:
            # FP data registers are sign extended
            return il.set_reg(self.size, self.reg, il.sign_extend(self.size, value), flags)
        else:
            # FP system control registers
            return il.set_reg(self.size, self.reg, value, flags)


class OpRegisterDirectPair:
    def __init__(self, size, reg1, reg2):
        self.size = size
        self.reg1 = reg1
        self.reg2 = reg2

    def __repr__(self):
        return "OpRegisterDirectPair(%d, %s, %s)" % (self.size, self.reg1, self.reg2)

    def format(self, addr):
        # d0:d1
        return [
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg1),
            InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ":"),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg2)
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return (il.reg(self.size, self.reg1), il.reg(self.size, self.reg2))

    def get_dest_il(self, il, values, flags=0):
        return (il.set_reg(self.size, self.reg1, values[0], flags), il.set_reg(self.size, self.reg2, values[1], flags))


class OpRegisterMovemList:
    def __init__(self, size, regs):
        self.size = size
        self.regs = regs

    def __repr__(self):
        return "OpRegisterMovemList(%d, %s)" % (self.size, repr(self.regs))

    def format(self, addr):
        # d0-d7/a0/a2/a4-a7
        if len(self.regs) == 0:
            return []
        tokens = [InstructionTextToken(InstructionTextTokenType.RegisterToken, self.regs[0])]
        last = self.regs[0]
        first = None
        for reg in self.regs[1:]:
            if Registers[Registers.index(last)+1] == reg and reg != 'a0':
                if first is None:
                    first = last
                last = reg
            else:
                if first is not None:
                    tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "-"))
                    tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, last))
                tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "/"))
                tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, reg))
                first = None
                last = reg
        if first is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "-"))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, last))
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return [il.reg(self.size, reg) for reg in self.regs]

    def get_dest_il(self, il, values, flags=0):
        return [il.set_reg(self.size, reg, val, flags) for reg, val in zip(self.regs, values)]


class FP_OpRegisterMovemList:
    def __init__(self, size, regs):
        self.size = size
        self.regs = regs

    def __repr__(self):
        return "FP_OpRegisterMovemList(%d, %s)" % (self.size, repr(self.regs))

    def format(self, addr):
        # fp0-fp7
        if len(self.regs) == 0:
            return []

        # The move order varies per the m68k manual, for now use: fp0-fp7
        # TODO: Observe the manual defined move order based on the addressing mode
        tokens = []
        last_reg = None
        seq = False
        for i in range(len(FP_Registers)):
            if FP_Registers[i] in self.regs:
                if last_reg is None:
                    last_reg = i
                    tokens.append(InstructionTextToken(
                        InstructionTextTokenType.RegisterToken, FP_Registers[i]))
                elif last_reg == i-1:
                    seq = True
                    last_reg = i
                else:
                    last_reg = i
                    tokens.append(InstructionTextToken(
                        InstructionTextTokenType.OperandSeparatorToken, "/"))
                    tokens.append(InstructionTextToken(
                        InstructionTextTokenType.RegisterToken, FP_Registers[i]))

            if FP_Registers[i] not in self.regs or i == len(FP_Registers)-1:
                if seq:
                    seq = False
                    tokens.append(InstructionTextToken(
                        InstructionTextTokenType.OperandSeparatorToken, "-"))
                    tokens.append(InstructionTextToken(
                        InstructionTextTokenType.RegisterToken, FP_Registers[last_reg]))
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return [il.reg(self.size, reg) for reg in self.regs]

    def get_dest_il(self, il, values, flags=0):
        return [il.set_reg(self.size, reg, val, flags) for reg, val in zip(self.regs, values)]


class FP_OpSCRegisterMovemList:
    def __init__(self, size, regs):
        self.size = size
        self.regs = regs

    def __repr__(self):
        return "FP_OpSCRegisterMovemList(%d, %s)" % (self.size, repr(self.regs))

    def format(self, addr):
        # fpcr/fpsr/fpiar
        if len(self.regs) == 0:
            return []

        # The move order is fixed per the m68k manual as: fpcr, fpsr, then fpiar
        tokens = []
        for i in sorted(FP_SCRegisters.keys(), reverse=True):
            if FP_SCRegisters[i] in self.regs:
                tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken,
                                                   FP_SCRegisters[i]))
                tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken,
                                                   "/"))
        tokens.pop()
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return [il.reg(self.size, reg) for reg in self.regs]

    def get_dest_il(self, il, values, flags=0):
        return [il.set_reg(self.size, reg, val, flags) for reg, val in zip(self.regs, values)]


class OpRegisterIndirect:
    def __init__(self, size, reg):
        self.size = size
        self.reg = reg

    def __repr__(self):
        return "OpRegisterIndirect(%d, %s)" % (self.size, self.reg)

    def format(self, addr):
        # (a0)
        return [
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")")
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.reg(4, self.reg)

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        #return il.store(self.size, self.get_address_il(il), value, flags)
        return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpRegisterIndirectPair:
    def __init__(self, size, reg1, reg2):
        self.size = size
        self.reg1 = reg1
        self.reg2 = reg2

    def __repr__(self):
        return "OpRegisterIndirectPair(%d, %s, %s)" % (self.size, self.reg1, self.reg2)

    def format(self, addr):
        # d0:d1
        return [
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg1),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"),
            InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ":"),
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg2),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")")
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return (il.reg(4, self.reg1), il.reg(4, self.reg2))

    def get_source_il(self, il):
        return (il.load(self.size, il.reg(4, self.reg1)), il.load(self.size, il.reg(4, self.reg2)))

    def get_dest_il(self, il, values, flags=0):
        #return (il.store(self.size, il.reg(4, self.reg1), values[0], flags), il.store(self.size, il.reg(4, self.reg2), values[1], flags))
        return (il.store(self.size, il.reg(4, self.reg1), values[0]), il.store(self.size, il.reg(4, self.reg2), values[1]))


class OpRegisterIndirectPostincrement:
    def __init__(self, size, reg):
        self.size = size
        self.reg = reg

    def __repr__(self):
        return "OpRegisterIndirectPostincrement(%d, %s)" % (self.size, self.reg)

    def format(self, addr):
        # (a0)+
        return [
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"),
            InstructionTextToken(InstructionTextTokenType.TextToken, "+")
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return il.set_reg(4,
            self.reg,
            il.add(4,
                il.reg(4, self.reg),
                il.const(4, self.size)
            )
        )

    def get_address_il(self, il):
        return il.reg(4, self.reg)

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        #return il.store(self.size, self.get_address_il(il), value, flags)
        return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpRegisterIndirectPredecrement:
    def __init__(self, size, reg):
        self.size = size
        self.reg = reg

    def __repr__(self):
        return "OpRegisterIndirectPredecrement(%d, %s)" % (self.size, self.reg)

    def format(self, addr):
        # -(a0)
        return [
            InstructionTextToken(InstructionTextTokenType.TextToken, "-"),
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")")
        ]

    def get_pre_il(self, il):
        return il.set_reg(4,
            self.reg,
            il.sub(4,
                il.reg(4, self.reg),
                il.const(4, self.size)
            )
        )

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.reg(4, self.reg)

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        #return il.store(self.size, self.get_address_il(il), value, flags)
        return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpRegisterIndirectDisplacement:
    def __init__(self, size, reg, offset):
        self.size = size
        self.reg = reg
        self.offset = offset

    def __repr__(self):
        return "OpRegisterIndirectDisplacement(%d, %s, 0x%x)" % (self.size, self.reg, self.offset)

    def format(self, addr):
        if self.reg == 'pc':
            return [
                InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
                InstructionTextToken(InstructionTextTokenType.PossibleAddressToken, "${:08x}".format(addr+2+self.offset), addr+2+self.offset, 4),
                InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")")
            ]
        else:
            # $1234(a0)
            return [
                InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:04x}".format(self.offset), self.offset, 2),
                InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
                InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg),
                InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")")
            ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        if self.reg == 'pc':
            return il.const_pointer(4, il.current_address+2+self.offset)
        else:
            return il.add(4,
                il.reg(4, self.reg),
                il.const(4, self.offset)
            )

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        if self.reg == 'pc':
            return il.unimplemented()
        else:
            #return il.store(self.size, self.get_address_il(il), value, flags)
            return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpRegisterIndirectIndex:
    def __init__(self, size, reg, offset, ireg, ireg_long, scale):
        self.size = size
        self.reg = reg
        self.offset = offset
        self.ireg = ireg
        self.ireg_long = ireg_long
        self.scale = scale

    def __repr__(self):
        return "OpRegisterIndirectIndex(%d, %s, 0x%x, %s, %d, %d)" % (self.size, self.reg, self.offset, self.ireg, self.ireg_long, self.scale)

    def format(self, addr):
        # ($1234,a0,a1.l*4)
        tokens = []
        tokens.append(InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("))
        tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:x}".format(self.offset), self.offset))
        if self.reg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg))
        if self.ireg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.ireg))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "."))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "l" if self.ireg_long else 'w'))
            if self.scale != 1:
                tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "*"))
                tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "{}".format(self.scale), self.scale))
        tokens.append(InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"))
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        if self.reg is None:
            reg_off_il = il.const(4, self.offset)
        else:
            reg_off_il = il.add(4,
                il.const_pointer(4, il.current_address+2) if self.reg == 'pc' else il.reg(4, self.reg),
                il.const(4, self.offset)
            )

        if self.ireg is None:
            return reg_off_il
        else:
            return il.add(4,
                reg_off_il,
                il.mult(4,
                    il.reg(4 if self.ireg_long else 2, self.ireg),
                    il.const(1, self.scale)
                )
            )

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        if self.reg == 'pc':
            return il.unimplemented()
        else:
            #return il.store(self.size, self.get_address_il(il), value, flags)
            return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpMemoryIndirectPostindex:
    def __init__(self, size, reg, offset, ireg, ireg_long, scale, outer_displacement):
        self.size = size
        self.reg = reg
        self.offset = offset
        self.ireg = ireg
        self.ireg_long = ireg_long
        self.scale = scale
        self.outer_displacement = outer_displacement

    def __repr__(self):
        return "OpMemoryIndirectPostindex(%d, %s, 0x%x, %s, %d, %d, 0x%x)" % (self.size, self.reg, self.offset, self.ireg, self.ireg_long, self.scale, self.outer_displacement)

    def format(self, addr):
        # ([$1234,a0],a1.l*4,$1234)
        tokens = []
        tokens.append(InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("))
        tokens.append(InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "["))
        tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:x}".format(self.offset), self.offset))
        if self.reg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg))
        tokens.append(InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, "]"))
        if self.ireg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.ireg))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "."))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "l" if self.ireg_long else 'w'))
            if self.scale != 1:
                tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "*"))
                tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "{}".format(self.scale), self.scale))
        if self.outer_displacement != 0:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:x}".format(self.outer_displacement), self.outer_displacement))
        tokens.append(InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"))
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        if self.reg is None:
            reg_off_il = il.const(4, self.offset)
        else:
            reg_off_il = il.add(4,
                il.const_pointer(4, il.current_address+2) if self.reg == 'pc' else il.reg(4, self.reg),
                il.const(4, self.offset)
            )

        if self.ireg is None:
            ireg_il = il.const(4, 0)
        else:
            ireg_il = il.mult(4,
                il.reg(4 if self.ireg_long else 2, self.ireg),
                il.const(1, self.scale)
            )

        return il.add(4,
            il.load(4, reg_off_il),
            il.add(4,
                ireg_il,
                il.const(4, self.outer_displacement)
            )
        )

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        if self.reg == 'pc':
            return il.unimplemented()
        else:
            #return il.store(self.size, self.get_address_il(il), value, flags)
            return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpMemoryIndirectPreindex:
    def __init__(self, size, reg, offset, ireg, ireg_long, scale, outer_displacement):
        self.size = size
        self.reg = reg
        self.offset = offset
        self.ireg = ireg
        self.ireg_long = ireg_long
        self.scale = scale
        self.outer_displacement = outer_displacement

    def __repr__(self):
        return "OpMemoryIndirectPreindex(%d, %s, 0x%x, %s, %d, %d, 0x%x)" % (self.size, self.reg, self.offset, self.ireg, self.ireg_long, self.scale, self.outer_displacement)

    def format(self, addr):
        # ([$1234,a0,a1.l*4],$1234)
        tokens = []
        tokens.append(InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("))
        tokens.append(InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "["))
        tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:x}".format(self.offset), self.offset))
        if self.reg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.reg))
        if self.ireg is not None:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.RegisterToken, self.ireg))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "."))
            tokens.append(InstructionTextToken(InstructionTextTokenType.TextToken, "l" if self.ireg_long else 'w'))
            if self.scale != 1:
                tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, "*"))
                tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "{}".format(self.scale), self.scale))
        tokens.append(InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, "]"))
        if self.outer_displacement != 0:
            tokens.append(InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ","))
            tokens.append(InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:x}".format(self.outer_displacement), self.outer_displacement))
        tokens.append(InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"))
        return tokens

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        if self.reg is None:
            reg_off_il = il.const(4, self.offset)
        else:
            reg_off_il = il.add(4,
                il.const_pointer(4, il.current_address+2) if self.reg == 'pc' else il.reg(4, self.reg),
                il.const(4, self.offset)
            )

        if self.ireg is None:
            ireg_il = il.const(4, 0)
        else:
            ireg_il = il.mult(4,
                il.reg(4 if self.ireg_long else 2, self.ireg),
                il.const(1, self.scale)
            )

        return il.add(4,
            il.load(4,
                il.add(4,
                    reg_off_il,
                    ireg_il
                )
            ),
            il.const(4, self.outer_displacement)
        )

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        if self.reg == 'pc':
            return il.unimplemented()
        else:
            #return il.store(self.size, self.get_address_il(il), value, flags)
            return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpAbsolute:
    def __init__(self, size, address, address_size, address_width):
        self.size = size
        self.address = address
        self.address_size = address_size
        self.address_width = address_width

    def __repr__(self):
        return "OpAbsolute(%d, 0x%x, %d, %d)" % (self.size, self.address, self.address_size, self.address_width)

    def format(self, addr):
        # ($1234).w
        return [
            InstructionTextToken(InstructionTextTokenType.BeginMemoryOperandToken, "("),
            InstructionTextToken(InstructionTextTokenType.PossibleAddressToken, "${:0{}x}".format(self.address, 1 << self.address_size), self.address, 1 << self.address_size),
            InstructionTextToken(InstructionTextTokenType.EndMemoryOperandToken, ")"+SizeSuffix[self.address_size])
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.sign_extend(self.address_width,
            il.const(1 << self.address_size, self.address)
        )

    def get_source_il(self, il):
        return il.load(self.size, self.get_address_il(il))

    def get_dest_il(self, il, value, flags=0):
        #return il.store(self.size, self.get_address_il(il), value, flags)
        return il.expr(LowLevelILOperation.LLIL_STORE, self.get_address_il(il).index, value.index, size=self.size, flags=flags)


class OpImmediate:
    def __init__(self, size, value):
        self.size = size
        self.value = value

    def __repr__(self):
        return "OpImmediate(%d, 0x%x)" % (self.size, self.value)

    def format(self, addr):
        # #$1234
        return [
            InstructionTextToken(InstructionTextTokenType.TextToken, "#"),
            #InstructionTextToken(InstructionTextTokenType.PossibleAddressToken, "${:0{}x}".format(self.value, self.size), self.value, self.size)
            InstructionTextToken(InstructionTextTokenType.IntegerToken, "${:0{}x}".format(self.value, self.size), self.value, self.size)
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return il.const(self.size, self.value)

    def get_dest_il(self, il, value, flags=0):
        return il.unimplemented()


class FP_OpImmediate:
    # The 'size' argument must be one of 'FP data formats'
    # The 'data' argument must be in the appropriate form for the size as shown below:
    #
    #   size:                        data format:
    #   FP_DATA_SINGLE_PRECISION     IEEE 754
    #   FP_DATA_DOUBLE_PRECISION     IEEE 754
    #   FP_DATA_EXTENDED_PRECISION   IEEE 754 m64k modified 64-bit precision
    #
    def __init__(self, size, data):
        self.size = size

        # TODO: Add proper support for packed
        format_specifier = None
        if self.size == FP_ActualFormatSize[FP_DATA_EXTENDED_PRECISION]:
            value_unpacked = m64k_extended_bytes2float(data)
        else:
            if self.size == FP_ActualFormatSize[FP_DATA_SINGLE_PRECISION]:
                format_specifier = '>f'
            elif self.size == FP_ActualFormatSize[FP_DATA_DOUBLE_PRECISION]:
                format_specifier = '>d'
            else:
                format_specifier = '>Q'

            value_unpacked = struct.unpack_from(format_specifier, data, 0)[0]

        if format_specifier == '>Q':
            self.value = value_unpacked
            self.text = "${:x}".format(value_unpacked)
        else:
            self.value = int.from_bytes(data, 'big')
            self.text = "${:.4e}".format(value_unpacked)

    def __repr__(self):
        return "FP_OpImmediate(%d, %x)" % (self.size, self.value)

    def format(self, addr):
        # #$2.5e+02
        return [
            # Attempting to use a 'InstructionTextTokenType.FloatingPointToken' here currently
            # crashes Binary Ninja
            InstructionTextToken(InstructionTextTokenType.TextToken, "#"),
            InstructionTextToken(InstructionTextTokenType.IntegerToken,
                                 self.text,
                                 self.value,
                                 self.size)
        ]

    def get_pre_il(self, il):
        return None

    def get_post_il(self, il):
        return None

    def get_address_il(self, il):
        return il.unimplemented()

    def get_source_il(self, il):
        return il.const(self.size, self.value)

    def get_dest_il(self, il, value, flags=0):
        return il.unimplemented()


# condition mapping to LLIL flag conditions
ConditionMapping = {
    'hi': LowLevelILFlagCondition.LLFC_UGT,
    'ls': LowLevelILFlagCondition.LLFC_ULE,
    'cc': LowLevelILFlagCondition.LLFC_UGE,
    'cs': LowLevelILFlagCondition.LLFC_ULT,
    'ne': LowLevelILFlagCondition.LLFC_NE,
    'eq': LowLevelILFlagCondition.LLFC_E,
    'vc': LowLevelILFlagCondition.LLFC_NO,
    'vs': LowLevelILFlagCondition.LLFC_O,
    'pl': LowLevelILFlagCondition.LLFC_POS,
    'mi': LowLevelILFlagCondition.LLFC_NEG,
    'ge': LowLevelILFlagCondition.LLFC_SGE,
    'lt': LowLevelILFlagCondition.LLFC_SLT,
    'gt': LowLevelILFlagCondition.LLFC_SGT,
    'le': LowLevelILFlagCondition.LLFC_SLE,
}

class M68000(Architecture):
    name = "M68000"
    address_size = 3
    default_int_size = 4
    max_instr_length = 22
    endianness = Endianness.BigEndian
    regs = {
        'd0':    RegisterInfo('d0', 4),
        'd1':    RegisterInfo('d1', 4),
        'd2':    RegisterInfo('d2', 4),
        'd3':    RegisterInfo('d3', 4),
        'd4':    RegisterInfo('d4', 4),
        'd5':    RegisterInfo('d5', 4),
        'd6':    RegisterInfo('d6', 4),
        'd7':    RegisterInfo('d7', 4),
        'a0':    RegisterInfo('a0', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a1':    RegisterInfo('a1', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a2':    RegisterInfo('a2', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a3':    RegisterInfo('a3', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a4':    RegisterInfo('a4', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a5':    RegisterInfo('a5', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'a6':    RegisterInfo('a6', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),
        'sp':    RegisterInfo('sp', 4, extend=ImplicitRegisterExtend.SignExtendToFullWidth),

        'sr':    RegisterInfo('sr', 2),
        'ccr':   RegisterInfo('sr', 1),

        # control registers
        # MC68010/MC68020/MC68030/MC68040/CPU32
        'sfc':   RegisterInfo('sfc', 4),
        'dfc':   RegisterInfo('dfc', 4),
        'usp':   RegisterInfo('usp', 4),
        'vbr':   RegisterInfo('vbr', 4),
        # MC68020/MC68030/MC68040
        'cacr':  RegisterInfo('cacr', 4),
        'caar':  RegisterInfo('caar', 4),
        'msp':   RegisterInfo('msp', 4),
        'isp':   RegisterInfo('isp', 4),
        # MC68040
        'fp0':   RegisterInfo('fp0', 10),
        'fp1':   RegisterInfo('fp1', 10),
        'fp2':   RegisterInfo('fp2', 10),
        'fp3':   RegisterInfo('fp3', 10),
        'fp4':   RegisterInfo('fp4', 10),
        'fp5':   RegisterInfo('fp5', 10),
        'fp6':   RegisterInfo('fp6', 10),
        'fp7':   RegisterInfo('fp7', 10),
        'fpcr':  RegisterInfo('fpcr', 2),
        'fpsr':  RegisterInfo('fpsr', 4),
        'fpiar': RegisterInfo('fpiar', 4),
        # MC68040/MC68LC040
        'tc':    RegisterInfo('tc', 4),
        'itt0':  RegisterInfo('itt0', 4),
        'itt1':  RegisterInfo('itt1', 4),
        'dtt0':  RegisterInfo('dtt0', 4),
        'dtt1':  RegisterInfo('dtt1', 4),
        'mmusr': RegisterInfo('mmusr', 4),
        'urp':   RegisterInfo('urp', 4),
        'srp':   RegisterInfo('srp', 4),
        # MC68EC040
        'iacr0': RegisterInfo('iacr0', 4),
        'iacr1': RegisterInfo('iacr1', 4),
        'dacr0': RegisterInfo('dacr0', 4),
        'dacr1': RegisterInfo('dacr1', 4),
    }
    stack_pointer = 'sp'
    flags = ['x', 'n', 'z', 'v', 'c']
    flag_write_types = ['*', 'nzvc']
    flags_written_by_flag_write_type = {
        '*': ['x', 'n', 'z', 'v', 'c'],
        'nzvc': ['n', 'z', 'v', 'c'],
    }
    flag_roles = {
        'x': FlagRole.SpecialFlagRole,
        'n': FlagRole.NegativeSignFlagRole,
        'z': FlagRole.ZeroFlagRole,
        'v': FlagRole.OverflowFlagRole,
        'c': FlagRole.CarryFlagRole,
    }
    flags_required_for_flag_condition = {
        LowLevelILFlagCondition.LLFC_UGT: ['c', 'z'], # hi
        LowLevelILFlagCondition.LLFC_ULE: ['c', 'z'], # ls
        LowLevelILFlagCondition.LLFC_UGE: ['c'], # cs
        LowLevelILFlagCondition.LLFC_ULT: ['c'], # cs
        LowLevelILFlagCondition.LLFC_NE:  ['z'], # ne
        LowLevelILFlagCondition.LLFC_E:   ['z'], # eq
        LowLevelILFlagCondition.LLFC_NO:  ['v'], # vc
        LowLevelILFlagCondition.LLFC_O:   ['v'], # vs
        LowLevelILFlagCondition.LLFC_POS: ['n'], # pl
        LowLevelILFlagCondition.LLFC_NEG: ['n'], # mi
        LowLevelILFlagCondition.LLFC_SGE: ['n', 'v'], # ge
        LowLevelILFlagCondition.LLFC_SLT: ['n', 'v'], # lt
        LowLevelILFlagCondition.LLFC_SGT: ['n', 'v', 'z'], # gt
        LowLevelILFlagCondition.LLFC_SLE: ['n', 'v', 'z'], # le
    }
    control_registers = {
    }
    memory_indirect = False
    movem_store_decremented = False

    def fp_decode_effective_address(self, mode, register, data, size=None, fp_format=None):

        mode &= 0x07
        register &= 0x07

        # TODO: As a wrapper, a lot of the following checks can eventually go away. But for now, it
        #       provides some bounds checking and insight into what FP effective addresses have
        #       been tested.

        if mode == 0:
            # data register direct
            if size <= FP_ActualFormatSize[FP_DATA_LONG]:
                return self.decode_effective_address(mode, register, data, size)
        if mode == 1:
            # address register direct
            if size <= FP_ActualFormatSize[FP_DATA_LONG]:
                return self.decode_effective_address(mode, register, data, size)
        elif mode == 2:
            # address register indirect
            if size == FP_ActualFormatSize[FP_DATA_LONG] or \
               size == FP_ActualFormatSize[FP_DATA_SINGLE_PRECISION]:
                return self.decode_effective_address(mode, register, data, size)
        elif mode == 3:
            # address register indirect with postincrement
            return self.decode_effective_address(mode, register, data, size)
        elif mode == 4:
            # address register indirect with predecrement
            return self.decode_effective_address(mode, register, data, size)
        elif mode == 5:
            # address register indirect with displacement
            return self.decode_effective_address(mode, register, data, size)
        elif mode == 6:
            # extended addressing mode
            return self.decode_effective_address(mode, register, data, size)
        elif mode == 7:
            if register == 1:
                # absolute long addressing
                return self.decode_effective_address(mode, register, data, size)
            if register == 4:
                # immediates
                if fp_format == FP_DATA_SINGLE_PRECISION or \
                   fp_format == FP_DATA_DOUBLE_PRECISION or \
                   fp_format == FP_DATA_EXTENDED_PRECISION:
                    return (FP_OpImmediate(size, data[:size]), size)
                elif size is not None and size <= ActualFormatSize[DATA_LONG]:
                    return self.decode_effective_address(mode, register, data, size)

        # log_error('Unsupported FP effective address')

        return (None, None)

    def decode_effective_address(self, mode, register, data, size=None):
        mode &= 0x07
        register &= 0x07

        reg = None

        if mode == 0:
            # data register direct
            return (OpRegisterDirect(size, Registers[register]), 0)
        elif mode == 1:
            # address register direct
            return (OpRegisterDirect(size, Registers[register+8]), 0)
        elif mode == 2:
            # address register indirect
            return (OpRegisterIndirect(size, Registers[register+8]), 0)
        elif mode == 3:
            # address register indirect with postincrement
            return (OpRegisterIndirectPostincrement(size, Registers[register+8]), 0)
        elif mode == 4:
            # address register indirect with predecrement
            return (OpRegisterIndirectPredecrement(size, Registers[register+8]), 0)
        elif mode == 5:
            # address register indirect with displacement
            return (OpRegisterIndirectDisplacement(size, Registers[register+8], struct.unpack_from('>h', data, 0)[0]), 2)
        elif mode == 6:
            # extended addressing mode
            reg = Registers[register+8]
        elif mode == 7:
            if register == 0:
                # absolute short
                val = struct.unpack_from('>H', data, 0)[0]
                if val & 0x8000:
                    if self.address_size == 4:
                        val |= 0xffff0000 # extend to 32-bits
                    else:
                        val |= 0xff0000 # extend to 24-bits (for 68000)
                return (OpAbsolute(size, val, 1, self.address_size), 2)
            if register == 1:
                # absolute long
                return (OpAbsolute(size, struct.unpack_from('>L', data, 0)[0], 2, self.address_size), 4)
            elif register == 2:
                # program counter indirect with displacement
                return (OpRegisterIndirectDisplacement(size, 'pc', struct.unpack_from('>h', data, 0)[0]), 2)
            elif register == 3:
                # extended addressing mode
                reg = 'pc'
            elif register == 4:
                # immediate
                if size == None:
                    # unspecified length
                    return (OpImmediate(size, None), None)
                elif size == ActualFormatSize[DATA_BYTE]:
                    # byte
                    return (OpImmediate(size, struct.unpack_from('>b', data, 1)[0]), 2)
                elif size == ActualFormatSize[DATA_WORD]:
                    # word
                    return (OpImmediate(size, struct.unpack_from('>h', data, 0)[0]), 2)
                elif size == ActualFormatSize[DATA_LONG]:
                    # long
                    return (OpImmediate(size, struct.unpack_from('>l', data, 0)[0]), 4)

        if reg is not None:
            extra = struct.unpack_from('>H', data, 0)[0]
            # index register
            xn = Registers[extra >> 12]
            # index register size
            index_size = (extra >> 11) & 1
            # index register scale
            scale = 1 << ((extra >> 9) & 3)
            length = 2

            if extra & 0x0100:
                # full extension word
                bd = 0
                od = 0

                # base register suppress
                if (extra >> 7) & 1:
                    reg = None

                # index register suppress
                if (extra >> 6) & 1:
                    xn = None

                # base displacement
                if (extra >> 4) & 3 == 2:
                    # word base displacement
                    bd = struct.unpack_from('>h', data, length)[0]
                    length += 2
                elif (extra >> 4) & 3 == 3:
                    # long base displacement
                    bd = struct.unpack_from('>L', data, length)[0]
                    length += 4

                # outer displacement
                if extra & 3 == 2:
                    # word outer displacement
                    od = struct.unpack_from('>h', data, length)[0]
                    length += 2
                elif extra & 3 == 3:
                    # long outer displacement
                    od = struct.unpack_from('>L', data, length)[0]
                    length += 4

                # Select the appropriate non-memory or memory specific operand class
                if extra & 7 == 0:
                    return (OpRegisterIndirectIndex(size, reg, bd, xn, index_size, scale), length)
                elif (extra >> 2) & 1:
                    return (OpMemoryIndirectPostindex(size, reg, bd, xn, index_size, scale, od), length)
                else:
                    return (OpMemoryIndirectPreindex(size, reg, bd, xn, index_size, scale, od), length)
            else:
                # brief extension word
                # 8 bit displacement
                d8 = extra & 0xff
                if d8 & 0x80:
                    d8 -= 256
                return (OpRegisterIndirectIndex(size, reg, d8, xn, index_size, scale), length)

        return (None, None)

    def decode_instruction(self, data, addr):
        error_value = ('unimplemented', len(data), None, None, None, None)
        if len(data) < 2:
            return error_value

        instruction = struct.unpack_from('>H', data)[0]

        msb = instruction >> 8
        operation_code = msb >> 4

        #print((hex(addr), hex(instruction)))

        instr = None
        length = None
        size = None
        source = None
        dest = None
        third = None

        if operation_code == 0x0:
            # Bit manipulation/MOVEP/Immed late
            if instruction & 0xf9c0 == 0x00c0:
                # rtm, callm, chk2, cmp2
                if instruction & 0xfff0 == 0x06c0:
                    instr = 'rtm'
                    dest = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[instruction & 15])
                    length = 2
                elif instruction & 0xffc0 == 0x06c0:
                    instr = 'callm'
                    source = OpImmediate(ActualFormatSize[DATA_BYTE], struct.unpack_from('>B', data, 3)[0])
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[DATA_BYTE]) # check
                    if extra_dest is None:
                        return error_value
                    length = 4+extra_dest
                else:
                    size = (instruction >> 9) & 3
                    extra = struct.unpack_from('>H', data, 2)[0]
                    if extra & 0x0800:
                        instr = 'chk2'
                    else:
                        instr = 'cmp2'
                    source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[DATA_BYTE]) # check
                    dest = OpRegisterDirect(ActualFormatSize[size], Registers[(extra >> 12) & 15])
                    if extra_source is None:
                        return error_value
                    length = 4+extra_source
            elif instruction & 0xffc0 in (0x0ac0, 0x0cc0, 0x0ec0):
                if instruction & 0xf9ff == 0x08fc:
                    instr = 'cas2'
                    size = ((instruction >> 9) & 3) - 1
                    extra1 = struct.unpack_from('>H', data, 2)[0]
                    extra2 = struct.unpack_from('>H', data, 4)[0]
                    source = OpRegisterDirectPair(ActualFormatSize[size], Registers[extra1 & 7], Registers[extra2 & 7])
                    dest = OpRegisterDirectPair(ActualFormatSize[size], Registers[(extra1 >> 6) & 7], Registers[(extra2 >> 6) & 7])
                    third = OpRegisterIndirectPair(ActualFormatSize[size], Registers[(extra1 >> 12) & 15], Registers[(extra2 >> 12) & 15])
                    length = 6
                else:
                    instr = 'cas'
                    size = ((instruction >> 9) & 3) - 1
                    extra = struct.unpack_from('>H', data, 2)[0]
                    source = OpRegisterDirect(ActualFormatSize[size], Registers[extra & 7])
                    dest = OpRegisterDirect(ActualFormatSize[size], Registers[(extra >> 6) & 7])
                    third, extra_third = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[size])
                    if extra_third is None:
                        return error_value
                    length = 4+extra_third
            elif msb in (0x00, 0x02, 0x04, 0x06, 0x0a, 0x0c):
                # ORI, ANDI, SUBI, ADDI, EORI, CMPI
                if msb == 0x00:
                    instr = 'ori'
                elif msb == 0x02:
                    instr = 'andi'
                elif msb == 0x04:
                    instr = 'subi'
                elif msb == 0x06:
                    instr = 'addi'
                elif msb == 0x0a:
                    instr = 'eori'
                elif msb == 0x0c:
                    instr = 'cmpi'
                size = (instruction >> 6) & 0x03
                source, extra_source = self.decode_effective_address(7, 4, data[2:], ActualFormatSize[size])
                if instruction & 0x00ff == 0x003c:
                    dest = OpRegisterDirect(ActualFormatSize[size], 'ccr')
                    extra_dest = 0
                elif instruction & 0x00ff == 0x007c:
                    dest = OpRegisterDirect(ActualFormatSize[size], 'sr')
                    extra_dest = 0
                else:
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[size])

                if dest is None:
                    instr = None
                else:
                    length = 2+extra_source+extra_dest
            elif msb == 0x08:
                # btst, bchg, bclr, bset with constant
                if instruction & 0xffc0 == 0x0800:
                    instr = 'btst'
                elif instruction & 0xffc0 == 0x0840:
                    instr = 'bchg'
                elif instruction & 0xffc0 == 0x0880:
                    instr = 'bclr'
                elif instruction & 0xffc0 == 0x08C0:
                    instr = 'bset'
                source = OpImmediate(ActualFormatSize[DATA_BYTE], struct.unpack_from('>B', data, 3)[0])
                dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[DATA_BYTE])
                if isinstance(dest, OpRegisterDirect):
                    dest.size = DATA_LONG
                if dest is None:
                    instr = None
                else:
                    length = 4+extra_dest
            elif msb & 0xf1 == 0x01:
                # movep, btst, bchg, bclr, bset with register
                if instruction & 0xf138 == 0x0108:
                    instr = 'movep'
                    size = ((instruction >> 6) & 1) + 1
                    source, extra_source = self.decode_effective_address(5, instruction, data[2:], ActualFormatSize[DATA_BYTE]) # check
                    dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                    length = 2+extra_source
                    if instruction & 0x0080:
                        source, dest = dest, source
                else:
                    if instruction & 0xf1c0 == 0x0100:
                        instr = 'btst'
                    elif instruction & 0xf1c0 == 0x0140:
                        instr = 'bchg'
                    elif instruction & 0xf1c0 == 0x0180:
                        instr = 'bclr'
                    elif instruction & 0xf1c0 == 0x01c0:
                        instr = 'bset'
                    source = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[(instruction >> 9) & 7]) # check
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[DATA_BYTE])
                    if isinstance(dest, OpRegisterDirect):
                        dest.size = DATA_LONG
                    if dest is None:
                        instr = None
                    else:
                        length = 2+extra_dest
            elif instruction & 0xff00 == 0x0e00:
                instr = 'moves'
                extra = struct.unpack_from('>H', data, 2)[0]
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[extra >> 12])
                source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[size])
                if extra & 0x0800:
                    source, dest = dest, source
                if extra_source is None:
                    return error_value
                length = 4+extra_source
        elif operation_code in (0x1, 0x2, 0x3):
            # move
            instr = 'move'
            if operation_code == 0x1:
                # Move byte
                size = DATA_BYTE
            elif operation_code == 0x2:
                # Move long
                size = DATA_LONG
            elif operation_code == 0x3:
                # Move word
                size = DATA_WORD

            source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
            if source is None:
                instr = None
            else:
                dest, extra_dest = self.decode_effective_address(instruction >> 6, instruction >> 9, data[2+extra_source:], ActualFormatSize[size])
                if dest is None or isinstance(dest, OpImmediate):
                    instr = None
                else:
                    if isinstance(dest, OpRegisterDirect) and (dest.reg[0] == 'a' or dest.reg == 'sp'):
                        instr = 'movea'
                    length = 2+extra_source+extra_dest
        elif operation_code == 0x4:
            # Miscellaneous
            extra_source = 0
            extra_dest = 0
            size = None
            skip_ea = False
            if instruction & 0xf100 == 0x4100:
                # lea, extb, chk
                if instruction & 0xf1c0 == 0x41c0:
                    if instruction & 0x0038:
                        instr = 'lea'
                        dest = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[((instruction >> 9) & 7) + 8])
                    else:
                        instr = 'extb'
                    size = DATA_LONG
                else:
                    instr = 'chk'
                    if instruction & 0x0080:
                        size = DATA_WORD
                    else:
                        size = DATA_LONG
                    dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
            elif msb == 0x40:
                # move from sr, negx
                if instruction & 0xffc0 == 0x40c0:
                    # move from sr
                    instr = 'move'
                    size = DATA_WORD
                    source = OpRegisterDirect(ActualFormatSize[size], 'sr')
                else:
                    instr = 'negx'
                    size = instruction >> 6
            elif msb == 0x42:
                # move to ccr, clr
                if instruction & 0xffc0 == 0x42c0:
                    # move to ccr
                    instr = 'move'
                    size = DATA_WORD
                    source = OpRegisterDirect(ActualFormatSize[size], 'ccr')
                else:
                    instr = 'clr'
                    size = instruction >> 6
            elif msb == 0x44:
                # move from ccr, neg
                if instruction & 0xffc0 == 0x44c0:
                    # move from ccr
                    instr = 'move'
                    size = DATA_WORD
                    dest = OpRegisterDirect(ActualFormatSize[size], 'ccr')
                else:
                    instr = 'neg'
                    size = instruction >> 6
            elif msb == 0x46:
                # move from sr, not
                if instruction & 0xffc0 == 0x46c0:
                    # move from sr
                    instr = 'move'
                    size = DATA_WORD
                    dest = OpRegisterDirect(ActualFormatSize[size], 'sr')
                else:
                    instr = 'not'
                    size = instruction >> 6
            elif msb in (0x48, 0x4c):
                # link, nbcd, movem, ext, swap, bkpt, pea, divs, divu, divsl, divul, muls, mulu
                if instruction & 0xfff8 == 0x4808:
                    instr = 'link'
                    size = DATA_LONG
                    dest, extra_dest = self.decode_effective_address(7, 4, data[2:], ActualFormatSize[size])
                elif instruction & 0xffc0 == 0x4800:
                    instr = 'nbcd'
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[DATA_BYTE])
                    skip_ea = True
                elif instruction & 0xfb80 == 0x4880:
                    if instruction & 0x0040:
                        size = DATA_LONG
                    else:
                        size = DATA_WORD
                    if instruction & 0x0038:
                        instr = 'movem'
                        extra_source = 2
                        extra = struct.unpack_from('>H', data, 2)[0]
                        reg_list = []
                        if instruction & 0x0038 == 0x0020:
                            for k in range(16):
                                if extra << k & 0x8000:
                                    reg_list.append(Registers[k])
                        else:
                            for k in range(16):
                                if extra >> k & 0x0001:
                                    reg_list.append(Registers[k])
                        source = OpRegisterMovemList(ActualFormatSize[size], reg_list)
                    else:
                        instr = 'ext'
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[size])
                    skip_ea = True
                    if instruction & 0x0400:
                        source, dest = dest, source
                elif instruction & 0xfff8 == 0x4840:
                    instr = 'swap'
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[DATA_LONG])
                    skip_ea = True
                elif instruction & 0xfff8 == 0x4848:
                    instr = 'bkpt'
                    source = OpImmediate(ActualFormatSize[DATA_BYTE], instruction & 7)
                    skip_ea = True
                elif instruction & 0xffc0 == 0x4840:
                    instr = 'pea'
                    size = DATA_LONG
                elif msb == 0x4c:
                    size = DATA_LONG
                    extra_dest = 2
                    extra = struct.unpack_from('>H', data, 2)[0]
                    source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_dest:], ActualFormatSize[size])
                    dh = Registers[extra & 7]
                    dl = Registers[(extra >> 12) & 7]
                    dest = OpRegisterDirect(ActualFormatSize[size], dl)
                    if instruction & 0x0040:
                        if extra & 0x0800:
                            instr = 'divs'
                        else:
                            instr = 'divu'
                        if extra & 0x0400:
                            dest = OpRegisterDirectPair(ActualFormatSize[size], dh, dl)
                        elif dh != dl:
                            dest = OpRegisterDirectPair(ActualFormatSize[size], dh, dl)
                            instr += 'l'
                    else:
                        if extra & 0x0800:
                            instr = 'muls'
                        else:
                            instr = 'mulu'
                        if extra & 0x0400:
                            dest = OpRegisterDirectPair(ActualFormatSize[size], dh, dl)
                    skip_ea = True
            elif msb == 0x4a:
                # bgnd, illegal, tas, tst
                if instruction == 0x4afa:
                    instr = 'bgnd'
                    skip_ea = True
                elif instruction == 0x4afc:
                    instr = 'illegal'
                    skip_ea = True
                elif instruction & 0xffc0 == 0x4ac0:
                    instr = 'tas'
                    skip_ea = True
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[DATA_BYTE])
                else:
                    instr = 'tst'
                    size = instruction >> 6
            elif msb == 0x4e:
                # trap, link, unlk, move, reset, nop, stop, rte, rtd, rts, trapv, rtr, movec, jsr, jmp
                if instruction & 0xfff0 == 0x4e40:
                    instr = 'trap'
                    length = 2
                    source = OpImmediate(ActualFormatSize[DATA_BYTE], instruction & 15)
                    skip_ea = True
                elif instruction & 0xfff0 == 0x4e50:
                    if instruction & 0xfff8 == 0x4e50:
                        instr = 'link'
                        dest, extra_dest = self.decode_effective_address(7, 4, data[2:], ActualFormatSize[DATA_WORD])
                    else:
                        instr = 'unlk'
                    source = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[(instruction & 7) + 8])
                    skip_ea = True
                elif instruction & 0xfff0 == 0x4e60:
                    instr = 'move'
                    size = DATA_LONG
                    source = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[(instruction & 7) + 8])
                    dest = OpRegisterDirect(ActualFormatSize[size], 'usp')
                    if instruction & 0x08:
                        source, dest = dest, source
                    skip_ea = True
                elif instruction == 0x4e70:
                    instr = 'reset'
                    skip_ea = True
                elif instruction == 0x4e71:
                    instr = 'nop'
                    skip_ea = True
                elif instruction == 0x4e72:
                    instr = 'stop'
                    source = OpImmediate(ActualFormatSize[DATA_WORD], struct.unpack_from(">H", data, 2)[0])
                    extra_source = 2
                    skip_ea = True
                elif instruction == 0x4e73:
                    instr = 'rte'
                    skip_ea = True
                elif instruction == 0x4e74:
                    instr = 'rtd'
                    dest, extra_dest = self.decode_effective_address(7, 4, data[2:], ActualFormatSize[DATA_WORD])
                    skip_ea = True
                elif instruction == 0x4e75:
                    instr = 'rts'
                    skip_ea = True
                elif instruction == 0x4e76:
                    instr = 'trapv'
                    skip_ea = True
                elif instruction == 0x4e77:
                    instr = 'rtr'
                    skip_ea = True
                elif instruction & 0xfffe == 0x4e7A:
                    instr = 'movec'
                    size = DATA_LONG
                    extended = struct.unpack_from('>H', data, 2)[0]
                    control_reg = self.control_registers.get(extended & 0x0fff, None)
                    reg = (extended >> 12) & 15
                    if control_reg is None:
                        instr = None
                    else:
                        source = OpRegisterDirect(ActualFormatSize[size], control_reg)
                        dest = OpRegisterDirect(ActualFormatSize[size], Registers[reg])
                        if instruction & 1:
                            source, dest = dest, source
                    extra_source = 2
                    skip_ea = True
                elif instruction & 0xff80 == 0x4e80:
                    if instruction & 0xffc0 == 0x4e80:
                        instr = 'jsr'
                    else:
                        instr = 'jmp'
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[DATA_LONG])
                    skip_ea = True
            if instr is not None:
                if size is not None:
                    size &= 3
                if skip_ea:
                    pass
                elif dest is None:
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_source:], ActualFormatSize[size])
                else:
                    source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2+extra_dest:], ActualFormatSize[size])
                if extra_source is None or extra_dest is None:
                    instr = None
                else:
                    length = 2+extra_source+extra_dest
        elif operation_code == 0x5:
            # ADDQ/SUBQ/Scc/DBcc/TRAPcc
            if instruction & 0xf0c0 == 0x50c0:
                if instruction & 0xf0f8 == 0x50c8:
                    instr = 'db'+Condition[(instruction >> 8) & 0xf]
                    source = OpRegisterDirect(ActualFormatSize[DATA_WORD], Registers[instruction & 7])
                    dest = OpRegisterIndirectDisplacement(ActualFormatSize[DATA_LONG], 'pc', struct.unpack_from('>h', data, 2)[0])
                    length = 4
                elif instruction & 0xf0ff in (0x50fa, 0x50fb, 0x50fc):
                    instr = 'trap'+Condition[(instruction >> 8) & 0xf]
                    if instruction & 7 == 2:
                        length = 4
                        source = OpImmediate(ActualFormatSize[DATA_WORD], struct.unpack_from('>H', data, 2)[0])
                    elif instruction & 7 == 3:
                        length = 6
                        source = OpImmediate(ActualFormatSize[DATA_LONG], struct.unpack_from('>L', data, 2)[0])
                    elif instruction & 7 == 4:
                        length = 2
                else:
                    instr = 's'+Condition[(instruction >> 8) & 0xf]
                    size = DATA_BYTE
                    dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                    if extra_dest is None:
                        return error_value
                    length = 2+extra_dest
            else:
                if instruction & 0x0100:
                    instr = 'subq'
                else:
                    instr = 'addq'
                val = (instruction >> 9) & 7
                if val == 0:
                    val = 8
                size = (instruction >> 6) & 3
                source = OpImmediate(ActualFormatSize[DATA_BYTE], val)
                dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                if extra_dest is None:
                    return error_value
                length = 2+extra_dest
        elif operation_code == 0x6:
            # Bcc/BSR/BRA
            if msb == 0x60:
                instr = 'bra'
            elif msb == 0x61:
                instr = 'bsr'
            else:
                instr = 'b'+Condition[(instruction >> 8) & 0xf]
            val = instruction & 0xff
            if val == 0:
                val = struct.unpack_from('>h', data, 2)[0]
                length = 4
            elif val == 0xff:
                val = struct.unpack_from('>L', data, 2)[0]
                length = 6
            else:
                if val & 0x80:
                    val -= 256
                length = 2
            dest = OpRegisterIndirectDisplacement(ActualFormatSize[DATA_LONG], 'pc', val)
        elif operation_code == 0x7:
            # MOVEQ
            instr = 'moveq'
            size = DATA_LONG
            val = instruction & 0xff
            if val & 0x80:
                val |= 0xffffff00
            source = OpImmediate(ActualFormatSize[size], val)
            dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
            length = 2
        elif operation_code == 0x8:
            # OR/DIV/SBCD
            if instruction & 0xf0c0 == 0x80c0:
                if instruction & 0x0100:
                    instr = 'divs'
                else:
                    instr = 'divu'
                size = DATA_WORD
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                if extra_source is None:
                    return error_value
                length = 2+extra_source
            elif instruction & 0xf1f0 == 0x8100:
                instr = 'sbcd'
                length = 2
                dest = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[(instruction >> 9) & 7])
                source = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[instruction & 7])
                if instruction & 8:
                    dest = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[((instruction >> 9) & 7) + 8])
                    source = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[(instruction & 7) + 8])
            elif instruction & 0xf130 == 0x8100:
                if instruction & 0x0040:
                    instr = 'pack'
                    if instruction & 8:
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[((instruction >> 9) & 7) + 8])
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_WORD], Registers[(instruction & 7) + 8])
                    else:
                        dest = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[(instruction >> 9) & 7])
                        source = OpRegisterDirect(ActualFormatSize[DATA_WORD], Registers[instruction & 7])
                else:
                    instr = 'unpk'
                    if instruction & 8:
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_WORD], Registers[((instruction >> 9) & 7) + 8])
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[(instruction & 7) + 8])
                    else:
                        dest = OpRegisterDirect(ActualFormatSize[DATA_WORD], Registers[(instruction >> 9) & 7])
                        source = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[instruction & 7])
                length = 4
                third = OpImmediate(ActualFormatSize[DATA_WORD], struct.unpack_from(">H", data, 2)[0])
            else:
                instr = 'or'
                opmode = (instruction >> 6) & 0x7
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                if opmode & 4:
                    source, dest = dest, source
                if extra_source is None:
                    return error_value
                length = 2+extra_source
        elif operation_code == 0x9:
            # SUB/SUBA/SUBX
            instr = 'sub'
            opmode = (instruction >> 6) & 0x7
            if opmode in (0x03, 0x07):
                instr = 'suba'
                if opmode == 0x03:
                    size = DATA_WORD
                else:
                    size = DATA_LONG
                dest = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[((instruction >> 9) & 7) + 8])
            else:
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
            source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
            if instr == 'sub' and opmode & 4:
                if isinstance(source, OpRegisterDirect):
                    instr = 'subx'
                    if source.reg[0] == 'a' or source.reg == 'sp':
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[size], source.reg)
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[size], dest.reg)
                else:
                    source, dest = dest, source
            if extra_source is None:
                return error_value
            length = 2+extra_source
        elif operation_code == 0xa:
            # (unassigned, reserved)
            pass
        elif operation_code == 0xb:
            # CMP/EOR
            instr = 'cmp'
            opmode = (instruction >> 6) & 0x7
            if opmode in (0x03, 0x07):
                instr = 'cmpa'
                if opmode == 0x03:
                    size = DATA_WORD
                else:
                    size = DATA_LONG
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[((instruction >> 9) & 7) + 8])
            else:
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
            source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
            if instr == 'cmp' and opmode & 4:
                if instruction & 0x0038 == 0x0008:
                    instr = 'cmpm'
                    source = OpRegisterIndirectPostincrement(ActualFormatSize[size], Registers[instruction & 15])
                    dest = OpRegisterIndirectPostincrement(ActualFormatSize[size], Registers[((instruction >> 9) & 7) + 8])
                else:
                    source, dest = dest, source
                    instr = 'eor'
            if extra_source is None:
                return error_value
            length = 2+extra_source
        elif operation_code == 0xc:
            # AND/MUL/ABCD/EXG
            if instruction & 0xf0c0 == 0xc0c0:
                if instruction & 0x0100:
                    instr = 'muls'
                else:
                    instr = 'mulu'
                size = DATA_WORD
                source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                if extra_source is None:
                    return error_value
                length = 2+extra_source
            elif instruction & 0xf130 == 0xc100:
                if instruction & 0xf1f0 == 0xc100:
                    instr = 'abcd'
                    if instruction & 0x0008:
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[(instruction & 7) + 8])
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[DATA_BYTE], Registers[((instruction >> 9) & 7) + 8])
                    else:
                        source = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[instruction & 7])
                        dest = OpRegisterDirect(ActualFormatSize[DATA_BYTE], Registers[(instruction >> 9) & 7])
                else:
                    instr = 'exg'
                    size = DATA_LONG
                    source = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                    dest = OpRegisterDirect(ActualFormatSize[size], Registers[instruction & 7])
                    if instruction & 0xf1f8 == 0xc148:
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[size], Registers[((instruction >> 9) & 7) + 8])
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[size], Registers[(instruction & 7) + 8])
                    if instruction & 0xf1f8 == 0xc188:
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[size], Registers[(instruction & 7) + 8])
                length = 2
            else:
                instr = 'and'
                opmode = (instruction >> 6) & 0x7
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
                source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                if opmode & 4:
                    source, dest = dest, source
                if extra_source is None:
                    return error_value
                length = 2+extra_source
        elif operation_code == 0xd:
            # ADD/ADDA/ADDX
            instr = 'add'
            opmode = (instruction >> 6) & 0x7
            if opmode in (0x03, 0x07):
                instr = 'adda'
                if opmode == 0x03:
                    size = DATA_WORD
                else:
                    size = DATA_LONG
                dest = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[((instruction >> 9) & 7) + 8])
            else:
                size = (instruction >> 6) & 3
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[(instruction >> 9) & 7])
            source, extra_source = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
            if instr == 'add' and opmode & 4:
                if isinstance(source, OpRegisterDirect):
                    instr = 'addx'
                    if source.reg[0] == 'a' or source.reg == 'sp':
                        source = OpRegisterIndirectPredecrement(ActualFormatSize[size], source.reg)
                        dest = OpRegisterIndirectPredecrement(ActualFormatSize[size], dest.reg)
                else:
                    source, dest = dest, source
            if extra_source is None:
                return error_value
            length = 2+extra_source
        elif operation_code == 0xe:
            # shift/rotate/bit field
            if instruction & 0xF8C0 == 0xE0C0:
                # shift/rotate
                size = DATA_WORD
                direction = (instruction >> 8) & 1
                style = (instruction >> 9) & 3
                dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[2:], ActualFormatSize[size])
                instr = ShiftStyle[style]
                if direction:
                    instr += 'l'
                else:
                    instr += 'r'
                if extra_dest is None:
                    return error_value
                length = 2+extra_dest
            elif instruction & 0xF8C0 == 0xE8C0:
                # bit field instructions
                # TODO
                style = (instruction >> 8) & 0x7
                instr = 'bf'+BitfieldStyle[style]
                dest, extra_dest = self.decode_effective_address(instruction >> 3, instruction, data[4:], ActualFormatSize[DATA_LONG])
                length = 4
                if extra_dest is not None:
                    length += extra_dest
            else:
                # shift/rotate
                size = (instruction >> 6) & 3
                direction = (instruction >> 8) & 1
                style = (instruction >> 3) & 3
                if (instruction >> 5) & 1:
                    source = OpRegisterDirect(ActualFormatSize[DATA_LONG], Registers[(instruction >> 9) & 7])
                else:
                    val = (instruction >> 9) & 7
                    if val == 0:
                        val = 8
                    source = OpImmediate(ActualFormatSize[DATA_BYTE], val)
                dest = OpRegisterDirect(ActualFormatSize[size], Registers[instruction & 7])
                instr = ShiftStyle[style]
                if direction:
                    instr += 'l'
                else:
                    instr += 'r'
                length = 2
        elif operation_code == 0xf:
            # Check if this is a MC68040 floating point instruction (processor ID is 1)
            if instruction & 0xfe00 == 0xf200:
                fp_operation_code = (instruction >> 6) & 7
                if fp_operation_code == 0:
                    length = 4
                    extra = struct.unpack_from('>H', data, 2)[0]
                    sub_fp_operation_code = extra >> 13
                    if sub_fp_operation_code & 5 == 0:
                        destination_register = (extra >> 7) & 7
                        source_specifier = (extra >> 10) & 7
                        opmode = extra & 0x7f
                        r_m = (extra >> 14) & 1
                        if r_m == 0:
                            size = FP_DATA_REGISTER
                            source = FP_OpRegisterDirect(FP_ActualFormatSize[size],
                                                         FP_Registers[source_specifier])
                            dest = FP_OpRegisterDirect(FP_ActualFormatSize[size],
                                                       FP_Registers[destination_register])
                        else:
                            if source_specifier == 7:
                                # TODO: Add support for 'fmovecr'
                                pass
                            else:
                                dest = FP_OpRegisterDirect(FP_ActualFormatSize[FP_DATA_REGISTER],
                                                           FP_Registers[destination_register])
                                size = source_specifier
                                source, extra_source = self.fp_decode_effective_address(
                                    instruction >> 3,
                                    instruction,
                                    data[length:],
                                    FP_ActualFormatSize[size],
                                    size)
                                if extra_source is not None:
                                    length += extra_source

                        instr = None
                        if (opmode >> 3) == 6:
                            # TODO: Add support for 'fsincos'
                            pass
                        else:
                            instr_sig = opmode & 0x3b
                            if opmode == 4 or (opmode & 0x63) == 0x41:
                                # atypical opmode signature
                                instr = 'fsqrt'
                            elif instr_sig == 0:
                                # fmove <ea> -> FP register
                                instr = 'fmove'
                            elif instr_sig == 0x18:
                                instr = 'fabs'
                            elif instr_sig == 0x1a:
                                instr = 'fneg'
                            elif instr_sig == 0x20:
                                instr = 'fdiv'
                            elif instr_sig == 0x22:
                                instr = 'fadd'
                            elif instr_sig == 0x23:
                                instr = 'fmul'
                            elif instr_sig == 0x28:
                                instr = 'fsub'
                            elif instr_sig == 0x38:
                                instr = 'fcmp'
                            elif instr_sig == 0x3a:
                                instr = 'ftst'

                        # Handle single and double precision rounding variants
                        if instr is not None and (opmode >> 6):
                            if (opmode >> 2) & 1:
                                instr = 'fd' + instr[1:]
                            else:
                                instr = 'fs' + instr[1:]

                    elif sub_fp_operation_code == 3:
                        # fmove FP register -> <ea>
                        instr = 'fmove'
                        source_register = (extra >> 7) & 7
                        source = FP_OpRegisterDirect(FP_ActualFormatSize[FP_DATA_REGISTER],
                                                     FP_Registers[source_register])
                        size = (extra >> 10) & 7
                        dest, extra_dest = self.fp_decode_effective_address(
                            instruction >> 3,
                            instruction,
                            data[length:],
                            FP_ActualFormatSize[size],
                            size)
                        if extra_dest is not None:
                            length += extra_dest

                    elif (sub_fp_operation_code & 6) == 4:
                        # Per M68k manual, this is always a 32-bit operation
                        size = FP_DATA_SCREGISTER
                        source, extra_source = self.fp_decode_effective_address(
                            instruction >> 3,
                            instruction,
                            data[length:],
                            FP_ActualFormatSize[size],
                            size)
                        if extra_source is not None:
                            length += extra_source

                        fpscr = (extra >> 10) & 7
                        if fpscr in FP_SCRegisters:
                            # fmove single FP system control register <-> <ea>
                            instr = 'fmove'
                            dest = FP_OpRegisterDirect(FP_ActualFormatSize[FP_DATA_SCREGISTER],
                                                       FP_SCRegisters[fpscr])
                        else:
                            # fmove multiple FP system control registers <-> <ea>
                            instr = 'fmovem'
                            dest = FP_OpSCRegisterMovemList(
                                FP_ActualFormatSize[FP_DATA_SCREGISTER],
                                [FP_SCRegisters[i] for i in FP_SCRegisters.keys() if i & fpscr])

                        if (extra >> 13) & 1:
                            source, dest = dest, source

                    elif (sub_fp_operation_code & 6) == 6:
                        # TODO: Consider matching hardware enforced constraints on mode field,
                        #       direction field, register list, and effective address combinations

                        # fmove multiple FP data registers <-> <ea>
                        instr = 'fmovem'
                        # Per M68k manual, this is always an extended precision operation
                        size = FP_DATA_EXTENDED_PRECISION
                        source, extra_source = self.fp_decode_effective_address(
                            instruction >> 3,
                            instruction,
                            data[length:],
                            FP_ActualFormatSize[size],
                            size)
                        if extra_source is not None:
                            length += extra_source

                        mode_field = (extra >> 11) & 3
                        if mode_field == 0 or mode_field == 2:
                            # The static register list changes order based on the mode
                            registers_list = extra & 0xff
                            dest = FP_OpRegisterMovemList(
                                FP_ActualFormatSize[FP_DATA_REGISTER],
                                [FP_Registers[i] for i in range(len(FP_Registers))
                                 if (1 << (len(FP_Registers)-1-i if mode_field else i))
                                 & registers_list])
                        else:
                            # The dynamic register list is held in an integer data register
                            dest = OpRegisterDirect(
                                ActualFormatSize[DATA_BYTE], Registers[(extra >> 4) & 7])

                        if (extra >> 13) & 1:
                            source, dest = dest, source

                elif fp_operation_code == 1:
                    extra = struct.unpack_from('>H', data, 2)[0]
                    mode = (instruction >> 3) & 7
                    trap_mode_field = instruction & 7
                    if mode == 1:
                        # TODO: Add support for 'FDBcc'
                        pass
                    elif mode == 7 and trap_mode_field > 1:
                        condition = extra & 0x3f
                        if condition < len(FP_Condition):
                            # ftrapcc
                            instr = 'ftrap'+FP_Condition[condition]
                            length = 4
                            if (trap_mode_field & 2) == 2:
                                register = 4  # immediate
                                size = FP_DATA_WORD if trap_mode_field == 2 else FP_DATA_LONG
                                dest, extra_dest = self.fp_decode_effective_address(
                                    mode,
                                    register,
                                    data[length:],
                                    FP_ActualFormatSize[size],
                                    size)
                                if extra_dest is not None:
                                    length += extra_dest
                    else:
                        condition = extra & 0x3f
                        if condition < len(FP_Condition):
                            # fscc
                            instr = 'fs'+FP_Condition[condition]
                            # Per M68k manual, this is always a byte operation
                            size = FP_DATA_BYTE
                            length = 4
                            dest, extra_dest = self.fp_decode_effective_address(
                                instruction >> 3,
                                instruction,
                                data[length:],
                                FP_ActualFormatSize[size],
                                size)
                            if extra_dest is not None:
                                length += extra_dest
                elif (fp_operation_code & 2) == 2:
                    condition = instruction & 0x3f
                    if condition < len(FP_Condition):
                        # fbcc
                        instr = 'fb'+FP_Condition[condition]
                        if (fp_operation_code & 1) == 0:
                            format_specifier = '>h'
                            length = 4
                        else:
                            format_specifier = '>L'
                            length = 6
                        displacement = struct.unpack_from(format_specifier, data, 2)[0]
                        dest = OpRegisterIndirectDisplacement(
                            ActualFormatSize[DATA_LONG], 'pc', displacement)
                elif (fp_operation_code & 4) == 4:
                    instr = 'fsave' if fp_operation_code == 4 else 'frestore'  # 5
                    length = 2
                    # State frames vary in size, use the largest one specified for the M68040
                    source, extra_source = self.fp_decode_effective_address(
                        instruction >> 3,
                        instruction,
                        data[length:],
                        96)
                    if extra_source is not None:
                        length += extra_source

            elif instruction & 0xff20 == 0xf400:
                instr = 'cinv'
                length = 2
            elif instruction & 0xff20 == 0xf420:
                instr = 'cpush'
                length = 2
            elif instruction & 0xffe0 == 0xf500:
                # MC68*040 variant
                instr = 'pflush'
                length = 2
            elif instruction & 0xff80 == 0xff80:
                instruction = 'illFF'
                length = 2
            # coprocessor instructions
            # TODO
        if instr is None:
            # FIXME uncomment to debug
            #log_error('Bad opcode at 0x{:x}'.format(addr))
            return error_value

        #print((instr, length, size, source, dest, third))
        return instr, length, size, source, dest, third

    def generate_instruction_il(self, il, instr, length, size, source, dest, third):
        size_bytes = None
        if size is not None:
            size_bytes = 1 << size

        if instr in ('move', 'moveq'):
            if instr == 'move' and isinstance(dest, OpRegisterDirect) and dest.reg in ('ccr', 'sr'):
                il.append(il.set_reg(1, LLIL_TEMP(0), source.get_source_il(il)))
                il.append(il.set_flag('c', il.test_bit(1, il.reg(1, LLIL_TEMP(0)), il.const(1, 0x01))))
                il.append(il.set_flag('v', il.test_bit(1, il.reg(1, LLIL_TEMP(0)), il.const(1, 0x02))))
                il.append(il.set_flag('z', il.test_bit(1, il.reg(1, LLIL_TEMP(0)), il.const(1, 0x04))))
                il.append(il.set_flag('n', il.test_bit(1, il.reg(1, LLIL_TEMP(0)), il.const(1, 0x08))))
                il.append(il.set_flag('x', il.test_bit(1, il.reg(1, LLIL_TEMP(0)), il.const(1, 0x10))))
            else:
                flags = 'nzvc'
                if ((isinstance(source, OpRegisterDirect) and source.reg in ('usp', 'ccr', 'sr')) or
                    (isinstance(dest, OpRegisterDirect) and dest.reg in ('usp', 'ccr', 'sr'))):
                    # move to/from control registers do not set flags
                    flags = 0
                il.append(
                    dest.get_dest_il(il,
                        source.get_source_il(il),
                        flags
                    )
                )
        elif instr in ('movea', 'movec'):
            # dest.size = DATA_LONG
            # il.append(
            #     dest.get_dest_il(il,
            #         il.sign_extend(4,
            #             source.get_source_il(il)
            #         )
            #     )
            # )
            il.append(
                dest.get_dest_il(il,
                    source.get_source_il(il)
                )
            )
        elif instr == 'clr':
            il.append(
                dest.get_dest_il(il,
                    il.const(4, 0),
                    'nzvc'
                )
            )
        elif instr in ('add', 'addi', 'addq'):
            il.append(
                dest.get_dest_il(il,
                    il.add(size_bytes,
                        dest.get_source_il(il),
                        source.get_source_il(il),
                        flags='*'
                    )
                )
            )
        elif instr == 'adda':
            dest.size = DATA_LONG
            il.append(
                dest.get_dest_il(il,
                    il.add(4,
                        dest.get_source_il(il),
                        il.sign_extend(4,
                            source.get_source_il(il)
                        )
                    )
                )
            )
        elif instr == 'addx':
            il.append(
                dest.get_dest_il(il,
                    il.add(size_bytes,
                        il.add(size_bytes,
                            dest.get_source_il(il),
                            source.get_source_il(il),
                            flags='*'
                        ),
                        il.flag('x'),
                        flags='*'
                    )
                )
            )
        elif instr in ('sub', 'subi', 'subq'):
            il.append(
                dest.get_dest_il(il,
                    il.sub(size_bytes,
                        dest.get_source_il(il),
                        source.get_source_il(il),
                        flags='*'
                    )
                )
            )
        elif instr == 'suba':
            dest.size = DATA_LONG
            il.append(
                dest.get_dest_il(il,
                    il.sub(4,
                        dest.get_source_il(il),
                        il.sign_extend(4,
                            source.get_source_il(il)
                        )
                    )
                )
            )
        elif instr == 'subx':
            il.append(
                dest.get_dest_il(il,
                    il.sub(size_bytes,
                        il.sub(size_bytes,
                            dest.get_source_il(il),
                            source.get_source_il(il),
                            flags='*'
                        ),
                        il.flag('x'),
                        flags='*'
                    )
                )
            )
        elif instr == 'neg':
            il.append(
                dest.get_dest_il(il,
                    il.neg_expr(size_bytes,
                        dest.get_source_il(il),
                        flags='*'
                    )
                )
            )
        elif instr == 'negx':
            il.append(
                dest.get_dest_il(il,
                    il.sub(size_bytes,
                        il.neg_expr(size_bytes,
                            dest.get_source_il(il),
                            flags='*'
                        ),
                        il.flag('x'),
                        flags='*'
                    )
                )
            )
        elif instr == 'abcd':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'sbcd':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'nbcd':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'pack':
            il.append(
                il.set_reg(2,
                    LLIL_TEMP(0),
                    il.add(2,
                        source.get_source_il(il),
                        third.get_source_il(il)
                    )
                )
            )
            il.append(
                dest.get_dest_il(il,
                    il.or_expr(1,
                        il.and_expr(2,
                            il.reg(2, LLIL_TEMP(0)),
                            il.const(2, 0x000F)
                        ),
                        il.logical_shift_right(2,
                            il.and_expr(2,
                                il.reg(2, LLIL_TEMP(0)),
                                il.const(2, 0x0F00)
                            ),
                            il.const(1, 4)
                        )
                    )
                )
            )
        elif instr == 'unpk':
            il.append(
                il.set_reg(1,
                    LLIL_TEMP(0),
                    source.get_source_il(il)
                )
            )
            il.append(
                dest.get_dest_il(il,
                    il.add(2,
                        il.or_expr(2,
                            il.and_expr(2,
                                il.reg(1, LLIL_TEMP(0)),
                                il.const(1, 0x0F)
                            ),
                            il.shift_left(2,
                                il.and_expr(2,
                                    il.reg(1, LLIL_TEMP(0)),
                                    il.const(1, 0xF0)
                                ),
                                il.const(1, 4)
                            )
                        ),
                        third.get_source_il(il)
                    )
                )
            )
        elif instr in ('muls', 'mulu'):
            if isinstance(dest, OpRegisterDirectPair):
                il.append(
                    il.set_reg_split(4,
                        dest.reg1,
                        dest.reg2,
                        il.mult(4,
                            source.get_source_il(il),
                            dest.get_source_il(il)[0],
                            flags='nzvc'
                        )
                    )
                )
            else:
                il.append(
                    il.set_reg(4,
                        dest.reg,
                        il.mult(4,
                            source.get_source_il(il),
                            dest.get_source_il(il),
                            flags='nzvc'
                        )
                    )
                )
        elif instr == 'divs':
            if size == 1:
                dividend_il = dest.get_source_il(il)
                divisor_il = source.get_source_il(il)
                dest.size = DATA_LONG
                il.append(
                    dest.get_dest_il(il,
                        il.or_expr(4,
                            il.shift_left(4, il.mod_signed(2, dividend_il, divisor_il), il.const(1, 16)),
                            il.div_signed(2, dividend_il, divisor_il, flags='nzvc')
                        )
                    )
                )
            elif isinstance(dest, OpRegisterDirect):
                dividend_il = dest.get_source_il(il)
                divisor_il = source.get_source_il(il)
                il.append(
                    dest.get_dest_il(il,
                        il.div_signed(4, dividend_il, divisor_il, flags='nzvc')
                    )
                )
            else:
                dividend_il = il.or_expr(8, il.shift_left(8, il.reg(4, dest.reg1), il.const(1, 32)), il.reg(4, dest.reg2))
                divisor_il = source.get_source_il(il)
                il.append(
                    il.set_reg(4,
                        LLIL_TEMP(0),
                        il.mod_signed(4, dividend_il, divisor_il)
                    )
                )
                il.append(
                    il.set_reg(4,
                        dest.reg2,
                        il.div_signed(4, dividend_il, divisor_il, flags='nzvc')
                    )
                )
                il.append(
                    il.set_reg(4,
                        dest.reg1,
                        il.reg(4, LLIL_TEMP(0))
                    )
                )
        elif instr == 'divsl':
            dividend_il = il.reg(4, dest.reg2)
            divisor_il = source.get_source_il(il)
            il.append(
                il.set_reg(4,
                    dest.reg1,
                    il.mod_signed(4, dividend_il, divisor_il)
                )
            )
            il.append(
                il.set_reg(4,
                    dest.reg2,
                    il.div_signed(4, dividend_il, divisor_il, flags='nzvc')
                )
            )
        elif instr == 'divu':
            if size == 1:
                dividend_il = dest.get_source_il(il)
                divisor_il = source.get_source_il(il)
                dest.size = DATA_LONG
                il.append(
                    dest.get_dest_il(il,
                        il.or_expr(4,
                            il.shift_left(4, il.mod_unsigned(2, dividend_il, divisor_il), il.const(1, 16)),
                            il.div_unsigned(2, dividend_il, divisor_il, flags='nzvc')
                        )
                    )
                )
            elif isinstance(dest, OpRegisterDirect):
                dividend_il = dest.get_source_il(il)
                divisor_il = source.get_source_il(il)
                il.append(
                    dest.get_dest_il(il,
                        il.div_unsigned(4, dividend_il, divisor_il, flags='nzvc')
                    )
                )
            else:
                dividend_il = il.or_expr(8, il.shift_left(8, il.reg(4, dest.reg1), il.const(1, 32)), il.reg(4, dest.reg2))
                divisor_il = source.get_source_il(il)
                il.append(
                    il.set_reg(4,
                        LLIL_TEMP(0),
                        il.mod_unsigned(4, dividend_il, divisor_il)
                    )
                )
                il.append(
                    il.set_reg(4,
                        dest.reg2,
                        il.div_unsigned(4, dividend_il, divisor_il, flags='nzvc')
                    )
                )
                il.append(
                    il.set_reg(4,
                        dest.reg1,
                        il.reg(4, LLIL_TEMP(0))
                    )
                )
        elif instr == 'divul':
            dividend_il = il.reg(4, dest.reg2)
            divisor_il = source.get_source_il(il)
            il.append(
                il.set_reg(4,
                    dest.reg1,
                    il.mod_unsigned(4, dividend_il, divisor_il)
                )
            )
            il.append(
                il.set_reg(4,
                    dest.reg2,
                    il.div_unsigned(4, dividend_il, divisor_il, flags='nzvc')
                )
            )
        elif instr == 'cas':
            skip_label_found = True

            skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

            if skip is None:
                skip = LowLevelILLabel()
                skip_label_found = False

            il.append(
                il.sub(size_bytes,
                    third.get_source_il(il),
                    source.get_source_il(il),
                    flags='nzvc'
                )
            )

            equal = LowLevelILLabel()
            not_equal = LowLevelILLabel()

            il.append(
                il.if_expr(il.flag_condition(LowLevelILFlagCondition.LLFC_E), equal, not_equal)
            )

            il.mark_label(equal)

            il.append(
                third.get_dest_il(il,
                    dest.get_source_il(il)
                )
            )

            il.append(
                il.goto(skip)
            )

            il.mark_label(not_equal)

            il.append(
                source.get_dest_il(il,
                    third.get_source_il(il)
                )
            )

            if not skip_label_found:
                il.mark_label(skip)
        elif instr == 'cas2':
            skip_label_found = True

            skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

            if skip is None:
                skip = LowLevelILLabel()
                skip_label_found = False

            il.append(
                il.sub(size_bytes,
                    third.get_source_il(il)[0],
                    source.get_source_il(il)[0],
                    flags='nzvc'
                )
            )

            equal = LowLevelILLabel()
            not_equal = LowLevelILLabel()
            check2 = LowLevelILLabel()

            il.append(
                il.if_expr(il.flag_condition(LowLevelILFlagCondition.LLFC_E), check2, not_equal)
            )

            il.mark_label(check2)

            il.append(
                il.sub(size_bytes,
                    third.get_source_il(il)[1],
                    source.get_source_il(il)[1],
                    flags='nzvc'
                )
            )

            il.append(
                il.if_expr(il.flag_condition(LowLevelILFlagCondition.LLFC_E), equal, not_equal)
            )

            il.mark_label(equal)

            for it in third.get_dest_il(il,
                        dest.get_source_il(il)
                    ):
                il.append(it)

            il.append(
                il.goto(skip)
            )

            il.mark_label(not_equal)

            for it in source.get_dest_il(il,
                        third.get_source_il(il)
                    ):
                il.append(it)

            il.append(
                il.goto(skip)
            )

            if not skip_label_found:
                il.mark_label(skip)
        elif instr == 'chk':
            skip_label_found = True

            skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

            if skip is None:
                skip = LowLevelILLabel()
                skip_label_found = False

            trap = LowLevelILLabel()
            check = LowLevelILLabel()

            il.append(
                il.if_expr(
                    il.compare_unsigned_less_than(size_bytes,
                        dest.get_source_il(il),
                        il.const(size_bytes, 0)
                    ),
                    trap,
                    check
                )
            )

            il.mark_label(check)

            il.append(
                il.if_expr(
                    il.compare_unsigned_greater_than(size_bytes,
                        dest.get_source_il(il),
                        source.get_source_il(il)
                    ),
                    trap,
                    skip
                )
            )

            il.mark_label(trap)

            il.append(
                il.system_call()
            )

            il.append(
                il.goto(skip)
            )

            if not skip_label_found:
                il.mark_label(skip)
        elif instr == 'chk2':
            skip_label_found = True

            skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

            if skip is None:
                skip = LowLevelILLabel()
                skip_label_found = False

            trap = LowLevelILLabel()
            check = LowLevelILLabel()

            il.append(
                il.set_reg(4,
                    LLIL_TEMP(0),
                    source.get_address_il(il)
                )
            )

            il.append(
                il.if_expr(
                    il.compare_unsigned_less_than(size_bytes,
                        dest.get_source_il(il),
                        il.load(size_bytes,
                            il.reg(4, LLIL_TEMP(0))
                        )
                    ),
                    trap,
                    check
                )
            )

            il.mark_label(check)

            il.append(
                il.if_expr(
                    il.compare_unsigned_greater_than(size_bytes,
                        dest.get_source_il(il),
                        il.load(size_bytes,
                            il.add(4,
                                il.reg(4, LLIL_TEMP(0)),
                                il.const(4, size_bytes)
                            )
                        )
                    ),
                    trap,
                    skip
                )
            )

            il.mark_label(trap)

            il.append(
                il.system_call()
            )

            il.append(
                il.goto(skip)
            )

            if not skip_label_found:
                il.mark_label(skip)
        elif instr == 'bchg':
            bit_number_il = il.mod_unsigned(1,
                source.get_source_il(il),
                il.const(1, 8 << dest.size)
            )
            il.append(
                il.set_flag('z',
                    il.compare_not_equal(4,
                        il.test_bit(4,
                            dest.get_source_il(il),
                            il.shift_left(4,
                                il.const(4, 1),
                                bit_number_il
                            )
                        ),
                        il.const(4, 0)
                    )
                )
            )
            il.append(
                dest.get_dest_il(il,
                    il.xor_expr(4,
                        dest.get_source_il(il),
                        il.shift_left(4,
                            il.const(4, 1),
                            bit_number_il
                        )
                    )
                )
            )
        elif instr == 'bclr':
            bit_number_il = il.mod_unsigned(1,
                source.get_source_il(il),
                il.const(1, 8 << dest.size)
            )
            il.append(
                il.set_flag('z',
                    il.compare_not_equal(4,
                        il.test_bit(4,
                            dest.get_source_il(il),
                            il.shift_left(4,
                                il.const(4, 1),
                                bit_number_il
                            )
                        ),
                        il.const(4, 0)
                    )
                )
            )
            il.append(
                dest.get_dest_il(il,
                    il.and_expr(4,
                        dest.get_source_il(il),
                        il.not_expr(4,
                            il.shift_left(4,
                                il.const(4, 1),
                                bit_number_il
                            )
                        )
                    )
                )
            )
        elif instr == 'bset':
            bit_number_il = il.mod_unsigned(1,
                source.get_source_il(il),
                il.const(1, 8 << dest.size)
            )
            il.append(
                il.set_flag('z',
                    il.compare_not_equal(4,
                        il.test_bit(4,
                            dest.get_source_il(il),
                            il.shift_left(4,
                                il.const(4, 1),
                                bit_number_il
                            )
                        ),
                        il.const(4, 0)
                    )
                )
            )
            il.append(
                dest.get_dest_il(il,
                    il.or_expr(4,
                        dest.get_source_il(il),
                        il.shift_left(4,
                            il.const(4, 1),
                            bit_number_il
                        )
                    )
                )
            )
        elif instr == 'btst':
            bit_number_il = il.mod_unsigned(1,
                source.get_source_il(il),
                il.const(1, 8 << dest.size)
            )
            il.append(
                il.set_flag('z',
                    il.compare_not_equal(4,
                        il.test_bit(4,
                            dest.get_source_il(il),
                            il.shift_left(4,
                                il.const(4, 1),
                                bit_number_il
                            )
                        ),
                        il.const(4, 0)
                    )
                )
            )
        elif instr in ('asl', 'lsl'):
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.shift_left(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        flags='*'
                    )
                )
            )
        elif instr == 'asr':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.arith_shift_right(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        flags='*'
                    )
                )
            )
        elif instr == 'lsr':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.logical_shift_right(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        flags='*'
                    )
                )
            )
        elif instr == 'rol':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.rotate_left(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        flags='*'
                    )
                )
            )
        elif instr == 'ror':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.rotate_right(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        flags='*'
                    )
                )
            )
        elif instr == 'roxl':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.rotate_left_carry(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        il.flag('x'),
                        flags='*'
                    )
                )
            )
        elif instr == 'roxr':
            source_il = il.const(1, 1)
            if source is not None:
                source_il = source.get_source_il(il)
            il.append(
                dest.get_dest_il(il,
                    il.rotate_right_carry(size_bytes,
                        dest.get_source_il(il),
                        source_il,
                        il.flag('x'),
                        flags='*'
                    )
                )
            )
        elif instr in ('cmp', 'cmpi', 'cmpm'):
            il.append(
                il.sub(size_bytes,
                    dest.get_source_il(il),
                    source.get_source_il(il),
                    flags='nzvc'
                )
            )
        elif instr == 'cmpa':
            dest.size = DATA_LONG
            il.append(
                il.sub(4,
                    dest.get_source_il(il),
                    il.sign_extend(4,
                        source.get_source_il(il)
                    ),
                    flags='nzvc'
                )
            )
        elif instr == 'cmp2':
            skip_label_found = True

            skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

            if skip is None:
                skip = LowLevelILLabel()
                skip_label_found = False

            check = LowLevelILLabel()

            il.append(
                il.set_reg(4,
                    LLIL_TEMP(0),
                    source.get_address_il(il)
                )
            )

            il.append(
                il.sub(size_bytes,
                    dest.get_source_il(il),
                    il.load(size_bytes,
                        il.reg(4, LLIL_TEMP(0))
                    ),
                    flags='nzvc'
                )
            )

            il.append(
                il.if_expr(
                    il.flag_condition(LowLevelILFlagCondition.LLFC_ULT),
                    skip,
                    check
                )
            )

            il.mark_label(check)

            il.append(
                il.sub(size_bytes,
                    dest.get_source_il(il),
                    il.load(size_bytes,
                        il.add(4,
                            il.reg(4, LLIL_TEMP(0)),
                            il.const(4, size_bytes)
                        )
                    ),
                    flags='nzvc'
                )
            )

            il.append(
                il.goto(skip)
            )

            if not skip_label_found:
                il.mark_label(skip)
        elif instr == 'tas':
            il.append(
                il.set_reg(1, LLIL_TEMP(0), dest.get_source_il(il), flags='nzvc')
            )
            il.append(
                dest.get_dest_il(il,
                    il.or_expr(1,
                        il.reg(1, LLIL_TEMP(0)),
                        il.const(1, 0x80)
                    )
                )
            )
        elif instr == 'tst':
            il.append(
                il.sub(size_bytes,
                    dest.get_source_il(il),
                    il.const(4, 0),
                    flags='nzvc'
                )
            )
        elif instr in ('and', 'andi'):
            if instr == 'andi' and isinstance(dest, OpRegisterDirect) and dest.reg in ('ccr', 'sr'):
                if not source.value & 0x01: il.append(il.set_flag('c', il.const(1, 0)))
                if not source.value & 0x02: il.append(il.set_flag('v', il.const(1, 0)))
                if not source.value & 0x04: il.append(il.set_flag('z', il.const(1, 0)))
                if not source.value & 0x08: il.append(il.set_flag('n', il.const(1, 0)))
                if not source.value & 0x11: il.append(il.set_flag('x', il.const(1, 0)))
            else:
                il.append(
                    dest.get_dest_il(il,
                        il.and_expr(size_bytes,
                            dest.get_source_il(il),
                            source.get_source_il(il),
                            flags='nzvc'
                        )
                    )
                )
        elif instr in ('or', 'ori'):
            if instr == 'ori' and isinstance(dest, OpRegisterDirect) and dest.reg in ('ccr', 'sr'):
                if source.value & 0x01: il.append(il.set_flag('c', il.const(1, 1)))
                if source.value & 0x02: il.append(il.set_flag('v', il.const(1, 1)))
                if source.value & 0x04: il.append(il.set_flag('z', il.const(1, 1)))
                if source.value & 0x08: il.append(il.set_flag('n', il.const(1, 1)))
                if source.value & 0x11: il.append(il.set_flag('x', il.const(1, 1)))
            else:
                il.append(
                    dest.get_dest_il(il,
                        il.or_expr(size_bytes,
                            dest.get_source_il(il),
                            source.get_source_il(il),
                            flags='nzvc'
                        )
                    )
                )
        elif instr in ('eor', 'eori'):
            if instr == 'eori' and isinstance(dest, OpRegisterDirect) and dest.reg in ('ccr', 'sr'):
                if source.value & 0x01: il.append(il.set_flag('c', il.xor_expr(1, il.flag('c'), il.const(1, 1))))
                if source.value & 0x02: il.append(il.set_flag('v', il.xor_expr(1, il.flag('v'), il.const(1, 1))))
                if source.value & 0x04: il.append(il.set_flag('z', il.xor_expr(1, il.flag('z'), il.const(1, 1))))
                if source.value & 0x08: il.append(il.set_flag('n', il.xor_expr(1, il.flag('n'), il.const(1, 1))))
                if source.value & 0x11: il.append(il.set_flag('x', il.xor_expr(1, il.flag('x'), il.const(1, 1))))
            else:
                il.append(
                    dest.get_dest_il(il,
                        il.xor_expr(size_bytes,
                            dest.get_source_il(il),
                            source.get_source_il(il),
                            flags='nzvc'
                        )
                    )
                )
        elif instr == 'not':
            il.append(
                dest.get_dest_il(il,
                    il.not_expr(size_bytes,
                        dest.get_source_il(il),
                        flags='nzvc'
                    )
                )
            )
        elif instr == 'swap':
            il.append(
                dest.get_dest_il(il,
                    il.rotate_right(4,
                        dest.get_source_il(il),
                        il.const(1, 16)
                    )
                )
            )
        elif instr == 'exg':
            il.append(
                il.set_reg(4, LLIL_TEMP(0), source.get_source_il(il))
            )
            il.append(
                source.get_dest_il(il, dest.get_source_il(il))
            )
            il.append(
                dest.get_dest_il(il, il.reg(4, LLIL_TEMP(0)))
            )
        elif instr == 'ext':
            if not dest:
                il.append(il.unimplemented())
            elif dest.size == 1:
                il.append(
                    il.set_reg(2,
                        dest.reg,
                        il.sign_extend(4,
                            il.reg(1, dest.reg),
                            flags='nzvc'
                        )
                    )
                )
            else:
                il.append(
                    il.set_reg(4,
                        dest.reg,
                        il.sign_extend(4,
                            il.reg(2, dest.reg),
                            flags='nzvc'
                        )
                    )
                )
        elif instr == 'extb':
            reg = dest.reg
            il.append(
                il.set_reg(4,
                    reg,
                    il.sign_extend(4,
                        il.reg(1, reg),
                        flags='nzvc'
                    )
                )
            )
        elif instr == 'movem':
            if isinstance(source, OpRegisterMovemList):
                if isinstance(dest, OpRegisterIndirectPredecrement):
                    il.append(
                        il.set_reg(4, LLIL_TEMP(0), dest.get_address_il(il))
                    )
                    if self.movem_store_decremented:
                        il.append(
                            il.set_reg(4,
                                dest.reg,
                                il.sub(4,
                                    il.reg(4, LLIL_TEMP(0)),
                                    il.const(4, len(source.regs)*size_bytes)
                                )
                            )
                        )
                    for k in range(len(source.regs)):
                        il.append(
                            il.store(size_bytes,
                                il.sub(4,
                                    il.reg(4, LLIL_TEMP(0)),
                                    il.const(4, (k+1)*size_bytes)
                                ),
                                il.reg(size_bytes, source.regs[len(source.regs)-1-k])
                            )
                        )
                    if not self.movem_store_decremented:
                        il.append(
                            il.set_reg(4,
                                dest.reg,
                                il.sub(4,
                                    il.reg(4, LLIL_TEMP(0)),
                                    il.const(4, len(source.regs)*size_bytes)
                                )
                            )
                        )
                else:
                    il.append(
                        il.set_reg(4, LLIL_TEMP(0), dest.get_address_il(il))
                    )
                    for k in range(len(source.regs)):
                        il.append(
                            il.store(size_bytes,
                                il.add(4,
                                    il.reg(4, LLIL_TEMP(0)),
                                    il.const(4, k*size_bytes)
                                ),
                                il.reg(size_bytes, source.regs[k])
                            )
                        )
            else:
                il.append(
                    il.set_reg(4, LLIL_TEMP(0), source.get_address_il(il))
                )
                for k in range(len(dest.regs)):
                    il.append(
                        il.set_reg(size_bytes,
                            dest.regs[k],
                            il.load(size_bytes,
                                il.add(4,
                                    il.reg(4, LLIL_TEMP(0)),
                                    il.const(4, k*size_bytes)
                                )
                            )
                        )
                    )
                if isinstance(source, OpRegisterIndirectPostincrement):
                    il.append(
                        il.set_reg(4,
                            source.reg,
                            il.add(4,
                                il.reg(4, LLIL_TEMP(0)),
                                il.const(4, len(dest.regs)*size_bytes)
                            )
                        )
                    )
        elif instr == 'lea':
            il.append(
                dest.get_dest_il(il, source.get_address_il(il))
            )
        elif instr == 'pea':
            il.append(
                il.push(4, dest.get_address_il(il))
            )
        elif instr == 'link':
            source.size = DATA_LONG
            il.append(
                il.push(4, source.get_source_il(il))
            )
            il.append(
                source.get_dest_il(il, il.reg(4, "sp"))
            )
            il.append(
                il.set_reg(4,
                    "sp",
                    il.add(4,
                        il.reg(4, "sp"),
                        il.sign_extend(4, dest.get_source_il(il))
                    )
                )
            )
        elif instr == 'unlk':
            il.append(
                il.set_reg(4, "sp", source.get_source_il(il))
            )
            il.append(
                source.get_dest_il(il, il.pop(4))
            )
        elif instr in ('jmp', 'bra'):
            dstil = dest.get_address_il(il)

            dstlabel = None
            if il[dstil].operation == LowLevelILOperation.LLIL_CONST:
                dstlabel = il.get_label_for_address(il.arch, il[dstil].constant)

            if dstlabel is not None:
                il.append(
                    il.goto(dstlabel)
                )
            else:
                il.append(
                    il.jump(dstil)
                )
        elif instr in ('jsr', 'bsr'):
            il.append(
                il.call(dest.get_address_il(il))
            )
        elif instr == 'callm':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'cpush':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'cinv':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'pflush':
            # TODO
            il.append(il.unimplemented())
        elif instr in ('bhi', 'bls', 'bcc', 'bcs', 'bne', 'beq', 'bvc', 'bvs',
                    'bpl', 'bmi', 'bge', 'blt', 'bgt', 'ble'):
            flag_cond = ConditionMapping.get(instr[1:], None)
            dest_il = dest.get_address_il(il)
            cond_il = None

            if flag_cond is not None:
                cond_il = il.flag_condition(flag_cond)

            if cond_il is None:
                il.append(il.unimplemented())
            else:
                t = None
                if il[dest_il].operation == LowLevelILOperation.LLIL_CONST:
                    t = il.get_label_for_address(il.arch, il[dest_il].constant)

                indirect = False

                if t is None:
                    t = LowLevelILLabel()
                    indirect = True

                f_label_found = True

                f = il.get_label_for_address(il.arch, il.current_address+length)

                if f is None:
                    f = LowLevelILLabel()
                    f_label_found = False

                il.append(
                    il.if_expr(cond_il, t, f)
                )

                if indirect:
                    il.mark_label(t)
                    il.append(il.jump(dest_il))

                if not f_label_found:
                    il.mark_label(f)
        elif instr in ('dbt', 'dbf', 'dbhi', 'dbls', 'dbcc', 'dbcs', 'dbne',
                    'dbeq', 'dbvc', 'dbvs', 'dbpl', 'dbmi', 'dbge', 'dblt',
                    'dbgt', 'dble'):
            flag_cond = ConditionMapping.get(instr[2:], None)
            dest_il = dest.get_address_il(il)
            cond_il = None

            if flag_cond is not None:
                cond_il = il.flag_condition(flag_cond)
            elif instr == 'dbt':
                cond_il = il.const(1, 1)
            elif instr == 'dbf':
                cond_il = il.const(1, 0)

            if cond_il is None:
                il.append(il.unimplemented())
            else:
                branch = None
                if il[dest_il].operation == LowLevelILOperation.LLIL_CONST:
                    branch = il.get_label_for_address(Architecture['M68000'], il[dest_il].constant)

                indirect = False

                if branch is None:
                    branch = LowLevelILLabel()
                    indirect = True

                skip_label_found = True

                skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

                if skip is None:
                    skip = LowLevelILLabel()
                    skip_label_found = False

                decrement = LowLevelILLabel()

                il.append(
                    il.if_expr(cond_il, skip, decrement)
                )

                il.mark_label(decrement)

                il.append(
                    il.set_reg(2,
                        LLIL_TEMP(0),
                        il.sub(2,
                            source.get_source_il(il),
                            il.const(2, 1)
                        )
                    )
                )

                il.append(
                    source.get_dest_il(il, il.reg(2, LLIL_TEMP(0)))
                )

                il.append(
                    il.if_expr(
                        il.compare_equal(2,
                            il.reg(2, LLIL_TEMP(0)),
                            il.const(2, -1)
                        ),
                        skip,
                        branch
                    )
                )

                if indirect:
                    il.mark_label(branch)
                    il.append(il.jump(dest_il))

                if not skip_label_found:
                    il.mark_label(skip)
        elif instr in ('st', 'sf', 'shi', 'sls', 'scc', 'scs', 'sne', 'seq',
                    'svc', 'svs', 'spl', 'smi', 'sge', 'slt', 'sgt', 'sle'):
            flag_cond = ConditionMapping.get(instr[1:], None)
            cond_il = None

            if flag_cond is not None:
                cond_il = il.flag_condition(flag_cond)
            elif instr == 'st':
                cond_il = il.const(1, 1)
            elif instr == 'sf':
                cond_il = il.const(1, 0)

            if cond_il is None:
                il.append(il.unimplemented())
            else:
                skip_label_found = True

                skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

                if skip is None:
                    skip = LowLevelILLabel()
                    skip_label_found = False

                set_dest = LowLevelILLabel()
                clear_dest = LowLevelILLabel()

                il.append(
                    il.if_expr(cond_il, set_dest, clear_dest)
                )

                il.mark_label(set_dest)

                il.append(
                    dest.get_dest_il(il, il.const(1, 1))
                )

                il.append(
                    il.goto(skip)
                )

                il.mark_label(clear_dest)

                il.append(
                    dest.get_dest_il(il, il.const(1, 0))
                )

                il.append(
                    il.goto(skip)
                )

                if not skip_label_found:
                    il.mark_label(skip)
        elif instr == 'rtd':
            il.append(
                il.set_reg(4,
                    LLIL_TEMP(0),
                    il.pop(4)
                )
            )
            il.append(
                il.set_reg(4, 'sp',
                    il.add(4,
                        il.reg(4, 'sp'),
                        il.sign_extend(4, il.const(2,
                            dest.value),
                            0
                        )
                    )
                )
            )
            il.append(
                il.ret(
                    il.reg(4, LLIL_TEMP(0))
                )
            )
        elif instr == 'rte':
            il.append(
                il.set_reg(2,
                    "sr",
                    il.pop(2)
                )
            )
            il.append(
                il.ret(
                    il.pop(4)
                )
            )
        elif instr == 'rtm':
            # TODO
            il.append(il.unimplemented())
        elif instr == 'rtr':
            il.append(
                il.set_reg(2,
                    "ccr",
                    il.pop(2)
                )
            )
            il.append(
                il.ret(
                    il.pop(4)
                )
            )
        elif instr == 'rts':
            il.append(
                il.ret(
                    il.pop(4)
                )
            )
        elif instr in ('trapv', 'trapt', 'trapf', 'traphi', 'trapls', 'trapcc',
                    'trapcs', 'trapne', 'trapeq', 'trapvc', 'trapvs', 'trappl',
                    'trapmi', 'trapge', 'traplt', 'trapgt', 'traple'):
            flag_cond = ConditionMapping.get(instr[4:], None)
            cond_il = None

            if flag_cond is not None:
                cond_il = il.flag_condition(flag_cond)
            elif instr == 'trapt':
                cond_il = il.const(1, 1)
            elif instr == 'trapf':
                cond_il = il.const(1, 0)
            elif instr == 'trapv':
                cond_il = il.flag_condition(LowLevelILFlagCondition.LLFC_O)

            if cond_il is None:
                il.append(il.unimplemented())
            else:
                skip_label_found = True

                skip = il.get_label_for_address(Architecture['M68000'], il.current_address+length)

                if skip is None:
                    skip = LowLevelILLabel()
                    skip_label_found = False

                trap = LowLevelILLabel()

                il.append(
                    il.if_expr(cond_il, trap, skip)
                )

                il.mark_label(trap)

                il.append(
                    il.system_call()
                )

                il.append(
                    il.goto(skip)
                )

                if not skip_label_found:
                    il.mark_label(skip)
        elif instr in ('trap', 'illegal', 'bkpt'):
            il.append(il.system_call())
        elif instr in ('bgnd', 'nop', 'reset', 'stop'):
            il.append(il.nop())
        else:
            il.append(il.unimplemented())

    def perform_get_instruction_info(self, data, addr):
        instr, length, _size, _source, dest, _third = self.decode_instruction(data, addr)
        if instr == 'unimplemented':
            return None

        result = InstructionInfo()
        result.length = length

        if instr in ('rtd', 'rte', 'rtr', 'rts'):
            result.add_branch(BranchType.FunctionReturn)
        elif instr in ('jmp', 'jsr',
                    'bra', 'bsr', 'bhi', 'bls', 'bcc', 'bcs', 'bne', 'beq',
                    'bvc', 'bvs', 'bpl', 'bmi', 'bge', 'blt', 'bgt', 'ble',
                    'dbt', 'dbf', 'dbhi', 'dbls', 'dbcc', 'dbcs', 'dbne',
                    'dbeq', 'dbvc', 'dbvs', 'dbpl', 'dbmi', 'dbge', 'dblt',
                    'dbgt', 'dble') + FBcc_Instructions:
            conditional = False
            branch_dest = None

            bt = BranchType.UnresolvedBranch
            if instr in ('jmp', 'bra'):
                bt = BranchType.UnconditionalBranch
            elif instr in ('jsr', 'bsr'):
                bt = BranchType.CallDestination
            else:
                conditional = True

            if isinstance(dest, OpAbsolute):
                branch_dest = dest.address
            elif isinstance(dest, OpRegisterIndirect):
                if dest.reg == 'pc':
                    branch_dest = addr+2
                else:
                    bt = BranchType.UnresolvedBranch
            elif isinstance(dest, OpRegisterIndirectDisplacement):
                if dest.reg == 'pc':
                    branch_dest = addr+2+dest.offset
                else:
                    bt = BranchType.UnresolvedBranch
            elif isinstance(dest, OpRegisterIndirectIndex):
                bt = BranchType.UnresolvedBranch

            if conditional:
                # pylint: disable=unsubscriptable-object
                if instr[0:2] == 'db':
                    result.add_branch(BranchType.TrueBranch, addr+length)
                    result.add_branch(BranchType.FalseBranch, branch_dest)
                else:
                    result.add_branch(BranchType.TrueBranch, branch_dest)
                    result.add_branch(BranchType.FalseBranch, addr+length)
            else:
                if bt == BranchType.IndirectBranch or bt == BranchType.UnresolvedBranch or branch_dest is None:
                    result.add_branch(bt)
                else:
                    result.add_branch(bt, branch_dest)

        return result

    def perform_get_instruction_text(self, data, addr):
        instr, length, size, source, dest, third = self.decode_instruction(data, addr)

        if size is not None:
            if instr[0] == 'f':
                instr += FP_SizeSuffix[size]
            else:
                # pylint: disable=invalid-sequence-index
                instr += SizeSuffix[size]

        tokens = [InstructionTextToken(InstructionTextTokenType.InstructionToken, "%-10s" % instr)]

        if source is not None:
            tokens += source.format(addr)

        if dest is not None:
            if source is not None:
                tokens += [InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ',')]
            tokens += dest.format(addr)

        if third is not None:
            if source is not None or dest is not None:
                tokens += [InstructionTextToken(InstructionTextTokenType.OperandSeparatorToken, ',')]
            tokens += third.format(addr)

        return tokens, length

    def perform_get_instruction_low_level_il(self, data, addr, il):
        instr, length, size, source, dest, third = self.decode_instruction(data, addr)

        if instr == 'movem':
            # movem overrides default predecrement/postincrement IL generation

            self.generate_instruction_il(il, instr, length, size, source, dest, third)

        elif instr is not None:

            # predecrement
            if source is not None:
                pre_il = source.get_pre_il(il)
                if pre_il is not None:
                    il.append(pre_il)

            if dest is not None:
                pre_il = dest.get_pre_il(il)
                if pre_il is not None:
                    il.append(pre_il)

            if third is not None:
                pre_il = third.get_pre_il(il)
                if pre_il is not None:
                    il.append(pre_il)

            self.generate_instruction_il(il, instr, length, size, source, dest, third)

            # postincrement
            if source is not None:
                post_il = source.get_post_il(il)
                if post_il is not None:
                    il.append(post_il)

            if dest is not None:
                post_il = dest.get_post_il(il)
                if post_il is not None:
                    il.append(post_il)

            if third is not None:
                post_il = third.get_post_il(il)
                if post_il is not None:
                    il.append(post_il)
        else:
            il.append(il.unimplemented())
        return length

    def perform_is_never_branch_patch_available(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60:
            # BRA, BSR, Bcc
            return True
        if data[0] == 0x4e and data[1] & 0x80 == 0x80:
            # JMP, JSR
            return True
        return False

    def perform_is_invert_branch_patch_available(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60 and data[0] & 0xfe != 0x60:
            # Bcc
            return True
        return False

    def perform_is_always_branch_patch_available(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60 and data[0] & 0xfe != 0x60:
            # Bcc
            return True
        return False

    def perform_is_skip_and_return_zero_patch_available(self, data, addr):
        return self.perform_skip_and_return_value(data, addr)

    def perform_is_skip_and_return_value_patch_available(self, data, addr):
        data = bytearray(data)
        if data[0] == 0x61:
            # BSR
            return True
        if data[0] == 0x4e and data[1] & 0xc0 == 0x80:
            # JSR
            return True
        return False

    def perform_convert_to_nop(self, data, addr):
        count = int(len(data)/2)
        if count*2 != len(data):
            return None
        return b'\x4e\x71' * count

    def perform_never_branch(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60:
            # BRA, BSR, Bcc
            return self.perform_convert_to_nop(data, addr)
        if data[0] == 0x4e and data[1] & 0x80 == 0x80:
            # JMP, JSR
            return self.perform_convert_to_nop(data, addr)
        return None

    def perform_invert_branch(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60 and data[0] & 0xfe != 0x60:
            # Bcc
            return bytearray([data[0]^1])+data[1:]
        return None

    def perform_always_branch(self, data, addr):
        data = bytearray(data)
        if data[0] & 0xf0 == 0x60 and data[0] & 0xfe != 0x60:
            # Bcc
            return b'\x60'+data[1:]
        return None

    def perform_skip_and_return_value(self, data, addr, value=0):
        count = int(len(data)/2)
        if count*2 != len(data):
            return None
        data = bytearray(data)
        ok = False
        if data[0] == 0x61:
            # BSR
            ok = True
        if data[0] == 0x4e and data[1] & 0xc0 == 0x80:
            # JSR
            ok = True
        if not ok:
            return None

        if value > 0x80000000:
            value = value - 0x100000000

        if value >= -128 and value <= 127 and len(data) >= 2:
            value = value & 0xff
            return b'\x70'+struct.pack('>b',value)+b'\x4e\x71'*(count-1)

        if len(data) >= 6:
            return b'\x20\x3C'+struct.pack('>l', value)+b'\x4e\x71'*(count-3)

        return None


class M68008(M68000):
    name = "M68008"


class M68010(M68000):
    name = "M68010"
    control_registers = {
        0x000: 'sfc',
        0x001: 'dfc',
        0x800: 'usp',
        0x801: 'vbr',
    }

    # add BKPT, MOVE from CCR, MOVEC, MOVES, RTD


class M68020(M68010):
    name = "M68020"
    control_registers = {
        0x000: 'sfc',
        0x001: 'dfc',
        0x800: 'usp',
        0x801: 'vbr',
        0x002: 'cacr',
        0x802: 'caar',
        0x803: 'msp',
        0x804: 'isp',
    }
    address_size = 4
    memory_indirect = True
    movem_store_decremented = True

    # add BFCHG, BFCLR, BFEXTS, BFEXTU, BFFO, BFINS, BFSET, BFTST, CALLM, CAS, CAS2, CHK2, CMP2, cpBcc, cpDBcc, cpGEN, cpRESTORE, cpSAVE, cpScc, cpTRAPcc
    # DIVSL, DIVUL, EXTB, PACK, RTM, TRAPcc, UNPK
    # add memory indirect addressing


class M68030(M68020):
    name = "M68030"

    # remove CALLM, RTM
    # add PFLUSH, PFLUSHA, PLOAD, PMOVE, PTEST


class M68040(M68030):
    name = "M68040"
    control_registers = {
        0x000: 'sfc',
        0x001: 'dfc',
        0x800: 'usp',
        0x801: 'vbr',
        0x002: 'cacr',
        0x803: 'msp',
        0x804: 'isp',
        0x003: 'tc',
        0x004: 'itt0',
        0x005: 'itt1',
        0x006: 'dtt0',
        0x007: 'dtt1',
        0x805: 'mmusr',
        0x806: 'urp',
        0x807: 'srp',
    }

    # remove cpBcc, cpDBcc, cpGEN, cpRESTORE, cpSAVE, cpScc, cpTRAPcc, PFLUSHA, PLOAD, PMOVE
    # add CINV, CPUSH, floating point, MOVE16


class M68LC040(M68040):
    name = "M68LC040"


class M68EC040(M68040):
    name = "M68EC040"
    control_registers = {
        0x000: 'sfc',
        0x001: 'dfc',
        0x800: 'usp',
        0x801: 'vbr',
        0x002: 'cacr',
        0x803: 'msp',
        0x804: 'isp',
        0x004: 'iacr0',
        0x005: 'iacr1',
        0x006: 'dacr0',
        0x007: 'dacr1'
    }


class M68330(M68010):
    name = "M68330"
    movem_store_decremented = True
    # AKA CPU32

    # add BGND, CHK2, CMP2, DIVSL, DIVUL, EXTB, LPSTOP, TBLS, TBLSN, TBLU, TBLUN, TRAPcc


class M68340(M68330):
    name = "M68340"


def create_vector_table(view, addr, size=256):
    vectors = {
        0: 'reset_initial_interrupt_stack_pointer',
        1: 'reset_initial_program_counter',
        2: 'access_fault',
        3: 'address_error',
        4: 'illegal_instruction',
        5: 'integer_divide_by_zero',
        6: 'chk_chk2_instruction',
        7: 'ftrapcc_trapcc_trapv_instruction',
        8: 'privilege_violation',
        9: 'trace',
        10: 'line_1010_emulator',
        11: 'line_1111_emulator',
        # 12 unassigned_reserved
        13: 'coprocessor_protocol_violation',
        14: 'format_error',
        15: 'uninitialized_interrupt',
        # 16-23 unassigned_reserved
        24: 'spurious_interrupt',
        25: 'level_1_interrupt_autovector',
        26: 'level_2_interrupt_autovector',
        27: 'level_3_interrupt_autovector',
        28: 'level_4_interrupt_autovector',
        29: 'level_5_interrupt_autovector',
        30: 'level_6_interrupt_autovector',
        31: 'level_7_interrupt_autovector',
        32: 'trap_0_instruction',
        33: 'trap_1_instruction',
        34: 'trap_2_instruction',
        35: 'trap_3_instruction',
        36: 'trap_4_instruction',
        37: 'trap_5_instruction',
        38: 'trap_6_instruction',
        39: 'trap_7_instruction',
        40: 'trap_8_instruction',
        41: 'trap_9_instruction',
        42: 'trap_10_instruction',
        43: 'trap_11_instruction',
        44: 'trap_12_instruction',
        45: 'trap_13_instruction',
        46: 'trap_14_instruction',
        47: 'trap_15_instruction',
        48: 'fp_branch_or_set_on_unordered_condition',
        49: 'fp_inexact_result',
        50: 'fp_divide_by_zero',
        51: 'fp_underflow',
        52: 'fp_operand_error',
        53: 'fp_overflow',
        54: 'fp_signaling_nan',
        55: 'fp_unimplemented_data_type',
        56: 'mmu_configuration_error',
        57: 'mmu_illegal_operation_error',
        58: 'mmu_access_level_violation_error',
        # 59-63 unassigned_reserved
    }
    for k in range(0, 192):
        vectors[k+64] = 'user_%d' % k

    t = view.parse_type_string("void *")[0]

    for k in range(size):
        name = vectors.get(k, 'unassigned_reserved')

        view.define_user_symbol(Symbol(SymbolType.DataSymbol, addr+4*k, "_vector_%d_%s" % (k, name)))
        view.define_user_data_var(addr+4*k, t)
        value = struct.unpack(">L", view.read(addr+4*k, 4))[0]

        if k > 0:
            view.define_user_symbol(Symbol(SymbolType.FunctionSymbol, value, "vector_%d_%s" % (k, name)))
            view.add_entry_point(value)


def prompt_create_vector_table(view, addr=None):
    architectures = ['M68000', 'M68008', 'M68010', 'M68020', 'M68030', 'M68040', 'M68LC040', 'M68EC040', 'M68330', 'M68340']
    size_choices = ['Full (256)', 'MMU (59)', 'FP (56)', 'Traps (48)', 'Interrupts (32)']
    size_raw = [256, 59, 56, 48, 32]

    if addr is None:
        addr = 0

    need_arch = True
    if view.platform is not None and view.platform.arch.name in architectures:
        # 68k arch already selected
        need_arch = False

    address_field = AddressField('Address', view, addr)
    arch_field = ChoiceField('Architecture', architectures)
    size_field = ChoiceField('Table size', size_choices)

    res = False

    if need_arch:
        res = get_form_input([address_field, arch_field, size_field], 'Create M68k vector table')
    else:
        res = get_form_input([address_field, size_field], 'Create M68k vector table')

    if res:
        address = address_field.result
        size = size_raw[size_field.result]

        if need_arch:
            arch = architectures[arch_field.result]
            view.platform = Architecture[arch].standalone_platform

        create_vector_table(view, address, size)


#PluginCommand.register("Create M68k vector table", "Create M68k vector table", prompt_create_vector_table)
PluginCommand.register_for_address("Create M68k vector table", "Create M68k vector table", prompt_create_vector_table)

M68000.register()
M68008.register()
M68010.register()
M68020.register()
M68030.register()
M68040.register()
M68LC040.register()
M68EC040.register()
M68330.register()
M68340.register()

BinaryViewType['ELF'].register_arch(4, Endianness.BigEndian, Architecture['M68030'])

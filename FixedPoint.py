#!/usr/bin/python3
# Simple Python Fixed-Point Module (SPFPM)
# (C)Copyright 2006-2022, RW Penney


# This file is (C)Copyright 2006-2022, RW Penney
# and is released under the Python-2.4.2 license
# (see http://www.python.org/psf/license),
# it therefore comes with NO WARRANTY, and NO CLAIMS OF FITNESS FOR ANY PURPOSE.
# However, the author welcomes *constructive* feedback
# and bug-fixes via: rwpenney 'AT' users 'DOT' sourceforge 'DOT' net


"""
The Simple Python Fixed-Point Module (SPFPM) provides objects of types
FXnum and FXfamily which implement basic mathematical operations
on fixed-point binary numbers (i.e. having a fixed number of
fractional binary digits, with the number of integer digits being either
arbitrary or subject to a user-defined limit).

FXnum objects exist within a user-controllable collection of families
managed by the FXfamily class, which sets the number of fractional
& integer digits for each family. This can be used, for example,
to ensure that a set of 8-bit quantities can be manipulated consistently
and kept separate from a set of 200-bit quantities in the same program.
Conversion between FXnum objects in different families is supported,
but solely through an explicit cast.

>>> x = FXnum(2.1)                  # default FXfamily, with 64 fractional bits
>>> print(x)
2.1000000000000000888
>>> x = FXnum(21) / 10              # fractional error ~1/2^64 or ~5e-20
>>> print(x)
2.0999999999999999999
>>> rx = x.sqrt()                   # rx created in same family as x
>>> print(rx)
1.4491376746189438573
>>> v = x + 2 * rx
>>> print(v)
4.9982753492378877146

>>> y = FXnum(3.2, FXfamily(12))    # lower-precision 12-bit number
>>> ly = y.log()                    # ly created in same family as y
>>> print(ly)                       # fractional error ~1/2^12 or ~2e-4
1.162841
>>> print(ly.exp())
3.198730
>>> fy = float(y)
>>> print(fy)
3.199951171875

>>> # a = x + y                     # throws exception - different families
>>> a = x + FXnum(y, _defaultFamily)
>>> print(a)
5.3000732421874999999
>>> b = rx + x                      # ok - same families
>>> # c = rx + ly                   # throws exception - different families
>>> d = ly + y                      # ok - same families

>>> a = FXnum(1.4, FXfamily(12, 4)) # limit magnitude to 2^(4-1)
>>> print(a)
1.399902
>>> print(a * 5, a * -5)
6.999511 -6.999511
>>> #print(a * 6, a * -6)           # throws exception indicating overflow

>>> fam = FXfamily(200)
>>> print(fam.pi)
3.141592653589793238462643383279502884197169399375105820974944
>>> #   60-digit precision has error less than 6e-61

Note:
    Be careful not to assume that a large number of fractional bits within
    a number will necessarily mean large accuracy. For example, computations
    involving exponentiation and logarithms are intrinsically vulnerable to
    magnifying mere rounding errors in their inputs into significant errors
    in their outputs. This is a fact of life with any approximation to
    real arithmetic using finite-precision quantities.

SPFPM is provided as-is, with no warranty of any form.
"""


SPFPM_VERSION = '1.6.2'

import math


log10_2 = math.log10(2)


class FXfamily:
    """Descriptor of the accuracy of a set of fixed-point numbers.

    This class defines the fixed-point resolution of a set of FXnum objects.
    All arithmetic operations between FXnum objects that are
    not explicitly cast into a different FXfamily
    must share the same FXfamily.
    Multiple FXfamily objects can exist within the same application so that,
    for example, sets of 12-bit, 32-bit & 200-bit quantities
    can be manipulated concurrently.
    """

    def __init__(self, n_bits=64, n_intbits=None):
        self.fraction_bits = n_bits         # Bits to right of binary point
        self.integer_bits = n_intbits       # Bits to left of binary point (including sign)
        self.scale = 1 << n_bits
        self._roundup = 1 << (n_bits - 1)

        try:
            thresh = 1 << (n_bits + n_intbits - 1)
            def validate(scaledval):
                if scaledval >= thresh or scaledval < -thresh:
                    raise FXoverflowError
        except:
            def validate(scaledval): return
        self.validate = validate

        # Cached values of various mathematical constants:
        self._exp1, self._log2, self._pi, self._sqrt2 = (None,) * 4

    @property
    def resolution(self):
        """The number of fractional binary digits"""
        return self.fraction_bits

    def _pseudo_precision(self, transition_width=4):
        """Estimate an effective number of fractional decimal digits

        The number of decimal digits needed to exactly represent
        b fractional bits is also b, but this drastically overestimates
        the practical accuracy. This formula heuristically interpolates
        between one decimal digit per bit, and a growth rate of order
        0.301 digits per bit for bit-counts greater than about four.
        """
        frac_bits = self.fraction_bits
        if frac_bits < (10 * transition_width):
            enhancement = -(1 - log10_2) * transition_width \
                            * math.expm1(-frac_bits / transition_width)
        else:
            enhancement = 0.0
        return frac_bits * log10_2 + enhancement

    @property
    def exp1(self):
        """Inverse natural logarithm of unity."""
        if self._exp1 is None:
            # Brute-force calculation of exp(1) using augmented accuracy:
            augfamily = self.augment()
            exp0_25 = (1 / FXnum(4, augfamily))._rawexp()
            exp0_5 = exp0_25 * exp0_25
            exp1 = exp0_5 * exp0_5
            self._exp1 = FXnum(exp1, self)
        return self._exp1

    @property
    def log2(self):
        """Natural logarithm of two."""
        if self._log2 is None:
            # Brute-force calculation of log(2) using augmented accuracy
            #   via log(2) = 5log(3^12 / 2^19) - 12log(3^5 / 2^8)
            augfamily = self.augment()

            q0 = FXnum((3 ** 12) - (1 << 19), augfamily) >> 19
            q1 = FXnum((3 ** 5) - (1 << 8), augfamily) >> 8
            auglog2 = (5 * q0._rawlog(isDelta=True)
                        - 12 * q1._rawlog(isDelta=True))
            self._log2 = FXnum(auglog2, self)
        return self._log2

    @property
    def pi(self):
        """Ratio of circle's perimeter to its diameter."""
        if self._pi is None:
            # Use Bailey-Borwein-Plouffe representation of Pi,
            # involving powers of 1/16 and simple rational terms:
            augfamily = self.augment()

            augpi = augfamily(0)
            k4 = 0
            while True:
                k8 = k4 * 2
                term = (4 / augfamily(k8 + 1)
                        - 2 / augfamily(k8 + 4)
                        - 1 / augfamily(k8 + 5)
                        - 1 / augfamily(k8 + 6)) >> k4

                if term.scaledval == 0: break

                augpi += term
                k4 += 4

            self._pi = FXnum(augpi, self)
        return self._pi

    @property
    def sqrt2(self):
        """Square-root of two."""
        if self._sqrt2 is None:
            augfamily = self.augment()
            # Use initial two-step Newton-Raphson approximation, sqrt(2)~=1.414216
            x = FXnum(577, augfamily) / 408
            while True:
                # Apply Newton-Raphson iteration to f(x)=2/(x*x)-1:
                delta = (x * (2 - x * x)) >> 2
                x += delta
                if abs(delta.scaledval) <= 1:
                    break
            self._sqrt2 = FXnum(x, self)
        return self._sqrt2

    @property
    def unity(self):
        """The multiplicative identity."""
        return FXnum(1, self)

    @property
    def zero(self):
        """The additive identity."""
        return FXnum(0, self)

    def __hash__(self):
        return hash(self.fraction_bits)

    def __repr__(self):
        return 'FXfamily(n_bits={}, n_intbits={})'.format(self.fraction_bits,
                                                          self.integer_bits)

    def __eq__(self, other):
        try:
            return (self.fraction_bits == other.fraction_bits
                    and self.integer_bits == other.integer_bits)
        except AttributeError:
            return false

    def __ne__(self, other):
        try:
            return (self.fraction_bits != other.fraction_bits
                    or self.integer_bits != other.integer_bits)
        except AttributeError:
            return true

    def __call__(self, val):
        """Create a fixed-point number within this family."""
        return FXnum(val, family=self)

    def from2c(self, n, n_intbits=None):
        """Create fixed-point number from two's complement number

        The supplied integer is assumed to represent all the bits
        covered by the integer and fractional bits of this FXfamily.
        """
        try:
            m = self.scale << (n_intbits if n_intbits is not None
                                         else self.integer_bits)
        except:
            raise FXfamilyError("Two's complement requires known number"
                                " of integer bits")

        if n < 0 or n >= m:
            raise FXdomainError("Two's complement number outside range"
                                " [0, 0x{:x})".format(m))

        if n < (m >> 1):
            scaledval = n
        else:
            scaledval = n - m

        return FXnum._rawbuild(self, scaledval)

    def convert(self, other, other_val):
        """Convert number from different number of fraction-bits"""
        bit_inc = self.fraction_bits - other.fraction_bits
        if bit_inc == 0:
            return other_val
        elif bit_inc > 0:
            new_val = other_val << bit_inc
            if other_val > 0:
                new_val |= 1 << (bit_inc - 1)
            else:
                new_val |= ((1 << (bit_inc -1)) - 1)
            return new_val
        else:
            # Safest approach is to truncate bits, rather than rounding:
            return (other_val >> -bit_inc)

    def augment(self, opcount=None):
        """Construct new FXfamily with enhanced resolution.

        The returned FXfamily will have an increased number of fractional bits,
        sufficient to accommodate the worst-case accumulation of 1-LSB errors
        over the specified number of operations. If the supplied
        operation-count is None, then this defaults to
        the existing number of fractional digits.
        """

        nb = opcount if opcount is not None else self.fraction_bits
        augbits = 4
        while nb > 0:
            augbits += 1
            nb >>= 1

        return FXfamily(self.fraction_bits + augbits)
# ^^^ class FXfamily ^^^

_defaultFamily = FXfamily()


####
# Exceptions
#

class FXexception(ArithmeticError):
    """Base-class of exceptions generated by SPFPM operations"""

class FXdomainError(FXexception):
    """Signal that input argument of mathematical function is unsuitable"""

class FXoverflowError(FXexception):
    """Signal that value has overflowed its most-significant bit"""

class FXfamilyError(FXexception, TypeError):
    """Signal that family-types of FXnums in binary operation are mismatched"""

class FXbrokenError(FXexception):
    """Signal some form of internal error, e.g. broken logic"""



class FXnum:
    """Representation of a binary fixed-point real number."""

    __slots__ = ('family', 'scaledval')

    def __init__(self, val=0, family=_defaultFamily, **kwargs):
        self.family = family
        converter = family.convert
        try:
            # Assume that val is similar to FXnum:
            self.scaledval = converter(val.family, val.scaledval)
        except AttributeError:
            if 'scaled_value' in kwargs:
                sv = kwargs['scaled_value']
            elif isinstance(val, float):
                tmpfam = FXfamily(family.fraction_bits + 1)
                (n, d) = val.as_integer_ratio()
                sv = ((tmpfam(n) / d).scaledval + 1) >> 1
            else:
                sv = int(round(val * family.scale))
                # 'int' casting improves compatibility with Python-2.7
            self.scaledval = sv
        self.family.validate(self.scaledval)

    @classmethod
    def _rawbuild(cls, fam, sv):
        """Shortcut for creating new FXnum instance, for internal use only."""
        num = object.__new__(cls)
        fam.validate(sv)
        num.family = fam
        num.scaledval = sv
        return num

    def __hash__(self):
        return hash(self.scaledval) ^ hash(self.family)

    def __repr__(self):
        """Create unambiguous string representation of self"""
        return 'FXnum(family={}, scaled_value={})'.format(self.family,
                                                          self.scaledval)

    # Conversion operations:
    def __int__(self):
        """Cast to integer"""
        if self.scaledval >= 0:
            return int(self.scaledval // self.family.scale)
        else:
            return int((self.scaledval + self.family.scale - 1) // self.family.scale)

    def __float__(self):
        """Cast to floating-point"""
        sv_bits = self.scaledval.bit_length()
        thresh = 970
        if sv_bits < thresh and self.family.fraction_bits < thresh:
            return float(self.scaledval) / float(self.family.scale)
        else:
            num_shift = max(sv_bits - thresh, 0)
            dnm_shift = max(self.family.fraction_bits - thresh, 0)
            x = (float(self.scaledval >> num_shift)
                    / float(self.family.scale >> dnm_shift))
            if num_shift > dnm_shift:
                s = 1 << (num_shift - dnm_shift)
            else:
                s = 1.0 / (1 << (dnm_shift - num_shift))
            return x * s

    def _CastOrFail_(self, other):
        """Turn number into FXnum or check that it is in same family"""
        try:
            # Binary operations must involve members of same family
            if self.family != other.family:
                raise FXfamilyError(1)
        except AttributeError:
            # Automatic casting from types other than FXnum is allowed:
            other = FXnum(other, self.family)
        return other

    # Unary arithmetic operations:
    def __abs__(self):
        """Modulus"""
        if self.scaledval < 0:
            return -self
        else:
            return self

    def __neg__(self):
        """Change sign"""
        return FXnum._rawbuild(self.family, -self.scaledval)

    def __pos__(self):
        """Identity operation"""
        return self

    # Arithmetic comparison tests:
    def __eq__(self, other):
        """Equality test"""
        other = self._CastOrFail_(other)
        return self.scaledval == other.scaledval and self.family == other.family

    def __ne__(self, other):
        """Inequality test"""
        other = self._CastOrFail_(other)
        return self.scaledval != other.scaledval

    def __ge__(self, other):
        """Greater-or-equal test"""
        other = self._CastOrFail_(other)
        return self.scaledval >= other.scaledval

    def __gt__(self, other):
        """Greater-than test"""
        other = self._CastOrFail_(other)
        return self.scaledval > other.scaledval

    def __le__(self, other):
        """Less-or-equal test"""
        other = self._CastOrFail_(other)
        return self.scaledval <= other.scaledval

    def __lt__(self, other):
        """Greater-than test"""
        other = self._CastOrFail_(other)
        return self.scaledval < other.scaledval

    def __bool__(self):
        """Test for truth/falsehood"""
        return (self.scaledval != 0)

    def __nonzero__(self):
        """Test for non-zero"""
        return (self.scaledval != 0)

    # Arithmetic combinations:
    def __add__(self, other):
        """Add another number"""
        other = self._CastOrFail_(other)
        return FXnum._rawbuild(self.family,
                               (self.scaledval + other.scaledval))

    def __radd__(self, other):
        return FXnum(other, self.family) + self

    def __sub__(self, other):
        """Subtract another number"""
        other = self._CastOrFail_(other)
        return FXnum._rawbuild(self.family,
                               (self.scaledval - other.scaledval))

    def __rsub__(self, other):
        return FXnum(other, self.family) - self

    def __mul__(self, other):
        """Multiply by another number"""
        other = self._CastOrFail_(other)
        return FXnum._rawbuild(self.family,
                               ((self.scaledval * other.scaledval
                                            + self.family._roundup)
                                        // self.family.scale))

    def __rmul__(self, other):
        return FXnum(other, self.family) * self

    def __lshift__(self, shift):
        return FXnum._rawbuild(self.family,
                               (self.scaledval << shift))

    def __rshift__(self, shift):
        return FXnum._rawbuild(self.family,
                               (self.scaledval >> shift))

    def __truediv__(self, other):
        """Divide by another number (without truncation)"""
        other = self._CastOrFail_(other)
        return FXnum._rawbuild(self.family,
                               ((self.scaledval * self.family.scale
                                        + self.family._roundup)
                                    // other.scaledval))
    __div__ = __truediv__

    def __rtruediv__(self, other):
        return FXnum(other, self.family) / self
    __rdiv__ = __rtruediv__

    # Printing/converstion routines:
    def __str__(self):
        """Convert number (as decimal) into string"""
        return self.toDecimalString()

    def toDecimalString(self, precision=None, round10=False):
        """Convert number (as decimal) into string

        precision -     The maximum number of digits after the decimal point.
                        If this is None, then a heuristic estimate is made
                        of the indicative base-10 precision, which may be
                        significantly less than the number of decimal digits
                        required to fully represent the lowest-order
                        fractional bit. Set this to self.family.fractional_bits
                        to guarantee that all non-zero decimal digits are shown.
        round10 -       Round last decimal digit of fractional part,
                        by adding 0.5/10^precision.
        """
        # Despite rebinding costs, list+join idiom appears slower here
        # than string concatenation building 'rep' from successive digits
        famScale = self.family.scale
        if precision is None or not isinstance(precision, int):
            precision = round(self.family._pseudo_precision())

        val = self.scaledval
        rep = ''
        if self.scaledval < 0:
            rep = '-'
            val *= -1

        if round10:
            # Round (decimal) fractional part by adding half of last-digit:
            decimalScale = 10 ** precision
            val = (val * decimalScale + famScale // 2) // decimalScale

        whole = val // famScale
        frac = val - whole * famScale
        rep += str(whole)

        if frac != 0 and precision > 0:
            rep += '.'
            idx = 0
            while idx < precision and frac != 0:
                frac *= 10
                q = frac // famScale
                rep += str(q)
                frac -= q * famScale
                idx += 1
        return rep

    def toBinaryString(self, logBase=1, twosComp=True):
        """Convert number into string in base 2/4/8/16

        logBase -       log_2 of the number base for printing.
                        (e.g. 1 for binary, 3 for octal, 4 for hexadecimal).
                        This must be no greater than 4.
        twosComp -      Whether to convert negative numbers into
                        twos-complement form. If this is False,
                        then negative numbers are simply prefixed
                        by a minus sign.

        Note that when negative numbers are converted to twos-complement form,
        this may involve estimating how many bits are needed
        to contain the integer part if this is not specified by the FXfamily.
        """
        if not isinstance(logBase, int) or logBase > 4 or logBase < 1:
            raise ValueError('Cannot convert to base greater than 16')

        absSelf, prefix = self, ''
        if self.scaledval < 0 and not twosComp:
            absSelf, prefix = -self, '-'
        (bits, intDigits, fracDigits) = absSelf._toTwosComplement(logBase)

        digits = []
        mask = (1 << logBase) - 1
        for dig in range(intDigits+fracDigits):
            digits.append('{:1x}'.format(bits & mask))
            bits >>= logBase
        digits = ''.join(reversed(digits))

        return prefix + digits[:-fracDigits] + '.' + digits[-fracDigits:]

    def _toTwosComplement(self, logBase=1):
        """Convert binary representation to twos-complement for printing.

        This will convert negative numbers into their twos-complement form,
        and automatically guess the number of digits required to represent
        the integer part of the invoking number. The returned bit-pattern
        is aligned so that it has a whole number of digits (in base 1<<logBase)
        both before and after the binary/octal/hexadecimal-point.
        """
        fracDigits = (self.family.resolution + logBase - 1) // logBase
        bitPattern = self.scaledval

        if self.family.integer_bits is not None:
            intDigits = (self.family.integer_bits + logBase - 1) // logBase
        else:
            intDigits = 1
            intPart = self.scaledval >> self.family.resolution
            if intPart >= 0:
                while intPart >= (1 << (intDigits * logBase)):
                    intDigits += 1
            else:
                while (1 << (intDigits * logBase - 1)) + intPart < 0:
                    intDigits += 1

        if bitPattern < 0:
            bitPattern += 1 << (intDigits * logBase + self.family.resolution)

        bitPattern <<= (fracDigits * logBase - self.family.resolution)

        return (bitPattern, intDigits, fracDigits)

    # Mathematical functions:
    def __pow__(self, other, modulus=None):
        """Evaluate self ^ other"""
        assert modulus is None
        if self == 0:
            if other > 0:
                return self.family.zero
            else:
                raise FXdomainError

        ipwr = int(other)
        rmdr = (other - ipwr)
        if rmdr == 0:
            frac = self.family.unity
        else:
            frac = (rmdr * self.log()).exp()
        return self.intpower(ipwr) * frac

    def __rpow__(self, other):
        return FXnum(other, self.family) ** self

    def intpower(self, pwr):
        """Compute integer power by repeated squaring"""
        assert isinstance(pwr, int)
        invert = False
        if pwr < 0:
            pwr *= -1
            invert = True
        result = self.family.unity
        term = self
        while True:
            if pwr & 1:
                result *= term
            pwr >>= 1
            if not pwr:
                break
            term *= term
        if invert:
            result = FXnum(1, self.family) / result
        return result

    def sqrt(self):
        """Compute square-root of given number."""
        if self.scaledval < 0:
            raise FXdomainError
        elif self.scaledval == 0:
            return self

        # Refine crude initial approximation by Newton iteration:
        rt = self._init_sqrt()
        while True:
            delta = (rt - self / rt) >> 1
            rt -= delta
            if delta.scaledval == 0: break
        return rt

    def _init_sqrt(self):
        """Compute initial value for iterative computation of sqrt(self)"""
        rt = FXnum(family=self.family,
                   scaled_value=(1 << (self.family.fraction_bits // 2)))
        val = self.scaledval
        while val > 1:
            val >>= 2
            rt.scaledval <<= 1
        return rt

    def exp(self):
        """Compute exponential of given number"""
        pwr = int(self)
        return (self - pwr)._rawexp() * (self.family.exp1 ** pwr)

    def _rawexp(self):
        """Brute-force exponential of given number (assumed smallish)"""
        ex = self.family.unity
        term = self.family.unity
        idx = 1
        while True:
            term *= self / idx
            ex += term
            idx += 1
            if term.scaledval == 0: break
        return ex

    def log(self):
        """Compute (natural) logarithm of given number"""
        if self == 1:
            return FXnum(0, self.family)
        (val, count) = self._log_align()
        return val._rawlog() + count * self.family.log2

    def log2(self):
        """Compute base-2 logarithm of given number"""
        if self == 1:
            return FXnum(0, self.family)
        (val, count) = self._log_align()
        return val._rawlog() / self.family.log2 + count

    def _log_align(self):
        """Extract powers of two to create x * 2^n with x close to unity"""
        if self.scaledval <= 0:
            raise FXdomainError

        uprthresh = FXnum(13, self.family) >> 3 # biased to preserve low-order bits
        lwrthresh = uprthresh / 2

        count = self.scaledval.bit_length() - self.family.fraction_bits - 1
        if count == 0:
            val = self
        elif count < 0:
            val = self << (-count)
        else:
            val = self / (1 << count)

        while val > uprthresh:
            val /= 2
            count += 1
        while val < lwrthresh:
            val *= 2
            count -= 1
        return (val, count)

    def _rawlog(self, isDelta=False):
        """Compute (natural) logarithm of given number (assumed close to 1)"""
        lg = self.family.zero
        if isDelta:
            z = self / (self + 2)
        else:
            z = (self - 1) / (self + 1)
        z2 = z * z
        term = 2 * z
        idx = 1
        while True:
            lg += term / idx
            term *= z2
            idx += 2
            if term.scaledval == 0: break
        return lg

    def sin(self):
        """Compute sine of given number (as angle in radians)"""
        (ang, idx, reflect) = self._angnorm()
        idx = idx % 4
        if idx == 0: sn = ang._rawQsine(False)
        elif idx == 1: sn = ang._rawQsine(True)
        elif idx == 2: sn = -ang._rawQsine(False)
        elif idx == 3: sn = -ang._rawQsine(True)
        else: raise FXbrokenError
        if reflect: sn *= -1
        return sn

    def asin(self):
        """Compute inverse sine of given number"""
        arg = self
        reflect = False
        if self < 0:
            arg *= -1
            reflect = True
        if arg <= 0.5:
            asn = arg._rawarcsin()
        else:
            # apply 1-cos2t transformation:
            cs2 = (1 - arg) / 2
            if cs2 < 0: raise FXdomainError
            asn = self.family.pi / 2 - 2 * cs2.sqrt()._rawarcsin()
        if reflect: asn *= -1
        return asn

    def _rawarcsin(self):
        """Brute-force inverse-sine of given number.

        This requires roughly as many integer bits as fractional bits,
        in order to accommodate (2n!)/(n!n!).
        """
        asn = FXnum(1, self.family)
        x2 = self * self
        x2n = x2
        half = self.family.unity / 2
        nCn = 2     # (2n)! / ((n!)^2)
        idx = 1
        while True:
            delta = x2n * ((FXnum(nCn, self.family) >> (2 * idx))
                                / (2 * idx + 1))
            asn += delta
            if delta.scaledval == 0: break
            idx += 1
            x2n *= x2
            nCn = (nCn * 2 * (2 * idx - 1)) // idx
        return self * asn

    def cos(self):
        """Compute cosine of given number (as angle in radians)"""
        (ang, idx, reflect) = self._angnorm()
        idx = idx % 4
        if idx == 0: cs = ang._rawQsine(True)
        elif idx == 1: cs = -ang._rawQsine(False)
        elif idx == 2: cs = -ang._rawQsine(True)
        elif idx == 3: cs = ang._rawQsine(False)
        else: raise FXbrokenError
        return cs

    def acos(self):
        """Compute inverse cosine of given number"""
        arg = self
        reflect = False
        if self < 0:
            arg *= -1
            reflect = True
        if arg <= 0.5:
            acs = self.family.pi / 2 - arg._rawarcsin()
        else:
            # apply 1-cos2t transformation:
            sn2 = (1 - arg) / 2
            if sn2 < 0: raise FXdomainError
            acs = 2 * (sn2.sqrt())._rawarcsin()
        if reflect: acs = self.family.pi - acs
        return acs

    def sincos(self):
        """Compute sine & cosine of given number (as angle in radians)"""
        (ang, idx, reflect) = self._angnorm()
        osn = ang._rawQsine(False)
        ocs = ang._rawQsine(True)
        # transform according to sin(ang+offset), cos(ang+offset):
        idx = idx % 4
        if idx == 0: (sn, cs) = (osn, ocs)
        elif idx == 1: (sn, cs) = (ocs, -osn)
        elif idx == 2: (sn, cs) = (-osn, -ocs)
        elif idx == 3: (sn, cs) = (-ocs, osn)
        else: raise FXbrokenError
        if reflect: sn *= -1
        return (sn, cs)

    def _angnorm(self):
        """Helper function for reducing angle modulo 2.Pi"""
        reflect = False
        ang = self
        if ang < 0:
            ang *= -1
            reflect = True
        # Find nearest multiple of pi/2:
        halfpi = self.family.pi / 2
        idx = int(ang / halfpi + 0.5)
        ang -= idx * halfpi
        return (ang, idx, reflect)

    def _rawQsine(self, doCos=False, doHyp=False):
        """Helper function for brute-force calculation of sine & cosine"""
        sn = self.family.zero
        if doHyp:
            x2 = self * self
        else:
            x2 = -self * self
        term = self.family.unity
        if doCos: idx = 1
        else: idx = 2
        while True:
            sn += term
            term *= x2 / (idx * (idx + 1))
            idx += 2
            if term.scaledval == 0: break
        if doCos: return sn
        else: return self * sn

    def tan(self):
        """Compute tangent of given number (as angle in radians)"""
        (sn, cs) = self.sincos()
        return sn / cs

    def atan(self):
        """Compute inverse-tangent of given number (as angle in radians)"""
        reflect = False
        recip = False
        double = False
        tan = self
        if tan < 0:
            tan *= -1
            reflect = True
        if tan > 1:
            tan = 1 / tan
            recip = True
        if tan > 0.414:
            tan = ((1 + tan * tan).sqrt() - 1) / tan
            double = True
        ang = tan._rawarctan()
        if double:
            ang *= 2
        if recip:
            ang = self.family.pi / 2 - ang
        if reflect:
            ang *= -1
        return ang

    def _rawarctan(self):
        """Brute-force inverse-tangent of given number (for |self|<1)."""
        atn = 1
        x2 = self * self
        omx2 = 1 - x2
        opx2 = 1 + x2
        x4 = x2 * x2
        term = x2
        idx = 1
        while True:
            # Combine pair of successive terms with opposite signs:
            delta = term * (4 * idx * omx2 + opx2) / (16 * idx * idx - 1)
            atn -= delta
            term *= x4
            idx += 1
            if delta.scaledval == 0: break
        return self * atn
# ^^^ class FXnum ^^^


if __name__ == "__main__":
    import doctest
    try:
        doctest.testmod()
    except TypeError:
        print("*** Problems running doctest module ***")

# vim: set ts=4 sw=4 et:

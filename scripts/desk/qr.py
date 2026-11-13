"""A small QR code encoder (byte mode, error correction level M, versions 1 to 10), enough for the
phone's link, drawn as SVG. It follows the QR standard (ISO/IEC 18004) the way Project Nayuki's
reference encoder lays it out; the tests read its codes back with OpenCV.
"""

# Error correction level M: codewords per block and blocks, by version.
ECC = [None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26]
BLOCKS = [None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5]
FORMAT_M = 0  # level M's two format bits
MAX_VERSION = 10


def raw_modules(ver):
    """How many modules of a version hold data (everything but the fixed patterns)."""
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def data_codewords(ver):
    return raw_modules(ver) // 8 - ECC[ver] * BLOCKS[ver]


# -- Reed-Solomon over GF(256) ------------------------------------------------------------------

def gf_multiply(x, y):
    z = 0
    for i in reversed(range(8)):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def rs_divisor(degree):
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            result[j] = gf_multiply(result[j], root)
            if j + 1 < degree:
                result[j] ^= result[j + 1]
        root = gf_multiply(root, 0x02)
    return result


def rs_remainder(data, divisor):
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= gf_multiply(coef, factor)
    return result


def with_ecc(data, ver):
    """The data codewords split into blocks, each with its error correction, interleaved."""
    blocks_n, ecc_len = BLOCKS[ver], ECC[ver]
    raw = raw_modules(ver) // 8
    short_n = blocks_n - raw % blocks_n
    short_len = raw // blocks_n
    divisor = rs_divisor(ecc_len)
    blocks, k = [], 0
    for i in range(blocks_n):
        part = data[k:k + short_len - ecc_len + (0 if i < short_n else 1)]
        k += len(part)
        ecc = rs_remainder(part, divisor)
        if i < short_n:
            part = part + [0]
        blocks.append(part + ecc)
    out = []
    for i in range(len(blocks[0])):
        for j, block in enumerate(blocks):
            if i != short_len - ecc_len or j >= short_n:
                out.append(block[i])
    return out


# -- the matrix ----------------------------------------------------------------------------------

class Matrix:
    def __init__(self, ver):
        self.ver = ver
        self.size = ver * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def put(self, x, y, dark):
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def patterns(self):
        size = self.size
        for i in range(size):
            self.put(6, i, i % 2 == 0)
            self.put(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (size - 4, 3), (3, size - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < size and 0 <= y < size:
                        self.put(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        spots = self.alignment_spots()
        last = len(spots) - 1
        for i, ax in enumerate(spots):
            for j, ay in enumerate(spots):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.put(ax + dx, ay + dy, max(abs(dx), abs(dy)) != 1)
        self.format_bits(0)
        self.version_bits()

    def alignment_spots(self):
        if self.ver == 1:
            return []
        n = self.ver // 7 + 2
        step = (self.ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
        return list(reversed([self.size - 7 - i * step for i in range(n - 1)] + [6]))

    def format_bits(self, mask):
        data = FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        size = self.size
        for i in range(6):
            self.put(8, i, bit(i))
        self.put(8, 7, bit(6))
        self.put(8, 8, bit(7))
        self.put(7, 8, bit(8))
        for i in range(9, 15):
            self.put(14 - i, 8, bit(i))
        for i in range(8):
            self.put(size - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.put(8, size - 15 + i, bit(i))
        self.put(8, size - 8, True)

    def version_bits(self):
        if self.ver < 7:
            return
        rem = self.ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = self.ver << 12 | rem
        for i in range(18):
            dark = (bits >> i) & 1 == 1
            a, b = self.size - 11 + i % 3, i // 3
            self.put(a, b, dark)
            self.put(b, a, dark)

    def codewords(self, data):
        size, i, right = self.size, 0, self.size - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(size):
                for j in range(2):
                    x = right - j
                    upward = (right + 1) & 2 == 0
                    y = size - 1 - vert if upward else vert
                    if not self.fixed[y][x] and i < len(data) * 8:
                        self.dark[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def mask(self, m):
        rules = (
            lambda x, y: (x + y) % 2 == 0,
            lambda x, y: y % 2 == 0,
            lambda x, y: x % 3 == 0,
            lambda x, y: (x + y) % 3 == 0,
            lambda x, y: (x // 3 + y // 2) % 2 == 0,
            lambda x, y: x * y % 2 + x * y % 3 == 0,
            lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
            lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0,
        )
        rule = rules[m]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fixed[y][x] and rule(x, y):
                    self.dark[y][x] = not self.dark[y][x]

    def penalty(self):
        """How hard the code is to read (the standard's four rules, simply counted)."""
        size, score = self.size, 0
        lines = ["".join("1" if d else "0" for d in row) for row in self.dark]
        lines += ["".join("1" if self.dark[y][x] else "0" for y in range(size)) for x in range(size)]
        for line in lines:
            run, last = 0, None
            for c in line + "x":
                if c == last:
                    run += 1
                    continue
                if run >= 5:
                    score += 3 + run - 5
                run, last = 1, c
            score += 40 * (line.count("10111010000") + line.count("00001011101"))
        for y in range(size - 1):
            for x in range(size - 1):
                c = self.dark[y][x]
                if c == self.dark[y][x + 1] == self.dark[y + 1][x] == self.dark[y + 1][x + 1]:
                    score += 3
        dark = sum(sum(row) for row in self.dark)
        total = size * size
        score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
        return score


def encode(text):
    """The QR code for `text`: a square list of rows, True for dark."""
    data = list(text.encode("utf-8"))
    for ver in range(1, MAX_VERSION + 1):
        count_bits = 8 if ver < 10 else 16
        if 4 + count_bits + 8 * len(data) <= data_codewords(ver) * 8:
            break
    else:
        raise ValueError("too long for a QR code here")
    bits = []

    def add(value, n):
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    add(0b0100, 4)
    add(len(data), count_bits)
    for b in data:
        add(b, 8)
    capacity = data_codewords(ver) * 8
    add(0, min(4, capacity - len(bits)))
    add(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < capacity:
        add(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]

    m = Matrix(ver)
    m.patterns()
    m.codewords(with_ecc(words, ver))
    best, best_score = 0, None
    for mask in range(8):
        m.mask(mask)
        m.format_bits(mask)
        score = m.penalty()
        if best_score is None or score < best_score:
            best, best_score = mask, score
        m.mask(mask)  # undo
    m.mask(best)
    m.format_bits(best)
    return m.dark


def svg(text, quiet=4):
    """The QR code for `text` as an SVG picture: black on white, with its quiet zone."""
    rows = encode(text)
    size = len(rows) + 2 * quiet
    path = "".join(f"M{x + quiet},{y + quiet}h1v1h-1z" for y, row in enumerate(rows) for x, dark in enumerate(row) if dark)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" shape-rendering="crispEdges">'
            f'<rect width="{size}" height="{size}" fill="#fff"/><path d="{path}" fill="#000"/></svg>')

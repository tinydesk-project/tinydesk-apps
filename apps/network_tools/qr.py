# qr.py - a small QR code encoder for MicroPython: byte mode, error
# correction level M, versions 1 to 10 (up to 213 bytes), the best of the
# eight masks. qr.encode(data) returns the matrix as a list of rows of
# True (dark) / False. Checked against the segno library on a PC.

# Per version (1..10), level M: (codewords in all, ec codewords per block,
# blocks in group 1, data codewords there, blocks in group 2, data there).
_M = (
    None,
    (26, 10, 1, 16, 0, 0),
    (44, 16, 1, 28, 0, 0),
    (70, 26, 1, 44, 0, 0),
    (100, 18, 2, 32, 0, 0),
    (134, 24, 2, 43, 0, 0),
    (172, 16, 4, 27, 0, 0),
    (196, 18, 4, 31, 0, 0),
    (242, 22, 2, 38, 2, 39),
    (292, 22, 3, 36, 2, 37),
    (346, 26, 4, 43, 1, 44),
)
_ALIGN = (None, (), (6, 18), (6, 22), (6, 26), (6, 30), (6, 34), (6, 22, 38), (6, 24, 42), (6, 26, 46), (6, 28, 50))

# GF(256) with the QR polynomial 0x11D.
_EXP = [0] * 512
_LOG = [0] * 256
_x = 1
for _i in range(255):
    _EXP[_i] = _x
    _LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _EXP[_i] = _EXP[_i - 255]


def _mul(a, b):
    return 0 if a == 0 or b == 0 else _EXP[_LOG[a] + _LOG[b]]


def _generator(n):
    g = [1]
    for i in range(n):
        nxt = [0] * (len(g) + 1)
        for j, c in enumerate(g):
            nxt[j] ^= c
            nxt[j + 1] ^= _mul(c, _EXP[i])
        g = nxt
    return g


def _ec(data, n):
    gen = _generator(n)
    rem = list(data) + [0] * n
    for i in range(len(data)):
        c = rem[i]
        if c:
            for j in range(1, len(gen)):
                rem[i + j] ^= _mul(gen[j], c)
    return rem[len(data):]


def _codewords(data, ver):
    total, ecn, b1, d1, b2, d2 = _M[ver]
    cap = b1 * d1 + b2 * d2
    bits = []

    def put(v, n):
        for i in range(n - 1, -1, -1):
            bits.append((v >> i) & 1)

    put(4, 4)   # byte mode
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    words = [int(''.join(str(b) for b in bits[i:i + 8]), 2) for i in range(0, len(bits), 8)]
    pad = 0xEC
    while len(words) < cap:
        words.append(pad)
        pad ^= 0xEC ^ 0x11
    blocks, ecs, at = [], [], 0
    for count, size in ((b1, d1), (b2, d2)):
        for _ in range(count):
            blk = words[at:at + size]
            at += size
            blocks.append(blk)
            ecs.append(_ec(blk, ecn))
    out = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ecn):
        for e in ecs:
            out.append(e[i])
    return out


def _base(ver):
    n = 17 + 4 * ver
    m = [[None] * n for _ in range(n)]

    def finder(r, c):
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                rr, cc = r + dr, c + dc
                if 0 <= rr < n and 0 <= cc < n:
                    ring = max(abs(dr - 3), abs(dc - 3))
                    m[rr][cc] = ring != 2 and ring != 4
    finder(0, 0)
    finder(0, n - 7)
    finder(n - 7, 0)
    for i in range(8, n - 8):
        m[6][i] = m[i][6] = i % 2 == 0
    pos = _ALIGN[ver]
    last = len(pos) - 1
    for i, r in enumerate(pos):
        for j, c in enumerate(pos):
            if (i, j) in ((0, 0), (0, last), (last, 0)):
                continue   # under a finder; those on the timing lines are drawn
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    m[r + dr][c + dc] = max(abs(dr), abs(dc)) != 1
    m[n - 8][8] = True   # the dark module
    # Reserve the format areas (written later) and version areas.
    for i in range(9):
        if m[8][i] is None:
            m[8][i] = False
        if m[i][8] is None:
            m[i][8] = False
    for i in range(8):
        if m[8][n - 1 - i] is None:
            m[8][n - 1 - i] = False
        if m[n - 1 - i][8] is None:
            m[n - 1 - i][8] = False
    if ver >= 7:
        rem = ver
        for _ in range(12):
            rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
        bits = ver << 12 | rem
        for i in range(18):
            b = (bits >> i) & 1 == 1
            a, c = i // 3, n - 11 + i % 3
            m[a][c] = b
            m[c][a] = b
    return m


def _place(m, words):
    n = len(m)
    fixed = [[v is not None for v in row] for row in m]
    bits = []
    for w in words:
        for i in range(7, -1, -1):
            bits.append((w >> i) & 1 == 1)
    k = 0
    right = n - 1
    upward = True
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            r = n - 1 - vert if upward else vert
            for c in (right, right - 1):
                if not fixed[r][c]:
                    m[r][c] = bits[k] if k < len(bits) else False
                    k += 1
        upward = not upward
        right -= 2
    return fixed


_MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


def _format(m, mask):
    n = len(m)
    data = 0 << 3 | mask   # level M is 00
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    bits = (data << 10 | rem) ^ 0x5412
    # Around the top-left finder: bits 0-5 down column 8, then 6-8 at the
    # corner, 9-14 along row 8 from the left.
    for i in range(6):
        m[i][8] = (bits >> i) & 1 == 1
    m[7][8] = (bits >> 6) & 1 == 1
    m[8][8] = (bits >> 7) & 1 == 1
    m[8][7] = (bits >> 8) & 1 == 1
    for i in range(9, 15):
        m[8][14 - i] = (bits >> i) & 1 == 1
    # The second copy: bits 0-7 along row 8 at the right, 8-14 up column 8 at
    # the bottom.
    for i in range(8):
        m[8][n - 1 - i] = (bits >> i) & 1 == 1
    for i in range(8, 15):
        m[n - 15 + i][8] = (bits >> i) & 1 == 1
    m[n - 8][8] = True


def _penalty(m):
    n = len(m)
    score = 0
    for lines in (m, [list(col) for col in zip(*m)]):
        for row in lines:
            run, prev = 0, None
            for v in row:
                if v == prev:
                    run += 1
                else:
                    if run >= 5:
                        score += run - 2
                    run, prev = 1, v
            if run >= 5:
                score += run - 2
            for i in range(n - 10):
                seg = row[i:i + 11]
                if seg == [True, False, True, True, True, False, True, False, False, False, False] or \
                        seg == [False, False, False, False, True, False, True, True, True, False, True]:
                    score += 40
    for r in range(n - 1):
        for c in range(n - 1):
            v = m[r][c]
            if v == m[r][c + 1] == m[r + 1][c] == m[r + 1][c + 1]:
                score += 3
    dark = sum(sum(1 for v in row if v) for row in m)
    score += abs(dark * 20 - n * n * 10) // (n * n) * 10
    return score


def encode(data):
    """The QR code of data (str or bytes) as rows of booleans (True: dark)."""
    if isinstance(data, str):
        data = data.encode()
    for ver in range(1, 11):
        total, ecn, b1, d1, b2, d2 = _M[ver]
        need = 4 + (8 if ver < 10 else 16) + 8 * len(data)
        if need <= (b1 * d1 + b2 * d2) * 8:
            break
    else:
        raise ValueError('too long for a QR code here (213 bytes at most)')
    words = _codewords(data, ver)
    best, best_score = None, None
    for mask in range(8):
        m = _base(ver)
        fixed = _place(m, words)
        f = _MASKS[mask]
        for r in range(len(m)):
            for c in range(len(m)):
                if not fixed[r][c] and f(r, c):
                    m[r][c] = not m[r][c]
        _format(m, mask)
        s = _penalty(m)
        if best_score is None or s < best_score:
            best, best_score = m, s
    return best

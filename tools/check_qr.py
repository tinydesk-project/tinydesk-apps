"""Check apps/network_tools/qr.py against the segno library (pip install
segno): every module of 300 random codes, versions 1 to 10, every mask.

segno adds a zero byte after data that ends on a byte boundary (the
standard does not; decoders stop at the terminator either way), so for this
check qr.py's data codewords are made the same way."""
import random
import string
import sys
from pathlib import Path

import segno

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'apps' / 'network_tools'))
import qr  # noqa: E402

_codewords = qr._codewords


def segno_like(data, ver):
    total, ecn, b1, d1, b2, d2 = qr._M[ver]
    cap = b1 * d1 + b2 * d2
    acc = []

    def put(v, n):
        for i in range(n - 1, -1, -1):
            acc.append((v >> i) & 1)

    put(4, 4)
    put(len(data), 8 if ver < 10 else 16)
    for b in data:
        put(b, 8)
    put(0, min(4, cap * 8 - len(acc)))
    if len(acc) % 8 == 0 and len(acc) // 8 < cap:
        acc += [0] * 8
    while len(acc) % 8:
        acc.append(0)
    words = [int(''.join(map(str, acc[i:i + 8])), 2) for i in range(0, len(acc), 8)][:cap]
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
            ecs.append(qr._ec(blk, ecn))
    out = []
    for i in range(max(len(b) for b in blocks)):
        for b in blocks:
            if i < len(b):
                out.append(b[i])
    for i in range(ecn):
        for e in ecs:
            out.append(e[i])
    return out


qr._codewords = segno_like
random.seed(7)
samples = ['WIFI:T:WPA;S:TinyDesk-5545;P:8tgkypkwq2;;', 'hello', 'x' * 213]
samples += [''.join(random.choice(string.printable[:94]) for _ in range(random.randint(1, 213))) for _ in range(300)]
bad = []
for s in samples:
    m = qr.encode(s)
    ver = (len(m) - 17) // 4
    if not any([[bool(v) for v in row] for row in
                segno.make(s.encode(), error='m', mode='byte', boost_error=False, mask=k, version=ver,
                           micro=False).matrix] == m for k in range(8)):
        bad.append((len(s), ver))
print('%d of %d codes match segno exactly' % (len(samples) - len(bad), len(samples)))
if bad:
    sys.exit('mismatches (length, version): %s' % bad[:20])

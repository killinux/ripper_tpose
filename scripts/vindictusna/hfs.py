r"""Vindictus (Mabinogi Heroes, Source engine) .hfs archives: catalogue and extraction through the game's own code.

    python hfs.py --catalog [--procs 8]            # scan every archive index -> <work>\catalog.pkl  (~15 min)
    python hfs.py --find <regex> [--limit 50]      # search the catalogue
    python hfs.py --get <dest> <path|re:regex> ... # extract files, keeping their game paths under <dest>
    python hfs.py --list <archive_00000.hfs>       # one archive's files

Game folder: VINDICTUS_DIR (default D:\vindictus\appdata\en-US, the NA client from the Nexon launcher; the CN client
E:\TCGameApps\cmh\zh-CN works the same).  Work folder: VINDICTUSNA_WORK (default E:\tools\vindictusna).

The client keeps its assets in hfs\<sha1>_<NNNNN>.hfs: one logical archive per sha1 name, the _00000 part holds the
header and the index, the higher parts continue the data.  The current format (v4) is encrypted and compressed;
rather than reimplementing it, Archive maps the game's bin\FileSystem_Stdio.dll into an emulator (hfs_emu.py) and
calls its own open / read functions: the file list comes from the index text the DLL produces while it opens the
archive, each file's bytes from its read path (decrypted and decompressed by the game code).  Read-only.
"""
import argparse
import collections
import os
import pickle
import re
import struct
import sys
import time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

GAME_DIR = os.environ.get('VINDICTUS_DIR', r'D:\vindictus\appdata\en-US')
HFS_DIR = os.path.join(GAME_DIR, 'hfs')
WORK = os.environ.get('VINDICTUSNA_WORK', r'E:\tools\vindictusna')
CATALOG = os.path.join(WORK, 'catalog.pkl')

# entry points in FileSystem_Stdio.dll (identical NA / CN build, see hfs_emu.py)
OPEN_ARCH = 0x100528A0   # archive::Open(out, &wstr_dir, &wstr_name, ...)
OPEN_FILE = 0x1005F480   # archive::OpenFile(out_stream, &wstr_name)  (thiscall, ecx = archive)
MK_PATH = 0x1008EA30     # builds the path object Open expects
DECRYPT_SITE = 0x100AEB49  # the per-block decrypt call: its output buffers are the index text
READ_VOFS = 9 * 4        # stream vtable slot of Read(buf, n)


def parse_index(pt):
    """index text -> [(name, fields)]; record = i32 name length, UTF-16 name, 7 x u32 (fields[3] = file size),
    16-byte hash, 2 x u32"""
    ents, p = [], 0
    while p < len(pt) - 60:
        nl = struct.unpack_from('<i', pt, p)[0]
        if not 0 < nl < 128:
            break
        name = pt[p + 4:p + 4 + 2 * nl].decode('utf-16-le', 'replace')
        u = struct.unpack_from('<7I', pt, p + 4 + 2 * nl)
        ents.append((name, u))
        p += 4 + 2 * nl + 52
    return ents


class Archive:
    """One logical archive (path of its _00000 part).  .ents = [(name, fields)], read(name, size) -> bytes."""

    def __init__(self, path):
        from hfs_emu import Emu, DLL
        from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
        from unicorn.x86_const import UC_X86_REG_EBP, UC_X86_REG_ESP
        self.path = os.path.normpath(path)
        dll = os.path.join(os.path.dirname(os.path.dirname(self.path)), 'bin', 'FileSystem_Stdio.dll')
        self.emu = emu = Emu(dll=dll if os.path.exists(dll) else DLL, verbose=0)
        uc = emu.uc
        run = {'end': None}
        calls, pending, hooked = [], {}, set()

        def on_view(uc, access, addr, size, value, user):
            for base, n, p in emu.views:
                if base <= addr < base + n + 0x1000:
                    off = addr - base
                    run['end'] = off + size if run['end'] != off else run['end'] + size

        def on_setup(uc, addr, size, user):
            ebp = uc.reg_read(UC_X86_REG_EBP)
            a = [emu.r32(ebp + 8 + 4 * i) for i in range(8)]
            rec = {'len': a[2], 'buf': a[0], 'ebp': ebp, 'off': (run['end'] - a[2]) if run['end'] is not None else None}
            calls.append(rec)
            ret = emu.r32(ebp + 4)
            pending.setdefault(ret, []).append(rec)
            if ret not in hooked:
                hooked.add(ret)
                uc.hook_add(UC_HOOK_CODE, on_ret, begin=ret, end=ret)

        def on_ret(uc, addr, size, user):
            esp = uc.reg_read(UC_X86_REG_ESP)
            for rec in list(pending.get(addr, [])):
                if esp > rec['ebp']:
                    rec['pt'] = bytes(uc.mem_read(rec['buf'], rec['len']))
                    pending[addr].remove(rec)

        hv = uc.hook_add(UC_HOOK_MEM_READ, on_view, begin=Emu.FILEVIEW, end=Emu.FILEVIEW + 0x10000000)
        hs = uc.hook_add(UC_HOOK_CODE, on_setup, begin=DECRYPT_SITE, end=DECRYPT_SITE)
        out = emu.alloc(16)
        a1 = emu.make_wstring('')
        a2 = emu.alloc(0x200)
        emu.call(MK_PATH, [a2, emu.make_wstring(self.path)])
        emu.call(OPEN_ARCH, [out, a1, a2, 0, 0, 0, 0], count=800_000_000)
        self.obj = emu.r32(out)
        if not self.obj:
            raise RuntimeError('archive open failed: %s' % path)
        # the index text = every decrypted block after the first (that one is the 64-byte archive header)
        idx = [c for c in calls[1:] if 'pt' in c and c['off'] is not None]
        self.ents = []
        if idx:
            base = idx[0]['off']
            pt = bytearray(max(c['off'] + c['len'] for c in idx) - base)
            for c in idx:
                o = c['off'] - base
                if 0 <= o <= len(pt) - c['len']:
                    pt[o:o + c['len']] = c['pt']
            self.ents = parse_index(bytes(pt))
        uc.hook_del(hv)
        uc.hook_del(hs)

    def read(self, name, size):
        emu = self.emu
        sout = emu.alloc(16)
        emu.call(OPEN_FILE, [sout, emu.make_wstring(name)], ecx=self.obj, count=300_000_000)
        stream = emu.r32(sout)
        if not stream:
            return None
        buf = emu.alloc(size + 64)
        vt = emu.r32(stream)
        got = emu.call(emu.r32(vt + READ_VOFS), [buf, size], ecx=stream, count=800_000_000)
        return bytes(emu.uc.mem_read(buf, min(got, size)))


# ------------------------------------------------------------------------------------------------ catalogue
def _scan(job):
    wid, files = job
    out = []
    t0 = time.time()
    for i, fn in enumerate(files):
        try:
            ar = Archive(os.path.join(HFS_DIR, fn))
            out.append((fn, [(n, u[3]) for n, u in ar.ents]))
            ar.emu = None
        except Exception as ex:          # noqa: BLE001 - one bad archive must not stop the scan
            out.append((fn, 'ERR:' + repr(ex)[:80]))
        if i % 100 == 0:
            print('[w%d] %d/%d  %.0fs' % (wid, i, len(files), time.time() - t0), flush=True)
    return out


def build_catalog(procs=8):
    names = sorted(f for f in os.listdir(HFS_DIR) if f.lower().endswith('_00000.hfs'))
    slices = [(w, names[w::procs]) for w in range(procs)]
    print('archives %d, %d processes' % (len(names), procs), flush=True)
    catalog, byname, errors = {}, {}, []
    with Pool(procs) as pool:
        for rows in pool.imap_unordered(_scan, slices):
            for fn, ents in rows:
                if isinstance(ents, str):
                    errors.append((fn, ents))
                    continue
                catalog[fn] = ents
                for n, sz in ents:
                    byname[n] = (fn, sz)
    os.makedirs(WORK, exist_ok=True)
    stamp = {f: os.path.getsize(os.path.join(HFS_DIR, f)) for f in names}
    pickle.dump({'catalog': catalog, 'byname': byname, 'errors': errors, 'game_dir': GAME_DIR, 'stamp': stamp},
                open(CATALOG, 'wb'))
    print('catalogue: %d archives, %d files, %d errors -> %s' % (len(catalog), len(byname), len(errors), CATALOG))
    return byname


_BY = None


def catalog():
    """name -> (archive _00000 file, size); names keep the game's case, look up through lower()"""
    global _BY
    if _BY is None:
        if not os.path.exists(CATALOG):
            raise SystemExit('no catalogue yet: python hfs.py --catalog')
        _BY = pickle.load(open(CATALOG, 'rb'))['byname']
    return _BY


def lower_index():
    return {n.lower(): n for n in catalog()}


def _extract(job):
    root, arch, names = job
    ar = Archive(os.path.join(HFS_DIR, arch))
    size = dict((n, u[3]) for n, u in ar.ents)
    done = []
    for n in names:
        data = ar.read(n, size[n])
        dst = os.path.join(root, n.replace('/', os.sep))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(data or b'')
        done.append((n, bool(data) and len(data) == size[n]))
    ar.emu = None
    return done


def fetch(root, names, procs=6, quiet=False):
    """Extract catalogue names (game spelling) into root/<game path>; files already there are skipped.
    Returns the number of short / failed reads."""
    by = catalog()
    per = collections.defaultdict(list)
    for n in names:
        if not os.path.exists(os.path.join(root, n.replace('/', os.sep))):
            per[by[n][0]].append(n)
    jobs = [(root, a, ns) for a, ns in per.items()]
    if not jobs:
        return 0
    if not quiet:
        print('extract %d files from %d archives' % (sum(len(j[2]) for j in jobs), len(jobs)), flush=True)
    bad = 0
    if len(jobs) == 1 or procs <= 1:
        results = map(_extract, jobs)
        for r in results:
            bad += sum(not ok for _n, ok in r)
    else:
        with Pool(min(procs, len(jobs))) as pool:
            for r in pool.imap_unordered(_extract, jobs):
                bad += sum(not ok for _n, ok in r)
    if bad:
        print('  %d files read short' % bad)
    return bad


def resolve(specs):
    """exact paths (any case) or 're:<regex>' -> catalogue names"""
    low = lower_index()
    out = set()
    for s in specs:
        if s.startswith('re:'):
            rx = re.compile(s[3:], re.I)
            out.update(n for n in catalog() if rx.search(n))
        elif s.lower().replace('\\', '/') in low:
            out.add(low[s.lower().replace('\\', '/')])
        else:
            print('not in the catalogue:', s)
    return sorted(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--catalog', action='store_true')
    ap.add_argument('--procs', type=int, default=8)
    ap.add_argument('--find')
    ap.add_argument('--limit', type=int, default=50)
    ap.add_argument('--get', nargs='+', metavar=('DEST', 'PATH'))
    ap.add_argument('--list')
    a = ap.parse_args()
    if a.catalog:
        build_catalog(a.procs)
    elif a.find:
        rx = re.compile(a.find, re.I)
        hits = sorted(n for n in catalog() if rx.search(n))
        for n in hits[:a.limit]:
            print('%-90s %10d' % (n, catalog()[n][1]))
        print('%d matches' % len(hits))
    elif a.get:
        names = resolve(a.get[1:])
        fetch(a.get[0], names, a.procs)
        print('%d files under %s' % (len(names), a.get[0]))
    elif a.list:
        ar = Archive(a.list)
        for n, u in ar.ents:
            print('%-90s %10d' % (n, u[3]))
    else:
        ap.print_help()


if __name__ == '__main__':
    main()

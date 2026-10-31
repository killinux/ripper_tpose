r"""Unicorn harness for the game's own 32-bit bin\FileSystem_Stdio.dll (Vindictus / Mabinogi Heroes, Source engine).

The .hfs archives of the current clients (NA and CN, format v4) are read by the game's own archive code: this file maps
the DLL into a Unicorn x86 emulator, gives it the handful of Win32 / tier0 imports it needs (file reads, memory,
locks) and lets hfs.py call its open / read functions.  Nothing of the archive format is reimplemented here.
The NA and CN clients ship the same DLL (sha1 8c84dca5c726d66daa98d1375420baada27373a7, 2026-09), so the function
addresses in hfs.py hold for both.

The DLL is taken from VINDICTUS_DIR (default D:\vindictus\appdata\en-US, the NA client) or passed to Emu(dll=...).
"""
import os
import re
import struct
import sys

import pefile
from unicorn import Uc, UcError, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_UNMAPPED
from unicorn.x86_const import *

GAME_DIR = os.environ.get('VINDICTUS_DIR', r'D:\vindictus\appdata\en-US')
DLL = os.path.join(GAME_DIR, 'bin', 'FileSystem_Stdio.dll')


def align(x, a=0x1000):
    return (x + a - 1) & ~(a - 1)


class Stop(Exception):
    pass


class Emu:
    STUB = 0x7E000000
    HEAP = 0x30000000
    HEAP_SIZE = 0x30000000
    STACK = 0x00100000
    STACK_SIZE = 0x00400000
    TEB = 0x7FFD0000
    FILEVIEW = 0x60000000
    RET_MAGIC = 0x7E1FFFF0

    def __init__(self, dll=DLL, verbose=True):
        self.verbose = verbose
        pe = self.pe = pefile.PE(dll)
        raw = open(dll, 'rb').read()
        self.base = base = pe.OPTIONAL_HEADER.ImageBase
        uc = self.uc = Uc(UC_ARCH_X86, UC_MODE_32)
        uc.mem_map(base, align(pe.OPTIONAL_HEADER.SizeOfImage))
        uc.mem_write(base, raw[:pe.OPTIONAL_HEADER.SizeOfHeaders])
        for s in pe.sections:
            d = raw[s.PointerToRawData:s.PointerToRawData + s.SizeOfRawData]
            if s.Misc_VirtualSize and s.Misc_VirtualSize < len(d):
                d = d[:s.Misc_VirtualSize]
            uc.mem_write(base + s.VirtualAddress, d)
        uc.mem_map(self.HEAP, self.HEAP_SIZE)
        self.sizes = {}
        self.heap_top = self.HEAP + 0x1000
        uc.mem_map(self.STACK, self.STACK_SIZE)
        uc.mem_map(self.TEB, 0x10000)
        uc.mem_map(self.STUB, 0x200000)
        uc.mem_write(self.STUB, b'\xc3' * 0x200000)
        # TEB: SEH head, stack limits, self pointer
        uc.mem_write(self.TEB, struct.pack('<IIII', 0xFFFFFFFF, self.STACK + self.STACK_SIZE, self.STACK, 0))
        uc.mem_write(self.TEB + 0x18, struct.pack('<I', self.TEB))
        self._gdt()
        self.stubs = {}
        self.nstub = 0
        self.handles = {}
        self.fpos = {}
        self.file_reads = []
        self.next_handle = 0x100
        self.views = []
        self.view_top = self.FILEVIEW
        self.calls_log = []
        self._imports()
        uc.hook_add(UC_HOOK_CODE, self._on_stub, begin=self.STUB, end=self.STUB + 0x200000 - 1)
        uc.hook_add(UC_HOOK_MEM_UNMAPPED, self._on_unmapped)

    def _gdt(self):
        """flat GDT with an FS segment over the fake TEB (Unicorn has no FS_BASE in 32-bit mode)"""
        def entry(base, limit, access, flags):
            e = limit & 0xFFFF
            e |= (base & 0xFFFFFF) << 16
            e |= (access & 0xFF) << 40
            e |= ((limit >> 16) & 0xF) << 48
            e |= (flags & 0xF) << 52
            e |= ((base >> 24) & 0xFF) << 56
            return struct.pack('<Q', e)
        GDT = 0x7FFE0000
        self.uc.mem_map(GDT, 0x1000)
        # 2 = flat ring-0 data (4 KB granular, 32-bit) for SS/DS/ES/GS, 15 = FS over the TEB
        self.uc.mem_write(GDT + 2 * 8, entry(0, 0xFFFFF, 0x92, 0xC))
        self.uc.mem_write(GDT + 15 * 8, entry(self.TEB, 0xFFF, 0x92, 0x4))
        self.uc.reg_write(UC_X86_REG_GDTR, (0, GDT, 31 * 8 - 1, 0x0))
        for r in (UC_X86_REG_SS, UC_X86_REG_DS, UC_X86_REG_ES, UC_X86_REG_GS):
            self.uc.reg_write(r, 2 << 3)
        self.uc.reg_write(UC_X86_REG_FS, 15 << 3)

    # ---------------------------------------------------------------- memory helpers
    def r32(self, a):
        return struct.unpack('<I', self.uc.mem_read(a, 4))[0]

    def w32(self, a, v):
        self.uc.mem_write(a, struct.pack('<I', v & 0xFFFFFFFF))

    def alloc(self, n, zero=True):
        n = max(n, 1)
        a = align(self.heap_top, 0x20)
        self.heap_top = a + align(n, 0x20) + 0x20
        self.sizes[a] = n
        if self.heap_top > self.HEAP + self.HEAP_SIZE:
            raise Stop('heap exhausted')
        if zero:
            self.uc.mem_write(a, b'\0' * n)
        return a

    def wstr_read(self, a, maxn=4096):
        out = bytearray()
        while len(out) < maxn * 2:
            c = bytes(self.uc.mem_read(a + len(out), 2))
            if c == b'\0\0':
                break
            out += c
        return out.decode('utf-16-le', 'replace')

    def cstr_read(self, a, maxn=4096):
        out = bytearray()
        while len(out) < maxn:
            c = bytes(self.uc.mem_read(a + len(out), 1))
            if c == b'\0':
                break
            out += c
        return out.decode('latin-1')

    def make_wstring(self, s):
        """MSVC x86 std::wstring (24 bytes): buf/ptr[16], size, capacity"""
        obj = self.alloc(24)
        enc = s.encode('utf-16-le') + b'\0\0'
        if len(s) < 8:
            self.uc.mem_write(obj, enc)
            cap = 7
        else:
            p = self.alloc(len(enc) + 2)
            self.uc.mem_write(p, enc)
            self.w32(obj, p)
            cap = len(s)
        self.w32(obj + 0x10, len(s))
        self.w32(obj + 0x14, cap)
        return obj

    def read_wstring(self, obj):
        size, cap = self.r32(obj + 0x10), self.r32(obj + 0x14)
        p = self.r32(obj) if cap >= 8 else obj
        return bytes(self.uc.mem_read(p, size * 2)).decode('utf-16-le', 'replace')

    # ---------------------------------------------------------------- imports
    def _new_stub(self, name, handler=None):
        a = self.STUB + self.nstub * 16
        self.nstub += 1
        self.stubs[a] = (name, handler)
        return a

    def _imports(self):
        for e in self.pe.DIRECTORY_ENTRY_IMPORT:
            dll = e.dll.decode()
            for i in e.imports:
                name = i.name.decode() if i.name else 'ord%d' % i.ordinal
                if name in ('g_pMemAlloc', 'g_pVCR', 'g_VProfCurrentProfile', 'g_ClockSpeedMillisecondsMultiplier'):
                    var = self.alloc(64)
                    if name in ('g_pMemAlloc', 'g_pVCR'):
                        obj = self.alloc(64)
                        vt = self.alloc(4 * 128)
                        for k in range(128):
                            self.w32(vt + 4 * k, self._new_stub('%s::vfunc%d' % (name, k)))
                        self.w32(obj, vt)
                        self.w32(var, obj)
                    elif name == 'g_ClockSpeedMillisecondsMultiplier':
                        self.uc.mem_write(var, struct.pack('<d', 1.0 / 3e6))
                    self.w32(i.address, var)
                else:
                    self.w32(i.address, self._new_stub('%s!%s' % (dll, name)))

    def _ret(self, value, nargs):
        uc = self.uc
        esp = uc.reg_read(UC_X86_REG_ESP)
        ret = self.r32(esp)
        uc.reg_write(UC_X86_REG_EAX, value & 0xFFFFFFFF)
        uc.reg_write(UC_X86_REG_ESP, esp + 4 + 4 * nargs)
        uc.reg_write(UC_X86_REG_EIP, ret)

    def arg(self, k):
        return self.r32(self.uc.reg_read(UC_X86_REG_ESP) + 4 + 4 * k)

    def _on_stub(self, uc, addr, size, user):
        if addr == self.RET_MAGIC:
            uc.emu_stop()
            return
        name, _h = self.stubs.get(addr, ('?%x' % addr, None))
        if self.verbose > 1:
            print('  [api] %s ret=%08x args %08x %08x %08x %08x' % (name, self.r32(uc.reg_read(UC_X86_REG_ESP)), self.arg(0), self.arg(1), self.arg(2), self.arg(3)))
        try:
            v, n = self.api(name)
        except Stop as e:
            print('STOP in %s: %s' % (name, e))
            uc.emu_stop()
            return
        self._ret(v, n)

    def _on_unmapped(self, uc, access, address, size, value, user):
        print('UNMAPPED access %d at %08x size %d eip %08x' % (access, address, size, uc.reg_read(UC_X86_REG_EIP)))
        self.backtrace()
        return False

    def backtrace(self, depth=0x800):
        uc = self.uc
        esp = uc.reg_read(UC_X86_REG_ESP)
        regs = ' '.join('%s=%08x' % (n, uc.reg_read(r)) for n, r in [('eax', UC_X86_REG_EAX), ('ebx', UC_X86_REG_EBX), ('ecx', UC_X86_REG_ECX), ('edx', UC_X86_REG_EDX), ('esi', UC_X86_REG_ESI), ('edi', UC_X86_REG_EDI), ('ebp', UC_X86_REG_EBP), ('esp', UC_X86_REG_ESP)])
        print('  regs', regs)
        lo, hi = self.base + 0x1000, self.base + 0x240000
        out = []
        for k in range(0, depth, 4):
            try:
                v = self.r32(esp + k)
            except Exception:
                break
            if lo <= v < hi:
                b = bytes(uc.mem_read(v - 5, 5))
                b6 = bytes(uc.mem_read(v - 6, 6))
                if b[0] == 0xE8 or b6[0] == 0xFF and b6[1] in (0x15, 0x55, 0x95) or bytes(uc.mem_read(v - 2, 2))[0] == 0xFF or bytes(uc.mem_read(v - 3, 3))[0] == 0xFF:
                    out.append('%08x(+%x)' % (v, k))
        print('  stack return addresses:', ' '.join(out[:24]))

    # ---------------------------------------------------------------- API emulation
    def api(self, name):
        a = self.arg
        log = self.verbose
        if name.startswith('g_pMemAlloc::vfunc'):
            k = int(name.rsplit('vfunc', 1)[1])
            if k == 0:      # Alloc(size, file, line)
                return self.alloc(a(0)), 3
            if k == 1:      # Alloc(size)
                return self.alloc(a(0)), 1
            if k in (2, 3):  # 2 = Realloc(p, size, file, line), 3 = Realloc(p, size)
                p, n = a(0), a(1)
                q = self.alloc(n)
                if p:
                    self.uc.mem_write(q, bytes(self.uc.mem_read(p, min(self.alloc_size(p), n))))
                if self.verbose:
                    print('  realloc vfunc%d %08x %d -> %08x' % (k, p, n, q))
                return q, 4 if k == 2 else 2
            if k == 4:      # Free(p, file, line)
                return 0, 3
            if k == 5:      # Free(p)
                return 0, 1
            if k == 23:     # IsDebugHeap()
                return 0, 0
            raise Stop('memalloc vfunc %d args %08x %08x %08x' % (k, a(0), a(1), a(2)))
        short = name.split('!', 1)[-1]
        if short == 'CreateFileW':
            path = self.wstr_read(a(0))
            if log:
                print('  CreateFileW', path)
            if not os.path.exists(path):
                return 0xFFFFFFFF, 7
            h = self.next_handle; self.next_handle += 4
            self.handles[h] = ('file', path)
            return h, 7
        if short == 'SetFilePointer':
            kind, path = self.handles[a(0)][:2]
            pos = self.fpos.get(a(0), 0)
            dist = a(1) - (1 << 32) if a(1) & 0x80000000 else a(1)
            if a(2):
                dist = (self.r32(a(2)) << 32) | a(1)
            base = {0: 0, 1: pos, 2: os.path.getsize(path)}[a(3)]
            pos = base + dist
            self.fpos[a(0)] = pos
            if a(2):
                self.w32(a(2), pos >> 32)
            return pos & 0xFFFFFFFF, 4
        if short == 'SetFilePointerEx':
            kind, path = self.handles[a(0)][:2]
            pos = self.fpos.get(a(0), 0)
            dist = struct.unpack('<q', struct.pack('<II', a(1), a(2)))[0]
            base = {0: 0, 1: pos, 2: os.path.getsize(path)}[a(4)]
            pos = base + dist
            self.fpos[a(0)] = pos
            if a(3):
                self.uc.mem_write(a(3), struct.pack('<q', pos))
            return 1, 5
        if short == 'ReadFile':
            kind, path = self.handles[a(0)][:2]
            pos = self.fpos.get(a(0), 0)
            with open(path, 'rb') as fh:
                fh.seek(pos)
                d = fh.read(a(2))
            if getattr(self, 'patches', None):
                d = bytearray(d)
                for o, v in self.patches.items():
                    if pos <= o < pos + len(d):
                        d[o - pos] = v & 0xFF
                d = bytes(d)
            self.uc.mem_write(a(1), d)
            self.fpos[a(0)] = pos + len(d)
            if a(3):
                self.w32(a(3), len(d))
            if self.verbose > 1:
                print('  ReadFile pos %d n %d -> %d' % (pos, a(2), len(d)))
            self.file_reads.append((pos, len(d)))
            return 1, 5
        if short == 'CreateFileMappingW':
            h = self.next_handle; self.next_handle += 4
            self.handles[h] = ('map', self.handles[a(0)][1])
            return h, 6
        if short == 'MapViewOfFile':
            path = self.handles[a(0)][1]
            data = open(path, 'rb').read()
            if getattr(self, 'patches', None):
                data = bytearray(data)
                for o, v in self.patches.items():
                    data[o] = v & 0xFF
                data = bytes(data)
            base = self.view_top
            sz = align(len(data) + 1)
            self.uc.mem_map(base, sz)
            self.uc.mem_write(base, data)
            self.view_top += sz + 0x10000
            self.views.append((base, len(data), path))
            if log:
                print('  MapViewOfFile %s -> %08x (%d bytes)' % (os.path.basename(path), base, len(data)))
            return base, 5
        if short in ('CloseHandle', 'UnmapViewOfFile'):
            return 1, 1
        if short in ('GetFileSizeEx',):
            path = self.handles[a(0)][1]
            self.uc.mem_write(a(1), struct.pack('<Q', os.path.getsize(path)))
            return 1, 2
        if short == 'GetFileSize':
            path = self.handles[a(0)][1]
            if a(1):
                self.w32(a(1), 0)
            return os.path.getsize(path), 2
        if short in ('EnterCriticalSection', 'LeaveCriticalSection', 'InitializeCriticalSection', 'DeleteCriticalSection'):
            return 0, 1
        if short in ('InitializeCriticalSectionAndSpinCount', 'InitializeCriticalSectionEx'):
            return 1, 2 if short.endswith('SpinCount') else 3
        if short in ('GetSystemInfo', 'GetNativeSystemInfo'):
            self.uc.mem_write(a(0), struct.pack('<HHIIIIIIIHH', 0, 0, 0x1000, 0x10000, 0x7FFEFFFF, 0xF, 4, 586, 0x10000, 6, 0))
            return 0, 1
        if short == 'SystemFunction036':     # RtlGenRandom(buf, len) - deterministic for the RE runs
            self.uc.mem_write(a(0), bytes((int(os.environ.get('EMU_RND', '90')) + i * 7) & 0xFF for i in range(a(1))))
            return 1, 2
        if short in ('CryptAcquireContextA', 'CryptAcquireContextW'):
            self.w32(a(0), 0x77); return 1, 5
        if short == 'CryptGenRandom':
            self.uc.mem_write(a(2), bytes((0x33 + i * 5) & 0xFF for i in range(a(1)))); return 1, 3
        if short == 'CryptReleaseContext':
            return 1, 2
        if short == 'GetFileAttributesW':
            path = self.wstr_read(a(0))
            if log:
                print('  GetFileAttributesW', path, os.path.exists(path))
            if not os.path.exists(path):
                return 0xFFFFFFFF, 1
            return 0x10 if os.path.isdir(path) else 0x20, 1
        if short == 'GetFileAttributesExW':
            path = self.wstr_read(a(0))
            if log:
                print('  GetFileAttributesExW', path, os.path.exists(path))
            if not os.path.exists(path):
                return 0, 3
            st = os.stat(path)
            self.uc.mem_write(a(2), struct.pack('<I24xII', 0x10 if os.path.isdir(path) else 0x20, st.st_size >> 32, st.st_size & 0xFFFFFFFF))
            return 1, 3
        if short == 'RaiseException':
            code, flags, n, pargs = a(0), a(1), a(2), a(3)
            info = ''
            if code == 0xE06D7363 and n >= 3:
                obj, ti = self.r32(pargs + 4), self.r32(pargs + 8)
                try:
                    what = self.r32(obj + 4)
                    info = 'what=%r' % self.cstr_read(what, 300) if what else ''
                except Exception:
                    pass
                try:   # ThrowInfo -> CatchableTypeArray -> first CatchableType -> TypeDescriptor name
                    cta = self.r32(ti + 12); ct = self.r32(cta + 4); td = self.r32(ct + 4)
                    info += ' type=%s' % self.cstr_read(td + 8, 200)
                except Exception:
                    pass
            self.backtrace()
            raise Stop('C++ exception %08x %s' % (code, info))
        if short in ('Sleep',):
            return 0, 1
        if short in ('SwitchToThread',):
            return 0, 0
        if short == 'GetLastError':
            return 0, 0
        if short == 'SetLastError':
            return 0, 1
        if short in ('GetTickCount', 'timeGetTime'):
            return 123456, 0
        if short == 'QueryPerformanceCounter':
            self.uc.mem_write(a(0), struct.pack('<Q', 1234567)); return 1, 1
        if short == 'QueryPerformanceFrequency':
            self.uc.mem_write(a(0), struct.pack('<Q', 10000000)); return 1, 1
        if short == 'GetCurrentThreadId':
            return 0x1234, 0
        if short == 'GetCurrentProcessId':
            return 0x4321, 0
        if short in ('ThreadInterlockedIncrement',):
            v = self.r32(a(0)) + 1; self.w32(a(0), v); return v, 0
        if short in ('ThreadInterlockedDecrement',):
            v = self.r32(a(0)) - 1; self.w32(a(0), v); return v, 0
        if short == 'ThreadInterlockedExchangeAdd':
            v = self.r32(a(0)); self.w32(a(0), v + a(1)); return v, 0
        if short in ('?Lock@CThreadMutex@@QAEXXZ', '?Unlock@CThreadMutex@@QAEXXZ', '?Lock@CThreadMutex@@QBEXXZ'):
            return 0, 0
        if short == '?Lock@CThreadFastMutex@@QCEXI@Z':
            return 0, 1
        if short in ('Log', 'Error', 'Msg', 'Warning', 'DevMsg', 'DevWarning'):
            print('  %s: %s' % (short, self.cstr_read(a(0))[:200]))
            return 0, 0
        raise Stop('unhandled import %s (args %08x %08x %08x %08x)' % (name, a(0), a(1), a(2), a(3)))

    def alloc_size(self, p):
        return self.sizes.get(p, 0x100)

    # ---------------------------------------------------------------- calls
    def call(self, func, args, ecx=None, count=0, timeout=0):
        """cdecl / thiscall call; returns eax"""
        uc = self.uc
        esp = self.STACK + self.STACK_SIZE - 0x1000
        for v in reversed(args):
            esp -= 4
            self.w32(esp, v)
        esp -= 4
        self.w32(esp, self.RET_MAGIC)
        uc.reg_write(UC_X86_REG_ESP, esp)
        uc.reg_write(UC_X86_REG_EBP, 0)
        if ecx is not None:
            uc.reg_write(UC_X86_REG_ECX, ecx)
        try:
            uc.emu_start(func, self.RET_MAGIC, timeout=timeout, count=count)
        except UcError as e:
            print('UcError %s at eip %08x' % (e, uc.reg_read(UC_X86_REG_EIP)))
            raise
        return uc.reg_read(UC_X86_REG_EAX)


if __name__ == '__main__':
    emu = Emu()
    print('stubs', emu.nstub)

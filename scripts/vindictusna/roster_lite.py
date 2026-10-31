"""Read a Source .mdl header without its .vvd / .vtx: name, bones, materials, cd paths, $includemodel list, hull."""
import struct


def cstr(d, o):
    return d[o:d.index(b'\0', o)].decode('latin-1')


def mdl_info(path):
    d = open(path, 'rb').read()
    if d[:4] != b'IDST':
        return None
    nb, bi = struct.unpack_from('<2i', d, 156)
    bones = [cstr(d, bi + i * 216 + struct.unpack_from('<i', d, bi + i * 216)[0]) for i in range(nb)]
    nt, ti, ncd, cdi = struct.unpack_from('<4i', d, 204)
    tex = [cstr(d, ti + i * 64 + struct.unpack_from('<i', d, ti + i * 64)[0]) for i in range(nt)]
    cd = [cstr(d, struct.unpack_from('<i', d, cdi + i * 4)[0]) for i in range(ncd)]
    ni, ii = struct.unpack_from('<2i', d, 336)
    inc = [cstr(d, ii + i * 8 + struct.unpack_from('<2i', d, ii + i * 8)[1]) for i in range(ni)]
    return {'version': struct.unpack_from('<i', d, 4)[0], 'name': cstr(d, 12), 'nbones': nb, 'bones': bones,
            'textures': tex, 'cd': cd, 'include': inc,
            'hull': [struct.unpack_from('<3f', d, 104), struct.unpack_from('<3f', d, 116)]}

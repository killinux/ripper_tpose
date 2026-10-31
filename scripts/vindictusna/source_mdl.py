"""Minimal Source-engine model reader (MDL v44-48 + VVD v4 + VTX v7), pure Python, no bpy.

    m = load_model('.../fiona.mdl')     # reads the .vvd and .dx90.vtx next to it
    m.bones      -> [Bone(name, parent, pos, quat, pose_to_bone(3x4))]
    m.textures   -> material names;  m.cdtextures -> material search dirs
    m.bodyparts  -> [BodyPart(name, models=[Model(name, meshes=[Mesh(material, verts, tris)])])]
    Mesh.verts   -> list of (pos, normal, uv, [(bone, weight), ...])   in model space (Z-up, game units)
    Mesh.tris    -> list of (i0, i1, i2) into Mesh.verts

Only what is needed to rebuild the bind-pose geometry with its skin weights and materials.
Struct layouts follow the public Source SDK (studio.h / optimize.h).
"""
import os
import struct
from collections import namedtuple

Bone = namedtuple('Bone', 'name parent pos quat pose_to_bone')
Mesh = namedtuple('Mesh', 'material verts tris mtype mparam flexes', defaults=((),))
# flexes = [(flex name, [(local vertex index, (dx, dy, dz)), ...]), ...] - Source facial flexes (vertex animations)
Model = namedtuple('Model', 'name meshes eyeballs')
Eyeball = namedtuple('Eyeball', 'name bone org zoffset radius up forward texture iris_scale')
BodyPart = namedtuple('BodyPart', 'name models')


def _cstr(d, off):
    end = d.index(b'\0', off)
    return d[off:end].decode('latin-1')


class SourceModel:
    pass


def _read_vvd(path, checksum):
    d = open(path, 'rb').read()
    ident, ver, chk, nlods = struct.unpack_from('<4sIiI', d, 0)
    assert ident == b'IDSV', path
    lodverts = struct.unpack_from('<8I', d, 16)
    nfix, fixstart, vstart, tstart = struct.unpack_from('<4I', d, 48)
    pool = []
    for i in range(lodverts[0]):
        o = vstart + i * 48
        w = struct.unpack_from('<3f', d, o)
        b0, b1, b2, nb = struct.unpack_from('<3bB', d, o + 12)
        pos = struct.unpack_from('<3f', d, o + 16)
        nrm = struct.unpack_from('<3f', d, o + 28)
        uv = struct.unpack_from('<2f', d, o + 40)
        pool.append((pos, nrm, uv, list(zip((b0, b1, b2), w))[:nb]))
    if not nfix:
        return pool
    # LOD 0 vertex order = the fixup ranges (every fixup with lod >= 0), concatenated
    out = []
    for k in range(nfix):
        lod, src, cnt = struct.unpack_from('<3i', d, fixstart + 12 * k)
        if lod >= 0:
            out.extend(pool[src:src + cnt])
    return out


def _read_vtx(path):
    """-> {(bodypart, model): [mesh -> [(vtx_verts[orig_id...], indices)] ]} for LOD 0"""
    d = open(path, 'rb').read()
    ver, vcache, mbs, mbt, mbv, chk, nlods, mrl, nbp, bpoff = struct.unpack_from('<iiHHiiiiii', d, 0)
    assert ver == 7, ('vtx version', ver)
    out = {}
    for b in range(nbp):
        bpo = bpoff + b * 8
        nmod, modoff = struct.unpack_from('<ii', d, bpo)
        for m in range(nmod):
            mo = bpo + modoff + m * 8
            mnlod, lodoff = struct.unpack_from('<ii', d, mo)
            lo = mo + lodoff                                 # LOD 0
            nmesh, meshoff, _sp = struct.unpack_from('<iif', d, lo)
            meshes = []
            for k in range(nmesh):
                me = lo + meshoff + k * 9
                nsg, sgoff = struct.unpack_from('<ii', d, me)
                groups = []
                for g in range(nsg):
                    so = me + sgoff + g * 25
                    nv, voff, ni, ioff, nstrip, stoff = struct.unpack_from('<6i', d, so)
                    verts = [struct.unpack_from('<H', d, so + voff + i * 9 + 4)[0] for i in range(nv)]
                    idx = struct.unpack_from('<%dH' % ni, d, so + ioff)
                    strips = []
                    for s in range(nstrip):
                        sto = so + stoff + s * 27
                        sni, sio, snv, svo = struct.unpack_from('<4i', d, sto)
                        flags = d[sto + 18]
                        strips.append((sni, sio, flags))
                    groups.append((verts, idx, strips))
                meshes.append(groups)
            out[(b, m)] = meshes
    return out


def load_model(mdl_path):
    d = open(mdl_path, 'rb').read()
    ident, ver, chk = struct.unpack_from('<4sii', d, 0)
    assert ident == b'IDST', mdl_path
    m = SourceModel()
    m.version = ver
    m.name = d[12:76].split(b'\0')[0].decode('latin-1')
    (nbones, boneidx) = struct.unpack_from('<ii', d, 156)
    (ntex, texidx, ncd, cdidx, nskinref, nskinfam, skinidx, nbp, bpidx) = struct.unpack_from('<9i', d, 204)
    nflexdesc, flexdescidx = struct.unpack_from('<ii', d, 0x104)
    m.flexdesc = [_cstr(d, flexdescidx + i * 4 + struct.unpack_from('<i', d, flexdescidx + i * 4)[0])
                  for i in range(nflexdesc)]
    # bones
    m.bones = []
    for i in range(nbones):
        o = boneidx + i * 216
        nameoff, parent = struct.unpack_from('<ii', d, o)
        pos = struct.unpack_from('<3f', d, o + 32)
        quat = struct.unpack_from('<4f', d, o + 44)
        p2b = struct.unpack_from('<12f', d, o + 96)
        m.bones.append(Bone(_cstr(d, o + nameoff), parent, pos, quat, p2b))
    # textures / cd dirs / skin table (family 0)
    m.textures = [_cstr(d, texidx + i * 64 + struct.unpack_from('<i', d, texidx + i * 64)[0]) for i in range(ntex)]
    m.cdtextures = [_cstr(d, struct.unpack_from('<i', d, cdidx + i * 4)[0]) for i in range(ncd)]
    skin0 = struct.unpack_from('<%dh' % nskinref, d, skinidx) if nskinref else ()
    base = os.path.splitext(mdl_path)[0]
    vvd = _read_vvd(base + '.vvd', chk)
    vtxp = base + '.dx90.vtx'
    if not os.path.exists(vtxp):
        vtxp = base + '.vtx'
    vtx = _read_vtx(vtxp)
    m.bodyparts = []
    for b in range(nbp):
        bo = bpidx + b * 16
        nameoff, nmodels, bbase, modidx = struct.unpack_from('<iiii', d, bo)
        bpname = _cstr(d, bo + nameoff)
        models = []
        for mi in range(nmodels):
            mo = bo + modidx + mi * 148
            mname = d[mo:mo + 64].split(b'\0')[0].decode('latin-1')
            nmesh, meshidx, nverts, vindex = struct.unpack_from('<iiii', d, mo + 72)
            neye, eyeidx = struct.unpack_from('<ii', d, mo + 100)
            eyeballs = []
            for e in range(neye):
                eo = mo + eyeidx + e * 172
                enameoff, ebone = struct.unpack_from('<ii', d, eo)
                org = struct.unpack_from('<3f', d, eo + 8)
                zoff, rad = struct.unpack_from('<2f', d, eo + 20)
                up = struct.unpack_from('<3f', d, eo + 28)
                fwd = struct.unpack_from('<3f', d, eo + 40)
                etex = struct.unpack_from('<i', d, eo + 52)[0]
                iscale = struct.unpack_from('<f', d, eo + 60)[0]
                eyeballs.append(Eyeball(_cstr(d, eo + enameoff), ebone, org, zoff, rad, up, fwd, etex, iscale))
            vbase = vindex // 48
            meshes = []
            vtx_meshes = vtx.get((b, mi), [])
            for k in range(nmesh):
                me = mo + meshidx + k * 116
                mat, _midx, mnv, voff = struct.unpack_from('<iiii', d, me)
                mtype, mparam = struct.unpack_from('<ii', d, me + 24)
                matname = m.textures[skin0[mat]] if skin0 and mat < len(skin0) else (m.textures[mat] if mat < len(m.textures) else 'mat%d' % mat)
                verts, tris = [], []
                remap = {}
                for verts_g, idx, strips in (vtx_meshes[k] if k < len(vtx_meshes) else []):
                    for sni, sio, flags in strips:
                        seq = idx[sio:sio + sni]
                        if flags & 2:      # tristrip
                            tri_list = [(seq[i], seq[i + 1], seq[i + 2]) if i % 2 == 0 else (seq[i + 1], seq[i], seq[i + 2]) for i in range(len(seq) - 2)]
                        else:
                            tri_list = [tuple(seq[i:i + 3]) for i in range(0, len(seq) - 2, 3)]
                        for t in tri_list:
                            tt = []
                            for gi in t:
                                gv = vbase + voff + verts_g[gi]
                                if gv not in remap:
                                    remap[gv] = len(verts)
                                    verts.append(vvd[gv])
                                tt.append(remap[gv])
                            if len(set(tt)) == 3:
                                tris.append(tuple(tt))
                # flexes: mstudioflex_t (60 bytes) -> vertanims (16 bytes, 18 with a wrinkle delta): ushort index
                # (mesh-relative), speed, side, half-float delta[3], half-float normal delta[3]
                nflex, flexidx = struct.unpack_from('<ii', d, me + 16)
                flexes = []
                for f in range(nflex):
                    fo = me + flexidx + f * 60
                    desc, _t0, _t1, _t2, _t3, fnv, fvi, _pair, vat = struct.unpack_from('<i4fiiiB', d, fo)
                    size = 18 if vat == 1 else 16
                    deltas = []
                    for j in range(fnv):
                        vo = fo + fvi + j * size
                        idx = struct.unpack_from('<H', d, vo)[0]
                        local = remap.get(vbase + voff + idx)
                        if local is not None:
                            deltas.append((local, struct.unpack_from('<3e', d, vo + 4)))
                    if deltas:
                        flexes.append((m.flexdesc[desc] if desc < len(m.flexdesc) else 'flex%d' % desc, deltas))
                meshes.append(Mesh(matname, verts, tris, mtype, mparam, flexes))
            models.append(Model(mname, meshes, eyeballs))
        m.bodyparts.append(BodyPart(bpname, models))
    return m


if __name__ == '__main__':
    import sys
    for p in sys.argv[1:]:
        mm = load_model(p)
        print('%s  v%d  bones=%d  tex=%s  cd=%s' % (os.path.basename(p), mm.version, len(mm.bones), mm.textures, mm.cdtextures))
        for bp in mm.bodyparts:
            print('  bodypart %-16s models=%d' % (bp.name, len(bp.models)))
            for md in bp.models:
                nv = sum(len(x.verts) for x in md.meshes); nt = sum(len(x.tris) for x in md.meshes)
                print('     model %-34s meshes=%d verts=%d tris=%d mats=%s' % (md.name or '(blank)', len(md.meshes), nv, nt, sorted(set(x.material for x in md.meshes))))
                for e in md.eyeballs:
                    print('        eyeball %s bone=%d org=%s r=%.3f up=%s fwd=%s tex=%d iris_scale=%.3f z=%.3f' % (e.name, e.bone, tuple(round(x, 2) for x in e.org), e.radius, tuple(round(x, 2) for x in e.up), tuple(round(x, 2) for x in e.forward), e.texture, e.iris_scale, e.zoffset))
                for x in md.meshes:
                    if x.mtype:
                        print('        mesh %s mtype=%d param=%d verts=%d' % (x.material, x.mtype, x.mparam, len(x.verts)))

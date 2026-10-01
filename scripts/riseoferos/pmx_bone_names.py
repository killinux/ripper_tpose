"""Short, unique PMX bone names that a VMD can address.

A VMD names every keyed bone in 15 bytes of Shift-JIS.  MMD gives a key to the bone whose name starts with those
15 bytes; Blender's mmd_tools only takes an exact match of the whole name.  So a bone whose name is longer than
15 bytes cannot be driven by any VMD in Blender, and two bones that share their first 15 bytes
(``Bip001 Eyebrow_LC`` / ``Bip001 Eyebrow_LL`` -> ``Bip001 Eyebrow_``) cannot both be keyed anywhere.
ROE rigs have 40-60 such bones per model: twist helpers, face bones, hair, skirt chains.

``short_names`` picks a new name for each of them and keeps every other name as it is:

1. drop the Biped root prefix (``Bip001 R ForeTwist1`` -> ``R ForeTwist1``);
2. ``(mirrored)`` -> ``_m``;
3. drop a separate word "bone" (``AC cheek_bone_L01`` -> ``AC cheek_L01``) unless another bone has that name;
4. while the name is still too long, cut the longest word by one letter at a time
   (``AC eyelid_bone_BL`` -> ``AC eyel_bone_BL``), never below two letters, keeping digits and side letters;
5. if the result is taken by another bone, keep cutting; as a last resort end the name with ``~<n>``.

The same original name gives the same short name in every model unless a collision forces step 4.  The exporter
writes the original name into the bone's English name (empty in ROE PMX), so nothing is lost and tools that map
game bones to PMX bones (make_roe_vmd.py) can still find them.  Plain Python: used by the Blender exporter, the
roe_pmx_tools add-on and pmx_short_bone_names.py (existing PMX files).
"""
import re

LIMIT = 15                      # bytes of Shift-JIS a VMD keeps of a bone or morph name


def sjis_len(name):
    return len(name.encode("shift_jis", "replace"))


def fits(name):
    return 0 < sjis_len(name) <= LIMIT


def _first_pass(name):
    s = re.sub(r"^Bip\d{3}[ _]", "", name)
    s = s.replace("(mirrored)", "_m")
    s = re.sub(r"_{2,}", "_", s).strip(" _") or name
    return s


def _cut_longest_word(s):
    """One letter off the longest run of letters (leftmost on a tie); None when every run is down to two."""
    runs = [(m.start(), m.end()) for m in re.finditer(r"[A-Za-z]+", s)]
    runs = [r for r in runs if r[1] - r[0] > 2]
    if not runs:
        return None
    start, end = max(runs, key=lambda r: (r[1] - r[0], -r[0]))
    return s[:end - 1] + s[end:]


def candidates(name):
    """Shorter spellings of ``name``, best first; each fits in LIMIT bytes."""
    s = _first_pass(name)
    if fits(s):
        yield s
    # a separate "bone" word says nothing: AC cheek_bone_L01 -> AC cheek_L01.  When that name is taken
    # (AC eyelid_bone_BL next to AC eyelid_BL) the letters are cut from the full spelling instead, so the new
    # name still says "bone" rather than passing for its neighbour.
    plain = re.sub(r"(?i)[ _]bone(?=[ _])", "", s)
    if plain != s and fits(plain):
        yield plain
    while s is not None:
        if fits(s):
            yield s
        s = _cut_longest_word(s)


def _fallback(base, taken):
    for n in range(1, 10000):
        tail = "~%d" % n
        head = base
        while head and sjis_len(head + tail) > LIMIT:
            head = head[:-1]
        cand = head.rstrip(" _") + tail
        if cand not in taken:
            return cand
    raise RuntimeError("no free short name for %r" % base)


def short_names(names):
    """``{index: new name}`` for the names a VMD cannot address, in the order given (PMX bone order).

    A name is renamed when it is longer than LIMIT bytes or when an earlier bone already has it; a name that fits
    but shares its first LIMIT bytes with a long one is fine once the long one is renamed.  New names never equal a
    name that stays.
    """
    keep = set()
    seen = set()
    rename = []
    for i, n in enumerate(names):
        if fits(n) and n not in seen:
            keep.add(n)
            seen.add(n)
        else:
            rename.append(i)
            seen.add(n)
    taken = set(keep)
    out = {}
    for i in rename:
        n = names[i]
        new = next((c for c in candidates(n) if c not in taken), None)
        if new is None:
            new = _fallback(_first_pass(n), taken)
        taken.add(new)
        out[i] = new
    return out


def describe(names, mapping):
    """``old -> new`` lines for a report."""
    return ["%s -> %s" % (names[i], new) for i, new in sorted(mapping.items())]

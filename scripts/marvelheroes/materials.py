"""MaterialInstanceConstant parameters of a Marvel Heroes Omega package: parent, texture / scalar / vector parameter
values and the other plain properties.  Parent materials (Material3) are not parsed - their compiled shader data is
what stops UE Viewer - so a parameter the instance does not override is simply missing here.

    python -I materials.py <file.upk> [--json out.json]
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from upk import Package  # noqa: E402


def read_instances(pkg):
    """{instance name: {"path", "parent", "textures", "scalars", "vectors", "other"}} for every MIC export."""
    res = {}
    for i in pkg.of_class("materialinstanceconstant"):
        props, _ = pkg.object_props(i)
        m = {"path": pkg.obj_path(i + 1), "parent": "", "textures": {}, "scalars": {}, "vectors": {}, "other": {}}
        for name, ptype, size, index, extra, val in props:
            low = name.lower()
            if low == "parent":
                m["parent"] = val[1]
            elif low in ("textureparametervalues", "scalarparametervalues", "vectorparametervalues"):
                for item in pkg.struct_array(val):
                    item = {k.lower(): v for k, v in item.items()}
                    pn = str(item.get("parametername"))
                    pv = item.get("parametervalue")
                    if low.startswith("texture"):
                        m["textures"][pn] = pv[1] if isinstance(pv, tuple) else str(pv)
                    elif low.startswith("scalar"):
                        m["scalars"][pn] = pv
                    else:
                        m["vectors"][pn] = list(pv) if isinstance(pv, tuple) else pv
            elif ptype == "ArrayProperty":
                m["other"][name] = "array[%d]" % val[1]
            elif not isinstance(val, list):
                m["other"][name] = val[1] if isinstance(val, tuple) and ptype == "ObjectProperty" else val
        res[pkg.exports[i]["name"]] = m
    return res


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    pkg = Package(sys.argv[1])
    res = read_instances(pkg)
    for name, m in res.items():
        print("== %s  (parent %s)" % (m["path"], m["parent"]))
        for k, v in m["textures"].items():
            print("   texture %-40s %s" % (k, v))
        for k, v in m["scalars"].items():
            print("   scalar  %-40s %s" % (k, v))
        for k, v in m["vectors"].items():
            print("   vector  %-40s %s" % (k, v))
    if "--json" in sys.argv:
        with open(sys.argv[sys.argv.index("--json") + 1], "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, ensure_ascii=False, default=str)


if __name__ == "__main__":
    main()

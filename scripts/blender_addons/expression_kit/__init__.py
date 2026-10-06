# -*- coding: utf-8 -*-
"""Expression Kit - one add-on for facial expressions, several ways in and several ways out.

Sources: a MetaHuman DNA (Vindictus, MetaHuman Creator), the model's own ARKit shape keys, a pose
library (captured poses / actions / pose markers), or calibrated recipes for bone-only faces.
Outputs: MMD bone morphs, MMD vertex morphs (or per expression, whichever a 4-weight PMX shows
correctly), and the 52 ARKit shape keys registered with Faceit for iPhone live capture.

Blender add-on package.  UI: 3D viewport sidebar > 表情.  Scripts: ``api`` (see api.py).
"""
bl_info = {
    "name": "Expression Kit",
    "author": "ripper_tpose",
    "version": (0, 1, 0),
    "blender": (3, 6, 0),
    "location": "View3D > Sidebar > 表情",
    "description": "Facial expressions from a MetaHuman DNA, ARKit keys, a pose library or bone-only faces, "
                   "as MMD bone / vertex morphs or 52 ARKit shape keys for Faceit",
    "category": "Animation",
}

# junction-installed from the repo: Reload Scripts / re-enable refreshes the submodules too
if "bpy" in locals():
    import importlib

    for _module in (names, dna, roles, recipes, sources, bake, mmd, faceit, ue_weights, engine,   # noqa: F821
                    api, ui):                                                                     # noqa: F821
        importlib.reload(_module)

import bpy  # noqa: E402,F401

from . import names, dna, roles, recipes, sources, bake, mmd, faceit, ue_weights, engine, api, ui  # noqa: E402


def register():
    ui.register()


def unregister():
    ui.unregister()

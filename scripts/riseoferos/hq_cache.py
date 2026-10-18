r"""Where the Rise of Eros game-material data lives (hq_material_data.py's <id>.json + textures\ + export\): one answer
for the batch export, both Blender add-ons (roe_game_materials, roe_xps_addon's 2.5 button) and the helper scripts.

  1. ROE_HQ_CACHE, when set;
  2. the archive's copy E:\game_export\RiseOfEros\_meta\_hq_materials, when it exists (moved there 2026-10-17: it
     outlives D:\roe_exports, which is emptied once a batch is archived);
  3. <export root>\_hq_materials - D:\roe_exports\_hq_materials, where it lived before.

An add-on's own cache field, or a cache= argument, still wins over all three.  No bpy, no UnityPy: plain Python.
"""
import os

DEFAULT_EXPORT_ROOT = r"D:\roe_exports"
ARCHIVE_CACHE = r"E:\game_export\RiseOfEros\_meta\_hq_materials"


def default_cache(export_root=None):
    """The folder to read / fill when nothing names one."""
    env = os.environ.get("ROE_HQ_CACHE")
    if env:
        return env
    if os.path.isdir(ARCHIVE_CACHE):
        return ARCHIVE_CACHE
    return os.path.join(export_root or DEFAULT_EXPORT_ROOT, "_hq_materials")


if __name__ == "__main__":
    print(default_cache())

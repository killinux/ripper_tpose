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


def relocate(path, cache=None):
    """A file path an earlier run recorded inside the cache (a material's roe_hq_pmx / roe_hq_xps) whose file is gone -
    the cache moved, D:\\roe_exports\\_hq_materials -> the E: archive, 2026-10-17 - as the same file under `cache`
    (default_cache() when None).  Paths that exist, or that have no copy there, come back unchanged."""
    if not path or os.path.isfile(path):
        return path
    norm = path.replace("\\", "/")
    key = "/_hq_materials/"
    if key not in norm:
        return path
    moved = os.path.join(cache or default_cache(), *norm.split(key, 1)[1].split("/"))
    return moved if os.path.isfile(moved) else path


if __name__ == "__main__":
    print(default_cache())

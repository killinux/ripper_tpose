"""Blender headless FBX -> XPS/PMX/GLB converter.

Called by extract_character.ps1 via:
  blender --background --python convert_fbx.py -- <input.fbx> <output_dir> <format>

Supported formats: xps, pmx, glb
"""
import sys
import os

def main():
    argv = sys.argv
    sep = argv.index('--') if '--' in argv else -1
    if sep < 0 or len(argv) < sep + 4:
        print("Usage: blender --background --python convert_fbx.py -- <input.fbx> <output_dir> <format>")
        print("Formats: xps, pmx, glb")
        sys.exit(1)

    fbx_path = argv[sep + 1]
    out_dir = argv[sep + 2]
    fmt = argv[sep + 3].lower()

    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)

    print(f"[convert] Importing {fbx_path}")
    bpy.ops.import_scene.fbx(
        filepath=fbx_path,
        automatic_bone_orientation=True,
        use_image_search=False
    )

    basename = os.path.splitext(os.path.basename(fbx_path))[0]
    os.makedirs(out_dir, exist_ok=True)

    if fmt == 'glb':
        out_path = os.path.join(out_dir, basename + '.glb')
        print(f"[convert] Exporting GLB -> {out_path}")
        bpy.ops.export_scene.gltf(
            filepath=out_path,
            export_format='GLB',
            export_skins=True,
            export_morph=True,
            export_animations=False,
            use_selection=False
        )
        print(f"[convert] Done: {out_path}")

    elif fmt == 'xps':
        out_path = os.path.join(out_dir, basename + '.mesh.ascii')
        print(f"[convert] Exporting XPS -> {out_path}")
        try:
            import io_scene_xps_tools
        except ImportError:
            pass
        try:
            bpy.ops.xps_tools.export_model(filepath=out_path)
            print(f"[convert] Done: {out_path}")
        except Exception as e:
            print(f"[convert] XPS export via xps_tools failed: {e}")
            print("[convert] Trying b2xps_addon...")
            try:
                bpy.ops.b2xps.export(filepath=out_path)
                print(f"[convert] Done: {out_path}")
            except Exception as e2:
                print(f"[convert] b2xps also failed: {e2}")
                print("[convert] Falling back to Noesis CLI for XPS conversion")
                sys.exit(2)

    elif fmt == 'pmx':
        out_path = os.path.join(out_dir, basename + '.pmx')
        print(f"[convert] Exporting PMX -> {out_path}")
        try:
            import mmd_tools
        except ImportError:
            pass
        try:
            bpy.ops.mmd_tools.export_pmx(
                filepath=out_path,
                scale=0.08,
                copy_textures=False
            )
            print(f"[convert] Done: {out_path}")
        except Exception as e:
            print(f"[convert] PMX export failed: {e}")
            sys.exit(2)

    else:
        print(f"[convert] Unknown format: {fmt}")
        sys.exit(1)


if __name__ == '__main__':
    main()

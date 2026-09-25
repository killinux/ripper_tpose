"""A UnityPy Environment over NARAKA's StreamingAssets: load a bundle by path
and, on demand, the bundles it depends on (from its AssetBundle object)."""
import os

import UnityPy

import naraka_bundle
import naraka_manifest

GAME = r"E:\SteamLibrary\steamapps\common\NARAKA BLADEPOINT"
STREAMING = os.path.join(GAME, "NarakaBladepoint_Data", "StreamingAssets")


class Game:
    def __init__(self, streaming=STREAMING):
        self.root = streaming
        self.manifest = naraka_manifest.read(streaming)
        self.asset_bundle = {a: b for b, assets in self.manifest.items() for a in assets}
        self.env = UnityPy.Environment()
        self.loaded = {}                      # bundle path -> AssetBundle object data

    def load(self, bundle, deps=True):
        """Load a bundle (and its dependencies); returns its AssetBundle data."""
        if bundle in self.loaded:
            return self.loaded[bundle]
        self.loaded[bundle] = None
        files = []
        for name, blob in naraka_bundle.open_lazy(os.path.join(self.root, bundle)):
            files.append(self.env.load_file(blob, name=name))
        ab = None
        for f in files:
            for obj in getattr(f, "objects", {}).values():
                if obj.type.name == "AssetBundle":
                    ab = obj.read()
        self.loaded[bundle] = ab
        if deps and ab is not None:
            for dep in ab.m_Dependencies:
                self.load(dep, deps=True)
        return ab

    def container(self, bundle):
        """{asset path: [PPtr, ...]} of one bundle (an .fbx maps to several
        objects: the root GameObject, the Avatar, meshes...)."""
        ab = self.load(bundle)
        out = {}
        for path, info in (ab.m_Container if ab else []):
            out.setdefault(path, []).append(info.asset)
        return out

    def objects(self, path):
        return self.container(self.asset_bundle[path])[path]

    def asset(self, path, kind="GameObject"):
        """The object of type `kind` an asset path ("assets/res/...prefab") maps to."""
        items = self.objects(path)
        for ptr in items:
            if ptr.type.name == kind:
                return ptr
        return items[0]

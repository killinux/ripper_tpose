"""Script entry points.

    import sys; sys.path.insert(0, r"...\scripts\blender_addons")
    from mmd_face_morphs import api
    report = api.setup(root_or_any_object_of_the_model)

``report["morphs"]`` lists what was created, ``report["skipped"]`` what could
not be (name, reason), ``report["face"]`` the bones found per role.
"""
from . import build, expressions, faces


def analyze_model(obj):
    """Face bones of the model ``obj`` belongs to (a ``faces.Face``)."""
    root, arm = build.model_of(obj)
    return faces.resolve(arm)


def possible(face):
    """Names of the recipes that have at least one bone on this face."""
    names = []
    for recipe in expressions.MORPHS:
        if any(face.bone(role) for role, _kind, _amount in recipe["actions"]):
            names.append(recipe["name"])
    return names


def setup(obj, categories=expressions.CATEGORIES, names=None, scales=None, replace=True,
          log=print):
    """Build the standard expression set as bone morphs on the model.

    ``categories``: which of EYEBROW / EYE / MOUTH to build.
    ``names``: restrict to these morph names.
    ``scales``: {"eyes": x, "brows": x, "mouth": x, "tongue": x} multipliers.
    ``replace``: rebuild morphs of the same name (the ROE worker's old nine).
    """
    root, arm = build.model_of(obj)
    recipes = [r for r in expressions.MORPHS
               if r["category"] in categories and (names is None or r["name"] in names)]
    created, skipped, face = build.build(root, arm, recipes, scales=scales, replace=replace, log=log)
    if log:
        log("face: %s" % face.describe())
        log("%d morphs created, %d skipped" % (len(created), len(skipped)))
    return {
        "morphs": created,
        "skipped": skipped,
        "face": dict(face.bones),
        "style": face.style,
        "unit": face.unit,
        "by_category": {c: [r["name"] for r in recipes if r["category"] == c and r["name"] in created]
                        for c in expressions.CATEGORIES},
    }


def clear(obj):
    root, _arm = build.model_of(obj)
    return build.clear(root)

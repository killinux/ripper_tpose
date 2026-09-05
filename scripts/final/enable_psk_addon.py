"""在无头 Blender 里启用 io_scene_psk_psa（PSK/PSKX 导入器）。

validate_ff7remake_model.py 只探测导入器是否存在、不负责启用；无头启动时用户偏好里
的插件并不会自动加载，所以批量脚本把本文件作为**前置** --python 传入：

    blender --background --python enable_psk_addon.py --python validate_ff7remake_model.py -- ...

注意 addon_utils.enable 的关键字是 default_set，不是 persist。
"""
import addon_utils

NAME = "io_scene_psk_psa"
try:
    addon_utils.enable(NAME, default_set=True, handle_error=None)
    print("[enable_psk] %s enabled=%s" % (NAME, addon_utils.check(NAME)[1]))
except Exception as exc:  # noqa: BLE001 - 只打印，让后面的导入器探测给出明确错误
    print("[enable_psk] %s error: %s" % (NAME, exc))

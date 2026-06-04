"""pytest 排除設定。

`test_smoke_all.py` 跟 `test_migration_safety.py` 是 standalone Python runner
（自帶 `__main__` 結尾 sys.exit、整個 test body 在 module level 跑），
不是 pytest-style discoverable test。直接執行：

    python tests/test_smoke_all.py
    python tests/test_migration_safety.py

pytest 嘗試 import 收集時會在 module body 跑到 `sys.exit(0)` 直接 abort 整個
collection（pytest INTERNALERROR）。此 conftest 排除這兩檔避免污染 `pytest tests/`。
"""
collect_ignore = ["test_smoke_all.py", "test_migration_safety.py", "test_deadline_engine.py"]

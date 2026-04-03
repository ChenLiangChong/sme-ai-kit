"""
測試 update_employee 工具。
使用獨立的測試 DB，不動正式資料。
"""
import sqlite3
import os
import sys
import tempfile

# 設定測試 DB
TEST_DB = tempfile.mktemp(suffix=".db")
os.environ["SME_DB_PATH"] = TEST_DB

# 載入 server
sys.path.insert(0, os.path.dirname(__file__))
from server import register_employee, update_employee, lookup_employee, init_db

def setup():
    """初始化測試 DB 和種子資料"""
    init_db()
    print("✓ 測試 DB 初始化完成")

    result = register_employee("York", role="boss", department="管理部", permissions="admin", phone="0912-000-001")
    print(f"✓ 建立測試員工: {result}")

    result = register_employee("小王", role="staff", department="倉管", permissions="basic", phone="0912-000-002")
    print(f"✓ 建立測試員工: {result}")

def test_update_name():
    result = update_employee(1, name="York Chen")
    assert "已更新" in result and "name" in result, f"FAIL: {result}"
    print(f"✓ 更新姓名: {result}")

def test_update_line_binding():
    result = update_employee(1, line_user_id="U1234567890")
    assert "已更新" in result and "line_user_id" in result, f"FAIL: {result}"
    # 驗證
    info = lookup_employee("U1234567890")
    assert "已綁定" in info, f"FAIL: LINE 綁定未生效 - {info}"
    print(f"✓ LINE 綁定: {result}")

def test_update_line_unbind():
    result = update_employee(1, line_user_id="")
    assert "已更新" in result, f"FAIL: {result}"
    info = lookup_employee("York Chen")
    assert "未綁定" in info, f"FAIL: LINE 解綁未生效 - {info}"
    print(f"✓ LINE 解綁: {result}")

def test_update_deactivate():
    result = update_employee(2, active=0, permissions="none", notes="2026-04-03 離職")
    assert "已更新" in result, f"FAIL: {result}"
    assert "active" in result, f"FAIL: active 未出現 - {result}"
    print(f"✓ 停用帳號: {result}")

def test_update_multiple_fields():
    result = update_employee(1, department="營運部", phone="0912-999-999")
    assert "已更新" in result, f"FAIL: {result}"
    assert "department" in result and "phone" in result, f"FAIL: 多欄位更新 - {result}"
    print(f"✓ 多欄位更新: {result}")

def test_update_nonexistent():
    result = update_employee(999)
    assert "沒有指定" in result or "找不到" in result, f"FAIL: 應報錯 - {result}"
    print(f"✓ 不存在的員工: {result}")

def test_update_no_fields():
    result = update_employee(1)
    assert "沒有指定" in result, f"FAIL: 應報錯 - {result}"
    print(f"✓ 無欄位更新: {result}")

def cleanup():
    try:
        os.unlink(TEST_DB)
    except:
        pass

if __name__ == "__main__":
    try:
        setup()
        print("\n--- 測試開始 ---\n")
        test_update_name()
        test_update_line_binding()
        test_update_line_unbind()
        test_update_deactivate()
        test_update_multiple_fields()
        test_update_nonexistent()
        test_update_no_fields()
        print("\n=== 全部通過 ✅ ===")
    except AssertionError as e:
        print(f"\n=== 測試失敗 ❌ === {e}")
        sys.exit(1)
    finally:
        cleanup()

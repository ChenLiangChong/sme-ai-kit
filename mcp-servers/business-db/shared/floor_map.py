"""
Floor capability config layer（決策 #171）— floor → 該層能力（keystone）。

#6 從「dept→floor 路由表」升級為「能力設定層」：每一層 floor 對應一組能力
{business_units, financial_visibility, role, escalation_target, department}。
一個安全預設、導入(onboarding)時客製。#9 上報路由 / #11 BU 分層讀 / 財務可見度
全讀這張表 = 整個彈性的 keystone。

設計原則（決策 #171，老闆「考慮最通用的作法 + 保留客製化的彈性」）：
- 預設最簡單安全（無設定檔 → 全權限層看全部、其餘 financial=none/role=staff），
  完全等同 #1/#8 既有行為（向後相容）。
- 要不一樣 → 改 floor-map.json（導入客製）、不改碼。

設定檔：data/floor-map.json（或 SME_FLOOR_MAP env 指定路徑）。格式見 floor-map.example.json。
應被 floored session sandbox denyRead（跨層設定不給部門 agent 讀）；business-db MCP 進程
（非 sandbox）讀得到。

financial_visibility 三態：
- 'none'（預設）：看不到任何財務工具。
- 'all'：看全部財務（如「會計層」：跨 BU 財務全可見、但 HR 仍移除）。
- 'own_bu'：只看自己 BU 的財務。**需 #11 對財務「讀」做 BU-scoping 才安全**；在 #11 落地前
  apply_floor_policy 對 own_bu fail-closed＝等同 none（不暴露未過濾的跨 BU 財務讀）。
"""
import json
import os
from dataclasses import dataclass


@dataclass
class FloorConfig:
    floor: str
    business_units: list        # 此層可碰哪些事業體（[] = 未指定）
    financial_visibility: str   # 'none' | 'own_bu' | 'all'
    role: str                   # 'boss' | 'manager' | 'staff'
    escalation_target: str      # floor 名 / line_user_id / 'boss'
    department: str             # 人看的部門標籤
    source: str                 # 'map' | 'default-full' | 'default-restricted'


def _map_path() -> str:
    """floor-map.json 路徑：SME_FLOOR_MAP env 優先，否則 SME_DB_PATH 同目錄的 floor-map.json。"""
    env = os.environ.get("SME_FLOOR_MAP", "").strip()
    if env:
        return env
    db = os.environ.get("SME_DB_PATH", "").strip()
    if db:
        return os.path.join(os.path.dirname(db), "floor-map.json")
    return ""


def load_floor_map() -> dict:
    """讀 floor-map.json，回 {floor_name: {config}}。缺檔/壞檔 → {}（走安全預設）。
    支援頂層 {"floors": {...}} 或直接 {floor: {...}}。"""
    p = _map_path()
    if not p:
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    floors = data.get("floors", data)
    return floors if isinstance(floors, dict) else {}


def get_floor_config(floor: str) -> FloorConfig:
    """解析某 floor 的能力設定。有 floor-map 條目用條目；否則安全預設：
    - 全權限層('' / 'confidential')：financial 'all'、role 'boss'。
    - 其餘（含 '__unexpanded__' fail-closed）：financial 'none'、role 'staff'、上報 'boss'。
    """
    fmap = load_floor_map()
    entry = fmap.get(floor) if isinstance(fmap, dict) else None
    if isinstance(entry, dict):
        return FloorConfig(
            floor=floor,
            business_units=entry.get("business_units") or [],
            financial_visibility=(entry.get("financial_visibility") or "none").strip(),
            role=(entry.get("role") or "staff").strip(),
            escalation_target=(entry.get("escalation_target") or "boss").strip(),
            department=entry.get("department") or "",
            source="map",
        )
    # 無設定 → 安全預設。FULL_ACCESS_FLOORS lazy import（避免與 floor_policy 載入時循環）
    from shared.floor_policy import FULL_ACCESS_FLOORS
    if floor in FULL_ACCESS_FLOORS:
        return FloorConfig(floor, [], "all", "boss", "boss", "(全權限層)", "default-full")
    return FloorConfig(floor, [], "none", "staff", "boss", "", "default-restricted")

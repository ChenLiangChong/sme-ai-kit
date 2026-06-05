"""去識別化自檢（legal-admin 信任/稽核）：純函式字串比對工具。

威脅模型與誠實邊界（**務必如實回報、不可宣稱「不可能外流」**）：
- 律所把時限寫進「外部行事曆 MCP」（Google Calendar 等）。事件文字應去識別化（只放案件代號 + 期限
  類型 + 日期、不放當事人姓名 / 案由）。風險＝ agent 誤把當事人名塞進事件文字 → 外洩到第三方行事曆。
- 本模組只能做兩件事：(1) 寫出去「之前」比對提議文字有無命中已知當事人名（advisory 擋 + 留底）；
  (2) 事後掃 interaction_log 有無當事人名漏進我方紀錄。
- **攔不到的**：外部行事曆 server 端實際寫入引擎在我方 sandbox 外，本檢查若被略過（agent 不呼叫）、
  或當事人名以本表未涵蓋的寫法出現，仍會外流。故只可說「已比對已知當事人名並留底」、
  **絕不可說「保證不外流 / 不可能外流」**。

純字串比對（無 NLP）：寧可誤報（多擋）、不可漏報靜默放行＝符合反捏造 / fail-toward 精神。
"""
import re

# 當事人名常見分隔（一個 client_name 欄可能寫多名：「王大明、李小華」「甲/乙」等）
_NAME_SPLIT_RE = re.compile(r"[、,，/／;；\s]+")


def extract_party_names(client_name, title=None) -> list:
    """從 matter 的 client_name（必要時含 title）抽出「應去識別化的當事人名 token」。

    - client_name 以常見分隔切多名；保留長度 >= 2 的 token（單字易誤報、且中文姓名多 2~4 字）。
    - title（案由）預設**不**納入比對來源（案由常為通案描述、納入會大量誤報）；caller 確有需要再傳。
    回 token list（去重、保序）。
    """
    seen = []
    for src in (client_name, title):
        if not src or not str(src).strip():
            continue
        for tok in _NAME_SPLIT_RE.split(str(src).strip()):
            tok = tok.strip()
            if len(tok) >= 2 and tok not in seen:
                seen.append(tok)
    return seen


def scan_text_for_names(text, names) -> list:
    """提議文字 text 是否命中 names 中任一當事人名。回命中的 name list（保序去重）。
    純子字串比對（case-sensitive，中文無大小寫）；空 text/names → 空 list。"""
    if not text or not names:
        return []
    s = str(text)
    hits = []
    for n in names:
        if n and n not in hits and n in s:
            hits.append(n)
    return hits

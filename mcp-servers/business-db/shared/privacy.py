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


# ───────────────── 匯出邊界去識別化（F-P2-WIN-2、pleading 回寫 gate 用）─────────────────

# 對造名：matter.title 慣用寫法「…（對造：盛康建設）」「(對造:沅泰物流)」。只抽「對造」明示標記後
# 的 token（title 其餘部分是案由通案描述、整段納入會大量誤報——與 extract_party_names 同取捨）。
_OPPOSING_RE = re.compile(r"對造[方]?\s*[:：]\s*([^)）(（,，、;；\s]{2,64})")

# 法院名（泛用 pattern）：臺灣臺中地方法院 / 臺中地院 / 高等法院臺中分院 / 臺中高分院 / 智慧財產及商業法院…
# 誠實邊界：涵蓋常見寫法、不是完備法院清單；未涵蓋寫法仍會漏。單獨「法院」二字（如「法院裁定」）不命中。
_COURT_GENERIC_RE = re.compile(
    r"(?:[臺台]灣)?[一-鿿]{1,4}(?:地方|高等|最高)法院(?:[一-鿿]{1,4}分院)?"
    r"|[一-鿿]{2}地院"
    r"|[一-鿿]{2}高分院"
    r"|智慧財產及商業法院"
)


def extract_opposing_names(title) -> list:
    """從 matter.title（案由）抽「對造：XXX」明示標記的對造名 token（去重、保序）。"""
    if not title or not str(title).strip():
        return []
    seen = []
    for tok in _OPPOSING_RE.findall(str(title)):
        tok = tok.strip()
        if len(tok) >= 2 and tok not in seen:
            seen.append(tok)
    return seen


def deidentify_for_export(text, party_tokens, court_tokens) -> tuple:
    """把「要送出我方邊界的自由文字」去識別化：已知當事人/對造名→「當事人」、已知法院名＋泛用法院
    pattern→「法院」。回 (清理後文字, 命中token數)。

    誠實邊界（同 screen_calendar_text）：只擋「已知」當事人名（matter 欄位可得）與常見法院寫法；
    當事人名以未涵蓋寫法出現仍會漏——**絕不可宣稱「保證不外流」**。純字串取代、無 NLP；
    寧可多擋（誤報＝文字變泛稱、無害）、不可漏報靜默放行。
    """
    if not text:
        return text, 0
    s = str(text)
    n_hits = 0
    for tok in sorted({t for t in (party_tokens or []) if t and len(t) >= 2}, key=len, reverse=True):
        if tok in s:
            s = s.replace(tok, "當事人")
            n_hits += 1
    for tok in sorted({t for t in (court_tokens or []) if t and len(t) >= 2}, key=len, reverse=True):
        if tok in s:
            s = s.replace(tok, "法院")
            n_hits += 1
    s, n_generic = _COURT_GENERIC_RE.subn("法院", s)
    n_hits += n_generic
    return s, n_hits

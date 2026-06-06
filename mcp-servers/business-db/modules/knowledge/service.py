"""Knowledge service — rules / decisions / interactions / context summary 業務邏輯。

層次邊界（P2.12 partial split，codex 建議路線）：
- knowledge 是 cross-cutting read model（rule_relations + superseded_by + cross-entity refs）
- 強拆 tools/service/repository 三層會產生大量薄 SQL wrapper、無實質好處
- 採 partial split：tools 薄殼 / service 含業務邏輯 + SQL（不抽 repository）
- 寫入流程升級到 with transaction()，與 P2.1-P2.11 一致
"""
import json
import sqlite3
from collections import OrderedDict, defaultdict
from datetime import datetime, timedelta

from shared.auth import _check_permission, _resolve_actor_label, writer_or_error
from shared.business_units import _validate_business_unit
from shared.db import _now, get_db, transaction
from shared.utils import _like_param

from modules.approvals import service as approvals_service

_KNOWN_CATEGORIES = [
    "hr", "pricing", "return_policy", "supplier", "customer_service",
    "inventory", "finance", "sop", "brand", "general",
]


# ============================================================
# store_fact
# ============================================================

def store_fact(
    category: str,
    title: str,
    content: str,
    source_type: str,
    source_quote: str,
    set_by: str,
    business_unit: str,
    confidential: bool,
    related_rule_ids: list[int],
) -> str:
    if source_type not in ("explicit", "observed", "inferred"):
        return "ERROR: source_type 必須是 explicit, observed, 或 inferred"
    if source_type == "explicit" and not source_quote.strip():
        return "ERROR: explicit 規則必須附上 source_quote（老闆的原話），不可省略"

    with transaction() as db:
        # actor fail-closed（反捏造核心、#10）：在任何 business_rules 寫入「之前」解析可信寫入者。
        # floored session 取 line-channel verified 員工名（忽略 agent 自填的 set_by）、operator 用傳入值；
        # floored 但查無 verified LINE 脈絡 → 擋下。防員工偽造 set_by='老闆' + 假引言寫成「老闆指示」。
        actor, err = writer_or_error(db, set_by)
        if err:
            return err

        # 正式規則需 manager（codex 複審第二輪殘留 finding）：writer_or_error 只擋「偽造他人名」、
        # 但 verified 的 basic 基層員工仍能寫 source_type='explicit'（會被當老闆正式指示 SOP）。
        # explicit 規則寫入前再加 manager gate fail-closed（floored basic 擋下、operator/manager+ 放行）；
        # source_type='observed'/'inferred'（觀察慣例 / AI 推斷）維持 basic 可寫、不阻一般知識沉澱。
        # 比照 approve_leave：非全權限層才驗（_check_permission 傳 "" → floored 取 verified user_id）；
        # operator（無 SME_FLOOR、is_full_access）放行＝受信任開發 / 老闆層。set_by 是名字非 user_id、
        # 不能拿去 _check_permission 查 line_user_id（會誤擋 operator），故走 floor gate。
        from shared.floor_policy import is_full_access
        if source_type == "explicit" and not is_full_access():
            perm_err = _check_permission(db, "", "manager")
            if perm_err:
                return (
                    f"ERROR: 寫入正式規則（source_type=explicit）需 manager 以上權限"
                    f"（{perm_err.removeprefix('ERROR: ')}）。"
                    "若是觀察到的慣例請用 source_type='observed'、AI 推斷用 'inferred'。"
                )

        like = _like_param(title)
        if business_unit:
            conflicts = db.execute(
                "SELECT id, title, content FROM business_rules "
                "WHERE category = ? AND superseded_by IS NULL "
                "AND (business_unit = ? OR business_unit IS NULL OR business_unit = '') "
                "AND (title LIKE ? OR content LIKE ?)",
                (category, business_unit, like, like),
            ).fetchall()
        else:
            conflicts = db.execute(
                "SELECT id, title, content FROM business_rules "
                "WHERE category = ? AND superseded_by IS NULL "
                "AND (title LIKE ? OR content LIKE ?)",
                (category, like, like),
            ).fetchall()

        warning = ""
        if conflicts:
            conflict_list = "\n".join(
                f"  - [#{r['id']}] {r['title']}: {r['content'][:80]}"
                for r in conflicts[:5]
            )
            warning = (
                f"\n注意：發現 {len(conflicts)} 條可能衝突的規則：\n{conflict_list}\n"
                "如需取代舊規則，請用 update_rule 工具。"
            )

        cursor = db.execute(
            "INSERT INTO business_rules "
            "(category, title, content, source_type, source_quote, set_by, business_unit, confidential) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (category, title, content, source_type, source_quote.strip() or None,
             actor or None, business_unit or None, 1 if confidential else 0),
        )
        rule_id = cursor.lastrowid

        db.execute(
            "INSERT INTO interaction_log "
            "(actor, action, target_type, target_id, detail, business_unit) "
            "VALUES (?,?,?,?,?,?)",
            (actor or "system", "rule_created", "rule", rule_id,
             f"[{category}] {title}", business_unit or None),
        )

        # 自動建立交叉引用
        if conflicts:
            for cr in conflicts[:5]:
                a, b = min(rule_id, cr["id"]), max(rule_id, cr["id"])
                try:
                    db.execute(
                        "INSERT INTO rule_relations "
                        "(rule_id_a, rule_id_b, relation_type, created_by) "
                        "VALUES (?,?,?,?)",
                        (a, b, "related", "auto"),
                    )
                except sqlite3.IntegrityError:
                    pass

        # 手動關聯
        linked = []
        for rid in (related_rule_ids or []):
            if rid == rule_id:
                continue
            exists = db.execute(
                "SELECT id, title FROM business_rules "
                "WHERE id=? AND superseded_by IS NULL",
                (rid,),
            ).fetchone()
            if not exists:
                continue
            a, b = min(rule_id, rid), max(rule_id, rid)
            try:
                db.execute(
                    "INSERT INTO rule_relations "
                    "(rule_id_a, rule_id_b, relation_type, created_by) "
                    "VALUES (?,?,?,?)",
                    (a, b, "related", actor or "system"),
                )
                linked.append(f"#{rid} {exists['title']}")
            except sqlite3.IntegrityError:
                pass

        bu_warn = _validate_business_unit(db, business_unit)

    msg = f"已儲存規則 #{rule_id} [{category}] {title}" + warning + bu_warn
    if linked:
        msg += f"\n   關聯：{', '.join(linked)}"
    return msg


# ============================================================
# query_knowledge
# ============================================================

def query_knowledge(question: str, category: str, business_unit: str) -> str:
    # floor-aware（決策 #168）：非全權限層過濾 confidential=1 的規則 + 交叉引用
    from shared.floor_policy import is_full_access
    fa = is_full_access()
    conf_filter = "" if fa else " AND confidential = 0"
    conf_filter_rel = "" if fa else " AND ba.confidential = 0 AND bb.confidential = 0"
    like = _like_param(question)
    db = get_db()
    try:
        results = []

        if category and business_unit:
            bu_filter = (
                "WHERE category = ? AND superseded_by IS NULL "
                "AND (business_unit = ? OR business_unit IS NULL OR business_unit = '') "
                "AND (title LIKE ? OR content LIKE ?)"
            )
            params = [category, business_unit, like, like]
        elif category:
            bu_filter = (
                "WHERE category = ? AND superseded_by IS NULL "
                "AND (title LIKE ? OR content LIKE ?)"
            )
            params = [category, like, like]
        elif business_unit:
            bu_filter = (
                "WHERE superseded_by IS NULL "
                "AND (business_unit = ? OR business_unit IS NULL OR business_unit = '') "
                "AND (title LIKE ? OR content LIKE ?)"
            )
            params = [business_unit, like, like]
        else:
            bu_filter = "WHERE superseded_by IS NULL AND (title LIKE ? OR content LIKE ?)"
            params = [like, like]

        rules = db.execute(
            f"SELECT id, category, title, content, source_type, set_by, business_unit, created_at "
            f"FROM business_rules {bu_filter}{conf_filter} LIMIT 10",
            params,
        ).fetchall()

        if rules:
            results.append("## 企業規則")
            for r in rules:
                src = {
                    "explicit": "老闆指示", "observed": "觀察慣例", "inferred": "AI推斷"
                }.get(r["source_type"], r["source_type"])
                bu_label = f" [{r['business_unit']}]" if r["business_unit"] else " [全域]"
                results.append(
                    f"- **[#{r['id']}] {r['title']}** [{r['category']}]{bu_label} ({src})"
                )
                results.append(f"  {r['content'][:200]}")

            rule_ids = [r["id"] for r in rules]
            placeholders = ",".join("?" * len(rule_ids))
            relations = db.execute(
                f"SELECT rr.relation_type, "
                f"  ba.id as id_a, ba.title as title_a, ba.content as content_a, ba.category as cat_a, "
                f"  bb.id as id_b, bb.title as title_b, bb.content as content_b, bb.category as cat_b "
                f"FROM rule_relations rr "
                f"JOIN business_rules ba ON rr.rule_id_a = ba.id "
                f"JOIN business_rules bb ON rr.rule_id_b = bb.id "
                f"WHERE (rr.rule_id_a IN ({placeholders}) OR rr.rule_id_b IN ({placeholders})) "
                f"AND ba.superseded_by IS NULL AND bb.superseded_by IS NULL "
                f"{conf_filter_rel} "
                f"LIMIT 10",
                rule_ids + rule_ids,
            ).fetchall()
            if relations:
                type_labels = {
                    "related": "相關", "depends_on": "依賴", "conflicts_with": "衝突",
                }
                main_id_set = set(rule_ids)
                seen_others = set()
                items = []
                for rel in relations:
                    label = type_labels.get(rel["relation_type"], rel["relation_type"])
                    if rel["id_a"] in main_id_set and rel["id_b"] not in main_id_set:
                        other_id, other_title, other_content, other_cat = (
                            rel["id_b"], rel["title_b"], rel["content_b"], rel["cat_b"]
                        )
                        main_id = rel["id_a"]
                    elif rel["id_b"] in main_id_set and rel["id_a"] not in main_id_set:
                        other_id, other_title, other_content, other_cat = (
                            rel["id_a"], rel["title_a"], rel["content_a"], rel["cat_a"]
                        )
                        main_id = rel["id_b"]
                    else:
                        items.append(
                            f"- [{label}] [#{rel['id_a']}] {rel['title_a']} ↔ "
                            f"[#{rel['id_b']}] {rel['title_b']}"
                        )
                        continue
                    if other_id in seen_others:
                        continue
                    seen_others.add(other_id)
                    snippet = (other_content or "")[:160].replace("\n", " ")
                    items.append(
                        f"- [{label} ← #{main_id}] [#{other_id}] {other_title} "
                        f"[{other_cat}]\n  {snippet}"
                    )
                if items:
                    results.append("\n## 相關規則（交叉引用）")
                    results.extend(items)

        # 跨域營運資料（任務／客戶／庫存）這三段無 server-side BU 過濾（codex HIGH）：
        # 非全權限層用知識工具就能撈到跨 BU 營運資料 = 越權。fail-safe 早退、只回知識規則段。
        # （列級 BU 過濾 #11 尚未落地、在那之前一律 drop、不靠 caller 自帶 BU。）
        if fa:
            tasks = db.execute(
                "SELECT id, title, description, assignee, status, due_date FROM tasks "
                "WHERE title LIKE ? OR description LIKE ? LIMIT 5",
                (like, like),
            ).fetchall()
            if tasks:
                results.append("\n## 相關任務")
                for t in tasks:
                    status_icon = {
                        "pending": "[待處理]", "in_progress": "[進行中]",
                        "done": "[已完成]", "cancelled": "[已取消]",
                    }.get(t["status"], "")
                    results.append(
                        f"- {status_icon} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}"
                    )

            customers = db.execute(
                "SELECT id, name, phone, tags, notes FROM customers "
                "WHERE name LIKE ? OR notes LIKE ? OR tags LIKE ? LIMIT 5",
                (like, like, like),
            ).fetchall()
            if customers:
                results.append("\n## 相關客戶")
                for c in customers:
                    results.append(f"- **{c['name']}** {c['phone'] or ''} {c['tags'] or ''}")

            inventory = db.execute(
                "SELECT id, sku, name, current_stock, min_stock, unit FROM inventory "
                "WHERE name LIKE ? OR sku LIKE ? OR category LIKE ? LIMIT 5",
                (like, like, like),
            ).fetchall()
            if inventory:
                results.append("\n## 相關庫存")
                for i in inventory:
                    alert = " 注意：低於安全庫存" if i["current_stock"] <= i["min_stock"] else ""
                    results.append(
                        f"- [{i['sku']}] {i['name']}: {i['current_stock']}{i['unit']}{alert}"
                    )

        if not results:
            return f"找不到與「{question}」相關的資料。"
        return "\n".join(results)
    finally:
        db.close()


# ============================================================
# update_rule
# ============================================================

def update_rule(
    rule_id: int, new_content: str, reason: str, actor_user_id: str
) -> str:
    with transaction() as db:
        perm_err = _check_permission(db, actor_user_id, "admin")
        if perm_err:
            return perm_err
        old = db.execute(
            "SELECT * FROM business_rules WHERE id = ? AND superseded_by IS NULL",
            (rule_id,),
        ).fetchone()
        if not old:
            return f"ERROR: 找不到有效規則 #{rule_id}（可能已被取代或不存在）"

        # Transactional flip：避免 idx_rules_unique_active 衝突
        # 帶入 old["confidential"]（codex HIGH）：不帶會吃 migration 006 預設 0、
        # 把原本機密規則降級成公開可查、連全權限層也誤洩。
        cursor = db.execute(
            "INSERT INTO business_rules "
            "(category, title, content, source_type, source_quote, set_by, business_unit, confidential, superseded_by) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (old["category"], old["title"], new_content, old["source_type"],
             old["source_quote"], old["set_by"], old["business_unit"],
             old["confidential"], rule_id),
        )
        new_id = cursor.lastrowid
        db.execute(
            "UPDATE business_rules SET superseded_by = ? WHERE id = ?",
            (new_id, rule_id),
        )
        db.execute(
            "UPDATE business_rules SET superseded_by = NULL WHERE id = ?", (new_id,)
        )

        # 具名 actor（codex MED、#10）：已過 admin gate、audit 不再記 'system'，
        # 用 _resolve_actor_label 寫 verified 操作者名（floored 取 verified 員工名、operator 用傳入值）。
        audit_actor = _resolve_actor_label(db, actor_user_id)
        db.execute(
            "INSERT INTO interaction_log "
            "(actor, action, target_type, target_id, detail, business_unit) "
            "VALUES (?,?,?,?,?,?)",
            (audit_actor, "rule_updated", "rule", new_id,
             f"取代 #{rule_id}，原因：{reason}", old["business_unit"]),
        )

        # 遷移交叉引用
        old_rels = db.execute(
            "SELECT id, rule_id_a, rule_id_b, relation_type, created_by "
            "FROM rule_relations WHERE rule_id_a = ? OR rule_id_b = ?",
            (rule_id, rule_id),
        ).fetchall()
        for rel in old_rels:
            other = rel["rule_id_b"] if rel["rule_id_a"] == rule_id else rel["rule_id_a"]
            db.execute("DELETE FROM rule_relations WHERE id = ?", (rel["id"],))
            if rel["relation_type"] in ("related", "conflicts_with"):
                ra, rb = min(new_id, other), max(new_id, other)
            elif rel["rule_id_a"] == rule_id:
                ra, rb = new_id, other
            else:
                ra, rb = other, new_id
            try:
                db.execute(
                    "INSERT INTO rule_relations "
                    "(rule_id_a, rule_id_b, relation_type, created_by) "
                    "VALUES (?,?,?,?)",
                    (ra, rb, rel["relation_type"], rel["created_by"]),
                )
            except sqlite3.IntegrityError:
                pass

        relations = db.execute(
            "SELECT rr.relation_type, "
            "  CASE WHEN rr.rule_id_a = ? THEN rr.rule_id_b ELSE rr.rule_id_a END as related_id, "
            "  br.title, br.category "
            "FROM rule_relations rr "
            "JOIN business_rules br ON br.id = "
            "  CASE WHEN rr.rule_id_a = ? THEN rr.rule_id_b ELSE rr.rule_id_a END "
            "WHERE (rr.rule_id_a = ? OR rr.rule_id_b = ?) AND br.superseded_by IS NULL",
            (new_id, new_id, new_id, new_id),
        ).fetchall()

    related_warning = ""
    if relations:
        type_labels = {"related": "相關", "depends_on": "依賴", "conflicts_with": "衝突"}
        rel_list = "\n".join(
            f"  - [#{r['related_id']}] {r['title']} [{r['category']}]"
            f"（{type_labels.get(r['relation_type'], r['relation_type'])}）"
            for r in relations[:5]
        )
        related_warning = (
            f"\n\n以下 {len(relations)} 條關聯規則可能也需要檢查：\n{rel_list}"
        )

    return f"規則已更新：#{rule_id} → #{new_id}\n原因：{reason}" + related_warning


# ============================================================
# knowledge_changelog
# ============================================================

def knowledge_changelog(days: int) -> str:
    db = get_db()
    try:
        rows = db.execute(
            "SELECT il.action, il.detail, il.created_at, il.target_id, "
            "  br.category, br.title "
            "FROM interaction_log il "
            "LEFT JOIN business_rules br ON il.target_id = br.id AND il.target_type = 'rule' "
            "WHERE il.action IN ('rule_created', 'rule_updated') "
            "AND il.created_at >= datetime('now', 'localtime', '-' || ? || ' days') "
            "ORDER BY il.created_at DESC",
            (str(days),),
        ).fetchall()

        if not rows:
            return f"最近 {days} 天沒有知識變更記錄。"

        by_date: dict[str, list] = OrderedDict()
        total_created = total_updated = 0
        for r in rows:
            date_key = r["created_at"][:10]
            by_date.setdefault(date_key, []).append(r)
            if r["action"] == "rule_created":
                total_created += 1
            else:
                total_updated += 1

        lines = [f"## 知識變更日誌（最近 {days} 天）\n"]
        today = _now()[:10]
        for date_key, entries in by_date.items():
            label = "（今天）" if date_key == today else ""
            lines.append(f"### {date_key}{label}")
            created = [e for e in entries if e["action"] == "rule_created"]
            updated = [e for e in entries if e["action"] == "rule_updated"]
            if created:
                lines.append(f"新增 {len(created)} 條：")
                for e in created:
                    cat = f"[{e['category']}] " if e["category"] else ""
                    title = e["title"] or e["detail"] or ""
                    lines.append(f"- [#{e['target_id']}] {cat}{title}")
            if updated:
                lines.append(f"更新 {len(updated)} 條：")
                for e in updated:
                    cat = f"[{e['category']}] " if e["category"] else ""
                    title = e["title"] or ""
                    detail = e["detail"] or ""
                    lines.append(f"- [#{e['target_id']}] {cat}{title} — {detail}")
            lines.append("")

        lines.append(f"---\n共計：新增 {total_created} 條 | 更新 {total_updated} 條")
        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# lint_knowledge
# ============================================================

def lint_knowledge(checks: str) -> str:
    requested = {c.strip() for c in checks.split(",")}
    run_all = "all" in requested

    db = get_db()
    try:
        sections = []
        suggestions = []

        # 1. 矛盾
        if run_all or "contradictions" in requested:
            rules = db.execute(
                "SELECT id, category, title, content FROM business_rules "
                "WHERE superseded_by IS NULL ORDER BY category",
            ).fetchall()
            by_cat: dict[str, list] = defaultdict(list)
            for r in rules:
                by_cat[r["category"]].append(r)

            pairs = []
            for cat, cat_rules in by_cat.items():
                for i, a in enumerate(cat_rules):
                    a_key = a["title"].strip()
                    for b in cat_rules[i + 1:]:
                        b_key = b["title"].strip()
                        if len(a_key) < 4 and len(b_key) < 4:
                            hit = a_key == b_key
                        elif len(a_key) < 4:
                            hit = a_key in b["title"]
                        elif len(b_key) < 4:
                            hit = b_key in a["title"]
                        else:
                            a_in_b = a_key in (b["title"] + " " + b["content"])
                            b_in_a = b_key in (a["title"] + " " + a["content"])
                            hit = a_in_b or b_in_a
                        if hit:
                            pairs.append((a, b))

            if pairs:
                sections.append(f"### 潛在矛盾（{len(pairs)} 組）")
                for a, b in pairs[:10]:
                    sections.append(
                        f"- [#{a['id']}] {a['title']} ↔ [#{b['id']}] {b['title']} [{a['category']}]"
                    )
                    sections.append(f"  #{a['id']}: {a['content'][:80]}")
                    sections.append(f"  #{b['id']}: {b['content'][:80]}")
                suggestions.append(f"檢討 {len(pairs)} 組可能矛盾的規則")
            else:
                sections.append("### 潛在矛盾\n未發現矛盾")

        # 2. 過期
        if run_all or "stale" in requested:
            stale = db.execute(
                "SELECT id, category, title, created_at FROM business_rules "
                "WHERE superseded_by IS NULL "
                "AND created_at < datetime('now', 'localtime', '-6 months') "
                "ORDER BY created_at",
            ).fetchall()

            if stale:
                sections.append(f"\n### 可能過期（{len(stale)} 條，超過 6 個月未更新）")
                for r in stale[:15]:
                    sections.append(
                        f"- [#{r['id']}] {r['title']} [{r['category']}] — "
                        f"建立於 {r['created_at'][:10]}"
                    )
                suggestions.append(f"檢討 {len(stale)} 條可能過期的規則")
            else:
                sections.append("\n### 過期檢查\n所有規則都在 6 個月內")

        # 3. 覆蓋
        if run_all or "coverage" in requested:
            counts = db.execute(
                "SELECT category, COUNT(*) as cnt FROM business_rules "
                "WHERE superseded_by IS NULL GROUP BY category",
            ).fetchall()
            count_map = {r["category"]: r["cnt"] for r in counts}

            sections.append("\n### 覆蓋分析")
            empty_cats = []
            low_cats = []
            for cat in _KNOWN_CATEGORIES:
                cnt = count_map.get(cat, 0)
                if cnt == 0:
                    sections.append(f"- {cat}: 0 條（空白）")
                    empty_cats.append(cat)
                elif cnt <= 2:
                    sections.append(f"- 注意：{cat}: {cnt} 條（偏少）")
                    low_cats.append(cat)
                else:
                    sections.append(f"- {cat}: {cnt} 條")
            for cat, cnt in count_map.items():
                if cat not in _KNOWN_CATEGORIES:
                    sections.append(f"- {cat}: {cnt} 條（自訂類別）")

            if empty_cats:
                suggestions.append(f"補充 {', '.join(empty_cats)} 類別的規則")
            if low_cats:
                suggestions.append(f"充實 {', '.join(low_cats)} 類別（目前偏少）")

        # 4. 孤立鏈
        if run_all or "orphaned" in requested:
            orphaned = db.execute(
                "SELECT id, title, superseded_by FROM business_rules "
                "WHERE superseded_by IS NOT NULL "
                "AND superseded_by NOT IN (SELECT id FROM business_rules)",
            ).fetchall()

            if orphaned:
                sections.append(f"\n### 孤立鏈（{len(orphaned)} 條）")
                for r in orphaned[:10]:
                    sections.append(
                        f"- [#{r['id']}] {r['title']} → "
                        f"superseded_by #{r['superseded_by']}（不存在）"
                    )
                suggestions.append(f"修復 {len(orphaned)} 條孤立引用")
            else:
                sections.append("\n### 孤立鏈檢查\n資料完整性正常")

        if suggestions:
            sections.append("\n### 建議")
            for s in suggestions:
                sections.append(f"- {s}")

        return "## 知識庫健檢報告\n\n" + "\n".join(sections)
    finally:
        db.close()


# ============================================================
# link_rules
# ============================================================

def link_rules(rule_id_a: int, rule_id_b: int, relation_type: str) -> str:
    if relation_type not in ("related", "depends_on", "conflicts_with"):
        return "ERROR: relation_type 必須是 related, depends_on, 或 conflicts_with"
    if rule_id_a == rule_id_b:
        return "ERROR: 不能將規則與自身建立關聯"

    with transaction() as db:
        a = db.execute(
            "SELECT id, title, business_unit FROM business_rules "
            "WHERE id = ? AND superseded_by IS NULL",
            (rule_id_a,),
        ).fetchone()
        b = db.execute(
            "SELECT id, title, business_unit FROM business_rules "
            "WHERE id = ? AND superseded_by IS NULL",
            (rule_id_b,),
        ).fetchone()
        if not a:
            return f"ERROR: 找不到有效規則 #{rule_id_a}"
        if not b:
            return f"ERROR: 找不到有效規則 #{rule_id_b}"

        ra, rb = rule_id_a, rule_id_b
        if relation_type in ("related", "conflicts_with") and ra > rb:
            ra, rb = rb, ra

        try:
            db.execute(
                "INSERT INTO rule_relations "
                "(rule_id_a, rule_id_b, relation_type, created_by) "
                "VALUES (?,?,?,?)",
                (ra, rb, relation_type, "manual"),
            )
            db.execute(
                "INSERT INTO interaction_log "
                "(actor, action, target_type, target_id, detail, business_unit) "
                "VALUES (?,?,?,?,?,?)",
                ("system", "rule_linked", "rule", ra,
                 f"#{ra} ↔ #{rb} ({relation_type})", a["business_unit"]),
            )
        except sqlite3.IntegrityError:
            return f"關聯已存在：#{ra} ↔ #{rb} ({relation_type})"

    type_label = {
        "related": "相關", "depends_on": "依賴", "conflicts_with": "衝突",
    }.get(relation_type, relation_type)
    return (
        f"已建立關聯：[#{ra}] {a['title']} ↔ [#{rb}] {b['title']} （{type_label}）"
    )


# ============================================================
# get_rule / get_rule_relations
# ============================================================

def get_rule(rule_id: int) -> str:
    db = get_db()
    try:
        r = db.execute(
            "SELECT * FROM business_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        if not r:
            return f"ERROR: 找不到規則 #{rule_id}"
        # 機密規則對非全權限層等同不存在（決策 #168、不洩漏存在性）
        from shared.floor_policy import is_full_access
        if r["confidential"] and not is_full_access():
            return f"ERROR: 找不到規則 #{rule_id}"

        superseded_str = ""
        if r["superseded_by"]:
            sup = db.execute(
                "SELECT title FROM business_rules WHERE id = ?", (r["superseded_by"],)
            ).fetchone()
            superseded_str = (
                f"\n- 已被取代：[#{r['superseded_by']}] "
                f"{sup['title'] if sup else '（已刪除）'}"
            )

        supersedes = db.execute(
            "SELECT id, title FROM business_rules WHERE superseded_by = ?",
            (rule_id,),
        ).fetchall()
        supersedes_str = ""
        if supersedes:
            sup_lines = [f"  - [#{s['id']}] {s['title']}" for s in supersedes]
            supersedes_str = "\n- 取代了：\n" + "\n".join(sup_lines)

        source_quote_str = (
            f"\n- 老闆原話：「{r['source_quote']}」" if r["source_quote"] else ""
        )

        return (
            f"## 規則 #{rule_id}：{r['title']} [{r['category']}]\n"
            f"- 來源類型：{r['source_type'] or '未指定'}\n"
            f"- 設定者：{r['set_by'] or '未知'}\n"
            f"- 事業體：{r['business_unit'] or '全域'}\n"
            f"- 建立：{r['created_at']}"
            f"{source_quote_str}"
            f"{superseded_str}"
            f"{supersedes_str}\n"
            f"\n### 內容\n{r['content']}"
        )
    finally:
        db.close()


def get_rule_relations(rule_id: int) -> str:
    db = get_db()
    try:
        rule = db.execute(
            "SELECT id, title, category, confidential FROM business_rules WHERE id = ?", (rule_id,)
        ).fetchone()
        if not rule:
            return f"ERROR: 找不到規則 #{rule_id}"
        # 機密規則對非全權限層等同不存在；關聯也濾掉機密的另一端（決策 #168）
        from shared.floor_policy import is_full_access
        fa = is_full_access()
        if rule["confidential"] and not fa:
            return f"ERROR: 找不到規則 #{rule_id}"

        relations = db.execute(
            "SELECT rr.relation_type, "
            "  ba.id as id_a, ba.title as title_a, ba.category as cat_a, "
            "  bb.id as id_b, bb.title as title_b, bb.category as cat_b "
            "FROM rule_relations rr "
            "JOIN business_rules ba ON rr.rule_id_a = ba.id "
            "JOIN business_rules bb ON rr.rule_id_b = bb.id "
            "WHERE (rr.rule_id_a = ? OR rr.rule_id_b = ?) "
            "AND ba.superseded_by IS NULL AND bb.superseded_by IS NULL"
            + ("" if fa else " AND ba.confidential = 0 AND bb.confidential = 0"),
            (rule_id, rule_id),
        ).fetchall()

        if not relations:
            return f"規則 [#{rule_id}] {rule['title']} 沒有任何關聯。"

        type_labels = {"related": "相關", "depends_on": "依賴", "conflicts_with": "衝突"}
        lines = [f"## 規則 [#{rule_id}] {rule['title']} 的關聯\n"]
        for rel in relations:
            label = type_labels.get(rel["relation_type"], rel["relation_type"])
            if rel["id_a"] == rule_id:
                other_id, other_title, other_cat = rel["id_b"], rel["title_b"], rel["cat_b"]
            else:
                other_id, other_title, other_cat = rel["id_a"], rel["title_a"], rel["cat_a"]
            lines.append(f"- [{label}] [#{other_id}] {other_title} [{other_cat}]")

        return "\n".join(lines)
    finally:
        db.close()


# ============================================================
# get_context_summary — 啟動流程必跑（系統狀態總攬）
# ============================================================

def _date_reminders() -> list[str]:
    """月結／發薪／勞健保／報稅等日期提醒（純日曆推導、無 DB 機密）。各 floor 皆可見。"""
    today = datetime.now()
    day, month = today.day, today.month
    reminders: list[str] = []
    if day <= 5:
        reminders.append("每月 1-5 日：月結作業，確認上月帳務")
    if day in (4, 5):
        reminders.append("5 日前後：提醒發薪水")
    if 23 <= day <= 25:
        reminders.append("25 日前後：提醒繳勞健保")
    if month % 2 == 1 and 10 <= day <= 15:
        reminders.append(f"{month}/15：營業稅申報截止")
    if month == 5:
        reminders.append("5 月：營所稅 + 綜所稅申報")
    return reminders


def get_context_summary(scope: str) -> str:
    # floor-aware（決策 #166）：非全權限層（部門/受限）只回安全子集，不洩漏跨部門
    # 營運（訂單金額/客戶名/任務/審核/庫存/帳款）。BU-scoped 的「本層」區段待 #6
    # floor-map（dept→BU）後加回；在那之前 fail-safe 一律 drop。
    from shared.floor_policy import get_floor, is_full_access
    full_access = is_full_access()

    # codex P2.15：maintenance write 跟 read 顯式拆兩階段（不再用 hybrid transaction）
    # Phase 1：過期 stale approvals（with transaction）
    with transaction() as db:
        approvals_service.expire_stale_approvals(db)

    # Phase 2：純讀（get_db + close、無 write）
    db = get_db()
    try:
        sections = []

        # 公司資訊
        company = db.execute("SELECT * FROM company WHERE id = 1").fetchone()
        if company:
            sections.append(f"## {company['name']}（{company['industry'] or '未設定'}）")

        # ── floor gate（決策 #166）──────────────────────────────────
        # 非全權限層（部門/受限/__unexpanded__ fail-closed）：早退安全子集。
        # 早退在所有營運區段「之前」→ 日後新增區段預設「全權限限定」、不會誤洩漏。
        if not full_access:
            floor = get_floor()
            sections.append(
                f"\n_部門範圍精簡視圖（floor={floor or '?'}）：營運儀表板"
                f"（任務／訂單／帳款／庫存／待審／LINE 訊息）僅機密層與老闆可見。"
                f"需要本部門資料請直接詢問，或用帶 business_unit 的查詢工具。_"
            )
            # 全域企業規則（business_unit 為空 = 全公司共用 SOP、無 BU 機密）
            global_rules = db.execute(
                "SELECT category, title FROM business_rules "
                "WHERE superseded_by IS NULL AND (business_unit IS NULL OR business_unit = '') "
                "AND confidential = 0 "
                "ORDER BY created_at DESC LIMIT 10"
            ).fetchall()
            if global_rules:
                sections.append("\n## 公司規則（全域）")
                for r in global_rules:
                    sections.append(f"- [{r['category']}] {r['title']}")
            # 日期提醒（純日曆推導、無 DB 機密）
            reminders = _date_reminders()
            if reminders:
                sections.append("\n## 日期提醒")
                for r in reminders:
                    sections.append(f"- {r}")
            return "\n".join(sections)

        # 主管上報（#9/#173）：flusher 把 pending 推給主管；此處是全權限層的「保底拉取 + 卡關提醒」。
        # 放在全權限段最前（早退之後）＝部門層永遠看不到、老闆開機第一眼看得到。送不出/無收件人需處理。
        from shared.escalation import count_stuck_escalations
        stuck = count_stuck_escalations(db)
        if stuck["failed"] or stuck["no_recipient"]:
            sections.append("\n## 主管上報異常（需處理）")
            if stuck["failed"]:
                sections.append(
                    f"- {stuck['failed']} 筆送不出：主管可能未加 OA 好友／token 失效"
                    f"（查 pending_escalations status='failed'）"
                )
            if stuck["no_recipient"]:
                sections.append(
                    f"- {stuck['no_recipient']} 筆無收件人：請設老闆 LINE id"
                    f"（update_company(boss_line_id=...) 或建 role='boss' 員工）"
                )
        else:
            esc_pending = db.execute(
                "SELECT COUNT(*) c FROM pending_escalations WHERE status='pending'"
            ).fetchone()["c"]
            if esc_pending:
                sections.append(
                    f"\n## 主管上報\n- {esc_pending} 筆待送出（flusher 投遞中）"
                )

        # legal-admin 靜默失敗哨兵（#H1 時限掃描失聯 / #H2 待確認久未入庫）：全權限層開機第一眼看到。
        # 非律所場景（無時限、無待確認暫存）會自然全靜默、不污染一般 company-ops 開機。整段 try 包覆：
        # 哨兵是補強區、任何意外都不可拖垮核心儀表板。常數 SCAN_STALE_HOURS/WATCHDOG_STALE_HOURS 由
        # shared.deadlines 單一真相 import（不在此寫死、cross-file guard 綁死）。
        try:
            from shared.deadlines import (
                SCAN_STALE_HOURS,
                WATCHDOG_STALE_HOURS,
                check_scan_health,
            )
            health = check_scan_health(db)
            health_lines = []
            if health["scan_overdue"]:
                health_lines.append(
                    f"- [時限掃描失聯] 上次成功掃描 {health['last_scan_at'] or '無紀錄'}"
                    f"（已逾 {health['scan_age_hours']:.0f} 小時、超過 {SCAN_STALE_HOURS}h 門檻）。"
                    f"時限可能已停止倒數——請立即人工巡未結時限（list_upcoming_deadlines）、"
                    f"並檢查 scan_deadlines.py 的 cron 是否在跑"
                )
            elif health["scan_never"] and health["pending_deadlines"] > 0:
                health_lines.append(
                    f"- [時限掃描未啟用] 已有 {health['pending_deadlines']} 筆待處理時限卻無任何掃描紀錄。"
                    f"請部署 scan_deadlines.py cron（見 privacy-deploy）、否則時限不會自動倒數提醒"
                )
            if health["watchdog_overdue"]:
                health_lines.append(
                    f"- [監看 watchdog 失聯] 上次 {health['last_watchdog_at']}"
                    f"（已逾 {health['watchdog_age_hours']:.0f}h、超過 {WATCHDOG_STALE_HOURS}h）。"
                    f"時間驅動失聯告警可能失靈、請檢查 scan_heartbeat.py 的 cron"
                )
            elif health["watchdog_never"] and (
                health["pending_deadlines"] > 0 or not health["scan_never"]
            ):
                health_lines.append(
                    "- [監看 watchdog 未部署] 時間驅動失聯告警（scan_heartbeat.py）無執行紀錄、"
                    "建議補上 cron 以防掃描器靜默掛掉沒人知"
                )
            if health_lines:
                sections.append("\n## 時限系統健康（需處理）")
                sections.extend(health_lines)

            # #H2 待確認 backlog：抽出但人還沒一鍵確認入庫的時限（久未確認＝隱形漏掉風險）
            intake = db.execute(
                "SELECT COUNT(*) c, MIN(created_at) oldest "
                "FROM pending_intakes WHERE status='awaiting'"
            ).fetchone()
            if intake and intake["c"]:
                wait_txt = ""
                try:
                    o = datetime.strptime(str(intake["oldest"])[:19], "%Y-%m-%d %H:%M:%S")
                    wait_txt = f"、最久已等 {max(0.0, (datetime.now() - o).total_seconds() / 3600.0):.0f} 小時"
                except (ValueError, TypeError):
                    pass
                sections.append(
                    f"\n## 待確認時限（{intake['c']} 件尚未入庫{wait_txt}）"
                    f"\n- 抽出後還沒一鍵確認入庫的時限；久未確認可能漏掉。用 list_pending_intakes 查看，"
                    f"確認走 create_deadline(confirm_intake_id=)、不算了用 resolve_deadline_intake"
                )
        except Exception:
            pass  # 哨兵補強區失敗不影響核心儀表板

        # 待處理任務
        pending = db.execute(
            "SELECT id, title, assignee, priority, due_date FROM tasks "
            "WHERE status IN ('pending','in_progress') "
            "ORDER BY CASE priority WHEN 'urgent' THEN 0 WHEN 'normal' THEN 1 ELSE 2 END, "
            "due_date LIMIT ?",
            (20 if scope == "full" else 5,),
        ).fetchall()
        if pending:
            sections.append(f"\n## 待處理任務（{len(pending)} 項）")
            for t in pending:
                pri = {"urgent": "[急]", "normal": "[普通]", "low": "[低]"}.get(t["priority"], "")
                due = f" 截止:{t['due_date']}" if t["due_date"] else ""
                sections.append(
                    f"- {pri} [#{t['id']}] {t['title']} → {t['assignee'] or '未指派'}{due}"
                )

        # 等待審核
        approvals = db.execute(
            "SELECT id, type, summary, detail, requester, created_at, expires_at "
            "FROM approvals WHERE status = 'waiting' ORDER BY created_at",
        ).fetchall()
        if approvals:
            sections.append(f"\n## 等待審核（{len(approvals)} 項）")
            now = datetime.now()
            from modules.approvals.service import _extract_resume_action
            for a in approvals:
                detail_hint = ""
                if a["detail"]:
                    resume = _extract_resume_action(a["detail"])
                    if resume:
                        detail_hint = f" → 核准後執行 {resume}"
                    else:
                        # 非 JSON / 非 dict / 缺 resume_action → 印短摘要
                        detail_hint = f" | {a['detail'][:50]}"
                age_warning = ""
                try:
                    created = datetime.strptime(a["created_at"], "%Y-%m-%d %H:%M:%S")
                    hours_waiting = (now - created).total_seconds() / 3600
                    if hours_waiting > 48:
                        age_warning = f" 已等待 {int(hours_waiting)}h — 建議重新通知主管"
                except (ValueError, TypeError):
                    pass
                sections.append(
                    f"- [#{a['id']}] {a['type']}: {a['summary']} "
                    f"(申請人:{a['requester'] or '?'}){detail_hint}{age_warning}"
                )

        # 未處理 LINE 訊息
        queued = db.execute(
            "SELECT id, user_name, content, created_at FROM line_messages "
            "WHERE direction='inbound' AND status='queued' ORDER BY created_at",
        ).fetchall()
        if queued:
            sections.append(f"\n## 未處理 LINE 訊息（{len(queued)} 則）")
            for m in queued:
                sections.append(
                    f"- [{m['created_at']}] {m['user_name'] or '?'}: {m['content'][:100]}"
                )

        # 庫存警報
        alerts = db.execute(
            "SELECT sku, name, current_stock, min_stock, unit FROM inventory "
            "WHERE current_stock <= min_stock AND min_stock > 0",
        ).fetchall()
        if alerts:
            sections.append(f"\n## 庫存警報（{len(alerts)} 項）")
            for a in alerts:
                sections.append(
                    f"- [{a['sku']}] {a['name']}: 剩 {a['current_stock']}{a['unit']}"
                    f"（安全庫存 {a['min_stock']}）"
                )

        if scope == "full":
            rules_count = db.execute(
                "SELECT COUNT(*) as c FROM business_rules WHERE superseded_by IS NULL"
            ).fetchone()["c"]
            if rules_count:
                recent_rules = db.execute(
                    "SELECT category, title FROM business_rules WHERE superseded_by IS NULL "
                    "ORDER BY created_at DESC LIMIT 10"
                ).fetchall()
                sections.append(f"\n## 企業規則（共 {rules_count} 條有效）")
                for r in recent_rules:
                    sections.append(f"- [{r['category']}] {r['title']}")

            # active session handoff（含過期警告）
            handoff = db.execute(
                "SELECT id, summary, pending_items, created_at FROM session_handoffs "
                "WHERE status='active' ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
            if handoff:
                try:
                    created = datetime.strptime(handoff["created_at"], "%Y-%m-%d %H:%M:%S")
                    hours = (datetime.now() - created).total_seconds() / 3600
                    if hours < 24:
                        age = f"{int(hours)}h 前"
                    elif hours < 168:
                        age = f"{int(hours/24)} 天前 ⚠️ 接手前先跟使用者確認還有效"
                    else:
                        age = f"{int(hours/24)} 天前 ⚠️⚠️ 高機率已過時，務必先確認"
                except (ValueError, TypeError):
                    age = "時間解析失敗"
                sections.append(
                    f"\n## 上次 Session 交接 #{handoff['id']}"
                    f"（{handoff['created_at']} · {age}）"
                )
                sections.append(handoff["summary"])
                sections.append(
                    f"\n_接手完請跑 resolve_handoff({handoff['id']}) "
                    f"標記完成、避免下次又撈到。_"
                )

            active_orders = db.execute(
                "SELECT o.id, o.status, o.qc_status, o.total_amount, c.name as customer_name "
                "FROM orders o LEFT JOIN customers c ON o.customer_id = c.id "
                "WHERE o.status IN ('pending','confirmed','shipped','delivered') "
                "ORDER BY o.created_at DESC LIMIT 10"
            ).fetchall()
            if active_orders:
                sections.append(f"\n## 進行中訂單（{len(active_orders)} 筆）")
                status_icon = {
                    "pending": "[待處理]", "confirmed": "[已確認]",
                    "shipped": "[已出貨]", "delivered": "[已送達]",
                }
                for o in active_orders:
                    hint = ""
                    if o["status"] == "pending":
                        hint = " → 待確認"
                    elif o["status"] == "confirmed" and o["qc_status"] == "pending":
                        hint = f" → 待品檢 qc_order(order_id={o['id']})"
                    elif o["status"] == "confirmed" and o["qc_status"] == "passed":
                        hint = f" → 可出貨 fulfill_order(order_id={o['id']})"
                    elif o["status"] == "confirmed" and o["qc_status"] == "failed":
                        hint = " → QC不合格，需處理"
                    elif o["status"] == "shipped":
                        hint = " → 待送達確認"
                    elif o["status"] == "delivered":
                        hint = " → 待收款"
                    sections.append(
                        f"- {status_icon.get(o['status'], '')} [#{o['id']}] "
                        f"{o['customer_name'] or '?'} NT${o['total_amount']:,.0f}{hint}"
                    )

            overdue_count = db.execute(
                "SELECT COUNT(*) as c FROM transactions WHERE payment_status = 'overdue'"
            ).fetchone()["c"]
            if overdue_count:
                overdue_total = db.execute(
                    "SELECT COALESCE(SUM(amount - paid_amount), 0) as s FROM transactions "
                    "WHERE payment_status = 'overdue'"
                ).fetchone()["s"]
                sections.append(
                    f"\n## 逾期帳款：{overdue_count} 筆，合計 NT${overdue_total:,.0f}"
                )

            stats = {
                "員工": db.execute(
                    "SELECT COUNT(*) as c FROM employees WHERE active=1"
                ).fetchone()["c"],
                "客戶": db.execute(
                    "SELECT COUNT(*) as c FROM customers WHERE type='customer'"
                ).fetchone()["c"],
                "供應商": db.execute(
                    "SELECT COUNT(*) as c FROM customers WHERE type='supplier'"
                ).fetchone()["c"],
                "庫存品項": db.execute("SELECT COUNT(*) as c FROM inventory").fetchone()["c"],
            }
            sections.append(f"\n## 數據統計")
            sections.append(" | ".join(f"{k}: {v}" for k, v in stats.items()))

            yesterday = db.execute(
                "SELECT * FROM daily_snapshots ORDER BY snapshot_date DESC LIMIT 1"
            ).fetchone()
            if yesterday:
                sections.append(f"\n## 趨勢（vs {yesterday['snapshot_date']}）")
                current_pending = db.execute(
                    "SELECT COUNT(*) as c FROM tasks "
                    "WHERE status IN ('pending','in_progress')"
                ).fetchone()["c"]
                delta_tasks = current_pending - yesterday["pending_tasks"]
                delta_str = f"+{delta_tasks}" if delta_tasks > 0 else str(delta_tasks)
                sections.append(f"- 待處理任務：{current_pending}（{delta_str}）")

            reminders = _date_reminders()
            if reminders:
                sections.append("\n## 日期提醒")
                for r in reminders:
                    sections.append(f"- {r}")

            month_start = datetime.now().strftime("%Y-%m-01")
            push_counts = db.execute(
                "SELECT channel_id, COUNT(*) as cnt FROM line_messages "
                "WHERE direction IN ('outbound', 'broadcast') AND created_at >= ? "
                "GROUP BY channel_id", (month_start,),
            ).fetchall()
            if push_counts:
                sections.append("\n## LINE 推送額度（免費方案 200 則/月）")
                for pc in push_counts:
                    used = pc["cnt"]
                    pct = used / 200 * 100
                    tag = " 超限" if pct >= 100 else " 注意：接近上限" if pct >= 80 else ""
                    sections.append(f"- {pc['channel_id']}: {used}/200 ({pct:.0f}%){tag}")
    finally:
        db.close()

    if not sections:
        return "系統剛初始化，尚無資料。請從建立公司資訊和員工名單開始。"
    return "\n".join(sections)


# ============================================================
# log_interaction / log_decision
# ============================================================

def log_interaction(
    actor: str, action: str, target_type: str, target_id: int,
    detail: str, business_unit: str,
) -> str:
    with transaction() as db:
        db.execute(
            "INSERT INTO interaction_log "
            "(actor, action, target_type, target_id, detail, business_unit) "
            "VALUES (?,?,?,?,?,?)",
            (actor, action, target_type or None, target_id or None,
             detail or None, business_unit or None),
        )
    return f"已記錄：{actor} → {action}"


def log_decision(
    title: str,
    reason: str,
    supersedes_rule_ids: list[int],
    related_rule_ids: list[int],
    source_quote: str,
    set_by: str,
    business_unit: str,
    confidential: bool,
) -> str:
    sq = (source_quote or "").strip()
    src_type = "explicit" if sq else "inferred"

    superseded = []
    linked = []

    with transaction() as db:
        # actor fail-closed（反捏造核心、#10）：在任何 business_rules 寫入「之前」解析可信寫入者。
        # 防員工偽造 set_by='老闆' + 假引言寫成正式決策。
        actor, err = writer_or_error(db, set_by)
        if err:
            return err

        # 正式決策一律需 manager（codex 複審第二輪殘留 finding）：log_decision 寫的是
        # decision_record（公司治理級決策），不是一般觀察。verified 的 basic 基層員工不應能
        # 留正式決策。比照 store_fact(explicit)：非全權限層才驗（_check_permission 傳 "" → floored
        # 取 verified user_id）；operator（is_full_access）放行。set_by 是名字非 user_id、走 floor gate。
        from shared.floor_policy import is_full_access
        if not is_full_access():
            perm_err = _check_permission(db, "", "manager")
            if perm_err:
                return (
                    f"ERROR: 記錄正式決策需 manager 以上權限"
                    f"（{perm_err.removeprefix('ERROR: ')}）。"
                )

        cur = db.execute(
            "INSERT INTO business_rules "
            "(category, title, content, source_type, source_quote, set_by, business_unit, confidential) "
            "VALUES ('decision_record', ?, ?, ?, ?, ?, ?, ?)",
            (title, reason, src_type, sq or None,
             actor or "system", business_unit or None, 1 if confidential else 0),
        )
        new_id = cur.lastrowid

        for rid in (supersedes_rule_ids or []):
            r = db.execute(
                "SELECT id, title FROM business_rules "
                "WHERE id = ? AND superseded_by IS NULL",
                (rid,),
            ).fetchone()
            if r:
                db.execute(
                    "UPDATE business_rules SET superseded_by = ? WHERE id = ?",
                    (new_id, rid),
                )
                superseded.append(f"#{rid} {r['title']}")

        for rid in (related_rule_ids or []):
            if rid == new_id:
                continue
            exists = db.execute(
                "SELECT id, title FROM business_rules "
                "WHERE id=? AND superseded_by IS NULL",
                (rid,),
            ).fetchone()
            if not exists:
                continue
            a, b = min(new_id, rid), max(new_id, rid)
            try:
                db.execute(
                    "INSERT INTO rule_relations "
                    "(rule_id_a, rule_id_b, relation_type, created_by) "
                    "VALUES (?,?,?,?)",
                    (a, b, "related", actor or "system"),
                )
                linked.append(f"#{rid} {exists['title']}")
            except sqlite3.IntegrityError:
                pass

        db.execute(
            "INSERT INTO interaction_log "
            "(actor, action, target_type, target_id, detail, business_unit) "
            "VALUES (?,?,?,?,?,?)",
            (actor or "system", "decision_logged", "rule", new_id, title,
             business_unit or None),
        )

    msg = f"已記錄決策 #{new_id}（{src_type}）：{title}"
    if src_type == "inferred":
        msg += "\n   注意：沒附 source_quote、標 inferred；建議下次補老闆原話"
    if superseded:
        msg += f"\n   廢棄：{', '.join(superseded)}"
    if linked:
        msg += f"\n   關聯：{', '.join(linked)}"
    return msg

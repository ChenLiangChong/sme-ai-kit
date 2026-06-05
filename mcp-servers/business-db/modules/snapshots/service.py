"""Snapshots service — 每日快照流程（全域 + 各事業體、skip 已存在）。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
import sqlite3

from shared.db import _now, transaction

from . import repository


def save_daily() -> str:
    today = _now()[:10]
    saved: list[str] = []
    skipped: list[str] = []

    with transaction() as db:
        def _save(bu_key: str, label: str) -> None:
            # 原子 upsert：唯一鍵 (snapshot_date, COALESCE(business_unit,'')) 上用 INSERT OR IGNORE，
            # rowcount 判斷實際有沒有寫進。原「先 snapshot_exists 再 insert」的 check-then-insert 在
            # 併發下會撞唯一鍵 raise IntegrityError、整批同 tx 回滾全部快照。INSERT OR IGNORE 讓單筆
            # 衝突只 no-op 該筆、不影響其他 BU 的快照；再攔 IntegrityError 轉 skip 做雙保險。
            metrics = repository.compute_metrics(db, today, bu_key)
            try:
                inserted = repository.insert_snapshot_if_absent(db, today, bu_key, metrics)
            except sqlite3.IntegrityError:
                inserted = False
            (saved if inserted else skipped).append(label)

        _save("", "全域")
        for entity_id in repository.list_entity_ids(db):
            _save(entity_id, entity_id)

    if not saved:
        return f"今天（{today}）的快照已全部存在，跳過。"
    msg = f"{today} 快照已儲存（{', '.join(saved)}）"
    if skipped:
        msg += f"，已存在跳過（{', '.join(skipped)}）"
    return msg

"""Snapshots service — 每日快照流程（全域 + 各事業體、skip 已存在）。

層次邊界：transaction ownership 在這層，repository 不 commit。
"""
from shared.db import _now, transaction

from . import repository


def save_daily() -> str:
    today = _now()[:10]
    saved: list[str] = []
    skipped: list[str] = []

    with transaction() as db:
        def _save(bu_key: str, label: str) -> None:
            if repository.snapshot_exists(db, today, bu_key):
                skipped.append(label)
                return
            metrics = repository.compute_metrics(db, today, bu_key)
            repository.insert_snapshot(db, today, bu_key, metrics)
            saved.append(label)

        _save("", "全域")
        for entity_id in repository.list_entity_ids(db):
            _save(entity_id, entity_id)

    if not saved:
        return f"今天（{today}）的快照已全部存在，跳過。"
    msg = f"{today} 快照已儲存（{', '.join(saved)}）"
    if skipped:
        msg += f"，已存在跳過（{', '.join(skipped)}）"
    return msg

"""病害登记业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "disease"
REQUIRED_FIELDS = ["病害编号", "所在设施", "病害类型"]
STATUS_ORDER = ["待定级", "已定级", "处置中", "已闭环", "已挂起"]
ACTION_RULES = {"确认定级": "已定级", "提交闭环": "已闭环", "挂起病害": "已挂起"}
NEGATIVE_ACTIONS = []
OPEN_STATUSES = ["待定级", "已定级", "处置中"]
CLOSED_STATUS = "已闭环"
OVERDUE_DAYS = 7


def _normalize(entry: dict[str, Any]) -> dict[str, Any]:
    """状态以 status 为唯一准绳，病害状态列始终与它保持一致。

    列表、详情、导出、统计卡读到的都是这同一份结果，不会出现两处状态打架。
    """
    entry["病害状态"] = entry.get("status") or STATUS_ORDER[0]
    return entry


class DiseaseService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("病害编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_normalize(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _normalize(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _normalize(entry), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, str]:
        values = values or {}
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"病害记录 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于病害登记可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"

        notes: list[str] = []
        if action == "挂起病害":
            if entry.get("status") == CLOSED_STATUS:
                return None, "病害已闭环，不能再挂起"
            reason = str(values.get("挂起理由") or "").strip()
            if not reason:
                return None, "挂起理由未填写，请先补充挂起理由再挂起"
            entry["挂起理由"] = reason  # 重复挂起只保留最后一次理由
        elif action == "确认定级":
            grade = str(values.get("严重等级") or "").strip()
            if grade:
                entry["严重等级"] = grade
            elif str(entry.get("严重等级") or "").strip():
                notes.append(f"严重等级（定级结论）未填写，已沿用上一次生效值「{entry['严重等级']}」")
            else:
                return None, "严重等级（定级结论）未填写，且该记录没有可沿用的上一次定级结果"

        entry["status"] = target
        entry["pending"] = target in OPEN_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"病害记录已{action}"
        if notes:
            message = f"{message}：{'；'.join(notes)}"
        return _normalize(entry), message

    def stats(self) -> list[dict[str, Any]]:
        """统计卡口径：与列表、详情读同一批记录，按锚定后的 status 计数。"""
        rows = store.rows(MODULE)
        return [
            {"label": "待定级病害", "value": sum(1 for row in rows if row.get("status") == "待定级")},
            {"label": "处置中病害", "value": sum(1 for row in rows if row.get("status") == "处置中")},
            {"label": "超期未闭环", "value": sum(1 for row in rows if self._is_overdue(row))},
        ]

    @staticmethod
    def _is_overdue(row: dict[str, Any]) -> bool:
        """未闭环也未挂起、且发现日期距今超过 OVERDUE_DAYS 天的记为超期。"""
        if row.get("status") not in OPEN_STATUSES:
            return False
        try:
            found = date.fromisoformat(str(row.get("发现日期") or "").strip())
        except ValueError:
            return False
        return (date.today() - found).days > OVERDUE_DAYS

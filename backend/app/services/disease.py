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

# 状态只认内部 status 这一份，病害状态列始终向它对齐，列表、详情、统计卡才不看岔。
STATUS_FIELD = "病害状态"
# 定级结论落在严重等级字段；提交时留空就沿用记录里上一次生效的值。
GRADE_FIELD = "严重等级"
GRADE_ALIASES = ("严重等级", "定级结论")
SUSPEND_REASON_FIELD = "挂起理由"
CLOSED_STATUS = "已闭环"
RESTING_STATUSES = ("已闭环", "已挂起")
OVERDUE_DAYS = 7


class DiseaseService:
    @staticmethod
    def _anchored(row: dict[str, Any]) -> dict[str, Any]:
        """状态以内部 status 为准，病害状态列向它对齐，避免列表和详情各看一份。"""
        anchored = dict(row)
        anchored[STATUS_FIELD] = row.get("status") or STATUS_ORDER[0]
        return anchored

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
        return [self._anchored(row) for row in rows[start:start + size]], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._anchored(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry[STATUS_FIELD] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._anchored(entry), []

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
                return None, "病害记录已闭环，不能再挂起"
            reason = str(values.get(SUSPEND_REASON_FIELD) or "").strip()
            if not reason:
                return None, "挂起理由未填写，请先补充挂起理由再执行挂起"
            entry[SUSPEND_REASON_FIELD] = reason  # 多次挂起只保留最后一次理由
        if action == "确认定级":
            grade = ""
            for key in GRADE_ALIASES:
                grade = str(values.get(key) or "").strip()
                if grade:
                    break
            if grade:
                entry[GRADE_FIELD] = grade
            else:
                last = str(entry.get(GRADE_FIELD) or "").strip()
                if not last:
                    return None, "定级结论（严重等级）未填写，且没有可沿用的上一次定级，请补充后再确认定级"
                notes.append(f"定级结论（严重等级）未填写，已沿用上一次生效的严重等级「{last}」")
        entry["status"] = target
        entry[STATUS_FIELD] = target
        entry["pending"] = target not in RESTING_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        message = f"病害记录已{action}"
        if notes:
            message = f"{message}：{'；'.join(notes)}"
        return self._anchored(entry), message

    def stats(self) -> list[dict[str, Any]]:
        """统计卡口径：与列表、详情读同一份记录，按锚定后的 status 计数。"""
        rows = store.rows(MODULE)
        today = date.today()

        def is_overdue(row: dict[str, Any]) -> bool:
            if row.get("status") == CLOSED_STATUS:
                return False
            try:
                found = date.fromisoformat(str(row.get("发现日期") or ""))
            except ValueError:
                return False
            return (today - found).days > OVERDUE_DAYS

        return [
            {"label": "待定级病害", "value": sum(1 for row in rows if row.get("status") == "待定级")},
            {"label": "处置中病害", "value": sum(1 for row in rows if row.get("status") == "处置中")},
            {"label": "超期未闭环", "value": sum(1 for row in rows if is_overdue(row))},
        ]

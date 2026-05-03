"""Gmail 위젯 — Phase 5.13 リニューアル.

3-pane 레이아웃:
    좌측 (200px) — 라벨 (Ctrl+click 다중 토글, 알람 toggle, 표시 라벨 편집)
    중앙 (380px) — 메일 리스트 (검색 / 일괄 액션 / 무한 스크롤 / 多중 선택)
    우측 (가변) — 메일 본문 (HTML 안전 뷰 + 첨부 칩 + 액션 버튼)

새 기능:
    - LeeDetailHeader / LeeButton / LeePill / LeeCard 디자인 시스템 적용
    - 검색 (Ctrl+F): Gmail 검색 쿼리 그대로 (300ms 디바운스)
    - 다중 선택: 체크박스 / Shift+click 범위 선택
    - 일괄 액션: 既読 / アーカイブ / 削除 / ラベル 변경
    - 라벨 우클릭 → 「이 라벨 전부 기독」 / 알람 토글
    - 첨부 파일 칩 표시
    - 자동 갱신 (5분, 설정 가능) + 폴링
"""
from __future__ import annotations

import logging
import urllib.parse
import webbrowser
from typing import Optional

from PySide6.QtCore import (
    QPoint, QSize, Qt, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QAction, QBrush, QColor, QCursor, QFont, QIcon,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPushButton,
    QSizePolicy, QSplitter, QTextBrowser, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeeIconTile, LeePill,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_MAIL = "#EA4335"   # Gmail 빨강 (--c-mail)
_C_INFO = "#0A84FF"
_C_OK   = "#30D158"
_C_WARN = "#FF9F0A"
_C_BAD  = "#FF453A"

_SYSTEM_LABEL_NAMES = {
    "INBOX":     "受信トレイ",
    "STARRED":   "スター付き",
    "IMPORTANT": "重要",
    "SENT":      "送信済み",
    "DRAFT":     "下書き",
    "SPAM":      "迷惑メール",
    "TRASH":     "ゴミ箱",
}
_SYSTEM_LABEL_ICONS = {
    "INBOX":     "📥",
    "STARRED":   "⭐",
    "IMPORTANT": "❗",
    "SENT":      "📤",
    "DRAFT":     "📝",
    "SPAM":      "🚫",
    "TRASH":     "🗑",
}

# 아바타 색상 팔레트
_AVATAR_COLORS = [
    "#4285F4", "#EA4335", "#FBBC05", "#34A853",
    "#FF6D00", "#46BDC6", "#7986CB", "#E67C73",
    "#F4511E", "#0B8043", "#8E24AA", "#D50000",
]


# ──────────────────────────────────────────────────────────────────────
# 헬퍼
# ──────────────────────────────────────────────────────────────────────
def _sender_name(sender_raw: str) -> str:
    """'Foo Bar <foo@example.com>' → 'Foo Bar'"""
    if "<" in sender_raw:
        name = sender_raw[:sender_raw.index("<")].strip().strip('"')
    else:
        name = sender_raw.split("@")[0] if "@" in sender_raw else sender_raw
    return name or "(不明)"


def _sender_initial(sender_raw: str) -> tuple[str, str]:
    name = _sender_name(sender_raw)
    initial = name[0].upper() if name and name != "(不明)" else "?"
    color = _AVATAR_COLORS[abs(hash(name)) % len(_AVATAR_COLORS)]
    return initial, color


def _format_mail_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        import datetime as _dt
        dt = parsedate_to_datetime(date_str)
        local_dt = dt.astimezone()
        now = _dt.datetime.now().astimezone()
        if local_dt.date() == now.date():
            return local_dt.strftime("%H:%M")
        if local_dt.date() == (now.date() - _dt.timedelta(days=1)):
            return tr("昨日")
        if local_dt.year == now.year:
            return local_dt.strftime("%m/%d")
        return local_dt.strftime("%Y/%m/%d")
    except Exception:
        return date_str[:10]


def _format_size(byte_size: int) -> str:
    if byte_size <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if byte_size < 1024:
            return f"{byte_size:.0f} {unit}" if unit == "B" else f"{byte_size:.1f} {unit}"
        byte_size /= 1024
    return f"{byte_size:.1f} TB"


def _build_label_tree(labels: list) -> tuple[list, dict]:
    """이름의 '/' 로 부모-자식 트리 구성."""
    by_name: dict[str, dict] = {l.get("name", ""): l for l in labels}
    children: dict[str, list] = {}
    roots: list = []
    for lbl in labels:
        name = lbl.get("name", "")
        if lbl.get("type") == "system" or "/" not in name:
            roots.append(lbl); continue
        parent_name = name.rsplit("/", 1)[0]
        parent = by_name.get(parent_name)
        if parent:
            children.setdefault(parent.get("id", ""), []).append(lbl)
        else:
            roots.append(lbl)
    return roots, children


def _label_display_name(lbl: dict) -> str:
    lid = lbl.get("id", "")
    name = lbl.get("name", lid)
    if lid in _SYSTEM_LABEL_NAMES:
        return tr(_SYSTEM_LABEL_NAMES[lid])
    if "/" in name:
        return name.rsplit("/", 1)[1]
    return name


# ──────────────────────────────────────────────────────────────────────
# 1. _SafeTextBrowser — 외부 URL/이미지 차단 (보안)
# ──────────────────────────────────────────────────────────────────────
class _SafeTextBrowser(QTextBrowser):
    """외부 URL 로드를 차단하여 트래킹 픽셀·로컬 파일 접근 방지."""
    _BLOCKED = frozenset({"http", "https", "file", "data", "javascript", "ftp"})

    def loadResource(self, resource_type, url: QUrl):
        if url.scheme() in self._BLOCKED:
            return None
        return super().loadResource(resource_type, url)


# ──────────────────────────────────────────────────────────────────────
# 2. LabelEditDialog — LeeDialog 베이스 (라벨 표시 설정)
# ──────────────────────────────────────────────────────────────────────
class LabelEditDialog(LeeDialog):
    """표시할 라벨 선택 + 드래그 정렬."""

    def __init__(self, all_labels: list, visible_ids: Optional[list],
                 is_dark: bool = True, parent=None):
        super().__init__(tr("ラベル表示設定"), kind="info", parent=parent)
        self._is_dark = is_dark
        self._result_ids: Optional[list] = None
        self.set_message(tr("表示するラベルを選択 · ドラッグで並び替え"))

        body = QFrame()
        bl = QVBoxLayout(body); bl.setContentsMargins(0, 0, 0, 0); bl.setSpacing(8)

        self._list = QListWidget()
        self._list.setObjectName("gmailLabelEditList")
        self._list.setDragDropMode(QListWidget.InternalMove)
        self._list.setSelectionMode(QListWidget.SingleSelection)
        self._list.setMinimumHeight(280)
        for lbl in all_labels:
            lid = lbl.get("id", "")
            display = _label_display_name(lbl)
            if lid in _SYSTEM_LABEL_ICONS:
                display = f"{_SYSTEM_LABEL_ICONS[lid]}  {display}"
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, lid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            checked = (visible_ids is None) or (lid in visible_ids)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            self._list.addItem(item)
        bl.addWidget(self._list, 1)

        sel_row = QHBoxLayout(); sel_row.setSpacing(6)
        b_all  = LeeButton(tr("すべて表示"),   variant="secondary", size="sm")
        b_none = LeeButton(tr("すべて非表示"), variant="ghost",     size="sm")
        b_all.clicked.connect(lambda: self._set_all(Qt.Checked))
        b_none.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        sel_row.addWidget(b_all); sel_row.addWidget(b_none); sel_row.addStretch()
        bl.addLayout(sel_row)

        self.add_body_widget(body)
        self.add_button(tr("キャンセル"), variant="ghost",   role="reject")
        self.add_button(tr("適用"),       variant="primary", role="accept")

        self._apply_local_qss()
        self.resize(440, 540)

    def _set_all(self, state) -> None:
        for i in range(self._list.count()):
            self._list.item(i).setCheckState(state)

    def _apply_local_qss(self) -> None:
        bg = "#1B1E26"
        bs = "rgba(255,255,255,0.06)"
        fg = "#F2F4F7"
        accent_bg = "rgba(234,67,53,0.18)"
        self.setStyleSheet(self.styleSheet() + f"""
            QListWidget#gmailLabelEditList {{
                background: {bg}; color: {fg};
                border: 1px solid {bs}; border-radius: 10px;
                padding: 4px;
                font-size: 12px;
            }}
            QListWidget#gmailLabelEditList::item {{
                padding: 7px 10px; border-radius: 6px;
            }}
            QListWidget#gmailLabelEditList::item:selected {{
                background: {accent_bg}; color: {fg};
            }}
        """)

    def accept(self):
        self._result_ids = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
        ]
        super().accept()

    def get_visible_ids(self) -> Optional[list]:
        return self._result_ids


# ──────────────────────────────────────────────────────────────────────
# 3. LabelListPanel — 좌측 라벨 패널 (Ctrl+click 다중 토글)
# ──────────────────────────────────────────────────────────────────────
class LabelListPanel(QWidget):
    """라벨 목록. 단일선택 (기본) + Ctrl+click 다중 토글 + 우클릭 메뉴."""
    label_selection_changed = Signal(list)   # ordered list of selected label_ids
    alarm_toggled           = Signal(str, bool)
    visible_changed         = Signal(list)
    mark_label_all_read     = Signal(str)    # label_id 전부 기독

    def __init__(self, alarm_labels: set, visible_ids: Optional[list] = None, parent=None):
        super().__init__(parent)
        self._alarm_labels: set = set(alarm_labels)
        self._all_labels: list = []
        self._labels: list = []
        self._visible_ids: Optional[list] = visible_ids
        self._selected_ids: list[str] = []
        self._is_dark = True
        self._build_ui()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # 헤더
        hdr = QFrame(); hdr.setObjectName("gmailLabelHdr")
        hr = QHBoxLayout(hdr); hr.setContentsMargins(12, 10, 8, 10); hr.setSpacing(6)
        title = QLabel(tr("ラベル")); title.setObjectName("gmailLabelTitle")
        hr.addWidget(title); hr.addStretch()
        self._btn_edit = QPushButton("⚙"); self._btn_edit.setObjectName("gmailMiniBtn")
        self._btn_edit.setFixedSize(26, 26)
        self._btn_edit.setToolTip(tr("ラベル表示設定"))
        self._btn_edit.clicked.connect(self._open_editor)
        hr.addWidget(self._btn_edit)
        v.addWidget(hdr)

        # 트리
        self._tree = QTreeWidget()
        self._tree.setObjectName("gmailLabelTree")
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setRootIsDecorated(True)
        # 다중 선택 지원 — Ctrl+click 으로 토글
        self._tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self._tree.itemSelectionChanged.connect(self._on_selection_changed)
        self._tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tree.customContextMenuRequested.connect(self._on_context_menu)
        v.addWidget(self._tree, 1)

    # ── 외부 API ─────────────────────────────────────────────
    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._refresh()

    def set_labels(self, labels: list) -> None:
        self._all_labels = labels
        self._apply_visible()

    def _apply_visible(self) -> None:
        if self._visible_ids is None:
            self._labels = list(self._all_labels)
        else:
            order = {lid: i for i, lid in enumerate(self._visible_ids)}
            self._labels = sorted(
                [l for l in self._all_labels if l.get("id") in order],
                key=lambda l: order.get(l.get("id", ""), 9999),
            )
        self._refresh()

    def set_visible_ids(self, ids: Optional[list]) -> None:
        self._visible_ids = ids
        self._apply_visible()

    def update_unread(self, label_id: str, count: int) -> None:
        for lbl in self._labels:
            if lbl.get("id") == label_id:
                lbl["messagesUnread"] = count
                break
        item = self._find_item(label_id)
        if item is not None:
            self._update_item_text(item, self._get(label_id) or {"id": label_id})

    def _get(self, label_id: str) -> Optional[dict]:
        for l in self._labels:
            if l.get("id") == label_id:
                return l
        return None

    def get_alarm_labels(self) -> list[str]:
        return list(self._alarm_labels)

    def selected_label_ids(self) -> list[str]:
        return list(self._selected_ids)

    def select_first(self) -> None:
        """초기 호출 — 첫 번째 라벨 선택 (보통 INBOX)."""
        if self._tree.topLevelItemCount() == 0:
            return
        self._tree.blockSignals(True)
        self._tree.clearSelection()
        first = self._tree.topLevelItem(0)
        first.setSelected(True)
        self._tree.setCurrentItem(first)
        self._tree.blockSignals(False)
        self._on_selection_changed()

    # ── 내부 ─────────────────────────────────────────────────
    def _find_item(self, label_id: str) -> Optional[QTreeWidgetItem]:
        def _walk(it):
            if it.data(0, Qt.UserRole) == label_id:
                return it
            for i in range(it.childCount()):
                f = _walk(it.child(i))
                if f: return f
            return None
        for i in range(self._tree.topLevelItemCount()):
            f = _walk(self._tree.topLevelItem(i))
            if f: return f
        return None

    def _refresh(self) -> None:
        prev = list(self._selected_ids)
        self._tree.blockSignals(True)
        self._tree.clear()
        roots, children = _build_label_tree(self._labels)

        def _add(lbl, parent=None):
            lid = lbl.get("id", "")
            it = QTreeWidgetItem()
            it.setData(0, Qt.UserRole, lid)
            self._update_item_text(it, lbl)
            if parent is None:
                self._tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            for c in children.get(lid, []):
                _add(c, it)
            if children.get(lid):
                it.setExpanded(True)

        for lbl in roots:
            _add(lbl)

        # 이전 선택 복구
        for lid in prev:
            it = self._find_item(lid)
            if it: it.setSelected(True)
        self._tree.blockSignals(False)
        self._tree.resizeColumnToContents(0)

    def _update_item_text(self, item: QTreeWidgetItem, lbl: dict) -> None:
        lid = lbl.get("id", "")
        name = _label_display_name(lbl)
        unread = lbl.get("messagesUnread", 0) or 0
        if lid in _SYSTEM_LABEL_ICONS:
            name = f"{_SYSTEM_LABEL_ICONS[lid]}  {name}"
        alarm = " 🔔" if lid in self._alarm_labels else ""

        if unread > 0:
            item.setText(0, f"{name}{alarm}    {unread}")
            f = item.font(0); f.setBold(True); item.setFont(0, f)
            item.setForeground(0, QBrush(QColor(_C_MAIL if lid == "INBOX" else _C_INFO)))
        else:
            item.setText(0, f"{name}{alarm}")
            f = item.font(0); f.setBold(False); item.setFont(0, f)
            fg = "#F2F4F7" if self._is_dark else "#0B1220"
            item.setForeground(0, QBrush(QColor(fg)))

    def _on_selection_changed(self) -> None:
        items = self._tree.selectedItems()
        ids = [it.data(0, Qt.UserRole) for it in items if it.data(0, Qt.UserRole)]
        if ids != self._selected_ids:
            self._selected_ids = ids
            self.label_selection_changed.emit(list(ids))

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self._tree.itemAt(pos)
        if not item:
            return
        lid = item.data(0, Qt.UserRole)
        is_alarm = lid in self._alarm_labels
        menu = QMenu(self)

        a_mark = QAction(f"✓  {tr('このラベルをすべて既読')}", menu)
        a_mark.triggered.connect(lambda _=False, x=lid: self.mark_label_all_read.emit(x))
        menu.addAction(a_mark)

        menu.addSeparator()

        if is_alarm:
            a_alarm = QAction(f"🔕  {tr('アラームをオフ')}", menu)
        else:
            a_alarm = QAction(f"🔔  {tr('アラームをオン')}", menu)
        a_alarm.triggered.connect(lambda _=False, x=lid, it=item: self._toggle_alarm(x, it))
        menu.addAction(a_alarm)

        menu.exec(self._tree.viewport().mapToGlobal(pos))

    def _toggle_alarm(self, label_id: str, item: QTreeWidgetItem) -> None:
        if label_id in self._alarm_labels:
            self._alarm_labels.discard(label_id); enabled = False
        else:
            self._alarm_labels.add(label_id); enabled = True
        lbl = self._get(label_id)
        if lbl:
            self._update_item_text(item, lbl)
        self.alarm_toggled.emit(label_id, enabled)

    def _open_editor(self) -> None:
        dlg = LabelEditDialog(self._all_labels, self._visible_ids,
                              is_dark=self._is_dark, parent=self)
        from PySide6.QtWidgets import QDialog as _QD
        if dlg.exec() == _QD.Accepted:
            res = dlg.get_visible_ids()
            if res is not None:
                self._visible_ids = res
                self._apply_visible()
                self.visible_changed.emit(res)


# ──────────────────────────────────────────────────────────────────────
# 4. _MailItemWidget — 체크박스 + 별표 + 라벨 칩 + 메타
# ──────────────────────────────────────────────────────────────────────
class _MailItemWidget(QFrame):
    """메일 행 위젯. 체크박스 / 별 / 발신자 / 제목+미리보기 / 라벨 / 시각."""
    checked_changed = Signal(str, bool)   # mail_id, checked
    star_clicked    = Signal(str)         # mail_id

    def __init__(self, mail: dict, label_lookup: dict, parent=None):
        super().__init__(parent)
        self._mail = mail
        self._label_lookup = label_lookup
        self.setObjectName("gmailMailRow")
        self._build_ui()

    def _build_ui(self) -> None:
        is_unread = self._mail.get("is_unread", False)
        sender_raw = self._mail.get("from", "")
        initial, av = _sender_initial(sender_raw)

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 12, 8); root.setSpacing(8)

        # ── 좌측: 체크박스 + 안읽음 도트 + 아바타
        self._check = QCheckBox()
        self._check.setObjectName("gmailMailCheck")
        self._check.stateChanged.connect(
            lambda st: self.checked_changed.emit(
                self._mail.get("id", ""), st == Qt.Checked.value,
            )
        )
        root.addWidget(self._check, 0, Qt.AlignVCenter)

        # 안읽음 점 (3x10) — unread 만 표시
        self._dot = QFrame()
        self._dot.setFixedSize(3, 28)
        if is_unread:
            self._dot.setStyleSheet(f"background: {_C_MAIL}; border-radius: 1px;")
        else:
            self._dot.setStyleSheet("background: transparent;")
        root.addWidget(self._dot, 0, Qt.AlignVCenter)

        # 아바타
        avatar = QLabel(initial)
        avatar.setFixedSize(34, 34); avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(
            f"QLabel {{ background: {av}; color: white; border-radius: 17px;"
            f" font-size: 13px; font-weight: 800; }}"
        )
        root.addWidget(avatar, 0, Qt.AlignVCenter)

        # ── 우측 본문
        right = QVBoxLayout(); right.setSpacing(2); right.setContentsMargins(0, 0, 0, 0)

        # 1행: 발신자 + 시각
        row1 = QHBoxLayout(); row1.setSpacing(6)
        sender = _sender_name(sender_raw)
        sender_lbl = QLabel(sender[:30] + ("…" if len(sender) > 30 else ""))
        sender_lbl.setObjectName("gmailSender")
        sender_lbl.setProperty("unread", "true" if is_unread else "false")
        row1.addWidget(sender_lbl, 1, Qt.AlignVCenter)

        self._star = QPushButton("★" if self._mail.get("is_starred") else "☆")
        self._star.setObjectName("gmailStar")
        self._star.setFixedSize(22, 22)
        self._star.setProperty("starred", "true" if self._mail.get("is_starred") else "false")
        self._star.clicked.connect(
            lambda: self.star_clicked.emit(self._mail.get("id", ""))
        )
        row1.addWidget(self._star, 0, Qt.AlignVCenter)

        date_lbl = QLabel(_format_mail_date(self._mail.get("date", "")))
        date_lbl.setObjectName("gmailDate")
        row1.addWidget(date_lbl, 0, Qt.AlignVCenter)
        right.addLayout(row1)

        # 2행: 제목 + 미리보기 (한 줄로 합침)
        subj = self._mail.get("subject", "(件名なし)")
        snip = self._mail.get("snippet", "")
        subj_short = subj[:50] + ("…" if len(subj) > 50 else "")
        snip_short = snip[:60] + ("…" if len(snip) > 60 else "")

        subj_lbl = QLabel(subj_short)
        subj_lbl.setObjectName("gmailSubject")
        subj_lbl.setProperty("unread", "true" if is_unread else "false")
        right.addWidget(subj_lbl)
        if snip_short:
            snip_lbl = QLabel(snip_short)
            snip_lbl.setObjectName("gmailSnippet")
            right.addWidget(snip_lbl)

        # 3행: 라벨 칩 (시스템 라벨 제외, 사용자 라벨만)
        chips = self._build_label_chips()
        if chips:
            row3 = QHBoxLayout(); row3.setSpacing(4)
            for c in chips[:3]:
                row3.addWidget(c)
            if len(chips) > 3:
                more = QLabel(f"+{len(chips) - 3}"); more.setObjectName("gmailChipMore")
                row3.addWidget(more)
            row3.addStretch()
            right.addLayout(row3)

        root.addLayout(right, 1)

    def _build_label_chips(self) -> list[QLabel]:
        out: list[QLabel] = []
        for lid in self._mail.get("label_ids", []):
            if lid in _SYSTEM_LABEL_NAMES or lid in ("UNREAD", "STARRED", "IMPORTANT", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES", "CATEGORY_FORUMS"):
                continue
            lbl = self._label_lookup.get(lid)
            name = _label_display_name(lbl) if lbl else lid
            color = (lbl or {}).get("color", {}).get("backgroundColor") or "#5856D6"
            chip = QLabel(name)
            chip.setObjectName("gmailLabelChip")
            chip.setStyleSheet(self._chip_qss(color))
            out.append(chip)
        return out

    @staticmethod
    def _chip_qss(color: str) -> str:
        # 라벨 색상의 alpha 톤 배경 + 진한 텍스트
        return (
            f"QLabel#gmailLabelChip {{"
            f" background: rgba(120,120,200,0.18); color: {color};"
            f" border: 1px solid rgba(120,120,200,0.35); border-radius: 999px;"
            f" padding: 1px 8px; font-size: 9px; font-weight: 800; }}"
        )

    def set_checked(self, checked: bool) -> None:
        self._check.blockSignals(True)
        self._check.setChecked(checked)
        self._check.blockSignals(False)

    def is_checked(self) -> bool:
        return self._check.isChecked()

    def get_mail(self) -> dict:
        return self._mail


# ──────────────────────────────────────────────────────────────────────
# 5. MailListPanel — 검색 + 일괄 액션 + 무한 스크롤 + 다중 선택
# ──────────────────────────────────────────────────────────────────────
class MailListPanel(QWidget):
    mail_selected       = Signal(dict)
    load_more_requested = Signal(str)            # page_token
    search_changed      = Signal(str)            # debounced
    bulk_action         = Signal(str, list)      # action, mail_ids
    star_toggled        = Signal(str, bool)      # mail_id, new_starred

    def __init__(self, parent=None):
        super().__init__(parent)
        self._next_page_token = ""
        self._loading = False
        self._selected_ids: set[str] = set()
        self._last_check_row: Optional[int] = None
        self._label_lookup: dict[str, dict] = {}

        self._build_ui()
        # 검색 디바운스
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(300)
        self._search_timer.timeout.connect(
            lambda: self.search_changed.emit(self.search_input.text().strip())
        )

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # 검색 행
        search_wrap = QFrame(); search_wrap.setObjectName("gmailSearchWrap")
        sw = QHBoxLayout(search_wrap); sw.setContentsMargins(12, 10, 12, 8); sw.setSpacing(6)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("gmailSearch")
        self.search_input.setPlaceholderText("🔍  " + tr("検索 (from:, subject:, has:attachment ...)"))
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedHeight(30)
        self.search_input.textChanged.connect(lambda _t: self._search_timer.start())
        sw.addWidget(self.search_input, 1)
        v.addWidget(search_wrap)

        # 일괄 액션 툴바 (선택 시 표시)
        self._bulk_bar = QFrame(); self._bulk_bar.setObjectName("gmailBulkBar")
        bb = QHBoxLayout(self._bulk_bar); bb.setContentsMargins(12, 8, 12, 8); bb.setSpacing(6)
        self._chk_all = QCheckBox()
        self._chk_all.setObjectName("gmailMailCheck")
        self._chk_all.setTristate(False)
        self._chk_all.stateChanged.connect(self._on_check_all)
        bb.addWidget(self._chk_all)
        self._bulk_count = QLabel("")
        self._bulk_count.setObjectName("gmailBulkCount")
        bb.addWidget(self._bulk_count, 1)
        for label, key in (
            ("✓  " + tr("既読"),       "read"),
            ("📥  " + tr("アーカイブ"), "archive"),
            ("🗑  " + tr("削除"),       "delete"),
        ):
            b = LeeButton(label, variant="secondary", size="sm")
            if key == "delete":
                b = LeeButton(label, variant="destructive", size="sm")
            b.clicked.connect(lambda _=False, k=key: self._fire_bulk(k))
            bb.addWidget(b)
        v.addWidget(self._bulk_bar)
        self._bulk_bar.setVisible(False)

        # 헤더 (라벨 / 카운트)
        self._hdr = QFrame(); self._hdr.setObjectName("gmailMailHdr")
        hr = QHBoxLayout(self._hdr); hr.setContentsMargins(12, 8, 12, 8); hr.setSpacing(8)
        self._hdr_lbl = QLabel(""); self._hdr_lbl.setObjectName("gmailMailHdrLbl")
        hr.addWidget(self._hdr_lbl, 1)
        self._count_pill = LeePill("0", variant="info")
        hr.addWidget(self._count_pill)
        v.addWidget(self._hdr)

        # 메일 리스트
        self._list = QListWidget()
        self._list.setObjectName("gmailMailList")
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.currentItemChanged.connect(self._on_current_changed)
        self._list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        v.addWidget(self._list, 1)
        # 첫 fetch 동안 메일 리스트 영역에 shimmer skeleton
        from app.ui.components.skeleton import install_skeleton_overlay
        self._list_skel = install_skeleton_overlay(self._list)

        # 빈 상태 + 더 로드
        self._empty_lbl = QLabel("📭  " + tr("該当するメールがありません"))
        self._empty_lbl.setObjectName("gmailEmpty")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setMinimumHeight(120)
        v.addWidget(self._empty_lbl)
        self._empty_lbl.hide()

        self._btn_more = LeeButton("⬇  " + tr("さらに読み込む"), variant="ghost", size="sm")
        self._btn_more.clicked.connect(self._load_more)
        self._btn_more.hide()
        v.addWidget(self._btn_more)

    # ── 외부 API ─────────────────────────────────────────────
    def set_label_lookup(self, labels: list) -> None:
        self._label_lookup = {l.get("id", ""): l for l in labels}

    def set_header(self, text: str) -> None:
        self._hdr_lbl.setText(text)

    def set_loading(self, loading: bool) -> None:
        if loading:
            self._empty_lbl.hide()

    def set_mails(self, mails: list, next_token: str) -> None:
        # 첫 데이터 도착 시 skeleton 제거 (mails 가 비어있어도 응답이 온 것이므로 제거)
        if getattr(self, "_list_skel", None) is not None:
            self._list_skel.stop(); self._list_skel.deleteLater(); self._list_skel = None
        self._list.clear()
        self._selected_ids.clear()
        self._last_check_row = None
        self._next_page_token = next_token
        if mails:
            self._count_pill.setText(f"{len(mails):,}")
            for m in mails:
                self._add_item(m)
            self._list.show(); self._empty_lbl.hide()
        else:
            self._count_pill.setText("0")
            self._list.hide(); self._empty_lbl.show()
        self._btn_more.setVisible(bool(next_token))
        self._update_bulk_bar()

    def append_mails(self, mails: list, next_token: str) -> None:
        self._next_page_token = next_token
        for m in mails:
            self._add_item(m)
        self._count_pill.setText(f"{self._list.count():,}")
        self._btn_more.setVisible(bool(next_token))
        self._loading = False

    def mark_read_local(self, mail_id: str) -> None:
        for i in range(self._list.count()):
            it = self._list.item(i)
            data = it.data(Qt.UserRole)
            if data and data.get("id") == mail_id:
                data["is_unread"] = False
                it.setData(Qt.UserRole, data)
                self._replace_item_widget(i, data)
                break

    def remove_local(self, mail_ids: list[str]) -> None:
        ids = set(mail_ids)
        for i in range(self._list.count() - 1, -1, -1):
            it = self._list.item(i)
            data = it.data(Qt.UserRole)
            if data and data.get("id") in ids:
                self._list.takeItem(i)
        self._selected_ids -= ids
        self._count_pill.setText(f"{self._list.count():,}")
        self._update_bulk_bar()
        if self._list.count() == 0:
            self._list.hide(); self._empty_lbl.show()

    def reset_load_btn(self) -> None:
        self._btn_more.setText("⬇  " + tr("さらに読み込む"))
        self._loading = False

    # ── 내부 ─────────────────────────────────────────────────
    def _add_item(self, mail: dict) -> None:
        item = QListWidgetItem()
        item.setData(Qt.UserRole, mail)
        item.setSizeHint(QSize(0, 84 if not mail.get("label_ids") else 100))
        w = _MailItemWidget(mail, self._label_lookup)
        w.checked_changed.connect(self._on_check_changed)
        w.star_clicked.connect(self._on_star_clicked)
        self._list.addItem(item)
        self._list.setItemWidget(item, w)

    def _replace_item_widget(self, row: int, mail: dict) -> None:
        item = self._list.item(row)
        if not item:
            return
        item.setSizeHint(QSize(0, 84 if not mail.get("label_ids") else 100))
        w = _MailItemWidget(mail, self._label_lookup)
        w.checked_changed.connect(self._on_check_changed)
        w.star_clicked.connect(self._on_star_clicked)
        self._list.setItemWidget(item, w)
        # 체크 상태 복원
        if mail.get("id", "") in self._selected_ids:
            w.set_checked(True)

    def _on_current_changed(self, current, _previous) -> None:
        if current is None:
            return
        mail = current.data(Qt.UserRole)
        if mail:
            self.mail_selected.emit(mail)

    def _on_scroll(self, value: int) -> None:
        bar = self._list.verticalScrollBar()
        if not self._loading and self._next_page_token:
            if value > bar.maximum() - bar.pageStep() * 2:
                self._load_more()

    def _load_more(self) -> None:
        if self._loading or not self._next_page_token:
            return
        self._loading = True
        self._btn_more.setText(tr("読込中..."))
        self.load_more_requested.emit(self._next_page_token)

    def _on_check_changed(self, mail_id: str, checked: bool) -> None:
        if checked:
            self._selected_ids.add(mail_id)
        else:
            self._selected_ids.discard(mail_id)
        # Shift+click 범위 선택 (현재 키 modifier 확인)
        mods = QApplication.keyboardModifiers()
        if mods & Qt.ShiftModifier and self._last_check_row is not None:
            cur_row = self._row_of(mail_id)
            if cur_row is not None:
                lo, hi = sorted((self._last_check_row, cur_row))
                for i in range(lo, hi + 1):
                    it = self._list.item(i)
                    if not it: continue
                    w = self._list.itemWidget(it)
                    if isinstance(w, _MailItemWidget):
                        w.set_checked(checked)
                        m = it.data(Qt.UserRole)
                        if m:
                            if checked:
                                self._selected_ids.add(m.get("id", ""))
                            else:
                                self._selected_ids.discard(m.get("id", ""))
        self._last_check_row = self._row_of(mail_id)
        self._update_bulk_bar()

    def _row_of(self, mail_id: str) -> Optional[int]:
        for i in range(self._list.count()):
            data = self._list.item(i).data(Qt.UserRole)
            if data and data.get("id") == mail_id:
                return i
        return None

    def _on_check_all(self, state) -> None:
        checked = (state == Qt.Checked.value)
        for i in range(self._list.count()):
            it = self._list.item(i)
            w = self._list.itemWidget(it)
            if isinstance(w, _MailItemWidget):
                w.set_checked(checked)
                data = it.data(Qt.UserRole)
                if data:
                    if checked:
                        self._selected_ids.add(data.get("id", ""))
                    else:
                        self._selected_ids.discard(data.get("id", ""))
        self._update_bulk_bar()

    def _update_bulk_bar(self) -> None:
        n = len(self._selected_ids)
        self._bulk_bar.setVisible(n > 0)
        if n > 0:
            self._bulk_count.setText(tr("{0} 件選択中").format(f"{n:,}"))

    def _fire_bulk(self, action: str) -> None:
        if not self._selected_ids:
            return
        self.bulk_action.emit(action, list(self._selected_ids))

    def _on_star_clicked(self, mail_id: str) -> None:
        # 토글 — 현재 별 상태 확인
        for i in range(self._list.count()):
            it = self._list.item(i)
            data = it.data(Qt.UserRole)
            if data and data.get("id") == mail_id:
                new_starred = not data.get("is_starred", False)
                data["is_starred"] = new_starred
                it.setData(Qt.UserRole, data)
                self._replace_item_widget(i, data)
                self.star_toggled.emit(mail_id, new_starred)
                break


# ──────────────────────────────────────────────────────────────────────
# 6. MailPreviewPanel — 본문 + 첨부 칩 + 액션 (返信/全員に返信/転送)
# ──────────────────────────────────────────────────────────────────────
class MailPreviewPanel(QWidget):
    reply_clicked    = Signal(dict)
    reply_all_clicked = Signal(dict)
    forward_clicked  = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._current: Optional[dict] = None
        self._build_ui()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)

        # 헤더 (제목 + 메타 + 액션)
        self._hdr_wrap = QFrame(); self._hdr_wrap.setObjectName("gmailPreviewHdr")
        hl = QVBoxLayout(self._hdr_wrap); hl.setContentsMargins(20, 16, 20, 12); hl.setSpacing(6)

        self._subj_lbl = QLabel(""); self._subj_lbl.setObjectName("gmailPreviewSubj")
        self._subj_lbl.setWordWrap(True)
        hl.addWidget(self._subj_lbl)

        meta_row = QHBoxLayout(); meta_row.setSpacing(8)
        self._from_lbl = QLabel(""); self._from_lbl.setObjectName("gmailPreviewFrom")
        meta_row.addWidget(self._from_lbl, 1)
        self._date_lbl = QLabel(""); self._date_lbl.setObjectName("gmailPreviewDate")
        self._date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        meta_row.addWidget(self._date_lbl)
        hl.addLayout(meta_row)

        # 첨부 칩 영역
        self._attach_wrap = QFrame(); self._attach_wrap.setObjectName("gmailAttachWrap")
        self._attach_lay = QHBoxLayout(self._attach_wrap)
        self._attach_lay.setContentsMargins(0, 6, 0, 0); self._attach_lay.setSpacing(6)
        hl.addWidget(self._attach_wrap)
        self._attach_wrap.setVisible(False)

        v.addWidget(self._hdr_wrap)

        # 본문 (HTML) — wrapper 로 감싸 inset card 효과 (디자인 톤 surface + 흰 letter)
        # padding 12px 균일 (디자인 명세 정합)
        self._browser_wrap = QFrame()
        self._browser_wrap.setObjectName("gmailPreviewBrowserWrap")
        bw = QVBoxLayout(self._browser_wrap)
        bw.setContentsMargins(12, 12, 12, 12); bw.setSpacing(0)
        self._browser = _SafeTextBrowser()
        self._browser.setObjectName("gmailPreviewBrowser")
        self._browser.setOpenExternalLinks(True)
        bw.addWidget(self._browser)
        v.addWidget(self._browser_wrap, 1)

        # 빈 상태
        self._empty_lbl = QLabel("📧  " + tr("メールを選択してください"))
        self._empty_lbl.setObjectName("gmailPreviewEmpty")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        v.addWidget(self._empty_lbl, 1)

        # 액션 푸터
        self._actions = QFrame(); self._actions.setObjectName("gmailPreviewActions")
        af = QHBoxLayout(self._actions); af.setContentsMargins(20, 10, 20, 12); af.setSpacing(6)
        self._btn_reply     = LeeButton("↩  " + tr("返信"),       variant="secondary", size="sm")
        self._btn_reply_all = LeeButton("↩↩  " + tr("全員に返信"), variant="secondary", size="sm")
        self._btn_forward   = LeeButton("↪  " + tr("転送"),        variant="secondary", size="sm")
        self._btn_browser   = LeeButton("↗  " + tr("ブラウザで開く"), variant="ghost",   size="sm")
        af.addWidget(self._btn_reply)
        af.addWidget(self._btn_reply_all)
        af.addWidget(self._btn_forward)
        af.addStretch()
        af.addWidget(self._btn_browser)
        v.addWidget(self._actions)

        self._btn_reply.clicked.connect(
            lambda: self._current and self.reply_clicked.emit(self._current)
        )
        self._btn_reply_all.clicked.connect(
            lambda: self._current and self.reply_all_clicked.emit(self._current)
        )
        self._btn_forward.clicked.connect(
            lambda: self._current and self.forward_clicked.emit(self._current)
        )
        self._btn_browser.clicked.connect(self._open_in_browser)

        # 초기 빈 상태
        self._show_empty_only()

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark

    # ── 외부 API ─────────────────────────────────────────────
    def show_loading(self) -> None:
        self._hdr_wrap.hide(); self._browser_wrap.hide()
        self._actions.hide(); self._empty_lbl.hide()

    def show_empty(self) -> None:
        self._current = None
        self._show_empty_only()

    def _show_empty_only(self) -> None:
        self._hdr_wrap.hide(); self._browser_wrap.hide()
        self._actions.hide(); self._empty_lbl.show()

    def show_mail(self, mail: dict) -> None:
        self._current = mail
        self._subj_lbl.setText(mail.get("subject", tr("(件名なし)")))
        self._from_lbl.setText(f"👤 {mail.get('from', '')}")
        self._date_lbl.setText(mail.get("date", "")[:31])

        # 첨부
        atts = mail.get("attachments", []) or []
        # 기존 칩 제거
        while self._attach_lay.count() > 0:
            it = self._attach_lay.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        if atts:
            for a in atts:
                fname = a.get("filename", "?")
                size = _format_size(a.get("size", 0))
                chip = QLabel(f"📎 {fname[:24]}  ·  {size}")
                chip.setObjectName("gmailAttachChip")
                chip.setStyleSheet(self._attach_chip_qss())
                self._attach_lay.addWidget(chip)
            self._attach_lay.addStretch()
            self._attach_wrap.setVisible(True)
        else:
            self._attach_wrap.setVisible(False)

        # 본문
        body = mail.get("body_html", "")
        if body:
            css = (
                "<style>"
                "html, body {"
                "  font-family: Arial, Helvetica, sans-serif;"
                "  font-size: 14px;"
                "  color: #202124;"
                "  background: #ffffff !important;"
                "  margin: 0; padding: 14px 20px;"
                "}"
                "a { color: #1a73e8; text-decoration: none; }"
                "a:hover { text-decoration: underline; }"
                "img { max-width: 100% !important; height: auto !important; display: inline-block; }"
                "* { word-wrap: break-word; overflow-wrap: break-word; box-sizing: border-box; }"
                "pre, code { white-space: pre-wrap; word-wrap: break-word;"
                "  font-family: 'Courier New', 'DejaVu Sans Mono', monospace; font-size: 12px; }"
                "table { border-collapse: collapse; max-width: 100% !important; }"
                "td, th { word-wrap: break-word; max-width: 100%; }"
                "</style>"
            )
            self._browser.setHtml(css + body)
        else:
            self._browser.setHtml(f"<p style='color:#888'>{tr('(本文なし)')}</p>")

        self._empty_lbl.hide()
        self._hdr_wrap.show(); self._browser_wrap.show(); self._actions.show()

    def _attach_chip_qss(self) -> str:
        return (
            "QLabel#gmailAttachChip {"
            " background: rgba(10,132,255,0.12); color: #0A84FF;"
            " border: 1px solid rgba(10,132,255,0.30); border-radius: 999px;"
            " padding: 4px 10px; font-size: 11px; font-weight: 700;"
            " font-family: 'JetBrains Mono', 'Consolas', monospace; }"
        )

    def _open_in_browser(self) -> None:
        if self._current and self._current.get("id"):
            mid = urllib.parse.quote(self._current["id"], safe="")
            webbrowser.open(f"https://mail.google.com/mail/u/0/#inbox/{mid}")


# ──────────────────────────────────────────────────────────────────────
# 7. GmailCard — 대시보드 카드 (옵션)
# ──────────────────────────────────────────────────────────────────────
class GmailCard(QFrame):
    """대시보드 — Gmail 진입점 + 안 읽은 메일 카운트 + 최근 3개 미리보기."""
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("gmailDashCard")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._build_ui()
        self._apply_qss()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(10)
        head.addWidget(LeeIconTile(icon=QIcon(":/img/gmail.svg"), color=_C_MAIL,
                                    size=40, radius=10))
        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        t = QLabel("Gmail"); t.setObjectName("gmailDashTitle")
        s = QLabel(tr("受信トレイ")); s.setObjectName("gmailDashSub")
        title_box.addWidget(t); title_box.addWidget(s)
        head.addLayout(title_box, 1)
        self._unread_pill = LeePill("0", variant="accent")
        head.addWidget(self._unread_pill, 0, Qt.AlignTop)
        v.addLayout(head)

        # 최근 3개 미리보기 자리
        self._preview_box = QVBoxLayout(); self._preview_box.setSpacing(4)
        v.addLayout(self._preview_box)

        self._empty_lbl = QLabel(tr("最近: —"))
        self._empty_lbl.setObjectName("gmailDashEmpty")
        v.addWidget(self._empty_lbl)

    def set_unread(self, count: int) -> None:
        self._unread_pill.setText(f"{count:,}")

    def set_recent(self, mails: list) -> None:
        # 기존 미리보기 제거
        while self._preview_box.count() > 0:
            it = self._preview_box.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        if not mails:
            self._empty_lbl.setVisible(True); return
        self._empty_lbl.setVisible(False)
        for m in mails[:3]:
            sender = _sender_name(m.get("from", ""))[:20]
            subj = (m.get("subject") or "(件名なし)")[:32]
            row = QLabel(f"<b>{sender}</b>  ·  {subj}")
            row.setObjectName("gmailDashRow")
            row.setTextFormat(Qt.RichText)
            self._preview_box.addWidget(row)

    def refresh(self) -> None:
        """대시보드 데이터 페치 — INBOX 미읽 수 + 최근 3개."""
        try:
            from app.api.google.auth import is_authenticated
            if not is_authenticated():
                self.set_unread(0); self.set_recent([]); return
            from app.api.google.gmail import FetchLabelsWorker, FetchMailListWorker
            self._lbl_worker = FetchLabelsWorker()
            self._lbl_worker.data_fetched.connect(self._on_labels)
            self._lbl_worker.error.connect(lambda _e: None)
            self._lbl_worker.finished.connect(self._lbl_worker.deleteLater)
            self._lbl_worker.start()

            self._mail_worker = FetchMailListWorker(["INBOX"], max_results=3)
            self._mail_worker.data_fetched.connect(
                lambda mails, _t: self.set_recent(mails)
            )
            self._mail_worker.error.connect(lambda _e: None)
            self._mail_worker.finished.connect(self._mail_worker.deleteLater)
            self._mail_worker.start()
        except Exception as e:
            logger.debug(f"GmailCard.refresh 실패: {e}")

    def _on_labels(self, labels: list) -> None:
        for lbl in labels:
            if lbl.get("id") == "INBOX":
                self.set_unread(int(lbl.get("messagesUnread", 0) or 0))
                return

    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self._is_dark
        bg = "#14161C" if d else "#FFFFFF"
        fg_p = "#F2F4F7" if d else "#0B1220"
        fg_t = "#6B7280" if d else "#8A93A6"
        bs = "rgba(255,255,255,0.06)" if d else "rgba(11,18,32,0.06)"
        self.setStyleSheet(f"""
            QFrame#gmailDashCard {{
                background: {bg}; border: 1px solid {bs};
                border-left: 4px solid {_C_MAIL};
                border-radius: 14px;
            }}
            QFrame#gmailDashCard:hover {{ border-color: {_C_MAIL}; }}
            QLabel#gmailDashTitle {{
                color: {fg_p}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#gmailDashSub {{
                color: {fg_t}; background: transparent; font-size: 11px;
            }}
            QLabel#gmailDashRow {{
                color: {fg_p}; background: transparent; font-size: 11px;
            }}
            QLabel#gmailDashEmpty {{
                color: {fg_t}; background: transparent; font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)


# ──────────────────────────────────────────────────────────────────────
# 8. GmailWidget — 메인 페이지
# ──────────────────────────────────────────────────────────────────────
class GmailWidget(BaseWidget):
    """3-pane Gmail 페이지 (Phase 5.13)."""

    def __init__(self):
        super().__init__()
        self._labels: list = []
        self._selected_label_ids: list[str] = ["INBOX"]
        self._selected_label_name = tr("受信トレイ")
        self._search_query = ""
        self._prev_unread_counts: dict = {}

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_new_mail)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh)

        self._build_ui()
        bus.google_auth_changed.connect(self._on_auth_changed)
        QTimer.singleShot(2250, self._check_auth_and_load)

    # ── UI 빌드 ───────────────────────────────────────────────
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 22, 28, 22); outer.setSpacing(14)

        # 1) DetailHeader
        self._header = LeeDetailHeader(
            title="Gmail",
            subtitle=tr("メール · 受信トレイ"),
            accent=_C_MAIL,
            icon_qicon=QIcon(":/img/gmail.svg"),
            badge=None,
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))

        self._status_pill = LeePill("", variant="info")
        self._header.add_action(self._status_pill)
        self._status_pill.setVisible(False)

        self._btn_refresh = LeeButton("↻  " + tr("更新"), variant="secondary", size="sm")
        self._btn_refresh.clicked.connect(self._refresh_labels_and_mail)
        self._header.add_action(self._btn_refresh)

        outer.addWidget(self._header)

        # 2) 외곽 카드 + 3-pane splitter
        outer_card = QFrame(); outer_card.setObjectName("gmailOuterCard")
        oc = QVBoxLayout(outer_card); oc.setContentsMargins(0, 0, 0, 0); oc.setSpacing(0)
        outer.addWidget(outer_card, 1)
        self._outer_card = outer_card

        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)
        oc.addWidget(self._splitter, 1)

        # 좌측: 라벨
        s = self.settings
        alarm = set(s.get("gmail_alarm_labels", ["INBOX"]))
        visible_ids = s.get("gmail_visible_labels", None)
        self._label_panel = LabelListPanel(alarm, visible_ids)
        self._label_panel.setMinimumWidth(180)
        self._label_panel.setMaximumWidth(280)
        self._label_panel.label_selection_changed.connect(self._on_labels_selected)
        self._label_panel.alarm_toggled.connect(self._on_alarm_toggled)
        self._label_panel.visible_changed.connect(self._on_visible_labels_changed)
        self._label_panel.mark_label_all_read.connect(self._on_mark_label_all_read)

        # 중앙: 메일 리스트
        self._mail_panel = MailListPanel()
        self._mail_panel.setMinimumWidth(320)
        self._mail_panel.setMaximumWidth(440)
        self._mail_panel.mail_selected.connect(self._on_mail_selected)
        self._mail_panel.load_more_requested.connect(self._load_more_mails)
        self._mail_panel.search_changed.connect(self._on_search_changed)
        self._mail_panel.bulk_action.connect(self._on_bulk_action)

        # 우측: 미리보기
        self._preview_panel = MailPreviewPanel()
        self._preview_panel.reply_clicked.connect(self._on_reply)
        self._preview_panel.reply_all_clicked.connect(self._on_reply_all)
        self._preview_panel.forward_clicked.connect(self._on_forward)

        self._splitter.addWidget(self._label_panel)
        self._splitter.addWidget(self._mail_panel)
        self._splitter.addWidget(self._preview_panel)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setStretchFactor(2, 1)
        self._splitter.setSizes([200, 380, 720])

        # 3) 미인증 오버레이
        self._auth_overlay = self._build_auth_overlay()
        outer.addWidget(self._auth_overlay)
        self._auth_overlay.setVisible(False)

        # 단축키: Ctrl+F → 검색 포커스
        from PySide6.QtGui import QShortcut, QKeySequence
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self._mail_panel.search_input.setFocus()
        )

    def _build_auth_overlay(self) -> QFrame:
        f = QFrame(); f.setObjectName("gmailAuthOverlay")
        lay = QVBoxLayout(f); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(8)
        lbl = QLabel("🔑  " + tr("Google 認証が必要です"))
        lbl.setObjectName("gmailAuthLbl"); lbl.setAlignment(Qt.AlignCenter)
        sub = QLabel(tr("設定画面から Google アカウントで認証してください。"))
        sub.setObjectName("gmailAuthSub"); sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(lbl); lay.addWidget(sub)
        return f

    # ── 테마 ─────────────────────────────────────────────────
    def apply_theme_custom(self) -> None:
        self._header.set_theme(self.is_dark)
        self._label_panel.set_theme(self.is_dark)
        self._preview_panel.set_theme(self.is_dark)
        self._apply_qss()

    def _apply_qss(self) -> None:
        d = self.is_dark
        bg_app        = "#0A0B0F" if d else "#F5F6F8"
        bg_surface    = "#14161C" if d else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if d else "#F0F2F5"
        bg_alt        = "#161922" if d else "#F7F8FA"
        fg_primary    = "#F2F4F7" if d else "#0B1220"
        fg_secondary  = "#A8B0BD" if d else "#4A5567"
        fg_tertiary   = "#6B7280" if d else "#8A93A6"
        border_subtle = "rgba(255,255,255,0.04)" if d else "rgba(11,18,32,0.06)"  # 글로벌 TOKENS 정합
        border        = "rgba(255,255,255,0.10)" if d else "rgba(11,18,32,0.10)"
        sel_bg        = "rgba(234,67,53,0.14)" if d else "rgba(234,67,53,0.10)"
        accent_bg     = "rgba(234,67,53,0.18)" if d else "rgba(234,67,53,0.10)"

        self.setStyleSheet(f"""
            QFrame#gmailOuterCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QSplitter::handle {{ background: transparent; }}

            /* ── 라벨 패널 ── */
            QFrame#gmailLabelHdr {{
                background: {bg_surface_2};
                border-bottom: 1px solid {border_subtle};
                border-top-left-radius: 16px;
            }}
            QLabel#gmailLabelTitle {{
                color: {fg_secondary}; background: transparent;
                font-size: 11px; font-weight: 800;
                letter-spacing: 0.06em;
            }}
            QPushButton#gmailMiniBtn {{
                background: {bg_surface}; color: {fg_secondary};
                border: 1px solid {border_subtle}; border-radius: 7px;
                font-size: 13px;
            }}
            QPushButton#gmailMiniBtn:hover {{
                background: {bg_alt}; color: {fg_primary};
            }}
            QTreeWidget#gmailLabelTree {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: none; outline: 0;
                font-size: 12px;
            }}
            QTreeWidget#gmailLabelTree::item {{
                padding: 5px 8px; border-radius: 6px;
            }}
            QTreeWidget#gmailLabelTree::item:selected {{
                background: {accent_bg};
                color: {fg_primary};
            }}
            QTreeWidget#gmailLabelTree::item:hover:!selected {{
                background: {bg_alt};
            }}
            QTreeWidget#gmailLabelTree::branch {{ background: transparent; }}

            /* ── 메일 리스트 패널 ── */
            QFrame#gmailSearchWrap {{
                background: {bg_surface};
                border-bottom: 1px solid {border_subtle};
            }}
            QLineEdit#gmailSearch {{
                background: {bg_surface_2}; color: {fg_primary};
                border: 1px solid {border_subtle}; border-radius: 8px;
                padding: 0 12px; font-size: 12px;
            }}
            QLineEdit#gmailSearch:focus {{ border: 1px solid {_C_MAIL}; }}
            QFrame#gmailBulkBar {{
                background: {accent_bg};
                border-bottom: 1px solid {border_subtle};
            }}
            QLabel#gmailBulkCount {{
                color: {_C_MAIL}; background: transparent;
                font-size: 11.5px; font-weight: 800;
            }}
            QFrame#gmailMailHdr {{
                background: {bg_surface};
                border-bottom: 1px solid {border_subtle};
            }}
            QLabel#gmailMailHdrLbl {{
                color: {fg_primary}; background: transparent;
                font-size: 13px; font-weight: 800;
            }}
            QListWidget#gmailMailList {{
                background: {bg_surface};
                border: none; outline: 0;
            }}
            QListWidget#gmailMailList::item {{
                border-bottom: 1px solid {border_subtle};
                padding: 0;
            }}
            QListWidget#gmailMailList::item:selected {{
                background: {sel_bg};
            }}
            QListWidget#gmailMailList::item:hover:!selected {{
                background: {bg_alt};
            }}
            QFrame#gmailMailRow {{ background: transparent; }}
            QLabel#gmailSender[unread="true"] {{
                color: {fg_primary}; background: transparent;
                font-size: 12.5px; font-weight: 800;
            }}
            QLabel#gmailSender[unread="false"] {{
                color: {fg_secondary}; background: transparent;
                font-size: 12.5px; font-weight: 500;
            }}
            QLabel#gmailDate {{
                color: {fg_tertiary}; background: transparent;
                font-size: 10.5px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QPushButton#gmailStar[starred="true"] {{
                color: #F4B400; background: transparent;
                border: none; font-size: 14px;
            }}
            QPushButton#gmailStar[starred="false"] {{
                color: {fg_tertiary}; background: transparent;
                border: none; font-size: 14px;
            }}
            QPushButton#gmailStar:hover {{ color: #F4B400; }}
            QLabel#gmailSubject[unread="true"] {{
                color: {fg_primary}; background: transparent;
                font-size: 12px; font-weight: 700;
            }}
            QLabel#gmailSubject[unread="false"] {{
                color: {fg_secondary}; background: transparent;
                font-size: 12px;
            }}
            QLabel#gmailSnippet {{
                color: {fg_tertiary}; background: transparent;
                font-size: 10.5px;
            }}
            QLabel#gmailChipMore {{
                color: {fg_tertiary}; background: transparent;
                font-size: 9px; font-weight: 700;
            }}
            QCheckBox#gmailMailCheck {{ background: transparent; }}
            QCheckBox#gmailMailCheck::indicator {{
                width: 14px; height: 14px;
                border: 1.5px solid {fg_tertiary}; border-radius: 3px;
                background: transparent;
            }}
            QCheckBox#gmailMailCheck::indicator:checked {{
                background: {_C_MAIL}; border-color: {_C_MAIL};
                image: none;
            }}

            QLabel#gmailEmpty {{
                color: {fg_tertiary}; background: transparent;
                font-size: 12px;
            }}

            /* ── 미리보기 패널 ── */
            QFrame#gmailPreviewHdr {{
                background: {bg_surface_2};
                border-bottom: 1px solid {border_subtle};
                border-top-right-radius: 16px;
            }}
            QLabel#gmailPreviewSubj {{
                color: {fg_primary}; background: transparent;
                font-size: 17px; font-weight: 800;
            }}
            QLabel#gmailPreviewFrom {{
                color: {fg_secondary}; background: transparent;
                font-size: 12px;
            }}
            QLabel#gmailPreviewDate {{
                color: {fg_tertiary}; background: transparent;
                font-size: 11px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QFrame#gmailAttachWrap {{ background: transparent; }}
            QFrame#gmailPreviewActions {{
                background: {bg_surface_2};
                border-top: 1px solid {border_subtle};
                border-bottom-right-radius: 16px;
            }}
            QFrame#gmailPreviewBrowserWrap {{
                background: {bg_surface};
                border: none;
            }}
            QTextBrowser#gmailPreviewBrowser {{
                background: #FFFFFF;
                color: #202124;
                border: 1px solid {border_subtle};
                border-radius: 12px;
            }}
            QLabel#gmailPreviewEmpty {{
                color: {fg_tertiary}; background: {bg_surface};
                font-size: 13px;
            }}

            /* ── 미인증 오버레이 ── */
            QFrame#gmailAuthOverlay {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 16px;
            }}
            QLabel#gmailAuthLbl {{
                color: {fg_secondary}; background: transparent;
                font-size: 15px; font-weight: 700;
            }}
            QLabel#gmailAuthSub {{
                color: {fg_tertiary}; background: transparent;
                font-size: 12px;
            }}
        """)

    # ── 인증 / 데이터 로드 ────────────────────────────────────
    def _check_auth_and_load(self) -> None:
        from app.api.google.auth import is_authenticated
        if is_authenticated():
            self._auth_overlay.setVisible(False)
            self._outer_card.setVisible(True)
            self._refresh_labels_and_mail()
            self._start_poll_timer()
        else:
            self._outer_card.setVisible(False)
            self._auth_overlay.setVisible(True)

    def _start_poll_timer(self) -> None:
        interval_min = self.settings.get("gmail_poll_interval", 5)
        self._poll_timer.start(interval_min * 60 * 1000)
        auto_min = self.settings.get("gmail_auto_refresh_interval", 10)
        self._auto_refresh_timer.start(auto_min * 60 * 1000)

    # ── 設定変更 즉시 반영 (bus.settings_saved → _apply_settings_all → 본 hook) ──
    def apply_settings_custom(self):
        """settings 변경 시 호출 — 폴링 / 자동 갱신 / 메일 건수 재적용."""
        try:
            from app.api.google.auth import is_authenticated
            if not is_authenticated():
                return
            poll_min = int(self.settings.get("gmail_poll_interval", 5))
            auto_min = int(self.settings.get("gmail_auto_refresh_interval", 10))
            if self._poll_timer.isActive():
                self._poll_timer.start(max(1, poll_min) * 60 * 1000)
            if self._auto_refresh_timer.isActive():
                self._auto_refresh_timer.start(max(1, auto_min) * 60 * 1000)
            # gmail_max_results 는 다음 fetch 호출 시 settings 에서 자동 반영
        except Exception as e:
            logger.debug(f"Gmail apply_settings_custom 실패: {e}")

    def _auto_refresh(self) -> None:
        from app.api.google.auth import is_authenticated
        if is_authenticated():
            self._refresh_labels_and_mail()

    def _set_status(self, text: str) -> None:
        if text:
            self._status_pill.setText(text)
            self._status_pill.setVisible(True)
        else:
            self._status_pill.setVisible(False)

    def _refresh_labels_and_mail(self) -> None:
        from app.api.google.gmail import FetchLabelsWorker
        self._set_status(tr("読込中..."))
        w = FetchLabelsWorker()
        w.data_fetched.connect(self._on_labels_fetched)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _fetch_mail_list(self, label_ids: list[str], page_token: str = "",
                         q: str = "") -> None:
        from app.api.google.gmail import FetchMailListWorker
        if not page_token:
            self._mail_panel.set_loading(True)
            self.set_loading(True, self._mail_panel)
            self._set_status(tr("読込中..."))
        max_r = self.settings.get("gmail_max_results", 50)
        w = FetchMailListWorker(label_ids, max_results=max_r,
                                page_token=page_token, q=q)
        if page_token:
            w.data_fetched.connect(self._on_more_mails_fetched)
        else:
            w.data_fetched.connect(self._on_mails_fetched)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _load_more_mails(self, page_token: str) -> None:
        self._fetch_mail_list(self._selected_label_ids, page_token, q=self._search_query)

    def _poll_new_mail(self) -> None:
        from app.api.google.auth import is_authenticated
        if not is_authenticated():
            return
        target = set(self._label_panel.get_alarm_labels())
        target.add("INBOX")
        target.update(self._selected_label_ids)
        from app.api.google.gmail import PollNewMailWorker
        w = PollNewMailWorker(list(target), self._prev_unread_counts)
        w.new_mail.connect(self._on_new_mail_detected)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    # ── 핸들러 ───────────────────────────────────────────────
    def _on_labels_fetched(self, labels: list) -> None:
        self._labels = labels
        for lbl in labels:
            self._prev_unread_counts[lbl.get("id", "")] = lbl.get("messagesUnread", 0)
        self._label_panel.set_labels(labels)
        self._mail_panel.set_label_lookup(labels)
        # 첫 진입에는 INBOX 자동 선택
        if not self._label_panel.selected_label_ids():
            self._label_panel.select_first()
        else:
            # 라벨 갱신 후 현재 선택 라벨 유지하면서 메일 다시 fetch
            self._fetch_mail_list(self._selected_label_ids, q=self._search_query)
        self._set_status("")

    def _on_labels_selected(self, label_ids: list[str]) -> None:
        if not label_ids:
            return
        self._selected_label_ids = label_ids
        # 헤더 이름 — 첫 번째 라벨 + (외 N)
        first = next((l for l in self._labels if l.get("id") == label_ids[0]), None)
        name = _label_display_name(first) if first else label_ids[0]
        if len(label_ids) > 1:
            name = f"{name}  +{len(label_ids) - 1}"
        self._selected_label_name = name
        self._mail_panel.set_header(name)
        self._preview_panel.show_empty()
        self._fetch_mail_list(label_ids, q=self._search_query)

    def _on_mails_fetched(self, mails: list, next_token: str) -> None:
        self.set_loading(False, self._mail_panel)
        self._mail_panel.set_header(self._selected_label_name)
        self._mail_panel.set_mails(mails, next_token)
        self._preview_panel.show_empty()
        self._set_status("")

    def _on_more_mails_fetched(self, mails: list, next_token: str) -> None:
        self._mail_panel.append_mails(mails, next_token)
        self._mail_panel.reset_load_btn()

    def _on_search_changed(self, q: str) -> None:
        self._search_query = q
        self._fetch_mail_list(self._selected_label_ids, q=q)

    def _on_mail_selected(self, mail: dict) -> None:
        mid = mail.get("id", "")
        if not mid:
            return
        if "body_html" in mail:
            self._preview_panel.show_mail(mail)
            self._maybe_mark_read(mail); return
        self._preview_panel.show_loading()
        self.set_loading(True, self._preview_panel)
        from app.api.google.gmail import FetchMailDetailWorker
        w = FetchMailDetailWorker(mid)
        w.data_fetched.connect(self._on_mail_detail_fetched)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_mail_detail_fetched(self, mail: dict) -> None:
        self.set_loading(False, self._preview_panel)
        self._preview_panel.show_mail(mail)
        self._maybe_mark_read(mail)

    def _maybe_mark_read(self, mail: dict) -> None:
        if not mail.get("is_unread", False):
            return
        mail["is_unread"] = False
        mid = mail.get("id", "")
        self._mail_panel.mark_read_local(mid)
        for lid in mail.get("label_ids", []):
            for lbl in self._labels:
                if lbl.get("id") == lid:
                    cur = lbl.get("messagesUnread", 0)
                    new = max(0, cur - 1)
                    lbl["messagesUnread"] = new
                    self._prev_unread_counts[lid] = new
                    self._label_panel.update_unread(lid, new)
                    break
        from app.api.google.gmail import MarkReadWorker
        w = MarkReadWorker(mid)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_new_mail_detected(self, label_name_or_id: str, unread_count: int) -> None:
        matched_id = None
        for lbl in self._labels:
            if lbl.get("name") == label_name_or_id or lbl.get("id") == label_name_or_id:
                matched_id = lbl.get("id", "")
                self._prev_unread_counts[matched_id] = unread_count
                lbl["messagesUnread"] = unread_count
                self._label_panel.update_unread(matched_id, unread_count)
                if matched_id in self._selected_label_ids:
                    self._fetch_mail_list(self._selected_label_ids, q=self._search_query)
                break
        if matched_id and matched_id in self._label_panel.get_alarm_labels():
            bus.gmail_new_mail.emit(label_name_or_id, unread_count)

    def _on_mark_label_all_read(self, label_id: str) -> None:
        from app.api.google.gmail import MarkAllReadWorker
        self._set_status(tr("既読処理中..."))
        w = MarkAllReadWorker(label_id)
        w.success.connect(self._on_mark_all_read_done)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_mark_all_read_done(self, _count: int) -> None:
        self._set_status("")
        self._refresh_labels_and_mail()

    def _on_bulk_action(self, action: str, mail_ids: list[str]) -> None:
        if not mail_ids:
            return
        from app.api.google.gmail import BatchModifyWorker, BatchDeleteWorker
        self._set_status(tr("一括処理中..."))

        def _on_done(_n: int):
            self._set_status("")
            self._refresh_labels_and_mail()

        if action == "read":
            w = BatchModifyWorker(mail_ids, remove_labels=["UNREAD"])
        elif action == "archive":
            w = BatchModifyWorker(mail_ids, remove_labels=["INBOX"])
        elif action == "delete":
            if not LeeDialog.confirm(
                tr("削除の確認"),
                tr("選択した {0} 件のメールをゴミ箱に移動しますか?").format(len(mail_ids)),
                ok_text=tr("削除"), destructive=True, parent=self,
            ):
                self._set_status(""); return
            w = BatchDeleteWorker(mail_ids)
        else:
            return
        w.success.connect(_on_done)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        # 낙관적 UI — 즉시 화면에서 제거 (read 는 제외)
        if action in ("archive", "delete"):
            self._mail_panel.remove_local(mail_ids)
        elif action == "read":
            for mid in mail_ids:
                self._mail_panel.mark_read_local(mid)
        w.start()
        self.track_worker(w)

    def _on_alarm_toggled(self, _label_id: str, _enabled: bool) -> None:
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["gmail_alarm_labels"] = self._label_panel.get_alarm_labels()
        save_settings(s)

    def _on_visible_labels_changed(self, ids: list) -> None:
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["gmail_visible_labels"] = ids
        save_settings(s)

    def _on_reply(self, mail: dict) -> None:
        self._open_compose("reply", mail)

    def _on_reply_all(self, mail: dict) -> None:
        self._open_compose("reply_all", mail)

    def _on_forward(self, mail: dict) -> None:
        self._open_compose("forward", mail)

    def _open_compose(self, mode: str, mail: dict) -> None:
        """Gmail 웹 작성 화면을 브라우저로 오픈 (네이티브 작성 다이얼로그는 향후 별도 구현)."""
        thread_id = mail.get("thread_id") or mail.get("id", "")
        if not thread_id:
            return
        action = {"reply": "reply", "reply_all": "replyall", "forward": "forward"}.get(mode, "reply")
        url = f"https://mail.google.com/mail/u/0/#inbox/{urllib.parse.quote(thread_id, safe='')}"
        webbrowser.open(url)
        bus.toast_requested.emit(tr("ブラウザで {0} を開きます").format(action), "info")

    def _on_error(self, err: str) -> None:
        self.set_loading(False, self._mail_panel)
        self.set_loading(False, self._preview_panel)
        self._set_status(tr("エラー"))
        logger.error(f"Gmail error: {err}")

    def _on_auth_changed(self, authenticated: bool) -> None:
        if authenticated:
            self._auth_overlay.setVisible(False)
            self._outer_card.setVisible(True)
            self._refresh_labels_and_mail()
            self._start_poll_timer()
        else:
            self._outer_card.setVisible(False)
            self._auth_overlay.setVisible(True)
            self._poll_timer.stop()
            self._auto_refresh_timer.stop()
            self._label_panel.set_labels([])
            self._mail_panel.set_mails([], "")
            self._preview_panel.show_empty()
            self._set_status("")

    # ── 라이프사이클 ─────────────────────────────────────────
    def closeEvent(self, event):
        self._poll_timer.stop()
        self._auto_refresh_timer.stop()
        try:
            bus.google_auth_changed.disconnect(self._on_auth_changed)
        except (RuntimeError, TypeError):
            pass
        super().closeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)
        from app.api.google.auth import is_authenticated
        if is_authenticated() and not self._labels:
            self._refresh_labels_and_mail()
            self._start_poll_timer()


__all__ = ["GmailWidget", "GmailCard"]

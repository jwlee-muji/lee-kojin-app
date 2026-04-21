"""
Gmail 위젯 - 3 페인 레이아웃 (라벨 목록 / 메일 목록 / HTML 미리보기)
"""
import logging
import urllib.parse
import webbrowser
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem,
    QSplitter, QScrollArea, QTextBrowser,
    QSizePolicy, QApplication, QMenu, QDialog,
)
from PySide6.QtCore import Qt, QTimer, QUrl, QSize, Signal
from PySide6.QtGui import QColor, QFont, QCursor, QAction, QBrush
from app.ui.common import BaseWidget
from app.ui.theme import UIColors
from app.core.i18n import tr
from app.core.events import bus

logger = logging.getLogger(__name__)

# 시스템 라벨 표시 이름 매핑 (일본어)
_SYSTEM_LABEL_NAMES = {
    "INBOX":     "受信トレイ",
    "STARRED":   "スター付き",
    "IMPORTANT": "重要",
    "SENT":      "送信済み",
    "SPAM":      "迷惑メール",
    "TRASH":     "ゴミ箱",
}
_SYSTEM_LABEL_ICONS = {
    "INBOX":     "📥",
    "STARRED":   "⭐",
    "IMPORTANT": "❗",
    "SENT":      "📤",
    "SPAM":      "🚫",
    "TRASH":     "🗑",
}


# ── 안전한 텍스트 브라우저 (외부 이미지 차단) ─────────────────────────────

class _SafeTextBrowser(QTextBrowser):
    """외부 URL 로드를 차단하여 트래킹 픽셀·로컬 파일 접근을 방지."""
    _BLOCKED_SCHEMES = frozenset({"http", "https", "file", "data", "javascript", "ftp"})

    def loadResource(self, resource_type, url: QUrl):
        if url.scheme() in self._BLOCKED_SCHEMES:
            return None
        return super().loadResource(resource_type, url)


# ── 라벨 표시 설정 다이얼로그 ────────────────────────────────────────────────

class LabelEditDialog(QDialog):
    """表示するラベルを選択・並び替え (ドラッグ対応) するダイアログ。"""

    def __init__(self, all_labels: list, visible_ids: list | None,
                 is_dark: bool = True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("ラベル表示設定"))
        self.setMinimumWidth(320)
        self.setMinimumHeight(420)
        self.setModal(True)
        self._result_ids: list | None = None
        self._build_ui(all_labels, visible_ids, is_dark)

    def _build_ui(self, all_labels: list, visible_ids: list | None, is_dark: bool):
        d   = is_dark
        pc  = UIColors.get_panel_colors(d)
        bg  = pc["bg"]
        bg2 = pc["hover"]
        bd  = pc["border"]
        txt = pc["text"]
        accent = UIColors.ACCENT_DARK if d else UIColors.ACCENT_LIGHT
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background: {bg}; color: {txt}; }}
            QListWidget {{ background: {bg2}; border: 1px solid {bd}; border-radius: 4px; }}
            QListWidget::item {{ padding: 6px 8px; }}
            QListWidget::item:selected {{ background: {accent}; color: #ffffff; }}
            QPushButton {{ background: {'#3e3e42' if d else '#e0e0e0'};
                           color: {txt}; border: none; border-radius: 4px; padding: 0 10px; }}
            QPushButton:hover {{ background: {'#505055' if d else '#d0d0d0'}; }}
            QPushButton#applyBtn {{ background: {accent}; color: #fff; font-weight: bold; }}
            QPushButton#applyBtn:hover {{ background: {'#1177bb' if d else '#1976d2'}; }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        hint = QLabel(tr("表示するラベルを選択してください。ドラッグで並び替え可能です。"))
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size: 11px; color: #888;")
        layout.addWidget(hint)

        self._list = QListWidget()
        self._list.setDragDropMode(QListWidget.InternalMove)
        self._list.setSelectionMode(QListWidget.SingleSelection)

        for lbl_data in all_labels:
            lid  = lbl_data.get("id", "")
            name = lbl_data.get("name", lid)
            if lid in _SYSTEM_LABEL_NAMES:
                name = f"{_SYSTEM_LABEL_ICONS.get(lid, '')}  {tr(_SYSTEM_LABEL_NAMES[lid])}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, lid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            is_visible = (visible_ids is None) or (lid in visible_ids)
            item.setCheckState(Qt.Checked if is_visible else Qt.Unchecked)
            self._list.addItem(item)

        layout.addWidget(self._list, 1)

        # すべて選択/解除
        sel_row = QHBoxLayout()
        btn_all  = QPushButton(tr("すべて表示"))
        btn_none = QPushButton(tr("すべて非表示"))
        btn_all.setFixedHeight(28)
        btn_none.setFixedHeight(28)
        btn_all.clicked.connect(lambda: [
            self._list.item(i).setCheckState(Qt.Checked)
            for i in range(self._list.count())
        ])
        btn_none.clicked.connect(lambda: [
            self._list.item(i).setCheckState(Qt.Unchecked)
            for i in range(self._list.count())
        ])
        sel_row.addWidget(btn_all); sel_row.addWidget(btn_none); sel_row.addStretch()
        layout.addLayout(sel_row)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet(f"border-top: 1px solid {bd};")
        layout.addWidget(sep)

        final_row = QHBoxLayout()
        btn_cancel = QPushButton(tr("キャンセル"))
        btn_cancel.setFixedHeight(32); btn_cancel.clicked.connect(self.reject)
        btn_ok = QPushButton(tr("適用"))
        btn_ok.setObjectName("applyBtn"); btn_ok.setFixedHeight(32)
        btn_ok.clicked.connect(self._on_ok)
        final_row.addStretch()
        final_row.addWidget(btn_cancel)
        final_row.addWidget(btn_ok)
        layout.addLayout(final_row)

    def _on_ok(self):
        self._result_ids = [
            self._list.item(i).data(Qt.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.Checked
        ]
        self.accept()

    def get_visible_ids(self) -> list | None:
        """適用 → ordered list of visible IDs. キャンセル → None."""
        return self._result_ids


# ── 라벨 계층 트리 헬퍼 ──────────────────────────────────────────────────────

def _build_label_tree(labels: list) -> tuple[list, dict]:
    """
    Gmail 라벨 이름의 "/" 구분자로 부모-자식 관계를 파악.
    Returns (root_labels, children_map {parent_id: [child_label, ...]})
    """
    by_name: dict[str, dict] = {l.get("name", ""): l for l in labels}
    children: dict[str, list] = {}
    roots: list = []

    for lbl in labels:
        name = lbl.get("name", "")
        if lbl.get("type") == "system" or "/" not in name:
            roots.append(lbl)
            continue
        parent_name = name.rsplit("/", 1)[0]
        parent = by_name.get(parent_name)
        if parent:
            pid = parent.get("id", "")
            children.setdefault(pid, []).append(lbl)
        else:
            roots.append(lbl)

    return roots, children


# ── 라벨 목록 패널 ────────────────────────────────────────────────────────────

class LabelListPanel(QWidget):
    """라벨 목록. 미읽 배지 + 우클릭 알람 + 편집(표시 설정)."""
    label_selected    = Signal(str, str)   # (label_id, label_name)
    alarm_toggled     = Signal(str, bool)  # (label_id, enabled)
    visible_changed   = Signal(list)       # ordered visible label IDs

    def __init__(self, alarm_labels: set, visible_ids: list | None = None, parent=None):
        super().__init__(parent)
        self._alarm_labels  = set(alarm_labels)
        self._all_labels: list = []
        self._visible_ids: list | None = visible_ids  # None = all
        self._labels: list = []          # currently displayed labels
        self._selected_id: str = ""
        self._is_dark = True
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더
        hdr = QFrame()
        hdr.setObjectName("gmailLabelHdr")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(12, 8, 8, 8)
        title = QLabel("Gmail")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")

        self._btn_edit_labels = QPushButton("⚙")
        self._btn_edit_labels.setFixedSize(24, 24)
        self._btn_edit_labels.setToolTip(tr("ラベル表示設定"))
        self._btn_edit_labels.setCursor(Qt.PointingHandCursor)
        self._btn_edit_labels.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #888; font-size: 14px; }"
            "QPushButton:hover { color: #ccc; }"
        )
        self._btn_edit_labels.clicked.connect(self._open_label_editor)

        hrow.addWidget(title)
        hrow.addStretch()
        hrow.addWidget(self._btn_edit_labels)
        layout.addWidget(hdr)

        # 라벨 트리
        self._list = QTreeWidget()
        self._list.setObjectName("labelList")
        self._list.setHeaderHidden(True)
        self._list.setIndentation(16)
        self._list.setRootIsDecorated(True)
        self._list.setStyleSheet("""
            QTreeWidget { border: none; outline: none; }
            QTreeWidget::item {
                padding: 5px 8px;
            }
            QTreeWidget::branch {
                background: transparent;
            }
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings {
                border-image: none;
                image: none;
            }
        """)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.itemSelectionChanged.connect(self._on_item_changed)
        layout.addWidget(self._list, 1)

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark
        self._refresh_list()   # 라벨 텍스트 색상을 테마에 맞게 재렌더링

    def set_labels(self, labels: list):
        self._all_labels = labels
        self._apply_visible_filter()

    def _apply_visible_filter(self):
        """_visible_ids に従って表示ラベルを絞り込み、リストを更新。"""
        if self._visible_ids is None:
            self._labels = list(self._all_labels)
        else:
            id_order = {lid: i for i, lid in enumerate(self._visible_ids)}
            self._labels = sorted(
                [l for l in self._all_labels if l.get("id") in id_order],
                key=lambda l: id_order.get(l.get("id", ""), 9999),
            )
        self._refresh_list()

    def set_visible_ids(self, visible_ids: list | None):
        self._visible_ids = visible_ids
        self._apply_visible_filter()

    def _open_label_editor(self):
        dlg = LabelEditDialog(
            self._all_labels, self._visible_ids,
            is_dark=self._is_dark, parent=self,
        )
        if dlg.exec() == QDialog.Accepted:
            result = dlg.get_visible_ids()
            if result is not None:
                self._visible_ids = result
                self._apply_visible_filter()
                self.visible_changed.emit(result)

    def update_unread(self, label_id: str, count: int):
        item = self._find_item(label_id)
        if item:
            lbl = self._get_label_by_id(label_id)
            if lbl:
                lbl["messagesUnread"] = count
            self._update_item_text(item, lbl or {"id": label_id})

    def _get_label_by_id(self, label_id: str) -> dict | None:
        for lbl in self._labels:
            if lbl.get("id") == label_id:
                return lbl
        return None

    def _find_item(self, label_id: str) -> QTreeWidgetItem | None:
        """DFS search for QTreeWidgetItem by label_id."""
        def _search(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            if item.data(0, Qt.UserRole) == label_id:
                return item
            for i in range(item.childCount()):
                found = _search(item.child(i))
                if found:
                    return found
            return None
        for i in range(self._list.topLevelItemCount()):
            found = _search(self._list.topLevelItem(i))
            if found:
                return found
        return None

    def _refresh_list(self):
        current_id = self._selected_id
        self._list.blockSignals(True)
        self._list.clear()

        roots, children = _build_label_tree(self._labels)

        def _add(lbl: dict, parent: QTreeWidgetItem | None = None) -> QTreeWidgetItem:
            lid = lbl.get("id", "")
            item = QTreeWidgetItem()
            item.setData(0, Qt.UserRole, lid)
            self._update_item_text(item, lbl)
            if parent is None:
                self._list.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child_lbl in children.get(lid, []):
                _add(child_lbl, item)
            if children.get(lid):
                item.setExpanded(True)
            return item

        selected_item: QTreeWidgetItem | None = None
        for lbl in roots:
            it = _add(lbl)
            if lbl.get("id") == current_id:
                selected_item = it

        self._list.blockSignals(False)
        self._list.resizeColumnToContents(0)   # 텍스트 잘림 방지

        if selected_item:
            self._list.setCurrentItem(selected_item)
        elif self._list.topLevelItemCount() > 0:
            self._list.setCurrentItem(self._list.topLevelItem(0))

    def _update_item_text(self, item: QTreeWidgetItem, lbl: dict):
        lid    = lbl.get("id", "")
        name   = lbl.get("name", lid)
        unread = lbl.get("messagesUnread", 0) or 0

        if lid in _SYSTEM_LABEL_NAMES:
            icon = _SYSTEM_LABEL_ICONS.get(lid, "")
            name = f"{icon}  {tr(_SYSTEM_LABEL_NAMES[lid])}"
        elif "/" in name:
            name = name.rsplit("/", 1)[1]   # 자식 라벨은 마지막 컴포넌트만 표시

        alarm_icon = " 🔔" if lid in self._alarm_labels else ""

        if unread > 0:
            item.setText(0, f"{name}{alarm_icon}  ({unread})")
            font = item.font(0); font.setBold(True); item.setFont(0, font)
            unread_color = "#5ab3ff" if self._is_dark else UIColors.ACCENT_LIGHT
            item.setForeground(0, QBrush(QColor(unread_color)))
        else:
            item.setText(0, f"{name}{alarm_icon}")
            font = item.font(0); font.setBold(False); item.setFont(0, font)
            pc = UIColors.get_panel_colors(self._is_dark)
            item.setForeground(0, QBrush(QColor(pc["text"])))

    def _on_item_changed(self):
        items = self._list.selectedItems()
        if not items:
            return
        item = items[0]
        lid  = item.data(0, Qt.UserRole)
        self._selected_id = lid
        lbl  = self._get_label_by_id(lid)
        name = lbl.get("name", lid) if lbl else lid
        if "/" in name:
            name = name.rsplit("/", 1)[1]
        if lid in _SYSTEM_LABEL_NAMES:
            name = tr(_SYSTEM_LABEL_NAMES[lid])
        self.label_selected.emit(lid, name)

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        lid      = item.data(0, Qt.UserRole)
        is_alarm = lid in self._alarm_labels

        menu = QMenu(self)
        if is_alarm:
            act = QAction(f"🔕  {tr('アラームをオフ')}", self)
        else:
            act = QAction(f"🔔  {tr('アラームをオン')}", self)
        act.triggered.connect(lambda: self._toggle_alarm(lid, item))
        menu.addAction(act)
        menu.exec(QCursor.pos())

    def _toggle_alarm(self, label_id: str, item: QTreeWidgetItem):
        if label_id in self._alarm_labels:
            self._alarm_labels.discard(label_id)
            enabled = False
        else:
            self._alarm_labels.add(label_id)
            enabled = True
        lbl = self._get_label_by_id(label_id)
        if lbl:
            self._update_item_text(item, lbl)
        self.alarm_toggled.emit(label_id, enabled)

    def get_alarm_labels(self) -> list:
        return list(self._alarm_labels)


# 아바타 색상 팔레트 (발신자 이름 해시로 선택)
_AVATAR_COLORS = [
    "#4285F4", "#EA4335", "#FBBC05", "#34A853",
    "#FF6D00", "#46BDC6", "#7986CB", "#E67C73",
    "#F4511E", "#0B8043", "#8E24AA", "#D50000",
]


def _sender_initial(sender_raw: str) -> tuple[str, str]:
    """(이니셜, 아바타 색상) 반환."""
    if "<" in sender_raw:
        name = sender_raw[:sender_raw.index("<")].strip().strip('"')
    else:
        name = sender_raw.split("@")[0] if "@" in sender_raw else sender_raw
    initial = name[0].upper() if name else "?"
    color   = _AVATAR_COLORS[abs(hash(name)) % len(_AVATAR_COLORS)]
    return initial, color


def _format_mail_date(date_str: str) -> str:
    if not date_str:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        import datetime as _dt
        dt       = parsedate_to_datetime(date_str)
        # ローカルタイムゾーンに変換して「今日か否か」を正確に判定
        local_dt = dt.astimezone()
        now      = _dt.datetime.now().astimezone()
        if local_dt.date() == now.date():
            return local_dt.strftime("%H:%M")
        elif local_dt.year == now.year:
            return local_dt.strftime("%m/%d")
        else:
            return local_dt.strftime("%Y/%m/%d")
    except Exception:
        return date_str[:10]


# ── 메일 목록 패널 ────────────────────────────────────────────────────────────

class _MailItemWidget(QWidget):
    """메일 목록 아이템 — 아바타 + 발신자/날짜/제목/스니펫."""
    def __init__(self, mail: dict, parent=None):
        super().__init__(parent)
        self._mail = mail
        self._build_ui()

    def _build_ui(self):
        is_unread = self._mail.get("is_unread", False)
        sender_raw = self._mail.get("from", "")
        initial, av_color = _sender_initial(sender_raw)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 8, 12, 8)
        root.setSpacing(10)

        # ── 왼쪽: 미읽 점 + 아바타 ──────────────────────────
        left = QVBoxLayout()
        left.setSpacing(0)
        left.setAlignment(Qt.AlignVCenter)

        # 미읽 파란 점 (레이아웃 기반, absolute 아님)
        dot_row = QHBoxLayout()
        dot_row.setContentsMargins(0, 0, 0, 0)
        if is_unread:
            dot = QFrame()
            dot.setFixedSize(7, 7)
            dot.setStyleSheet("background: #4285F4; border-radius: 3px;")
            dot_row.addWidget(dot)
        else:
            spacer = QFrame()
            spacer.setFixedSize(7, 7)
            dot_row.addWidget(spacer)

        # 아바타 원
        avatar = QLabel(initial)
        avatar.setFixedSize(36, 36)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setStyleSheet(f"""
            QLabel {{
                background: {av_color};
                color: white;
                border-radius: 18px;
                font-size: 15px;
                font-weight: bold;
            }}
        """)

        left.addLayout(dot_row)
        left.addWidget(avatar)
        root.addLayout(left)

        # ── 오른쪽: 텍스트 영역 ──────────────────────────────
        content = QVBoxLayout()
        content.setSpacing(1)
        content.setAlignment(Qt.AlignVCenter)

        # 발신자 + 날짜
        top = QHBoxLayout()
        top.setSpacing(6)

        if "<" in sender_raw:
            sender = sender_raw[:sender_raw.index("<")].strip().strip('"')
        else:
            sender = sender_raw
        sender_lbl = QLabel(sender[:28] if sender else "(不明)")
        weight = "700" if is_unread else "400"
        sender_lbl.setStyleSheet(f"font-size: 13px; font-weight: {weight};")
        sender_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        date_lbl = QLabel(_format_mail_date(self._mail.get("date", "")))
        date_lbl.setObjectName("mailSecondary")
        date_lbl.setStyleSheet("font-size: 11px;")
        date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        date_lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        top.addWidget(sender_lbl, 1)
        if self._mail.get("is_starred"):
            star = QLabel("★")
            star.setStyleSheet("color: #F4B400; font-size: 12px;")
            top.addWidget(star)
        top.addWidget(date_lbl)

        # 제목
        subject = self._mail.get("subject", tr("(件名なし)"))
        subj_lbl = QLabel(subject[:54] + ("…" if len(subject) > 54 else ""))
        subj_style = f"font-size: 12px; font-weight: {'600' if is_unread else 'normal'};"
        subj_lbl.setStyleSheet(subj_style)

        # 스니펫
        snippet = self._mail.get("snippet", "")
        snip_lbl = QLabel(snippet[:68] + ("…" if len(snippet) > 68 else ""))
        snip_lbl.setObjectName("mailSecondary")
        snip_lbl.setStyleSheet("font-size: 11px;")

        content.addLayout(top)
        content.addWidget(subj_lbl)
        content.addWidget(snip_lbl)
        root.addLayout(content, 1)

    def get_mail(self) -> dict:
        return self._mail


class MailListPanel(QWidget):
    """메일 목록 패널. 다음 페이지 로드 (무한 스크롤)."""
    mail_selected       = Signal(dict)
    load_more_requested = Signal(str)   # (page_token)
    mark_all_read       = Signal()      # 全既読ボタン押下

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_label_id = ""
        self._next_page_token  = ""
        self._loading = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더
        self._hdr = QFrame()
        self._hdr.setObjectName("mailListHdr")
        hrow = QHBoxLayout(self._hdr)
        hrow.setContentsMargins(12, 8, 8, 8)
        self._hdr_lbl = QLabel()
        self._hdr_lbl.setStyleSheet("font-size: 13px; font-weight: bold;")
        self._count_lbl = QLabel()
        self._count_lbl.setStyleSheet("font-size: 11px; color: #888;")
        self._btn_mark_all = QPushButton(tr("すべて既読"))
        self._btn_mark_all.setObjectName("secondaryActionBtn")
        self._btn_mark_all.setFixedHeight(24)
        self._btn_mark_all.setCursor(Qt.PointingHandCursor)
        self._btn_mark_all.clicked.connect(self.mark_all_read.emit)
        self._btn_mark_all.hide()

        hrow.addWidget(self._hdr_lbl)
        hrow.addStretch()
        hrow.addWidget(self._count_lbl)
        hrow.addWidget(self._btn_mark_all)
        layout.addWidget(self._hdr)

        # 메일 목록
        self._list = QListWidget()
        self._list.setObjectName("mailList")
        self._list.setStyleSheet("""
            QListWidget { border: none; outline: none; }
        """)
        self._list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self._list.currentItemChanged.connect(self._on_item_changed)
        self._list.verticalScrollBar().valueChanged.connect(self._on_scroll)
        layout.addWidget(self._list, 1)

        # 빈 상태 표시
        self._empty_lbl = QLabel(tr("このラベルにメールはありません"))
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #555; font-size: 13px;")
        self._empty_lbl.hide()
        layout.addWidget(self._empty_lbl, 1)

        # 더 로드 버튼
        self._btn_more = QPushButton(tr("さらに読み込む"))
        self._btn_more.setObjectName("secondaryActionBtn")
        self._btn_more.setFixedHeight(32)
        self._btn_more.setCursor(Qt.PointingHandCursor)
        self._btn_more.clicked.connect(self._load_more)
        self._btn_more.hide()
        layout.addWidget(self._btn_more)

    def set_header(self, label_name: str):
        self._hdr_lbl.setText(label_name)

    def set_loading(self, loading: bool):
        if loading:
            self._empty_lbl.hide()
            self._count_lbl.setText("")

    def set_mails(self, mails: list, next_token: str):
        self._list.clear()
        self._next_page_token = next_token
        if mails:
            self._count_lbl.setText(f"{len(mails)}{tr('  件')}")
            for mail in mails:
                self._add_mail_item(mail)
            self._list.show()
            self._empty_lbl.hide()
            has_unread = any(m.get("is_unread") for m in mails)
            self._btn_mark_all.setVisible(has_unread)
        else:
            self._count_lbl.setText("")
            self._list.hide()
            self._empty_lbl.show()
            self._btn_mark_all.hide()
        self._btn_more.setVisible(bool(next_token))

    def append_mails(self, mails: list, next_token: str):
        self._next_page_token = next_token
        count = self._list.count()
        for mail in mails:
            self._add_mail_item(mail)
        self._count_lbl.setText(f"{self._list.count()}{tr('  件')}")
        self._btn_more.setVisible(bool(next_token))
        self._loading = False

    def _add_mail_item(self, mail: dict):
        item = QListWidgetItem()
        item.setData(Qt.UserRole, mail)
        item_w = _MailItemWidget(mail)
        item.setSizeHint(QSize(0, 76))
        self._list.addItem(item)
        self._list.setItemWidget(item, item_w)

    def mark_read(self, mail_id: str):
        for i in range(self._list.count()):
            item = self._list.item(i)
            mail = item.data(Qt.UserRole)
            if mail and mail.get("id") == mail_id:
                mail["is_unread"] = False
                item.setData(Qt.UserRole, mail)
                new_w = _MailItemWidget(mail)
                item.setSizeHint(QSize(0, 76))
                self._list.setItemWidget(item, new_w)
                break

    def _on_item_changed(self, current, previous):
        if current is None:
            return
        mail = current.data(Qt.UserRole)
        if mail:
            self.mail_selected.emit(mail)

    def _on_scroll(self, value: int):
        """스크롤 끝 근처에서 다음 페이지 자동 로드."""
        bar = self._list.verticalScrollBar()
        if not self._loading and self._next_page_token:
            if value > bar.maximum() - bar.pageStep() * 2:
                self._load_more()

    def _load_more(self):
        if self._loading or not self._next_page_token:
            return
        self._loading = True
        self._btn_more.setText(tr("読込中..."))
        self.load_more_requested.emit(self._next_page_token)

    def reset_load_btn(self):
        self._btn_more.setText(tr("さらに読み込む"))
        self._loading = False


# ── 메일 미리보기 패널 ────────────────────────────────────────────────────────

class MailPreviewPanel(QWidget):
    """HTML 미리보기 패널. 외부 이미지 차단."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_mail_id = ""
        self._is_dark = True
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 헤더 (발신자 / 제목 / 날짜)
        self._meta_panel = QFrame()
        self._meta_panel.setObjectName("previewMeta")
        meta_layout = QVBoxLayout(self._meta_panel)
        meta_layout.setContentsMargins(20, 16, 20, 12)
        meta_layout.setSpacing(4)

        # 제목
        self._subj_lbl = QLabel()
        self._subj_lbl.setStyleSheet("font-size: 16px; font-weight: bold;")
        self._subj_lbl.setWordWrap(True)

        # 발신자 + 날짜 행
        info_row = QHBoxLayout()
        self._from_lbl = QLabel()
        self._from_lbl.setStyleSheet("font-size: 12px; color: #aaa;")
        self._from_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._date_lbl = QLabel()
        self._date_lbl.setStyleSheet("font-size: 11px; color: #666;")
        self._date_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        info_row.addWidget(self._from_lbl, 1)
        info_row.addWidget(self._date_lbl)

        # 버튼 행
        btn_row = QHBoxLayout()
        self._btn_browser = QPushButton(f"↗  {tr('ブラウザで開く')}")
        self._btn_browser.setObjectName("secondaryActionBtn")
        self._btn_browser.setFixedHeight(28)
        self._btn_browser.setCursor(Qt.PointingHandCursor)
        self._btn_browser.clicked.connect(self._open_in_browser)
        self._btn_browser.hide()
        btn_row.addStretch()
        btn_row.addWidget(self._btn_browser)

        meta_layout.addWidget(self._subj_lbl)
        meta_layout.addLayout(info_row)
        meta_layout.addLayout(btn_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)

        # HTML 뷰어 (항상 흰 배경 — 이메일 HTML은 라이트 배경 기준으로 설계됨)
        self._browser = _SafeTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet("border: none; background: #ffffff;")

        # 빈 상태
        self._empty_lbl = QLabel(tr("📧  メールを選択してください"))
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: #555; font-size: 14px;")

        layout.addWidget(self._meta_panel)
        layout.addWidget(sep)
        layout.addWidget(self._browser, 1)
        layout.addWidget(self._empty_lbl, 1)

        self._meta_panel.hide()
        sep.hide()
        self._browser.hide()
        self._sep = sep

    def set_theme(self, is_dark: bool):
        self._is_dark = is_dark

    def show_loading(self):
        """본문 조회 중 — 스켈레톤 로딩 애니메이션용 뷰 상태 준비."""
        self._meta_panel.hide()
        self._sep.hide()
        self._empty_lbl.hide()

    def show_empty(self):
        self._meta_panel.hide()
        self._sep.hide()
        self._browser.hide()
        self._empty_lbl.show()

    def show_mail(self, mail: dict):
        self._current_mail_id = mail.get("id", "")
        subject = mail.get("subject", tr("(件名なし)"))
        self._subj_lbl.setText(subject)
        self._from_lbl.setText(mail.get("from", ""))
        self._date_lbl.setText(mail.get("date", "")[:25])

        body = mail.get("body_html", "")
        if body:
            # 이메일 기본 CSS — 흰 배경 고정 (이메일 HTML은 라이트 테마 기준으로 설계됨)
            # inline style 을 침해하지 않도록 !important 는 레이아웃 관련에만 사용
            css = (
                "<style>"
                "html, body {"
                "  font-family: Arial, Helvetica, sans-serif;"
                "  font-size: 14px;"
                "  color: #202124;"
                "  background: #ffffff !important;"
                "  margin: 0;"
                "  padding: 10px 18px;"
                "}"
                "a { color: #1a73e8; text-decoration: none; }"
                "a:hover { text-decoration: underline; }"
                "img { max-width: 100% !important; height: auto !important; display: inline-block; }"
                "* { word-wrap: break-word; overflow-wrap: break-word; box-sizing: border-box; }"
                "pre, code {"
                "  white-space: pre-wrap;"
                "  word-wrap: break-word;"
                "  font-family: 'Courier New', 'DejaVu Sans Mono', monospace;"
                "  font-size: 12px;"
                "}"
                "table { border-collapse: collapse; max-width: 100% !important; }"
                "td, th { word-wrap: break-word; max-width: 100%; }"
                "</style>"
            )
            self._browser.setHtml(css + body)
        else:
            self._browser.setHtml(
                f"<p style='color:#888'>{tr('(本文なし)')}</p>"
            )

        self._empty_lbl.hide()
        self._meta_panel.show()
        self._sep.show()
        self._browser.show()
        self._btn_browser.setVisible(bool(self._current_mail_id))

    def _open_in_browser(self):
        if self._current_mail_id:
            safe_id = urllib.parse.quote(self._current_mail_id, safe="")
            url = f"https://mail.google.com/mail/u/0/#inbox/{safe_id}"
            webbrowser.open(url)


# ── GmailWidget ───────────────────────────────────────────────────────────────

class GmailWidget(BaseWidget):
    def __init__(self):
        super().__init__()
        self._labels: list  = []
        self._selected_label_id   = "INBOX"
        self._selected_label_name = tr("受信トレイ")
        self._prev_unread_counts: dict = {}
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll_new_mail)
        # 전체 라벨·메일 자동 갱신 (더 긴 주기)
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._auto_refresh)
        self._build_ui()
        bus.google_auth_changed.connect(self._on_auth_changed)
        QTimer.singleShot(2250, self._check_auth_and_load)

    # ── UI 구성 ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 헤더
        hdr = self._make_header()
        root.addWidget(hdr)

        # 메인 스플리터
        self._splitter = QSplitter(Qt.Horizontal)
        self._splitter.setHandleWidth(1)

        # 알람 활성 라벨 + 표시 라벨 설정 로드
        s            = self.settings
        alarm_labels = set(s.get("gmail_alarm_labels", ["INBOX"]))
        visible_ids  = s.get("gmail_visible_labels", None)   # None = show all

        self._label_panel = LabelListPanel(alarm_labels, visible_ids)
        self._label_panel.setMinimumWidth(180)
        # 최대폭 제한 없음 — 스플리터로 조절, 텍스트 잘림 방지
        self._label_panel.label_selected.connect(self._on_label_selected)
        self._label_panel.alarm_toggled.connect(self._on_alarm_toggled)
        self._label_panel.visible_changed.connect(self._on_visible_labels_changed)

        self._mail_panel = MailListPanel(self._splitter)
        self._mail_panel.setMinimumWidth(260)
        self._mail_panel.setMaximumWidth(360)
        self._mail_panel.mail_selected.connect(self._on_mail_selected)
        self._mail_panel.load_more_requested.connect(self._load_more_mails)
        self._mail_panel.mark_all_read.connect(self._on_mark_all_read)

        self._preview_panel = MailPreviewPanel()

        self._splitter.addWidget(self._label_panel)
        self._splitter.addWidget(self._mail_panel)
        self._splitter.addWidget(self._preview_panel)
        self._splitter.setSizes([220, 290, 490])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setStretchFactor(2, 1)

        root.addWidget(self._splitter, 1)

        # 미인증 오버레이
        self._auth_overlay = self._build_auth_overlay()
        root.addWidget(self._auth_overlay)
        self._auth_overlay.hide()

    def _make_header(self) -> QFrame:
        hdr = QFrame()
        hdr.setObjectName("gmailHdr")
        hrow = QHBoxLayout(hdr)
        hrow.setContentsMargins(16, 10, 16, 10)
        hrow.setSpacing(10)

        title_lbl = QLabel("✉  " + tr("Gmail"))
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")

        self._status_lbl = QLabel()
        self._status_lbl.setStyleSheet("color: #888; font-size: 12px;")

        self._btn_refresh = QPushButton(tr("🔄 更新"))
        self._btn_refresh.setObjectName("secondaryActionBtn")
        self._btn_refresh.setFixedHeight(30)
        self._btn_refresh.setCursor(Qt.PointingHandCursor)
        self._btn_refresh.clicked.connect(self._refresh_labels_and_mail)

        hrow.addWidget(title_lbl)
        hrow.addWidget(self._status_lbl)
        hrow.addStretch()
        hrow.addWidget(self._btn_refresh)
        return hdr

    def _build_auth_overlay(self) -> QFrame:
        overlay = QFrame()
        layout = QVBoxLayout(overlay)
        layout.setAlignment(Qt.AlignCenter)
        lbl = QLabel("🔑  " + tr("Google 認証が必要です"))
        lbl.setStyleSheet("font-size: 15px; color: #aaa;")
        lbl.setAlignment(Qt.AlignCenter)
        sub = QLabel(tr("設定画面から Google アカウントで認証してください。"))
        sub.setStyleSheet("font-size: 12px; color: #666;")
        sub.setAlignment(Qt.AlignCenter)
        layout.addWidget(lbl)
        layout.addWidget(sub)
        return overlay

    # ── 데이터 로드 ──────────────────────────────────────────────────────────

    def _check_auth_and_load(self):
        from app.api.google.auth import is_authenticated
        if is_authenticated():
            self._auth_overlay.hide()
            self._refresh_labels_and_mail()
            self._start_poll_timer()
        else:
            self._auth_overlay.show()

    def _start_poll_timer(self):
        interval_min = self.settings.get("gmail_poll_interval", 5)
        self._poll_timer.start(interval_min * 60 * 1000)
        # 자동 갱신: 기본 10분 (설정 가능)
        auto_min = self.settings.get("gmail_auto_refresh_interval", 10)
        self._auto_refresh_timer.start(auto_min * 60 * 1000)

    def _auto_refresh(self):
        """조용한 자동 갱신 — UI에 '読込中...' 표시 없이 백그라운드 새로 고침."""
        from app.api.google.auth import is_authenticated
        if not is_authenticated():
            return
        self._refresh_labels_and_mail()

    def _refresh_labels_and_mail(self):
        from app.api.google.gmail import FetchLabelsWorker
        self._status_lbl.setText(tr("読込中..."))
        w = FetchLabelsWorker()
        w.data_fetched.connect(self._on_labels_fetched)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _fetch_mail_list(self, label_id: str, page_token: str = ""):
        from app.api.google.gmail import FetchMailListWorker
        if not page_token:
            self._mail_panel.set_loading(True)
            self.set_loading(True, self._mail_panel._list)
            self._status_lbl.setText(tr("読込中..."))
        max_r = self.settings.get("gmail_max_results", 50)
        w = FetchMailListWorker([label_id], max_results=max_r, page_token=page_token)
        if page_token:
            w.data_fetched.connect(lambda mails, token: self._on_more_mails_fetched(mails, token))
        else:
            w.data_fetched.connect(self._on_mails_fetched)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _load_more_mails(self, page_token: str):
        self._fetch_mail_list(self._selected_label_id, page_token)

    def _poll_new_mail(self):
        from app.api.google.auth import is_authenticated
        if not is_authenticated():
            return
            
        # 감시할 라벨: 알람 설정된 라벨 + 수신함(INBOX) + 현재 선택된 라벨
        target_labels = set(self._label_panel.get_alarm_labels())
        target_labels.add("INBOX")
        if self._selected_label_id:
            target_labels.add(self._selected_label_id)

        from app.api.google.gmail import PollNewMailWorker
        w = PollNewMailWorker(list(target_labels), self._prev_unread_counts)
        w.new_mail.connect(self._on_new_mail_detected)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    # ── 이벤트 핸들러 ────────────────────────────────────────────────────────

    def _on_labels_fetched(self, labels: list):
        self._labels = labels
        # unread count 캐시 갱신
        for lbl in labels:
            self._prev_unread_counts[lbl.get("id", "")] = lbl.get("messagesUnread", 0)
        self._label_panel.set_labels(labels)
        self._status_lbl.setText("")
        # 현재 선택된 라벨 메일 로드
        self._fetch_mail_list(self._selected_label_id)

    def _on_mails_fetched(self, mails: list, next_token: str):
        self.set_loading(False, self._mail_panel._list)
        self._mail_panel.set_header(self._selected_label_name)
        self._mail_panel.set_mails(mails, next_token)
        self._preview_panel.show_empty()
        self._status_lbl.setText("")

    def _on_more_mails_fetched(self, mails: list, next_token: str):
        self._mail_panel.append_mails(mails, next_token)
        self._mail_panel.reset_load_btn()

    def _on_label_selected(self, label_id: str, label_name: str):
        self._selected_label_id   = label_id
        self._selected_label_name = label_name
        self._preview_panel.show_empty()
        self._status_lbl.setText(tr("読込中..."))
        self._fetch_mail_list(label_id)

    def _on_mail_selected(self, mail: dict):
        mail_id = mail.get("id", "")
        if not mail_id:
            return

        # 미리보기에서 HTML 이미 있으면 바로 표시
        if "body_html" in mail:
            self._preview_panel.show_mail(mail)
            self._maybe_mark_read(mail)
            return

        # HTML 없으면 전체 본문 조회 — 로딩 표시 먼저
        self._preview_panel.show_loading()
        self.set_loading(True, self._preview_panel._browser)
        from app.api.google.gmail import FetchMailDetailWorker
        w = FetchMailDetailWorker(mail_id)
        w.data_fetched.connect(lambda detail: self._on_mail_detail_fetched(detail))
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_mail_detail_fetched(self, mail: dict):
        self.set_loading(False, self._preview_panel._browser)
        self._preview_panel.show_mail(mail)
        self._maybe_mark_read(mail)

    def _maybe_mark_read(self, mail: dict):
        if not mail.get("is_unread", False):
            return
            
        # 낙관적 업데이트: 즉시 읽음 처리하여 UI(목록, 라벨 트리) 실시간 반영
        mail["is_unread"] = False
        mail_id = mail.get("id", "")
        self._mail_panel.mark_read(mail_id)

        for lid in mail.get("label_ids", []):
            for lbl in self._labels:
                if lbl.get("id") == lid:
                    current = lbl.get("messagesUnread", 0)
                    new_count = max(0, current - 1)
                    lbl["messagesUnread"] = new_count
                    self._prev_unread_counts[lid] = new_count
                    self._label_panel.update_unread(lid, new_count)
                    break

        from app.api.google.gmail import MarkReadWorker
        w = MarkReadWorker(mail_id)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_new_mail_detected(self, label_name_or_id: str, unread_count: int):
        # unread 캐시 및 라벨 UI 실시간 갱신
        matched_id = None
        for lbl in self._labels:
            if lbl.get("name") == label_name_or_id or lbl.get("id") == label_name_or_id:
                matched_id = lbl.get("id", "")
                self._prev_unread_counts[matched_id] = unread_count
                lbl["messagesUnread"] = unread_count
                self._label_panel.update_unread(matched_id, unread_count)
                
                # 새 메일이 온 라벨이 현재 보고 있는 라벨이면 목록도 조용히 갱신
                if matched_id == self._selected_label_id:
                    self._fetch_mail_list(matched_id)
                break
                
        # 전역 알림은 사용자가 알람을 켜둔 라벨인 경우에만 발송
        if matched_id and matched_id in self._label_panel.get_alarm_labels():
            bus.gmail_new_mail.emit(label_name_or_id, unread_count)

    def _on_mark_all_read(self):
        """全既読: 現在のラベルの未読メールをすべて既読にする。"""
        from app.api.google.gmail import MarkAllReadWorker
        self._status_lbl.setText(tr("処理中..."))
        w = MarkAllReadWorker(self._selected_label_id)
        w.success.connect(self._on_mark_all_read_done)
        w.error.connect(self._on_error)
        w.finished.connect(w.deleteLater)
        w.start()
        self.track_worker(w)

    def _on_mark_all_read_done(self, count: int):
        self._status_lbl.setText("")
        # リスト上のアイテムを全部既読に更新してから再取得
        self._refresh_labels_and_mail()

    def _on_alarm_toggled(self, label_id: str, enabled: bool):
        """알람 라벨 설정 저장."""
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["gmail_alarm_labels"] = list(self._label_panel.get_alarm_labels())
        save_settings(s)

    def _on_visible_labels_changed(self, visible_ids: list):
        """표시 라벨 편집 결과를 설정에 저장."""
        from app.core.config import load_settings, save_settings
        s = load_settings()
        s["gmail_visible_labels"] = visible_ids
        save_settings(s)

    def _on_error(self, err: str):
        self._mail_panel.set_loading(False)
        self.set_loading(False, self._mail_panel._list)
        self.set_loading(False, self._preview_panel._browser)
        self._status_lbl.setText(tr("エラー"))
        logger.error(f"Gmail error: {err}")

    def _on_auth_changed(self, authenticated: bool):
        if authenticated:
            self._auth_overlay.hide()
            self._refresh_labels_and_mail()
            self._start_poll_timer()
        else:
            self._auth_overlay.show()
            self._poll_timer.stop()
            self._auto_refresh_timer.stop()
            self._label_panel.set_labels([])
            self._mail_panel.set_mails([], "")
            self._preview_panel.show_empty()
            self._status_lbl.setText("")

    # ── 테마 ────────────────────────────────────────────────────────────────

    def set_theme(self, is_dark: bool):
        self.is_dark = is_dark
        self._preview_panel.set_theme(is_dark)
        self._label_panel.set_theme(is_dark)
        self.apply_theme_custom()

    def apply_theme_custom(self):
        is_dark = self.is_dark
        pc   = UIColors.get_panel_colors(is_dark)
        bg   = pc["bg"]
        bg2  = pc["hover"]
        bg3  = bg
        bd   = pc["border"]
        txt  = pc["text"]
        sub  = pc["text_dim"]
        accent = UIColors.ACCENT_DARK if is_dark else UIColors.ACCENT_LIGHT
        self.setStyleSheet(f"""
            QWidget {{ background: {bg}; color: {txt}; }}
            QLabel {{ background: transparent; }}
            QFrame#gmailHdr {{ background: {bg2}; border-bottom: 1px solid {bd}; }}
            QFrame#gmailLabelHdr {{ background: {bg2}; border-bottom: 1px solid {bd}; }}
            QFrame#mailListHdr {{ background: {bg3}; border-bottom: 1px solid {bd}; }}
            QFrame#previewMeta {{ background: {bg2}; }}
            QListWidget {{ background: {bg3}; color: {txt}; }}
            QListWidget#labelList {{ background: {bg2}; border-right: 1px solid {bd}; }}
            QTreeWidget#labelList {{
                background: {bg2};
                border-right: 1px solid {bd};
                color: {txt};
            }}
            QTreeWidget#labelList::item:selected {{
                background: {'rgba(14, 99, 156, 0.4)' if is_dark else 'rgba(26, 115, 232, 0.15)'};
                border-left: 3px solid {accent};
            }}
            QTreeWidget#labelList::item:hover:!selected {{
                background: {'rgba(255,255,255,0.04)' if is_dark else 'rgba(0,0,0,0.03)'};
            }}
            QListWidget#mailList {{ background: {bg}; border-right: 1px solid {bd}; }}
            QListWidget#mailList::item {{ border-bottom: 1px solid {bd}; padding: 0; }}
            QListWidget#mailList::item:selected {{ background: {'rgba(14, 99, 156, 0.4)' if is_dark else 'rgba(26, 115, 232, 0.15)'}; }}
            QListWidget#mailList::item:hover:!selected {{ background: {'rgba(255,255,255,0.04)' if is_dark else 'rgba(0,0,0,0.03)'}; }}
            QTextBrowser {{ background: #ffffff; color: #202124; border: 1px solid {bd}; border-radius: 4px; margin: 4px; }}
            QLabel#mailSecondary {{ color: {sub}; background: transparent; }}
            QPushButton#secondaryActionBtn {{
                background: {'#3e3e42' if is_dark else '#e0e0e0'};
                color: {txt}; border: none; border-radius: 4px; padding: 0 12px;
            }}
            QPushButton#secondaryActionBtn:hover {{
                background: {'#505055' if is_dark else '#d0d0d0'};
            }}
            QScrollBar:vertical {{
                background: {bg2}; width: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {'#555' if is_dark else '#ccc'}; border-radius: 3px;
            }}
        """)

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

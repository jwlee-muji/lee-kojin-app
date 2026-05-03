"""バグレポート ウィジェット — Phase 5.10 リニューアル + Gmail バックエンド.

권한 분기:
    - 일반 사용자 → 송신 폼만 (_BugFormPage)
    - 관리자 → 전체 화면: 통계 + 필터 + 테이블 + 상세 (_BugAdminPage)

데이터 (Option 2 — Gmail API 파싱):
    - 일반 사용자: SMTP 메일 송신만 (Google 자격증명 0)
    - 관리자: 자기 Gmail 受信トレイ를 OAuth 로 읽고 BUG_REPORT_TO 宛 메일을 파싱
    - 상태 (status/priority/deleted): 관리자 PC 의 로컬 SQLite 오버레이 —
      Gmail message_id 키. Gmail 자체에는 라벨 변경/삭제를 가하지 않음.

디자인 출처: handoff/LEE_PROJECT/varA-misc-detail2.jsx BugSendForm / BugAdminPage
"""
from __future__ import annotations

import logging
import platform
import sys
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QPoint, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMenu, QScrollArea,
    QSplitter, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from app.api.email_api import SendBugReportWorker, BUG_REPORT_TO
from app.api.bug_mail import (
    BugMailReadWorker,
    is_available as mail_available,
    set_status as mail_set_status,
    set_deleted as mail_set_deleted,
)
from app.core.events import bus
from app.core.i18n import tr
from app.ui.common import BaseWidget
from app.ui.components import (
    LeeButton, LeeDetailHeader, LeeDialog, LeeIconTile,
    LeeKPI, LeePill, LeeSegment,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# 토큰
# ──────────────────────────────────────────────────────────────────────
_C_BUG     = "#A8B0BD"   # bug 아이콘 회색
_C_BUG_HOT = "#FF453A"   # 위험
_C_OK      = "#30D158"
_C_WARN    = "#FF9F0A"
_C_INFO    = "#0A84FF"
_C_AI      = "#5856D6"

_MAX_LOG_LINES = 80
_SUMMARY_LIMIT = 100

# 카테고리 (라벨 + key) — 송신 폼 (일반 사용자) 옵션
_CATEGORIES_FORM = [
    ("bug",    "🐛  バグ・エラー"),
    ("ui",     "🖥️  UI 表示の問題"),
    ("data",   "📡  データ取得エラー"),
    ("perf",   "⚡  パフォーマンス問題"),
    ("feat",   "💡  機能要望"),
    ("other",  "❓  その他"),
]
# 관리자 표시용 — 폼 옵션 + access (login_window 의 アクセス申請 메일 자동 분류)
_CATEGORIES = _CATEGORIES_FORM + [
    ("access", "🔑  アクセス申請"),
]
_CATEGORY_MAP = dict(_CATEGORIES)

# 종류 (kind) — 種別 필터 옵션 (관리자 화면)
_KINDS = [
    ("",       "全て"),
    ("bug",    "🐛  バグレポート"),
    ("access", "🔑  アクセス申請"),
]
_KIND_LABEL = {
    "bug":    "🐛 バグ",
    "access": "🔑 アクセス申請",
}

# 상태 옵션
_STATUSES = {
    "open":    {"label": "未対応",   "color": _C_BUG_HOT},
    "wip":     {"label": "対応中",   "color": _C_WARN},
    "fixed":   {"label": "解決",     "color": _C_OK},
    "wontfix": {"label": "対応せず", "color": _C_BUG},
}
_PRIORITIES = {
    "high":   {"label": "高", "color": _C_BUG_HOT},
    "medium": {"label": "中", "color": _C_WARN},
    "low":    {"label": "低", "color": _C_INFO},
}


# ──────────────────────────────────────────────────────────────────────
# 권한 체크
# ──────────────────────────────────────────────────────────────────────
def _is_admin() -> bool:
    try:
        from app.core.config import get_session_email, ADMIN_EMAIL
        return get_session_email().lower() == ADMIN_EMAIL.lower()
    except Exception:
        return False


def _current_email() -> str:
    try:
        from app.core.config import get_session_email
        return get_session_email() or ""
    except Exception:
        return ""


def _read_log_tail(n: int = _MAX_LOG_LINES) -> str:
    try:
        from app.core.config import LOG_FILE
        lines = Path(LOG_FILE).read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def _os_info() -> str:
    try:
        return f"{platform.system()} {platform.release()} ({platform.version()})"
    except Exception:
        return ""


def _screen_info() -> str:
    try:
        screen = QApplication.primaryScreen()
        if screen is None:
            return ""
        size = screen.size()
        dpi = int(screen.logicalDotsPerInch())
        return f"{size.width()}x{size.height()} @ {dpi} DPI"
    except Exception:
        return ""


# ──────────────────────────────────────────────────────────────────────
# A. BugReportWidget — 권한 분기 진입점
# ──────────────────────────────────────────────────────────────────────
class BugReportWidget(BaseWidget):
    """관리자 / 일반 사용자 분기 라우팅."""

    def __init__(self):
        super().__init__()
        self._is_admin_user = _is_admin()
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        if self._is_admin_user:
            self._inner = _BugAdminPage()
        else:
            self._inner = _BugFormPage()
        outer.addWidget(self._inner)

    def apply_theme_custom(self) -> None:
        if hasattr(self._inner, "set_theme"):
            self._inner.set_theme(self.is_dark)


# ──────────────────────────────────────────────────────────────────────
# B. _BugFormPage — 일반 사용자 송신 폼
# ──────────────────────────────────────────────────────────────────────
class _BugFormPage(QWidget):
    """송신 폼만 표시 — 카테고리 / 概要 / 詳細 / 스크린샷 / 자동 정보."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._screenshot_path: Optional[str] = None
        self._worker: Optional[SendBugReportWorker] = None
        self._show_auto_info = False
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setObjectName("bugFormScroll")
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(scroll, 1)

        content = QWidget(); content.setObjectName("bugFormContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(16)

        # 1) DetailHeader
        from app.core.config import __version__
        self._header = LeeDetailHeader(
            title=tr("バグレポート"),
            subtitle=tr("不具合や要望をお知らせください — {0}").format(BUG_REPORT_TO),
            accent=_C_BUG_HOT,
            icon_qicon=QIcon(":/img/bug.svg"),
            badge=f"v{__version__}",
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) 인포 카드
        info_card = QFrame(); info_card.setObjectName("bugInfoCard")
        ic_lay = QHBoxLayout(info_card); ic_lay.setContentsMargins(18, 14, 18, 14); ic_lay.setSpacing(14)
        ic_icon = LeeIconTile(icon=QIcon(":/img/bug.svg"), color=_C_BUG_HOT, size=44, radius=12)
        ic_lay.addWidget(ic_icon, 0, Qt.AlignTop)
        ic_text = QVBoxLayout(); ic_text.setSpacing(2); ic_text.setContentsMargins(0, 0, 0, 0)
        ic_title = QLabel(tr("不便な点やバグをお知らせください"))
        ic_title.setObjectName("bugInfoTitle")
        ic_sub = QLabel(tr("送信される情報: 概要、詳細、ログ (直近 80 行)。送信先: ") + BUG_REPORT_TO)
        ic_sub.setObjectName("bugInfoSub"); ic_sub.setWordWrap(True)
        ic_text.addWidget(ic_title); ic_text.addWidget(ic_sub)
        ic_lay.addLayout(ic_text, 1)
        root.addWidget(info_card)
        self._info_card = info_card

        # 3) 폼 카드
        form_card = QFrame(); form_card.setObjectName("bugFormCard")
        fc_lay = QVBoxLayout(form_card); fc_lay.setContentsMargins(20, 18, 20, 18); fc_lay.setSpacing(14)

        # 카테고리
        fc_lay.addWidget(self._field_label(tr("分類")))
        self._category_seg = LeeSegment(
            [(k, l.split("  ", 1)[-1]) for k, l in _CATEGORIES_FORM],
            value="bug", accent=_C_BUG_HOT,
        )
        fc_lay.addWidget(self._category_seg)

        # 概要
        fc_lay.addWidget(self._field_label(tr("概要"), suffix=tr("(必須, 100 文字以内)")))
        self._summary_edit = QLineEdit()
        self._summary_edit.setObjectName("bugSummaryEdit")
        self._summary_edit.setMaxLength(_SUMMARY_LIMIT)
        self._summary_edit.setPlaceholderText(tr("簡潔に問題を記述してください..."))
        self._summary_edit.setFixedHeight(38)
        self._summary_edit.textChanged.connect(self._update_count)
        fc_lay.addWidget(self._summary_edit)
        self._summary_count_lbl = QLabel(f"0 / {_SUMMARY_LIMIT}")
        self._summary_count_lbl.setObjectName("bugCountLbl")
        self._summary_count_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        fc_lay.addWidget(self._summary_count_lbl)

        # 詳細
        fc_lay.addWidget(self._field_label(tr("詳細・再現手順"), suffix=tr("(任意)")))
        self._detail_edit = QTextEdit()
        self._detail_edit.setObjectName("bugDetailEdit")
        self._detail_edit.setPlaceholderText(
            tr("詳しい状況・再現手順・期待された動作などを記述してください...")
        )
        self._detail_edit.setMinimumHeight(140)
        fc_lay.addWidget(self._detail_edit)

        # 스크린샷 첨부
        fc_lay.addWidget(self._field_label(tr("スクリーンショット"), suffix=tr("(任意)")))
        ss_row = QHBoxLayout(); ss_row.setSpacing(8)
        self._screenshot_lbl = QLabel(tr("(添付なし)"))
        self._screenshot_lbl.setObjectName("bugScreenLbl")
        ss_row.addWidget(self._screenshot_lbl, 1)
        self._btn_attach = LeeButton(tr("📎  ファイル選択"), variant="secondary", size="sm")
        self._btn_attach.clicked.connect(self._on_attach)
        ss_row.addWidget(self._btn_attach)
        self._btn_remove_ss = LeeButton(tr("✕"), variant="ghost", size="sm")
        self._btn_remove_ss.clicked.connect(self._on_remove_screenshot)
        ss_row.addWidget(self._btn_remove_ss)
        fc_lay.addLayout(ss_row)

        # 자동 첨부 정보 (toggle)
        toggle_row = QHBoxLayout(); toggle_row.setSpacing(8)
        toggle_row.addWidget(self._field_label(tr("自動添付情報")))
        toggle_row.addStretch()
        self._btn_toggle_info = LeeButton(tr("▼  表示"), variant="ghost", size="sm")
        self._btn_toggle_info.clicked.connect(self._toggle_info)
        toggle_row.addWidget(self._btn_toggle_info)
        fc_lay.addLayout(toggle_row)

        self._info_box = QFrame(); self._info_box.setObjectName("bugInfoBox")
        ib_lay = QVBoxLayout(self._info_box); ib_lay.setContentsMargins(12, 10, 12, 10); ib_lay.setSpacing(6)

        from app.core.config import __version__
        info_lines = [
            (tr("アプリバージョン"), f"v{__version__}"),
            (tr("OS"), _os_info()),
            (tr("Python"), f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
            (tr("画面"), _screen_info()),
            (tr("ユーザー"), _current_email() or "(未設定)"),
        ]
        for label, value in info_lines:
            r = QHBoxLayout(); r.setContentsMargins(0, 0, 0, 0); r.setSpacing(8)
            l = QLabel(label); l.setObjectName("bugInfoKey"); l.setMinimumWidth(120)
            v = QLabel(value); v.setObjectName("bugInfoVal"); v.setWordWrap(True)
            r.addWidget(l); r.addWidget(v, 1)
            ib_lay.addLayout(r)
        # 로그 미리보기 (최근 5 줄만)
        log_label = QLabel(tr("ログ末尾 (最後 5 行)"))
        log_label.setObjectName("bugInfoKey")
        ib_lay.addWidget(log_label)
        log_preview = QTextEdit()
        log_preview.setObjectName("bugInfoLog")
        log_preview.setReadOnly(True)
        log_preview.setMaximumHeight(110)
        log_tail_lines = (_read_log_tail(_MAX_LOG_LINES) or "").splitlines()
        log_preview.setPlainText("\n".join(log_tail_lines[-5:]))
        ib_lay.addWidget(log_preview)

        fc_lay.addWidget(self._info_box)
        self._info_box.setVisible(False)

        root.addWidget(form_card)
        self._form_card = form_card

        # 4) 송신 버튼
        btn_row = QHBoxLayout(); btn_row.setSpacing(10); btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_clear = LeeButton(tr("クリア"), variant="ghost", size="md")
        self._btn_clear.clicked.connect(self._on_clear)
        btn_row.addWidget(self._btn_clear)
        btn_row.addStretch()
        self._btn_send = LeeButton(tr("送信する"), variant="primary", size="md")
        self._btn_send.clicked.connect(self._on_send)
        btn_row.addWidget(self._btn_send)
        root.addLayout(btn_row)

        # 5) 상태 라벨
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("bugFormStatus")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        root.addWidget(self._status_lbl)

        root.addStretch()
        self._apply_qss()

    def _field_label(self, text: str, *, suffix: str = "") -> QLabel:
        lbl = QLabel(f"{text}  <span style='opacity:0.5'>{suffix}</span>" if suffix else text)
        lbl.setObjectName("bugFieldLabel")
        lbl.setTextFormat(Qt.RichText)
        return lbl

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_app        = "#0A0B0F" if is_dark else "#F5F6F8"
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        self.setStyleSheet(f"""
            QScrollArea#bugFormScroll {{ background: {bg_app}; border: none; }}
            QWidget#bugFormContent {{ background: {bg_app}; }}

            QFrame#bugInfoCard, QFrame#bugFormCard {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QLabel#bugInfoTitle {{
                font-size: 14px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#bugInfoSub {{
                font-size: 11px;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#bugFieldLabel {{
                font-size: 11px; font-weight: 700;
                color: {fg_secondary}; background: transparent;
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }}
            QLineEdit#bugSummaryEdit {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 0 12px;
                font-size: 13px;
            }}
            QLineEdit#bugSummaryEdit:focus {{ border: 1px solid {_C_BUG_HOT}; }}
            QLabel#bugCountLbl {{
                font-size: 10px;
                color: {fg_tertiary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QTextEdit#bugDetailEdit {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border};
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 13px;
                selection-background-color: rgba(255,69,58,0.25);
            }}
            QTextEdit#bugDetailEdit:focus {{ border: 1px solid {_C_BUG_HOT}; }}
            QLabel#bugScreenLbl {{
                font-size: 11px; color: {fg_tertiary};
                background: {bg_surface_2};
                border: 1px dashed {border};
                border-radius: 8px;
                padding: 8px 12px;
            }}
            QFrame#bugInfoBox {{
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 10px;
            }}
            QLabel#bugInfoKey {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
            }}
            QLabel#bugInfoVal {{
                font-size: 11px;
                color: {fg_secondary}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QTextEdit#bugInfoLog {{
                background: {bg_surface};
                color: {fg_secondary};
                border: 1px solid {border_subtle};
                border-radius: 6px;
                padding: 6px 8px;
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 10px;
            }}
            QLabel#bugFormStatus {{
                font-size: 12px; font-weight: 600;
                background: transparent;
            }}
        """)

    # ── Theme ─────────────────────────────────────────────────
    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._header.set_theme(is_dark)
        self._category_seg.set_theme(is_dark)
        self._apply_qss()

    # ── Actions ───────────────────────────────────────────────
    def _update_count(self) -> None:
        n = len(self._summary_edit.text())
        self._summary_count_lbl.setText(f"{n} / {_SUMMARY_LIMIT}")

    def _toggle_info(self) -> None:
        self._show_auto_info = not self._show_auto_info
        self._info_box.setVisible(self._show_auto_info)
        self._btn_toggle_info.setText(tr("▲  非表示") if self._show_auto_info else tr("▼  表示"))

    def _on_attach(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("スクリーンショット選択"), "",
            "Images (*.png *.jpg *.jpeg *.gif *.bmp)",
        )
        if not path: return
        self._screenshot_path = path
        name = Path(path).name
        size_kb = Path(path).stat().st_size / 1024
        self._screenshot_lbl.setText(f"📎  {name}  ({size_kb:.1f} KB)")

    def _on_remove_screenshot(self) -> None:
        self._screenshot_path = None
        self._screenshot_lbl.setText(tr("(添付なし)"))

    def _on_clear(self) -> None:
        self._summary_edit.clear()
        self._detail_edit.clear()
        self._screenshot_path = None
        self._screenshot_lbl.setText(tr("(添付なし)"))
        self._category_seg.set_value("bug")
        self._set_status("")

    def _on_send(self) -> None:
        summary = self._summary_edit.text().strip()
        if not summary:
            self._set_status(tr("⚠️  概要を入力してください"), error=True)
            self._summary_edit.setFocus()
            return

        from app.core.config import __version__
        category_key = self._category_seg.value()
        category_label = _CATEGORY_MAP.get(category_key, category_key)

        subject = f"[LEE v{__version__}] {category_label.split('  ', 1)[-1]}: {summary}"
        body_parts = [
            f"【分類】 {category_label}",
            f"【概要】 {summary}",
            f"【ユーザー】 {_current_email() or '(unknown)'}",
            f"【アプリ】 v{__version__}",
            f"【OS】 {_os_info()}",
            f"【画面】 {_screen_info()}",
            "",
            "【詳細・再現手順】",
            self._detail_edit.toPlainText() or "(未記入)",
            "",
            f"【ログ (直近 {_MAX_LOG_LINES} 行)】",
            _read_log_tail(_MAX_LOG_LINES) or "(取得失敗)",
        ]
        if self._screenshot_path:
            body_parts.insert(7, f"【添付】 {Path(self._screenshot_path).name} (別途添付)")
        body = "\n".join(body_parts)

        # SMTP 메일 송신 — 일반 사용자는 SMTP 만 사용 (Google 자격증명 0)
        # 관리자측은 자기 Gmail 受信トレイ에서 OAuth 로 직접 파싱
        self._btn_send.setEnabled(False)
        self._btn_send.setText(tr("送信中..."))
        self._set_status("")
        self._worker = SendBugReportWorker(subject, body)
        self._worker.success.connect(self._on_send_success)
        self._worker.error.connect(self._on_send_error)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_send_success(self) -> None:
        self._btn_send.setEnabled(True)
        self._btn_send.setText(tr("送信する"))
        self._set_status(tr("✅  レポートを送信しました。ありがとうございます"), error=False)
        bus.toast_requested.emit(tr("✅ バグレポート送信完了"), "success")
        # 폼 클리어
        QTimer.singleShot(800, self._on_clear)

    def _on_send_error(self, err: str) -> None:
        self._btn_send.setEnabled(True)
        self._btn_send.setText(tr("送信する"))
        # 짧은 토스트 + 폼 status (LeeDialog 모달은 burst 회피로 사용 X)
        self._set_status(tr("❌  送信失敗: {0}").format(err), error=True)
        bus.toast_requested.emit(tr("⚠ バグレポート送信失敗"), "warning")

    def _set_status(self, msg: str, *, error: bool = False) -> None:
        self._status_lbl.setText(msg)
        color = _C_BUG_HOT if error else _C_OK
        self._status_lbl.setStyleSheet(
            f"QLabel#bugFormStatus {{ font-size: 12px; font-weight: 600; "
            f"color: {color}; background: transparent; }}"
        )
        if msg and not error:
            QTimer.singleShot(6000, lambda: self._status_lbl.setText(""))


# ──────────────────────────────────────────────────────────────────────
# C. _BugAdminPage — 관리자 화면 (KPI + 필터 + 테이블 + 상세)
# ──────────────────────────────────────────────────────────────────────
class _BugAdminPage(QWidget):
    """관리자: 통계 + 필터 + 테이블 + 상세 패널."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_dark = True
        self._reports: list[dict] = []
        self._selected_id: Optional[str] = None       # Gmail message_id
        self._filter_kind = ""        # "" | "bug" | "access"
        self._filter_status = ""
        self._filter_category = ""
        self._search = ""
        self._read_worker: Optional[BugMailReadWorker] = None
        self._build_ui()
        self._reload()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        scroll = QScrollArea(); scroll.setObjectName("bugAdminScroll")
        scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll, 1)

        content = QWidget(); content.setObjectName("bugAdminContent")
        scroll.setWidget(content)

        root = QVBoxLayout(content)
        root.setContentsMargins(28, 22, 28, 22); root.setSpacing(16)

        # 1) DetailHeader
        from app.core.config import __version__
        self._header = LeeDetailHeader(
            title=tr("バグレポート / アクセス申請 (管理者)"),
            subtitle=tr("受信メールの管理 · v{0}").format(__version__),
            accent=_C_BUG_HOT,
            icon_qicon=QIcon(":/img/bug.svg"),
            badge=tr("ADMIN"),
            show_export=False,
        )
        self._header.back_clicked.connect(lambda: bus.page_requested.emit(0))
        root.addWidget(self._header)

        # 2) KPI 4 개 (전체 / 미처리 / 처리중 / 완료)
        kpi_row = QHBoxLayout(); kpi_row.setSpacing(10)
        self._kpi_total = LeeKPI(tr("全件"),  value="0", color=_C_INFO)
        self._kpi_open  = LeeKPI(tr("未対応"), value="0", color=_C_BUG_HOT)
        self._kpi_wip   = LeeKPI(tr("対応中"), value="0", color=_C_WARN)
        self._kpi_fixed = LeeKPI(tr("解決"),  value="0", color=_C_OK)
        for k in (self._kpi_total, self._kpi_open, self._kpi_wip, self._kpi_fixed):
            kpi_row.addWidget(k, 1)
        root.addLayout(kpi_row)

        # 3) 필터 카드
        filter_card = QFrame(); filter_card.setObjectName("bugFilterCard")
        fc_lay = QHBoxLayout(filter_card); fc_lay.setContentsMargins(16, 12, 16, 12); fc_lay.setSpacing(10)

        fc_lay.addWidget(self._field("種別:"))
        self._kind_combo = QComboBox(); self._kind_combo.setObjectName("bugAdminCombo")
        for k, l in _KINDS:
            self._kind_combo.addItem(tr(l), k)
        self._kind_combo.currentIndexChanged.connect(self._on_kind_changed)
        fc_lay.addWidget(self._kind_combo)

        fc_lay.addWidget(self._field("状態:"))
        self._status_combo = QComboBox(); self._status_combo.setObjectName("bugAdminCombo")
        self._status_combo.addItem(tr("全て"), "")
        for k, meta in _STATUSES.items():
            self._status_combo.addItem(meta["label"], k)
        self._status_combo.currentIndexChanged.connect(self._on_filter_changed)
        fc_lay.addWidget(self._status_combo)

        fc_lay.addWidget(self._field("分類:"))
        self._cat_combo = QComboBox(); self._cat_combo.setObjectName("bugAdminCombo")
        self._cat_combo.addItem(tr("全て"), "")
        for k, l in _CATEGORIES:
            self._cat_combo.addItem(l, k)
        self._cat_combo.currentIndexChanged.connect(self._on_filter_changed)
        fc_lay.addWidget(self._cat_combo)

        self._search_edit = QLineEdit()
        self._search_edit.setObjectName("bugAdminSearch")
        self._search_edit.setPlaceholderText("🔍 " + tr("検索 (概要/詳細)"))
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.setFixedHeight(32)
        self._search_edit.textChanged.connect(self._on_search)
        fc_lay.addWidget(self._search_edit, 1)

        self._btn_refresh = LeeButton(tr("🔄  更新"), variant="ghost", size="sm")
        self._btn_refresh.clicked.connect(self._reload)
        fc_lay.addWidget(self._btn_refresh)

        root.addWidget(filter_card)
        self._filter_card = filter_card

        # 4) 분할 (테이블 + 상세 패널)
        sp = QSplitter(Qt.Horizontal)
        sp.setHandleWidth(1)

        # 테이블
        self._table = QTableWidget()
        self._table.setObjectName("bugAdminTable")
        self._table.setColumnCount(6)
        self._table.setHorizontalHeaderLabels([
            "ID", tr("分類"), tr("概要"), tr("報告者"), tr("状態"), tr("日時"),
        ])
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setShowGrid(False)
        h = self._table.horizontalHeader()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self._table.itemSelectionChanged.connect(self._on_select)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_table_context)

        sp.addWidget(self._table)

        # 상세 패널
        self._detail_pane = self._build_detail_pane()
        sp.addWidget(self._detail_pane)

        sp.setStretchFactor(0, 2)
        sp.setStretchFactor(1, 1)
        sp.setSizes([700, 400])

        root.addWidget(sp, 1)
        self._splitter = sp

        # 5) admin 상태 라벨 (Gmail 연결 표시)
        st_row = QHBoxLayout(); st_row.setSpacing(10)
        self._admin_status_lbl = QLabel("")
        self._admin_status_lbl.setObjectName("bugAdminStatus")
        st_row.addWidget(self._admin_status_lbl)
        st_row.addStretch()
        backend = QLabel(tr("Gmail 接続") if mail_available() else tr("Google 未認証 — 設定で OAuth 認証してください"))
        backend.setObjectName("bugAdminBackend")
        st_row.addWidget(backend)
        root.addLayout(st_row)

        self._apply_qss()

    def _set_admin_status(self, msg: str, *, error: bool = False) -> None:
        self._admin_status_lbl.setText(msg)
        if not msg: return
        color = _C_BUG_HOT if error else _C_OK
        self._admin_status_lbl.setStyleSheet(
            f"color: {color}; background: transparent; "
            f"font-size: 11px; font-weight: 600;"
        )
        if not error:
            QTimer.singleShot(4000, lambda: self._admin_status_lbl.setText(""))

    def _build_detail_pane(self) -> QFrame:
        wrap = QFrame(); wrap.setObjectName("bugDetailPane")
        v = QVBoxLayout(wrap); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

        # 빈 상태
        self._empty_lbl = QLabel(tr("リストから1件選択してください"))
        self._empty_lbl.setObjectName("bugDetailEmpty")
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setMinimumHeight(120)
        v.addWidget(self._empty_lbl)

        # 본 영역 (선택 시)
        self._body_widget = QWidget()
        bv = QVBoxLayout(self._body_widget)
        bv.setContentsMargins(0, 0, 0, 0); bv.setSpacing(8)

        # 헤더 (ID + 카테고리 pill + 상태 pill)
        head = QHBoxLayout(); head.setContentsMargins(0, 0, 0, 0); head.setSpacing(8)
        self._d_id_lbl = QLabel(""); self._d_id_lbl.setObjectName("bugDetailId")
        head.addWidget(self._d_id_lbl)
        head.addStretch()
        self._d_cat_pill = LeePill("", variant="info")
        head.addWidget(self._d_cat_pill)
        self._d_status_pill = LeePill("", variant="warning")
        head.addWidget(self._d_status_pill)
        bv.addLayout(head)

        # 제목
        self._d_summary_lbl = QLabel("")
        self._d_summary_lbl.setObjectName("bugDetailSummary")
        self._d_summary_lbl.setWordWrap(True)
        bv.addWidget(self._d_summary_lbl)

        # 메타
        self._d_meta_lbl = QLabel("")
        self._d_meta_lbl.setObjectName("bugDetailMeta")
        self._d_meta_lbl.setWordWrap(True)
        bv.addWidget(self._d_meta_lbl)

        # 본문
        self._d_detail_view = QTextEdit()
        self._d_detail_view.setObjectName("bugDetailDetailView")
        self._d_detail_view.setReadOnly(True)
        bv.addWidget(self._d_detail_view, 1)

        # 액션 (상태 변경)
        action_row = QHBoxLayout(); action_row.setSpacing(6)
        action_row.addWidget(QLabel(tr("状態 変更:")))
        self._d_status_combo = QComboBox(); self._d_status_combo.setObjectName("bugAdminCombo")
        for k, meta in _STATUSES.items():
            self._d_status_combo.addItem(meta["label"], k)
        action_row.addWidget(self._d_status_combo)
        self._d_btn_apply = LeeButton(tr("適用"), variant="primary", size="sm")
        self._d_btn_apply.clicked.connect(self._on_apply_status)
        action_row.addWidget(self._d_btn_apply)
        action_row.addStretch()
        self._d_btn_delete = LeeButton(tr("削除"), variant="ghost", size="sm")
        self._d_btn_delete.clicked.connect(self._on_delete_selected)
        action_row.addWidget(self._d_btn_delete)
        bv.addLayout(action_row)

        v.addWidget(self._body_widget)
        self._body_widget.setVisible(False)
        return wrap

    def _field(self, text: str) -> QLabel:
        lbl = QLabel(text); lbl.setObjectName("bugAdminFieldLbl")
        return lbl

    def _apply_qss(self) -> None:
        is_dark = self._is_dark
        bg_app        = "#0A0B0F" if is_dark else "#F5F6F8"
        fg_primary    = "#F2F4F7" if is_dark else "#0B1220"
        fg_secondary  = "#A8B0BD" if is_dark else "#4A5567"
        fg_tertiary   = "#6B7280" if is_dark else "#8A93A6"
        bg_surface    = "#14161C" if is_dark else "#FFFFFF"
        bg_surface_2  = "#1B1E26" if is_dark else "#F0F2F5"
        bg_alt        = "#161922" if is_dark else "#F7F8FA"
        border_subtle = "rgba(255,255,255,0.06)" if is_dark else "rgba(11,18,32,0.06)"
        border        = "rgba(255,255,255,0.10)" if is_dark else "rgba(11,18,32,0.10)"
        sel_bg        = "rgba(255,69,58,0.12)" if is_dark else "rgba(255,69,58,0.08)"
        self.setStyleSheet(f"""
            QScrollArea#bugAdminScroll {{ background: {bg_app}; border: none; }}
            QWidget#bugAdminContent {{ background: {bg_app}; }}

            QFrame#bugFilterCard, QFrame#bugDetailPane {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
            }}
            QLabel#bugAdminFieldLbl {{
                font-size: 11px; font-weight: 700;
                color: {fg_tertiary}; background: transparent;
            }}
            QComboBox#bugAdminCombo {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 4px 8px;
                font-size: 11px;
            }}
            QLineEdit#bugAdminSearch {{
                background: {bg_surface_2};
                color: {fg_primary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QLineEdit#bugAdminSearch:focus {{ border: 1px solid {_C_BUG_HOT}; }}

            QSplitter::handle {{ background: transparent; }}

            QTableWidget#bugAdminTable {{
                background: {bg_surface};
                border: 1px solid {border_subtle};
                border-radius: 14px;
                color: {fg_primary};
                gridline-color: {border_subtle};
                alternate-background-color: {bg_alt};
                font-size: 12px;
            }}
            QTableWidget#bugAdminTable::item:selected {{
                background: {sel_bg};
                color: {fg_primary};
            }}
            QHeaderView::section {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: none;
                border-bottom: 1px solid {border_subtle};
                padding: 8px 10px;
                font-size: 11px; font-weight: 700;
            }}

            QLabel#bugDetailEmpty {{
                font-size: 12px; color: {fg_tertiary};
                background: transparent; font-style: italic;
            }}
            QLabel#bugDetailId {{
                font-size: 11px; font-weight: 800;
                color: {_C_BUG_HOT}; background: transparent;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#bugDetailSummary {{
                font-size: 16px; font-weight: 800;
                color: {fg_primary}; background: transparent;
            }}
            QLabel#bugDetailMeta {{
                font-size: 11px; color: {fg_tertiary};
                background: transparent;
            }}
            QTextEdit#bugDetailDetailView {{
                background: {bg_surface_2};
                color: {fg_secondary};
                border: 1px solid {border_subtle};
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 12px;
            }}
            QLabel#bugAdminBackend {{
                font-size: 10px; color: {fg_tertiary};
                background: {bg_surface_2};
                border: 1px solid {border_subtle};
                border-radius: 999px;
                padding: 3px 10px;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
        """)

    # ── Theme ─────────────────────────────────────────────────
    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        self._header.set_theme(is_dark)
        for k in (self._kpi_total, self._kpi_open, self._kpi_wip, self._kpi_fixed):
            k.set_theme(is_dark)
        self._apply_qss()

    # ── Data ──────────────────────────────────────────────────
    def _reload(self) -> None:
        """Gmail OAuth 가능 시 워커 사용, 아니면 빈 결과 + 안내."""
        if not mail_available():
            self._reports = []
            self._render_kpi({"total": 0, "open": 0, "wip": 0, "fixed": 0})
            self._render_table()
            self._set_admin_status(
                tr("⚠ Google 未認証 — 設定画面で OAuth 認証してください"), error=True,
            )
            return
        # 진행 중 워커 보호
        try:
            if self._read_worker and self._read_worker.isRunning():
                return
        except (RuntimeError, AttributeError):
            self._read_worker = None
        self._read_worker = BugMailReadWorker(
            status_f=self._filter_status,
            category_f=self._filter_category,
            search=self._search,
            kind_f=self._filter_kind,
        )
        self._read_worker.finished.connect(self._on_mail_loaded)
        self._read_worker.error.connect(self._on_mail_error)
        self._read_worker.finished.connect(self._read_worker.deleteLater)
        self._read_worker.start()

    def _on_mail_loaded(self, records: list, s: dict) -> None:
        self._reports = records
        self._render_kpi(s)
        self._render_table()
        # 결과 가시화 — 0건이면 명확히 안내, 있으면 짧게 토스트성 표시
        if s.get("total", 0) == 0:
            self._set_admin_status(
                tr("📭 受信トレイに該当レポートなし — 件名「[LEE v…]」+ 宛先「{0}」を検索"
                   ).format(BUG_REPORT_TO),
                error=False,
            )
        else:
            shown = len(records)
            total = s.get("total", 0)
            self._set_admin_status(
                tr("✅ {0} 件取得 (表示 {1} 件)").format(total, shown), error=False,
            )

    def _on_mail_error(self, err: str) -> None:
        self._set_admin_status(tr("⚠ Gmail 取得失敗: {0}").format(err), error=True)

    def _render_kpi(self, s: dict) -> None:
        self._kpi_total.set_value(str(s.get("total", 0)), unit="件")
        self._kpi_open.set_value(str(s.get("open", 0)),  unit="件")
        self._kpi_wip.set_value(str(s.get("wip", 0)),   unit="件")
        self._kpi_fixed.set_value(str(s.get("fixed", 0)), unit="件")

    def _render_table(self) -> None:
        self._table.setRowCount(len(self._reports))
        for row, r in enumerate(self._reports):
            kind = r.get("kind", "bug")
            # 分類セル — access は専用ラベルで上書き
            if kind == "access":
                cat_cell = "🔑 アクセス申請"
            else:
                cat_cell = _CATEGORY_MAP.get(r["category"], r["category"]).split("  ", 1)[-1]
            status_meta = _STATUSES.get(r["status"], _STATUSES["open"])
            short_id = str(r["id"])[-6:] if r["id"] else "?"
            cells = [
                f"#{short_id}",
                cat_cell,
                r["summary"][:80],
                r["reporter_email"][:32],
                status_meta["label"],
                r["created_at"][:16] if r["created_at"] else "",
            ]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if col == 4:   # 상태 컬럼 — 색
                    item.setForeground(self._brush(status_meta["color"]))
                self._table.setItem(row, col, item)

    @staticmethod
    def _brush(color_hex: str):
        from PySide6.QtGui import QBrush, QColor
        return QBrush(QColor(color_hex))

    # ── Actions ───────────────────────────────────────────────
    def _on_kind_changed(self) -> None:
        self._filter_kind = self._kind_combo.currentData() or ""
        # access 専用なら分類フィルタは意味なし — クリア + disable
        if self._filter_kind == "access":
            self._cat_combo.setCurrentIndex(0)
            self._cat_combo.setEnabled(False)
            self._filter_category = ""
        else:
            self._cat_combo.setEnabled(True)
        self._reload()

    def _on_filter_changed(self) -> None:
        self._filter_status = self._status_combo.currentData() or ""
        self._filter_category = self._cat_combo.currentData() or ""
        self._reload()

    def _on_search(self, text: str) -> None:
        self._search = text.strip()
        # debounce 200ms
        if hasattr(self, "_search_timer"):
            self._search_timer.stop()
        else:
            self._search_timer = QTimer(self)
            self._search_timer.setSingleShot(True)
            self._search_timer.setInterval(220)
            self._search_timer.timeout.connect(self._reload)
        self._search_timer.start()

    def _on_select(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            self._selected_id = None
            self._empty_lbl.setVisible(True)
            self._body_widget.setVisible(False)
            return
        idx = rows[0].row()
        if idx >= len(self._reports): return
        r = self._reports[idx]
        self._selected_id = r["id"]
        self._render_detail(r)

    def _render_detail(self, r: dict) -> None:
        self._empty_lbl.setVisible(False)
        self._body_widget.setVisible(True)
        kind = r.get("kind", "bug")
        if kind == "access":
            cat_label = "🔑 アクセス申請"
        else:
            cat_label = _CATEGORY_MAP.get(r["category"], r["category"]).split("  ", 1)[-1]
        status_meta = _STATUSES.get(r["status"], _STATUSES["open"])
        short_id = str(r["id"])[-8:] if r["id"] else "?"

        self._d_id_lbl.setText(f"#{short_id}")
        self._d_cat_pill.setText(cat_label)
        self._d_status_pill.setText(status_meta["label"])
        self._d_summary_lbl.setText(r["summary"])
        # access 종류는 OS/アプリ 정보가 없으므로 메타 라인 단순화
        if kind == "access":
            self._d_meta_lbl.setText(
                f"{tr('申請者')}: {r['reporter_email']}\n"
                f"{tr('受信')}: {r['created_at']}"
            )
            self._d_detail_view.setPlainText(r["detail"] or "(メッセージなし)")
        else:
            self._d_meta_lbl.setText(
                f"{tr('報告者')}: {r['reporter_email']} · "
                f"{tr('アプリ')}: {r['app_version']} · "
                f"{tr('OS')}: {r['os_info']}\n"
                f"{tr('受信')}: {r['created_at']}"
            )
            self._d_detail_view.setPlainText(r["detail"] or "(本文なし)")
        # status combo 위치 동기화
        for i in range(self._d_status_combo.count()):
            if self._d_status_combo.itemData(i) == r["status"]:
                self._d_status_combo.setCurrentIndex(i); break

    def _on_apply_status(self) -> None:
        if not self._selected_id: return
        new_status = self._d_status_combo.currentData()
        # 로컬 상태 오버레이 — 즉시 동기 SQLite 업데이트
        mail_set_status(self._selected_id, new_status)
        bus.toast_requested.emit(tr("✅ ステータスを更新しました"), "success")
        self._reload()

    def _on_delete_selected(self) -> None:
        if not self._selected_id: return
        short = str(self._selected_id)[-8:]
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("レポート #{0} を削除しますか?\n(Gmail 上のメールはそのまま残ります)").format(short),
            ok_text=tr("削除"), destructive=True, parent=self,
        ): return
        mail_set_deleted(self._selected_id)
        self._selected_id = None
        self._empty_lbl.setVisible(True)
        self._body_widget.setVisible(False)
        bus.toast_requested.emit(tr("レポートを非表示にしました"), "info")
        self._reload()

    def _on_table_context(self, pos: QPoint) -> None:
        idx = self._table.indexAt(pos)
        if not idx.isValid(): return
        row = idx.row()
        if row >= len(self._reports): return
        r = self._reports[row]
        menu = QMenu(self)
        for k, meta in _STATUSES.items():
            act = QAction(tr("状態: {0}").format(meta["label"]), menu)
            act.triggered.connect(lambda _=False, sk=k, rid=r["id"]:
                                  (mail_set_status(rid, sk), self._reload()))
            menu.addAction(act)
        menu.addSeparator()
        act_del = QAction(tr("削除"), menu)
        act_del.triggered.connect(lambda _=False, rid=r["id"]: self._delete_via_ctx(rid))
        menu.addAction(act_del)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def _delete_via_ctx(self, rid: str) -> None:
        short = str(rid)[-8:]
        if not LeeDialog.confirm(
            tr("削除の確認"),
            tr("レポート #{0} を削除しますか?\n(Gmail 上のメールはそのまま残ります)").format(short),
            ok_text=tr("削除"), destructive=True, parent=self,
        ): return
        mail_set_deleted(rid)
        self._reload()


# ──────────────────────────────────────────────────────────────────────
# BugReportCard — 대시보드용 (관리자만 표시)
# ──────────────────────────────────────────────────────────────────────
class BugReportCard(QFrame):
    """대시보드 — 미처리 버그/액세스 신청 요약."""
    open_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("bugDashCard")
        self.setCursor(Qt.PointingHandCursor)
        self._is_dark = True
        self._build_ui()
        self._apply_qss()

    def _build_ui(self) -> None:
        v = QVBoxLayout(self); v.setContentsMargins(18, 16, 18, 16); v.setSpacing(10)

        head = QHBoxLayout(); head.setSpacing(10)
        head.addWidget(LeeIconTile(icon=QIcon(":/img/bug.svg"), color=_C_BUG_HOT,
                                    size=40, radius=10))
        title_box = QVBoxLayout(); title_box.setSpacing(2); title_box.setContentsMargins(0, 0, 0, 0)
        t = QLabel(tr("バグ報告 / アクセス申請")); t.setObjectName("bugDashTitle")
        s = QLabel(tr("受信メールの管理")); s.setObjectName("bugDashSub")
        title_box.addWidget(t); title_box.addWidget(s)
        head.addLayout(title_box, 1)
        self._open_pill = LeePill("0", variant="error")
        head.addWidget(self._open_pill, 0, Qt.AlignTop)
        v.addLayout(head)

        # 통계 라인
        self._stats_lbl = QLabel(tr("未対応: 0  ·  対応中: 0  ·  解決: 0"))
        self._stats_lbl.setObjectName("bugDashStats")
        v.addWidget(self._stats_lbl)

        # 최근 1건
        self._recent_lbl = QLabel(tr("最近: —"))
        self._recent_lbl.setObjectName("bugDashRecent")
        self._recent_lbl.setWordWrap(True)
        v.addWidget(self._recent_lbl)

    def refresh(self) -> None:
        """Gmail 에서 최근 레코드 fetch — 비동기 워커 사용."""
        try:
            if not mail_available():
                self._stats_lbl.setText(tr("Google 未認証"))
                self._open_pill.setText("?")
                return
            self._worker = BugMailReadWorker()
            self._worker.finished.connect(self._on_loaded)
            self._worker.error.connect(lambda _e: None)
            self._worker.finished.connect(self._worker.deleteLater)
            self._worker.start()
        except Exception:
            pass

    def _on_loaded(self, records: list, stats: dict) -> None:
        n_open = stats.get("open", 0)
        n_wip  = stats.get("wip", 0)
        n_fix  = stats.get("fixed", 0)
        self._open_pill.setText(str(n_open))
        self._stats_lbl.setText(
            tr("未対応: {0}  ·  対応中: {1}  ·  解決: {2}").format(n_open, n_wip, n_fix)
        )
        if records:
            r = records[0]
            kind_emoji = "🔑" if r.get("kind") == "access" else "🐛"
            summary = (r.get("summary") or "")[:32]
            self._recent_lbl.setText(f"{kind_emoji}  {summary}")
        else:
            self._recent_lbl.setText(tr("最近: —"))

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
            QFrame#bugDashCard {{
                background: {bg}; border: 1px solid {bs};
                border-left: 4px solid {_C_BUG_HOT};
                border-radius: 14px;
            }}
            QFrame#bugDashCard:hover {{ border-color: {_C_BUG_HOT}; }}
            QLabel#bugDashTitle {{
                color: {fg_p}; background: transparent;
                font-size: 14px; font-weight: 800;
            }}
            QLabel#bugDashSub {{
                color: {fg_t}; background: transparent; font-size: 11px;
            }}
            QLabel#bugDashStats {{
                color: {fg_p}; background: transparent;
                font-size: 12px; font-weight: 700;
                font-family: "JetBrains Mono", "Consolas", monospace;
            }}
            QLabel#bugDashRecent {{
                color: {fg_t}; background: transparent; font-size: 11px;
            }}
        """)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.open_requested.emit()
        super().mouseReleaseEvent(event)


__all__ = [
    "BugReportWidget",
    "BugReportCard",
]

"""자동 업데이트 다이얼로그 4종 (LeeDialog 베이스).

흐름:
    UpdateAvailableDialog  → 사용자가 Yes 클릭 시 다운로드 시작
    UpdateProgressDialog   → 다운로드 진행률 표시 (모달, 닫기 불가)
    UpdateReadyDialog      → 다운로드 완료 → 인스톨러 실행
    DownloadErrorDialog    → 실패 시 재시도/취소

Usage (UpdateManager 내부):
    dlg = UpdateAvailableDialog("3.4.2", "3.4.5", parent=parent)
    if dlg.exec() == QDialog.Accepted:
        prog = UpdateProgressDialog(parent=parent)
        prog.show()
        # ... 다운로드 진행 시 prog.update_progress(done_mb, total_mb)
        prog.close()
        UpdateReadyDialog(parent=parent).exec()

    err = DownloadErrorDialog("通信エラー", details=str(exc), parent=parent)
    err.retry.connect(self._retry_download)
    err.exec()
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QProgressBar, QVBoxLayout, QWidget,
)

from app.ui.components.atoms import LeeRingSpinner
from app.ui.components.dialog import LeeDialog


# ──────────────────────────────────────────────────────────────────────────
# 1. UpdateAvailableDialog
# ──────────────────────────────────────────────────────────────────────────
class UpdateAvailableDialog(LeeDialog):
    """신버전 안내 다이얼로그.

    버전 비교 카드 (現在 vs NEW) 를 본문에 추가.
    버튼: 後で (reject) / 今すぐ更新 (primary, accept).

    Returns
    -------
    bool : exec() == QDialog.Accepted
    """

    def __init__(self, current_version: str, new_version: str, *, parent=None):
        super().__init__("アップデートのお知らせ", "update", parent)
        self.set_message(
            "新しいバージョンが利用可能です。\n"
            "ダウンロード後、自動でインストーラーが起動しアプリが再起動します。"
        )
        self.add_body_widget(_VersionCard(current_version, new_version))
        self.add_button("後で", "secondary", role="reject")
        self.add_button("今すぐ更新", "primary", role="accept")
        self.setMinimumWidth(480)


class _VersionCard(QFrame):
    """현재 버전 → 신버전 비교 카드 (UpdateAvailableDialog 내부용)."""

    def __init__(self, current: str, new: str, parent=None):
        super().__init__(parent)
        self.setObjectName("versionCompareCard")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignLeft)

        # 現在 칩
        cur_box = QVBoxLayout()
        cur_box.setSpacing(2)
        cur_label = QLabel("現在")
        cur_label.setObjectName("versionCardLabel")
        cur_value = QLabel(f"v{current}")
        cur_value.setObjectName("versionCardCurrent")
        cur_box.addWidget(cur_label)
        cur_box.addWidget(cur_value)
        layout.addLayout(cur_box)

        # 화살표
        arrow = QLabel("→")
        arrow.setObjectName("versionCardArrow")
        arrow.setAlignment(Qt.AlignCenter)
        layout.addWidget(arrow)

        # NEW 칩
        new_box = QVBoxLayout()
        new_box.setSpacing(2)
        new_label = QLabel("NEW")
        new_label.setObjectName("versionCardNewLabel")
        new_value = QLabel(f"v{new}")
        new_value.setObjectName("versionCardNew")
        new_box.addWidget(new_label)
        new_box.addWidget(new_value)
        layout.addLayout(new_box)

        layout.addStretch()


# ──────────────────────────────────────────────────────────────────────────
# 2. UpdateProgressDialog
# ──────────────────────────────────────────────────────────────────────────
class UpdateProgressDialog(LeeDialog):
    """다운로드 진행률 다이얼로그 (디자인: varA-dialogs.jsx DlgUpdateProgress).

    레이아웃:
        ┌──────────────────────────────────────────────────┐
        │ [Spinner 40px]  v3.5.0 をダウンロード中     47%   │
        │                 12.8 MB / 27.3 MB                │
        │ ──────────────── progress bar ────────────────── │
        │      ダウンロード完了後、自動的にインストーラー…  │
        └──────────────────────────────────────────────────┘
    """

    def __init__(self, *, version: str = "", parent=None):
        super().__init__("アップデートをダウンロード中", "update", parent)

        self._version = version

        # 기본 아이콘/메시지 비표시 (커스텀 레이아웃)
        self._icon.hide()
        self._message.hide()
        self._details.hide()
        self.set_footer_visible(False)

        # 본문 layout 재구성: 상단 row (스피너 + 텍스트 + %) + bar + 안내
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(14)

        self._spinner = LeeRingSpinner(size=40, color="#FF7A45")
        top_row.addWidget(self._spinner, 0, Qt.AlignVCenter)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        ver_text = f"v{version} をダウンロード中" if version else "アップデートをダウンロード中"
        self._title_text = QLabel(ver_text)
        self._title_text.setObjectName("updateProgressTitle")
        self._size_text = QLabel("準備中...")
        self._size_text.setObjectName("updateProgressSize")
        text_box.addWidget(self._title_text)
        text_box.addWidget(self._size_text)
        top_row.addLayout(text_box, 1)

        self._pct_text = QLabel("0%")
        self._pct_text.setObjectName("updateProgressPct")
        self._pct_text.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top_row.addWidget(self._pct_text)

        top_wrap = QFrame()
        top_wrap.setLayout(top_row)
        self.add_body_widget(top_wrap)

        # progress bar
        self._progress = QProgressBar()
        self._progress.setObjectName("updateProgressBar")
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(6)
        self.add_body_widget(self._progress)

        # 안내 텍스트
        self._hint = QLabel(
            "ダウンロード完了後、自動的にインストーラーが起動します。\n"
            "ネットワーク接続を維持してください。"
        )
        self._hint.setObjectName("updateProgressHint")
        self._hint.setAlignment(Qt.AlignCenter)
        self._hint.setWordWrap(True)
        self.add_body_widget(self._hint)

        self.setMinimumWidth(420)

        # 스피너 시작
        QTimer.singleShot(0, self._spinner.start)

        # 로컬 QSS
        self._apply_local_qss()

    def _apply_local_qss(self) -> None:
        self.setStyleSheet(self.styleSheet() + """
            QLabel#updateProgressTitle {
                font-size: 13px; font-weight: 700; color: #F2F4F7;
                background: transparent;
            }
            QLabel#updateProgressSize {
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 11px; color: #6B7280;
                background: transparent;
            }
            QLabel#updateProgressPct {
                font-family: "JetBrains Mono", "Consolas", monospace;
                font-size: 22px; font-weight: 800; color: #FF7A45;
                background: transparent;
            }
            QLabel#updateProgressHint {
                font-size: 10px; color: #6B7280;
                background: transparent;
                padding-top: 6px;
            }
            QProgressBar#updateProgressBar {
                background: rgba(255,255,255,0.05);
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar#updateProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #FF7A45,
                    stop:1 #FF9F0A
                );
                border-radius: 2px;
            }
        """)

    def update_progress(self, downloaded_mb: float, total_mb: float) -> None:
        if total_mb > 0:
            pct = int(downloaded_mb / total_mb * 100)
            self._progress.setRange(0, 100)
            self._progress.setValue(pct)
            self._size_text.setText(f"{downloaded_mb:.1f} MB / {total_mb:.1f} MB")
            self._pct_text.setText(f"{pct}%")
        else:
            self._progress.setRange(0, 0)
            self._size_text.setText(f"{downloaded_mb:.1f} MB ダウンロード済み")
            self._pct_text.setText("--")

    # ── ESC / 닫기 차단 ──────────────────────────────────────────────
    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        # 사용자가 윈도우를 끄려고 해도 무시
        event.ignore()

    def hideEvent(self, event) -> None:
        # 다이얼로그 종료 시 스피너 정지
        try:
            self._spinner.stop()
        except Exception:
            pass
        super().hideEvent(event)


# ──────────────────────────────────────────────────────────────────────────
# 3. UpdateReadyDialog
# ──────────────────────────────────────────────────────────────────────────
class UpdateReadyDialog(LeeDialog):
    """다운로드 완료 안내 다이얼로그.

    성공 아이콘 + "OK · インストールを開始" 버튼 1개.
    OK 클릭 시 호출자가 apply_update() 를 실행하면 됨.
    """

    def __init__(self, *, parent=None):
        super().__init__("アップデート準備完了", "success", parent)
        self.set_message(
            "ダウンロードが完了しました。\n"
            "インストーラーを起動します。アプリは自動的に再起動されます。"
        )
        self.add_button("OK · インストールを開始", "primary", role="accept")
        self.setMinimumWidth(460)


# ──────────────────────────────────────────────────────────────────────────
# 4. DownloadErrorDialog
# ──────────────────────────────────────────────────────────────────────────
class DownloadErrorDialog(LeeDialog):
    """다운로드 실패 다이얼로그.

    에러 메시지 + 모노 트레이스 박스.
    버튼: 閉じる (reject) / 再試行 (primary, accept).

    Signals
    -------
    retry : 再試行 버튼 클릭 시 emit.
    """

    retry = Signal()

    def __init__(self, error_message: str, *, details: str = "", parent=None):
        super().__init__("ダウンロードエラー", "error", parent)
        self.set_message(
            f"アップデートのダウンロードに失敗しました。\n{error_message}",
            details=details,
        )
        self.add_button("閉じる", "secondary", role="reject")
        self.add_button("再試行", "primary", role="accept")
        self.setMinimumWidth(480)

        # accept (= 再試行) 시 retry signal emit
        self.accepted.connect(self.retry.emit)


# ──────────────────────────────────────────────────────────────────────────
# QSS — UpdateAvailableDialog 의 _VersionCard + UpdateProgressDialog 의 진행 영역
# ──────────────────────────────────────────────────────────────────────────
_QSS = """
/* 버전 비교 카드 */
QFrame#versionCompareCard {{
    background: {bg_surface_2};
    border: 1px solid {border_subtle};
    border-radius: 10px;
}}
QLabel#versionCardLabel,
QLabel#versionCardNewLabel {{
    font-size: 10px;
    font-weight: 700;
    color: {fg_tertiary};
    letter-spacing: 1px;
    background: transparent;
}}
QLabel#versionCardNewLabel {{ color: {accent}; }}
QLabel#versionCardCurrent {{
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 16px;
    font-weight: 600;
    color: {fg_secondary};
    background: transparent;
}}
QLabel#versionCardNew {{
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 16px;
    font-weight: 700;
    color: {fg_primary};
    background: transparent;
}}
QLabel#versionCardArrow {{
    font-size: 18px;
    font-weight: 700;
    color: {accent};
    background: transparent;
    padding: 0 8px;
}}

/* 다운로드 프로그레스 바 */
QProgressBar#updateProgressBar {{
    background: {bg_surface_2};
    border: 1px solid {border_subtle};
    border-radius: 4px;
    text-align: center;
}}
QProgressBar#updateProgressBar::chunk {{
    background: {accent};
    border-radius: 3px;
}}
QLabel#updateProgressText {{
    font-family: "JetBrains Mono", "Consolas", monospace;
    font-size: 11px;
    color: {fg_secondary};
    background: transparent;
}}
"""


def qss(tokens: dict) -> str:
    """tokens 를 QSS 템플릿에 .format() 해서 반환.

    ThemeManager 가 components_qss 와 함께 결합 적용한다.
    """
    return _QSS.format(**tokens)

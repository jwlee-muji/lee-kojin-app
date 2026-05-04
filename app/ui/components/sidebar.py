"""LeeSidebar — 메인 윈도우 좌측 240px 사이드바.

레이아웃 (디자인: handoff/LEE_PROJECT/varA-shell.jsx Sidebar):
    ┌────────────────────────┐
    │  電力データ  ▼          │  ← 그룹 헤더 (일본어, 작은 letter-spaced)
    │  [icon] ダッシュボード   │  ← 28px 컬러 아이콘 타일 + 라벨
    │  [icon] スポット市場    │
    │  ...                   │
    │                        │
    │  ────────── (border-top)│
    │  [icon] ログ            │  ← 시스템 영역 (그룹 헤더 X, 평면 버튼)
    │  [icon] バグ報告        │
    │  [icon] マニュアル      │
    │  [icon] 設定           │
    │  ──────────────────────│
    │  Footer slot (옵션)    │  ← 사용자 정보 등
    └────────────────────────┘

active 아이템:
    bg = color-mix(item.color, 12%)
    text = item.color
    아이콘 타일 bg = item.color, fg = white

inactive:
    bg = transparent
    text = fg-secondary
    아이콘 타일 bg = bg-surface-2, fg = fg-secondary

Signals:
    item_clicked(str)
    group_toggled(str, bool)
"""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)


_SIDEBAR_WIDTH = 240


class LeeSidebar(QFrame):
    """카테고리 그룹 + 아이템 (컬러 아이콘 타일) + 시스템 푸터 + 사용자 슬롯."""

    item_clicked  = Signal(str)
    group_toggled = Signal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("leeSidebar")
        self.setFixedWidth(_SIDEBAR_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._groups: dict[str, dict] = {}
        self._items:  dict[str, dict] = {}      # key → {btn, label, color, icon_name, badge_lbl}
        self._system_items: dict[str, dict] = {}
        self._item_icon_provider: Optional[Callable[[str, bool], QIcon]] = None
        self._item_icons: dict[str, str] = {}
        self._active_key: Optional[str] = None
        self._is_dark = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 스크롤 영역 (그룹 + 아이템들)
        scroll = QScrollArea()
        scroll.setObjectName("sidebarScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self._content = QWidget()
        self._content.setObjectName("sidebarContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 12, 12, 4)
        self._content_layout.setSpacing(2)
        scroll.setWidget(self._content)

        # stretch (그룹 / 시스템 사이 공간)
        self._content_layout.addStretch(1)

        # 시스템 영역 (border-top 으로 분리)
        self._system_box = QWidget()
        self._system_box.setObjectName("sidebarSystemBox")
        self._system_layout = QVBoxLayout(self._system_box)
        self._system_layout.setContentsMargins(0, 8, 0, 8)
        self._system_layout.setSpacing(2)
        self._content_layout.addWidget(self._system_box)

        root.addWidget(scroll, 1)

        # 사용자 정보용 footer slot (외부 주입)
        self._footer_slot = QWidget()
        self._footer_slot.setObjectName("sidebarFooterSlot")
        self._footer_slot_layout = QVBoxLayout(self._footer_slot)
        self._footer_slot_layout.setContentsMargins(0, 0, 0, 0)
        self._footer_slot_layout.setSpacing(0)
        root.addWidget(self._footer_slot)

    # ──────────────────────────────────────────────────────────
    # 외부 API — 그룹 / 아이템
    # ──────────────────────────────────────────────────────────
    def set_icon_provider(self, provider: Callable[[str, bool], QIcon]) -> None:
        self._item_icon_provider = provider

    def add_group(self, key: str, label: str) -> None:
        if key in self._groups:
            raise KeyError(f"group already exists: {key}")

        # 그룹 헤더 (▼ collapse 토글)
        header_btn = QPushButton(f"▾  {label}")
        header_btn.setObjectName("sidebarGroupHeader")
        header_btn.setCursor(Qt.PointingHandCursor)
        header_btn.setFlat(True)
        header_btn.setFixedHeight(28)
        header_btn.clicked.connect(lambda _checked=False, k=key: self.toggle_group(k))

        container = QWidget()
        container.setObjectName("sidebarGroupContainer")
        c_layout = QVBoxLayout(container)
        c_layout.setContentsMargins(0, 0, 0, 8)
        c_layout.setSpacing(2)

        # stretch + system 직전에 삽입
        # 현재 레이아웃: [...groups...] [stretch] [system_box]
        # 마지막 stretch + system_box 앞에 삽입
        idx = self._content_layout.count() - 2  # 마지막 두 개 제외
        if idx < 0:
            idx = 0
        self._content_layout.insertWidget(idx, header_btn)
        self._content_layout.insertWidget(idx + 1, container)

        self._groups[key] = {
            "label":            label,
            "header_btn":       header_btn,
            "container":        container,
            "container_layout": c_layout,
            "items":            [],
            "collapsed":        False,
            "filtered_visible": True,
        }

    def add_item(
        self,
        group_key: str,
        item_key: str,
        label: str,
        *,
        icon_name: str = "",
        color: str = "#A8B0BD",
    ) -> QPushButton:
        if group_key not in self._groups:
            raise KeyError(f"group not found: {group_key}")
        if item_key in self._items:
            raise KeyError(f"item already exists: {item_key}")

        btn = self._build_item_button(item_key, label, icon_name, color)

        self._groups[group_key]["container_layout"].addWidget(btn)
        self._groups[group_key]["items"].append((item_key, btn))
        self._items[item_key]["group_key"] = group_key
        return btn

    def add_system_item(
        self,
        item_key: str,
        label: str,
        *,
        icon_name: str = "",
        color: str = "#A8B0BD",
    ) -> QPushButton:
        """시스템 영역 (그룹 헤더 없이 하단 평면 버튼) 에 아이템 추가.
        Top 탭 필터에 영향받지 않음 (항상 표시).
        """
        if item_key in self._items:
            raise KeyError(f"item already exists: {item_key}")

        btn = self._build_item_button(item_key, label, icon_name, color)
        self._system_layout.addWidget(btn)
        self._system_items[item_key] = self._items[item_key]
        return btn

    def update_item_label(self, item_key: str, label: str) -> None:
        info = self._items.get(item_key)
        if info is None:
            return
        info["label_widget"].setText(label)

    def update_item_badge(self, item_key: str, count: int) -> None:
        """아이템 우측 redmadge 카운트 (0 = 숨김)."""
        info = self._items.get(item_key)
        if info is None:
            return
        badge = info["badge_lbl"]
        if count > 0:
            badge.setText(str(count))
            badge.setVisible(True)
        else:
            badge.setVisible(False)

    # ──────────────────────────────────────────────────────────
    # 활성 표시
    # ──────────────────────────────────────────────────────────
    def set_active(self, item_key: Optional[str]) -> None:
        for k, info in self._items.items():
            self._set_item_active(k, k == item_key)
        self._active_key = item_key

    def active_key(self) -> Optional[str]:
        return self._active_key

    def visible_item_keys(self) -> list[str]:
        keys = []
        # 일반 그룹 아이템 (필터/접힘 반영)
        for g in self._groups.values():
            if not g["filtered_visible"] or g["collapsed"]:
                continue
            for k, b in g["items"]:
                if b.isVisible():
                    keys.append(k)
        # 시스템 아이템 (항상 표시)
        for k in self._system_items.keys():
            keys.append(k)
        return keys

    # ──────────────────────────────────────────────────────────
    # 그룹 접기 / 펴기
    # ──────────────────────────────────────────────────────────
    def toggle_group(self, group_key: str) -> None:
        g = self._groups.get(group_key)
        if g is None:
            return
        g["collapsed"] = not g["collapsed"]
        self._refresh_group_visibility(group_key)
        self.group_toggled.emit(group_key, g["collapsed"])

    def set_group_collapsed(self, group_key: str, collapsed: bool, *, emit: bool = False) -> None:
        g = self._groups.get(group_key)
        if g is None or g["collapsed"] == collapsed:
            return
        g["collapsed"] = collapsed
        self._refresh_group_visibility(group_key)
        if emit:
            self.group_toggled.emit(group_key, collapsed)

    def collapsed_states(self) -> dict[str, bool]:
        return {k: g["collapsed"] for k, g in self._groups.items()}

    def restore_collapsed_states(self, states: dict[str, bool]) -> None:
        for key, collapsed in states.items():
            self.set_group_collapsed(key, bool(collapsed), emit=False)

    # ──────────────────────────────────────────────────────────
    # Top 탭 필터 — 디자인은 단일 활성 (배타적). active_tab 만 표시.
    # ──────────────────────────────────────────────────────────
    def set_active_tab(self, tab_key: Optional[str]) -> None:
        """tab_key 와 일치하는 그룹만 표시. None / 빈 문자열이면 모두 표시 (필터 해제).
        시스템 아이템은 항상 표시.
        """
        for key in self._groups:
            visible = (not tab_key) or (key == tab_key)
            self._groups[key]["filtered_visible"] = visible
            self._refresh_group_visibility(key)

    # 하위 호환 (기존 코드가 set 으로 호출)
    def filter_by_tabs(self, active_tabs) -> None:
        if not active_tabs:
            self.set_active_tab(None)
        elif isinstance(active_tabs, str):
            self.set_active_tab(active_tabs)
        else:
            tab_set = set(active_tabs)
            self.set_active_tab(next(iter(tab_set), None))

    # ──────────────────────────────────────────────────────────
    # 푸터 슬롯
    # ──────────────────────────────────────────────────────────
    def set_footer(self, widget: QWidget) -> None:
        while self._footer_slot_layout.count():
            item = self._footer_slot_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        self._footer_slot_layout.addWidget(widget)

    # ──────────────────────────────────────────────────────────
    # 테마
    # ──────────────────────────────────────────────────────────
    def set_theme(self, is_dark: bool) -> None:
        self._is_dark = is_dark
        if self._item_icon_provider is None:
            return
        for k, info in self._items.items():
            icon_name = self._item_icons.get(k)
            if not icon_name:
                continue
            # active / inactive 모두 테마 변경 시 픽셀 다시 tinting
            # (이전엔 inactive 만 갱신하여 라이트모드 전환 후 active 아이콘이
            # 다크 그대로 유지되던 버그)
            is_active = bool(info.get("icon_active"))
            info["icon_label"].setPixmap(
                self._tinted_pix(icon_name, is_dark, info["color"], active=is_active)
            )

    # ──────────────────────────────────────────────────────────
    # 내부 — 아이템 빌더
    # ──────────────────────────────────────────────────────────
    def _build_item_button(
        self,
        item_key: str,
        label: str,
        icon_name: str,
        color: str,
    ) -> QPushButton:
        btn = QPushButton()
        btn.setObjectName("sidebarItem")
        btn.setProperty("itemColor", color)
        btn.setProperty("itemActive", False)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(40)
        btn.clicked.connect(lambda _checked=False, k=item_key: self._on_item_click(k))

        # 내부 레이아웃: 아이콘 타일 (28×28) + 라벨 + (배지)
        inner = QHBoxLayout(btn)
        inner.setContentsMargins(8, 6, 12, 6)
        inner.setSpacing(10)

        icon_lbl = QLabel()
        icon_lbl.setObjectName("sidebarItemIcon")
        icon_lbl.setProperty("itemColor", color)
        icon_lbl.setProperty("itemActive", False)
        icon_lbl.setFixedSize(28, 28)
        icon_lbl.setAlignment(Qt.AlignCenter)
        if icon_name and self._item_icon_provider is not None:
            icon_lbl.setPixmap(self._tinted_pix(icon_name, self._is_dark, color, active=False))
        inner.addWidget(icon_lbl)

        label_lbl = QLabel(label)
        label_lbl.setObjectName("sidebarItemLabel")
        inner.addWidget(label_lbl, 1)

        # redmadge 배지 (count, default 숨김)
        badge_lbl = QLabel("")
        badge_lbl.setObjectName("sidebarItemBadge")
        badge_lbl.setAlignment(Qt.AlignCenter)
        inner.addWidget(badge_lbl)
        badge_lbl.setVisible(False)   # setVisible 은 layout 추가 후

        if icon_name:
            self._item_icons[item_key] = icon_name

        self._items[item_key] = {
            "btn":          btn,
            "label_widget": label_lbl,
            "icon_label":   icon_lbl,
            "badge_lbl":    badge_lbl,
            "color":        color,
            "icon_active":  False,
        }
        return btn

    def _set_item_active(self, item_key: str, active: bool) -> None:
        info = self._items.get(item_key)
        if info is None:
            return
        # 이미 같은 상태면 skip
        if info.get("icon_active") == active:
            # 그래도 button property 는 갱신
            info["btn"].setProperty("itemActive", active)
            info["btn"].style().unpolish(info["btn"]); info["btn"].style().polish(info["btn"])
            return

        info["btn"].setProperty("itemActive", active)
        info["btn"].style().unpolish(info["btn"]); info["btn"].style().polish(info["btn"])

        info["icon_label"].setProperty("itemActive", active)
        info["icon_label"].style().unpolish(info["icon_label"]); info["icon_label"].style().polish(info["icon_label"])
        info["icon_active"] = active

        # 아이콘 픽스맵 갱신 (active 일 때 white tint, inactive 일 때 secondary)
        icon_name = self._item_icons.get(item_key)
        if icon_name and self._item_icon_provider is not None:
            info["icon_label"].setPixmap(
                self._tinted_pix(icon_name, self._is_dark, info["color"], active=active)
            )

    def _tinted_pix(self, icon_name: str, is_dark: bool, color: str, *, active: bool):
        """아이템 아이콘 픽스맵 — active 일 때 흰색 tint, 평소엔 테마별 tint.

        18×18 사이즈 명시적 보장 (DPI 가변에 따른 정렬 변형 방지).
        """
        if self._item_icon_provider is None:
            return None
        from PySide6.QtGui import QPixmap, QPainter, QColor
        ICON_SIZE = 18
        if active:
            # active 시 흰색 — provider 에 light theme 호출 후 white tint 재적용
            qicon = self._item_icon_provider(icon_name, False)
            base = qicon.pixmap(ICON_SIZE, ICON_SIZE)
            if base.isNull():
                return base
            # 정확히 18×18 캔버스에 dest 명시 후 그림 (사이즈/정렬 일관성)
            out = QPixmap(ICON_SIZE, ICON_SIZE)
            out.fill(Qt.transparent)
            p = QPainter(out)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(0, 0, ICON_SIZE, ICON_SIZE, base)
            p.setCompositionMode(QPainter.CompositionMode_SourceIn)
            p.fillRect(out.rect(), QColor("#ffffff"))
            p.end()
            return out
        else:
            # inactive — provider 의 테마별 tint 그대로, 18×18 캔버스에 정렬 보장
            qicon = self._item_icon_provider(icon_name, is_dark)
            base = qicon.pixmap(ICON_SIZE, ICON_SIZE)
            if base.isNull():
                return base
            out = QPixmap(ICON_SIZE, ICON_SIZE)
            out.fill(Qt.transparent)
            p = QPainter(out)
            p.setRenderHint(QPainter.SmoothPixmapTransform)
            p.drawPixmap(0, 0, ICON_SIZE, ICON_SIZE, base)
            p.end()
            return out

    def _on_item_click(self, item_key: str) -> None:
        self.set_active(item_key)
        self.item_clicked.emit(item_key)

    def _refresh_group_visibility(self, group_key: str) -> None:
        g = self._groups[group_key]
        g["header_btn"].setVisible(g["filtered_visible"])
        g["container"].setVisible(g["filtered_visible"] and not g["collapsed"])
        indicator = "▸" if g["collapsed"] else "▾"
        g["header_btn"].setText(f"{indicator}  {g['label']}")


# ──────────────────────────────────────────────────────────────
# QSS
# ──────────────────────────────────────────────────────────────
_QSS = """
QFrame#leeSidebar {{
    background: {bg_surface};
    border-right: 1px solid {border_subtle};
}}
QScrollArea#sidebarScroll {{ background: transparent; border: none; }}
QWidget#sidebarContent,
QWidget#sidebarGroupContainer,
QWidget#sidebarFooterSlot {{
    background: transparent;
}}
QWidget#sidebarSystemBox {{
    background: transparent;
    border-top: 1px solid {border_subtle};
}}

/* ── 그룹 헤더 ── */
QPushButton#sidebarGroupHeader {{
    background: transparent;
    color: {fg_tertiary};
    border: none;
    text-align: left;
    padding: 6px 8px 4px 12px;
    font-size: 10px;
    font-weight: 800;
    letter-spacing: 0.06em;
}}
QPushButton#sidebarGroupHeader:hover {{
    color: {fg_secondary};
}}

/* ── 아이템 버튼 ── */
QPushButton#sidebarItem {{
    background: transparent;
    border: none;
    border-radius: 12px;
    text-align: left;
    padding: 0;
}}
QPushButton#sidebarItem:hover[itemActive="false"] {{
    background: {bg_surface_2};
}}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FF7A45"] {{ background: rgba(255,122,69,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#5B8DEF"] {{ background: rgba(91,141,239,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#F25C7A"] {{ background: rgba(242,92,122,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#F4B740"] {{ background: rgba(244,183,64,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#2EC4B6"] {{ background: rgba(46,196,182,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#A78BFA"] {{ background: rgba(167,139,250,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#34C759"] {{ background: rgba(52,199,89,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#EA4335"] {{ background: rgba(234,67,53,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#5856D6"] {{ background: rgba(88,86,214,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FFCC00"] {{ background: rgba(255,204,0,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FF9500"] {{ background: rgba(255,149,0,0.12); }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#A8B0BD"] {{ background: {bg_surface_2}; }}

/* ── 아이템 라벨 ── */
QLabel#sidebarItemLabel {{
    background: transparent;
    color: {fg_secondary};
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FF7A45"] QLabel#sidebarItemLabel {{ color: #FF7A45; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#5B8DEF"] QLabel#sidebarItemLabel {{ color: #5B8DEF; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#F25C7A"] QLabel#sidebarItemLabel {{ color: #F25C7A; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#F4B740"] QLabel#sidebarItemLabel {{ color: #F4B740; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#2EC4B6"] QLabel#sidebarItemLabel {{ color: #2EC4B6; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#A78BFA"] QLabel#sidebarItemLabel {{ color: #A78BFA; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#34C759"] QLabel#sidebarItemLabel {{ color: #34C759; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#EA4335"] QLabel#sidebarItemLabel {{ color: #EA4335; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#5856D6"] QLabel#sidebarItemLabel {{ color: #5856D6; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FFCC00"] QLabel#sidebarItemLabel {{ color: #FFCC00; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#FF9500"] QLabel#sidebarItemLabel {{ color: #FF9500; }}
QPushButton#sidebarItem[itemActive="true"][itemColor="#A8B0BD"] QLabel#sidebarItemLabel {{ color: {fg_primary}; }}
QPushButton#sidebarItem:hover QLabel#sidebarItemLabel {{ color: {fg_primary}; }}

/* ── 아이콘 타일 ── */
QLabel#sidebarItemIcon {{
    background: {bg_surface_2};
    border-radius: 8px;
}}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#FF7A45"] {{ background: #FF7A45; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#5B8DEF"] {{ background: #5B8DEF; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#F25C7A"] {{ background: #F25C7A; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#F4B740"] {{ background: #F4B740; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#2EC4B6"] {{ background: #2EC4B6; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#A78BFA"] {{ background: #A78BFA; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#34C759"] {{ background: #34C759; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#EA4335"] {{ background: #EA4335; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#5856D6"] {{ background: #5856D6; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#FFCC00"] {{ background: #FFCC00; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#FF9500"] {{ background: #FF9500; }}
QLabel#sidebarItemIcon[itemActive="true"][itemColor="#A8B0BD"] {{ background: {fg_secondary}; }}

/* ── redmadge 배지 ── */
QLabel#sidebarItemBadge {{
    background: {c_bad};
    color: #ffffff;
    border-radius: 8px;
    font-size: 9px;
    font-weight: 700;
    padding: 1px 6px;
    min-width: 12px;
    max-height: 16px;
}}

QWidget#sidebarFooterSlot {{
    border-top: 1px solid {border_subtle};
}}
"""


def qss(tokens: dict) -> str:
    return _QSS.format(**tokens)

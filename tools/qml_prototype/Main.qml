// LEE QtQuick UI 프로토타입 — 옵션 B 검증용 단일 화면
//
// 핵심 기법:
//   - 모든 색상은 root 의 property color + Behavior on color { ColorAnimation }
//     으로 정의 → 테마 토글 시 GPU scenegraph 가 매 프레임 보간 (60fps 유지)
//   - 호버 / 스케일 애니메이션도 Behavior 로 GPU 가속
//   - FPS 카운터 = continuous Timer 가 측정. setStyleSheet cascade 같은 main
//     thread freeze 가 발생하면 즉시 0fps 로 떨어져 보임

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window

ApplicationWindow {
    id: root
    width: 980
    height: 640
    visible: true
    title: "LEE QML Prototype"

    // ── 테마 토큰 (모두 ColorAnimation 으로 자동 보간) ─────────────
    property bool isDark: themeBridge.theme === "dark"

    property color bgApp:        isDark ? "#0A0B0F" : "#F5F6F8"
    property color bgSurface:    isDark ? "#14161C" : "#FFFFFF"
    property color bgSurface2:   isDark ? "#1B1E26" : "#F0F2F5"
    property color bgSurface3:   isDark ? "#232730" : "#E6E9EE"
    property color fgPrimary:    isDark ? "#F2F4F7" : "#0B1220"
    property color fgSecondary:  isDark ? "#A8B0BD" : "#4A5567"
    property color fgTertiary:   isDark ? "#6B7280" : "#8A93A6"
    property color borderSubtle: isDark ? Qt.rgba(1,1,1,0.06) : Qt.rgba(0.04,0.07,0.13,0.06)
    property color accent:       "#5B8DEF"

    // 토글 시 250ms 보간 — 모든 자식 요소가 동시에 색 보간
    Behavior on bgApp        { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface    { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface2   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface3   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgPrimary    { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgSecondary  { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgTertiary   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on borderSubtle { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }

    color: bgApp

    // ── 테마 토글 시간 측정 (마지막 N 회 평균) ─────────────────────
    property real lastToggleMs: 0
    property real avgToggleMs: 0
    property int toggleCount: 0

    Connections {
        target: themeBridge
        function onToggleFinished(ms) {
            root.lastToggleMs = ms
            root.toggleCount += 1
            root.avgToggleMs = (root.avgToggleMs * (root.toggleCount - 1) + ms) / root.toggleCount
        }
    }

    // 250ms 후 markToggleEnd 호출 (Behavior 가 끝난 시점)
    Timer {
        id: toggleEndTimer
        interval: 260
        onTriggered: themeBridge.markToggleEnd()
    }

    Connections {
        target: themeBridge
        function onToggleStarted() { toggleEndTimer.restart() }
    }

    // ── FPS 카운터 (16ms tick, 1 초마다 평균 갱신) ─────────────────
    property real fps: 60.0
    property int _fpsTickCount: 0
    property real _fpsLastUpdate: 0

    Timer {
        interval: 16
        running: true
        repeat: true
        onTriggered: {
            root._fpsTickCount += 1
            const now = Date.now()
            if (root._fpsLastUpdate === 0) root._fpsLastUpdate = now
            if (now - root._fpsLastUpdate >= 1000) {
                root.fps = root._fpsTickCount * 1000.0 / (now - root._fpsLastUpdate)
                root._fpsTickCount = 0
                root._fpsLastUpdate = now
            }
        }
    }

    // ── 헤더 ──────────────────────────────────────────────────────
    Rectangle {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 60
        color: bgSurface

        Rectangle {  // 하단 디바이더
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 1
            color: borderSubtle
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24
            anchors.rightMargin: 18
            spacing: 14

            Rectangle {
                width: 32; height: 32; radius: 9
                color: accent
                Text {
                    anchors.centerIn: parent
                    text: "L"; color: "white"
                    font.pixelSize: 16; font.bold: true
                }
            }
            Text {
                text: "LEE QtQuick Prototype"
                color: fgPrimary
                font.pixelSize: 16; font.bold: true
            }
            Item { Layout.fillWidth: true }

            // 테마 토글 버튼
            Rectangle {
                id: themeBtn
                width: 36; height: 36; radius: 10
                color: themeMouse.containsMouse ? bgSurface3 : bgSurface2
                border.color: borderSubtle; border.width: 1
                Behavior on color  { ColorAnimation { duration: 120 } }
                Behavior on scale  { NumberAnimation { duration: 100 } }
                scale: themeMouse.pressed ? 0.95 : 1.0
                Text {
                    anchors.centerIn: parent
                    text: isDark ? "☀" : "☾"
                    color: fgPrimary
                    font.pixelSize: 16
                }
                MouseArea {
                    id: themeMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: themeBridge.toggle()
                }
            }
        }
    }

    // ── 메인 콘텐츠 ──────────────────────────────────────────────
    ColumnLayout {
        anchors {
            top: header.bottom; left: parent.left; right: parent.right; bottom: parent.bottom
            topMargin: 24; leftMargin: 24; rightMargin: 24; bottomMargin: 24
        }
        spacing: 18

        // KPI 카드 행
        RowLayout {
            Layout.fillWidth: true
            spacing: 16

            Repeater {
                model: [
                    { icon: "📊", title: "JEPX Spot",       value: "9.42",  unit: "¥/kWh", color: "#5B8DEF" },
                    { icon: "⚡", title: "予備率",          value: "18.5",  unit: "%",     color: "#34C759" },
                    { icon: "💧", title: "インバランス",     value: "12.3",  unit: "¥/kWh", color: "#A78BFA" }
                ]
                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 130
                    radius: 14
                    color: bgSurface
                    border.color: borderSubtle; border.width: 1
                    scale: cardMouse.containsMouse ? 1.015 : 1.0
                    Behavior on scale { NumberAnimation { duration: 140; easing.type: Easing.OutQuad } }
                    Behavior on color { ColorAnimation { duration: 250 } }

                    HoverHandler { id: cardMouse }

                    Column {
                        anchors.fill: parent
                        anchors.margins: 16
                        spacing: 10

                        Row {
                            spacing: 12
                            Rectangle {
                                width: 36; height: 36; radius: 10
                                color: Qt.rgba(modelData.color.r, modelData.color.g, modelData.color.b, 0.18)
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData.icon
                                    font.pixelSize: 18
                                }
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData.title
                                color: fgSecondary
                                font.pixelSize: 12; font.weight: Font.DemiBold
                            }
                        }
                        Row {
                            spacing: 6
                            anchors.left: parent.left
                            anchors.leftMargin: 4
                            Text {
                                text: modelData.value
                                color: modelData.color
                                font.pixelSize: 32; font.bold: true
                                font.family: "Consolas"
                            }
                            Text {
                                anchors.bottom: parent.bottom
                                anchors.bottomMargin: 6
                                text: modelData.unit
                                color: fgTertiary
                                font.pixelSize: 12
                            }
                        }
                        Text {
                            text: "Last: 14:25  ·  +0.12%"
                            color: fgTertiary
                            font.pixelSize: 10
                        }
                    }
                }
            }
        }

        // 알림 리스트
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: 14
            color: bgSurface
            border.color: borderSubtle; border.width: 1
            Behavior on color { ColorAnimation { duration: 250 } }

            ListView {
                anchors.fill: parent
                anchors.margins: 1
                clip: true
                model: 8
                delegate: Rectangle {
                    width: ListView.view.width
                    height: 52
                    color: itemMouse.containsMouse ? bgSurface2 : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    HoverHandler { id: itemMouse }

                    Rectangle { // 하단 디바이더
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom; leftMargin: 16; rightMargin: 16 }
                        height: 1
                        color: borderSubtle
                        visible: index < 7
                    }

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        anchors.left: parent.left
                        anchors.leftMargin: 16
                        spacing: 14

                        Text {
                            text: ["⚡","📊","💧","☁","📨","📅","🔔","📊"][index]
                            font.pixelSize: 18
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text {
                                text: ["Power Reserve updated",
                                       "Spot price refreshed",
                                       "Imbalance latest tick",
                                       "Weather forecast pulled",
                                       "Gmail: 3 new",
                                       "Calendar event in 30m",
                                       "System notification",
                                       "JEPX history sync"][index]
                                color: fgPrimary
                                font.pixelSize: 13; font.weight: Font.DemiBold
                            }
                            Text {
                                text: "14:" + String(20 + index).padStart(2, "0") + "  ·  module"
                                color: fgTertiary
                                font.pixelSize: 11
                                font.family: "Consolas"
                            }
                        }
                    }
                }
            }
        }
    }

    // ── 좌하단 회전 애니메이션 (freeze 시각 검증) ──────────────────
    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 12
        width: 28; height: 28; radius: 6
        color: accent
        opacity: 0.9
        RotationAnimation on rotation {
            from: 0; to: 360
            duration: 1500
            loops: Animation.Infinite
        }
    }

    // ── 우하단 메트릭 ──────────────────────────────────────────────
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        width: metricText.width + 24
        height: 36
        radius: 10
        color: bgSurface2
        border.color: borderSubtle; border.width: 1
        Behavior on color { ColorAnimation { duration: 250 } }

        Text {
            id: metricText
            anchors.centerIn: parent
            color: fgSecondary
            font.pixelSize: 11
            font.family: "Consolas"
            text: "FPS: " + root.fps.toFixed(1) +
                  "   |   last: " + root.lastToggleMs.toFixed(0) + "ms" +
                  "   |   avg: " + root.avgToggleMs.toFixed(0) + "ms" +
                  "   |   theme: " + themeBridge.theme
        }
    }
}

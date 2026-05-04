// LEE QtQuick — PowerReserve 페이지 실 데이터 prototype
//
// 검증 항목:
//   - 480 cell pivot 테이블 (48×10) 의 색상 갱신 / 테마 전환 부드러움
//   - LineSeries (QtCharts QML) 의 line chart 렌더링
//   - refresh 시 데이터 재바인딩 elapsed 측정 (Python markRefreshEnd 호출)

import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Window
import QtCharts

ApplicationWindow {
    id: root
    width: 1200
    height: 760
    visible: true
    title: "LEE QML — PowerReserve Real"

    // ── 테마 토큰 ───────────────────────────────────────────────────
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
    Behavior on bgApp        { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface    { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface2   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on bgSurface3   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgPrimary    { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgSecondary  { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on fgTertiary   { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    Behavior on borderSubtle { ColorAnimation { duration: 250; easing.type: Easing.InOutQuad } }
    color: bgApp

    // ── 측정 ────────────────────────────────────────────────────────
    property real lastToggleMs: 0
    property real lastRefreshMs: 0
    property real fps: 60

    Connections {
        target: themeBridge
        function onToggleStarted() { toggleEndTimer.restart() }
        function onToggleFinished(ms) { root.lastToggleMs = ms }
    }
    Timer {
        id: toggleEndTimer
        interval: 260
        onTriggered: themeBridge.markToggleEnd()
    }
    Connections {
        target: dataBridge
        function onRefreshStarted() { refreshEndTimer.restart() }
        function onRefreshFinished(ms) { root.lastRefreshMs = ms }
    }
    Timer {
        // 데이터 적용 + 1 frame paint 후 측정 (대략)
        id: refreshEndTimer
        interval: 16
        onTriggered: dataBridge.markRefreshEnd()
    }
    // FPS
    property int _fpsCount: 0
    property real _fpsLast: 0
    Timer {
        interval: 16
        running: true
        repeat: true
        onTriggered: {
            root._fpsCount += 1
            const now = Date.now()
            if (root._fpsLast === 0) root._fpsLast = now
            if (now - root._fpsLast >= 1000) {
                root.fps = root._fpsCount * 1000.0 / (now - root._fpsLast)
                root._fpsCount = 0
                root._fpsLast = now
            }
        }
    }

    // ── 색상 함수 (실 앱의 price_color reserve 모드와 동일) ────────
    function reserveColor(value) {
        if (value <= 8)  return Qt.rgba(220/255, 50/255, 50/255, 0.65)   // red
        if (value < 10)  return Qt.rgba(255/255, 200/255, 60/255, 0.55)  // yellow
        return Qt.rgba(60/255, 200/255, 100/255, 0.55)                    // green
    }

    // ── Header ──────────────────────────────────────────────────────
    Rectangle {
        id: header
        anchors { top: parent.top; left: parent.left; right: parent.right }
        height: 60
        color: bgSurface
        Rectangle {
            anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
            height: 1; color: borderSubtle
        }
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 24
            anchors.rightMargin: 18
            spacing: 14

            Rectangle {
                width: 32; height: 32; radius: 9; color: accent
                Text { anchors.centerIn: parent; text: "⚡"; color: "white"; font.pixelSize: 16 }
            }
            Text {
                text: "電力予備率"
                color: fgPrimary; font.pixelSize: 16; font.bold: true
            }
            Text {
                text: "OCCTO 30分単位 — 10 area (mock data)"
                color: fgTertiary; font.pixelSize: 11
            }
            Item { Layout.fillWidth: true }

            // refresh
            Button {
                text: "↻ Refresh"
                onClicked: dataBridge.refresh()
            }
            // theme toggle
            Rectangle {
                width: 36; height: 36; radius: 10
                color: themeMouse.containsMouse ? bgSurface3 : bgSurface2
                border.color: borderSubtle; border.width: 1
                Behavior on color { ColorAnimation { duration: 120 } }
                scale: themeMouse.pressed ? 0.95 : 1.0
                Behavior on scale { NumberAnimation { duration: 100 } }
                Text {
                    anchors.centerIn: parent
                    text: isDark ? "☀" : "☾"
                    color: fgPrimary; font.pixelSize: 16
                }
                MouseArea {
                    id: themeMouse
                    anchors.fill: parent; hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: themeBridge.toggle()
                }
            }
        }
    }

    // ── Body ────────────────────────────────────────────────────────
    ColumnLayout {
        anchors {
            top: header.bottom; left: parent.left; right: parent.right; bottom: parent.bottom
            margins: 18
        }
        spacing: 14

        // KPI 카드
        RowLayout {
            Layout.fillWidth: true
            spacing: 12
            Repeater {
                model: [
                    { title: "全国平均",   value: kpiAvg().toFixed(1), unit: "%", color: "#5B8DEF" },
                    { title: "最低予備率", value: kpiMin().toFixed(1), unit: "%", color: "#FF453A" },
                    { title: "注意エリア", value: kpiWarn(),            unit: "件", color: "#FF9F0A" }
                ]
                delegate: Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 90
                    radius: 14; color: bgSurface
                    border.color: borderSubtle; border.width: 1
                    Behavior on color { ColorAnimation { duration: 250 } }
                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 18
                        spacing: 14
                        Column {
                            spacing: 4
                            Text { text: modelData.title; color: fgSecondary; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Row {
                                spacing: 6
                                Text {
                                    text: modelData.value; color: modelData.color
                                    font.pixelSize: 30; font.bold: true; font.family: "Consolas"
                                }
                                Text {
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 5
                                    text: modelData.unit
                                    color: fgTertiary; font.pixelSize: 12
                                }
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }

        // Pivot table (48 × 11) + Chart 좌우 분할
        SplitView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            orientation: Qt.Horizontal

            // Left: Pivot grid
            Rectangle {
                SplitView.preferredWidth: parent.width * 0.62
                SplitView.minimumWidth: 400
                radius: 14; color: bgSurface
                border.color: borderSubtle; border.width: 1
                Behavior on color { ColorAnimation { duration: 250 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 12
                    spacing: 6

                    // 헤더 row
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 1
                        Rectangle { Layout.preferredWidth: 56; height: 28; color: bgSurface2; radius: 4
                            Text { anchors.centerIn: parent; text: "時刻"; color: fgSecondary; font.pixelSize: 10; font.bold: true }
                        }
                        Repeater {
                            model: dataBridge.areas
                            delegate: Rectangle {
                                Layout.fillWidth: true
                                Layout.preferredHeight: 28
                                color: bgSurface2; radius: 4
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData
                                    color: fgSecondary; font.pixelSize: 10; font.bold: true
                                }
                            }
                        }
                    }

                    // 데이터 rows — TableView 대신 ListView (성능 측정 목적)
                    ListView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: dataBridge.rows
                        spacing: 1
                        delegate: RowLayout {
                            width: ListView.view.width
                            height: 24
                            spacing: 1
                            // 시간
                            Rectangle {
                                Layout.preferredWidth: 56
                                Layout.fillHeight: true
                                color: bgSurface2; radius: 3
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData[0]
                                    color: fgSecondary; font.pixelSize: 10
                                    font.family: "Consolas"
                                }
                            }
                            Repeater {
                                model: 10
                                delegate: Rectangle {
                                    required property int index
                                    Layout.fillWidth: true
                                    Layout.fillHeight: true
                                    radius: 3
                                    color: reserveColor(modelData[index + 1])
                                    Behavior on color { ColorAnimation { duration: 200 } }
                                    Text {
                                        anchors.centerIn: parent
                                        text: modelData[index + 1].toFixed(1)
                                        color: isDark ? "white" : "#0B1220"
                                        font.pixelSize: 10; font.bold: true
                                        font.family: "Consolas"
                                    }
                                }
                            }
                        }
                    }
                }
            }

            // Right: Chart (Tokyo 24h)
            Rectangle {
                SplitView.fillWidth: true
                SplitView.minimumWidth: 300
                radius: 14; color: bgSurface
                border.color: borderSubtle; border.width: 1
                Behavior on color { ColorAnimation { duration: 250 } }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 14
                    spacing: 8
                    Text {
                        text: "東京 — 24h"
                        color: fgPrimary; font.pixelSize: 13; font.weight: Font.DemiBold
                    }
                    ChartView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        antialiasing: true
                        legend.visible: false
                        backgroundColor: bgSurface
                        plotAreaColor: "transparent"
                        margins.top: 0; margins.bottom: 0
                        margins.left: 0; margins.right: 0
                        Behavior on backgroundColor { ColorAnimation { duration: 250 } }

                        ValueAxis {
                            id: axX
                            min: 0; max: 47
                            tickCount: 7
                            labelsColor: fgTertiary
                            gridLineColor: borderSubtle
                            labelsFont.family: "Consolas"
                            labelsFont.pixelSize: 9
                        }
                        ValueAxis {
                            id: axY
                            min: 0; max: 35
                            tickCount: 6
                            labelsColor: fgTertiary
                            gridLineColor: borderSubtle
                            labelsFont.family: "Consolas"
                            labelsFont.pixelSize: 9
                        }
                        LineSeries {
                            id: tokyoSeries
                            axisX: axX; axisY: axY
                            color: accent
                            width: 2
                        }
                        // 데이터 갱신 시 line series 재구성
                        Connections {
                            target: dataBridge
                            function onRowsChanged() { rebuildSeries() }
                        }
                        Component.onCompleted: rebuildSeries()
                        function rebuildSeries() {
                            tokyoSeries.clear()
                            const rows = dataBridge.rows
                            // 東京 = areas index 2 → row[3] (시간 + 10 area, 동경=index 2)
                            for (let i = 0; i < rows.length; i++) {
                                tokyoSeries.append(i, rows[i][3])
                            }
                        }
                    }
                }
            }
        }
    }

    // ── 좌하단 회전 (freeze 검출) ──────────────────────────────────
    Rectangle {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.margins: 12
        width: 24; height: 24; radius: 5
        color: accent; opacity: 0.85
        RotationAnimation on rotation {
            from: 0; to: 360; duration: 1500
            loops: Animation.Infinite
        }
    }

    // ── 우하단 메트릭 ──────────────────────────────────────────────
    Rectangle {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 12
        width: metricText.width + 22; height: 36
        radius: 10; color: bgSurface2
        border.color: borderSubtle; border.width: 1
        Behavior on color { ColorAnimation { duration: 250 } }
        Text {
            id: metricText
            anchors.centerIn: parent
            color: fgSecondary
            font.pixelSize: 11; font.family: "Consolas"
            text: "FPS: " + root.fps.toFixed(1) +
                  "  |  refresh: " + root.lastRefreshMs.toFixed(0) + "ms" +
                  "  |  toggle: " + root.lastToggleMs.toFixed(0) + "ms"
        }
    }

    // ── KPI 계산 헬퍼 ──────────────────────────────────────────────
    function kpiAvg() {
        const rows = dataBridge.rows
        let sum = 0, n = 0
        for (let r = 0; r < rows.length; r++) {
            for (let c = 1; c < rows[r].length; c++) { sum += rows[r][c]; n += 1 }
        }
        return n > 0 ? sum / n : 0
    }
    function kpiMin() {
        const rows = dataBridge.rows
        let m = 999
        for (let r = 0; r < rows.length; r++) {
            for (let c = 1; c < rows[r].length; c++) {
                if (rows[r][c] < m) m = rows[r][c]
            }
        }
        return m === 999 ? 0 : m
    }
    function kpiWarn() {
        const rows = dataBridge.rows
        let cnt = 0
        for (let r = 0; r < rows.length; r++) {
            for (let c = 1; c < rows[r].length; c++) {
                if (rows[r][c] < 10) cnt += 1
            }
        }
        return cnt
    }
}

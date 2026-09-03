import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
// One model, one button, one agent picker, one share toggle. Renders purely from the
// snapshot file the controller writes; nothing here knows a model name, a flag, or a color.
Panel {
  id: root
  moduleName: "sero.local-ai"
  ipcTarget: "sero.local-ai"
  manageIpc: false
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  readonly property string sourceDir: String(Qt.resolvedUrl(".")).replace(/^file:\/\//, "").replace(/\/$/, "")
  readonly property string cli: sourceDir + "/bin/omarchy-local-ai"
  readonly property string stateDir: (Quickshell.env("XDG_STATE_HOME") || (Quickshell.env("HOME") + "/.local/state")) + "/omarchy/local-ai"

  property var snap: ({ state: "uninitialized", operation: {}, model: null, reason: "", share: {}, agents: {}, error: "" })
  readonly property string state: snap.state || "uninitialized"
  readonly property var model: snap.model || null
  readonly property var operation: snap.operation || ({})
  readonly property var share: snap.share || ({})
  readonly property var agentList: (snap.agents && snap.agents.launchable) || []
  readonly property bool busy: ["download", "starting", "unload"].indexOf(state) >= 0
  readonly property bool loaded: state === "ready"
  readonly property bool hasRunning: !!snap.running
  readonly property string defaultAgent: (snap.agents && snap.agents.default) || ""
  property string agentPick: ""
  property bool agentsOpen: false
  readonly property string agentSel: agentPick !== "" ? agentPick
    : (agentList.indexOf(defaultAgent) >= 0 ? defaultAgent : (agentList.length > 0 ? agentList[0] : ""))
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Util.alpha(foreground, 0.55)

  function refresh() { if (!poll.running) poll.running = true }
  function act(args) { if (busy || action.running) return; action.command = [cli].concat(args); action.running = true }
  function title() {
    if (loaded && model) return model.name
    if (hasRunning && snap.running && !snap.running.current) return "Older model running"
    return model ? model.name : "Local AI"
  }
  function status() {
    if (snap.error) return snap.error
    if (busy) return spinner() + " " + (operation.detail || state) + (operation.percent > 0 ? " · " + operation.percent + "%" : "")
    if (snap.reason) return snap.reason
    if (loaded && model) return model.engine + " · " + Math.round(model.ctxTokens / 1024) + "K context"
    return ""
  }
  property int spin: 0
  function spinner() { return ["|", "/", "-", "\\"][spin] }
  function startLabel() {
    if (!model) return "Start"
    return !model.downloaded && model.sizeGb > 0 ? "Start · " + model.sizeGb + " GB" : "Start"
  }
  function openAgent() { if (loaded && agentSel !== "") { act(["open-agent", agentSel]); root.close() } }

  // The controller rewrites the snapshot after every step; watching the file is what makes
  // progress live. The timer catches reality changing outside an operation.
  FileView {
    id: snapshotFile
    path: root.stateDir + "/snapshot.json"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: { try { root.snap = JSON.parse(text()) } catch (e) {} }
  }
  Process {
    id: poll
    command: [root.cli, "snapshot"]
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: { if (text.length > 262144) return; try { root.snap = JSON.parse(text) } catch (e) {} } }
  }
  Process { id: action; onExited: root.refresh() }
  Timer { interval: root.opened ? (root.busy ? 3000 : 10000) : 60000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
  Timer { interval: 140; running: root.busy && root.opened; repeat: true; onTriggered: root.spin = (root.spin + 1) % 4 }

  onOpenedChanged: if (opened) refresh()

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function load(): string { root.act(["load"]); return "ok" }
    function unload(): string { root.act(["unload"]); return "ok" }
    function agent(): string { root.openAgent(); return "ok" }
    function refresh(): string { root.refresh(); return "ok" }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Item {
        Rectangle { // hollow = idle, pulsing = working, filled = ready, urgent ring = error
          anchors.centerIn: parent; width: Style.space(9); height: width; radius: width / 2
          color: root.loaded ? root.foreground : "transparent"
          border.width: root.loaded ? 0 : Math.max(1, Style.space(1))
          border.color: root.state === "error" ? (root.bar ? root.bar.urgent : root.foreground) : root.foreground
          SequentialAnimation on opacity {
            running: root.busy; loops: Animation.Infinite; alwaysRunToEnd: true
            NumberAnimation { to: 0.25; duration: 500 } NumberAnimation { to: 1; duration: 500 }
          }
        }
      }
    }
    tooltipText: "Local AI · " + root.title()
    onPressed: function(code) { if (code === Qt.RightButton && root.loaded) root.openAgent(); else root.toggle() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keys
    contentWidth: panel.fittedContentWidth(Style.space(220))
    contentHeight: panel.fittedContentHeight(content.implicitHeight)
    PanelKeyCatcher {
      id: keys
      anchors.fill: parent
      onActivateRequested: { if (root.loaded) root.openAgent(); else if (root.model && !root.snap.reason) root.act(["load"]) }
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: Style.space(10)
        Text { width: parent.width; textFormat: Text.PlainText; text: root.title(); color: root.foreground; font.family: root.bar.fontFamily; font.pixelSize: Style.font.heading; font.weight: Font.Medium; elide: Text.ElideRight }
        Text { width: parent.width; textFormat: Text.PlainText; visible: root.status() !== ""; text: root.status(); color: root.snap.error ? (root.bar ? root.bar.urgent : root.foreground) : root.dim; font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap; maximumLineCount: 3 }
        Link { visible: !root.loaded; enabled: !root.busy && !!root.model && root.snap.reason === ""; text: root.startLabel(); onTriggered: root.act(["load"]) }
        Link { visible: root.loaded && root.agentList.length > 0; text: "Open agent · " + root.agentSel + (root.agentsOpen ? "  ^" : "  v"); onTriggered: root.agentsOpen = !root.agentsOpen }
        Text { visible: root.loaded && root.agentList.length === 0; width: parent.width; textFormat: Text.PlainText; text: "No installed agent can use this model"; color: root.dim; font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall }
        Column {
          visible: root.agentsOpen && root.loaded; width: parent.width; spacing: Style.space(6)
          Repeater {
            model: root.agentList
            Link { required property var modelData; width: content.width; text: "  " + modelData; onTriggered: { root.agentPick = modelData; root.agentsOpen = false; root.openAgent() } }
          }
        }
        Link { visible: root.loaded && !!root.share.available; enabled: !root.busy; text: root.share.active ? "Stop sharing" : "Share on Tailscale"; onTriggered: root.act(["share"]) }
        Text { visible: root.loaded && !!root.share.active; width: parent.width; textFormat: Text.PlainText; text: (root.share.url || "") + "\nkey " + (root.share.key || ""); color: root.dim; font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WrapAnywhere }
        Link { visible: root.loaded || root.hasRunning || root.state === "starting"; enabled: !root.busy; text: "Stop"; onTriggered: root.act(["unload"]) }
      }
    }
  }
  component Link: Text {
    signal triggered()
    textFormat: Text.PlainText
    color: root.foreground; opacity: enabled ? 1 : 0.32; font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall; elide: Text.ElideRight
    MouseArea { anchors.fill: parent; enabled: parent.enabled; hoverEnabled: true; cursorShape: parent.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: parent.triggered() }
  }
}

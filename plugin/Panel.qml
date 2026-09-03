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
  // pending: a verb was just issued and no snapshot has confirmed the worker yet. The panel treats
  // it as busy so the click has an immediate effect instead of a dead second while the worker starts.
  property bool pending: false
  readonly property bool working: ["download", "starting", "unload", "share"].indexOf(state) >= 0
  readonly property bool busy: working || pending
  property int elapsed: 0
  readonly property int expected: operation.expectedSeconds || 0
  readonly property int progress: operation.percent > 0 ? operation.percent
    : (expected > 0 && elapsed > 0 ? Math.min(95, Math.round(elapsed * 100 / expected)) : 0)
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
  function act(args) { if (busy || action.running) return; pending = true; pendingTimeout.restart(); action.command = [cli].concat(args); action.running = true }
  function take(json) { try { snap = JSON.parse(json); if (working || snap.error) pending = false; tick() } catch (e) {} }
  function tick() {
    var t = Date.parse(operation.startedAt || "")
    elapsed = working && !isNaN(t) ? Math.max(0, Math.round((Date.now() - t) / 1000)) : 0
  }
  function mmss(s) { return Math.floor(s / 60) + ":" + (s % 60 < 10 ? "0" : "") + (s % 60) }
  function title() {
    if (loaded && model) return model.name
    if (hasRunning && snap.running && !snap.running.current) return "Older model running"
    return model ? model.name : "Local AI"
  }
  function status() {
    if (snap.error && !pending) return snap.error
    if (pending && !working) return spinner() + " starting"
    if (busy) return spinner() + " " + (operation.detail || state)
      + (elapsed > 0 ? " · " + mmss(elapsed) + (expected > 0 ? " of about " + mmss(expected) : "") : "")
      + (progress > 0 ? " · " + progress + "%" : "")
    if (snap.reason) return snap.reason
    if (loaded && model) return model.engine + " · " + Math.round(model.ctxTokens / 1024) + "K context"
    return ""
  }
  property int spin: 0
  function spinner() { return ["|", "/", "-", "\\"][spin] }
  readonly property int lastStart: snap.lastStartSeconds || 0
  function startLabel() {
    if (!model) return "Start"
    var label = !model.downloaded && model.sizeGb > 0 ? "Start · " + model.sizeGb + " GB" : "Start"
    return lastStart > 0 && model.downloaded ? label + " · usually " + mmss(lastStart) : label
  }
  // The launch is its own process: the panel closes only when the terminal actually opened, and a
  // refusal (no model, wedged launcher) stays on screen instead of vanishing with the panel.
  function openAgent() {
    if (!loaded || agentSel === "" || busy || action.running || agentLaunch.running) return
    agentLaunch.command = [cli, "open-agent", agentSel]; agentLaunch.running = true
  }

  // The controller rewrites the snapshot after every step; watching the file is what makes
  // progress live. The timer catches reality changing outside an operation.
  FileView {
    id: snapshotFile
    path: root.stateDir + "/snapshot.json"
    watchChanges: true
    onFileChanged: reload()
    onLoaded: root.take(text())
  }
  Process {
    id: poll
    command: [root.cli, "snapshot"]
    stdout: StdioCollector { waitForEnd: true; onStreamFinished: { if (text.length <= 262144) root.take(text) } }
  }
  Process { id: action; onExited: root.refresh() }
  Process { id: agentLaunch; onExited: function(code) { root.refresh(); if (code === 0) root.close() } }
  // Poll fast while something runs, whether or not the panel is open, so the bar icon starts and
  // stops moving with the operation; slow when idle. The file watch above makes this a backstop.
  Timer { interval: root.pending ? 1000 : root.working ? 2000 : root.opened ? 10000 : 60000; running: true; repeat: true; triggeredOnStart: true; onTriggered: root.refresh() }
  Timer { id: pendingTimeout; interval: 20000; onTriggered: root.pending = false }
  Timer { interval: 1000; running: root.working; repeat: true; triggeredOnStart: true; onTriggered: root.tick() }
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
        // The ring is the model's place; the dot inside grows with progress and breathes while
        // working, so a glance at the bar says how far along a Start is. Full dot = ready,
        // urgent ring = error, hollow = idle.
        Rectangle {
          id: ring
          anchors.centerIn: parent; width: Style.space(9); height: width; radius: width / 2
          color: "transparent"
          border.width: Math.max(1, Style.space(1))
          border.color: root.state === "error" ? (root.bar ? root.bar.urgent : root.foreground) : root.foreground
          opacity: root.loaded ? 0 : 1
          Behavior on opacity { NumberAnimation { duration: 400 } }
        }
        Rectangle {
          id: dot
          anchors.centerIn: parent
          readonly property real fill: root.loaded ? 1 : root.busy ? Math.max(0.3, root.progress / 100) : 0
          width: ring.width * fill; height: width; radius: width / 2
          color: root.foreground
          Behavior on width { NumberAnimation { duration: 600; easing.type: Easing.OutCubic } }
          SequentialAnimation on opacity {
            running: root.busy; loops: Animation.Infinite; alwaysRunToEnd: true
            NumberAnimation { to: 0.3; duration: 600; easing.type: Easing.InOutSine } NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
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
        // A sliced sphere, the icon's shape at panel size: faint while idle, ripples while working
        // and fills row by row as the download lands, whole and breathing once the model is ready.
        Item {
          id: orb
          width: parent.width; height: Style.space(48)
          readonly property int rows: 9
          readonly property real fill: root.loaded ? 1 : root.progress / 100
          property real phase: 0
          NumberAnimation on phase { running: root.opened && (root.busy || root.loaded); loops: Animation.Infinite; from: 0; to: 1; duration: 2400 }
          Repeater {
            model: orb.rows
            Rectangle {
              required property int index
              readonly property real chord: Math.sqrt(1 - Math.pow((index + 0.5) / orb.rows * 2 - 1, 2))
              readonly property bool lit: (orb.rows - index) / orb.rows <= orb.fill
              readonly property real ripple: root.busy && !lit ? 0.4 + 0.6 * Math.abs(Math.sin((orb.phase + index / orb.rows) * Math.PI)) : 1
              x: (orb.width - width) / 2 + (index % 2 ? Style.space(3) : -Style.space(3))
              y: index * orb.height / orb.rows
              width: orb.width * 0.62 * chord * ripple
              height: orb.height / orb.rows * 0.55
              color: root.state === "error" && root.bar ? root.bar.urgent : root.foreground
              opacity: lit ? 0.85 + 0.15 * Math.sin(orb.phase * 2 * Math.PI) : (root.busy ? 0.55 : 0.28)
            }
          }
        }
        Text { width: parent.width; textFormat: Text.PlainText; text: root.title(); color: root.foreground; font.family: root.bar.fontFamily; font.pixelSize: Style.font.heading; font.weight: Font.Medium; elide: Text.ElideRight }
        Text { width: parent.width; textFormat: Text.PlainText; visible: root.status() !== ""; text: root.status(); color: root.snap.error ? (root.bar ? root.bar.urgent : root.foreground) : root.dim; font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall; wrapMode: Text.WordWrap; maximumLineCount: 3 }
        Link { visible: !root.loaded || (!!root.snap.error && !root.busy); enabled: !root.busy && !!root.model && root.snap.reason === ""; text: root.loaded ? "Restart" : root.startLabel(); onTriggered: root.act(["load"]) }
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
  component Link: Item {
    signal triggered()
    property alias text: label.text
    property alias enabled: mouse.enabled
    implicitWidth: label.implicitWidth
    implicitHeight: label.implicitHeight
    Rectangle { // rows are the only chrome the panel has; a hover wash says they are buttons
      anchors.fill: parent; radius: Style.space(2)
      color: mouse.containsMouse && mouse.enabled ? Util.alpha(root.foreground, 0.1) : "transparent"
    }
    Text {
      id: label
      width: parent.width; textFormat: Text.PlainText
      color: root.foreground; opacity: mouse.enabled ? 1 : 0.32
      font.family: root.bar.fontFamily; font.pixelSize: Style.font.bodySmall; elide: Text.ElideRight
    }
    MouseArea { id: mouse; anchors.fill: parent; hoverEnabled: true; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: parent.triggered() }
  }
}

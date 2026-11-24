import AVFoundation
import SwiftUI
import UIKit
import WebKit

/// 資料助秘NotebookLM MCP簡報 — iPhone／iPad 版
/// WKWebView 開啟 App 內建的網頁（和線上版同一份程式：六種產出、柔和插畫簡報、專案範本、成品庫、語音教學），
/// 由 LocalServer 在 127.0.0.1 提供 → 不用網路也能用內建範本產生（NotebookLM 要網路，在 Safari 開啟筆記本）。
/// 匯出的 PowerPoint／Word／圖片／網頁用分享面板交給「檔案」、LINE、AirDrop、Keynote 等。
@main
struct ZMSNotebookLMApp: App {
    init() {
        LocalServer.shared.start()
        // 語音教學：靜音開關打開時也要聽得到
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio, options: [.duckOthers])
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    var body: some Scene {
        WindowGroup {
            WebContainer()
                .background(Color(red: 0.059, green: 0.153, blue: 0.278))
                .ignoresSafeArea()
        }
    }
}

struct WebContainer: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView { Web.shared.view }
    func updateUIView(_ v: WKWebView, context: Context) {}
}

/// 網頁與 App 之間的橋：網頁呼叫 window.webkit.messageHandlers.zms.postMessage({cmd, args})，回傳 Promise
final class Web: NSObject, WKScriptMessageHandlerWithReply, WKNavigationDelegate, WKUIDelegate {
    static let shared = Web()
    let view: WKWebView

    override init() {
        let cfg = WKWebViewConfiguration()
        cfg.allowsInlineMediaPlayback = true
        cfg.mediaTypesRequiringUserActionForPlayback = []
        cfg.websiteDataStore = .default()
        let ver = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        // 讓網頁知道自己在 iPhone／iPad App 裡（app.js 會改用 App 的存檔、檢查更新）；
        // 網頁的錯誤訊息轉到 iOS 系統記錄（除錯：log show --predicate 'process == "ZMSNotebookLM"'）
        let shim = WKUserScript(source: """
            window.ZMSIOS = { version: '\(ver)' };
            (function () {
              function send(k, a) { try { window.webkit.messageHandlers.zms.postMessage({ cmd: 'log', args: [k, Array.prototype.map.call(a, function (x) { return x && x.stack ? x.stack : String(x); }).join(' ')] }); } catch (e) {} }
              var ce = console.error.bind(console);
              console.error = function () { send('error', arguments); ce.apply(null, arguments); };
              window.addEventListener('error', function (e) { send('pageerror', [e.message + ' @' + e.filename + ':' + e.lineno]); });
              window.addEventListener('unhandledrejection', function (e) { send('rejection', [e.reason]); });
            })();
            """, injectionTime: .atDocumentStart, forMainFrameOnly: true)
        cfg.userContentController.addUserScript(shim)
        view = WKWebView(frame: .zero, configuration: cfg)
        super.init()
        cfg.userContentController.addScriptMessageHandler(self, contentWorld: .page, name: "zms")
        view.navigationDelegate = self
        view.uiDelegate = self
        view.isOpaque = false
        view.backgroundColor = UIColor(red: 0.949, green: 0.961, blue: 0.980, alpha: 1)
        view.scrollView.backgroundColor = view.backgroundColor
        view.scrollView.bounces = false
        view.scrollView.contentInsetAdjustmentBehavior = .never   // 安全區域由網頁的 env(safe-area-inset-*) 處理
        view.allowsBackForwardNavigationGestures = false
        if #available(iOS 16.4, *) { view.isInspectable = true }
        view.load(URLRequest(url: LocalServer.shared.url))
    }

    // 外部連結（NotebookLM 筆記本、GitHub、安裝頁）用 Safari 開
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
        if let u = a.request.url, u.host != "127.0.0.1", ["http", "https", "itms-services"].contains(u.scheme ?? ""), a.targetFrame?.isMainFrame != false {
            UIApplication.shared.open(u); decisionHandler(.cancel); return
        }
        decisionHandler(.allow)
    }
    func webView(_ w: WKWebView, createWebViewWith c: WKWebViewConfiguration, for a: WKNavigationAction, windowFeatures f: WKWindowFeatures) -> WKWebView? {
        if let u = a.request.url { UIApplication.shared.open(u) }
        return nil
    }

    // 網頁的 confirm()／alert()：WKWebView 預設不顯示，要自己做對話框
    func webView(_ w: WKWebView, runJavaScriptConfirmPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping (Bool) -> Void) {
        let ac = UIAlertController(title: nil, message: m, preferredStyle: .alert)
        ac.addAction(UIAlertAction(title: "取消", style: .cancel) { _ in completionHandler(false) })
        ac.addAction(UIAlertAction(title: "確定", style: .default) { _ in completionHandler(true) })
        present(ac) { completionHandler(false) }
    }
    func webView(_ w: WKWebView, runJavaScriptAlertPanelWithMessage m: String, initiatedByFrame f: WKFrameInfo, completionHandler: @escaping () -> Void) {
        let ac = UIAlertController(title: nil, message: m, preferredStyle: .alert)
        ac.addAction(UIAlertAction(title: "確定", style: .default) { _ in completionHandler() })
        present(ac) { completionHandler() }
    }

    func webViewWebContentProcessDidTerminate(_ w: WKWebView) { w.reload() }

    // MARK: 網頁呼叫的功能
    func userContentController(_ u: WKUserContentController, didReceive m: WKScriptMessage, replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = m.body as? [String: Any], let cmd = body["cmd"] as? String else { replyHandler(nil, "bad message"); return }
        let args = body["args"] as? [Any] ?? []
        let s = { (i: Int) -> String in args.count > i ? "\(args[i])" : "" }
        let ver = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
        switch cmd {
        case "app_info":
            replyHandler(["status": "ok", "name": "資料助秘NotebookLM MCP簡報", "version": ver, "platform": "ios", "model": UIDevice.current.model], nil)
        case "log":
            NSLog("[web %@] %@", s(0), s(1))
            replyHandler(true, nil)
        case "open_url":
            if let u = URL(string: s(0)), ["github.com", "achir1015.github.io", "notebook.google.com", "notebooklm.google.com"].contains(u.host ?? "") { UIApplication.shared.open(u) }
            replyHandler(true, nil)
        case "save_file":
            // args: [檔名, base64 內容] → 存到暫存資料夾，開分享面板（存到「檔案」、AirDrop 到電腦、用其他 App 開啟）
            let name = (s(0) as NSString).lastPathComponent.isEmpty ? "成品.zip" : (s(0) as NSString).lastPathComponent
            guard let data = Data(base64Encoded: s(1)) else { replyHandler(nil, "bad data"); return }
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent("export", isDirectory: true)
            try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent(name)
            do { try data.write(to: url, options: .atomic) } catch { replyHandler(nil, "write failed"); return }
            let vc = UIActivityViewController(activityItems: [url], applicationActivities: nil)
            if let pop = vc.popoverPresentationController {           // iPad：分享面板要指定位置
                pop.sourceView = view
                pop.sourceRect = CGRect(x: view.bounds.midX, y: view.bounds.midY, width: 1, height: 1)
                pop.permittedArrowDirections = []
            }
            vc.completionWithItemsHandler = { _, done, _, _ in replyHandler(done, nil) }
            present(vc) { replyHandler(false, nil) }
        default:
            replyHandler(nil, "unknown command \(cmd)")
        }
    }

    private func present(_ vc: UIViewController, fail: () -> Void) {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        var top = scene?.windows.first(where: { $0.isKeyWindow })?.rootViewController
        while let p = top?.presentedViewController { top = p }
        if let top { top.present(vc, animated: true) } else { fail() }
    }
}

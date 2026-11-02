// Agent.swift: the viewer's side of vm-agent (100.102.86.30:8890): the clipboard as UTF-8 both ways and Mac files
// dropped on the window into the VM's ~/Downloads. The token is a text file in ~/Downloads/API, never in the code.
import Foundation

final class Agent: NSObject, URLSessionTaskDelegate {
    static let host = "100.102.86.30"
    let base = URL(string: "http://\(Agent.host):8890")!
    var token: String { (try? String(contentsOfFile: NSHomeDirectory() + "/Downloads/API/chromium-vm-agent.txt", encoding: .utf8))?
        .trimmingCharacters(in: .whitespacesAndNewlines) ?? "" }
    private lazy var session = URLSession(configuration: .default, delegate: self, delegateQueue: .main)
    private var progress: [Int: (Double) -> Void] = [:]

    private func request(_ path: String, method: String = "POST", body: Data? = nil) -> URLRequest {
        var r = URLRequest(url: base.appendingPathComponent(path))
        r.httpMethod = method; r.httpBody = body; r.timeoutInterval = 20
        r.setValue(token, forHTTPHeaderField: "X-Mantra-Token")
        return r
    }

    /// POST /api/<action>: calls back on the main queue with the result or an error sentence.
    func call(_ action: String, _ args: [String: Any] = [:], done: @escaping (Any?, String?) -> Void) {
        let body = try? JSONSerialization.data(withJSONObject: args)
        session.dataTask(with: request("api/" + action, body: body)) { d, _, e in
            guard let d, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else {
                return done(nil, e?.localizedDescription ?? "no answer from vm-agent") }
            if j["ok"] as? Bool == true { done(j["result"], nil) } else { done(nil, j["error"] as? String ?? "error") }
        }.resume()
    }

    func clipGet(_ done: @escaping (String?) -> Void) { call("clip_get") { r, _ in done(r as? String) } }
    func clipSet(_ text: String, _ done: @escaping (Bool) -> Void) { call("clip_set", ["text": text]) { _, e in done(e == nil) } }

    /// PUT /files/<name>: the file's bytes into ~/Downloads on the VM.
    func put(_ file: URL, progress p: @escaping (Double) -> Void, done: @escaping (String?, String?) -> Void) {
        let name = file.lastPathComponent.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? "file"
        var r = request("files/" + name, method: "PUT"); r.timeoutInterval = 3600
        let t = session.uploadTask(with: r, fromFile: file) { d, _, e in
            guard let d, let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else {
                return done(nil, e?.localizedDescription ?? "no answer") }
            if j["ok"] as? Bool == true, let res = j["result"] as? [String: Any] { done(res["path"] as? String, nil) }
            else { done(nil, j["error"] as? String ?? "error") }
        }
        progress[t.taskIdentifier] = p
        t.resume()
    }

    /// GET /files/<name>: a file of the VM's ~/Downloads into `dest` (written beside it first, then moved).
    func get(_ name: String, to dest: URL, done: @escaping (String?) -> Void) {
        let n = name.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? name
        var r = request("files/" + n, method: "GET"); r.timeoutInterval = 3600
        session.downloadTask(with: r) { tmp, resp, e in
            guard let tmp, (resp as? HTTPURLResponse)?.statusCode == 200 else { return done(e?.localizedDescription ?? "not found on the VM") }
            do {
                let fm = FileManager.default
                try fm.createDirectory(at: dest.deletingLastPathComponent(), withIntermediateDirectories: true)
                if fm.fileExists(atPath: dest.path) { try fm.removeItem(at: dest) }
                try fm.moveItem(at: tmp, to: dest); done(nil)
            } catch { done(error.localizedDescription) }
        }.resume()
    }

    func urlSession(_ s: URLSession, task: URLSessionTask, didSendBodyData _: Int64, totalBytesSent sent: Int64, totalBytesExpectedToSend total: Int64) {
        if total > 0 { progress[task.taskIdentifier]?(Double(sent) / Double(total)) }
    }
}

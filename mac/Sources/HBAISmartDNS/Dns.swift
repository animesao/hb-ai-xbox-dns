import Foundation

// Сервисы Smart DNS. Список тот же, что в XboxDns.cs (проверено 23.10.2026 из России).
enum Services {
    static let name = ["Comss.one", "GeoHide EU", "MagicDNS", "Astracat", "Xbox DNS"]
    static let short = ["Comss", "GeoHide", "MagicDNS", "Astracat", "Xbox"]
    static let v4: [[String]] = [
        ["83.220.169.155", "212.109.195.93"],
        ["143.20.64.192", "45.13.237.213"],
        ["109.120.132.43", "94.249.177.102"],
        ["135.106.217.200"],
        ["111.88.96.54", "111.88.96.55"],
    ]
    static let opens = [
        "ChatGPT, Claude, ElevenLabs, Grok; Gemini — через раз",
        "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
        "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
        "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
        "только Xbox Live, нейросети — нет",
    ]
    static let site = ["comss.ru", "geohide.ru", "magicdns.ru", "astracat", "xbox-dns.ru"]
    static let url = ["https://www.comss.ru/", "https://geohide.ru/", "https://magicdns.ru/", "https://astracat2022.github.io/dns/", "https://xbox-dns.ru/"]
    static let xboxSet = 4
    // адреса из прежних версий: xbox-dns.ru 1.0 и российский узел GeoHide 1.1
    static let oldSets: [String: Int] = ["111.88.96.50": 4, "111.88.96.51": 4, "159.194.200.33": 1, "193.233.112.67": 1]
    static var count: Int { name.count }
}

enum Shell {
    /// Запуск программы с таймаутом. Возвращает код выхода и весь вывод (stdout + stderr).
    @discardableResult
    static func run(_ path: String, _ args: [String], timeout: TimeInterval = 20) -> (code: Int32, out: String) {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: path)
        p.arguments = args
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = pipe
        do { try p.run() } catch { return (-1, "\(error)") }
        let group = DispatchGroup()
        group.enter()
        var data = Data()
        DispatchQueue.global().async {
            data = pipe.fileHandleForReading.readDataToEndOfFile()
            p.waitUntilExit()
            group.leave()
        }
        if group.wait(timeout: .now() + timeout) == .timedOut {
            p.terminate()
            return (-2, "timeout")
        }
        return (p.terminationStatus, String(data: data, encoding: .utf8) ?? "")
    }
}

// Смена DNS через стандартный networksetup. Права администратора macOS спрашивает сама (окно с паролем).
enum Dns {
    static let setup = "/usr/sbin/networksetup"

    /// Сетевые службы (Wi-Fi, Ethernet и т.д.) без отключённых (они помечены звёздочкой).
    static func services() -> [String] {
        let r = Shell.run(setup, ["-listallnetworkservices"])
        return r.out.split(separator: "\n").dropFirst().map { String($0).trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty && !$0.hasPrefix("*") }
    }

    /// nil — DNS сервиса не стоит, иначе номер набора.
    static func activeSet() -> Int? {
        for s in services() {
            let r = Shell.run(setup, ["-getdnsservers", s])
            for raw in r.out.split(separator: "\n") {
                let line = raw.trimmingCharacters(in: .whitespaces)
                for (k, ips) in Services.v4.enumerated() where ips.contains(line) { return k }
                if let k = Services.oldSets[line] { return k }
            }
        }
        return nil
    }

    static func enable(_ set: Int) -> String? { apply(Services.v4[set]) }
    static func disable() -> String? { apply(nil) }

    /// nil — всё хорошо, иначе текст ошибки для окна.
    private static func apply(_ ips: [String]?) -> String? {
        let svcs = services()
        if svcs.isEmpty { return "Не нашли сетевых подключений" }
        var cmds: [String] = []
        for s in svcs {
            let quoted = "\"" + s.replacingOccurrences(of: "\"", with: "\\\"") + "\""
            cmds.append("\(setup) -setdnsservers \(quoted) " + (ips?.joined(separator: " ") ?? "empty"))
        }
        cmds.append("/usr/bin/dscacheutil -flushcache")
        cmds.append("/usr/bin/killall -HUP mDNSResponder")
        let script = cmds.joined(separator: "; ")
        let esc = script.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "\"", with: "\\\"")
        let r = Shell.run("/usr/bin/osascript", ["-e", "do shell script \"\(esc)\" with administrator privileges"], timeout: 180)
        if r.code != 0 {
            if r.out.contains("-128") { return "Отменено: без пароля администратора DNS не поменять" }
            return "Не получилось: " + r.out.trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return nil
    }
}

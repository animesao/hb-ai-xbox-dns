import Foundation

// Проверка: спрашиваем DNS сервиса напрямую (dig), подключаемся к выданному адресу с именем сайта (curl --resolve)
// и смотрим ответ. Так видно, что получит человек, даже если DNS ещё не включён. dig и curl есть в каждой macOS.
enum Probe {
    static let host = ["chatgpt.com", "claude.ai", "gemini.google.com", "elevenlabs.io", "grok.com", "www.perplexity.ai"]
    static let label = ["ChatGPT", "Claude", "Gemini", "ElevenLabs", "Grok", "Perplexity"]
    static let ok = "открывается", blocked = "блок страны", captcha = "капча Google", noLink = "нет связи", noDns = "DNS молчит", zero = "не пускает"
    static let ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

    /// nil — сервер не ответил; "" — ответ без адреса; иначе IPv4.
    static func resolve(_ server: String, _ host: String) -> String? {
        let r = Shell.run("/usr/bin/dig", ["+short", "+time=3", "+tries=1", "@\(server)", host, "A"], timeout: 10)
        if r.out.contains("timed out") || r.out.contains("no servers could be reached") || r.code == -2 { return nil }
        let ip = r.out.split(separator: "\n").map { String($0).trimmingCharacters(in: .whitespaces) }
            .first { $0.range(of: #"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"#, options: .regularExpression) != nil }
        return ip ?? ""
    }

    static func site(_ host: String, _ ip: String) -> String {
        let r = Shell.run("/usr/bin/curl", ["-s", "-o", "/dev/null", "-m", "10", "--noproxy", "*", "-A", ua,
                                             "--resolve", "\(host):443:\(ip)", "-w", "%{http_code} %{redirect_url}", "https://\(host)/"], timeout: 15)
        let out = r.out
        if out.isEmpty || out.hasPrefix("000") { return noLink }
        if out.contains("/sorry/") { return captcha }
        for b in ["restrict", "unsupported", "unavailable", "not-available"] where out.contains(b) { return blocked }
        return ok
    }

    /// Результат по каждому сайту для набора DNS; сайты проверяются параллельно.
    static func service(_ set: Int) -> [String] {
        var res = Array(repeating: noDns, count: host.count)
        let lock = NSLock()
        let group = DispatchGroup()
        for (k, h) in host.enumerated() {
            group.enter()
            DispatchQueue.global().async {
                var ip: String? = nil
                for srv in Services.v4[set] { ip = resolve(srv, h); if ip != nil { break } }
                let verdict: String
                if ip == nil { verdict = noDns }
                else if ip == "" || ip == "0.0.0.0" { verdict = zero }
                else { verdict = site(h, ip!) }
                lock.lock(); res[k] = verdict; lock.unlock()
                group.leave()
            }
        }
        group.wait()
        return res
    }

    static func good(_ r: [String]?) -> Int { r?.filter { $0 == ok }.count ?? -1 }
}

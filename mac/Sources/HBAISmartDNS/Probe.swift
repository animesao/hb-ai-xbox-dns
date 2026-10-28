import Foundation

// Проверка: спрашиваем DNS сервиса напрямую (dig), подключаемся к выданному адресу с именем сайта (curl --resolve)
// и смотрим ответ. Так видно, что получит человек, даже если DNS ещё не включён. dig и curl есть в каждой macOS.
enum Probe {
    // Discord и YouTube — в конце списка: их сервис не проксирует (проверено 27.10.2026 из Москвы), DNS отдаёт
    // их настоящие адреса. Ranked отделяет их от нейросетей: «Найти лучший» выбирает сервис по нейросетям.
    static let host = ["chatgpt.com", "claude.ai", "gemini.google.com", "elevenlabs.io", "grok.com", "www.perplexity.ai", "discord.com", "www.youtube.com"]
    static let label = ["ChatGPT", "Claude", "Gemini", "ElevenLabs", "Grok", "Perplexity", "Discord", "YouTube"]
    static let ranked = 6   // столько сайтов в начале — нейросети: по ним выбирается лучший сервис
    static let ok = "открывается", blocked = "блок страны", captcha = "капча Google", noLink = "нет связи", noDns = "DNS молчит", zero = "не пускает"
    static let ua = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"

    /// nil — сервер не ответил; "" — ответ без адреса; иначе IPv4.
    /// Две попытки: UDP-пакет иногда теряется (27.10.2026 GeoHide раз в несколько запросов не отвечал).
    static func resolve(_ server: String, _ host: String) -> String? {
        let r = Shell.run("/usr/bin/dig", ["+short", "+time=3", "+tries=2", "@\(server)", host, "A"], timeout: 15)
        return parseDig(r.out, timedOut: r.code == -2)
    }

    /// Разбор вывода `dig +short`: первый адрес IPv4; nil — сервер не ответил.
    static func parseDig(_ out: String, timedOut: Bool) -> String? {
        if timedOut || out.contains("timed out") || out.contains("no servers could be reached") { return nil }
        let ip = out.split(separator: "\n").map { String($0).trimmingCharacters(in: .whitespaces) }
            .first { $0.range(of: #"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$"#, options: .regularExpression) != nil }
        return ip ?? ""
    }

    /// Что сказать по ответу DNS, не заходя на сайт; nil — адрес настоящий, надо проверять сайт.
    static func verdict(_ ip: String?) -> String? {
        guard let ip = ip else { return noDns }
        return ip == "" || ip == "0.0.0.0" ? zero : nil
    }

    static func site(_ host: String, _ ip: String) -> String {
        let r = Shell.run("/usr/bin/curl", ["-s", "-o", "/dev/null", "-m", "10", "--noproxy", "*", "-A", ua,
                                             "--resolve", "\(host):443:\(ip)", "-w", "%{http_code} %{redirect_url}", "https://\(host)/"], timeout: 15)
        return classify(r.out)
    }

    /// Что видит человек по ответу curl («код адрес_переадресации»): капча Google, «недоступно в стране» или сайт.
    static func classify(_ out: String) -> String {
        if out.isEmpty || out.hasPrefix("000") { return noLink }
        let o = out.lowercased()
        if o.contains("/sorry/") { return captcha }
        for b in ["restrict", "unsupported", "unavailable", "not-available"] where o.contains(b) { return blocked }
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
                let v = verdict(ip) ?? site(h, ip!)
                lock.lock(); res[k] = v; lock.unlock()
                group.leave()
            }
        }
        group.wait()
        return res
    }

    static func good(_ r: [String]?) -> Int { r.map { $0.prefix(ranked).filter { $0 == ok }.count } ?? -1 }

    /// Сервис, где открылось больше всего сайтов; при равенстве остаётся текущий, чтобы не переключать DNS впустую,
    /// а без текущего среди проверенных — тот, что раньше в списке. Непроверенный (nil), например Xbox, не выбирается.
    static func best(_ all: [[String]?], current: Int) -> Int {
        var b = current >= 0 && current < all.count && all[current] != nil ? current : 0
        for k in all.indices where good(all[k]) > good(all[b]) { b = k }
        return b
    }
}

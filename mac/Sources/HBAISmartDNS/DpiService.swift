import Foundation

/// Локальный сервис обхода блокировок DPI (GoodbyeDPI / Zapret) для macOS.
/// Поднимает HTTP CONNECT + SOCKS5 прокси на 127.0.0.1:2080 и раздаёт PAC-скрипт.
/// Фрагментирует пакеты Client Hello для YouTube и Discord.
public final class DpiService {
    public static let shared = DpiService()
    public static let defaultPort: UInt16 = 2080
    public private(set) var port: UInt16 = defaultPort
    private var serverFd: Int32 = -1
    public private(set) var isRunning: Bool = false
    private let queue = DispatchQueue(label: "com.hbai.dpiproxy", attributes: .concurrent)

    public static let bypassDomains = [
        "discord.com", "discord.gg", "discordapp.com", "discordapp.net",
        "discord.media", "discordcdn.com", "dis.gd", "discord.co",
        "youtube.com", "youtu.be", "googlevideo.com", "ytimg.com",
        "ggpht.com", "youtube-nocookie.com", "yt.be", "gvt1.com",
        "roblox.com", "rbxcdn.com", "robloxlabs.com", "rbx.com", "rbxmanagers.com",
        "steamcommunity.com", "steampowered.com", "steamstatic.com",
        "twitch.tv", "ttvnw.net", "jtvnw.net",
        "x.com", "twitter.com", "t.co", "twimg.com",
        "instagram.com", "cdninstagram.com", "threads.net",
        "spotify.com", "scdn.co",
        "notion.so", "notion.site"
    ]

    public static func matches(_ host: String) -> Bool {
        let h = host.lowercased()
        for d in bypassDomains {
            if h == d || h.hasSuffix("." + d) {
                return true
            }
        }
        return false
    }

    public static func pacScript(port: UInt16) -> String {
        let domains = bypassDomains.map { "\"\($0)\"" }.joined(separator: ", ")
        return """
        function FindProxyForURL(url, host) {
            var d = [\(domains)];
            for (var i = 0; i < d.length; i++) {
                if (host === d[i] || dnsDomainIs(host, "." + d[i])) {
                    return "PROXY 127.0.0.1:\(port); SOCKS5 127.0.0.1:\(port); DIRECT";
                }
            }
            return "DIRECT";
        }
        """
    }

    public func start() -> Bool {
        guard !isRunning else { return true }
        for p in DpiService.defaultPort...(DpiService.defaultPort + 10) {
            let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
            guard fd >= 0 else { continue }
            var yes: Int32 = 1
            Darwin.setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, socklen_t(MemoryLayout<Int32>.size))
            var addr = sockaddr_in()
            addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
            addr.sin_family = sa_family_t(AF_INET)
            addr.sin_port = p.bigEndian
            addr.sin_addr.s_addr = inet_addr("127.0.0.1")
            let bound = withUnsafePointer(to: &addr) {
                $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                    Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
                }
            }
            if bound == 0 && Darwin.listen(fd, 50) == 0 {
                serverFd = fd
                port = p
                isRunning = true
                queue.async { [weak self] in self?.acceptLoop() }
                setSystemProxy(true)
                return true
            }
            Darwin.close(fd)
        }
        return false
    }

    public func stop() {
        guard isRunning else { return }
        isRunning = false
        setSystemProxy(false)
        if serverFd >= 0 {
            Darwin.close(serverFd)
            serverFd = -1
        }
    }

    private func setSystemProxy(_ enable: Bool) {
        let setup = "/usr/sbin/networksetup"
        let svcs = Dns.services()
        for s in svcs {
            if enable {
                Shell.run(setup, ["-setautoproxyurl", s, "http://127.0.0.1:\(port)/proxy.pac"])
                Shell.run(setup, ["-setautoproxystate", s, "on"])
            } else {
                Shell.run(setup, ["-setautoproxystate", s, "off"])
            }
        }
    }

    private func acceptLoop() {
        while isRunning && serverFd >= 0 {
            let clientFd = Darwin.accept(serverFd, nil, nil)
            guard clientFd >= 0 else { break }
            queue.async { [weak self] in
                self?.handleClient(clientFd)
            }
        }
    }

    private func handleClient(_ clientFd: Int32) {
        defer { Darwin.close(clientFd) }
        var buf = [UInt8](repeating: 0, count: 4096)
        let n = Darwin.recv(clientFd, &buf, buf.count, 0)
        guard n > 0 else { return }

        // 1. PAC Request
        let reqStr = String(decoding: buf.prefix(n), as: UTF8.self)
        if reqStr.hasPrefix("GET ") && (reqStr.contains("/proxy.pac") || reqStr.contains("/pac") || reqStr.contains("GET / ")) {
            let pac = DpiService.pacScript(port: port)
            let resp = "HTTP/1.1 200 OK\r\nContent-Type: application/x-ns-proxy-autoconfig\r\nConnection: close\r\n\r\n" + pac
            resp.withCString { Darwin.send(clientFd, $0, strlen($0), 0) }
            return
        }

        // 2. HTTP CONNECT
        if reqStr.hasPrefix("CONNECT ") {
            let parts = reqStr.split(separator: " ")
            guard parts.count > 1 else { return }
            let target = parts[1].split(separator: ":")
            let host = String(target[0])
            let targetPort: UInt16 = target.count > 1 ? (UInt16(target[1]) ?? 443) : 443

            guard let upstreamFd = connectUpstream(host: host, port: targetPort) else { return }
            defer { Darwin.close(upstreamFd) }

            let ok = "HTTP/1.1 200 Connection Established\r\n\r\n"
            ok.withCString { Darwin.send(clientFd, $0, strlen($0), 0) }

            // Read TLS ClientHello
            let got = Darwin.recv(clientFd, &buf, buf.count, 0)
            if got > 0 {
                if got > 12 && buf[0] == 0x16 && buf[1] == 0x03 {
                    // Split at 8 bytes
                    buf.withUnsafeBytes { ptr in
                        Darwin.send(upstreamFd, ptr.baseAddress!, 8, 0)
                        usleep(3000)
                        Darwin.send(upstreamFd, ptr.baseAddress! + 8, got - 8, 0)
                    }
                } else {
                    buf.withUnsafeBytes { ptr in
                        Darwin.send(upstreamFd, ptr.baseAddress!, got, 0)
                    }
                }
            }

            pipe(clientFd, upstreamFd)
            return
        }
    }

    private func connectUpstream(host: String, port: UInt16) -> Int32? {
        let fd = Darwin.socket(AF_INET, SOCK_STREAM, 0)
        guard fd >= 0 else { return nil }
        var yes: Int32 = 1
        Darwin.setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &yes, socklen_t(MemoryLayout<Int32>.size))

        guard let hostEntry = gethostbyname(host) else {
            Darwin.close(fd)
            return nil
        }
        var addr = sockaddr_in()
        addr.sin_len = UInt8(MemoryLayout<sockaddr_in>.size)
        addr.sin_family = sa_family_t(AF_INET)
        addr.sin_port = port.bigEndian
        memcpy(&addr.sin_addr, hostEntry.pointee.h_addr_list[0]!, Int(hostEntry.pointee.h_length))

        let connected = withUnsafePointer(to: &addr) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_in>.size))
            }
        }
        if connected == 0 { return fd }
        Darwin.close(fd)
        return nil
    }

    private func pipe(_ s1: Int32, _ s2: Int32) {
        let g = DispatchGroup()
        g.enter(); g.enter()
        queue.async {
            var b = [UInt8](repeating: 0, count: 16384)
            while true {
                let n = Darwin.recv(s1, &b, b.count, 0)
                guard n > 0 else { break }
                b.withUnsafeBytes { Darwin.send(s2, $0.baseAddress!, n, 0) }
            }
            Darwin.shutdown(s2, SHUT_WR)
            g.leave()
        }
        queue.async {
            var b = [UInt8](repeating: 0, count: 16384)
            while true {
                let n = Darwin.recv(s2, &b, b.count, 0)
                guard n > 0 else { break }
                b.withUnsafeBytes { Darwin.send(s1, $0.baseAddress!, n, 0) }
            }
            Darwin.shutdown(s1, SHUT_WR)
            g.leave()
        }
        g.wait()
    }
}

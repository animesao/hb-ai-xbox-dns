#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HB AI · Smart DNS 1.25 для Linux.
ChatGPT, Claude, Gemini, ElevenLabs, Discord и YouTube одной кнопкой.

Поддерживает графический интерфейс (Tkinter) и работу из терминала (CLI).
Управление DNS через resolvectl (systemd-resolved), NetworkManager (nmcli),
resolvconf или прямое редактирование /etc/resolv.conf.
"""

import argparse
import json
import os
import re
import socket
import ssl
import struct
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from typing import Dict, List, Optional, Set, Tuple

VERSION = "1.25"
REPO_URL = "https://github.com/animesao/hb-ai-xbox-dns"
VK_URL = "https://vk.com/neiroseti_ai"


# ============================================================================
# СЕРВИСЫ SMART DNS
# ============================================================================

class Services:
    """Сервисы Smart DNS, проверенные из России."""
    NAME = ["Comss.one", "GeoHide EU", "MagicDNS", "Xbox DNS"]
    SHORT = ["Comss", "GeoHide", "MagicDNS", "Xbox"]
    V4 = [
        ["94.250.253.55", "212.109.195.93"],
        ["143.20.64.192", "45.13.237.213"],
        ["109.120.132.43", "94.249.177.102"],
        ["111.88.96.54", "111.88.96.55"],
    ]
    V6 = [
        [],
        [],
        [],
        ["2a00:ab00:1233:26::50", "2a00:ab00:1233:26::51"],
    ]
    OPENS = [
        "ChatGPT, Claude, Gemini, ElevenLabs, Grok, Perplexity",
        "ChatGPT, Claude, ElevenLabs, Grok, Perplexity; Gemini — через раз",
        "ChatGPT, Claude, Gemini, ElevenLabs, Grok, Perplexity",
        "только Xbox Live, нейросети — нет",
    ]
    SITE = ["comss.ru", "geohide.ru", "magicdns.ru", "xbox-dns.ru"]
    URL = [
        "https://www.comss.ru/",
        "https://geohide.ru/",
        "https://magicdns.ru/",
        "https://xbox-dns.ru/",
    ]
    XBOX_SET = 3

    # Адреса из прежних версий, которые ещё работают
    OLD_SETS: Dict[str, int] = {
        "111.88.96.50": 3,
        "111.88.96.51": 3,
        "83.220.169.155": 0,
    }

    # Нерабочие адреса прежних версий: российский узел GeoHide (1.1) и Astracat (1.2-1.21)
    STALE: Set[str] = {
        "159.194.200.33",
        "193.233.112.67",
        "135.106.217.200",
        "85.209.2.112",
    }

    @classmethod
    def count(cls) -> int:
        return len(cls.NAME)

    @classmethod
    def set_of(cls, address: str) -> Optional[int]:
        """Какому сервису принадлежит адрес DNS; None — чужой адрес."""
        a = address.split("%")[0].strip().lower()
        for k, ips in enumerate(cls.V4):
            if a in [ip.lower() for ip in ips]:
                return k
        for k, ips in enumerate(cls.V6):
            if a in [ip.lower() for ip in ips]:
                return k
        return cls.OLD_SETS.get(a)

    @classmethod
    def is_stale(cls, address: str) -> bool:
        """Адрес из прежних версий, который больше не работает."""
        a = address.split("%")[0].strip().lower()
        return a in cls.STALE

    @classmethod
    def find_index(cls, query: str) -> Optional[int]:
        """Поиск индекса сервиса по имени, короткому названию или индексу."""
        q = str(query).strip().lower()
        if q.isdigit():
            idx = int(q)
            if 0 <= idx < len(cls.NAME):
                return idx
        for i, s in enumerate(cls.SHORT):
            if q == s.lower():
                return i
        for i, n in enumerate(cls.NAME):
            if q in n.lower():
                return i
        return None


# ============================================================================
# ПРОВЕРКА ДОСТУПНОСТИ (PROBE)
# ============================================================================

class Probe:
    """Проверка доступности сайтов через DNS сервисов напрямую."""
    HOSTS = [
        "chatgpt.com",
        "claude.ai",
        "gemini.google.com",
        "elevenlabs.io",
        "grok.com",
        "www.perplexity.ai",
        "discord.com",
        "www.youtube.com",
        "www.roblox.com",
        "steamcommunity.com",
    ]
    LABELS = [
        "ChatGPT",
        "Claude",
        "Gemini",
        "ElevenLabs",
        "Grok",
        "Perplexity",
        "Discord",
        "YouTube",
        "Roblox",
        "Steam",
    ]
    RANKED = 6  # Первые 6 — нейросети, по ним выбирается «лучший» сервис

    OK = "открывается"
    BLOCKED = "блок страны"
    CAPTCHA = "капча Google"
    NO_LINK = "нет связи"
    NO_DNS = "DNS молчит"
    ZERO = "не пускает"

    QUERY_ID = 0x2A2A
    UA = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    @classmethod
    def build_dns_query(cls, host: str, qid: int = QUERY_ID) -> bytes:
        """Сборка RFC 1035 UDP пакета запроса A-записи."""
        header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)
        qname = bytearray()
        for part in host.split("."):
            encoded = part.encode("ascii")
            qname.append(len(encoded))
            qname.extend(encoded)
        qname.append(0)
        qtype_qclass = struct.pack(">HH", 1, 1)  # A, IN
        return header + bytes(qname) + qtype_qclass

    @classmethod
    def skip_name(cls, r: bytes, i: int) -> int:
        """Пропуск метки имени в DNS ответе с поддержкой сжатия (RFC 1035)."""
        while True:
            if i >= len(r):
                raise IndexError("DNS имя выходит за пределы пакета")
            b = r[i]
            if b == 0:
                return i + 1
            if (b & 0xC0) == 0xC0:
                return i + 2
            if (b & 0xC0) != 0:
                raise ValueError("Неизвестный тип метки DNS")
            i += b + 1

    @classmethod
    def parse_a(cls, r: bytes, expected_qid: int = QUERY_ID) -> Optional[str]:
        """
        Разбор первого IPv4 адреса из ответа DNS.
        Возвращает:
          - IPv4 адрес (строка)
          - "" если NXDOMAIN или пустой ответ
          - None если ответ битый, REFUSED или чужой ID
        """
        if len(r) < 12:
            return None
        qid, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", r[:12])
        if qid != expected_qid:
            return None
        if not (flags & 0x8000):  # Не ответ
            return None
        rcode = flags & 0x000F
        if rcode == 3:  # NXDOMAIN
            return ""
        if rcode != 0:  # REFUSED, SERVFAIL и т.д.
            return None

        try:
            i = 12
            for _ in range(qdcount):
                i = cls.skip_name(r, i) + 4
            for _ in range(ancount):
                i = cls.skip_name(r, i)
                if i + 10 > len(r):
                    return None
                rtype, rclass, _, rdlength = struct.unpack(">HHIH", r[i:i + 10])
                i += 10
                if rtype == 1 and rclass == 1 and rdlength == 4:
                    if i + 4 > len(r):
                        return None
                    return socket.inet_ntoa(r[i:i + 4])
                i += rdlength
            return ""
        except (IndexError, ValueError):
            return None

    @classmethod
    def resolve(cls, server: str, host: str) -> Optional[str]:
        """Отправка UDP DNS-запроса на указанный сервер с двумя попытками."""
        query_data = cls.build_dns_query(host)
        for _ in range(2):
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(2.5)
            try:
                sock.sendto(query_data, (server, 53))
                reply, _ = sock.recvfrom(4096)
                ip = cls.parse_a(reply)
                if ip is not None:
                    return ip
            except (OSError, socket.timeout):
                pass
            finally:
                sock.close()
        return None

    @classmethod
    def classify(cls, head: str) -> str:
        """Анализ HTTP-ответа: открывается, капча Google, блок страны."""
        if not head or head.startswith("000"):
            return cls.NO_LINK
        h = head.lower()
        if "/sorry/" in h:
            return cls.CAPTCHA
        if any(b in h for b in ["restrict", "unsupported", "unavailable", "not-available"]):
            return cls.BLOCKED
        return cls.OK

    @classmethod
    def verdict(cls, ip: Optional[str]) -> Optional[str]:
        """Вердикт по ответу DNS без перехода на сайт. None — нужно проверить HTTP."""
        if ip is None:
            return cls.NO_DNS
        if ip in ("", "0.0.0.0"):
            return cls.ZERO
        return None

    @classmethod
    def site(cls, host: str, ip: str) -> str:
        """Проверка доступности сайта по TLS через выданный IP-адрес."""
        is_dpi_target = DpiService.matches(host)
        if is_dpi_target:
            # Для Discord и YouTube применяем механизм обхода блокировок DPI (фрагментация TLS Client Hello на 8 байт)
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                incoming = ssl.MemoryBIO()
                outgoing = ssl.MemoryBIO()
                ss = ctx.wrap_bio(incoming, outgoing, server_hostname=host)
                try:
                    ss.do_handshake()
                except ssl.SSLWantReadError:
                    pass
                client_hello = outgoing.read()

                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.settimeout(6.0)
                sock.connect((ip, 443))

                # Split at 8 bytes
                sock.sendall(client_hello[:8])
                time.sleep(0.003)
                sock.sendall(client_hello[8:])

                while True:
                    try:
                        ss.do_handshake()
                        break
                    except ssl.SSLWantReadError:
                        data = sock.recv(4096)
                        if not data:
                            raise Exception("Connection closed")
                        incoming.write(data)
                    except ssl.SSLWantWriteError:
                        sock.sendall(outgoing.read())

                req = (
                    f"GET / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {cls.UA}\r\n"
                    "Accept: text/html\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                ss.write(req)
                sock.sendall(outgoing.read())

                resp = bytearray()
                while len(resp) < 16384:
                    try:
                        chunk = ss.read(4096)
                        if chunk:
                            resp.extend(chunk)
                            if b"\r\n\r\n" in resp:
                                break
                    except ssl.SSLWantReadError:
                        data = sock.recv(4096)
                        if not data:
                            break
                        incoming.write(data)
                sock.close()
                return cls.classify(resp.decode("latin1", errors="ignore"))
            except Exception:
                return cls.NO_LINK

        # Обычные сайты (нейросети): попытка curl, затем сокеты
        try:
            res = subprocess.run(
                [
                    "curl", "-s", "-o", "/dev/null", "-m", "8", "--noproxy", "*",
                    "-A", cls.UA, "--resolve", f"{host}:443:{ip}",
                    "-w", "%{http_code} %{redirect_url}", f"https://{host}/"
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=10,
            )
            out = res.stdout.strip()
            if out and not out.startswith("000"):
                return cls.classify(out)
        except Exception:
            pass

        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(6.0)
            sock.connect((ip, 443))
            with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                req = (
                    f"GET / HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {cls.UA}\r\n"
                    "Accept: text/html\r\nConnection: close\r\n\r\n"
                ).encode("ascii")
                ssock.sendall(req)
                resp = bytearray()
                while len(resp) < 16384:
                    chunk = ssock.recv(4096)
                    if not chunk:
                        break
                    resp.extend(chunk)
                    if b"\r\n\r\n" in resp:
                        break
                return cls.classify(resp.decode("latin1", errors="ignore"))
        except Exception:
            return cls.NO_LINK

    @classmethod
    def check_service(cls, set_idx: int) -> List[str]:
        """Параллельная проверка всех 8 сайтов для сервиса."""
        results = [cls.NO_DNS] * len(cls.HOSTS)
        threads = []

        def worker(idx: int):
            h = cls.HOSTS[idx]
            ip = None
            for srv in Services.V4[set_idx]:
                ip = cls.resolve(srv, h)
                if ip is not None:
                    break
            v = cls.verdict(ip)
            if v is not None:
                results[idx] = v
            else:
                results[idx] = cls.site(h, ip)

        for i in range(len(cls.HOSTS)):
            t = threading.Thread(target=worker, args=(i,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=15.0)

        return results

    @classmethod
    def good(cls, res: Optional[List[str]]) -> int:
        """Количество открывшихся сайтов среди нейросетей (первые 6)."""
        if res is None:
            return -1
        return sum(1 for x in res[:cls.RANKED] if x == cls.OK)

    @classmethod
    def best(cls, all_results: List[Optional[List[str]]], current: int = -1) -> int:
        """
        Сервис, где открылось больше всего нейросетей.
        При равенстве остаётся текущий (если он среди проверенных);
        Discord и YouTube на выбор не влияют.
        """
        best_idx = current if (0 <= current < len(all_results) and all_results[current] is not None) else 0
        for k in range(len(all_results)):
            if cls.good(all_results[k]) > cls.good(all_results[best_idx]):
                best_idx = k
        return best_idx


# ============================================================================
# УПРАВЛЕНИЕ СЕТЬЮ В LINUX
# ============================================================================

# ============================================================================
# ОБХОД БЛОКИРОВОК DPI (Zapret / GoodbyeDPI)
# ============================================================================

class DpiService:
    """Локальный сервис обхода DPI (GoodbyeDPI / Zapret):
    Поднимает HTTP CONNECT + SOCKS5 прокси на 127.0.0.1:2080 и раздаёт PAC-скрипт.
    Фрагментирует пакеты Client Hello для YouTube и Discord.
    """
    DEFAULT_PORT = 2080
    port = DEFAULT_PORT
    _server_sock: Optional[socket.socket] = None
    _running = False
    _thread: Optional[threading.Thread] = None

    BYPASS_DOMAINS = [
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
        "notion.so", "notion.site",
    ]

    @classmethod
    def matches(cls, host: str) -> bool:
        if not host:
            return False
        h = host.lower()
        for d in cls.BYPASS_DOMAINS:
            if h == d or h.endswith("." + d):
                return True
        return False

    @classmethod
    def pac_script(cls, p: int) -> str:
        domains_js = json.dumps(cls.BYPASS_DOMAINS)
        return (
            "function FindProxyForURL(url, host) {\n"
            f"  var d = {domains_js};\n"
            "  for (var i = 0; i < d.length; i++) {\n"
            "    if (host === d[i] || dnsDomainIs(host, '.' + d[i])) {\n"
            f"      return 'PROXY 127.0.0.1:{p}; SOCKS5 127.0.0.1:{p}; DIRECT';\n"
            "    }\n"
            "  }\n"
            "  return 'DIRECT';\n"
            "}\n"
        )

    @classmethod
    def enable_system_proxy(cls, pac_url: str) -> None:
        """Настройка автопрокси (PAC) для рабочего окружения GNOME/KDE."""
        try:
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "auto"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "autoconfig-url", pac_url],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass

    @classmethod
    def disable_system_proxy(cls) -> None:
        """Сброс настроек автопрокси в системе."""
        try:
            subprocess.run(["gsettings", "set", "org.gnome.system.proxy", "mode", "none"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
            subprocess.run(["gsettings", "reset", "org.gnome.system.proxy", "autoconfig-url"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except Exception:
            pass

    @classmethod
    def is_running(cls) -> bool:
        return cls._running

    @classmethod
    def start(cls) -> bool:
        if cls._running:
            return True
        for p in range(cls.DEFAULT_PORT, cls.DEFAULT_PORT + 10):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("127.0.0.1", p))
                s.listen(50)
                cls._server_sock = s
                cls.port = p
                cls._running = True
                cls._thread = threading.Thread(target=cls._serve, daemon=True)
                cls._thread.start()
                cls.enable_system_proxy(f"http://127.0.0.1:{p}/proxy.pac")
                return True
            except Exception:
                continue
        return False

    @classmethod
    def stop(cls) -> None:
        cls._running = False
        cls.disable_system_proxy()
        if cls._server_sock:
            try:
                cls._server_sock.close()
            except Exception:
                pass
            cls._server_sock = None

    @classmethod
    def _serve(cls) -> None:
        while cls._running and cls._server_sock:
            try:
                cs, _ = cls._server_sock.accept()
                threading.Thread(target=cls._handle_client, args=(cs,), daemon=True).start()
            except Exception:
                break

    @classmethod
    def _handle_client(cls, client: socket.socket) -> None:
        try:
            client.settimeout(6.0)
            buf = client.recv(4096)
            if not buf:
                client.close()
                return

            # 1. PAC Request
            if buf.startswith(b"GET ") and (b"/proxy.pac" in buf or b"/pac" in buf or (b"HTTP/" in buf and buf.split(b" ")[1] == b"/")):
                pac = cls.pac_script(cls.port).encode("utf-8")
                resp = (
                    b"HTTP/1.1 200 OK\r\nContent-Type: application/x-ns-proxy-autoconfig\r\n"
                    b"Connection: close\r\n\r\n" + pac
                )
                client.sendall(resp)
                client.close()
                return

            # 2. HTTP CONNECT
            if buf.startswith(b"CONNECT "):
                parts = buf.split(b" ")
                if len(parts) > 1:
                    target = parts[1].decode("ascii", errors="ignore").split(":")
                    host = target[0]
                    port = int(target[1]) if len(target) > 1 else 443

                    upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    upstream.settimeout(8.0)
                    upstream.connect((host, port))

                    client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")

                    payload = client.recv(16384)
                    if payload:
                        if len(payload) > 12 and payload[0] == 0x16 and payload[1] == 0x03:
                            upstream.sendall(payload[:8])
                            time.sleep(0.003)
                            upstream.sendall(payload[8:])
                        else:
                            upstream.sendall(payload)

                    cls._pipe(client, upstream)
                    return

            # 3. SOCKS5
            if buf[0] == 0x05:
                client.sendall(b"\x05\x00")
                nreq = client.recv(4096)
                if len(nreq) > 6 and nreq[0] == 0x05 and nreq[1] == 0x01:
                    atyp = nreq[3]
                    host = None
                    port = 0
                    if atyp == 0x01 and len(nreq) >= 10:
                        host = socket.inet_ntoa(nreq[4:8])
                        port = struct.unpack(">H", nreq[8:10])[0]
                    elif atyp == 0x03 and len(nreq) >= 7:
                        dlen = nreq[4]
                        if len(nreq) >= 5 + dlen + 2:
                            host = nreq[5:5 + dlen].decode("ascii", errors="ignore")
                            port = struct.unpack(">H", nreq[5 + dlen:5 + dlen + 2])[0]
                    if host and port:
                        upstream = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        upstream.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                        upstream.settimeout(8.0)
                        upstream.connect((host, port))
                        client.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")

                        payload = client.recv(16384)
                        if payload:
                            if len(payload) > 12 and payload[0] == 0x16 and payload[1] == 0x03:
                                upstream.sendall(payload[:8])
                                time.sleep(0.003)
                                upstream.sendall(payload[8:])
                            else:
                                upstream.sendall(payload)

                        cls._pipe(client, upstream)
                        return

            client.close()
        except Exception:
            try:
                client.close()
            except Exception:
                pass

    @classmethod
    def _pipe(cls, s1: socket.socket, s2: socket.socket) -> None:
        def fwd(src, dst):
            try:
                while True:
                    d = src.recv(32768)
                    if not d:
                        break
                    dst.sendall(d)
            except Exception:
                pass
            finally:
                try: dst.shutdown(socket.SHUT_WR)
                except Exception: pass
                try: src.close()
                except Exception: pass
                try: dst.close()
                except Exception: pass

        t1 = threading.Thread(target=fwd, args=(s1, s2), daemon=True)
        t2 = threading.Thread(target=fwd, args=(s2, s1), daemon=True)
        t1.start()
        t2.start()

class LinuxNet:
    """Управление DNS и IPv6 на Linux."""

    CONF_BACKUP = "/var/lib/hb-ai-smart-dns/resolv.conf.backup"
    IPV6_OFF_FILE = "/var/lib/hb-ai-smart-dns/ipv6-off.txt"
    USER_IPV6_OFF_FILE = os.path.expanduser("~/.local/share/hb-ai-smart-dns/ipv6-off.txt")

    @classmethod
    def enable_proxy(cls, pac_url: str) -> None:
        DpiService.enable_system_proxy(pac_url)

    @classmethod
    def disable_proxy(cls) -> None:
        DpiService.disable_system_proxy()

    @classmethod
    def get_ipv6_off_file(cls) -> str:
        """Путь к файлу отключённых интерфейсов IPv6."""
        if os.geteuid() == 0:
            os.makedirs(os.path.dirname(cls.CONF_BACKUP), exist_ok=True)
            return cls.IPV6_OFF_FILE
        os.makedirs(os.path.dirname(cls.USER_IPV6_OFF_FILE), exist_ok=True)
        return cls.USER_IPV6_OFF_FILE

    @classmethod
    def is_root(cls) -> bool:
        """Запущен ли процесс с правами root."""
        return hasattr(os, "geteuid") and os.geteuid() == 0

    @classmethod
    def run_cmd(cls, cmd: List[str]) -> Tuple[int, str]:
        """Выполнение команды с возвратом кода и вывода."""
        try:
            res = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=12,
            )
            return res.returncode, res.stdout.strip()
        except Exception as e:
            return -1, str(e)

    @classmethod
    def get_active_interfaces(cls) -> List[str]:
        """Список активных сетевых интерфейсов (исключая loopback, docker, veth и т.п.)."""
        interfaces = []
        # Чтение /sys/class/net
        sys_net = "/sys/class/net"
        if os.path.isdir(sys_net):
            for name in os.listdir(sys_net):
                if name == "lo" or any(name.startswith(p) for p in ["docker", "veth", "br-", "virbr", "tun", "tap", "wg"]):
                    continue
                operstate_file = os.path.join(sys_net, name, "operstate")
                if os.path.isfile(operstate_file):
                    try:
                        with open(operstate_file, "r") as f:
                            if f.read().strip() == "up":
                                interfaces.append(name)
                                continue
                    except OSError:
                        pass
                interfaces.append(name)
        if not interfaces:
            # Запасной вариант через ip link
            code, out = cls.run_cmd(["ip", "-o", "link", "show", "up"])
            if code == 0:
                for line in out.splitlines():
                    parts = line.split(":")
                    if len(parts) >= 2:
                        dev = parts[1].strip()
                        if dev != "lo" and not any(dev.startswith(p) for p in ["docker", "veth", "tun", "wg"]):
                            interfaces.append(dev)
        return list(dict.fromkeys(interfaces))

    @classmethod
    def get_current_dns_servers(cls) -> List[str]:
        """Получение списка текущих активных серверов DNS."""
        servers = []
        # 1. Попытка через resolvectl dns
        code, out = cls.run_cmd(["resolvectl", "dns"])
        if code == 0 and out:
            for line in out.splitlines():
                if ":" in line:
                    _, ips = line.split(":", 1)
                    for ip in ips.split():
                        if ip and ip not in servers:
                            servers.append(ip)
            if servers:
                return servers

        # 2. Попытка через nmcli dev show
        code, out = cls.run_cmd(["nmcli", "dev", "show"])
        if code == 0 and out:
            for line in out.splitlines():
                if "IP4.DNS" in line or "IP6.DNS" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        ip = parts[1].strip()
                        if ip and ip not in servers:
                            servers.append(ip)
            if servers:
                return servers

        # 3. Чтение /etc/resolv.conf
        if os.path.isfile("/etc/resolv.conf"):
            try:
                with open("/etc/resolv.conf", "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("nameserver"):
                            parts = line.split()
                            if len(parts) >= 2:
                                ip = parts[1].strip()
                                if ip and ip not in servers:
                                    servers.append(ip)
            except OSError:
                pass
        return servers

    @classmethod
    def active_set(cls) -> int:
        """Номер активного сервиса (0..3) или -1, если Smart DNS не включён."""
        for srv in cls.get_current_dns_servers():
            idx = Services.set_of(srv)
            if idx is not None:
                return idx
        return -1

    @classmethod
    def has_stale(cls) -> bool:
        """Стоят ли в системе устаревшие нерабочие адреса."""
        for srv in cls.get_current_dns_servers():
            if Services.is_stale(srv):
                return True
        return False

    @classmethod
    def has_ipv6(cls, iface: str) -> bool:
        """Есть ли у интерфейса глобальный IPv6 адрес."""
        code, out = cls.run_cmd(["ip", "-6", "addr", "show", "dev", iface, "scope", "global"])
        return code == 0 and "inet6" in out

    @classmethod
    def set_ipv6(cls, iface: str, enable: bool) -> bool:
        """Включение или выключение IPv6 на интерфейсе."""
        val = "0" if enable else "1"
        code, _ = cls.run_cmd(["sysctl", "-w", f"net.ipv6.conf.{iface}.disable_ipv6={val}"])
        if code == 0:
            return True
        # Прямая запись в /proc
        proc_path = f"/proc/sys/net/ipv6/conf/{iface}/disable_ipv6"
        if os.path.isfile(proc_path):
            try:
                with open(proc_path, "w") as f:
                    f.write(val)
                return True
            except OSError:
                pass
        return False

    @classmethod
    def read_ipv6_off_list(cls) -> List[str]:
        fpath = cls.get_ipv6_off_file()
        if os.path.isfile(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    return [line.strip() for line in f if line.strip()]
            except OSError:
                pass
        return []

    @classmethod
    def write_ipv6_off_list(cls, ifaces: List[str]):
        fpath = cls.get_ipv6_off_file()
        if not ifaces:
            if os.path.isfile(fpath):
                try:
                    os.remove(fpath)
                except OSError:
                    pass
            return
        try:
            with open(fpath, "w", encoding="utf-8") as f:
                for iface in ifaces:
                    f.write(f"{iface}\n")
        except OSError:
            pass

    @classmethod
    def restore_ipv6(cls) -> List[str]:
        """Восстановление IPv6 на ранее отключённых интерфейсах."""
        off_list = cls.read_ipv6_off_list()
        left = []
        for iface in off_list:
            ok = cls.set_ipv6(iface, True)
            if not ok:
                left.append(iface)
        cls.write_ipv6_off_list(left)
        return left

    @classmethod
    def flush_cache(cls):
        """Сброс кэша DNS."""
        cls.run_cmd(["resolvectl", "flush-caches"])
        cls.run_cmd(["systemd-resolve", "--flush-caches"])
        cls.run_cmd(["nscd", "-i", "hosts"])

    @classmethod
    def enable(cls, set_idx: int) -> Tuple[bool, str]:
        """Включение Smart DNS."""
        if not cls.is_root():
            return False, "Для изменения DNS требуются права root (запустите с sudo)"

        errors = []
        v4_servers = Services.V4[set_idx]
        v6_servers = Services.V6[set_idx]
        has_own_v6 = len(v6_servers) > 0
        all_servers = v4_servers + v6_servers

        interfaces = cls.get_active_interfaces()
        off_list = cls.read_ipv6_off_list()

        # 1. Попытка через systemd-resolved (resolvectl)
        resolved_applied = False
        code, _ = cls.run_cmd(["resolvectl", "--version"])
        if code == 0:
            for iface in interfaces:
                c1, o1 = cls.run_cmd(["resolvectl", "dns", iface] + all_servers)
                cls.run_cmd(["resolvectl", "domain", iface, "~."])
                if c1 == 0:
                    resolved_applied = True
                else:
                    errors.append(f"resolvectl {iface}: {o1}")

        # 2. Попытка через NetworkManager (nmcli)
        nm_applied = False
        code, _ = cls.run_cmd(["nmcli", "--version"])
        if code == 0:
            code_c, out_c = cls.run_cmd(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
            if code_c == 0:
                for line in out_c.splitlines():
                    if ":" in line:
                        conn_name = line.split(":", 1)[0]
                        c1, _ = cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv4.dns", " ".join(v4_servers)])
                        cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv4.ignore-auto-dns", "yes"])
                        if has_own_v6:
                            cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv6.dns", " ".join(v6_servers)])
                            cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv6.ignore-auto-dns", "yes"])
                        cls.run_cmd(["nmcli", "connection", "up", conn_name])
                        if c1 == 0:
                            nm_applied = True

        # 3. Запасной вариант: прямое редактирование /etc/resolv.conf
        if not resolved_applied and not nm_applied:
            try:
                if not os.path.exists(cls.CONF_BACKUP) and os.path.exists("/etc/resolv.conf"):
                    with open("/etc/resolv.conf", "r", encoding="utf-8") as rf:
                        with open(cls.CONF_BACKUP, "w", encoding="utf-8") as wf:
                            wf.write(rf.read())
                with open("/etc/resolv.conf", "w", encoding="utf-8") as f:
                    f.write("# Managed by HB AI Smart DNS\n")
                    for s in all_servers:
                        f.write(f"nameserver {s}\n")
            except Exception as e:
                errors.append(f"/etc/resolv.conf: {e}")

        # Управление IPv6
        if not has_own_v6:
            for iface in interfaces:
                if cls.has_ipv6(iface):
                    if iface not in off_list:
                        off_list.append(iface)
                    cls.set_ipv6(iface, False)
            cls.write_ipv6_off_list(off_list)
        else:
            cls.restore_ipv6()

        cls.flush_cache()
        if errors and not (resolved_applied or nm_applied):
            return False, "\n".join(errors)
        return True, ""

    @classmethod
    def disable(cls) -> Tuple[bool, str]:
        """Выключение Smart DNS и возврат к настройкам по умолчанию."""
        if not cls.is_root():
            return False, "Для изменения DNS требуются права root (запустите с sudo)"

        errors = []
        interfaces = cls.get_active_interfaces()

        # 1. resolvectl revert
        code, _ = cls.run_cmd(["resolvectl", "--version"])
        if code == 0:
            for iface in interfaces:
                cls.run_cmd(["resolvectl", "revert", iface])

        # 2. nmcli revert
        code, _ = cls.run_cmd(["nmcli", "--version"])
        if code == 0:
            code_c, out_c = cls.run_cmd(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"])
            if code_c == 0:
                for conn_name in out_c.splitlines():
                    conn_name = conn_name.strip()
                    if conn_name:
                        cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv4.dns", ""])
                        cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv4.ignore-auto-dns", "no"])
                        cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv6.dns", ""])
                        cls.run_cmd(["nmcli", "connection", "modify", conn_name, "ipv6.ignore-auto-dns", "no"])
                        cls.run_cmd(["nmcli", "connection", "up", conn_name])

        # 3. Восстановление /etc/resolv.conf
        if os.path.exists(cls.CONF_BACKUP):
            try:
                with open(cls.CONF_BACKUP, "r", encoding="utf-8") as rf:
                    with open("/etc/resolv.conf", "w", encoding="utf-8") as wf:
                        wf.write(rf.read())
                os.remove(cls.CONF_BACKUP)
            except Exception as e:
                errors.append(f"resolv.conf restore: {e}")

        # Включение IPv6 обратно
        cls.restore_ipv6()
        cls.flush_cache()
        if errors:
            return False, "\n".join(errors)
        return True, ""


# ============================================================================
# ПРОВЕРКА ОБНОВЛЕНИЙ
# ============================================================================

class Updates:
    """Проверка новых версий на GitHub."""

    @classmethod
    def check_latest(cls) -> Optional[str]:
        """Возвращает номер последней версии (например '1.24'), если она новее текущей."""
        url = "https://api.github.com/repos/animesao/hb-ai-xbox-dns/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "HB-AI-SmartDNS-Linux"})
        try:
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                tag = data.get("tag_name", "").lstrip("v").strip()
                if tag and cls.is_newer(tag, VERSION):
                    return tag
        except Exception:
            pass
        return None

    @classmethod
    def is_newer(cls, candidate: str, current: str) -> bool:
        """Сравнение версий как десятичных дробей (1.21 < 1.22 < 1.3), как в Windows и Mac."""
        try:
            from decimal import Decimal
            if not all(c in "0123456789." for c in candidate):
                return False
            if not all(c in "0123456789." for c in current):
                return False
            return Decimal(candidate) > Decimal(current)
        except Exception:
            return False


# ============================================================================
# ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (TKINTER)
# ============================================================================

def run_gui():
    """Запуск графического интерфейса Tkinter с тёмной темой."""
    import tkinter as tk
    from tkinter import messagebox

    # Цветовая палитра HB AI Dark
    BG = "#07070b"
    CARD_BG = "#13131d"
    CARD_BORDER = "#232332"
    TEXT_LIGHT = "#f0f0f5"
    TEXT_MUTED = "#9090aa"
    VIOLET = "#8c70ff"
    VIOLET_HOVER = "#7556f0"
    GREEN = "#22c55e"
    GREEN_HOVER = "#16a34a"
    RED = "#ef4444"
    YELLOW = "#f59e0b"

    root = tk.Tk()
    root.title(f"HB AI · Smart DNS {VERSION}")
    root.geometry("450x880")
    root.configure(bg=BG)
    root.resizable(False, False)

    # Иконка
    icon_path = os.path.join(os.path.dirname(__file__), "res", "icon.png")
    if os.path.exists(icon_path):
        try:
            img = tk.PhotoImage(file=icon_path)
            root.iconphoto(False, img)
        except Exception:
            pass

    selected_set = tk.IntVar(value=0)
    current_active = LinuxNet.active_set()
    if current_active >= 0:
        selected_set.set(current_active)

    probe_results: List[Optional[str]] = [None] * len(Probe.HOSTS)
    checking = tk.BooleanVar(value=False)
    update_version: List[Optional[str]] = [None]

    # --- ЗАГОЛОВОК ---
    header_frame = tk.Frame(root, bg=BG)
    header_frame.pack(fill="x", padx=24, pady=(20, 10))

    title_label = tk.Label(
        header_frame,
        text="HB AI · Smart DNS",
        font=("Helvetica", 18, "bold"),
        fg=TEXT_LIGHT,
        bg=BG,
    )
    title_label.pack(side="left")

    ver_badge = tk.Label(
        header_frame,
        text=f"v{VERSION}",
        font=("Helvetica", 9, "bold"),
        fg=VIOLET,
        bg="#1e1838",
        padx=8,
        pady=2,
    )
    ver_badge.pack(side="right")

    sub_label = tk.Label(
        root,
        text="ChatGPT, Claude, Gemini, ElevenLabs, Discord, YouTube, Roblox...",
        font=("Helvetica", 10),
        fg=TEXT_MUTED,
        bg=BG,
    )
    sub_label.pack(anchor="w", padx=24, pady=(0, 16))

    # --- КАРТОЧКА ГЛАВНОГО ПЕРЕКЛЮЧАТЕЛЯ ---
    toggle_card = tk.Frame(root, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
    toggle_card.pack(fill="x", padx=24, pady=8)

    status_str = tk.StringVar()

    def update_status_text():
        act = LinuxNet.active_set()
        if act >= 0:
            status_str.set(f"Включён: {Services.NAME[act]}")
            toggle_btn.config(
                text="Выключить Smart DNS",
                bg=GREEN,
                activebackground=GREEN_HOVER,
            )
        elif LinuxNet.has_stale():
            status_str.set("Стоят старые адреса DNS (нажмите для исправления)")
            toggle_btn.config(
                text="Поставить рабочий DNS",
                bg=YELLOW,
                activebackground="#d97706",
            )
        else:
            status_str.set("DNS выключен: автоматический от роутера")
            toggle_btn.config(
                text="Включить Smart DNS",
                bg=VIOLET,
                activebackground=VIOLET_HOVER,
            )

    status_display = tk.Label(
        toggle_card,
        textvariable=status_str,
        font=("Helvetica", 11, "bold"),
        fg=TEXT_LIGHT,
        bg=CARD_BG,
    )
    status_display.pack(pady=(16, 10))

    def on_toggle():
        if not LinuxNet.is_root():
            # Попытка перезапуска с pkexec
            msg = "Для изменения настроек сети требуются права администратора.\nПерезапустить программу с правами root?"
            if messagebox.askyesno("Требуются права root", msg):
                root.destroy()
                script = os.path.abspath(__file__)
                cmd = ["pkexec", sys.executable, script]
                subprocess.Popen(cmd)
                sys.exit(0)
            return

        act = LinuxNet.active_set()
        if act >= 0:
            ok, err = LinuxNet.disable()
            if not ok:
                messagebox.showerror("Ошибка выключения", err)
        else:
            s_idx = selected_set.get()
            ok, err = LinuxNet.enable(s_idx)
            if not ok:
                messagebox.showerror("Ошибка включения", err)
            else:
                run_check(s_idx)
        update_status_text()

    toggle_btn = tk.Button(
        toggle_card,
        text="Включить Smart DNS",
        font=("Helvetica", 13, "bold"),
        fg="#ffffff",
        bg=VIOLET,
        activeforeground="#ffffff",
        activebackground=VIOLET_HOVER,
        relief="flat",
        cursor="hand2",
        command=on_toggle,
        padx=20,
        pady=12,
    )
    toggle_btn.pack(fill="x", padx=20, pady=(0, 16))

    # --- ВЫБОР СЕРВИСА ---
    srv_card = tk.Frame(root, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
    srv_card.pack(fill="x", padx=24, pady=8)

    srv_title = tk.Label(
        srv_card,
        text="ВЫБОР СЕРВИСА SMART DNS",
        font=("Helvetica", 9, "bold"),
        fg=TEXT_MUTED,
        bg=CARD_BG,
    )
    srv_title.pack(anchor="w", padx=16, pady=(12, 8))

    btn_grid = tk.Frame(srv_card, bg=CARD_BG)
    btn_grid.pack(fill="x", padx=16, pady=4)

    srv_buttons = []
    desc_str = tk.StringVar()

    def update_service_desc():
        idx = selected_set.get()
        desc_str.set(Services.OPENS[idx])
        for i, b in enumerate(srv_buttons):
            if i == idx:
                b.config(bg="#2d244c", fg=VIOLET, highlightbackground=VIOLET)
            else:
                b.config(bg="#1a1a27", fg=TEXT_MUTED, highlightbackground=CARD_BORDER)

    def select_service(i):
        selected_set.set(i)
        update_service_desc()
        act = LinuxNet.active_set()
        if act >= 0 and act != i and LinuxNet.is_root():
            LinuxNet.enable(i)
            update_status_text()
            run_check(i)

    for i in range(Services.count()):
        b = tk.Button(
            btn_grid,
            text=Services.SHORT[i],
            font=("Helvetica", 10, "bold"),
            relief="flat",
            cursor="hand2",
            padx=10,
            pady=8,
            command=lambda x=i: select_service(x),
        )
        b.grid(row=0, column=i, sticky="ew", padx=3)
        btn_grid.columnconfigure(i, weight=1)
        srv_buttons.append(b)

    desc_label = tk.Label(
        srv_card,
        textvariable=desc_str,
        font=("Helvetica", 9),
        fg=TEXT_MUTED,
        bg=CARD_BG,
        wraplength=380,
        justify="left",
    )
    desc_label.pack(anchor="w", padx=16, pady=(8, 14))

    # --- КАРТОЧКА ПРОВЕРКИ (PROBE) ---
    probe_card = tk.Frame(root, bg=CARD_BG, highlightbackground=CARD_BORDER, highlightthickness=1)
    probe_card.pack(fill="x", padx=24, pady=8)

    probe_top = tk.Frame(probe_card, bg=CARD_BG)
    probe_top.pack(fill="x", padx=16, pady=(12, 10))

    check_btn_str = tk.StringVar(value="Проверить")
    best_btn_str = tk.StringVar(value="Найти лучший")

    check_btn = tk.Button(
        probe_top,
        textvariable=check_btn_str,
        font=("Helvetica", 9, "bold"),
        fg=TEXT_LIGHT,
        bg="#222233",
        activebackground="#333348",
        relief="flat",
        cursor="hand2",
        padx=12,
        pady=6,
        command=lambda: run_check(selected_set.get()),
    )
    check_btn.pack(side="left")

    best_btn = tk.Button(
        probe_top,
        textvariable=best_btn_str,
        font=("Helvetica", 9, "bold"),
        fg=TEXT_LIGHT,
        bg="#222233",
        activebackground="#333348",
        relief="flat",
        cursor="hand2",
        padx=12,
        pady=6,
        command=lambda: run_best(),
    )
    best_btn.pack(side="right")

    sites_grid = tk.Frame(probe_card, bg=CARD_BG)
    sites_grid.pack(fill="x", padx=16, pady=(4, 16))

    site_dots = []
    site_texts = []

    # 2 колонки по 5 строк
    # [ChatGPT, Claude, Gemini, ElevenLabs, Grok], [Perplexity, Discord, YouTube, Roblox, Steam]
    for i in range(len(Probe.HOSTS)):
        col = i // 5
        row = i % 5
        cell = tk.Frame(sites_grid, bg=CARD_BG)
        cell.grid(row=row, column=col, sticky="w", padx=4, pady=3)
        sites_grid.columnconfigure(col, weight=1)

        dot = tk.Canvas(cell, width=8, height=8, bg=CARD_BG, highlightthickness=0)
        dot_id = dot.create_oval(0, 0, 7, 7, fill="#464658", outline="")
        dot.pack(side="left", padx=(0, 4))
        site_dots.append((dot, dot_id))

        lbl = tk.Label(
            cell,
            text=Probe.LABELS[i],
            font=("Helvetica", 8, "bold"),
            fg=TEXT_LIGHT,
            bg=CARD_BG,
        )
        lbl.pack(side="left")
        site_texts.append(lbl)

    def update_probe_ui():
        for i, res in enumerate(probe_results):
            dot, dot_id = site_dots[i]
            if res is None:
                color = "#464658"
            elif res == Probe.OK:
                color = GREEN
            elif res == Probe.CAPTCHA:
                color = YELLOW
            else:
                color = RED
            dot.itemconfig(dot_id, fill=color)

    def run_check(s_idx: int):
        if checking.get():
            return
        checking.set(True)
        check_btn_str.set("Проверяем…")
        check_btn.config(state="disabled")
        best_btn.config(state="disabled")

        def task():
            res = Probe.check_service(s_idx)
            for i, r in enumerate(res):
                probe_results[i] = r
            root.after(0, finish)

        def finish():
            update_probe_ui()
            check_btn_str.set("Проверить")
            check_btn.config(state="normal")
            best_btn.config(state="normal")
            checking.set(False)

        threading.Thread(target=task, daemon=True).start()

    def run_best():
        if checking.get():
            return
        checking.set(True)
        best_btn_str.set("Ищем…")
        check_btn.config(state="disabled")
        best_btn.config(state="disabled")

        def task():
            all_res = []
            for k in range(Services.count()):
                if k == Services.XBOX_SET:
                    all_res.append(None)
                else:
                    all_res.append(Probe.check_service(k))
            best_k = Probe.best(all_res, current=selected_set.get())
            for i, r in enumerate(all_res[best_k] or []):
                probe_results[i] = r
            root.after(0, lambda: finish(best_k))

        def finish(best_k: int):
            selected_set.set(best_k)
            update_service_desc()
            update_probe_ui()
            act = LinuxNet.active_set()
            if act >= 0 and LinuxNet.is_root():
                LinuxNet.enable(best_k)
                update_status_text()
            best_btn_str.set("Найти лучший")
            check_btn.config(state="normal")
            best_btn.config(state="normal")
            checking.set(False)

        threading.Thread(target=task, daemon=True).start()

    # --- БАННЕР ОБНОВЛЕНИЯ ---
    update_btn = tk.Button(
        root,
        text="Доступна новая версия",
        font=("Helvetica", 10, "bold"),
        fg="#000000",
        bg=YELLOW,
        activebackground="#d97706",
        relief="flat",
        cursor="hand2",
        command=lambda: webbrowser.open(f"{REPO_URL}/releases/latest"),
    )

    def check_updates_async():
        new_v = Updates.check_latest()
        if new_v:
            update_version[0] = new_v
            root.after(0, lambda: show_update(new_v))

    def show_update(ver: str):
        update_btn.config(text=f"Скачать версию {ver}  →")
        update_btn.pack(fill="x", padx=24, pady=8, before=footer_frame)

    # --- ПОДВАЛ И СООБЩЕСТВО ---
    footer_frame = tk.Frame(root, bg=BG)
    footer_frame.pack(fill="x", padx=24, pady=(16, 20), side="bottom")

    vk_btn = tk.Button(
        footer_frame,
        text="Наша группа ВКонтакте  →",
        font=("Helvetica", 10, "bold"),
        fg=TEXT_LIGHT,
        bg="#272738",
        activebackground="#35354e",
        relief="flat",
        cursor="hand2",
        pady=8,
        command=lambda: webbrowser.open(VK_URL),
    )
    vk_btn.pack(fill="x", pady=(0, 10))

    brand_lbl = tk.Label(
        footer_frame,
        text="HB AI",
        font=("Helvetica", 12, "bold"),
        fg=VIOLET,
        bg=BG,
    )
    brand_lbl.pack(side="left")

    site_link = tk.Label(
        footer_frame,
        text="vk.com/neiroseti_ai",
        font=("Helvetica", 9),
        fg=TEXT_MUTED,
        bg=BG,
        cursor="hand2",
    )
    site_link.pack(side="right")
    site_link.bind("<Button-1>", lambda e: webbrowser.open(VK_URL))

    update_status_text()
    update_service_desc()
    threading.Thread(target=check_updates_async, daemon=True).start()

    root.mainloop()


# ============================================================================
# РАБОТА ИЗ КОНСОЛИ (CLI)
# ============================================================================

def run_cli_check(target_service: Optional[int] = None):
    """Вывод проверки в консоль."""
    if target_service is None:
        target_service = LinuxNet.active_set()
        if target_service < 0:
            target_service = 0

    print(f"\nПроверка серверов {Services.NAME[target_service]}...")
    res = Probe.check_service(target_service)
    print("------------------------------------------------------------")
    for i in range(len(Probe.HOSTS)):
        status = res[i]
        tag = "[ OK ]" if status == Probe.OK else "[CAPT]" if status == Probe.CAPTCHA else "[FAIL]"
        print(f"  {tag:6} {Probe.LABELS[i]:14} : {status}")
    print("------------------------------------------------------------")
    good_cnt = Probe.good(res)
    print(f"Итог: открывается {good_cnt} из {Probe.RANKED} нейросетей.\n")


def run_cli_best():
    """Поиск лучшего сервиса через CLI."""
    print("\nПоиск лучшего сервиса среди всех Smart DNS...")
    all_res = []
    for k in range(Services.count()):
        if k == Services.XBOX_SET:
            all_res.append(None)
            print(f"  [--] {Services.NAME[k]:14} : Xbox Live (пропущен)")
        else:
            r = Probe.check_service(k)
            all_res.append(r)
            cnt = Probe.good(r)
            print(f"  [OK] {Services.NAME[k]:14} : {cnt} из {Probe.RANKED} нейросетей открыто")

    best_idx = Probe.best(all_res, current=LinuxNet.active_set())
    print(f"\nРекомендованный сервис: {Services.NAME[best_idx]}")
    if LinuxNet.is_root():
        print(f"Включаем {Services.NAME[best_idx]}...")
        ok, err = LinuxNet.enable(best_idx)
        if ok:
            print("Успешно включено!")
        else:
            print(f"Ошибка: {err}")
    else:
        print(f"Для включения выполните: sudo hb-ai-smart-dns --enable {Services.SHORT[best_idx].lower()}")


def print_status():
    """Вывод текущего статуса DNS."""
    act = LinuxNet.active_set()
    current_dns = LinuxNet.get_current_dns_servers()
    stale = LinuxNet.has_stale()
    off_ipv6 = LinuxNet.read_ipv6_off_list()

    print("============================================================")
    print(f" HB AI · Smart DNS v{VERSION} (Linux)")
    print("============================================================")
    if act >= 0:
        print(f" Статус:      ВКЛЮЧЁН ({Services.NAME[act]})")
        print(f" Открывает:   {Services.OPENS[act]}")
    elif stale:
        print(" Статус:      ВНИМАНИЕ: Стоят устаревшие нерабочие адреса DNS!")
    else:
        print(" Статус:      ВЫКЛЮЧЕН (обычный DNS от роутера / провайдера)")

    print(f" Текущие DNS: {', '.join(current_dns) if current_dns else 'не определены'}")
    if off_ipv6:
        print(f" IPv6 выключен на: {', '.join(off_ipv6)}")
    print("============================================================")


def interactive_menu():
    """Интерактивное меню в терминале."""
    while True:
        print_status()
        print(" 1. Включить Comss.one")
        print(" 2. Включить GeoHide EU")
        print(" 3. Включить MagicDNS")
        print(" 4. Включить Xbox DNS")
        print(" 5. Выключить Smart DNS (вернуть авто)")
        print(" 6. Проверить доступность сайтов")
        print(" 7. Найти лучший сервис")
        print(" 0. Выход")
        print("------------------------------------------------------------")
        choice = input("Выберите действие [0-7]: ").strip()
        if choice == "0":
            break
        elif choice in ("1", "2", "3", "4"):
            idx = int(choice) - 1
            ok, err = LinuxNet.enable(idx)
            if ok:
                print(f"\n[OK] Сервис {Services.NAME[idx]} успешно включён!\n")
            else:
                print(f"\n[FAIL] Ошибка: {err}\n")
        elif choice == "5":
            ok, err = LinuxNet.disable()
            if ok:
                print("\n[OK] Smart DNS выключен, DNS сброшен к автоматическому.\n")
            else:
                print(f"\n[FAIL] Ошибка: {err}\n")
        elif choice == "6":
            run_cli_check()
        elif choice == "7":
            run_cli_best()
        else:
            print("Неверный ввод, повторите попытку.")
        input("Нажмите Enter для продолжения...")


# ============================================================================
# ТОЧКА ВХОДА
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description=f"HB AI · Smart DNS {VERSION} — ChatGPT, Claude, Gemini, ElevenLabs, Discord, YouTube, Roblox и др. одной кнопкой."
    )
    parser.add_argument("--status", action="store_true", help="Показать текущий статус DNS")
    parser.add_argument("--enable", metavar="SERVICE", help="Включить сервис (comss, geohide, magicdns, xbox или 0..3)")
    parser.add_argument("--disable", action="store_true", help="Выключить Smart DNS")
    parser.add_argument("--check", nargs="?", const="current", metavar="SERVICE", help="Проверить сайты через DNS сервиса")
    parser.add_argument("--best", action="store_true", help="Найти лучший сервис по доступности нейросетей")
    parser.add_argument("--gui", action="store_true", help="Принудительно запустить графический интерфейс")
    parser.add_argument("--cli", action="store_true", help="Запустить консольное меню")
    parser.add_argument("-v", "--version", action="version", version=f"HB AI Smart DNS {VERSION}")

    args = parser.parse_args()

    # Выполнение параметров CLI
    if args.status:
        print_status()
        return

    if args.disable:
        ok, err = LinuxNet.disable()
        if ok:
            print("Smart DNS успешно выключен.")
        else:
            print(f"Ошибка: {err}")
            sys.exit(1)
        return

    if args.enable:
        idx = Services.find_index(args.enable)
        if idx is None:
            print(f"Неизвестный сервис: {args.enable}")
            print(f"Доступные: {', '.join(Services.SHORT)}")
            sys.exit(1)
        ok, err = LinuxNet.enable(idx)
        if ok:
            print(f"Smart DNS ({Services.NAME[idx]}) успешно включён!")
        else:
            print(f"Ошибка: {err}")
            sys.exit(1)
        return

    if args.check:
        idx = None
        if args.check != "current":
            idx = Services.find_index(args.check)
        run_cli_check(idx)
        return

    if args.best:
        run_cli_best()
        return

    if args.cli:
        interactive_menu()
        return

    # Если запрошен GUI или доступен графический дисплей (X11 / Wayland)
    has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    if args.gui or has_display:
        try:
            run_gui()
            return
        except Exception as e:
            if args.gui:
                print(f"Ошибка запуска GUI: {e}")
                sys.exit(1)
            # Фолбэк на CLI
            print(f"Не удалось открыть графический интерфейс ({e}), переключаемся в CLI...")

    interactive_menu()


if __name__ == "__main__":
    main()

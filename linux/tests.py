#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Тесты для HB AI · Smart DNS (Linux).
Проверяют разбор пакетов DNS, логику выбора лучшего сервиса,
классификацию HTTP ответов, детекцию устаревших адресов и версий.
"""

import os
import struct
import tempfile
import unittest
import urllib.request

from hb_ai_smart_dns import DpiService, LinuxNet, Probe, Services, Updates, VERSION


class TestServices(unittest.TestCase):
    def test_set_of_known(self):
        self.assertEqual(Services.set_of("94.250.253.55"), 0)
        self.assertEqual(Services.set_of("212.109.195.93"), 0)
        self.assertEqual(Services.set_of("143.20.64.192"), 1)
        self.assertEqual(Services.set_of("45.13.237.213"), 1)
        self.assertEqual(Services.set_of("109.120.132.43"), 2)
        self.assertEqual(Services.set_of("94.249.177.102"), 2)
        self.assertEqual(Services.set_of("111.88.96.54"), 3)
        self.assertEqual(Services.set_of("111.88.96.55"), 3)

    def test_set_of_old_working(self):
        # Прежние адреса Comss и Xbox Live
        self.assertEqual(Services.set_of("83.220.169.155"), 0)
        self.assertEqual(Services.set_of("111.88.96.50"), 3)
        self.assertEqual(Services.set_of("111.88.96.51"), 3)

    def test_unknown_and_foreign(self):
        self.assertIsNone(Services.set_of("8.8.8.8"))
        self.assertIsNone(Services.set_of("1.1.1.1"))
        self.assertIsNone(Services.set_of("127.0.0.1"))

    def test_stale_addresses(self):
        self.assertTrue(Services.is_stale("159.194.200.33"))
        self.assertTrue(Services.is_stale("193.233.112.67"))
        self.assertTrue(Services.is_stale("135.106.217.200"))
        self.assertTrue(Services.is_stale("85.209.2.112"))
        self.assertFalse(Services.is_stale("94.250.253.55"))

    def test_find_index(self):
        self.assertEqual(Services.find_index("comss"), 0)
        self.assertEqual(Services.find_index("geohide"), 1)
        self.assertEqual(Services.find_index("magicdns"), 2)
        self.assertEqual(Services.find_index("xbox"), 3)
        self.assertEqual(Services.find_index("0"), 0)
        self.assertEqual(Services.find_index("3"), 3)
        self.assertIsNone(Services.find_index("unknown_xyz"))


class TestDnsParsing(unittest.TestCase):
    def test_build_query(self):
        q = Probe.build_dns_query("chatgpt.com", qid=0x1234)
        qid, flags, qdcount, ancount, _, _ = struct.unpack(">HHHHHH", q[:12])
        self.assertEqual(qid, 0x1234)
        self.assertEqual(flags, 0x0100)
        self.assertEqual(qdcount, 1)
        self.assertEqual(ancount, 0)
        # Проверяем QNAME
        self.assertIn(b"\x07chatgpt\x03com\x00", q)

    def test_parse_a_valid(self):
        # Строим искусственный ответ DNS на chatgpt.com -> 1.2.3.4
        qid = 0x2A2A
        flags = 0x8180  # Response, Standard query response, No error
        header = struct.pack(">HHHHHH", qid, flags, 1, 1, 0, 0)
        qname = b"\x07chatgpt\x03com\x00"
        qtail = struct.pack(">HH", 1, 1)  # QTYPE=A, QCLASS=IN
        # Ответ: сжатое имя 0xC00C (указывает на байт 12)
        aname = b"\xC0\x0C"
        answer = struct.pack(">HHIH", 1, 1, 60, 4) + bytes([1, 2, 3, 4])
        packet = header + qname + qtail + aname + answer

        ip = Probe.parse_a(packet, expected_qid=qid)
        self.assertEqual(ip, "1.2.3.4")

    def test_parse_a_cname_then_a(self):
        # Ответ: сначала CNAME, затем A
        qid = 0x2A2A
        flags = 0x8180
        header = struct.pack(">HHHHHH", qid, flags, 1, 2, 0, 0)
        qname = b"\x03www\x07chatgpt\x03com\x00"
        qtail = struct.pack(">HH", 1, 1)
        # RR 1: CNAME
        cname_data = b"\x03foo\x00"
        cname_rr = b"\xC0\x0C" + struct.pack(">HHIH", 5, 1, 60, len(cname_data)) + cname_data
        # RR 2: A
        a_data = bytes([94, 250, 253, 55])
        a_rr = b"\xC0\x23" + struct.pack(">HHIH", 1, 1, 60, len(a_data)) + a_data
        packet = header + qname + qtail + cname_rr + a_rr

        ip = Probe.parse_a(packet, expected_qid=qid)
        self.assertEqual(ip, "94.250.253.55")

    def test_parse_nxdomain(self):
        qid = 0x2A2A
        flags = 0x8183  # RCODE=3 (NXDOMAIN)
        packet = struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0) + b"\x03foo\x00" + struct.pack(">HH", 1, 1)
        self.assertEqual(Probe.parse_a(packet, expected_qid=qid), "")

    def test_parse_refused(self):
        qid = 0x2A2A
        flags = 0x8185  # RCODE=5 (REFUSED)
        packet = struct.pack(">HHHHHH", qid, flags, 1, 0, 0, 0)
        self.assertIsNone(Probe.parse_a(packet, expected_qid=qid))

    def test_parse_wrong_qid(self):
        packet = struct.pack(">HHHHHH", 0x9999, 0x8180, 0, 0, 0, 0)
        self.assertIsNone(Probe.parse_a(packet, expected_qid=0x2A2A))


class TestProbeClassification(unittest.TestCase):
    def test_classify(self):
        self.assertEqual(Probe.classify("HTTP/1.1 200 OK\r\nContent-Type: text/html"), Probe.OK)
        self.assertEqual(Probe.classify("HTTP/1.1 302 Found\r\nLocation: https://google.com/sorry/index"), Probe.CAPTCHA)
        self.assertEqual(Probe.classify("HTTP/1.1 403 Forbidden\r\nlocation: /unsupported_country"), Probe.BLOCKED)
        self.assertEqual(Probe.classify("HTTP/1.1 451 Unavailable For Legal Reasons\r\ngeo-restricted"), Probe.BLOCKED)
        self.assertEqual(Probe.classify("HTTP/1.1 302\r\nLocation: /not-available"), Probe.BLOCKED)
        self.assertEqual(Probe.classify(""), Probe.NO_LINK)
        self.assertEqual(Probe.classify("000"), Probe.NO_LINK)

    def test_verdict(self):
        self.assertEqual(Probe.verdict(None), Probe.NO_DNS)
        self.assertEqual(Probe.verdict(""), Probe.ZERO)
        self.assertEqual(Probe.verdict("0.0.0.0"), Probe.ZERO)
        self.assertIsNone(Probe.verdict("143.20.64.192"))


class TestBestServiceSelection(unittest.TestCase):
    def make_res(self, ai_count: int, dy_ok: bool = False) -> list:
        res = []
        for i in range(Probe.RANKED):
            res.append(Probe.OK if i < ai_count else Probe.NO_LINK)
        # Добавляем Discord и YouTube (7-й и 8-й сайты)
        res.append(Probe.OK if dy_ok else Probe.NO_LINK)
        res.append(Probe.OK if dy_ok else Probe.NO_LINK)
        return res

    def test_best_selection(self):
        # Сервис 2 открыл 6 нейросетей, остальные меньше
        all_res = [self.make_res(4), self.make_res(5), self.make_res(6), None]
        self.assertEqual(Probe.best(all_res, current=-1), 2)

    def test_tie_keeps_current(self):
        # При равенстве остаётся текущий
        all_res = [self.make_res(5), self.make_res(5), self.make_res(4), None]
        self.assertEqual(Probe.best(all_res, current=1), 1)
        self.assertEqual(Probe.best(all_res, current=0), 0)

    def test_discord_and_youtube_do_not_affect_ranking(self):
        # Сервис А: 3 нейросети + Discord + YouTube
        # Сервис Б: 4 нейросети, без Discord и YouTube
        # Лучшим должен быть сервис Б, так как у него больше нейросетей!
        res_a = self.make_res(3, dy_ok=True)
        res_b = self.make_res(4, dy_ok=False)
        self.assertEqual(Probe.best([res_a, res_b, None, None], current=-1), 1)

        # Одинаковое число нейросетей: даже если у второго открыты Discord и YouTube,
        # выбор не меняется и остаётся первый при current=-1
        res_c = self.make_res(3, dy_ok=False)
        self.assertEqual(Probe.best([res_c, res_a, None, None], current=-1), 0)

        # Только Discord и YouTube без нейросетей не делают сервис лучшим
        only_dy = [Probe.NO_LINK] * 6 + [Probe.OK, Probe.OK]
        res_one = self.make_res(1, dy_ok=False)
        self.assertEqual(Probe.best([only_dy, res_one, None, None], current=-1), 1)

    def test_xbox_service_not_selected_when_unprobed(self):
        all_res = [self.make_res(3), self.make_res(4), self.make_res(5), None]
        self.assertNotEqual(Probe.best(all_res, current=-1), 3)


class TestUpdates(unittest.TestCase):
    def test_is_newer(self):
        self.assertTrue(Updates.is_newer("1.23", "1.22"))
        self.assertTrue(Updates.is_newer("1.3", "1.22"))
        self.assertFalse(Updates.is_newer("1.22", "1.22"))
        self.assertFalse(Updates.is_newer("1.21", "1.22"))
        self.assertFalse(Updates.is_newer("beta", "1.22"))
        self.assertFalse(Updates.is_newer("1,23", "1.22"))


class TestIpv6Persistence(unittest.TestCase):
    def test_save_and_read(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            path = tf.name
        try:
            # Подменяем путь к файлу
            orig_fn = LinuxNet.get_ipv6_off_file
            LinuxNet.get_ipv6_off_file = classmethod(lambda cls: path)

            LinuxNet.write_ipv6_off_list(["eth0", "wlan0"])
            read_list = LinuxNet.read_ipv6_off_list()
            self.assertEqual(read_list, ["eth0", "wlan0"])

            LinuxNet.write_ipv6_off_list([])
            self.assertEqual(LinuxNet.read_ipv6_off_list(), [])
        finally:
            LinuxNet.get_ipv6_off_file = orig_fn
            if os.path.exists(path):
                os.remove(path)



class TestDpiBypass(unittest.TestCase):
    def test_pac_script(self):
        pac = DpiService.pac_script(2080)
        self.assertIn("FindProxyForURL", pac)
        self.assertIn("discord.com", pac)
        self.assertIn("youtube.com", pac)
        self.assertIn("googlevideo.com", pac)
        self.assertIn("PROXY 127.0.0.1:2080", pac)
        self.assertIn("DIRECT", pac)

    def test_proxy_service_http_pac(self):
        started = DpiService.start()
        self.assertTrue(started)
        try:
            req = urllib.request.Request(f"http://127.0.0.1:{DpiService.port}/proxy.pac")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = resp.read().decode("utf-8")
                self.assertIn("FindProxyForURL", data)
                self.assertIn(f"PROXY 127.0.0.1:{DpiService.port}", data)
        finally:
            DpiService.stop()
            self.assertFalse(DpiService.is_running())


if __name__ == "__main__":
    unittest.main()

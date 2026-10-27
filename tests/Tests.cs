// Тесты Smart DNS. Сборка и запуск: test.bat (тот же csc, без NuGet и фреймворков).
// DNS компьютера тесты не меняют: проверка адресов идёт через подставной DNS-сервер на 127.0.0.1.
using System;
using System.Collections.Generic;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Reflection;
using System.Threading;
using System.Windows.Forms;

namespace HbAi.XboxDns
{
    static class Tests
    {
        static readonly List<KeyValuePair<string, Action>> all = new List<KeyValuePair<string, Action>>();
        static void T(string name, Action a) { all.Add(new KeyValuePair<string, Action>(name, a)); }

        static void Eq<X>(X expected, X actual, string what = "")
        {
            if (!Equals(expected, actual))
                throw new Exception(what + " ждали «" + expected + "», получили «" + actual + "»");
        }

        [STAThread]
        static int Main()
        {
            DnsReplies();
            BestService();
            KnownAddresses();
            SiteAnswers();
            WindowDrag();
            PowerShellRun();

            int failed = 0;
            foreach (var t in all)
            {
                try { t.Value(); Console.WriteLine("ok    " + t.Key); }
                catch (Exception e)
                {
                    failed++;
                    var inner = e is TargetInvocationException ? e.InnerException : e;
                    Console.WriteLine("FAIL  " + t.Key + ": " + inner.Message);
                }
            }
            Console.WriteLine(failed == 0 ? "все " + all.Count + " прошли" : failed + " из " + all.Count + " упали");
            return failed;
        }

        // ---------- ответы DNS: подставной сервер на 127.0.0.1:53 отвечает заранее собранным пакетом ----------

        static byte[] Name(string host)
        {
            var b = new List<byte>();
            foreach (var p in host.Split('.')) { b.Add((byte)p.Length); b.AddRange(System.Text.Encoding.ASCII.GetBytes(p)); }
            b.Add(0);
            return b.ToArray();
        }

        static byte[] Rr(byte[] owner, int type, byte[] data)
        {
            var b = new List<byte>(owner);
            b.AddRange(new byte[] { (byte)(type >> 8), (byte)type, 0, 1, 0, 0, 0, 60, (byte)(data.Length >> 8), (byte)data.Length });
            b.AddRange(data);
            return b.ToArray();
        }

        static readonly byte[] ToQuestion = { 0xC0, 12 };   // указатель на имя из вопроса

        // ответ = запрос с флагом «ответ» и числом записей + сами записи
        static string Ask(string host, Func<byte[], byte[][]> answers)
        {
            var srv = new UdpClient(new IPEndPoint(IPAddress.Loopback, 53));
            var th = new Thread(() =>
            {
                try
                {
                    var from = new IPEndPoint(IPAddress.Any, 0);
                    var q = srv.Receive(ref from);
                    var rr = answers(q);
                    if (rr == null) return;
                    var r = new List<byte>(q);
                    r[2] = 0x81; r[3] = 0x80; r[6] = 0; r[7] = (byte)rr.Length;
                    foreach (var x in rr) r.AddRange(x);
                    srv.Send(r.ToArray(), r.Count, from);
                }
                catch (SocketException) { }
            });
            th.IsBackground = true; th.Start();
            try { return Probe.Resolve("127.0.0.1", host); }
            finally { srv.Close(); th.Join(1000); }
        }

        static void DnsReplies()
        {
            T("DNS: обычный ответ с адресом", () =>
                Eq("1.2.3.4", Ask("chatgpt.com", q => new[] { Rr(ToQuestion, 1, new byte[] { 1, 2, 3, 4 }) })));

            T("DNS: сначала CNAME, потом адрес", () =>
                Eq("5.6.7.8", Ask("claude.ai", q =>
                {
                    // CNAME указывает на edge.cdn.net, его имя лежит сразу после 12 байт заголовка, вопроса и 12 байт записи
                    int at = q.Length + 12;
                    return new[] { Rr(ToQuestion, 5, Name("edge.cdn.net")), Rr(new byte[] { 0xC0, (byte)at }, 1, new byte[] { 5, 6, 7, 8 }) };
                })));

            T("DNS: имя записи — метка и указатель (сжатие RFC 1035)", () =>
                Eq("9.9.9.9", Ask("chatgpt.com", q =>
                {
                    // «www» + указатель на «chatgpt.com» в вопросе
                    return new[] { Rr(new byte[] { 3, (byte)'w', (byte)'w', (byte)'w', 0xC0, 12 }, 1, new byte[] { 9, 9, 9, 9 }) };
                })));

            T("DNS: сервис отвечает 0.0.0.0", () =>
                Eq(Probe.Zero, Probe.Verdict(Ask("gemini.google.com", q => new[] { Rr(ToQuestion, 1, new byte[4]) }))));

            T("DNS: ответ без адресов", () =>
                Eq(Probe.Zero, Probe.Verdict(Ask("grok.com", q => new byte[0][]))));

            T("DNS: сервер молчит", () =>
                Eq(Probe.NoDns, Probe.Verdict(Ask("grok.com", q => null))));
        }

        // ---------- «Найти лучший» ----------

        static string[] Res(int ok)
        {
            return Enumerable.Range(0, Probe.Host.Length).Select(i => i < ok ? Probe.Ok : Probe.NoLink).ToArray();
        }

        static void BestService()
        {
            T("Лучший — где открылось больше сайтов", () =>
                Eq(2, Probe.Best(new[] { Res(5), Res(4), Res(6), Res(6), null })));

            T("При равенстве выбирается первый по списку", () =>
                Eq(1, Probe.Best(new[] { Res(3), Res(5), Res(5), Res(2), null })));

            T("Xbox DNS (не проверялся) лучшим не становится", () =>
                Eq(0, Probe.Best(new[] { Res(0), Res(0), Res(0), Res(0), null })));

            T("Капча Google не считается открывшимся сайтом", () =>
                Eq(1, Probe.Best(new[] {
                    new[] { Probe.Ok, Probe.Captcha, Probe.Captcha, Probe.Ok, Probe.Ok, Probe.Ok },
                    Res(5), null, null, null })));
        }

        // ---------- какой сервис стоит в Windows ----------

        static void KnownAddresses()
        {
            T("Адрес MagicDNS узнаётся", () => Eq(2, Dns.SetOf("109.120.132.43")));
            T("Второй адрес Comss узнаётся", () => Eq(0, Dns.SetOf("212.109.195.93")));
            T("IPv6 Xbox с зоной и заглавными буквами узнаётся", () => Eq(Dns.XboxSet, Dns.SetOf("2A00:AB00:1233:26::51%12")));
            T("Адрес Xbox DNS из версии 1.0 узнаётся", () => Eq(Dns.XboxSet, Dns.SetOf("111.88.96.50")));
            T("Адрес GeoHide из версии 1.1 узнаётся", () => Eq(1, Dns.SetOf("193.233.112.67")));
            T("DNS роутера — не сервис", () => Eq(-1, Dns.SetOf("192.168.1.1")));
            T("Google 8.8.8.8 — не сервис", () => Eq(-1, Dns.SetOf("8.8.8.8")));
        }

        // ---------- ответ сайта ----------

        static void SiteAnswers()
        {
            T("Обычная страница — открывается", () =>
                Eq(Probe.Ok, Probe.Classify("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")));
            T("Редирект на капчу Google", () =>
                Eq(Probe.Captcha, Probe.Classify("HTTP/1.1 302 Found\r\nLocation: https://www.google.com/sorry/index?continue=x\r\n\r\n")));
            T("Редирект на страницу unsupported_country", () =>
                Eq(Probe.Blocked, Probe.Classify("HTTP/1.1 302 Found\r\nLocation: https://chatgpt.com/unsupported_country\r\n\r\n")));
            T("Редирект на geo-restricted, заголовок заглавными", () =>
                Eq(Probe.Blocked, Probe.Classify("HTTP/1.1 307\r\nLOCATION: /geo-restricted\r\n\r\n")));
            T("Редирект на страницу …-unavailable-in-region", () =>
                Eq(Probe.Blocked, Probe.Classify("HTTP/1.1 302\r\nLocation: /app-unavailable-in-region\r\n\r\n")));
        }

        // ---------- окно: перетаскивание ----------

        static void WindowDrag()
        {
            T("Окно не уезжает, если нажали на кнопку сервиса и повели мышь", () =>
            {
                MainForm.ForceScale = 1f;
                using (var f = new MainForm())
                {
                    f.Location = new Point(300, 200);
                    int set = (int)typeof(MainForm).GetField("dnsSet", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(f);
                    var seg = ((Rectangle[])typeof(MainForm).GetField("rSeg", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(f))[set];
                    // нажатие на уже выбранный сервис ничего не включает и DNS не трогает
                    Mouse(f, "OnMouseDown", new Point(seg.X + seg.Width / 2, seg.Y + seg.Height / 2));
                    Mouse(f, "OnMouseMove", new Point(220, 470));   // свободное место под статусом
                    Eq(new Point(300, 200), f.Location, "окно:");
                }
            });

            T("Окно тянется за мышью с пустого места", () =>
            {
                MainForm.ForceScale = 1f;
                using (var f = new MainForm())
                {
                    f.Location = new Point(300, 200);
                    Mouse(f, "OnMouseDown", new Point(220, 470));
                    Mouse(f, "OnMouseMove", new Point(250, 480));
                    Eq(new Point(330, 210), f.Location, "окно:");
                }
            });
        }

        static void Mouse(Form f, string handler, Point p)
        {
            typeof(Control).GetMethod(handler, BindingFlags.NonPublic | BindingFlags.Instance)
                .Invoke(f, new object[] { new MouseEventArgs(MouseButtons.Left, 1, p.X, p.Y, 0) });
        }

        // ---------- запуск PowerShell ----------

        static void PowerShellRun()
        {
            T("PowerShell с большим выводом не вешает программу", () =>
            {
                var run = typeof(Dns).GetMethod("Run", BindingFlags.NonPublic | BindingFlags.Static);
                string err = "не дождались";
                var th = new Thread(() => err = (string)run.Invoke(null, new object[] { "[Console]::Out.Write('x' * 200000)" }));
                th.IsBackground = true; th.Start();
                if (!th.Join(30000)) throw new Exception("за 30 секунд PowerShell не завершился");
                Eq(null, err, "ошибка:");
            });
        }
    }
}

// HB AI · Smart DNS 1.21 — переключатель Smart DNS (Comss.one, GeoHide EU, MagicDNS, Astracat, xbox-dns.ru) со встроенной проверкой.
// Сборка: build.bat (csc из .NET Framework 4, есть в каждой Windows 10/11).
using System;
using System.Diagnostics;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Drawing.Text;
using System.IO;
using System.Linq;
using System.Net.NetworkInformation;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Threading;
using System.Windows.Forms;

namespace HbAi.XboxDns
{
    static class Dns
    {
        // Сервисы Smart DNS. Проверено 23.10.2026 из России (МГТС, Москва), tools/probe_dns.py:
        // MagicDNS и Astracat открывают ChatGPT, Claude, Gemini, ElevenLabs, Grok, Perplexity; GeoHide Европа — то же;
        // Comss.one — всё, кроме Gemini (прокси Comss упирается в капчу Google). Российские узлы GeoHide
        // (159.194.200.33, 193.233.112.x) отвечают, но их прокси из России не открываются — убраны.
        // xbox-dns.ru с 10.10.2026 на нейросети отвечает 0.0.0.0, оставлен только для Xbox Live.
        public static readonly string[] Name = { "Comss.one", "GeoHide EU", "MagicDNS", "Astracat", "Xbox DNS" };
        public static readonly string[] Short = { "Comss", "GeoHide", "MagicDNS", "Astracat", "Xbox" };
        public static readonly string[][] V4 = {
            new[] { "83.220.169.155", "212.109.195.93" },
            new[] { "143.20.64.192", "45.13.237.213" },
            new[] { "109.120.132.43", "94.249.177.102" },
            new[] { "135.106.217.200" },
            new[] { "111.88.96.54", "111.88.96.55" } };
        public static readonly string[][] V6 = {
            new string[0], new string[0], new string[0], new string[0],
            new[] { "2a00:ab00:1233:26::50", "2a00:ab00:1233:26::51" } };
        public static readonly string[] Opens = {
            "ChatGPT, Claude, ElevenLabs, Grok; Gemini — через раз",
            "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
            "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
            "ChatGPT, Claude, Gemini, ElevenLabs, Grok",
            "только Xbox Live, нейросети — нет" };
        public static readonly string[] Site = { "comss.ru", "geohide.ru", "magicdns.ru", "astracat", "xbox-dns.ru" };
        public static readonly string[] Url = { "https://www.comss.ru/", "https://geohide.ru/", "https://magicdns.ru/", "https://astracat2022.github.io/dns/", "https://xbox-dns.ru/" };
        public static int Count { get { return Name.Length; } }
        public const int XboxSet = 4;
        // Адреса из прежних версий: xbox-dns.ru 1.0 и российский узел GeoHide 1.1
        static readonly string[] XboxOld = { "111.88.96.50", "111.88.96.51" };
        static readonly string[] GeoHideOld = { "159.194.200.33", "193.233.112.67" };

        // -1 — DNS сервиса не стоит, иначе номер набора (IPv4 определяет набор)
        public static int ActiveSet()
        {
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up || ni.NetworkInterfaceType == NetworkInterfaceType.Loopback)
                    continue;
                foreach (var ip in ni.GetIPProperties().DnsAddresses)
                {
                    int k = SetOf(ip.ToString());
                    if (k >= 0) return k;
                }
            }
            return -1;
        }

        // какому сервису принадлежит адрес DNS; -1 — чужой адрес
        public static int SetOf(string address)
        {
            string s = address.Split('%')[0].ToLowerInvariant();
            for (int k = 0; k < V4.Length; k++) if (V4[k].Contains(s) || V6[k].Contains(s)) return k;
            if (XboxOld.Contains(s)) return XboxSet;
            if (GeoHideOld.Contains(s)) return 1;
            return -1;
        }

        public static string Enable(int set)
        {
            string all = string.Join(",", V4[set].Concat(V6[set]).Select(a => "'" + a + "'").ToArray());
            return Run("$a = Get-NetAdapter | Where-Object Status -eq 'Up'; foreach ($x in $a) { Set-DnsClientServerAddress -InterfaceIndex $x.ifIndex -ServerAddresses (" + all + ") }; Clear-DnsClientCache");
        }

        public static string Disable()
        {
            return Run("$a = Get-NetAdapter | Where-Object Status -eq 'Up'; foreach ($x in $a) { Set-DnsClientServerAddress -InterfaceIndex $x.ifIndex -ResetServerAddresses }; Clear-DnsClientCache");
        }

        static string Run(string script)
        {
            var psi = new ProcessStartInfo("powershell.exe",
                "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command \"" + script.Replace("\"", "\\\"") + "\"");
            psi.CreateNoWindow = true;
            psi.UseShellExecute = false;
            psi.RedirectStandardError = true;
            psi.RedirectStandardOutput = true;
            using (var p = Process.Start(psi))
            {
                // оба потока читаем одновременно: иначе PowerShell встаёт, заполнив один, пока ждём конца другого
                var output = p.StandardOutput.ReadToEndAsync();
                string err = p.StandardError.ReadToEnd();
                output.Wait();
                p.WaitForExit();
                return p.ExitCode == 0 && err.Trim().Length == 0 ? null : err.Trim();
            }
        }
    }

    // Проверка: спрашиваем DNS сервиса напрямую (UDP, порт 53), подключаемся к выданному адресу по TLS с именем
    // сайта и смотрим ответ. Так видно, что получит человек, даже если DNS ещё не включён.
    static class Probe
    {
        public static readonly string[] Host = { "chatgpt.com", "claude.ai", "gemini.google.com", "elevenlabs.io", "grok.com", "www.perplexity.ai" };
        public static readonly string[] Label = { "ChatGPT", "Claude", "Gemini", "ElevenLabs", "Grok", "Perplexity" };
        public const string Ok = "открывается", Blocked = "блок страны", Captcha = "капча Google", NoLink = "нет связи", NoDns = "DNS молчит", Zero = "не пускает";

        public static string Resolve(string server, string host)
        {
            var q = new System.IO.MemoryStream();
            var w = new System.IO.BinaryWriter(q);
            w.Write(new byte[] { 0x2a, 0x2a, 0x01, 0x00, 0, 1, 0, 0, 0, 0, 0, 0 });
            foreach (var part in host.Split('.')) { w.Write((byte)part.Length); w.Write(System.Text.Encoding.ASCII.GetBytes(part)); }
            w.Write(new byte[] { 0, 0, 1, 0, 1 });
            byte[] r;
            try
            {
                using (var u = new System.Net.Sockets.UdpClient())
                {
                    u.Client.ReceiveTimeout = 3000;
                    var ep = new System.Net.IPEndPoint(System.Net.IPAddress.Parse(server), 53);
                    var data = q.ToArray(); u.Send(data, data.Length, ep);
                    r = u.Receive(ref ep);
                }
            }
            catch { return null; }
            return FirstA(r);
        }

        // первый адрес IPv4 из ответа DNS; "" — адреса нет или ответ битый
        static string FirstA(byte[] r)
        {
            try
            {
                int qd = r[4] << 8 | r[5], an = r[6] << 8 | r[7], i = 12;
                for (int n = 0; n < qd; n++) i = SkipName(r, i) + 4;
                for (int n = 0; n < an; n++)
                {
                    i = SkipName(r, i);
                    int type = r[i] << 8 | r[i + 1]; int len = r[i + 8] << 8 | r[i + 9]; i += 10;
                    if (type == 1) return r[i] + "." + r[i + 1] + "." + r[i + 2] + "." + r[i + 3];
                    i += len;
                }
            }
            catch (IndexOutOfRangeException) { }
            return "";
        }

        // имя в пакете: метки, а в конце ноль или указатель на имя раньше в пакете (RFC 1035, 4.1.4)
        static int SkipName(byte[] r, int i)
        {
            while (r[i] != 0)
            {
                if ((r[i] & 0xC0) == 0xC0) return i + 2;
                i += r[i] + 1;
            }
            return i + 1;
        }

        public static string Site(string host, string ip)
        {
            try
            {
                using (var tcp = new System.Net.Sockets.TcpClient())
                {
                    var ar = tcp.BeginConnect(ip, 443, null, null);
                    if (!ar.AsyncWaitHandle.WaitOne(6000) || !tcp.Connected) return NoLink;
                    tcp.EndConnect(ar);
                    tcp.ReceiveTimeout = 8000; tcp.SendTimeout = 8000;
                    using (var ssl = new System.Net.Security.SslStream(tcp.GetStream(), false, (s, c, ch, e) => true))
                    {
                        ssl.AuthenticateAsClient(host, null, (System.Security.Authentication.SslProtocols)(3072 | 12288), false);
                        var req = System.Text.Encoding.ASCII.GetBytes("GET / HTTP/1.1\r\nHost: " + host +
                            "\r\nUser-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36" +
                            "\r\nAccept: text/html\r\nConnection: close\r\n\r\n");
                        ssl.Write(req, 0, req.Length); ssl.Flush();
                        var buf = new byte[16384]; int got = 0, n;
                        while (got < buf.Length && (n = ssl.Read(buf, got, buf.Length - got)) > 0)
                        { got += n; if (System.Text.Encoding.ASCII.GetString(buf, 0, got).Contains("\r\n\r\n")) break; }
                        return Classify(System.Text.Encoding.ASCII.GetString(buf, 0, got));
                    }
                }
            }
            catch { return NoLink; }
        }

        // что видит человек по заголовкам ответа сайта: капча Google, страница «недоступно в вашей стране» или сайт
        public static string Classify(string head)
        {
            head = head.ToLowerInvariant();
            if (head.Contains("/sorry/")) return Captcha;
            if (new[] { "restrict", "unsupported", "unavailable", "not-available" }.Any(head.Contains)) return Blocked;
            return Ok;
        }

        // результат по каждому сайту для набора DNS
        public static string[] Service(int set)
        {
            var res = new string[Host.Length];
            var th = new Thread[Host.Length];
            for (int i = 0; i < Host.Length; i++)
            {
                int k = i;
                th[k] = new Thread(() =>
                {
                    string ip = null;
                    foreach (var srv in Dns.V4[set]) { ip = Resolve(srv, Host[k]); if (ip != null) break; }
                    res[k] = Verdict(ip) ?? Site(Host[k], ip);
                });
                th[k].IsBackground = true; th[k].Start();
            }
            foreach (var x in th) x.Join();
            return res;
        }

        // что сказать по ответу DNS, не заходя на сайт; null — адрес настоящий, надо проверять сайт
        public static string Verdict(string ip)
        {
            if (ip == null) return NoDns;
            if (ip == "" || ip == "0.0.0.0") return Zero;
            return null;
        }

        public static int Good(string[] res) { return res == null ? -1 : res.Count(x => x == Ok); }

        // сервис, где открылось больше всего сайтов; при равенстве — тот, что раньше в списке.
        // Непроверенный сервис (null), например Xbox DNS, выбран не будет.
        public static int Best(string[][] all)
        {
            int best = 0;
            for (int k = 1; k < all.Length; k++) if (Good(all[k]) > Good(all[best])) best = k;
            return best;
        }
    }

    class MainForm : Form
    {
        static readonly Color Bg = Color.FromArgb(7, 7, 11);
        static readonly Color Violet = Color.FromArgb(140, 112, 255);
        static readonly Color Yellow = Color.FromArgb(255, 224, 102);
        static readonly Color Muted = Color.FromArgb(141, 141, 154);
        static readonly Color Soft = Color.FromArgb(207, 200, 255);
        static readonly Color CardBg = Color.FromArgb(17, 17, 24);
        static readonly Color CardLine = Color.FromArgb(38, 38, 48);
        static readonly Color Ink = Color.FromArgb(11, 11, 16);          // тёмный текст на жёлтом
        static readonly Color Light = Color.FromArgb(233, 233, 242);
        static readonly Color OkGreen = Color.FromArgb(80, 200, 130);
        static readonly Color Bad = Color.FromArgb(255, 138, 138);
        static readonly Color BadDot = Color.FromArgb(255, 110, 110);
        static readonly Color VioletFill = Color.FromArgb(40, 124, 92, 255);
        static readonly Color VioletLine = Color.FromArgb(115, 124, 92, 255);

        readonly PrivateFontCollection fonts = new PrivateFontCollection();
        FontFamily fHead, fBold, fMed;
        bool active, busy;
        int dnsSet;
        string error;
        float pulse;
        Rectangle rToggle, rClose, rMin, rSite, rGroup, rBrand, rVk, rCheck, rBest;
        readonly Rectangle[] rSeg = new Rectangle[Dns.Count];
        string[] check; int checkSet = -1; bool checking; string bestNote;
        // окно тянется, только если кнопку мыши нажали на пустом месте
        Point dragFrom; bool dragging;
        // Разметка в «логических» пикселях окна 440×852 (как при 100 %), на экран всё умножается на S = DPI / 96.
        const int LW = 440, LH = 852;
        float S = 1f;
        internal static float ForceScale;
        readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();

        public MainForm()
        {
            LoadFonts();
            Text = "HB AI · Smart DNS";
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Bg;
            DoubleBuffered = true;
            try { Icon = new Icon(Assembly.GetExecutingAssembly().GetManifestResourceStream("app.ico")); } catch { }
            ApplyScale(ForceScale > 0 ? ForceScale : WindowDpi() / 96f, Screen.FromPoint(Cursor.Position).WorkingArea);

            rClose = new Rectangle(LW - 58, 22, 36, 36);
            rMin = new Rectangle(LW - 100, 22, 36, 36);
            rToggle = new Rectangle((LW - 200) / 2, 196, 200, 200);

            anim.Interval = 30;
            anim.Tick += (s, e) => { pulse = (pulse + 0.035f) % 1f; if (busy || active) Invalidate(ToScreen(rToggleGlow())); };
            anim.Start();

            int cur = Dns.ActiveSet();
            active = cur >= 0;
            dnsSet = cur >= 0 ? cur : 0;
            int segW = (LW - 56) / Dns.Count;
            for (int k = 0; k < Dns.Count; k++) rSeg[k] = new Rectangle(28 + k * segW, 500, segW, 56);
            MouseDown += OnDown;
            MouseMove += OnMove;
        }

        Rectangle rToggleGlow() { var r = rToggle; r.Inflate(40, 40); return r; }

        [DllImport("user32.dll")] static extern uint GetDpiForWindow(IntPtr hwnd);

        float WindowDpi()
        {
            try { uint d = GetDpiForWindow(Handle); if (d > 0) return d; } catch { }   // Windows 10 1607+
            using (var g0 = CreateGraphics()) return g0.DpiX;
        }

        // Размер окна под масштаб: окно целиком должно влезать в рабочую область экрана
        // (на ноутбуке 1080p при 150 % высота 852 × 1,5 больше экрана — тогда окно уменьшается целиком).
        void ApplyScale(float scale, Rectangle wa)
        {
            S = ForceScale > 0 ? ForceScale : Math.Min(scale, Math.Min((wa.Height - 24f) / LH, (wa.Width - 24f) / LW));
            ClientSize = new Size((int)Math.Round(LW * S), (int)Math.Round(LH * S));
            Region = RoundRegion(ClientRectangle, (int)Math.Round(22 * S));
            if (IsHandleCreated && Visible)
                Location = new Point(Math.Max(wa.Left, Math.Min(Left, wa.Right - Width)), Math.Max(wa.Top, Math.Min(Top, wa.Bottom - Height)));
            Invalidate();
        }

        // Масштаб Windows поменяли на ходу или окно перенесли на другой монитор
        protected override void WndProc(ref Message m)
        {
            const int WM_DPICHANGED = 0x02E0;
            if (m.Msg == WM_DPICHANGED)
            {
                int dpi = (int)((long)m.WParam & 0xFFFF);
                var sug = (RECT)Marshal.PtrToStructure(m.LParam, typeof(RECT));
                var wa = Screen.FromRectangle(Rectangle.FromLTRB(sug.Left, sug.Top, sug.Right, sug.Bottom)).WorkingArea;
                Location = new Point(sug.Left, sug.Top);
                ApplyScale(dpi / 96f, wa);
                m.Result = IntPtr.Zero;
                return;
            }
            base.WndProc(ref m);
        }

        [StructLayout(LayoutKind.Sequential)] struct RECT { public int Left, Top, Right, Bottom; }

        Rectangle ToScreen(Rectangle r) { return Rectangle.FromLTRB((int)Math.Floor(r.Left * S), (int)Math.Floor(r.Top * S), (int)Math.Ceiling(r.Right * S), (int)Math.Ceiling(r.Bottom * S)); }
        Point ToLogical(Point p) { return new Point((int)(p.X / S), (int)(p.Y / S)); }
        // Размер шрифта в пунктах при 100 %; задаём в пикселях, чтобы его масштабировал ScaleTransform, а не DPI второй раз.
        static Font Pt(FontFamily fam, float pt) { return new Font(fam, pt * 96f / 72f, GraphicsUnit.Pixel); }

        void LoadFonts()
        {
            foreach (var name in new[] { "Unbounded-ExtraBold.ttf", "Manrope-Bold.ttf", "Manrope-Medium.ttf" })
            {
                using (var s = Assembly.GetExecutingAssembly().GetManifestResourceStream(name))
                {
                    if (s == null) continue;
                    var data = new byte[s.Length];
                    s.Read(data, 0, data.Length);
                    IntPtr ptr = Marshal.AllocCoTaskMem(data.Length);
                    Marshal.Copy(data, 0, ptr, data.Length);
                    fonts.AddMemoryFont(ptr, data.Length);
                }
            }
            fHead = Find("HB Unbounded", "Segoe UI");
            fBold = Find("HB Manrope Bold", "Segoe UI");
            fMed = Find("HB Manrope Medium", "Segoe UI");
        }

        FontFamily Find(string name, string fallback)
        {
            foreach (var f in fonts.Families) if (f.Name.StartsWith(name)) return f;
            return new FontFamily(fallback);
        }

        static Region RoundRegion(Rectangle r, int rad) { return new Region(RoundPath(r, rad)); }

        static GraphicsPath RoundPath(RectangleF r, float rad)
        {
            var p = new GraphicsPath();
            float d = rad * 2;
            p.AddArc(r.X, r.Y, d, d, 180, 90);
            p.AddArc(r.Right - d, r.Y, d, d, 270, 90);
            p.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
            p.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
            p.CloseFigure();
            return p;
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            var g = e.Graphics;
            g.ScaleTransform(S, S);
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;

            // фон: мягкое фиолетовое свечение, как на обложках сообщества
            Glow(g, new RectangleF(LW - 330, -260, 560, 520), Color.FromArgb(95, 124, 92, 255));
            Glow(g, new RectangleF(-260, 460, 520, 460), Color.FromArgb(55, 60, 140, 255));

            DrawTop(g);
            DrawToggle(g);
            DrawStatus(g);
            DrawSets(g);
            DrawCheck(g);
            DrawFooter(g);
        }

        static readonly StringFormat Center = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };

        // скруглённая плашка с заливкой и обводкой
        static void Panel(Graphics g, RectangleF r, float rad, Color fill, Color line)
        {
            using (var path = RoundPath(r, rad))
            using (var b = new SolidBrush(fill))
            using (var pen = new Pen(line))
            { g.FillPath(b, path); g.DrawPath(pen, path); }
        }

        // плашка с сайтом сервиса, крестик, «свернуть» и заголовок
        void DrawTop(Graphics g)
        {
            using (var f = Pt(fBold, 11f))
            {
                string pill = "Smart DNS 1.21 · " + Dns.Site[dnsSet];
                var sz = g.MeasureString(pill, f);
                var pr = new RectangleF(30, 24, sz.Width + 46, 34);
                rSite = Rectangle.Round(pr);
                Panel(g, pr, 17, VioletFill, VioletLine);
                using (var b = new SolidBrush(Yellow)) g.FillEllipse(b, pr.X + 16, pr.Y + 12, 10, 10);
                using (var b = new SolidBrush(Soft)) g.DrawString(pill, f, b, pr.X + 32, pr.Y + (34 - sz.Height) / 2 + 1);
            }
            using (var pen = new Pen(Muted, 2f))
            {
                int c = 9;
                var m = new Point(rClose.X + rClose.Width / 2, rClose.Y + rClose.Height / 2);
                g.DrawLine(pen, m.X - c, m.Y - c, m.X + c, m.Y + c);
                g.DrawLine(pen, m.X + c, m.Y - c, m.X - c, m.Y + c);
                var n = new Point(rMin.X + rMin.Width / 2, rMin.Y + rMin.Height / 2);
                g.DrawLine(pen, n.X - c, n.Y + 4, n.X + c, n.Y + 4);
            }
            using (var f = Pt(fHead, 22f))
            using (var b = new SolidBrush(Color.White))
            {
                g.DrawString("Доступ", f, b, 28, 82);
                string hl = "к сервисам";
                var sz = g.MeasureString(hl, f);
                using (var path = RoundPath(new RectangleF(28, 124, sz.Width + 6, sz.Height - 2), 8))
                using (var yb = new SolidBrush(Yellow)) g.FillPath(yb, path);
                using (var db = new SolidBrush(Ink)) g.DrawString(hl, f, db, 31, 124);
            }
        }

        void DrawStatus(Graphics g)
        {
            string status = busy ? "Применяем настройки…" : active ? "DNS включён" : "DNS выключен";
            using (var f = Pt(fHead, 15f))
            using (var b = new SolidBrush(active && !busy ? Yellow : Color.White))
                Centered(g, status, f, b, 420);
            using (var f = Pt(fMed, 10.5f))
            using (var b = new SolidBrush(error != null ? Bad : Muted))
                Centered(g, StatusNote(), f, b, 454, LW - 60);
        }

        string StatusNote()
        {
            if (error != null) return error;
            if (bestNote != null) return bestNote;
            if (busy) return "Секунду";
            return active ? Dns.Name[dnsSet] + ": " + Dns.Opens[dnsSet] : "Обычный DNS от роутера или провайдера";
        }

        // выбор сервиса
        void DrawSets(Graphics g)
        {
            Panel(g, new RectangleF(28, 500, LW - 56, 56), 16, CardBg, CardLine);
            for (int k = 0; k < Dns.Count; k++)
            {
                var sr = new RectangleF(rSeg[k].X + 4, rSeg[k].Y + 5, rSeg[k].Width - 8, rSeg[k].Height - 10);
                bool on = k == dnsSet;
                if (on)
                    using (var path = RoundPath(sr, 12))
                    using (var b = new SolidBrush(Yellow)) g.FillPath(b, path);
                using (var f = Pt(fBold, 8.5f))
                using (var b = new SolidBrush(on ? Ink : Soft))
                    g.DrawString(Dns.Short[k], f, b, sr, Center);
            }
        }

        // карточка проверки: адреса, кнопки и что открывается через выбранный сервис
        void DrawCheck(Graphics g)
        {
            var card = new RectangleF(28, 574, LW - 56, 150);
            Panel(g, card, 16, CardBg, CardLine);
            using (var fl = Pt(fBold, 9.5f))
            using (var fv = Pt(fMed, 10f))
            using (var bl = new SolidBrush(Violet))
            using (var bv = new SolidBrush(Light))
            {
                g.DrawString("DNS", fl, bl, card.X + 18, card.Y + 14);
                g.DrawString(string.Join("  /  ", Dns.V4[dnsSet]), fv, bv, card.X + 58, card.Y + 12);
            }
            rCheck = new Rectangle((int)card.X + 18, (int)card.Y + 40, 160, 30);
            rBest = new Rectangle((int)card.Right - 18 - 160, (int)card.Y + 40, 160, 30);
            DrawSmall(g, rCheck, checking && checkSet == dnsSet ? "Проверяем…" : "Проверить " + Dns.Short[dnsSet], !checking);
            DrawSmall(g, rBest, checking && checkSet == -2 ? "Ищем…" : "Найти лучший", !checking);
            // результаты по сайтам: две колонки по три строки
            bool forThis = check != null && checkSet == dnsSet;
            using (var fn = Pt(fMed, 9.5f))
            using (var fs = Pt(fBold, 8f))
            {
                for (int i = 0; i < Probe.Host.Length; i++)
                {
                    float x = card.X + 18 + (i / 3) * ((card.Width - 36) / 2), y = card.Y + 82 + (i % 3) * 22;
                    string r = forThis ? check[i] : null;
                    using (var b = new SolidBrush(r == null ? Color.FromArgb(70, 70, 88) : ResultColor(r, BadDot))) g.FillEllipse(b, x, y + 4, 9, 9);
                    using (var b = new SolidBrush(Light)) g.DrawString(Probe.Label[i], fn, b, x + 16, y);
                    if (r != null)
                        using (var b = new SolidBrush(ResultColor(r, Bad)))
                            g.DrawString(r, fs, b, x + 92, y + 2);
                }
            }
        }

        static Color ResultColor(string r, Color bad) { return r == Probe.Ok ? OkGreen : r == Probe.Captcha ? Yellow : bad; }

        // кнопка группы ВКонтакте и подвал
        void DrawFooter(Graphics g)
        {
            rVk = new Rectangle(28, 742, LW - 56, 56);
            using (var path = RoundPath(rVk, 16))
            using (var b = new LinearGradientBrush(rVk, Color.FromArgb(124, 92, 255), Color.FromArgb(76, 124, 255), LinearGradientMode.Horizontal))
                g.FillPath(b, path);
            using (var f = Pt(fHead, 11.5f))
            using (var b = new SolidBrush(Color.White))
                g.DrawString("Наша группа ВКонтакте  →", f, b, rVk, Center);
            using (var fb = Pt(fHead, 13f))
            using (var bb = new SolidBrush(Violet))
                g.DrawString("HB AI", fb, bb, 28, 812);
            using (var f = Pt(fMed, 9.5f))
            using (var b = new SolidBrush(Muted))
            {
                var t = "vk.com/neiroseti_ai";
                var sz = g.MeasureString(t, f);
                rGroup = new Rectangle((int)(LW - 28 - sz.Width), 817, (int)sz.Width, (int)sz.Height);
                g.DrawString(t, f, b, rGroup.X, rGroup.Y);
                rBrand = new Rectangle(28, 810, 110, 30);
            }
        }

        void DrawSmall(Graphics g, Rectangle r, string text, bool enabled)
        {
            Panel(g, r, 10, enabled ? VioletFill : Color.FromArgb(24, 24, 32), enabled ? VioletLine : CardLine);
            using (var f = Pt(fBold, 9f))
            using (var b = new SolidBrush(enabled ? Soft : Muted))
                g.DrawString(text, f, b, r, Center);
        }

        void DrawToggle(Graphics g)
        {
            var r = new RectangleF(rToggle.X, rToggle.Y, rToggle.Width, rToggle.Height);
            if (active || busy)
            {
                float k = (float)(0.5 + 0.5 * Math.Sin(pulse * Math.PI * 2));
                var gr = r; gr.Inflate(28 + 10 * k, 28 + 10 * k);
                Glow(g, gr, Color.FromArgb((int)(busy ? 60 : 90 + 40 * k), active ? Yellow : Violet));
            }
            // кольцо
            using (var b = new SolidBrush(active ? Yellow : CardBg)) g.FillEllipse(b, r);
            using (var pen = new Pen(active ? Yellow : Color.FromArgb(70, 70, 88), 3f)) g.DrawEllipse(pen, r);
            if (busy)
            {
                using (var pen = new Pen(Violet, 5f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
                {
                    var ar = r; ar.Inflate(-10, -10);
                    g.DrawArc(pen, ar, pulse * 360f, 90f);
                }
            }
            // значок питания
            var c = new PointF(r.X + r.Width / 2, r.Y + r.Height / 2 - 14);
            using (var pen = new Pen(active ? Ink : Color.White, 7f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                g.DrawArc(pen, c.X - 32, c.Y - 32, 64, 64, -60, 300);
                g.DrawLine(pen, c.X, c.Y - 40, c.X, c.Y - 6);
            }
            using (var f = Pt(fHead, 13f))
            using (var b = new SolidBrush(active ? Ink : Soft))
            {
                string t = active ? "ВКЛ" : "ВЫКЛ";
                var sz = g.MeasureString(t, f);
                g.DrawString(t, f, b, c.X - sz.Width / 2, r.Y + r.Height - 62);
            }
        }

        static void Glow(Graphics g, RectangleF r, Color c)
        {
            using (var path = new GraphicsPath())
            {
                path.AddEllipse(r);
                using (var pb = new PathGradientBrush(path))
                {
                    pb.CenterColor = c;
                    pb.SurroundColors = new[] { Color.FromArgb(0, c) };
                    g.FillEllipse(pb, r);
                }
            }
        }

        void Centered(Graphics g, string s, Font f, Brush b, float y, float maxW = 0)
        {
            var sf = new StringFormat { Alignment = StringAlignment.Center };
            float w = maxW > 0 ? maxW : LW;
            g.DrawString(s, f, b, new RectangleF((LW - w) / 2, y, w, 40), sf);
        }

        void OnDown(object s, MouseEventArgs e)
        {
            dragging = false;
            if (e.Button != MouseButtons.Left) return;
            var lp = ToLogical(e.Location);
            if (rClose.Contains(lp)) { Close(); return; }
            if (rMin.Contains(lp)) { WindowState = FormWindowState.Minimized; return; }
            if (rGroup.Contains(lp)) { Open("https://vk.com/neiroseti_ai"); return; }
            if (rSite.Contains(lp)) { Open(Dns.Url[dnsSet]); return; }
            if (rBrand.Contains(lp) || rVk.Contains(lp)) { Open("https://vk.com/neiroseti_ai"); return; }
            if (InToggle(lp)) { Toggle(); return; }
            for (int k = 0; k < Dns.Count; k++)
                if (rSeg[k].Contains(lp)) { PickSet(k); return; }
            if (rCheck.Contains(lp)) { RunCheck(dnsSet); return; }
            if (rBest.Contains(lp)) { RunBest(); return; }
            dragging = true;
            dragFrom = e.Location;
        }

        void OnMove(object s, MouseEventArgs e)
        {
            Cursor = OverControl(ToLogical(e.Location)) && !busy ? Cursors.Hand : Cursors.Default;
            if (dragging && e.Button == MouseButtons.Left)
                Location = new Point(Location.X + e.X - dragFrom.X, Location.Y + e.Y - dragFrom.Y);
        }

        bool InToggle(Point lp)
        {
            var c = new Point(rToggle.X + rToggle.Width / 2, rToggle.Y + rToggle.Height / 2);
            double dx = lp.X - c.X, dy = lp.Y - c.Y;
            return dx * dx + dy * dy <= rToggle.Width * rToggle.Width / 4.0;
        }

        bool OverControl(Point lp)
        {
            return InToggle(lp) || rSeg.Any(r => r.Contains(lp))
                || new[] { rClose, rMin, rGroup, rSite, rBrand, rVk, rCheck, rBest }.Any(r => r.Contains(lp));
        }

        static void Open(string url) { try { Process.Start(url); } catch { } }

        // смена набора: если DNS уже включён, сразу переключаем адреса
        void PickSet(int k)
        {
            if (busy || k == dnsSet) return;
            dnsSet = k;
            if (active) Apply(true); else Invalidate();
        }

        void Toggle()
        {
            if (busy) return;
            Apply(!active);
        }

        // проверить выбранный сервис: DNS сервиса → прокси → сайт
        void RunCheck(int set)
        {
            if (checking) return;
            checking = true; checkSet = set; check = null; bestNote = null; Invalidate();
            ThreadPool.QueueUserWorkItem(_ =>
            {
                var res = Probe.Service(set);
                BeginInvoke((Action)(() => { checking = false; check = res; checkSet = set; Invalidate(); }));
            });
        }

        // перебрать все сервисы для нейросетей и выбрать тот, где открывается больше всего
        void RunBest()
        {
            if (checking) return;
            checking = true; checkSet = -2; check = null; bestNote = null; Invalidate();
            ThreadPool.QueueUserWorkItem(_ =>
            {
                var all = new string[Dns.Count][];
                var th = Enumerable.Range(0, Dns.Count).Where(k => k != Dns.XboxSet)
                    .Select(k => new Thread(() => all[k] = Probe.Service(k)) { IsBackground = true }).ToArray();
                foreach (var x in th) x.Start();
                foreach (var x in th) x.Join();
                int best = Probe.Best(all);
                int good = Probe.Good(all[best]);
                BeginInvoke((Action)(() =>
                {
                    checking = false; check = all[best]; checkSet = best;
                    bestNote = good == 0 ? "Сейчас ни один сервис не открывает нейросети" : "Лучший сейчас: " + Dns.Name[best] + " (" + good + " из " + Probe.Host.Length + ")";
                    if (best != dnsSet) { dnsSet = best; if (active) Apply(true); }
                    Invalidate();
                }));
            });
        }

        void Apply(bool turnOn)
        {
            busy = true; error = null; bestNote = null; Invalidate();
            int set = dnsSet;
            ThreadPool.QueueUserWorkItem(_ =>
            {
                string err;
                try { err = turnOn ? Dns.Enable(set) : Dns.Disable(); }
                catch (Exception ex) { err = ex.Message; }
                Thread.Sleep(600);
                int now = Dns.ActiveSet();
                BeginInvoke((Action)(() =>
                {
                    busy = false;
                    active = now >= 0;
                    if (now >= 0) dnsSet = now;
                    if (err != null && active != turnOn)
                        error = "Не получилось: запустите от имени администратора";
                    Invalidate();
                    if (active && error == null && turnOn) RunCheck(dnsSet);
                }));
            });
        }
    }

    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            // проверка разметки при другом масштабе экрана: --shot 1.5 out.png (DNS не трогает)
            if (args.Length == 3 && args[0] == "--shot")
            {
                MainForm.ForceScale = float.Parse(args[1], System.Globalization.CultureInfo.InvariantCulture);
                using (var f = new MainForm())
                using (var bmp = new Bitmap(f.ClientSize.Width, f.ClientSize.Height))
                {
                    f.DrawToBitmap(bmp, new Rectangle(Point.Empty, f.ClientSize));
                    bmp.Save(args[2], System.Drawing.Imaging.ImageFormat.Png);
                }
                return;
            }
            Application.Run(new MainForm());
        }
    }
}

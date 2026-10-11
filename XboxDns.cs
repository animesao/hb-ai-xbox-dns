// HB AI · Smart DNS — переключатель Smart DNS (Comss.one, GeoHide, Astracat, xbox-dns.ru) в стиле сообщества «Нейросети и AI на практике».
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
        // Сервисы Smart DNS. Проверено 11.10.2026 из России: Comss.one, GeoHide и Astracat отдают прокси
        // для ChatGPT, Claude, Gemini и ElevenLabs; xbox-dns.ru с 10.10.2026 нейросети не пропускает (0.0.0.0).
        public static readonly string[] Name = { "Comss.one", "GeoHide", "Astracat", "Xbox DNS" };
        public static readonly string[][] V4 = {
            new[] { "83.220.169.155", "212.109.195.93" },
            new[] { "159.194.200.33", "193.233.112.67" },
            new[] { "135.106.217.200" },
            new[] { "111.88.96.54", "111.88.96.55" } };
        public static readonly string[][] V6 = {
            new string[0], new string[0], new string[0],
            new[] { "2a00:ab00:1233:26::50", "2a00:ab00:1233:26::51" } };
        public static readonly string[] Opens = {
            "ChatGPT, Claude, Gemini, ElevenLabs", "ChatGPT, Claude, Gemini, ElevenLabs",
            "ChatGPT, Claude, Gemini, ElevenLabs", "только Xbox Live, нейросети — нет" };
        public static readonly string[] Site = { "comss.ru", "geohide.ru", "astracat", "xbox-dns.ru" };
        public static readonly string[] Url = { "https://www.comss.ru/", "https://geohide.ru/", "https://astracat2022.github.io/dns/", "https://xbox-dns.ru/" };
        // Старые адреса xbox-dns.ru из версии 1.0: если стоят они, показываем Xbox DNS
        static readonly string[] XboxOld = { "111.88.96.50", "111.88.96.51" };

        // -1 — DNS сервиса не стоит, иначе номер набора (IPv4 определяет набор)
        public static int ActiveSet()
        {
            foreach (var ni in NetworkInterface.GetAllNetworkInterfaces())
            {
                if (ni.OperationalStatus != OperationalStatus.Up || ni.NetworkInterfaceType == NetworkInterfaceType.Loopback)
                    continue;
                foreach (var ip in ni.GetIPProperties().DnsAddresses)
                {
                    string s = ip.ToString().Split('%')[0].ToLowerInvariant();
                    for (int k = 0; k < V4.Length; k++) if (V4[k].Contains(s) || V6[k].Contains(s)) return k;
                    if (XboxOld.Contains(s)) return 3;
                }
            }
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
                string err = p.StandardError.ReadToEnd();
                p.StandardOutput.ReadToEnd();
                p.WaitForExit();
                return p.ExitCode == 0 && err.Trim().Length == 0 ? null : err.Trim();
            }
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

        readonly PrivateFontCollection fonts = new PrivateFontCollection();
        FontFamily fHead, fBold, fMed;
        bool active, busy;
        int dnsSet;
        string error;
        float pulse;
        Rectangle rToggle, rClose, rSite, rGroup, rBrand, rVk;
        readonly Rectangle[] rSeg = new Rectangle[4];
        Point dragFrom;
        readonly System.Windows.Forms.Timer anim = new System.Windows.Forms.Timer();

        public MainForm()
        {
            LoadFonts();
            Text = "HB AI · Smart DNS";
            ClientSize = new Size(440, 812);
            FormBorderStyle = FormBorderStyle.None;
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Bg;
            DoubleBuffered = true;
            try { Icon = new Icon(Assembly.GetExecutingAssembly().GetManifestResourceStream("app.ico")); } catch { }
            Region = RoundRegion(ClientRectangle, 22);

            rClose = new Rectangle(ClientSize.Width - 58, 22, 36, 36);
            rToggle = new Rectangle((ClientSize.Width - 200) / 2, 196, 200, 200);

            anim.Interval = 30;
            anim.Tick += (s, e) => { pulse = (pulse + 0.035f) % 1f; if (busy || active) Invalidate(rToggleGlow()); };
            anim.Start();

            int cur = Dns.ActiveSet();
            active = cur >= 0;
            dnsSet = cur >= 0 ? cur : 0;
            int segW = (ClientSize.Width - 56) / 4;
            for (int k = 0; k < 4; k++) rSeg[k] = new Rectangle(28 + k * segW, 500, segW, 56);
            MouseDown += OnDown;
            MouseMove += OnMove;
        }

        Rectangle rToggleGlow() { var r = rToggle; r.Inflate(40, 40); return r; }

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
            g.SmoothingMode = SmoothingMode.AntiAlias;
            g.TextRenderingHint = TextRenderingHint.AntiAliasGridFit;
            int W = ClientSize.Width;

            // фон: мягкое фиолетовое свечение, как на обложках сообщества
            Glow(g, new RectangleF(W - 330, -260, 560, 520), Color.FromArgb(95, 124, 92, 255));
            Glow(g, new RectangleF(-260, 460, 520, 460), Color.FromArgb(55, 60, 140, 255));

            // плашка сверху
            using (var f = new Font(fBold, 11f, GraphicsUnit.Point))
            {
                string pill = "Smart DNS · " + Dns.Site[dnsSet];
                var sz = g.MeasureString(pill, f);
                var pr = new RectangleF(30, 24, sz.Width + 46, 34);
                rSite = Rectangle.Round(pr);
                using (var path = RoundPath(pr, 17))
                using (var b = new SolidBrush(Color.FromArgb(40, 124, 92, 255)))
                using (var pen = new Pen(Color.FromArgb(115, 124, 92, 255)))
                { g.FillPath(b, path); g.DrawPath(pen, path); }
                using (var b = new SolidBrush(Yellow)) g.FillEllipse(b, pr.X + 16, pr.Y + 12, 10, 10);
                using (var b = new SolidBrush(Soft)) g.DrawString(pill, f, b, pr.X + 32, pr.Y + (34 - sz.Height) / 2 + 1);
            }
            // крестик
            using (var pen = new Pen(Muted, 2f))
            {
                int c = 9;
                var m = new Point(rClose.X + rClose.Width / 2, rClose.Y + rClose.Height / 2);
                g.DrawLine(pen, m.X - c, m.Y - c, m.X + c, m.Y + c);
                g.DrawLine(pen, m.X + c, m.Y - c, m.X - c, m.Y + c);
            }

            // заголовок
            using (var f = new Font(fHead, 22f, GraphicsUnit.Point))
            using (var b = new SolidBrush(Color.White))
            {
                g.DrawString("Доступ", f, b, 28, 82);
                var w = g.MeasureString("Доступ ", f).Width;
                string hl = "к сервисам";
                var sz = g.MeasureString(hl, f);
                using (var path = RoundPath(new RectangleF(28, 124, sz.Width + 6, sz.Height - 2), 8))
                using (var yb = new SolidBrush(Yellow)) g.FillPath(yb, path);
                using (var db = new SolidBrush(Color.FromArgb(11, 11, 16))) g.DrawString(hl, f, db, 31, 124);
            }

            DrawToggle(g);

            // статус
            string status = busy ? "Применяем настройки…" : active ? "DNS включён" : "DNS выключен";
            string sub = error != null ? error : busy ? "Секунду" : active ? Dns.Name[dnsSet] + ": " + Dns.Opens[dnsSet] : "Обычный DNS от роутера или провайдера";
            using (var f = new Font(fHead, 15f, GraphicsUnit.Point))
            using (var b = new SolidBrush(active && !busy ? Yellow : Color.White))
                Centered(g, status, f, b, 420);
            using (var f = new Font(fMed, 10.5f, GraphicsUnit.Point))
            using (var b = new SolidBrush(error != null ? Color.FromArgb(255, 138, 138) : Muted))
                Centered(g, sub, f, b, 454, W - 60);

            // выбор набора адресов
            using (var path = RoundPath(new RectangleF(28, 500, W - 56, 56), 16))
            using (var b = new SolidBrush(CardBg))
            using (var pen = new Pen(CardLine))
            { g.FillPath(b, path); g.DrawPath(pen, path); }
            for (int k = 0; k < 4; k++)
            {
                var sr = new RectangleF(rSeg[k].X + 5, rSeg[k].Y + 5, rSeg[k].Width - 10, rSeg[k].Height - 10);
                bool on = k == dnsSet;
                if (on)
                    using (var path = RoundPath(sr, 12))
                    using (var b = new SolidBrush(Yellow)) g.FillPath(b, path);
                string label = k == 3 ? "Xbox" : Dns.Name[k];
                using (var f = new Font(fBold, 9.5f, GraphicsUnit.Point))
                using (var b = new SolidBrush(on ? Color.FromArgb(11, 11, 16) : Soft))
                using (var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                    g.DrawString(label, f, b, sr, sf);
            }

            // карточка с адресами
            var card = new RectangleF(28, 574, W - 56, 86);
            using (var path = RoundPath(card, 16))
            using (var b = new SolidBrush(CardBg))
            using (var pen = new Pen(CardLine))
            { g.FillPath(b, path); g.DrawPath(pen, path); }
            using (var fl = new Font(fBold, 9.5f, GraphicsUnit.Point))
            using (var fv = new Font(fMed, 10.5f, GraphicsUnit.Point))
            using (var bl = new SolidBrush(Violet))
            using (var bv = new SolidBrush(Color.FromArgb(233, 233, 242)))
            {
                g.DrawString("DNS", fl, bl, card.X + 20, card.Y + 16);
                g.DrawString(string.Join("  /  ", Dns.V4[dnsSet]), fv, bv, card.X + 76, card.Y + 14);
                g.DrawString("Для", fl, bl, card.X + 20, card.Y + 48);
                g.DrawString(Dns.Opens[dnsSet], fv, bv, card.X + 76, card.Y + 46);
            }

            // кнопка группы ВКонтакте
            rVk = new Rectangle(28, 678, W - 56, 58);
            using (var path = RoundPath(rVk, 16))
            using (var b = new LinearGradientBrush(rVk, Color.FromArgb(124, 92, 255), Color.FromArgb(76, 124, 255), LinearGradientMode.Horizontal))
                g.FillPath(b, path);
            using (var f = new Font(fHead, 11.5f, GraphicsUnit.Point))
            using (var b = new SolidBrush(Color.White))
            using (var sf = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center })
                g.DrawString("Наша группа ВКонтакте  →", f, b, rVk, sf);

            // подвал
            using (var fb = new Font(fHead, 13f, GraphicsUnit.Point))
            using (var bb = new SolidBrush(Violet))
                g.DrawString("HB AI", fb, bb, 28, 760);
            using (var f = new Font(fMed, 9.5f, GraphicsUnit.Point))
            using (var b = new SolidBrush(Muted))
            {
                var t = "vk.com/neiroseti_ai";
                var sz = g.MeasureString(t, f);
                rGroup = new Rectangle((int)(W - 28 - sz.Width), 765, (int)sz.Width, (int)sz.Height);
                g.DrawString(t, f, b, rGroup.X, rGroup.Y);
                rBrand = new Rectangle(28, 758, 110, 30);
            }
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
            using (var pen = new Pen(active ? Color.FromArgb(11, 11, 16) : Color.White, 7f) { StartCap = LineCap.Round, EndCap = LineCap.Round })
            {
                g.DrawArc(pen, c.X - 32, c.Y - 32, 64, 64, -60, 300);
                g.DrawLine(pen, c.X, c.Y - 40, c.X, c.Y - 6);
            }
            using (var f = new Font(fHead, 13f, GraphicsUnit.Point))
            using (var b = new SolidBrush(active ? Color.FromArgb(11, 11, 16) : Soft))
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
            float w = maxW > 0 ? maxW : ClientSize.Width;
            g.DrawString(s, f, b, new RectangleF((ClientSize.Width - w) / 2, y, w, 40), sf);
        }

        void OnDown(object s, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left) return;
            if (rClose.Contains(e.Location)) { Close(); return; }
            if (rGroup.Contains(e.Location)) { Open("https://vk.com/neiroseti_ai"); return; }
            if (rSite.Contains(e.Location)) { Open(Dns.Url[dnsSet]); return; }
            if (rBrand.Contains(e.Location) || rVk.Contains(e.Location)) { Open("https://vk.com/neiroseti_ai"); return; }
            var c = new Point(rToggle.X + rToggle.Width / 2, rToggle.Y + rToggle.Height / 2);
            double dx = e.X - c.X, dy = e.Y - c.Y;
            if (dx * dx + dy * dy <= rToggle.Width * rToggle.Width / 4.0) { Toggle(); return; }
            for (int k = 0; k < 4; k++)
                if (rSeg[k].Contains(e.Location)) { PickSet(k); return; }
            dragFrom = e.Location;
        }

        void OnMove(object s, MouseEventArgs e)
        {
            var c = new Point(rToggle.X + rToggle.Width / 2, rToggle.Y + rToggle.Height / 2);
            double dx = e.X - c.X, dy = e.Y - c.Y;
            bool hand = rClose.Contains(e.Location) || rGroup.Contains(e.Location) || rSite.Contains(e.Location) || rBrand.Contains(e.Location) || rVk.Contains(e.Location) || rSeg.Any(r => r.Contains(e.Location))
                        || dx * dx + dy * dy <= rToggle.Width * rToggle.Width / 4.0;
            Cursor = hand && !busy ? Cursors.Hand : Cursors.Default;
            if (e.Button == MouseButtons.Left && !hand)
                Location = new Point(Location.X + e.X - dragFrom.X, Location.Y + e.Y - dragFrom.Y);
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

        void Apply(bool turnOn)
        {
            busy = true; error = null; Invalidate();
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
                }));
            });
        }
    }

    static class Program
    {
        [STAThread]
        static void Main()
        {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}

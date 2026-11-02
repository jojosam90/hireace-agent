<#
.SYNOPSIS
  The little HireAce agent that floats on the desktop while the panel is minimized.

.DESCRIPTION
  Started by panel.ps1 with the panel's window. When the panel is minimized, the
  mascot (assets\bubble.png) appears where the panel was, stays on top and blinks now
  and then; a click brings the panel back, dragging moves it. It quits when the panel
  is closed.

.EXAMPLE
  powershell -WindowStyle Hidden -File .\bubble.ps1 -Panel <window handle>
#>
param([Parameter(Mandatory = $true)][long]$Panel)

$ErrorActionPreference = 'Stop'
Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace HireAce {
  // A window drawn from a PNG with its transparency (a layered window), so the round
  // mascot and its soft shadow float on the desktop with no box around them.
  public class Bubble : Form {
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    struct BlendFunction { public byte Op, Flags, Alpha, Format; }
    [StructLayout(LayoutKind.Sequential)]
    struct Rect { public int Left, Top, Right, Bottom; }

    [DllImport("user32.dll")] static extern bool UpdateLayeredWindow(IntPtr hwnd, IntPtr dst, ref Point at, ref Size size, IntPtr src, ref Point from, int key, ref BlendFunction blend, int flags);
    [DllImport("user32.dll")] static extern IntPtr GetDC(IntPtr hwnd);
    [DllImport("user32.dll")] static extern int ReleaseDC(IntPtr hwnd, IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr CreateCompatibleDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern bool DeleteDC(IntPtr dc);
    [DllImport("gdi32.dll")] static extern IntPtr SelectObject(IntPtr dc, IntPtr obj);
    [DllImport("gdi32.dll")] static extern bool DeleteObject(IntPtr obj);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool ShowWindow(IntPtr hwnd, int cmd);
    [DllImport("user32.dll")] static extern bool SetForegroundWindow(IntPtr hwnd);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

    readonly IntPtr panel;
    readonly Bitmap open, blink;
    Rect panelRect;
    bool moved, down, dragging;
    Point downAt, formAt;
    int ticks;

    Bubble(IntPtr panel, Bitmap open, Bitmap blink) {
      this.panel = panel;
      this.open = open;
      this.blink = blink;
      FormBorderStyle = FormBorderStyle.None;
      ShowInTaskbar = false;
      StartPosition = FormStartPosition.Manual;
      TopMost = true;
      Size = open.Size;
      Cursor = Cursors.Hand;
      new ToolTip().SetToolTip(this, "HireAce - click to open");
      MouseDown += delegate(object s, MouseEventArgs e) {
        down = true; dragging = false; downAt = Cursor.Position; formAt = Location;
      };
      MouseMove += delegate(object s, MouseEventArgs e) {
        if (!down) return;
        Point now = Cursor.Position;
        if (Math.Abs(now.X - downAt.X) + Math.Abs(now.Y - downAt.Y) > 4) dragging = true;
        if (dragging) Location = new Point(formAt.X + now.X - downAt.X, formAt.Y + now.Y - downAt.Y);
      };
      MouseUp += delegate(object s, MouseEventArgs e) {
        if (dragging) moved = true; else OpenPanel();
        down = false; dragging = false;
      };
      Timer timer = new Timer();
      timer.Interval = 250;
      timer.Tick += delegate { Check(); };
      timer.Start();
    }

    // Layered, without a taskbar button, never taking the focus from other apps
    protected override CreateParams CreateParams {
      get { CreateParams p = base.CreateParams; p.ExStyle |= 0x80000 | 0x80 | 0x8; return p; }
    }
    protected override bool ShowWithoutActivation { get { return true; } }

    void Check() {
      if (!IsWindow(panel)) { Application.Exit(); return; }
      bool minimized = IsIconic(panel);
      if (!minimized) {
        GetWindowRect(panel, out panelRect);
        if (Visible) Hide();
        return;
      }
      if (!Visible) {
        if (!moved) PlaceWherePanelWas();
        Show();
        Draw(open);
        ticks = 0;
      }
      // A blink every 4 seconds
      ticks++;
      if (ticks % 16 == 0) Draw(blink);
      else if (ticks % 16 == 1) Draw(open);
    }

    void PlaceWherePanelWas() {
      Rectangle area = Screen.FromPoint(new Point(panelRect.Right - 1, panelRect.Top)).WorkingArea;
      int x = panelRect.Right > panelRect.Left ? panelRect.Right - Width : area.Right - Width - 16;
      int y = panelRect.Right > panelRect.Left ? panelRect.Top : area.Top + 16;
      Location = new Point(
        Math.Max(area.Left, Math.Min(x, area.Right - Width)),
        Math.Max(area.Top, Math.Min(y, area.Bottom - Height)));
    }

    void OpenPanel() {
      ShowWindow(panel, 9); // SW_RESTORE
      SetForegroundWindow(panel);
      Hide();
    }

    void Draw(Bitmap bitmap) {
      IntPtr screen = GetDC(IntPtr.Zero);
      IntPtr memory = CreateCompatibleDC(screen);
      IntPtr handle = bitmap.GetHbitmap(Color.FromArgb(0));
      IntPtr old = SelectObject(memory, handle);
      try {
        Size size = bitmap.Size;
        Point from = Point.Empty, at = Location;
        BlendFunction blend = new BlendFunction();
        blend.Alpha = 255;
        blend.Format = 1; // AC_SRC_ALPHA
        UpdateLayeredWindow(Handle, screen, ref at, ref size, memory, ref from, 0, ref blend, 2);
      } finally {
        SelectObject(memory, old);
        DeleteObject(handle);
        DeleteDC(memory);
        ReleaseDC(IntPtr.Zero, screen);
      }
    }

    static Bitmap LoadScaled(string path, int px) {
      Bitmap scaled = new Bitmap(px, px);
      using (Image source = Image.FromFile(path))
      using (Graphics g = Graphics.FromImage(scaled)) {
        g.InterpolationMode = InterpolationMode.HighQualityBicubic;
        g.PixelOffsetMode = PixelOffsetMode.HighQuality;
        g.DrawImage(source, 0, 0, px, px);
      }
      return scaled;
    }

    public static void Run(IntPtr panel, string openPng, string blinkPng) {
      SetProcessDPIAware();
      Application.EnableVisualStyles();
      int px;
      using (Graphics g = Graphics.FromHwnd(IntPtr.Zero)) { px = (int)(72 * g.DpiX / 96); }
      Bubble bubble = new Bubble(panel, LoadScaled(openPng, px), LoadScaled(blinkPng, px));
      bubble.CreateControl();
      Application.Run(new ApplicationContext());
    }
  }
}
'@

$assets = Join-Path $PSScriptRoot 'assets'
[HireAce.Bubble]::Run([IntPtr]$Panel, (Join-Path $assets 'bubble.png'), (Join-Path $assets 'bubble-blink.png'))

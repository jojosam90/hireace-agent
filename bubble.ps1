<#
.SYNOPSIS
  The HireAce assistant who stands on the desktop while the panel is minimized.

.DESCRIPTION
  Started by panel.ps1 with the panel's window. When the panel is minimized, the
  assistant (assets\avatar*.png, drawn by assets\make_avatar.py) stands at the
  bottom right of the screen, above the taskbar, on top of other windows, and
  blinks now and then. When the user has been away from the mouse and keyboard
  for -IdleMinutes, she knocks on the screen (knock... knock, assets\knock.wav),
  again every 2 minutes, until they are back. A click brings the panel back;
  dragging moves her. She leaves when the panel is closed.

.EXAMPLE
  powershell -WindowStyle Hidden -File .\bubble.ps1 -Panel <window handle>
#>
param(
  [Parameter(Mandatory = $true)][long]$Panel,
  # Away from the mouse and keyboard this long (minutes) before she knocks
  [double]$IdleMinutes = 5
)

$ErrorActionPreference = 'Stop'
Add-Type -ReferencedAssemblies System.Windows.Forms, System.Drawing -TypeDefinition @'
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Media;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace HireAce {
  // A window drawn from a PNG with its transparency (a layered window), so the
  // assistant and her shadow stand on the desktop with no box around them; clicks
  // on the transparent parts go to the window below.
  public class Bubble : Form {
    [StructLayout(LayoutKind.Sequential, Pack = 1)]
    struct BlendFunction { public byte Op, Flags, Alpha, Format; }
    [StructLayout(LayoutKind.Sequential)]
    struct LastInput { public uint Size, Time; }

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
    [DllImport("user32.dll")] static extern bool GetLastInputInfo(ref LastInput info);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();

    // The knock: hand up, tap (knock sound), back, tap (knock sound), hand up, stand
    static readonly int[] KnockFrames = { 2, 3, 2, 3, 2 };
    const int TickMs = 250;
    const int KnockAgainSeconds = 120;

    readonly IntPtr panel;
    readonly Bitmap[] frames;  // standing, blinking, hand up, tapping the screen
    readonly SoundPlayer knock;
    readonly int idleLimitSeconds;
    bool moved, down, dragging;
    Point downAt, formAt;
    int ticks;
    int knockStep = -1;  // where in KnockFrames she is; -1: not knocking
    DateTime nextKnock = DateTime.MinValue;

    Bubble(IntPtr panel, Bitmap[] frames, SoundPlayer knock, double idleMinutes) {
      this.panel = panel;
      this.frames = frames;
      this.knock = knock;
      idleLimitSeconds = (int)(idleMinutes * 60);
      FormBorderStyle = FormBorderStyle.None;
      ShowInTaskbar = false;
      StartPosition = FormStartPosition.Manual;
      TopMost = true;
      Size = frames[0].Size;
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
      timer.Interval = TickMs;
      timer.Tick += delegate { Check(); };
      timer.Start();
    }

    // Layered, without a taskbar button, never taking the focus from other apps
    protected override CreateParams CreateParams {
      get { CreateParams p = base.CreateParams; p.ExStyle |= 0x80000 | 0x80 | 0x8; return p; }
    }
    protected override bool ShowWithoutActivation { get { return true; } }

    // Seconds since the user last touched the mouse or keyboard
    static int IdleSeconds() {
      LastInput info = new LastInput();
      info.Size = (uint)Marshal.SizeOf(info);
      if (!GetLastInputInfo(ref info)) return 0;
      return (int)(((uint)Environment.TickCount - info.Time) / 1000);
    }

    void Check() {
      if (!IsWindow(panel)) { Application.Exit(); return; }
      if (!IsIconic(panel)) {
        if (Visible) Hide();
        knockStep = -1;
        return;
      }
      if (!Visible) {
        if (!moved) StandAtTheBottomRight();
        Show();
        Draw(frames[0]);
        ticks = 0;
        // Away already when the panel was minimized: knock after the full wait
        nextKnock = DateTime.Now.AddSeconds(Math.Max(0, idleLimitSeconds - IdleSeconds()));
      }
      ticks++;
      int idle = IdleSeconds();

      if (knockStep >= 0) {
        // Back at the mouse or keyboard: stop knocking at once
        if (idle < 1) { knockStep = -1; Draw(frames[0]); return; }
        int frame = KnockFrames[knockStep];
        Draw(frames[frame]);
        if (frame == 3) PlayKnock();
        knockStep++;
        if (knockStep >= KnockFrames.Length) { knockStep = -1; Draw(frames[0]); }
        return;
      }
      if (idle >= idleLimitSeconds && DateTime.Now >= nextKnock) {
        knockStep = 0;
        nextKnock = DateTime.Now.AddSeconds(KnockAgainSeconds);
        return;
      }
      // A blink every 4 seconds
      if (ticks % 16 == 0) Draw(frames[1]);
      else if (ticks % 16 == 1) Draw(frames[0]);
    }

    void PlayKnock() {
      if (knock == null) return;
      try { knock.Play(); } catch (Exception) { }  // no sound device: knock silently
    }

    // Standing on the taskbar at the bottom right of the screen the panel was on
    void StandAtTheBottomRight() {
      Rectangle area = Screen.FromHandle(panel).WorkingArea;
      Location = new Point(area.Right - Width - 24, area.Bottom - Height);
    }

    void OpenPanel() {
      knockStep = -1;
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

    static Bitmap LoadScaled(string path, int height) {
      using (Image source = Image.FromFile(path)) {
        int width = height * source.Width / source.Height;
        Bitmap scaled = new Bitmap(width, height);
        using (Graphics g = Graphics.FromImage(scaled)) {
          g.InterpolationMode = InterpolationMode.HighQualityBicubic;
          g.PixelOffsetMode = PixelOffsetMode.HighQuality;
          g.DrawImage(source, 0, 0, width, height);
        }
        return scaled;
      }
    }

    public static void Run(IntPtr panel, string folder, double idleMinutes) {
      SetProcessDPIAware();
      Application.EnableVisualStyles();
      int height;
      using (Graphics g = Graphics.FromHwnd(IntPtr.Zero)) { height = (int)(160 * g.DpiX / 96); }
      string[] names = { "avatar.png", "avatar-blink.png", "avatar-knock1.png", "avatar-knock2.png" };
      Bitmap[] frames = new Bitmap[names.Length];
      for (int i = 0; i < names.Length; i++) frames[i] = LoadScaled(System.IO.Path.Combine(folder, names[i]), height);
      SoundPlayer knock = null;
      string sound = System.IO.Path.Combine(folder, "knock.wav");
      if (System.IO.File.Exists(sound)) { knock = new SoundPlayer(sound); knock.Load(); }
      Bubble bubble = new Bubble(panel, frames, knock, idleMinutes);
      bubble.CreateControl();
      Application.Run(new ApplicationContext());
    }
  }
}
'@

[HireAce.Bubble]::Run([IntPtr]$Panel, (Join-Path $PSScriptRoot 'assets'), $IdleMinutes)

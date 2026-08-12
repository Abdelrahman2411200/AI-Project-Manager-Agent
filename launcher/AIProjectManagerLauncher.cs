using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

[assembly: AssemblyTitle("AI Project Manager")]
[assembly: AssemblyDescription("Click-to-run launcher for the local AI Project Manager")]
[assembly: AssemblyCompany("AI Project Manager")]
[assembly: AssemblyProduct("AI Project Manager")]
[assembly: AssemblyVersion("1.0.0.0")]
[assembly: AssemblyFileVersion("1.0.0.0")]

namespace AIProjectManagerLauncher
{
    internal static class Program
    {
        [DllImport("user32.dll")]
        private static extern bool SetProcessDPIAware();

        [STAThread]
        private static void Main(string[] args)
        {
            SetProcessDPIAware();
            string root = RepositoryLocator.Find();
            if (root == null)
            {
                MessageBox.Show(
                    "The launcher must remain inside the AI Project Manager repository. " +
                    "Keep 'AI Project Manager.exe' beside compose.demo.yaml.",
                    "AI Project Manager",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                Environment.ExitCode = 2;
                return;
            }

            bool headlessStart = HasArgument(args, "--headless-start");
            bool headlessStop = HasArgument(args, "--headless-stop");
            if (headlessStart || headlessStop)
            {
                string url = ProjectRuntime.GetApplicationUrl(root);
                if (headlessStart && ProjectRuntime.IsHealthy(url))
                {
                    Environment.ExitCode = 0;
                    return;
                }
                string script = headlessStop
                    ? Path.Combine(root, "infra", "release", "stop-local-demo.ps1")
                    : Path.Combine(root, "infra", "release", "start-local-ollama.ps1");
                string scriptArguments = headlessStop
                    ? string.Empty
                    : "-PreferCachedImages -SkipProviderProbe";
                Environment.ExitCode = ProjectRuntime.RunPowerShell(
                    root, script, scriptArguments, Console.WriteLine);
                return;
            }

            bool createdNew;
            using (Mutex mutex = new Mutex(true, "Local_AI_Project_Manager_Launcher", out createdNew))
            {
                if (!createdNew)
                {
                    ProjectRuntime.OpenBrowser(ProjectRuntime.GetApplicationUrl(root));
                    return;
                }
                Application.EnableVisualStyles();
                Application.SetCompatibleTextRenderingDefault(false);
                Application.Run(new LauncherForm(root));
            }
        }

        private static bool HasArgument(IEnumerable<string> arguments, string expected)
        {
            foreach (string argument in arguments)
            {
                if (string.Equals(argument, expected, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }
    }

    internal static class RepositoryLocator
    {
        public static string Find()
        {
            string[] starts =
            {
                AppDomain.CurrentDomain.BaseDirectory,
                Environment.CurrentDirectory,
                Environment.GetEnvironmentVariable("AI_PROJECT_MANAGER_ROOT")
            };
            foreach (string start in starts)
            {
                string found = WalkParents(start);
                if (found != null)
                {
                    return found;
                }
            }
            return null;
        }

        private static string WalkParents(string start)
        {
            if (string.IsNullOrWhiteSpace(start) || !Directory.Exists(start))
            {
                return null;
            }
            DirectoryInfo current = new DirectoryInfo(start);
            for (int depth = 0; current != null && depth < 6; depth++, current = current.Parent)
            {
                if (File.Exists(Path.Combine(current.FullName, "compose.demo.yaml")) &&
                    File.Exists(Path.Combine(current.FullName, "infra", "release", "start-local-ollama.ps1")))
                {
                    return current.FullName;
                }
            }
            return null;
        }
    }

    internal static class ProjectRuntime
    {
        public static string GetApplicationUrl(string root)
        {
            string port = "8080";
            string environmentPath = Path.Combine(root, ".env.demo");
            if (File.Exists(environmentPath))
            {
                foreach (string line in File.ReadAllLines(environmentPath))
                {
                    if (line.StartsWith("HTTP_PORT=", StringComparison.OrdinalIgnoreCase))
                    {
                        string candidate = line.Substring("HTTP_PORT=".Length).Trim();
                        int parsed;
                        if (int.TryParse(candidate, out parsed) && parsed >= 1 && parsed <= 65535)
                        {
                            port = parsed.ToString();
                        }
                        break;
                    }
                }
            }
            return "http://localhost:" + port;
        }

        public static bool IsHealthy(string applicationUrl)
        {
            try
            {
                HttpWebRequest request = (HttpWebRequest)WebRequest.Create(
                    applicationUrl.TrimEnd('/') + "/api/v1/health/ready");
                request.Method = "GET";
                request.Timeout = 5000;
                request.ReadWriteTimeout = 5000;
                using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                using (StreamReader reader = new StreamReader(response.GetResponseStream()))
                {
                    string body = reader.ReadToEnd();
                    return response.StatusCode == HttpStatusCode.OK && body.Contains("\"ready\"");
                }
            }
            catch
            {
                return false;
            }
        }

        public static int RunPowerShell(
            string root,
            string scriptPath,
            string scriptArguments,
            Action<string> onLine)
        {
            Directory.CreateDirectory(Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AI Project Manager"));
            string logPath = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "AI Project Manager",
                "launcher.log");
            string arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + scriptPath + "\"";
            if (!string.IsNullOrWhiteSpace(scriptArguments))
            {
                arguments += " " + scriptArguments;
            }
            ProcessStartInfo startInfo = new ProcessStartInfo
            {
                FileName = "powershell.exe",
                Arguments = arguments,
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8
            };
            StringBuilder collected = new StringBuilder();
            using (Process process = new Process())
            {
                process.StartInfo = startInfo;
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    Emit(eventArgs.Data, collected, onLine);
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                {
                    Emit(eventArgs.Data, collected, onLine);
                };
                try
                {
                    process.Start();
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                    process.WaitForExit();
                    process.WaitForExit(1000);
                    File.AppendAllText(
                        logPath,
                        Environment.NewLine + DateTime.Now.ToString("s") + Environment.NewLine +
                        collected + Environment.NewLine,
                        Encoding.UTF8);
                    return process.ExitCode;
                }
                catch (Exception error)
                {
                    Emit(error.Message, collected, onLine);
                    File.AppendAllText(logPath, collected.ToString(), Encoding.UTF8);
                    return 1;
                }
            }
        }

        private static void Emit(string line, StringBuilder collected, Action<string> onLine)
        {
            if (string.IsNullOrWhiteSpace(line))
            {
                return;
            }
            lock (collected)
            {
                collected.AppendLine(line);
            }
            if (onLine != null)
            {
                onLine(line);
            }
        }

        public static void OpenBrowser(string applicationUrl)
        {
            try
            {
                Process.Start(new ProcessStartInfo(applicationUrl) { UseShellExecute = true });
            }
            catch (Exception error)
            {
                MessageBox.Show(error.Message, "Unable to open browser", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }

    internal sealed class LauncherForm : Form
    {
        private readonly string root;
        private readonly string applicationUrl;
        private readonly Label statusLabel;
        private readonly Label detailLabel;
        private readonly ProgressBar progress;
        private readonly TextBox activity;
        private readonly Button startButton;
        private readonly Button openButton;
        private readonly Button stopButton;
        private readonly Button closeButton;
        private bool operationRunning;

        public LauncherForm(string repositoryRoot)
        {
            root = repositoryRoot;
            applicationUrl = ProjectRuntime.GetApplicationUrl(root);
            Text = "AI Project Manager";
            Width = 720;
            Height = 500;
            MinimumSize = new Size(660, 460);
            StartPosition = FormStartPosition.CenterScreen;
            BackColor = Color.FromArgb(10, 20, 43);
            ForeColor = Color.White;
            Font = new Font("Segoe UI", 9F);
            Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);

            Panel header = new Panel
            {
                Left = 0,
                Top = 0,
                Width = ClientSize.Width,
                Height = 112,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right,
                BackColor = Color.FromArgb(20, 35, 72)
            };
            Controls.Add(header);

            PictureBox logo = new PictureBox
            {
                Left = 26,
                Top = 25,
                Width = 62,
                Height = 62,
                Image = BrandArt.CreateLogo(62),
                SizeMode = PictureBoxSizeMode.StretchImage
            };
            header.Controls.Add(logo);

            Label title = new Label
            {
                Left = 104,
                Top = 25,
                Width = 500,
                Height = 34,
                Text = "AI Project Manager",
                ForeColor = Color.White,
                Font = new Font("Segoe UI Semibold", 19F, FontStyle.Bold)
            };
            header.Controls.Add(title);
            Label subtitle = new Label
            {
                Left = 106,
                Top = 62,
                Width = 520,
                Height = 25,
                Text = "Project intelligence - local secure workspace",
                ForeColor = Color.FromArgb(174, 190, 225),
                Font = new Font("Segoe UI", 10F)
            };
            header.Controls.Add(subtitle);

            statusLabel = new Label
            {
                Left = 28,
                Top = 137,
                Width = 630,
                Height = 31,
                Text = "Preparing your workspace",
                ForeColor = Color.White,
                Font = new Font("Segoe UI Semibold", 15F, FontStyle.Bold),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            Controls.Add(statusLabel);
            detailLabel = new Label
            {
                Left = 29,
                Top = 172,
                Width = 640,
                Height = 23,
                Text = "The launcher will check services and open " + applicationUrl,
                ForeColor = Color.FromArgb(174, 190, 225),
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            Controls.Add(detailLabel);
            progress = new ProgressBar
            {
                Left = 29,
                Top = 207,
                Width = 642,
                Height = 8,
                Style = ProgressBarStyle.Marquee,
                MarqueeAnimationSpeed = 28,
                Anchor = AnchorStyles.Top | AnchorStyles.Left | AnchorStyles.Right
            };
            Controls.Add(progress);
            activity = new TextBox
            {
                Left = 29,
                Top = 235,
                Width = 642,
                Height = 145,
                Multiline = true,
                ReadOnly = true,
                ScrollBars = ScrollBars.Vertical,
                BackColor = Color.FromArgb(14, 27, 54),
                ForeColor = Color.FromArgb(205, 217, 244),
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Consolas", 8.5F),
                Anchor = AnchorStyles.Top | AnchorStyles.Bottom | AnchorStyles.Left | AnchorStyles.Right
            };
            Controls.Add(activity);

            startButton = CreateButton("Start Project", 29, false);
            startButton.Click += async delegate { await StartProjectAsync(true); };
            openButton = CreateButton("Open Project", 163, true);
            openButton.Enabled = false;
            openButton.Click += delegate { ProjectRuntime.OpenBrowser(applicationUrl); };
            stopButton = CreateButton("Stop Project", 297, false);
            stopButton.Click += async delegate { await StopProjectAsync(); };
            closeButton = CreateButton("Close Launcher", 431, false);
            closeButton.Click += delegate { Close(); };

            Shown += async delegate { await StartProjectAsync(true); };
            FormClosing += delegate(object sender, FormClosingEventArgs eventArgs)
            {
                if (operationRunning)
                {
                    DialogResult result = MessageBox.Show(
                        "A startup or shutdown operation is still running. Close the launcher anyway? " +
                        "The operation may continue in the background.",
                        "AI Project Manager",
                        MessageBoxButtons.YesNo,
                        MessageBoxIcon.Question);
                    if (result == DialogResult.No)
                    {
                        eventArgs.Cancel = true;
                    }
                }
            };
        }

        private Button CreateButton(string text, int left, bool primary)
        {
            Button button = new Button
            {
                Left = left,
                Top = 397,
                Width = 122,
                Height = 36,
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = primary ? Color.FromArgb(79, 107, 255) : Color.FromArgb(28, 44, 78),
                ForeColor = Color.White,
                Anchor = AnchorStyles.Bottom | AnchorStyles.Left,
                Cursor = Cursors.Hand
            };
            button.FlatAppearance.BorderColor = primary
                ? Color.FromArgb(117, 139, 255)
                : Color.FromArgb(55, 75, 115);
            Controls.Add(button);
            return button;
        }

        private async Task StartProjectAsync(bool openWhenReady)
        {
            if (operationRunning)
            {
                return;
            }
            if (ProjectRuntime.IsHealthy(applicationUrl))
            {
                SetRunningState("AI Project Manager is already running.");
                if (openWhenReady)
                {
                    ProjectRuntime.OpenBrowser(applicationUrl);
                }
                return;
            }

            SetBusyState("Starting AI Project Manager", "Checking Ollama, Docker, and application services...");
            activity.Clear();
            string script = Path.Combine(root, "infra", "release", "start-local-ollama.ps1");
            int exitCode = await Task.Run(delegate
            {
                return ProjectRuntime.RunPowerShell(
                    root,
                    script,
                    "-PreferCachedImages -SkipProviderProbe",
                    AppendActivity);
            });
            if (exitCode == 0 && ProjectRuntime.IsHealthy(applicationUrl))
            {
                SetRunningState("All services are healthy and ready.");
                if (openWhenReady)
                {
                    ProjectRuntime.OpenBrowser(applicationUrl);
                }
            }
            else
            {
                SetErrorState(
                    "The project could not start",
                    "Review the activity log. Detailed logs are stored under Local AppData\\AI Project Manager.");
            }
        }

        private async Task StopProjectAsync()
        {
            if (operationRunning)
            {
                return;
            }
            SetBusyState("Stopping AI Project Manager", "Project data and built images will be preserved.");
            string script = Path.Combine(root, "infra", "release", "stop-local-demo.ps1");
            int exitCode = await Task.Run(delegate
            {
                return ProjectRuntime.RunPowerShell(root, script, string.Empty, AppendActivity);
            });
            if (exitCode == 0)
            {
                operationRunning = false;
                statusLabel.Text = "AI Project Manager is stopped";
                statusLabel.ForeColor = Color.FromArgb(205, 217, 244);
                detailLabel.Text = "Your project data is preserved. Click Start Project whenever you need it.";
                progress.Style = ProgressBarStyle.Blocks;
                progress.Value = 0;
                SetButtons(true, false, false, true);
            }
            else
            {
                SetErrorState("The project could not stop", "Review the activity log for details.");
            }
        }

        private void SetBusyState(string status, string detail)
        {
            operationRunning = true;
            statusLabel.Text = status;
            statusLabel.ForeColor = Color.White;
            detailLabel.Text = detail;
            progress.Style = ProgressBarStyle.Marquee;
            progress.MarqueeAnimationSpeed = 28;
            SetButtons(false, false, false, false);
        }

        private void SetRunningState(string detail)
        {
            operationRunning = false;
            statusLabel.Text = "AI Project Manager is ready";
            statusLabel.ForeColor = Color.FromArgb(45, 212, 191);
            detailLabel.Text = detail + " The project is available at " + applicationUrl;
            progress.Style = ProgressBarStyle.Continuous;
            progress.Value = 100;
            SetButtons(false, true, true, true);
        }

        private void SetErrorState(string status, string detail)
        {
            operationRunning = false;
            statusLabel.Text = status;
            statusLabel.ForeColor = Color.FromArgb(245, 112, 137);
            detailLabel.Text = detail;
            progress.Style = ProgressBarStyle.Blocks;
            progress.Value = 0;
            SetButtons(true, false, true, true);
        }

        private void SetButtons(bool start, bool open, bool stop, bool close)
        {
            startButton.Enabled = start;
            openButton.Enabled = open;
            stopButton.Enabled = stop;
            closeButton.Enabled = close;
        }

        private void AppendActivity(string line)
        {
            if (IsDisposed)
            {
                return;
            }
            if (InvokeRequired)
            {
                BeginInvoke(new Action<string>(AppendActivity), line);
                return;
            }
            activity.AppendText(line + Environment.NewLine);
            activity.SelectionStart = activity.TextLength;
            activity.ScrollToCaret();
            if (line.StartsWith("[", StringComparison.Ordinal) || line.Contains("ready"))
            {
                detailLabel.Text = line;
            }
        }
    }

    internal static class BrandArt
    {
        public static Bitmap CreateLogo(int size)
        {
            Bitmap bitmap = new Bitmap(size, size);
            using (Graphics graphics = Graphics.FromImage(bitmap))
            using (System.Drawing.Drawing2D.LinearGradientBrush brush =
                new System.Drawing.Drawing2D.LinearGradientBrush(
                    new Rectangle(0, 0, size, size),
                    Color.FromArgb(79, 107, 255),
                    Color.FromArgb(139, 92, 246),
                    45F))
            using (Pen pen = new Pen(Color.White, Math.Max(2F, size / 18F)))
            using (Brush white = new SolidBrush(Color.White))
            {
                graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
                graphics.FillRoundedRectangle(brush, new Rectangle(0, 0, size - 1, size - 1), size / 4);
                float scale = size / 64F;
                PointF leftTop = new PointF(17 * scale, 19 * scale);
                PointF leftBottom = new PointF(17 * scale, 45 * scale);
                PointF middle = new PointF(36 * scale, 32 * scale);
                PointF right = new PointF(49 * scale, 45 * scale);
                graphics.DrawLine(pen, leftTop, middle);
                graphics.DrawLine(pen, leftBottom, middle);
                graphics.DrawLine(pen, middle, right);
                float radius = 5 * scale;
                foreach (PointF point in new[] { leftTop, leftBottom, middle, right })
                {
                    graphics.FillEllipse(white, point.X - radius, point.Y - radius, radius * 2, radius * 2);
                }
                graphics.DrawLine(pen, 48 * scale, 12 * scale, 48 * scale, 22 * scale);
                graphics.DrawLine(pen, 43 * scale, 17 * scale, 53 * scale, 17 * scale);
            }
            return bitmap;
        }

        private static void FillRoundedRectangle(
            this Graphics graphics,
            Brush brush,
            Rectangle bounds,
            int radius)
        {
            int diameter = radius * 2;
            using (System.Drawing.Drawing2D.GraphicsPath path = new System.Drawing.Drawing2D.GraphicsPath())
            {
                path.AddArc(bounds.Left, bounds.Top, diameter, diameter, 180, 90);
                path.AddArc(bounds.Right - diameter, bounds.Top, diameter, diameter, 270, 90);
                path.AddArc(bounds.Right - diameter, bounds.Bottom - diameter, diameter, diameter, 0, 90);
                path.AddArc(bounds.Left, bounds.Bottom - diameter, diameter, diameter, 90, 90);
                path.CloseFigure();
                graphics.FillPath(brush, path);
            }
        }
    }
}

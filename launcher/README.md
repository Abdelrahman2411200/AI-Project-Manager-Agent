# Windows click-to-run launcher

`AI Project Manager.exe` is a native Windows launcher for the existing local
Docker/Ollama application. It does not replace or duplicate PostgreSQL, Ollama,
Docker, the API, workers, or the frontend. It coordinates those components and
opens the browser when the public health endpoint is ready.

## User experience

Double-click `AI Project Manager.exe` in the repository root. The launcher:

1. opens the project immediately when it is already healthy;
2. otherwise starts WSL Ollama and Docker Desktop when needed;
3. reuses cached application images, or builds them on the first launch;
4. starts PostgreSQL, migrations, the API, four workers, and the frontend;
5. waits for `/api/v1/health/ready`; and
6. opens the default browser at the configured `HTTP_PORT`.

The window also provides **Start Project**, **Open Project**, **Stop Project**,
and **Close Launcher**. Stopping preserves PostgreSQL data and Docker images.
Closing only closes the launcher; it does not stop the project.

## Build

From the repository root:

```powershell
& .\launcher\build-launcher.ps1
```

The build uses the Windows .NET Framework compiler that ships with supported
Windows installations and emits one small executable in the repository root.

## Automated verification switches

```powershell
& '.\AI Project Manager.exe' --headless-start
& '.\AI Project Manager.exe' --headless-stop
```

The process exit code is `0` on success. These switches do not open the browser.

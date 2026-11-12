<#
  启动一个「像正常人用的」Chrome 调试实例。

  与直接写死 --user-agent 的区别：
  - UA 用**本机真实 Chrome 版本**生成，和 Sec-CH-UA 客户端提示保持一致
    （UA 写 131 而 Client Hints 报 156 是典型的自动化特征）；
  - 默认**有头运行**（headless 的 UA/插件/渲染特征更容易被识别），加 -Headless 才无头；
  - 复用固定 profile，保留 cookie / localStorage，过完一次 antibot 就长期有效；
  - 支持代理：config.json 里配 proxy.server 即可挂 socks5/http 代理。

  用法:
    powershell -ExecutionPolicy Bypass -File web\launch_chrome.ps1
    powershell -ExecutionPolicy Bypass -File web\launch_chrome.ps1 -Headless
    powershell -ExecutionPolicy Bypass -File web\launch_chrome.ps1 -Proxy "socks5://127.0.0.1:1080"
#>
param(
  [switch]$Headless,
  [string]$Proxy = "",
  [switch]$NoProxy,
  [int]$Port = 9222,
  [string]$Profile = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# ---- 找 Chrome ----
$candidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { throw "未找到 chrome.exe" }

# ---- 真实版本 → 与 Client Hints 对齐的 UA ----
$ver = (Get-Item $chrome).VersionInfo.ProductVersion
$major = ($ver -split '\.')[0]
$ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/$ver Safari/537.36"

# ---- 代理 ----
if (-not $Proxy -and (Test-Path "$root\config.json")) {
  try {
    $cfg = Get-Content "$root\config.json" -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($cfg.proxy -and $cfg.proxy.enabled -and $cfg.proxy.server) { $Proxy = $cfg.proxy.server }
  } catch { }
}

if (-not $Profile) { $Profile = "$env:TEMP\ozon_cdp_prof" }
New-Item -ItemType Directory -Force -Path $Profile | Out-Null

# ---- 先清掉旧实例 ----
Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
  Where-Object { $_.CommandLine -like "*remote-debugging-port=$Port*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Start-Sleep -Milliseconds 800

$args = @(
  "--remote-debugging-port=$Port",
  "--user-data-dir=`"$Profile`"",
  "--user-agent=`"$ua`"",
  '--lang=ru-RU',
  '--no-first-run',
  '--no-default-browser-check',
  '--disable-blink-features=AutomationControlled',
  '--disable-features=Translate,OptimizationHints',
  '--window-size=1440,900',
  'https://www.ozon.ru/'
)
if ($Headless) { $args = @('--headless=new', '--disable-gpu') + $args }
if ($Proxy) { $args = @("--proxy-server=$Proxy") + $args }
elseif ($NoProxy) { $args = @('--no-proxy-server') + $args }
else {
  # 系统代理（VPN/Clash 等）经常把 ozon.ru 走挂，但直连是通的：
  # 默认只对 Ozon 域名绕过系统代理，其它站点仍走系统代理。
  $args = @('--proxy-bypass-list=*.ozon.ru;*.ozonstatic.cn;*.ozonstatic.com;<-loopback>') + $args
}

Write-Host "Chrome   : $chrome"
Write-Host "版本      : $ver  (UA 与 Client Hints 对齐)"
Write-Host "模式      : $(if ($Headless) { 'headless=new（更容易被识别）' } else { '有头（推荐）' })"
Write-Host "代理      : $(if ($Proxy) { $Proxy } elseif ($NoProxy) { '直连（--no-proxy-server）' } else { '系统代理（Ozon 域名直连）' })"
Write-Host "调试端口  : $Port"
Write-Host "Profile   : $Profile"

Start-Process -FilePath $chrome -ArgumentList $args

for ($i = 0; $i -lt 40; $i++) {
  Start-Sleep -Milliseconds 500
  try {
    $v = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 3
    Write-Host "就绪: $($v.Browser)"
    exit 0
  } catch { }
}
Write-Host "端口未就绪，请检查 Chrome 是否被安全软件拦截"
exit 1

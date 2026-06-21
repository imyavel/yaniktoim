<#
  Ф8′ — разовое заведение учёток (Admin/Nipna/Anibe) с ОДНИМ паролем + деплой воркера.
  Пишет в Cloudflare KV (USERS) ровно тот формат, что проверяет воркер
  (PBKDF2-HMAC-SHA256, 100000 итераций, соль 16 байт, base64), и деплоит свежий код
  (в т.ч. CORS для localhost). Пароль вводится СКРЫТНО — в чат/файлы не попадает.

  Перед запуском (один раз):
    npm i -g wrangler
    wrangler login            # откроет браузер, авторизуй Cloudflare
  Запуск:
    powershell -ExecutionPolicy Bypass -File seed_users.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$NS = "2a6d63cdc96c447491471c80cb62bb5c"   # id KV-namespace USERS (из wrangler.toml)
$users = @(
  @{ nick = "Admin"; role = "admin"  },
  @{ nick = "Nipna"; role = "editor" },
  @{ nick = "Anibe"; role = "editor" }
)

# wrangler доступен?
if (-not (Get-Command wrangler -ErrorAction SilentlyContinue)) {
  Write-Error "wrangler не найден. Сначала: npm i -g wrangler ; wrangler login"; exit 1
}

# пароль (скрытый ввод)
$sec = Read-Host -AsSecureString "Один пароль для всех трёх учёток"
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$pass = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
if ([string]::IsNullOrWhiteSpace($pass) -or $pass.Length -lt 4) { Write-Error "пустой/короткий пароль"; exit 1 }

function New-Record([string]$nick, [string]$role, [string]$password) {
  $salt = New-Object byte[] 16
  [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($salt)
  $kdf = New-Object System.Security.Cryptography.Rfc2898DeriveBytes(
    $password, $salt, 100000, [System.Security.Cryptography.HashAlgorithmName]::SHA256)
  $hash = $kdf.GetBytes(32)
  $kdf.Dispose()
  $rec = [ordered]@{
    nick      = $nick
    role      = $role
    salt      = [Convert]::ToBase64String($salt)
    hash      = [Convert]::ToBase64String($hash)
    createdAt = [int][DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  }
  return ($rec | ConvertTo-Json -Compress)
}

foreach ($u in $users) {
  $key = "user:" + $u.nick.ToLower()
  $json = New-Record $u.nick $u.role $pass
  $tmp = [System.IO.Path]::GetTempFileName()
  [System.IO.File]::WriteAllText($tmp, $json, (New-Object System.Text.UTF8Encoding($false)))
  Write-Host "→ $key  ($($u.role))"
  wrangler kv key put $key --path $tmp --namespace-id $NS --remote
  Remove-Item $tmp -Force
}

Write-Host "`nДеплой воркера (CORS localhost + /api/settings)…" -ForegroundColor Cyan
wrangler deploy

Write-Host "`nГотово. Логины: Admin / Nipna / Anibe — все с введённым паролем." -ForegroundColor Green
Write-Host "Проверь вход на сайте или локально (localhost теперь разрешён CORS)."

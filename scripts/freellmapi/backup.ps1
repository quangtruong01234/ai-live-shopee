# Backs up (or restores) the local freellmapi gateway (ADR-034): its SQLite database and the .env that holds ENCRYPTION_KEY.
# The provider keys in the database are AES-256-GCM ciphertext; without the exact ENCRYPTION_KEY they cannot be decrypted, so
# the two files are only useful together. freellmapi's own dashboard backups live inside the same Docker volume and die with it,
# hence this copy outside Docker.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/freellmapi/backup.ps1                     # new backup in ~/freellmapi-backup
#   powershell -ExecutionPolicy Bypass -File scripts/freellmapi/backup.ps1 -Restore <folder>   # restore one backup folder
#
# A backup folder holds plaintext-equivalent secrets (database + key). It stays in the user profile, outside this repo and
# outside any cloud-synced folder; never commit or upload it.

param(
    [string]$Restore,
    [string]$FreellmapiDir = (Join-Path $HOME 'freellmapi'),
    [string]$Dest = (Join-Path $HOME 'freellmapi-backup'),
    [string]$Project = 'freellmapi',  # compose project name; another name restores into a throwaway stack (tests)
    [int]$Keep = 10
)

$ErrorActionPreference = 'Stop'

$ComposeFile = Join-Path $FreellmapiDir 'docker-compose.yml'
$EnvFile = Join-Path $FreellmapiDir '.env'
$Service = 'freellmapi'
$DataDir = '/app/server/data'
$SnapshotInContainer = '/tmp/ailive-freeapi-backup.db'

# Runs inside the container with Node's built-in sqlite (no extra package). It never prints a key or a decrypted value.
# __MODE__ = snapshot: take a consistent online copy of the live WAL database, then check the copy.
# __MODE__ = check: check the live database as it is (used after a restore).
$CheckJs = @'
const crypto = require('node:crypto');
const { DatabaseSync, backup } = require('node:sqlite');
const KEY = '__KEY__';
const MODE = '__MODE__';
const LIVE = '__DATA__/freeapi.db';
const SNAP = '__SNAP__';
function check(path) {
  const db = new DatabaseSync(path, { readOnly: true });
  const integrity = Object.values(db.prepare('PRAGMA integrity_check').get())[0];
  const rows = db.prepare('SELECT encrypted_key, iv, auth_tag FROM api_keys').all();
  db.close();
  const key = Buffer.from(KEY, 'hex');
  let decrypted = 0;
  for (const r of rows) {
    try {
      const d = crypto.createDecipheriv('aes-256-gcm', key, Buffer.from(r.iv, 'hex'), { authTagLength: 16 });
      d.setAuthTag(Buffer.from(r.auth_tag, 'hex'));
      d.update(r.encrypted_key, 'hex');
      d.final();
      decrypted++;
    } catch (e) { /* counted as not decrypted */ }
  }
  return { integrity, keys: rows.length, decrypted };
}
(async () => {
  const out = {
    containerKeyMatches: process.env.ENCRYPTION_KEY === KEY,
    fingerprint: 'sha256:' + crypto.createHash('sha256').update(Buffer.from(KEY, 'hex')).digest('hex').slice(0, 16),
  };
  let path = LIVE;
  if (MODE === 'snapshot') {
    const src = new DatabaseSync(LIVE, { readOnly: true });
    await backup(src, SNAP);
    src.close();
    path = SNAP;
  }
  Object.assign(out, check(path));
  console.log(JSON.stringify(out));
})().catch((e) => { console.log(JSON.stringify({ error: String((e && e.message) || e) })); process.exit(1); });
'@

function Fail([string]$Message) {
    Write-Host "LỖI: $Message" -ForegroundColor Red
    exit 1
}

function Get-EncryptionKey([string]$Path) {
    if (-not (Test-Path $Path)) { Fail "không thấy $Path" }
    foreach ($line in Get-Content $Path) {
        if ($line -match '^\s*ENCRYPTION_KEY\s*=\s*"?([0-9a-fA-F]{64})"?\s*$') { return $Matches[1].ToLower() }
    }
    Fail "$Path không có ENCRYPTION_KEY dạng 64 ký tự hex"
}

function Invoke-Compose([string[]]$ComposeArgs) {
    & docker compose -p $Project -f $ComposeFile @ComposeArgs
    if ($LASTEXITCODE -ne 0) { Fail "docker compose $($ComposeArgs -join ' ') trả mã $LASTEXITCODE" }
}

function Get-RunningContainer {
    $id = (& docker compose -p $Project -f $ComposeFile ps -q $Service) | Select-Object -First 1
    if (-not $id) { Fail "container freellmapi (project '$Project') không chạy; bật Docker Desktop rồi 'docker compose up -d' trong $FreellmapiDir" }
    return $id.Trim()
}

function Invoke-Check([string]$ContainerId, [string]$Key, [string]$Mode) {
    $js = $CheckJs.Replace('__KEY__', $Key).Replace('__MODE__', $Mode).Replace('__DATA__', $DataDir).Replace('__SNAP__', $SnapshotInContainer)
    # The script (and the key inside it) goes through stdin, never the command line, so it does not show in process lists.
    $raw = $js | & docker exec -i -e NODE_NO_WARNINGS=1 $ContainerId node -
    $json = ($raw | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
    if (-not $json) { Fail "kiểm database trong container không trả kết quả (mã $LASTEXITCODE)" }
    $result = $json | ConvertFrom-Json
    if ($result.error) { Fail "kiểm database lỗi: $($result.error)" }
    return $result
}

function Assert-Healthy($Result, [string]$What) {
    if ($Result.integrity -ne 'ok') { Fail "$What hỏng (integrity_check: $($Result.integrity))" }
    if ($Result.keys -gt 0 -and $Result.decrypted -eq 0) { Fail "$What có $($Result.keys) key nhưng ENCRYPTION_KEY không giải mã được key nào" }
    if ($Result.decrypted -lt $Result.keys) {
        Write-Host "CHÚ Ý: chỉ giải mã được $($Result.decrypted)/$($Result.keys) key trong $What" -ForegroundColor Yellow
    }
}

function New-Backup {
    $key = Get-EncryptionKey $EnvFile
    $cid = Get-RunningContainer
    $result = Invoke-Check $cid $key 'snapshot'
    if (-not $result.containerKeyMatches) {
        & docker exec $cid rm -f $SnapshotInContainer | Out-Null
        Fail "ENCRYPTION_KEY trong $EnvFile khác key container đang chạy; bản sao lưu sẽ không giải mã được. Kiểm .env rồi khởi động lại freellmapi trước"
    }
    Assert-Healthy $result 'bản chụp database'

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $folder = Join-Path $Dest $stamp
    New-Item -ItemType Directory -Force $folder | Out-Null
    & docker cp "${cid}:$SnapshotInContainer" (Join-Path $folder 'freeapi.db') | Out-Null
    $copyCode = $LASTEXITCODE
    & docker exec $cid rm -f $SnapshotInContainer | Out-Null
    if ($copyCode -ne 0) { Fail "docker cp trả mã $copyCode" }
    Copy-Item $EnvFile (Join-Path $folder 'freellmapi.env')
    [ordered]@{
        created_at   = (Get-Date).ToString('o')
        fingerprint  = $result.fingerprint
        api_keys     = $result.keys
        decrypted    = $result.decrypted
        integrity    = $result.integrity
        project      = $Project
    } | ConvertTo-Json | Set-Content -Encoding utf8 (Join-Path $folder 'manifest.json')

    # Prune only folders this script made (timestamp name + manifest), oldest first.
    $ours = Get-ChildItem $Dest -Directory | Where-Object { $_.Name -match '^\d{8}-\d{6}$' -and (Test-Path (Join-Path $_.FullName 'manifest.json')) } | Sort-Object Name
    if ($Keep -gt 0 -and $ours.Count -gt $Keep) {
        $ours | Select-Object -First ($ours.Count - $Keep) | ForEach-Object { Remove-Item -Recurse -Force $_.FullName }
    }

    $size = [math]::Round((Get-Item (Join-Path $folder 'freeapi.db')).Length / 1MB, 1)
    Write-Host "Đã sao lưu freellmapi vào $folder" -ForegroundColor Green
    Write-Host "  database $size MB, integrity ok, giải mã được $($result.decrypted)/$($result.keys) key nhà cung cấp, key $($result.fingerprint)"
    return $folder
}

function Restore-Backup([string]$Folder) {
    $Folder = (Resolve-Path $Folder).Path
    $db = Join-Path $Folder 'freeapi.db'
    $backupEnv = Join-Path $Folder 'freellmapi.env'
    if (-not (Test-Path $db) -or -not (Test-Path $backupEnv)) { Fail "$Folder thiếu freeapi.db hoặc freellmapi.env" }
    $backupKey = Get-EncryptionKey $backupEnv

    # Undo point: snapshot the current state first, when there is one.
    $running = (& docker compose -p $Project -f $ComposeFile ps -q $Service) | Select-Object -First 1
    if ($running) {
        Write-Host 'Sao lưu trạng thái hiện tại trước khi khôi phục...'
        New-Backup | Out-Null
    }

    if (-not (Test-Path $EnvFile) -or (Get-EncryptionKey $EnvFile) -ne $backupKey) {
        if (Test-Path $EnvFile) {
            $aside = "$EnvFile.before-restore-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
            Copy-Item $EnvFile $aside
            Write-Host "ENCRYPTION_KEY khác bản sao lưu; .env cũ giữ ở $aside"
        }
        Copy-Item $backupEnv $EnvFile -Force
    }

    Invoke-Compose @('stop', $Service)
    # Drop the WAL/SHM of the old database: SQLite would otherwise replay the old WAL onto the restored file.
    $script = "rm -f $DataDir/freeapi.db-wal $DataDir/freeapi.db-shm && cp /restore/freeapi.db $DataDir/freeapi.db && chown node:node $DataDir/freeapi.db && chmod 600 $DataDir/freeapi.db"
    Invoke-Compose @('run', '--rm', '--no-deps', '--user', 'root', '--entrypoint', 'sh', '-v', "${Folder}:/restore:ro", $Service, '-c', $script)
    Invoke-Compose @('up', '-d', $Service)

    $cid = Get-RunningContainer
    $deadline = (Get-Date).AddSeconds(90)
    do {
        Start-Sleep -Seconds 3
        $health = (& docker inspect -f '{{.State.Health.Status}}' $cid).Trim()
    } while ($health -ne 'healthy' -and (Get-Date) -lt $deadline)
    if ($health -ne 'healthy') { Fail "freellmapi chưa healthy sau 90 s (trạng thái: $health); xem 'docker compose logs freellmapi'" }

    $result = Invoke-Check $cid $backupKey 'check'
    if (-not $result.containerKeyMatches) { Fail 'container không chạy bằng ENCRYPTION_KEY của bản sao lưu' }
    Assert-Healthy $result 'database đã khôi phục'
    Write-Host "Đã khôi phục $Folder (project '$Project'): healthy, giải mã được $($result.decrypted)/$($result.keys) key" -ForegroundColor Green
}

if (-not (Test-Path $ComposeFile)) { Fail "không thấy $ComposeFile (đặt -FreellmapiDir)" }
if ($Restore) { Restore-Backup $Restore } else { New-Backup | Out-Null }

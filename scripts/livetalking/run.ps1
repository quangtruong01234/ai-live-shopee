# Starts the LiveTalking fork for feature 005 in the current terminal (fork-protocol §5, data-model §1).
# Reads .env.example for defaults, then the repo .env on top, so the four fork-only variables always have a value.
# The app never spawns this process (research R2): the operator runs it before opening the app.
#
# Usage: powershell scripts/livetalking/run.ps1

$ErrorActionPreference = 'Stop'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$ForkDir = Join-Path $RepoRoot 'vendor\livetalking'

function Read-DotEnv {
    param([string]$Path, [hashtable]$Into)
    if (-not (Test-Path $Path)) { return }
    foreach ($raw in Get-Content -Path $Path -Encoding UTF8) {
        $line = $raw.Trim()
        if (-not $line -or $line.StartsWith('#') -or -not $line.Contains('=')) { continue }
        $key, $rest = $line.Split('=', 2)
        $Into[$key.Trim()] = $rest.Split('#', 2)[0].Trim()
    }
}

$cfg = @{}
Read-DotEnv (Join-Path $RepoRoot '.env.example') $cfg
if (-not (Test-Path (Join-Path $RepoRoot '.env'))) {
    throw 'Chưa có .env ở thư mục repo. Copy .env.example thành .env rồi điền giá trị.'
}
Read-DotEnv (Join-Path $RepoRoot '.env') $cfg

$python = $cfg['LIVETALKING_PYTHON']
if (-not $python) { $python = 'vendor/livetalking/.venv/Scripts/python.exe' }
if (-not [System.IO.Path]::IsPathRooted($python)) { $python = Join-Path $RepoRoot $python }
if (-not (Test-Path $python)) {
    throw "Không thấy Python của venv fork ở $python. Chạy scripts/livetalking/setup.ps1 trước."
}

$avatarDir = $cfg['AVATAR_DIR']
if (-not $avatarDir) { throw 'AVATAR_DIR trống trong .env.' }
if (-not [System.IO.Path]::IsPathRooted($avatarDir)) { $avatarDir = Join-Path $RepoRoot $avatarDir }
if (-not (Test-Path (Join-Path $avatarDir 'character.json'))) {
    throw "Không thấy character.json trong $avatarDir. Chạy 'uv run python -m ai_live.avatar prepare <AVATAR_DIR>' trước."
}

$port = ([System.Uri]$cfg['LIVETALKING_URL']).Port

# ailive_ext reads these from the environment; the label is drawn inside the fork's frames (constitution: AI label always visible).
foreach ($name in 'AI_LABEL_TEXT', 'AI_LABEL_POSITION', 'LIVETALKING_BATCH_SIZE', 'LIVETALKING_LIP_EVERY_N',
                  'LIVETALKING_TRANSITION_S', 'LIVETALKING_HOLD_S') {
    Set-Item -Path "Env:$name" -Value $cfg[$name]
}

# Flags checked against config.py of the pinned commit; --ailive_character is ours (an `# ailive:` hook in config.py).
$forkArgs = @(
    'app.py',
    '--model', 'wav2lip',
    '--transport', 'webrtc',
    '--max_session', '1',
    '--listenport', "$port",
    '--batch_size', $cfg['LIVETALKING_BATCH_SIZE'],
    '--ailive_character', $avatarDir
)

Write-Host "Bật fork LiveTalking ở 127.0.0.1:$port, nhân vật $avatarDir (Ctrl+C để dừng)"
Push-Location $ForkDir
try {
    & $python @forkArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

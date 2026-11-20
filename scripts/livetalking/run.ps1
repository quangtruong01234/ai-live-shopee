# Starts the LiveTalking fork for feature 005 in the current terminal (fork-protocol §5, data-model §1).
# LIVETALKING_MODEL picks the lip-sync model: wav2lip, or the character's trained ultralight (011 lipsync-selection §2).
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

$defaults = @{}
Read-DotEnv (Join-Path $RepoRoot '.env.example') $defaults
$cfg = $defaults.Clone()
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

$model = $cfg['LIVETALKING_MODEL']
if ($model -notin 'wav2lip', 'ultralight') { throw 'LIVETALKING_MODEL phải là wav2lip hoặc ultralight' }

# ailive_ext reads these from the environment; the label is drawn inside the fork's frames (constitution: AI label always visible).
$forkEnv = @('AI_LABEL_TEXT', 'AI_LABEL_POSITION', 'LIVETALKING_BATCH_SIZE')
# Clip rotation and the 010 mouth methods belong to the Wav2Lip clip path; Ultralight has one avatar and its own model
# (research R8), so they are not passed and a non-default value is reported instead of silently ignored.
$wav2lipOnly = @('LIVETALKING_LIP_EVERY_N', 'LIVETALKING_MOUTH_METHOD', 'LIVETALKING_TRANSITION_S', 'LIVETALKING_HOLD_S')
if ($model -eq 'wav2lip') {
    $forkEnv += $wav2lipOnly
} else {
    foreach ($name in $wav2lipOnly) {
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        if ($cfg[$name] -ne $defaults[$name]) { Write-Host "bỏ qua cho ultralight: $name" }
    }
}
foreach ($name in $forkEnv) {
    Set-Item -Path "Env:$name" -Value $cfg[$name]
}

# Self-check recording (ailive_ext/recorder.py): off unless AILIVE_RECORD_DIR is set; a relative dir is under the repo,
# not the fork, so recordings land in the gitignored out/ next to other measurements.
$recordDir = $cfg['AILIVE_RECORD_DIR']
if ($recordDir) {
    if (-not [System.IO.Path]::IsPathRooted($recordDir)) { $recordDir = Join-Path $RepoRoot $recordDir }
    $env:AILIVE_RECORD_DIR = $recordDir
    if ($cfg['AILIVE_RECORD_MAX_S']) { $env:AILIVE_RECORD_MAX_S = $cfg['AILIVE_RECORD_MAX_S'] }
    Write-Host "Ghi luồng tự kiểm: bật, thư mục $recordDir (POST /ailive/record/start|stop)"
}

# Flags checked against config.py of the pinned commit; --ailive_character and --ailive_teacher are ours (`# ailive:`
# hooks in config.py).
$forkArgs = @(
    'app.py',
    '--model', $model,
    '--transport', 'webrtc',
    '--max_session', '1',
    '--listenport', "$port",
    '--batch_size', $cfg['LIVETALKING_BATCH_SIZE'],
    '--ailive_character', $avatarDir
)
$modelNote = 'Wav2Lip'
if ($model -eq 'ultralight') {
    $teacher = $cfg['LIVETALKING_ULTRALIGHT_TEACHER']
    $forkArgs += @('--ailive_teacher', $teacher)
    $modelNote = "Ultralight, thầy $teacher"
}

Write-Host "Bật fork LiveTalking ở 127.0.0.1:$port, nhân vật $avatarDir, model $modelNote (Ctrl+C để dừng)"
Push-Location $ForkDir
try {
    & $python @forkArgs
    exit $LASTEXITCODE
} finally {
    Pop-Location
}

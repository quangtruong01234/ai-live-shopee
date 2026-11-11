# Builds the LiveTalking fork for feature 005 (fork-protocol §5, research R2, R11, R14).
# Clones upstream into vendor/livetalking (gitignored), pins a commit, creates the `ailive` branch and a separate
# Python 3.12 venv with torch + the upstream requirements. Never downloads model weights: those are fetched by hand
# after the user approves ADR-048 (quickstart step 3), so their licenses can be checked first.
#
# Usage: powershell scripts/livetalking/setup.ps1 [-UpstreamCommit <sha>] [-Cuda cu128|cu126]

param(
    [string]$UpstreamCommit = '',
    [ValidateSet('cu128', 'cu126')]
    [string]$Cuda = 'cu128'
)

$ErrorActionPreference = 'Stop'

$LIVETALKING_REPO = 'https://github.com/lipku/LiveTalking'
# Upstream main on 2026-11-07, when the fork was first built (plan 005, fork-protocol §5).
$LIVETALKING_UPSTREAM_COMMIT = 'c7269433a2b6ecebcd9342445d2ecc882c98b0da'
$TORCH_VERSION = '2.9.1'
$PYTHON_VERSION = '3.12'

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot '..\..')
$ForkDir = Join-Path $RepoRoot 'vendor\livetalking'
$VenvPython = Join-Path $ForkDir '.venv\Scripts\python.exe'

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Lệnh thất bại (mã $LASTEXITCODE): $Exe $($Arguments -join ' ')"
    }
}

if (-not $UpstreamCommit) { $UpstreamCommit = $LIVETALKING_UPSTREAM_COMMIT }
if (-not $UpstreamCommit) {
    throw 'Chưa ghim commit LiveTalking. Truyền -UpstreamCommit <sha> hoặc điền $LIVETALKING_UPSTREAM_COMMIT trong setup.ps1.'
}

foreach ($tool in 'git', 'uv') {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Không tìm thấy '$tool' trong PATH." }
}

# Clone once; later runs reuse the checkout so local `ailive` commits are never overwritten.
if (-not (Test-Path (Join-Path $ForkDir '.git'))) {
    Write-Host "Clone $LIVETALKING_REPO vào $ForkDir"
    New-Item -ItemType Directory -Force (Split-Path $ForkDir) | Out-Null
    Invoke-Native git @('clone', $LIVETALKING_REPO, $ForkDir)
} else {
    Write-Host "Đã có $ForkDir, bỏ qua bước clone"
    Invoke-Native git @('-C', $ForkDir, 'fetch', 'origin')
}

# TODO: R2, where the `ailive` branch is pushed (private remote or local only). Until then it is created locally
# from the pinned commit; an existing branch is checked out as is.
& git -C $ForkDir rev-parse --verify --quiet ailive | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host 'Nhánh ailive đã có, checkout giữ nguyên thay đổi'
    Invoke-Native git @('-C', $ForkDir, 'checkout', 'ailive')
} else {
    Write-Host "Tạo nhánh ailive từ commit $UpstreamCommit"
    Invoke-Native git @('-C', $ForkDir, 'checkout', '-b', 'ailive', $UpstreamCommit)
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Tạo venv Python $PYTHON_VERSION ở $ForkDir\.venv"
    Invoke-Native uv @('venv', '--python', $PYTHON_VERSION, (Join-Path $ForkDir '.venv'))
}

# torch comes from the PyTorch index first so requirements.txt cannot pull a CPU-only build (research R11).
Write-Host "Cài torch $TORCH_VERSION ($Cuda)"
Invoke-Native uv @('pip', 'install', '--python', $VenvPython,
    "torch==$TORCH_VERSION", 'torchvision', 'torchaudio',
    '--index-url', "https://download.pytorch.org/whl/$Cuda")

Write-Host 'Cài requirements.txt của LiveTalking'
Invoke-Native uv @('pip', 'install', '--python', $VenvPython, '-r', (Join-Path $ForkDir 'requirements.txt'))
# The ailive_ext tests run in this venv (plan.md: pytest of the fork, no GPU); same runner as the app.
Invoke-Native uv @('pip', 'install', '--python', $VenvPython, 'pytest')

Write-Host ''
Write-Host 'Xong. Kiểm CUDA (quickstart bước 1):'
Write-Host "  $VenvPython -c `"import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.get_arch_list())`""
Write-Host '  Kỳ vọng: True, GeForce GTX 1650 Ti, có sm_75. Sai thì chạy lại với -Cuda cu126 (research R11).'
Write-Host ''
Write-Host 'Tải model bằng tay, chỉ sau khi người dùng duyệt ADR-048 (quickstart bước 3); không commit:'
Write-Host '  - wav2lip256.pth (thư mục Google Drive / Quark trong README LiveTalking) -> vendor/livetalking/models/wav2lip.pth'
Write-Host '  - https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth'
Write-Host '    -> vendor/livetalking/avatars/wav2lip/face_detection/detection/sfd/s3fd.pth'
Write-Host '  - Ghi sha256 hai file vào docs/DECISIONS.md, ADR-048.'

# Schedules a one-time Windows task that reopens Claude Code in this repo shortly after the usage limit resets, so planned
# work continues while nobody is at the keyboard. Used by the `/schedule-resume` command; when the limit is already hit the
# model cannot run, so call it from the prompt with `!` (the shell runs it directly, no model call).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/claude/schedule_resume.ps1 -At 10:00   # reset time; runs at 10:01
#   ... -At 10am -DelayMinutes 2 -New -Prompt "..."                                       # new session, own prompt
#   ... -Status | -Cancel
#
# The task runs only while this Windows user is logged on (the screen may be locked) so the Claude window is visible.
# It wakes the PC if wake timers are allowed, and starts as soon as possible if the PC was asleep at that minute.

param(
    [string]$At,
    [int]$DelayMinutes = 1,
    [string]$Prompt,
    [switch]$New,
    [ValidateSet('acceptEdits', 'auto', 'bypassPermissions', 'manual', 'dontAsk', 'plan')]
    [string]$PermissionMode = 'auto',
    [switch]$Status,
    [switch]$Cancel,
    [switch]$DryRun,
    [string]$ClaudePath  # tests only: a stand-in for the claude command
)

$ErrorActionPreference = 'Stop'

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$TaskName = 'ClaudeResume-' + (Split-Path $RepoRoot -Leaf)
$WorkDir = Join-Path $RepoRoot 'out\claude-resume'  # out/ is gitignored
$Launcher = Join-Path $WorkDir 'launch.ps1'
$LogFile = Join-Path $WorkDir 'history.log'

$DefaultPrompt = 'Hạn mức Claude đã reset, đây là phiên tự bật lại theo lịch hẹn. Làm tiếp đúng việc đang dở trước lúc hết hạn mức. ' +
    'Nếu không còn việc dở thì đọc progress/STATUS.md, mục next_step, và làm tiếp theo kế hoạch. ' +
    'Giữ mọi quy tắc trong CLAUDE.md: chỉ commit khi người dùng bảo, không push, không dùng dịch vụ tốn tiền. ' +
    'Việc cần người dùng quyết thì gom lại báo ở cuối.'

function Get-Task { Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue }

if ($Cancel) {
    if (Get-Task) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Đã hủy lịch $TaskName."
    } else {
        Write-Output 'Không có lịch nào để hủy.'
    }
    exit 0
}

if ($Status) {
    $task = Get-Task
    if (-not $task) { Write-Output 'Chưa có lịch nào.'; exit 0 }
    $info = $task | Get-ScheduledTaskInfo
    Write-Output "Lịch $TaskName ($($task.State)): chạy lúc $($info.NextRunTime); lần chạy trước $($info.LastRunTime), mã kết quả $($info.LastTaskResult)."
    exit 0
}

function ConvertTo-ResetTime([string]$text) {
    # Accepts what the limit message and people say: 10:00, 10h, 10h30, 10am, 10:30pm, 22:15, or a full date and time.
    $t = $text.Trim().ToLowerInvariant()
    if ($t -match '^(\d{1,2})(?:[:h](\d{2})?)?\s*(am|pm)?$') {
        $hour = [int]$Matches[1]
        $minute = if ($Matches[2]) { [int]$Matches[2] } else { 0 }
        if ($Matches[3] -eq 'pm' -and $hour -lt 12) { $hour += 12 }
        if ($Matches[3] -eq 'am' -and $hour -eq 12) { $hour = 0 }
        if ($hour -gt 23 -or $minute -gt 59) { throw "Giờ không hợp lệ: '$text'." }
        $when = (Get-Date).Date.AddHours($hour).AddMinutes($minute)
        # A reset time already past today means tomorrow's.
        if ($when.AddMinutes($DelayMinutes) -le (Get-Date)) { $when = $when.AddDays(1) }
        return $when
    }
    try { return [datetime]::Parse($text) } catch { throw "Không hiểu giờ '$text'. Ví dụ: 10:00, 10h30, 10am, '2026-11-14 10:00'." }
}

if (-not $At) { throw 'Thiếu giờ reset hạn mức. Ví dụ: -At 10:00 (máy sẽ bật Claude lúc 10:01).' }
if ($DelayMinutes -lt 0) { throw '-DelayMinutes phải >= 0.' }
$runAt = (ConvertTo-ResetTime $At).AddMinutes($DelayMinutes)
if ($runAt -le (Get-Date)) { throw "Giờ chạy $runAt đã qua." }

if (-not $ClaudePath) {
    $cmd = Get-Command claude -CommandType ExternalScript, Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $cmd) { throw 'Không tìm thấy lệnh claude trong PATH.' }
    $ClaudePath = $cmd.Source
}
if (-not $Prompt) { $Prompt = $DefaultPrompt }

$claudeArgs = @()
if (-not $New) { $claudeArgs += '--continue' }
$claudeArgs += @('--permission-mode', $PermissionMode, $Prompt)

function Quote([string]$s) { "'" + $s.Replace("'", "''") + "'" }

# Runs in the launcher before claude takes over the console. The new window opens behind whatever the user has open, and
# the old Claude window still shows the limit message, so people type there and think nothing restarted. Hence: a toast,
# the window brought to the front, and a warning about other Claude windows (two of them on one session edit the same files).
$notifyBlock = @'
$others = @(Get-Process -Name claude -ErrorAction SilentlyContinue).Count
$body = 'Làm tiếp trong cửa sổ "Claude Code: tự chạy tiếp". '
if ($others -gt 0) { $body += "Đang có $others cửa sổ Claude khác: đóng cửa sổ cũ (gõ /exit) để hai phiên không sửa đè nhau." }
try {
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
    $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $texts = $xml.GetElementsByTagName('text')
    $texts.Item(0).AppendChild($xml.CreateTextNode('Claude Code đã tự bật lại')) | Out-Null
    $texts.Item(1).AppendChild($xml.CreateTextNode($body)) | Out-Null
    $appId = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe'
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($appId).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
} catch { }
try {
    Add-Type -Namespace ClaudeResume -Name Win -MemberDefinition @"
[DllImport("kernel32.dll")] public static extern System.IntPtr GetConsoleWindow();
[DllImport("user32.dll")] public static extern bool ShowWindow(System.IntPtr h, int cmd);
[DllImport("user32.dll")] public static extern bool SetForegroundWindow(System.IntPtr h);
[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, System.UIntPtr extra);
"@
    $h = [ClaudeResume.Win]::GetConsoleWindow()
    [ClaudeResume.Win]::ShowWindow($h, 9) | Out-Null  # SW_RESTORE
    # Windows only lets a background process take the foreground right after a key event; a lone Alt press is harmless.
    [ClaudeResume.Win]::keybd_event(0x12, 0, 0, [UIntPtr]::Zero)
    [ClaudeResume.Win]::keybd_event(0x12, 0, 2, [UIntPtr]::Zero)
    [ClaudeResume.Win]::SetForegroundWindow($h) | Out-Null
} catch { }
Write-Host ('>>> ' + $body) -ForegroundColor Yellow
'@

New-Item -ItemType Directory -Force -Path $WorkDir | Out-Null
$launcherBody = @(
    '# Written by scripts/claude/schedule_resume.ps1; overwritten on every schedule.',
    "Set-Location -LiteralPath $(Quote $RepoRoot)",
    "`$host.UI.RawUI.WindowTitle = 'Claude Code: tự chạy tiếp sau khi hạn mức reset'",
    "Add-Content -LiteralPath $(Quote $LogFile) -Encoding UTF8 -Value (`"`$(Get-Date -Format s) start`")",
    $notifyBlock,
    "`$claudeArgs = @($(($claudeArgs | ForEach-Object { Quote $_ }) -join ', '))",
    "& $(Quote $ClaudePath) @claudeArgs",
    "Add-Content -LiteralPath $(Quote $LogFile) -Encoding UTF8 -Value (`"`$(Get-Date -Format s) exit `$LASTEXITCODE`")"
) -join "`r`n"
# UTF8 in Windows PowerShell 5.1 writes a BOM, which it needs to read the Vietnamese prompt back correctly.
Set-Content -LiteralPath $Launcher -Value $launcherBody -Encoding UTF8

$mode = if ($New) { 'phiên mới' } else { 'tiếp phiên gần nhất (--continue)' }
if ($DryRun) {
    Write-Output "Thử (không đặt lịch): sẽ chạy lúc $($runAt.ToString('HH:mm dd/MM/yyyy')), $mode, quyền '$PermissionMode'. Launcher: $Launcher"
    exit 0
}

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $RepoRoot `
    -Argument "-NoExit -ExecutionPolicy Bypass -File `"$Launcher`""
$trigger = New-ScheduledTaskTrigger -Once -At $runAt
# Drop the task by itself 12 h after its window so old schedules do not pile up.
$trigger.EndBoundary = $runAt.AddHours(12).ToString('yyyy-MM-ddTHH:mm:sszzz')
$settings = New-ScheduledTaskSettingsSet -WakeToRun -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -DeleteExpiredTaskAfter (New-TimeSpan -Days 1)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
    -Description "Bật lại Claude Code ở $RepoRoot sau khi hạn mức reset." -Force | Out-Null

Write-Output "Đã hẹn: $($runAt.ToString('HH:mm dd/MM/yyyy')) mở Claude Code ở repo này, $mode, quyền '$PermissionMode'."
Write-Output 'Xem lịch: thêm -Status. Hủy: thêm -Cancel. Nhật ký chạy: out/claude-resume/history.log'

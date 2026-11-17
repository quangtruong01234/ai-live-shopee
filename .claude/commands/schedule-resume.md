---
description: Schedule Claude Code to reopen in this repo right after the usage limit resets and continue the planned work
argument-hint: "<reset time, e.g. 10:00 | 10am | 10h30> [new] [delay=N] [mode=auto|acceptEdits|...] [cancel|status] [note to add]"
---

You are scheduling a one-time Windows task that reopens Claude Code in this repo after the usage limit resets, using
`scripts/claude/schedule_resume.ps1`. Reply to the user in Vietnamese.

Arguments from the user: $ARGUMENTS

## Steps
1. Parse the arguments:
   - `status` → run the script with `-Status`; `cancel` → `-Cancel`. Report the output and stop.
   - Reset time → `-At`. If no time was given, look for the latest usage-limit message in this conversation
     ("limit … resets 10am" and similar) and use its time. If there is none, ask the user for the reset time; do not guess.
   - `new` → `-New` (fresh session that starts from `progress/STATUS.md`); default continues the most recent session.
   - `delay=N` → `-DelayMinutes N` (default 1). `mode=X` → `-PermissionMode X` (default `auto`, the mode the user works in).
   - Any remaining free text is a note for the resumed session: build `-Prompt` from the script's default prompt plus that note
     (Vietnamese, one paragraph, no double quotes).
2. Before scheduling, make sure the work to resume is written down: if `progress/STATUS.md` `next_step` does not describe the
   current plan, update it (one or two lines) so a resumed session that lost context still knows what to do.
3. Run: `powershell -ExecutionPolicy Bypass -File scripts/claude/schedule_resume.ps1 -At <time> [options]`.
4. Report in Vietnamese: the run time, continue or new session, permission mode, and how to check or cancel
   (`/schedule-resume status`, `/schedule-resume cancel`). Remind the user that the laptop must stay on and logged in
   (screen may be locked), plugged in, and that once the limit is already hit this command cannot run (the model is out of
   quota); then they type in the prompt instead:
   `! powershell -ExecutionPolicy Bypass -File scripts/claude/schedule_resume.ps1 -At <time>`
   Also say that the resumed session opens in a **new** window (with a Windows toast, brought to the front): close the old
   window once the limit is hit (`/exit`) and continue in the new one, so two windows do not edit the same session and files.

## Do not
- Schedule more than one task: the script replaces the previous schedule for this repo.
- Use `bypassPermissions` unless the user asked for it by name.

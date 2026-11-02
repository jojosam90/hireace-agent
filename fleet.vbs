' Keeps the HireAce monitor (fleet.ps1) running, with no window, from Windows sign-in.
' It starts again if it stops or after an update, unless it says not to:
' 3 = it is already running, 4 = no portal is set up for this PC.
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
Do
  code = shell.Run("powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "\fleet.ps1""", 0, True)
  If code = 3 Or code = 4 Then Exit Do
  WScript.Sleep 15000
Loop

' Starts HireAce with no window at all: the desktop icon runs this.
' (powershell -WindowStyle Hidden is not enough: on Windows 11, Windows Terminal
' opens it in a terminal window anyway; wscript starts it hidden from the start.)
Set shell = CreateObject("WScript.Shell")
folder = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = folder
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & folder & "\start.ps1"" -Background", 0, False

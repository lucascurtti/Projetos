Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
base = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = base & "\.venv\Scripts\pythonw.exe"
app = base & "\app.py"

If Not fso.FileExists(pythonw) Then
  MsgBox "Execute setup_windows.bat primeiro.", 48, "SubSync Studio"
  WScript.Quit 1
End If

cmd = Chr(34) & pythonw & Chr(34) & " " & Chr(34) & app & Chr(34)
shell.Run cmd, 0, False

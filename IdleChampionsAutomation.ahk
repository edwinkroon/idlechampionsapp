; Idle Champions of the Forgotten Realms - Automatisering
; AutoHotkey v2
; Start/stop: Ctrl+Alt+A

#Requires AutoHotkey v2.0
Persistent

SetKeyDelay 50, 50
; Venster zoeken: titel kan ergens in de venstertitel staan (niet alleen aan het begin)
SetTitleMatchMode 2

; ============ INSTELLINGEN (pas aan naar wens) ============
; Zoekvenster: deel van de venstertitel van het spel (bijv. "Idle Champions" of "Forgotten Realms")
WindowTitle := "Idle Champions"

; Levelen: interval1234567890 in seconden (elke X seconden ` + F1-F12)
LevelIntervalSeconds := 20

; Auto progress: aan (elke X min toets G sturen)? false = geen auto progress
EnableAutoProgress := false
; Interval in minuten (alleen als EnableAutoProgress = true)
AutoProgressIntervalMinutes := 5

; Special abilities: elke X minuten toetsen 1 t/m 9 en 0
AbilitiesIntervalMinutes := 1

; Level click damage (backtick) meenemen bij levelen? true = ja, false = nee
LevelClickDamage := true

; Welke champions levelen: F12 eerst, aflopend naar F1
LevelChampions := "12,11,10,9,8,7,6,5,4,3,2,1"

; Pauze tussen toetsen in ms – hoger = meer tijd tussen F12, F11, F10… (champions zijn even “disabled” na levelen)
KeyDelayMs := 80

; Wacht na venster activeren (ms) – sommige spellen hebben even nodig om toetsen te accepteren
ActivateSleepMs := 400

; Stuur toetsen ZONDER het spelvenster focus te geven (je kunt doorwerken). ControlSend naar het venster.
; Werkt niet bij alle spellen; als er niet geleveld wordt, zet op false zodat het venster wel geactiveerd wordt.
SendWithoutFocus := true

; Macro: opname en afspelen van muiskliks
; Bestand waar opgenomen kliks worden opgeslagen (relatief t.o.v. spelvenster)
MacroFile := A_ScriptDir "\IdleChampionsMacro.txt"
; Afspelen: elke X seconden de opgenomen kliks uitvoeren (0 = alleen handmatig afspelen via hotkey)
MacroPlaybackIntervalSeconds := 300

; ============ INTERNE VARIABELEN ============
Running := false
MacroRecording := false
MacroPlaying := false
MacroClicks := []       ; array van {x, y, delay} relatief t.o.v. spelvenster
MacroLastClickTick := 0
MacroPlaybackTimerMs := 0
LevelTimerMs := LevelIntervalSeconds * 1000
AutoProgressTimerMs := AutoProgressIntervalMinutes * 60 * 1000
AbilitiesTimerMs := AbilitiesIntervalMinutes * 60 * 1000
MacroPlaybackTimerMs := MacroPlaybackIntervalSeconds * 1000

; ============ HOTKEY: Start/Stop (Ctrl+Alt+A) ============
^!a:: {
  global Running, LevelTimerMs, AutoProgressTimerMs, AbilitiesTimerMs, EnableAutoProgress
  Running := !Running
  if Running {
    SetTimer LevelLoop, LevelTimerMs
    if EnableAutoProgress
      SetTimer AutoProgressLoop, AutoProgressTimerMs
    SetTimer AbilitiesLoop, AbilitiesTimerMs
    LevelLoop()   ; eerste level-ronde meteen, daarna om de LevelIntervalSeconds
    TrayTip "Idle Champions", "Automatisering GESTART – level + abilities" . (EnableAutoProgress ? " + auto progress" : ""), 1
  } else {
    SetTimer LevelLoop, 0
    SetTimer AutoProgressLoop, 0
    SetTimer AbilitiesLoop, 0
    TrayTip "Idle Champions", "Automatisering GESTOPT", 1
  }
}

; ============ Venster vinden (zonder te activeren) ============
GetGameHwnd() {
  global WindowTitle
  hwnd := WinExist(WindowTitle)
  return hwnd ? hwnd : 0
}

; ============ LEVEL-LUS: backtick + F12..F1 ============
LevelLoop() {
  global Running, LevelClickDamage, LevelChampions, KeyDelayMs, ActivateSleepMs, SendWithoutFocus
  if !Running
    return
  hwnd := SendWithoutFocus ? GetGameHwnd() : ActivateGame()
  if !hwnd
    return
  if !SendWithoutFocus
    Sleep ActivateSleepMs
  if LevelClickDamage {
    SendKeyToGame(hwnd, "{sc029}")  ; backtick-toets (links van 1)
    Sleep KeyDelayMs
  }
  for part in StrSplit(LevelChampions, ",") {
    try
      idx := Integer(Trim(part))
    catch
      continue
    if idx >= 1 && idx <= 12 {
      SendKeyToGame(hwnd, "F" . idx)
      Sleep KeyDelayMs
    }
  }
  ; Na F1 nog een backtick (`) in dezelfde cyclus
  SendKeyToGame(hwnd, "{sc029}")  ; backtick-toets (links van 1)
  Sleep KeyDelayMs
}

; ============ AUTO PROGRESS-LUS: toets G (toggle) ============
AutoProgressLoop() {
  global Running, ActivateSleepMs, SendWithoutFocus
  if !Running
    return
  hwnd := SendWithoutFocus ? GetGameHwnd() : ActivateGame()
  if !hwnd
    return
  if !SendWithoutFocus
    Sleep ActivateSleepMs
  SendKeyToGame(hwnd, "g")
}

; ============ SPECIAL ABILITIES-LUS: elke minuut toetsen 1 t/m 9 en 0 ============
AbilitiesLoop() {
  global Running, KeyDelayMs, ActivateSleepMs, SendWithoutFocus
  if !Running
    return
  hwnd := SendWithoutFocus ? GetGameHwnd() : ActivateGame()
  if !hwnd
    return
  if !SendWithoutFocus
    Sleep ActivateSleepMs
  for key in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"] {
    SendKeyToGame(hwnd, key)
    Sleep KeyDelayMs
  }
}

; ============ Venster activeren ============
; Retourneert hwnd van het venster als gevonden en geactiveerd, anders 0
ActivateGame() {
  global WindowTitle
  hwnd := WinExist(WindowTitle)
  if !hwnd
    return 0
  try {
    WinActivate "ahk_id " . hwnd
    WinWaitActive "ahk_id " . hwnd,, 3
    return hwnd
  }
  return 0
}

; Toetsen naar het spelvenster sturen (ook als focus even weg is)
SendKeyToGame(hwnd, key) {
  try
    ControlSend key, "", "ahk_id " . hwnd
}

; ============ MACRO: Opname (Ctrl+Alt+R) en afspelen (Ctrl+Alt+P) ============
; Bij opname: linkermuisknopprikken worden opgeslagen relatief t.o.v. het spelvenster.
; Afspelen: opgenomen kliks uitvoeren; interval instelbaar via MacroPlaybackIntervalSeconds.

~LButton:: {
  global MacroRecording, MacroClicks, MacroLastClickTick, WindowTitle
  if !MacroRecording
    return
  hwnd := WinExist(WindowTitle)
  if !hwnd {
    TrayTip "Macro", "Spelvenster niet gevonden – klik niet opgenomen.", 2
    return
  }
  try WinGetPos &winX, &winY,,, "ahk_id " hwnd
  catch
    return
  MouseGetPos &mx, &my
  delay := MacroLastClickTick ? (A_TickCount - MacroLastClickTick) : 0
  MacroLastClickTick := A_TickCount
  MacroClicks.Push({x: mx - winX, y: my - winY, delay: delay})
  TrayTip "Macro", "Klik " MacroClicks.Length " opgenomen", 1
}

^!r:: {
  global MacroRecording, MacroClicks, MacroLastClickTick, MacroFile, WindowTitle
  MacroRecording := !MacroRecording
  if MacroRecording {
    MacroClicks := []
    MacroLastClickTick := 0
    TrayTip "Macro", "Opname GESTART – doe je kliks in/op het spelvenster. Ctrl+Alt+R om te stoppen.", 3
    return
  }
  ; Stoppen en opslaan
  if MacroClicks.Length = 0 {
    TrayTip "Macro", "Geen kliks opgenomen.", 2
    return
  }
  try {
    f := FileOpen(MacroFile, "w")
    f.Write("x,y,delay`n")
    for c in MacroClicks
      f.Write(c.x "," c.y "," c.delay "`n")
    f.Close()
  } catch as err {
    TrayTip "Macro", "Opslaan mislukt: " err.Message, 3
    return
  }
  TrayTip "Macro", MacroClicks.Length " kliks opgeslagen in " MacroFile, 2
}

^!p:: {
  global MacroPlaying, MacroPlaybackTimerMs, MacroPlaybackIntervalSeconds
  MacroPlaying := !MacroPlaying
  if MacroPlaying {
    if MacroPlaybackIntervalSeconds > 0
      SetTimer MacroPlaybackLoop, MacroPlaybackTimerMs
    ok := MacroPlaybackLoop()
    if ok
      TrayTip "Macro", "Afspelen GESTART. Ctrl+Alt+P om te stoppen.", 2
  } else {
    SetTimer MacroPlaybackLoop, 0
    TrayTip "Macro", "Afspelen GESTOPT", 1
  }
}

; Retourneert true als afspelen is uitgevoerd, false bij fout (en toont MsgBox)
MacroPlaybackLoop() {
  global WindowTitle, MacroFile
  hwnd := WinExist(WindowTitle)
  if !hwnd {
    MsgBox "Spelvenster niet gevonden.`n`nZorg dat Idle Champions open is en dat de venstertitel '" WindowTitle "' bevat.", "Macro afspelen", "Icon!"
    return false
  }
  if !FileExist(MacroFile) {
    MsgBox "Geen macrobestand gevonden.`n`nVerwacht: " MacroFile "`n`nEerst opnemen met Ctrl+Alt+R (opname stoppen slaat het bestand op).", "Macro afspelen", "Icon!"
    return false
  }
  clicks := []
  loop read, MacroFile {
    if A_Index = 1 && InStr(A_LoopReadLine, "x,y")
      continue
    line := Trim(A_LoopReadLine)
    if line = ""
      continue
    parts := StrSplit(line, ",")
    if parts.Length >= 3 {
      try {
        clicks.Push({x: Integer(parts[1]), y: Integer(parts[2]), delay: Integer(parts[3])})
      } catch
        continue
    }
  }
  if clicks.Length = 0 {
    MsgBox "Geen geldige kliks in macrobestand.`n`nBestand: " MacroFile "`n`nOpnieuw opnemen met Ctrl+Alt+R.", "Macro afspelen", "Icon!"
    return false
  }
  try WinGetPos &winX, &winY,,, "ahk_id " hwnd
  catch {
    MsgBox "Kon vensterpositie niet lezen.", "Macro afspelen", "Icon!"
    return false
  }
  WinActivate "ahk_id " hwnd
  WinWaitActive "ahk_id " hwnd,, 2
  Sleep 100
  for c in clicks {
    Sleep c.delay
    Click winX + c.x, winY + c.y
  }
  return true
}

; ============ TEST: Ctrl+Alt+T of Ctrl+Shift+T = vind venster, pop-up met resultaat, stuur 1x F12 ============
; Er verschijnt een venster in het midden van het scherm – kijk in het spel of er geleveld wordt
^!t:: {   ; Ctrl+Alt+T
  RunTest()
}
^+t:: {   ; Ctrl+Shift+T (alternatief als Ctrl+Alt+T door iets anders wordt gebruikt)
  RunTest()
}

RunTest() {
  global WindowTitle
  id := WinExist(WindowTitle)
  if !id {
    MsgBox "Venster NIET gevonden.`n`nGezochte titel: " . WindowTitle . "`n`nControleer of Idle Champions open is en pas WindowTitle aan in het script.", "Idle Champions – Test", "Icon!"
    return
  }
  title := WinGetTitle("ahk_id " . id)
  WinActivate "ahk_id " . id
  Sleep 400
  SendInput "F12"
  MsgBox "Venster gevonden: " . title . "`n`nF12 is verzonden. Kijk in het spel of champion 12 geleveld wordt.", "Idle Champions – Test", "Iconi"
}

; ============ Eerste startmelding – belangrijk: druk Ctrl+Alt+A om te starten ============
MsgBox "Idle Champions script is geladen.`n`n• Ctrl+Alt+A = levelen starten/stoppen`n• Ctrl+Alt+R = macro opname (muiskliks) starten/stoppen`n• Ctrl+Alt+P = macro afspelen starten/stoppen`n`nZorg dat Idle Champions open staat.", "Idle Champions – Automatisering", "Iconi"
TrayTip "Idle Champions", "Ctrl+Alt+A levelen | Ctrl+Alt+R opname | Ctrl+Alt+P afspelen", 1

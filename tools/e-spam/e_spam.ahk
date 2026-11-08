; ============================================================
;  E 연타 매크로 (AutoHotkey v2)
;  - F12      : 켜기 / 끄기
;  - 켜진 상태에서 마우스 왼쪽 버튼을 누르고 있는 동안 E 를 연타
;  - Ctrl+F12 : 프로그램 종료 (상태 창의 X 로도 종료)
;  - 연타 속도는 상태 창의 슬라이더로 조절 (자동 저장)
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
;@Ahk2Exe-SetName E 연타
;@Ahk2Exe-SetDescription E 연타 매크로

SendMode "Input"
ListLines False
KeyHistory 0
A_MaxHotkeysPerInterval := 10000
DllCall("winmm\timeBeginPeriod", "UInt", 1)   ; 대기를 1ms 단위로 정확하게
OnExit 종료정리

설정파일 := A_ScriptDir "\e_spam.ini"
간격 := Integer(IniRead(설정파일, "설정", "간격", 8))   ; ms (8 = 초당 약 60회). 누른 시간 = 뗀 시간 = 간격
간격 := Max(1, Min(30, 간격))
켜짐 := false

; ---- 상태 창 ------------------------------------------------
창 := Gui("+AlwaysOnTop -MaximizeBox", "E 연타")
창.BackColor := "White"
창.SetFont("s22 bold", "Malgun Gothic")
상태 := 창.Add("Text", "w220 h60 Center +0x200 cWhite", "")   ; 0x200 = 세로 가운데
창.SetFont("s10 norm")
버튼 := 창.Add("Button", "w220 h32", "켜기 / 끄기  (F12)")
속도글 := 창.Add("Text", "w220 Center", "")
슬라이더 := 창.Add("Slider", "w220 Range1-30 Invert", 간격)   ; 왼쪽 = 느림, 오른쪽 = 빠름
창.SetFont("s9")
창.Add("Text", "w220 Center cGray", "좌클릭 누르는 동안 E 연타`n렉/씹힘 → 슬라이더를 왼쪽으로`nCtrl+F12 또는 X = 종료")
버튼.OnEvent("Click", (*) => 전환())
슬라이더.OnEvent("Change", 속도변경)
창.OnEvent("Close", (*) => ExitApp())
화면갱신()
속도글갱신()
창.Show("x20 y20 NoActivate")

전환() {
    global 켜짐
    켜짐 := !켜짐
    if !켜짐
        SendInput "{Blind}{vk45 up}"
    화면갱신()
}

화면갱신() {
    상태.Text := 켜짐 ? "ON" : "OFF"
    상태.Opt(켜짐 ? "Background2E9E44" : "Background9A9A9A")
    상태.Redraw()
}

속도변경(*) {
    global 간격
    간격 := 슬라이더.Value
    속도글갱신()
    try IniWrite 간격, 설정파일, "설정", "간격"
}

속도글갱신() {
    속도글.Text := "속도: 초당 약 " Round(1000 / (간격 * 2)) "회"
}

종료정리(*) {
    SendInput "{Blind}{vk45 up}"
    DllCall("winmm\timeEndPeriod", "UInt", 1)
}

; AutoHotkey 의 Sleep 은 최소 약 15ms 라서 속도 조절이 안 됨 → 직접 정밀하게 대기
정밀대기(ms) {
    static 주파수 := 0
    if !주파수
        DllCall("QueryPerformanceFrequency", "Int64*", &주파수)
    시작 := 0, 지금 := 0
    DllCall("QueryPerformanceCounter", "Int64*", &시작)
    끝 := 시작 + 주파수 * ms // 1000
    if ms > 1
        DllCall("Sleep", "UInt", ms - 1)       ; 대부분은 쉬면서 대기 (CPU 절약)
    loop                                       ; 남은 1ms 미만은 정확하게 맞춤
        DllCall("QueryPerformanceCounter", "Int64*", &지금)
    until 지금 >= 끝
}

; ---- 단축키 -------------------------------------------------
$F12::전환()
$^F12::ExitApp

; 연타하는 동안 Ctrl 을 막아 두는 단축키 (평소엔 꺼져 있음)
;  - 키보드는 Ctrl 을 누르고 있으면 계속 "Ctrl 눌림" 신호를 보내서, 막지 않으면 Ctrl 이 다시 눌림
Ctrl막기(*) => 0
for 키 in ["*LCtrl", "*RCtrl", "*LCtrl up", "*RCtrl up"]
    Hotkey 키, Ctrl막기, "Off"

Ctrl막기켜기(켜기) {
    ; 단축키 안에서 Hotkey 를 쓰면 그 단축키의 조건(#HotIf)을 따라가서 오류가 남
    ; → 조건 없음으로 되돌린 뒤 켜고 끄기. 혹시 실패해도 E 연타는 멈추지 않게 try
    HotIf
    for 키 in ["*LCtrl", "*RCtrl", "*LCtrl up", "*RCtrl up"]
        try Hotkey 키, 켜기 ? "On" : "Off"
}

#HotIf 켜짐 && !WinActive("ahk_id " 창.Hwnd)   ; 상태 창 클릭할 땐 연타 안 함
*~LButton:: {                  ; * : Ctrl/Shift/Alt 를 누르고 있어도 작동, ~ : 원래 좌클릭도 그대로 동작
    ; Ctrl 을 누르고 있으면: 연타 시작할 때 Ctrl 을 한 번만 떼고, 끝나면 한 번만 다시 누름
    ; → 연타 중에는 게임에 Ctrl 없이 E 만 들어감 (Ctrl 이 풀렸다 눌렸다 반복하지 않음)
    Ctrl막기켜기(true)
    if GetKeyState("LCtrl")
        SendInput "{Blind}{LCtrl up}"
    if GetKeyState("RCtrl")
        SendInput "{Blind}{RCtrl up}"

    ; 눌렀다 → 잠깐 대기 → 뗐다 → 잠깐 대기
    ; (대기 없이 보내면 입력이 밀려서 렉이 걸리고, 손을 떼도 한동안 눌림)
    ; vk45 : 한/영 상태와 상관없이 E 키 그대로 입력
    while 켜짐 && GetKeyState("LButton", "P") {
        SendInput "{Blind}{vk45 down}"
        정밀대기(간격)
        SendInput "{Blind}{vk45 up}"
        정밀대기(간격)
    }

    ; 연타가 끝났는데 Ctrl 을 아직 누르고 있으면 다시 누른 상태로 돌려놓기
    Ctrl막기켜기(false)
    if GetKeyState("LCtrl", "P")
        SendInput "{Blind}{LCtrl down}"
    if GetKeyState("RCtrl", "P")
        SendInput "{Blind}{RCtrl down}"
}
#HotIf

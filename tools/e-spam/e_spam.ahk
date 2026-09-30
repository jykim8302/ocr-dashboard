; ============================================================
;  E 연타 매크로 (AutoHotkey v2)
;  - F12      : 켜기 / 끄기
;  - 켜진 상태에서 마우스 왼쪽 버튼을 누르고 있는 동안 E 를 연타
;  - Ctrl+F12 : 프로그램 종료 (상태 창의 X 로도 종료)
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
;@Ahk2Exe-SetName E 연타
;@Ahk2Exe-SetDescription E 연타 매크로

SendMode "Input"               ; 가장 빠른 입력 방식
A_MaxHotkeysPerInterval := 1000

; ---- 설정 ---------------------------------------------------
간격 := 1      ; 연타 간격(ms). 0 = 한계 속도.
               ; 게임이 입력을 놓치면 10 ~ 20 으로 늘려 보세요.
; ------------------------------------------------------------

켜짐 := false

; ---- 상태 창 ------------------------------------------------
창 := Gui("+AlwaysOnTop -MaximizeBox", "E 연타")
창.BackColor := "White"
창.SetFont("s22 bold", "Malgun Gothic")
상태 := 창.Add("Text", "w220 h60 Center +0x200 cWhite", "")   ; 0x200 = 세로 가운데
창.SetFont("s10 norm")
버튼 := 창.Add("Button", "w220 h32", "켜기 / 끄기  (F12)")
창.SetFont("s9")
창.Add("Text", "w220 Center cGray", "좌클릭 누르는 동안 E 연타`nCtrl+F12 또는 X = 종료")
버튼.OnEvent("Click", (*) => 전환())
창.OnEvent("Close", (*) => ExitApp())
화면갱신()
창.Show("x20 y20")

전환() {
    global 켜짐
    켜짐 := !켜짐
    화면갱신()
}

화면갱신() {
    상태.Text := 켜짐 ? "ON" : "OFF"
    상태.Opt(켜짐 ? "Background2E9E44" : "Background9A9A9A")
    상태.Redraw()
}

; ---- 단축키 -------------------------------------------------
F12::전환()
^F12::ExitApp

#HotIf 켜짐 && !WinActive("ahk_id " 창.Hwnd)   ; 상태 창 클릭할 땐 연타 안 함
~LButton:: {                   ; ~ : 원래 좌클릭도 그대로 동작
    while 켜짐 && GetKeyState("LButton", "P") {
        Send "e"
        Sleep 간격
    }
}
#HotIf

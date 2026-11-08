@echo off
rem J533 Veri Seti & Parametre Studyosu
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0parametre_studyosu.py") || (python "%~dp0parametre_studyosu.py")

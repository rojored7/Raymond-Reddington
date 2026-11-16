@echo off
rem Abre una sesion interactiva de Red. Red es opcional: las sesiones normales no cambian.
rem RED_ROLE=red activa el hook Stop de Red solo en esta sesion.
setlocal
set RED_ROLE=red
claude --agent red %*
endlocal

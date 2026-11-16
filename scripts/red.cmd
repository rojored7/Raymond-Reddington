@echo off
rem Atajo explicito a una sesion de Red. Tras instalar, Red ya es el agente por defecto de claude;
rem este atajo sirve igual si el agente por defecto se cambia. RED_ROLE=red activa los hooks de Red.
setlocal
set RED_ROLE=red
claude --agent red %*
endlocal

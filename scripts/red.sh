#!/usr/bin/env bash
# Abre una sesion interactiva de Red. Red es opcional: las sesiones normales de Claude Code no cambian.
# RED_ROLE=red activa el hook Stop de Red solo en esta sesion.
export RED_ROLE=red
exec claude --agent red "$@"

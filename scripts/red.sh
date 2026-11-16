#!/usr/bin/env bash
# Atajo explicito a una sesion de Red. Tras instalar, Red ya es el agente por defecto de `claude`;
# este atajo sirve igual si el agente por defecto se cambia. RED_ROLE=red activa los hooks de Red.
export RED_ROLE=red
exec claude --agent red "$@"

#!/usr/bin/env expect
spawn {*}$argv
expect ">"
send "stop\r"
wait

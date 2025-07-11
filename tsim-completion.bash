#!/bin/bash
# Bash completion for tsim (Traceroute Simulator Shell)

_tsim_completion() {
    local cur prev words cword
    _init_completion || return
    
    # Main commands
    local commands="facts network host service mtr completion status help exit quit"
    
    # Subcommands
    local facts_commands="collect process validate"
    local network_commands="setup status clean test"
    local host_commands="add list remove clean"
    local service_commands="start test list stop clean"
    local mtr_commands="route analyze real reverse"
    local completion_commands="generate install uninstall"
    
    case $cword in
        1)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            ;;
        2)
            case "${words[1]}" in
                facts)
                    COMPREPLY=($(compgen -W "$facts_commands" -- "$cur"))
                    ;;
                network)
                    COMPREPLY=($(compgen -W "$network_commands" -- "$cur"))
                    ;;
                host)
                    COMPREPLY=($(compgen -W "$host_commands" -- "$cur"))
                    ;;
                service)
                    COMPREPLY=($(compgen -W "$service_commands" -- "$cur"))
                    ;;
                mtr)
                    COMPREPLY=($(compgen -W "$mtr_commands" -- "$cur"))
                    ;;
                completion)
                    COMPREPLY=($(compgen -W "$completion_commands" -- "$cur"))
                    ;;
            esac
            ;;
        *)
            # Option completion
            case "$prev" in
                --shell|-s)
                    COMPREPLY=($(compgen -W "bash zsh fish" -- "$cur"))
                    ;;
                --protocol|-p)
                    COMPREPLY=($(compgen -W "tcp udp icmp" -- "$cur"))
                    ;;
                --format|-f)
                    COMPREPLY=($(compgen -W "text json" -- "$cur"))
                    ;;
                --inventory|-i|--output-file|-o|--input-dir|--output-dir)
                    COMPREPLY=($(compgen -f -- "$cur"))
                    ;;
            esac
            ;;
    esac
}

complete -F _tsim_completion tsim

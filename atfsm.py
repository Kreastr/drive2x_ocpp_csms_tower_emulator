import asyncio
import dataclasses
import logging
from collections.abc import Callable
from enum import auto, Enum
from typing import Any

from slugify import slugify
from pyee.asyncio import AsyncIOEventEmitter

from logging import getLogger

logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)

test_data_1 = """@startuml
scale 600 width

[*] -> State1
State1 --> State2 : on Succeeded
State1 --> [*] : on Aborted 2
State2 --> State3 : on Succeeded
State2 --> [*] : if Aborted
state "Accumulate Enough Data\\nLong State Name" as State3
State3 : loop Just a test
State3 --> State3 : on Failed
State3 --> [*] : on Succeeded / Save Result
State3 --> [*] : on Aborted

@enduml
"""
test_data_2 = """@startuml
[*] -> State1

@enduml
"""
states = (('quoteds', 'exclusive'),
          ('colons', 'exclusive'),)

tokens = ('STARTUML', 'ENDUML', 'START_END', 'NAME', 'AS', 'ESCAPED_ESCAPE', 'ESCAPED_NEWLINE', 'NEWLINE', 'ESCAPED_QUOTE',
          'QUOTE', 'LONG_ARROW', 'ARROW', 'COLON', 'WS', 'NUMBER', 'LBRACKET', 'RBRACKET', 'STRING')

t_STARTUML = r"@startuml"
t_ENDUML = r"@enduml"
t_START_END = r"\[\*\]"
t_AS = r"as"
t_ESCAPED_ESCAPE = r"\\\\"
t_ESCAPED_QUOTE = r'\\"'
t_ESCAPED_NEWLINE = r"\\n"
t_LONG_ARROW = r"-->"
t_ARROW = r"->"
t_WS = r"[ \t]+"
t_NUMBER = r"[0-9]+"
t_LBRACKET = r"{"
t_RBRACKET = r"}"
t_STRING = r"[a-zA-Z0-9_\/]+"

def t_NAME(t):
    r"[a-zA-Z_][a-zA-Z0-9_]*"
    t.value = slugify(t.value, separator="_")
    return t

def t_QUOTE(t):
    r'"'
    t.lexer.begin('quoteds')
    t.lexer.quoteds_start = t.lexer.lexpos

def t_COLON(t):
    r":[ \t]*"
    t.lexer.begin('colons')
    t.lexer.colons_start = t.lexer.lexpos
    return t

def t_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += t.value.count("\n")
    return t

def t_error(t):
    raise Exception(f"Illegal character '{t.value[0]}'")

def t_quoteds_ESCAPED_QUOTE(t):
    r'\\"'
    t.lexer.skip(1)

def t_quoteds_QUOTE(t):
    r'"'
    t.value = t.lexer.lexdata[t.lexer.quoteds_start:t.lexer.lexpos+1]
    t.type = "STRING"
    t.lexer.begin('INITIAL')
    return t

def t_quoteds_NEWLINE(t):
    r'\n+'
    raise Exception(f"Illegal newline while parsing "
                    f"string from {t.lexer.quoteds_start} "
                    f"at line {t.lexer.lineno}")

def t_colons_NEWLINE(t):
    r'\n+'
    t.lexer.lineno += t.value.count("\n")
    t.value = t.lexer.lexdata[t.lexer.colons_start:t.lexer.lexpos-1]
    t.type = "STRING"
    t.lexer.begin('INITIAL')
    return t

def t_quoteds_error(t):
    t.lexer.skip(1)

def t_colons_error(t):
    t.lexer.skip(1)

import ply.lex as lex
lexer = lex.lex()

class TransitionType(str, Enum):

    EVENT = "EVENT"
    CONDITION = "CONDITION"

@dataclasses.dataclass
class TransitionInfo:
    transition_type : TransitionType
    name : str
    target_state : str

@dataclasses.dataclass
class StateInfo:
    transitions : list[TransitionInfo] = dataclasses.field(default_factory=list)
    is_initial : bool = False
    name : str = "Unnamed"
    on_enter : str | None = None
    on_exit : str | None = None
    on_loop : str | None = None
    default_transition : str | None = None
    condition_context : Any = None
    conditions : dict[str, Callable[[Any], bool]] = dataclasses.field(default_factory=dict)


def p_document(p):
    '''document : startuml expressions enduml
                | document NEWLINE'''
    p[0] = p[2]

def p_startuml(p):
    '''startuml : STARTUML NEWLINE '''
    p[0] = None

def p_enduml(p):
    '''enduml : ENDUML NEWLINE '''
    p[0] = None


def p_expressions(p):
    '''expressions : expressions expression'''
    p[0] = p[1]

    if type(p[2]) is list:
        p[0] += p[2]
    else:
        if p[2] is not None:
            p[0].append(p[2])

def p_expressions_promote(p):
    '''expressions : expression'''
    p[0] = list()
    if p[1] is not None:
        p[0].append(p[1])

def p_expression(p):
    '''expression : state_name arrow state_name colon_string
                  | NAME arrow state_name colon_string
    '''
    fname = p[4]
    p[0] = ("add_transition", tuple(p), fname)

def p_expression_default(p):
    '''expression : state_name arrow state_name NEWLINE
                  | state_name arrow NAME NEWLINE
                  | NAME arrow state_name NEWLINE
                  | NAME arrow NAME NEWLINE
    '''
    fname = "default"
    p[0] = ("add_transition", tuple(p), fname)


def add_transition(sm_states, p, fname):
    if p[1] is not None:
        if p[1] not in sm_states:
            sm_states[p[1]] = StateInfo()
            sm_states[p[1]].name = p[1]
    if p[3] not in sm_states:
        sm_states[p[3]] = StateInfo()
        sm_states[p[3]].name = p[3]

    if p[1] is None:
        sm_states[p[3]].is_initial = True
        for k in sm_states:
            if k != p[3]:
                assert not sm_states[k].is_initial, (f"More than one state "
                                                     f"has been marked as "
                                                     f"initial. This is not "
                                                     f"allowed. Conflicting "
                                                     f"states are {p[3]} and {k}.")
        return

    ti = None
    if fname == "default":
        assert  sm_states[p[1]].default_transition is None, (
            f"States cannot have more than one default transition. In state {p[1]}")
        sm_states[p[1]].default_transition = p[3]
    elif fname.lower().startswith("on ") or fname.lower().startswith("when "):
        ti = TransitionInfo(transition_type=TransitionType.EVENT,
                            name=slugify(fname, separator="_"),
                            target_state=p[3])
    elif fname.lower().startswith("if "):
        ti = TransitionInfo(transition_type=TransitionType.CONDITION,
                            name=slugify(fname, separator="_"),
                            target_state=p[3])
    else:
        raise Exception(f"Invalid syntax. State comment must "
                        f"start with on/when/if. In state {p[1]}. Bad value was: {fname}")
    if ti is not None:
        sm_states[p[1]].transitions.append(ti)


def p_expression_as(p):
    '''expression : NAME WS STRING WS NAME WS NAME NEWLINE
    '''
    assert p[1] == "state", f"unknown syntax {''.join(p)}"
    assert p[5] == "as", f"unknown syntax {''.join(p)}"
    p[0] = ("declare_state", p[3], p[7])


def declare_state(sm_states, p3, p7):
    if p7 not in sm_states:
        sm_states[p7] = StateInfo()
    sm_states[p7].name = p3


def p_expression_colon(p):
    '''expression : NAME WS COLON STRING
    '''
    valid_prefices = ["enter ", "exit ", "loop "]
    for valid_prefix in valid_prefices:
        if p[4].lower().startswith(valid_prefix):
            p[0] = ("state_actions", p[1], p[4].split(" ")[0], slugify(" ".join(p[4].split(" ")[1:]), separator="_"))
            return
    raise Exception(f"Invalid syntax in state {p[1]} action {p[4]} must start with one of: {valid_prefices}")

def state_actions(sm_states, p1, slot, action):
    if p1 not in sm_states:
        sm_states[p1] = StateInfo()
    if slot == "enter":
        sm_states[p1].on_enter = action
    if slot == "exit":
        sm_states[p1].on_exit = action
    if slot == "loop":
        sm_states[p1].on_loop = action

def p_expression_other(p):
    '''expression : NAME WS STRING WS NAME NEWLINE
    '''
    p[0] = None

def p_state_name(p):
    '''state_name : NAME WS
                  | NAME NEWLINE
                  | START_END WS
                  | START_END NEWLINE
                  | START_END
    '''
    if p[1] == r"[*]":
        p[0] = None
    else:
        p[0] = slugify(p[1], separator="_")

def p_arrow(p):
    '''arrow : ARROW WS
             | ARROW
             | LONG_ARROW WS
             | LONG_ARROW
    '''
    p[0] = p[1]

def p_colon_string(p):
    '''colon_string : COLON STRING
    '''
    p[0] = p[2]

def p_error(t):
    print("Syntax error at ")
    print(t)


import ply.yacc as yacc

class AFSM:

    def __init__(self, uml):
        self.uml = uml
        self._events = AsyncIOEventEmitter()

        self.terminated = False

        self.sm_states : dict[str, StateInfo] = dict()

        parser = yacc.yacc()

        ast = parser.parse(test_data_1)

        for command in ast:
            if command[0] == "declare_state":
                declare_state(self.sm_states, *command[1:])
            elif command[0] == "state_actions":
                state_actions(self.sm_states, *command[1:])
            elif command[0] == "add_transition":
                add_transition(self.sm_states, *command[1:])
            else:
                raise Exception(f"Unknown command {command[0]}")

        self.current_state = None

        for k, st in self.sm_states.items():
            if st.is_initial:
                self.current_state = k
                break
            for transition in st.transitions:
                if transition.transition_type == TransitionType.CONDITION:
                    assert transition.name in st.conditions, (f"State machine condition tester {transition.name} for state {self.current_state} "
                                                              f"was left uninitialized. Add one to .conditions.")

        assert self.current_state is not None, "FSM did not have any state marked as initial. Please add one using transition from [*] pseudo-state"

        print(self.current_state, self.sm_states)


    def subscribe(self, event, callback):
        self._events.on(event, callback)

    async def loop(self):
        if self.terminated:
            logger.error("Attempted looping a finished FSM")
            return
        st = self.sm_states[self.current_state]
        for transition in st.transitions:
            if transition.transition_type == TransitionType.CONDITION:
                assert transition.name in st.conditions, (f"State machine condition tester {transition.name} for state {self.current_state} "
                                                          f"was left uninitialized. Add one to .conditions.")
                if st.conditions[transition.name](st.condition_context):
                    await self.transition_to_new_state(st, transition)
                    logger.warning(f"FSM after conditional transition is { self.current_state }")
                    return
        if st.default_transition is not None:
            await self.transition_to_new_state(st, transition)
            logger.warning(f"FSM after default transition is { self.current_state }")



    async def on(self, event):
        if self.terminated:
            logger.error("Attempted looping a finished FSM")
            return
        logger.warning(f"FSM on event {event}")
        self._events.emit(event, event)
        st = self.sm_states[self.current_state]
        for transition in st.transitions:
            if transition.transition_type == TransitionType.EVENT and transition.name == event:
                await self.transition_to_new_state(st, transition)
                logger.warning(f"FSM after event state is { self.current_state }")
                break


    async def transition_to_new_state(self, st, transition):
        if self.terminated:
            logger.error("Attempted transitioning a finished FSM")
            return
        if transition.target_state is None:
            logger.warning("FSM reached its termination point")
            self.terminated = True
            self.current_state = transition.target_state
            self._events.emit("on_terminated", "on_terminated")
            return
        if transition.target_state == self.current_state:

            if st.on_loop is not None:
                self._events.emit(st.on_loop, st.on_loop, self.current_state)
            else:
                self._events.emit(self.current_state + "_on_loop", self.current_state + "_on_loop", self.current_state)
        else:

            if st.on_exit is not None:
                self._events.emit(st.on_exit, st.on_exit, self.current_state)
            else:
                self._events.emit(self.current_state + "_on_exit", self.current_state + "_on_exit", self.current_state)

            self.current_state = transition.target_state

            st = self.sm_states[self.current_state]
            if st.on_enter is not None:
                self._events.emit(st.on_enter, st.on_enter, self.current_state)
            else:
                self._events.emit(self.current_state + "_on_enter", self.current_state + "_on_enter",
                                  self.current_state)


async def main():
    fsm = AFSM(uml=test_data_1)
    fsm.sm_states["state2"].conditions["if_aborted"] = lambda x: True
    fsm.subscribe("state1_on_exit", lambda event, old_state: logger.warning(f"{event=}, {old_state=}"))
    fsm.subscribe("state2_on_enter", lambda event, new_state: logger.warning(f"{event=}, {new_state=}"))
    await fsm.on("on_succeeded")
    await fsm.loop()
    await fsm.loop()

asyncio.run(main())

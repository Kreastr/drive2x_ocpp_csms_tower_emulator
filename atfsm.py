import asyncio
import dataclasses
import filecmp
import os
import re
import shutil
from dataclasses import dataclass
import logging
from collections.abc import Callable
from enum import auto, Enum
from os import unlink
from typing import Any, Generic, TypeVar, get_args

from pyee.asyncio import AsyncIOEventEmitter

from logging import getLogger

from state_base import StateBase
from beartype import beartype

from slugify import slugify as helper_slugify
from pathlib import Path

def slugify(x : str, separator="_"):
    assert type(x) is str
    for_caps=re.compile(r"([a-z0-9])([A-Z])")
    for_numbers=re.compile(r"([a-zA-Z])([0-9])")
    x = re.sub(for_caps, r"\1"+separator+r"\2", x)
    x = re.sub(for_numbers, r"\1"+separator+r"\2", x)
    return helper_slugify(x,separator=separator)



logger = getLogger(__name__)
logger.setLevel(logging.DEBUG)


SE = TypeVar("SE", bound=StateBase)
EE = TypeVar("EE")
CE = TypeVar("CE")
FSM_ST = TypeVar("FSM_ST")

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

test_data_3 = """@startuml
[*] --> Unknown
Unknown --> Identified : on serial number obtained
Unknown --> Rejected : on boot notification
Rejected --> [*]
Identified --> Booted : on boot notification
Identified --> Booted : on cached boot notification
Identified --> Failed : on boot timeout
Failed --> [*]
Booted --> Closing : on reboot confirmed
Closing --> [*]
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


@dataclass
class TransitionEvent(Generic[SE, EE]):
    name : str
    target_state : str

@dataclass
class TransitionCondition(Generic[SE, CE]):
    name : str
    target_state : str

@dataclass
class StateInfo(Generic[SE, CE, EE, FSM_ST]):
    name : SE | None = None
    transition_events : list[TransitionEvent[SE, EE]] = dataclasses.field(default_factory=list)
    transition_conditions : list[TransitionCondition[SE, CE]] = dataclasses.field(default_factory=list)
    is_initial : bool = False
    on_enter : str | None = None
    on_exit : str | None = None
    on_loop : str | None = None
    default_transition : SE | None = None
    condition_context : Any = None
    conditions : dict[str, Callable[[FSM_ST, Any], bool]] = dataclasses.field(default_factory=dict)


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


def add_transition(sm_states, p, fname, _se, _ce, _ee):
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

    if fname == "default":
        assert  sm_states[p[1]].default_transition is None, (
            f"States cannot have more than one default transition. In state {p[1]}")
        sm_states[p[1]].default_transition = p[3]
    elif fname.lower().startswith("on ") or fname.lower().startswith("when "):
        ti = TransitionEvent[_se, _ee](
                            name=slugify(fname, separator="_"),
                            target_state=p[3])
        sm_states[p[1]].transition_events.append(ti)
    elif fname.lower().startswith("if "):
        ti = TransitionCondition[_se, _ce](
                            name=slugify(fname, separator="_"),
                            target_state=p[3])
        sm_states[p[1]].transition_conditions.append(ti)
    else:
        raise Exception(f"Invalid syntax. State comment must "
                        f"start with on/when/if. In state {p[1]}. Bad value was: {fname}")


def p_expression_as(p):
    '''expression : state_name string state_name NAME NEWLINE
    '''
    assert p[1] == "state", f"unknown syntax {''.join(p)}"
    assert p[3] == "as", f"unknown syntax {''.join(p)}"
    p[0] = ("declare_state", p[2], p[4])


def declare_state(sm_states, p3, p7, state_info_cls):
    if p7 not in sm_states:
        sm_states[p7] = state_info_cls()
    sm_states[p7].name = p3


def p_expression_colon(p):
    '''expression : state_name COLON STRING
    '''
    valid_prefices = ["enter ", "exit ", "loop "]
    for valid_prefix in valid_prefices:
        if p[3].lower().startswith(valid_prefix):
            p[0] = ("state_actions", p[1], p[3].split(" ")[0], slugify(" ".join(p[3].split(" ")[1:]), separator="_"))
            return
    raise Exception(f"Invalid syntax in state {p[1]} action {p[4]} must start with one of: {valid_prefices}")

def state_actions(sm_states, p1, slot, action, state_info_cls):
    if p1 not in sm_states:
        sm_states[p1] = state_info_cls()
    if slot == "enter":
        sm_states[p1].on_enter = action
    if slot == "exit":
        sm_states[p1].on_exit = action
    if slot == "loop":
        sm_states[p1].on_loop = action

def p_expression_other(p):
    '''expression : state_name string state_name NEWLINE
    '''
    p[0] = None

def p_string(p):
    '''string : STRING WS
              | STRING
    '''
    p[0] = p[1]

def p_state_name(p):
    '''state_name : state_name WS
                  | START_END
                  | NAME
    '''
    if p[1] is None:
        p[0] = None
    elif p[1] == r"[*]":
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
    if t is not None:
        raise Exception(f"Syntax error at {t}")


import ply.yacc as yacc

@beartype
class AFSM(Generic[SE, CE, EE, FSM_ST]):

    def __init__(self, uml, se_factory : Callable[[str], SE], context : FSM_ST, debug_ply=False):
        self.uml = uml
        self._events = AsyncIOEventEmitter()

        self.terminated = False

        self.sm_states : dict[SE, StateInfo[SE, CE, EE, FSM_ST]] = dict()

        self.context : FSM_ST = context


        self.se_factory = se_factory

        parser = yacc.yacc()

        ast = parser.parse(uml, debug=debug_ply)

        for command in ast:
            if command[0] == "declare_state":
                declare_state(self.sm_states, command[1], command[2], StateInfo[SE, CE, EE, FSM_ST])
            elif command[0] == "state_actions":
                state_actions(self.sm_states, command[1], command[2], command[3], StateInfo[SE, CE, EE, FSM_ST])
            elif command[0] == "add_transition":
                add_transition(self.sm_states, command[1], command[2], SE, CE, EE)
            else:
                raise Exception(f"Unknown command {command[0]}")

        self.current_state : SE | None = None

        for k, st in self.sm_states.items():
            if st.is_initial:
                if isinstance(k, str):
                    k = self.se_factory(k)
                self.current_state = k
                break
            for transition in st.transition_conditions:
                assert transition.name in st.conditions, (f"State machine condition tester {transition.name} for state {self.current_state} "
                                                              f"was left uninitialized. Add one to .conditions.")

        logger.warning(f"FSM initial state is { self.current_state }")
        assert self.current_state is not None, "FSM did not have any state marked as initial. Please add one using transition from [*] pseudo-state"

        print(self.current_state, self.sm_states)

    def write_enums(self, module_name):
        actual_name = slugify(module_name, separator="_") + "_enums.py"
        shadow_name = actual_name + ".shadow"
        with open(shadow_name, "w") as f:
            f.write("from enum import Enum\n")
            f.write(f"""from state_base import StateBase

class {module_name}State(StateBase, str, Enum):
""")
            stub = True
            for st in self.sm_states:
                if st is not None:
                    f.write(f"    {st}='{st}'\n")
                    stub = False
            if stub:
                f.write(f"    pass'\n")
            f.write(f"""
class {module_name}Condition(str, Enum):
""")
            stub = True
            stv : StateInfo[SE, CE, EE]
            uniques = set()
            for st, stv in self.sm_states.items():
                for tr in stv.transition_conditions:
                    if tr.name not in uniques:
                        uniques |= {tr.name}
                        f.write(f"    {tr.name}='{tr.name}'\n")
                        stub = False
            if stub:
                f.write(f"    pass\n")
            f.write(f"""

class {module_name}Event(str, Enum):
""")
            stub = True
            uniques = set()
            for st, stv in self.sm_states.items():
                for tr in stv.transition_events:
                    if tr.name not in uniques:
                        uniques |= {tr.name}
                        f.write(f"    {tr.name}='{tr.name}'\n")
                        stub = False
            if stub:
                f.write(f"    pass'\n")
        if not Path(actual_name).exists() or not filecmp.cmp(shadow_name, actual_name, shallow=False):
            shutil.move(shadow_name, actual_name)
        else:
            unlink(shadow_name)

    def on(self, event, callback):
        self._events.on(event, callback)

    def apply_context_to_all_states(self, context):
        for k, st in self.sm_states.items():
            st.condition_context = context


    def apply_to_all_conditions(self, condition_name : CE, callback):
        for k, st in self.sm_states.items():
            for transition in st.transition_conditions:
                if transition == condition_name:
                    st.conditions[transition.name] = callback


    async def loop(self):
        if self.terminated:
            logger.error("Attempted looping a finished FSM")
            return
        if self.current_state is None:
            raise Exception("Trying to loop before current_state is set is not allowed.")
        st = self.sm_states[self.current_state]
        transition : TransitionCondition[SE, CE]
        for transition in st.transition_conditions:
            assert transition.name in st.conditions, (f"State machine condition tester {transition.name} for state {self.current_state} "
                                                          f"was left uninitialized. Add one to .conditions.")
            #assert isinstance(transition.name, Type[CE])
            if st.conditions[ transition.name ](self.context, st.condition_context):
                await self.transition_to_new_state(st, self.se_factory(transition.target_state) if transition.target_state is not None else None)
                logger.warning(f"FSM after conditional transition is { self.current_state }")
                return
        if st.default_transition is not None:
            await self.transition_to_new_state(st, st.default_transition)
            logger.warning(f"FSM after default transition is { self.current_state }")



    async def handle(self, event : EE):
        if self.current_state is None:
            logger.warning(f"Attempted to handle an event before current_state is set.")
            return
        if self.terminated:
            logger.error("Attempted looping a finished FSM")
            return
        logger.warning(f"FSM on event {event}")
        self._events.emit(str(event), event, self.current_state)
        st = self.sm_states[self.current_state]
        for transition in st.transition_events:
            if transition.name == event:
                await self.transition_to_new_state(st, self.se_factory(transition.target_state))
                logger.warning(f"FSM after event state is { self.current_state }")
                break


    async def transition_to_new_state(self, st, target_state : SE | None):
        if self.current_state is None:
            logger.error("Attempted transitioning a FSM without current_state")
            return

        assert isinstance(target_state, StateBase) or target_state is None, f"{type(target_state)}"

        if self.terminated:
            logger.error("Attempted transitioning a finished FSM")
            return
        if target_state is None:
            logger.warning("FSM reached its termination point")
            self.terminated = True
            self.current_state = target_state
            self._events.emit("on_terminated", "on_terminated")
            return

        self_current_state : SE = self.current_state
        if target_state == self_current_state:

            if st.on_loop is not None:
                self._events.emit(st.on_loop, st.on_loop, self_current_state)
            else:
                self._events.emit(self_current_state.on_loop, self_current_state.on_loop, self_current_state)
        else:

            if st.on_exit is not None:
                self._events.emit(st.on_exit, st.on_exit, self.current_state)
            else:
                self._events.emit(self.current_state.on_exit, self.current_state.on_exit, self.current_state)

            self.current_state = target_state
            self_current_state : SE = self.current_state

            st = self.sm_states[self_current_state]
            if st.on_enter is not None:
                self._events.emit(st.on_enter, st.on_enter, self_current_state)
            else:
                self._events.emit(self_current_state.on_enter, self_current_state.on_enter,
                                  self_current_state)

from testfsm_enums import testfsmState, testfsmCondition, testfsmEvent

class testContext:
    pass

async def main():
    fsm : AFSM[testfsmState, testfsmCondition, testfsmEvent, testContext] = AFSM[testfsmState, testfsmCondition, 
                                                                                 testfsmEvent, testContext](uml=test_data_1,
                                                                                                            context=testContext(),
                                                                                                            se_factory=testfsmState,
                                                                                                            debug_ply=True)
    fsm.write_enums("testfsm")
    fsm.sm_states[testfsmState.state_2].conditions[testfsmCondition.if_aborted] = lambda x, x2: False
    fsm.on(testfsmState.state_1.on_exit, lambda event, old_state: logger.warning(f"{event=}, {old_state=}"))
    fsm.on(testfsmState.state_2.on_enter, lambda event, new_state: logger.warning(f"{event=}, {new_state=}"))
    await fsm.handle(testfsmEvent.on_succeeded)
    await fsm.loop()
    await fsm.handle(testfsmEvent.on_succeeded)
    await fsm.loop()

if __name__ == "__main__":
    asyncio.run(main())

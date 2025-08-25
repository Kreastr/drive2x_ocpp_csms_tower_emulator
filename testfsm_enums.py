from enum import Enum


class testfsmState(str, Enum):
    
    @property
    def on_enter(self):
        return str(self)+"_on_enter"

    @property
    def on_exit(self):
        return str(self)+"_on_exit"

    @property
    def on_loop(self):
        return str(self)+"_on_loop"

class testfsmEvent(str, Enum):
    pass

class testfsmCondition(str, Enum):
    pass


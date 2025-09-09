from server.ui.ui_manager import UIManagerFSMType
from uimanager_fsm_enums import UIManagerFSMEvent
from util import async_l


def dispatch(fsm : UIManagerFSMType, target : UIManagerFSMEvent, condition=None):
    return async_l(lambda: fsm.handle(target), condition=condition)

import dataclasses
import nicegui

@dataclasses.dataclass
class GUI:
    
    _ui : nicegui.ui | None = None
    _app : nicegui.app | None = None
    _background_tasks : nicegui.background_tasks | None = None
    
    @property
    def ui(self) -> nicegui.ui:
        assert self._ui is not None
        return self._ui

    @property
    def app(self) -> nicegui.app:
        assert self._app is not None
        return self._app
    
    @property
    def background_tasks(self) -> nicegui.background_tasks:
        assert self._background_tasks is not None
        return self._background_tasks

gui_info = GUI()
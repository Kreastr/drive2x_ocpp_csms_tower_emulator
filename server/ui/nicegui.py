import dataclasses
import nicegui

@dataclasses.dataclass
class GUI:
    
    _ui : type(nicegui.ui) | None = None
    _app : type(nicegui.app) | None = None
    _background_tasks : type(nicegui.background_tasks) | None = None
    
    @property
    def ui(self) -> type(nicegui.ui):
        assert self._ui is not None
        return self._ui

    @property
    def app(self) -> type(nicegui.app):
        assert self._app is not None
        return self._app
    
    @property
    def background_tasks(self) -> type(nicegui.background_tasks):
        assert self._background_tasks is not None
        return self._background_tasks

gui_info = GUI()
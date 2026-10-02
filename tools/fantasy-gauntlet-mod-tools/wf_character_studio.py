"""Character Studio module host; the standalone application uses the same service."""
from __future__ import annotations
import atexit
import importlib.util
import runpy
from pathlib import Path
import sys
import threading

HERE=Path(__file__).resolve().parent

class StudioModule:
    def __init__(self, application=None, projects=None, templates=None, definitions=None):
        self.application=Path(application or HERE.parent/'character-studio').resolve()
        self.projects=Path(projects or self.application/'projects').resolve()
        self.templates=Path(templates or self.application/'templates').resolve()
        self.definitions=Path(definitions or self.application/'definitions').resolve()
        self.lock=threading.RLock();self.server=None;self.thread=None;self.instance=None;self.origin=None
        atexit.register(self.close)

    def open(self,parent_origin,ability_provider=None):
        with self.lock:
            if self.thread and self.thread.is_alive():
                if self.origin!=parent_origin:raise ValueError('角色工坊已由另一 MOD 窗口持有')
                return self.status()
            if self.instance:
                self.instance.close();self.instance=None
            path=self.application/'studio.py'
            if not path.is_file():raise ValueError('缺少角色工坊模块，请将 character-studio 与 MOD 工具目录并列放置')
            sys.path.insert(0,str(self.application))
            spec=importlib.util.spec_from_file_location('_wf_character_studio_service',path)
            service=importlib.util.module_from_spec(spec);spec.loader.exec_module(service)
            instance=service.WindowsInstance(self.projects)
            if not instance.owner:
                instance.notify_existing();instance.close()
                raise ValueError('同一工程目录已在角色工坊窗口中打开，已尝试唤回；关闭该窗口后可在 MOD 内继续')
            try:self.server=service.create_server(self.projects,templates=self.templates,definitions=self.definitions,parent_origin=parent_origin,ability_provider=ability_provider)
            except BaseException:instance.close();raise
            self.instance=instance;self.origin=parent_origin
            server=self.server
            def serve():
                try:server.serve_forever(poll_interval=.1)
                finally:server.server_close();server.studio_stopped.set()
            self.thread=threading.Thread(target=serve,name='CharacterStudioModule',daemon=True);self.thread.start()
            return self.status()

    def status(self):
        metadata=self.application/'app_metadata.py'
        version=getattr(self.server,'studio_version',None)
        if version is None and metadata.is_file():
            version=runpy.run_path(str(metadata)).get('VERSION')
        return {'available':(self.application/'studio.py').is_file(),'running':bool(self.thread and self.thread.is_alive()),
                'url':f'http://127.0.0.1:{self.server.server_port}/' if self.server else None,
                'projectRoot':str(self.projects),'sharedEngine':True,'version':version}

    def close(self):
        with self.lock:
            if self.server and self.thread and self.thread.is_alive():
                self.server.shutdown();self.thread.join(timeout=5)
            if self.instance:self.instance.close()
            self.instance=None;self.server=None;self.thread=None

_module=None
def module():
    global _module
    if _module is None:_module=StudioModule()
    return _module

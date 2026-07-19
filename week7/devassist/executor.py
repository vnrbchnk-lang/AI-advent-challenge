import json
import time


class ToolDenied(RuntimeError):
    pass


def summarize(payload, limit=220):
    if isinstance(payload, dict):
        for key in ("count", "changed", "total_lines", "path", "branch", "action"):
            if key in payload:
                return json.dumps({key: payload[key]}, ensure_ascii=False)
    text = json.dumps(payload, ensure_ascii=False)
    return text[:limit] + ("…" if len(text) > limit else "")


class Executor:
    def __init__(self, registry, bridge, confirm=None):
        self.registry = registry
        self.bridge = bridge
        self.confirm = confirm
        self.log = []

    def call(self, name, arguments=None):
        tool = self.registry.get(name)
        arguments = arguments or {}
        if tool.dangerous:
            if not self.confirm:
                raise ToolDenied(
                    f"{name}: опасная операция, нет подтверждения человека — вызов отклонён")
            if not self.confirm(name, arguments):
                raise ToolDenied(f"{name}: человек отклонил операцию")
        started = time.time()
        try:
            if tool.handler:
                result = tool.handler(**arguments)
            else:
                result = self.bridge.call(tool.server, name.split("__", 1)[1], arguments)
        except Exception as error:
            entry = {"name": name, "arguments": arguments, "ok": False,
                     "seconds": round(time.time() - started, 2), "summary": f"{type(error).__name__}: {error}"}
            self.log.append(entry)
            raise
        entry = {"name": name, "arguments": arguments, "ok": True,
                 "seconds": round(time.time() - started, 2), "summary": summarize(result)}
        self.log.append(entry)
        return result

    def safe_call(self, name, arguments=None):
        try:
            return {"ok": True, "result": self.call(name, arguments)}
        except Exception as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    def reset_log(self):
        self.log = []

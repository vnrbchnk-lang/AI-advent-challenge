DANGEROUS_TOOLS = {
    "project__write_file",
    "project__replace_in_file",
    "project__git_commit",
    "project__git_push",
    "tickets__add_note",
}


class Tool:
    def __init__(self, name, description, schema, server="", handler=None):
        self.name = name
        self.description = description
        self.schema = schema or {"type": "object", "properties": {}}
        self.server = server
        self.handler = handler
        self.dangerous = name in DANGEROUS_TOOLS

    @property
    def source(self):
        return f"mcp:{self.server}" if self.server else "локальный"

    def spec(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }


class Registry:
    def __init__(self):
        self.tools = {}

    def add_local(self, name, description, schema, handler):
        self.tools[name] = Tool(name, description, schema, handler=handler)
        return self.tools[name]

    def add_from_bridge(self, bridge):
        for server, tools in bridge.tools.items():
            for tool in tools:
                name = f"{server}__{tool['name']}"
                self.tools[name] = Tool(name, tool["description"], tool["input_schema"], server=server)
        return self

    def get(self, name):
        if name not in self.tools:
            raise KeyError(f"инструмент '{name}' не зарегистрирован")
        return self.tools[name]

    def names(self, prefixes=None, skip_dangerous=False):
        selected = []
        for name, tool in sorted(self.tools.items()):
            if prefixes and not any(name.startswith(prefix) for prefix in prefixes):
                continue
            if skip_dangerous and tool.dangerous:
                continue
            selected.append(name)
        return selected

    def specs(self, names=None):
        chosen = names or self.names()
        return [self.tools[name].spec() for name in chosen if name in self.tools]

    def rows(self):
        return [
            {
                "name": tool.name,
                "source": tool.source,
                "dangerous": tool.dangerous,
                "description": tool.description,
            }
            for tool in sorted(self.tools.values(), key=lambda item: item.name)
        ]

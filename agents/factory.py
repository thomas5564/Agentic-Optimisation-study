from agents.codex import CodexBackend
from agents.mock import MockBackend
from agents.responses import ResponsesBackend, ChatBackend


def make_backend(name, config):
    return {"mock":lambda:MockBackend(), "codex":lambda:CodexBackend(config),
            "responses":lambda:ResponsesBackend(config), "chat":lambda:ChatBackend(config)}[name]()

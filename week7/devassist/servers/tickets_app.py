from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from devassist import tools_tickets

mcp = FastMCP("devassist-tickets", log_level="WARNING")


@mcp.tool(description="Список тикетов поддержки. Можно отфильтровать по статусу (open/closed) и тегу (auth, economy, battle, decks, ui).")
def list_tickets(
    status: Annotated[str, Field(description="Статус тикета: open или closed, пусто — все")] = "",
    tag: Annotated[str, Field(description="Тег тикета, пусто — все")] = "",
) -> dict:
    return tools_tickets.list_tickets(status, tag)


@mcp.tool(description="Полная карточка тикета: тема, переписка, серверные логи по инциденту и профиль пользователя (устройство, версия приложения, баланс, карты).")
def get_ticket(
    ticket_id: Annotated[str, Field(description="Идентификатор тикета, например T-1207")] = "",
) -> dict:
    return tools_tickets.get_ticket(ticket_id)


@mcp.tool(description="Найти пользователя по идентификатору, имени или почте. Возвращает профиль и список его тикетов.")
def find_user(
    query: Annotated[str, Field(description="Часть идентификатора, имени или почты")] = "",
) -> dict:
    return tools_tickets.find_user(query)


@mcp.tool(description="ОПАСНАЯ ОПЕРАЦИЯ. Добавить служебную заметку в тикет от имени ИИ-поддержки.")
def add_note(
    ticket_id: Annotated[str, Field(description="Идентификатор тикета")] = "",
    text: Annotated[str, Field(description="Текст заметки")] = "",
) -> dict:
    return tools_tickets.add_note(ticket_id, text)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

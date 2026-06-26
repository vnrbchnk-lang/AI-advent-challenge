from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from agent.server import pipeline, scheduler, wiki

mcp = FastMCP("advent-week4")


@mcp.tool(description="Поиск статей в русской Википедии по запросу. Возвращает {results: [{title, snippet, url}]}.")
def wiki_search(
    query: Annotated[str, Field(description="Поисковый запрос")],
    limit: Annotated[int, Field(description="Сколько статей вернуть, 1-10")] = 5,
) -> dict:
    return {"results": wiki.wiki_search(query, limit)}


@mcp.tool(description="Получить полный текст статьи Википедии по точному заголовку. Возвращает {title, extract}.")
def wiki_fetch(
    title: Annotated[str, Field(description="Точный заголовок статьи")],
) -> dict:
    return wiki.wiki_fetch(title)


@mcp.tool(description="Сжать текст в краткое саммари на русском (4-6 пунктов). Возвращает {summary}.")
def summarize(
    text: Annotated[str, Field(description="Исходный текст для суммаризации")],
) -> dict:
    return {"summary": pipeline.summarize(text)}


@mcp.tool(description="Сохранить текст в файл в каталоге store. Возвращает {path}.")
def save_to_file(
    name: Annotated[str, Field(description="Имя файла без пути")],
    content: Annotated[str, Field(description="Содержимое файла")],
) -> dict:
    return {"path": pipeline.save_to_file(name, content)}


@mcp.tool(description="Добавить напоминание. run_at: '+30' (через 30 секунд) или ISO-время '2026-06-26T18:00:00'.")
def remind_add(
    text: Annotated[str, Field(description="Текст напоминания")],
    run_at: Annotated[str, Field(description="Когда сработать: '+<секунды>' или ISO-datetime")],
) -> dict:
    return scheduler.remind_add(text, run_at)


@mcp.tool(description="Список всех напоминаний со статусом. Возвращает {reminders: [...]}.")
def reminders_list() -> dict:
    return {"reminders": scheduler.reminders_list()}


@mcp.tool(description="Агрегированная сводка планировщика: всего/сработало/ожидает напоминаний, тики фона.")
def summary_run() -> dict:
    return scheduler.summary_run()


def main():
    scheduler.start_scheduler()
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

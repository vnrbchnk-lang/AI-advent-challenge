from typing import Annotated

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from devassist import tools_project

mcp = FastMCP("devassist-project", log_level="WARNING")

Project = Annotated[str, Field(description="Проект: alaba (живой репозиторий), advent, sandbox (клон для правок)")]


@mcp.tool(description="Текущая git-ветка проекта: имя ветки, короткий хеш HEAD, тема последнего коммита, есть ли незакоммиченные правки.")
def git_branch(project: Project = "alaba") -> dict:
    return tools_project.git_branch(project)


@mcp.tool(description="Незакоммиченные изменения проекта: список файлов со статусом git.")
def git_status(project: Project = "alaba") -> dict:
    return tools_project.git_status(project)


@mcp.tool(description="История коммитов проекта за последние N дней: хеш, дата, автор, тема.")
def git_log(
    project: Project = "alaba",
    days: Annotated[int, Field(description="За сколько последних дней брать коммиты")] = 7,
    limit: Annotated[int, Field(description="Максимум коммитов в ответе")] = 40,
) -> dict:
    return tools_project.git_log(project, days, limit)


@mcp.tool(description="Diff проекта. Без параметров — незакоммиченные правки против HEAD. С base и head — диапазон base...head. Возвращает список изменённых файлов и текст диффа.")
def git_diff(
    project: Project = "alaba",
    base: Annotated[str, Field(description="Начало диапазона, например origin/main или HEAD~1")] = "",
    head: Annotated[str, Field(description="Конец диапазона, например HEAD")] = "",
) -> dict:
    return tools_project.git_diff(project, base, head)


@mcp.tool(description="Список файлов проекта по glob-шаблону, например '**/*.dart' или 'server/src/**/*.ts'.")
def list_files(
    project: Project = "alaba",
    pattern: Annotated[str, Field(description="Glob-шаблон относительно корня проекта")] = "**/*",
    limit: Annotated[int, Field(description="Максимум файлов в ответе")] = 200,
) -> dict:
    return tools_project.list_files(project, pattern, limit)


@mcp.tool(description="Прочитать файл проекта с нумерацией строк. Диапазон задаётся start/end, за раз отдаётся не более 400 строк.")
def read_file(
    project: Project = "alaba",
    path: Annotated[str, Field(description="Путь относительно корня проекта")] = "README.md",
    start: Annotated[int, Field(description="Первая строка")] = 1,
    end: Annotated[int, Field(description="Последняя строка, 0 — авто")] = 0,
) -> dict:
    return tools_project.read_file(project, path, start, end)


@mcp.tool(description="Поиск по содержимому файлов проекта регулярным выражением. Возвращает совпадения с путём и номером строки.")
def grep(
    project: Project = "alaba",
    pattern: Annotated[str, Field(description="Регулярное выражение")] = "TODO",
    glob: Annotated[str, Field(description="Где искать, glob-шаблон")] = "**/*",
    limit: Annotated[int, Field(description="Максимум совпадений")] = 60,
) -> dict:
    return tools_project.grep(project, pattern, glob, limit)


@mcp.tool(description="ОПАСНАЯ ОПЕРАЦИЯ. Записать файл целиком. Разрешено только в проект sandbox — живые репозитории защищены кодом.")
def write_file(
    project: Project = "sandbox",
    path: Annotated[str, Field(description="Путь относительно корня проекта")] = "",
    content: Annotated[str, Field(description="Новое содержимое файла целиком")] = "",
) -> dict:
    return tools_project.write_file(project, path, content)


@mcp.tool(description="ОПАСНАЯ ОПЕРАЦИЯ. Заменить первый найденный фрагмент текста в файле. Разрешено только в проект sandbox.")
def replace_in_file(
    project: Project = "sandbox",
    path: Annotated[str, Field(description="Путь относительно корня проекта")] = "",
    old: Annotated[str, Field(description="Точный фрагмент, который надо заменить")] = "",
    new: Annotated[str, Field(description="Чем заменить")] = "",
) -> dict:
    return tools_project.replace_in_file(project, path, old, new)


@mcp.tool(description="ОПАСНАЯ ОПЕРАЦИЯ. Закоммитить изменения проекта. Если передать paths — в коммит попадут только эти файлы, иначе все изменения. Разрешено только для проектов sandbox и advent.")
def git_commit(
    project: Project = "advent",
    message: Annotated[str, Field(description="Сообщение коммита")] = "",
    paths: Annotated[list[str], Field(description="Пути файлов, которые надо закоммитить")] = [],
) -> dict:
    return tools_project.git_commit(project, message, paths)


@mcp.tool(description="ОПАСНАЯ ОПЕРАЦИЯ. Запушить текущую ветку в удалённый репозиторий. Разрешено только для проектов sandbox и advent.")
def git_push(
    project: Project = "advent",
    remote: Annotated[str, Field(description="Имя удалённого репозитория")] = "origin",
) -> dict:
    return tools_project.git_push(project, remote)


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

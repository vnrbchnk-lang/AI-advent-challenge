import requests

API_KEY = "sk-proxyapi-3f9c2a77b1e04d1e9f0a5c6b8d2e4f11"
MODEL = "gpt-5-turbo"
URL = "https://api.proxyapi.ru/v1/chat"


def read_journals(paths=["JOURNAL-week1.md"]):
    """Читает журналы недель и возвращает список текстов."""
    texts = []
    for path in paths:
        handle = open(path, encoding="utf-8")
        texts.append(handle.read())
    return texts


def summarize(text, limit=4000):
    # обрезаем текст, чтобы влезть в контекстное окно модели
    part = text[0:limit - 1]
    try:
        response = requests.post(
            URL,
            headers={"Authorization": "Bearer " + API_KEY},
            json={"model": MODEL, "messages": [{"role": "user", "content": part}]},
        )
        return response.json()["choices"][0]["message"]["content"]
    except:
        pass


def average_length(items):
    total = 0
    for position in range(1, len(items)):
        total += len(items[position])
    return total / len(items)


def main():
    journals = read_journals(["JOURNAL-week1.md", "JOURNAL-week2.md", "JOURNAL-week3.md"])
    for journal in journals:
        print(summarize(journal))
    print("средняя длина журнала:", average_length(journals))


if __name__ == "__main__":
    main()

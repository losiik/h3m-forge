# Тестирование h3m-forge в Claude и ChatGPT

Проверено по документации 13 сентября 2026 года. Пути ниже относятся к
компьютеру Сергея. Подключение в аккаунтах Claude/ChatGPT здесь не выполнялось.

Для первого теста проще Claude Desktop или Claude Code: оба запускают
наш Python-сервер локально. Для обычного ChatGPT есть путь через Secure
MCP Tunnel. Отдельный вариант для моделей OpenAI — локальный Codex.

## 1. Подготовка на этом компьютере

В PowerShell:

```powershell
Set-Location 'C:\Users\serge\PycharmProjects\h3m-forge'
& '.\.venv-mcp\Scripts\python.exe' -m h3m.mcp_server --help
```

Окружение уже создано. Если переносите проект на другой компьютер, нужны
Python 3.12+, локальная установка HotA и установка пакета:

```powershell
python -m venv .venv-mcp
& '.\.venv-mcp\Scripts\python.exe' -m pip install -e '.[mcp]'
```

Клиент сам запускает сервер. Отдельное окно Python держать открытым не нужно.
Каталог читается без игры; генератору нужны установленные карты HotA как
источник шаблонов. Компьютер должен быть включён во время генерации.

## 2. Claude Desktop — обычный чат в приложении Windows

1. Откройте **Settings → Developer → Edit Config**.
2. Файл Windows: `%APPDATA%\Claude\claude_desktop_config.json`.
3. Если конфигурация пустая, скопируйте содержимое
   [готового JSON](../examples/claude-desktop.mcp.json). Если серверы уже есть,
   добавьте только запись `h3m-forge` внутрь существующего `mcpServers`.
4. Полностью закройте Claude, в том числе из системного трея, и запустите снова.
5. Откройте новый чат и включите инструменты h3m-forge в меню подключений.
   Клиент может запросить разрешение на вызов инструмента.

Это подключение для локального чата Claude Desktop. У веб-версии claude.ai
и вкладки Claude Code отдельные подключения.
[Инструкция MCP для Claude Desktop](https://modelcontextprotocol.io/docs/develop/connect-local-servers),
[различия с облачными коннекторами Claude](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

## 3. Claude Code — если тестируете через терминал

Из корня проекта выполните одной строкой:

```powershell
claude mcp add --transport stdio --scope local --env PYTHONUTF8=1 h3m-forge -- "C:/Users/serge/PycharmProjects/h3m-forge/.venv-mcp/Scripts/python.exe" -m h3m.mcp_server --workspace "C:/Users/serge/PycharmProjects/h3m-forge" --game-dir "C:/Games/Heroes of Might and Magic III Complete"
```

Проверьте `claude mcp get h3m-forge`. В новой сессии Claude Code команда
`/mcp` показывает состояние подключения. Выберите нужную доступную модель
и используйте тот же тестовый запрос. Настройка `local` относится к текущему
проекту. [Официальная инструкция Claude Code](https://code.claude.com/docs/en/mcp).

## 4. ChatGPT — через Secure MCP Tunnel

Наш сервер использует stdio. В поле URL ChatGPT нельзя вставить путь к
Python. Документация OpenAI предусматривает туннель к локальному stdio-серверу.
Доступ к туннелям и Developer mode зависит от аккаунта и прав.

1. Откройте [Platform Tunnels](https://platform.openai.com/settings/organization/tunnels),
   создайте туннель и свяжите его с нужным рабочим пространством ChatGPT.
2. Сохраните `tunnel_id`, подготовьте runtime API key и установите
   `tunnel-client` по ссылке со страницы Platform для своей ОС.
3. Когда `tunnel-client` доступен в PowerShell, выполните:

```powershell
$env:PYTHONUTF8 = '1'
$env:CONTROL_PLANE_API_KEY = '<КЛЮЧ_ДЛЯ_ТУННЕЛЯ>'
tunnel-client init --sample sample_mcp_stdio_local --profile h3m-forge --tunnel-id '<ВАШ_TUNNEL_ID>' --mcp-command 'C:/Users/serge/PycharmProjects/h3m-forge/.venv-mcp/Scripts/python.exe -m h3m.mcp_server --workspace C:/Users/serge/PycharmProjects/h3m-forge --game-dir "C:/Games/Heroes of Might and Magic III Complete"'
tunnel-client doctor --profile h3m-forge --explain
tunnel-client run --profile h3m-forge
```

Оставьте клиент работающим. Ключ вводится локально, не в переписку.
Если нужной сборки клиента или прав нет, используйте локальный Codex ниже;
совместимость клиента туннеля с этим Windows здесь не проверялась.
[Secure MCP Tunnel: требования и команды](https://developers.openai.com/api/docs/guides/secure-mcp-tunnels).

В ChatGPT:

1. **Settings → Security and login → Developer mode**.
2. **Plugins → «+»**, название `h3m-forge`, **Connection → Tunnel**.
3. Выберите созданный туннель либо вставьте `tunnel_id`.
4. Создайте подключение, проверьте обнаруженные инструменты, добавьте его
   в новый разговор через меню инструментов.

Если выбранная модель не позволяет использовать подключение, выберите
другую модель с доступными MCP-инструментами. Конкретную доступность модели
в вашем аккаунте эта инструкция не предполагает.
[Подключение в ChatGPT](https://developers.openai.com/plugins/deploy/connect-chatgpt).

## 5. Локальный Codex — альтернативный тест моделей OpenAI

Готовые параметры: [codex.mcp.toml](../examples/codex.mcp.toml).
Добавьте таблицу в конфигурацию доверенного проекта `.codex/config.toml`,
сохранив остальные настройки. Перезапустите сессию и проверьте `/mcp`
в терминальном клиенте. В этом варианте ключ и туннель для MCP не нужны.
[Официальная документация](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## 6. Первый проверочный запрос

Сначала отправьте выбранному агенту только этот текст:

> Используй MCP h3m-forge. Вызови project_status, затем catalog_get для
> category="creatures", id=153, ruleset="hota_1.8.0" и catalog_get для
> category="artifacts", id=160, ruleset="hota_1.8.0". Назови существо и
> его здоровье, затем состав артефакта и суммарный доход в день. Пока не
> создавай карту. Если инструменты недоступны, сообщи об этом прямо.

Ожидается ответ **по результатам вызовов**: Нимфа, 4 здоровья; Золотой гусь,
компоненты 117/116/115, итоговый доход 7000 золота в день. Сейчас сервер
объявляет 18 инструментов. Одного правильного ответа без вызовов недостаточно
для проверки подключения.

После этого используйте один из [двух готовых сюжетных запросов](../examples/mcp-test-prompts.md).
Для каждой модели открывайте новый чат без истории разработки «Одиссеи».
Используйте одинаковые запрос, seed и настройки сложности; запишите имя модели.

## 7. Что сравнивать

| Проверка | Признак успеха |
|---|---|
| Подключение | Модель действительно вызывает MCP и получает результаты |
| Каталог | ID выбраны через каталог; неизвестные значения не придуманы |
| Создание | Возвращён существующий .h3m и отчёт генератора |
| Ограничения | Модель соблюдает схему generate_scenario, не обещает неподдержанные механики |
| Маршрут | Понятны обязательная линия и необязательное ответвление |
| Игра | Можно высадиться, пройти обязательные этапы и получить победу |
| Баланс | Бои требуют решений; после потерь нет обязательного ожидания найма |

Профиль `fixed` фиксирует авторские армии и награды на 80–200%, но не
доказывает баланс боя. Время игры 30–60 минут в запросах — цель теста.
Прохождение вручную остаётся отдельной проверкой.

Готовую карту ищите по пути из ответа генератора внутри `out/mcp/`.
Для игры скопируйте выбранный новый `.h3m` в
`C:\Games\Heroes of Might and Magic III Complete\Maps` под отдельным именем
и начните новую игру. Старое сохранение не подхватывает новую карту.

Если соединение не работает: проверьте абсолютные пути, перезапустите
клиент; в Claude Desktop откройте `%APPDATA%\Claude\logs`, для туннеля
повторите `doctor`. Первый вызов генерации может несколько минут собирать
кэш шаблонов; при доступной настройке таймаута дайте вызову до 600 секунд.
Сначала выясните результат предыдущего вызова, прежде чем повторять генерацию.

Локальная независимая проверка сервера, без генерации карты:

```powershell
Set-Location 'C:\Users\serge\PycharmProjects\h3m-forge'
& '.\.venv-mcp\Scripts\python.exe' tools/export_mcp_catalog.py
```

Она экспортирует схемы и примеры, но не доказывает соединение вашего чата.

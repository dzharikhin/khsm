# Кто хочет стать миллионером
### Как запускать
> Нужен docker и docker-compose
1. Скопировать ![.env.ex](./.env.ex) в `.env`
2. Заполнить `.env`
3. `docker-compose up`.  
Если не хочется, читать логи в консоли, то с ключом `-d`
4. Если нужно поднять не все, то надо перечислить нужные имена сервисов docker-compose через пробел
> Схема в базе поднимается через service.init() поэтому недостаточно запустить только db, если хочется работать с даными
5. Чтобы подцепиться к логам `docker-compose logs --follow --timestamps`
> здесь и далее может понадобиться sudo, если текущий юзер не в группе `docker`
6. Накатить на базу файл init-data.sql через psql. Порт базы экспозится, так что подключаться можно через хост
7. Для целей тестирования можно накатить еще test-data.sql
### Как остановить
- `docker-compose down`. Если требуется пересборка образов, то имеет смысл добавить опцию `--rmi local`
## Настройка бота
- у бота есть name, description и есть about
- не забыть про опции `/setjoingroups`, `/setprivacy`

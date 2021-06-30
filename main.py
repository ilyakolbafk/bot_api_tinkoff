from datetime import datetime, timedelta
import sqlite3
import telebot
from telebot import types
import pandas as pd
import mplfinance as mpf
import requests

with open('TOKENS.txt') as f:
    TOKEN_TINK = f.readline()
    TOKEN_TG = f.readline()
url_stocks = "https://api-invest.tinkoff.ru/openapi/sandbox/market/stocks"
url_bonds = "https://api-invest.tinkoff.ru/openapi/sandbox/market/bonds"
url_etfs = "https://api-invest.tinkoff.ru/openapi/sandbox/market/etfs"
url_currencies = "https://api-invest.tinkoff.ru/openapi/sandbox/market/currencies"
urls = [url_stocks, url_bonds, url_etfs, url_currencies]
conn = sqlite3.connect('exchange_hse.db')
cursor = conn.cursor()
try:
    query = 'CREATE TABLE "exchange" ("ID" INTEGER UNIQUE, "user_id" INTEGER, "figi" TEXT, "ticker" TEXT, PRIMARY KEY ("ID"))'
    cursor.execute(query)
except:
    pass
payload = ""
headers = {
    'Authorization': f'Bearer {TOKEN_TINK}'
}
all_tickers = {}
for url in urls:
    for t in requests.request("GET", url, headers=headers, data=payload).json()['payload']['instruments']:
        all_tickers.update({t['ticker']: t['figi']})
bot = telebot.TeleBot(TOKEN_TG)
start_text = "Привет, я бот, который позволит тебе отслеживать информацию о ценных бумагах, а также сохранять их " \
             "для дальнейшего отслеживания\nС чего начнем?"


@bot.message_handler(commands=['start'])
def send_start_keyboard(message, text=start_text):
    keyboard = types.ReplyKeyboardMarkup(row_width=2)
    itembtn1 = types.KeyboardButton('Найти тикер')
    itembtn2 = types.KeyboardButton('Показать информацию по тикеру')
    itembtn3 = types.KeyboardButton('Избранные тикеры')
    keyboard.add(itembtn1, itembtn2)
    keyboard.add(itembtn3)
    msg = bot.send_message(message.from_user.id, text=text, reply_markup=keyboard)
    bot.register_next_step_handler(msg, callback_worker_start)


def callback_worker_start(call):
    if call.text == "Найти тикер":
        msg = bot.send_message(call.chat.id, 'Введите несколько символов, которые есть в тикере, либо введите "*", '
                                             'для того чтобы посмотреть все тикеры')
        bot.register_next_step_handler(msg, find_tickers)
    elif call.text == 'Показать информацию по тикеру':
        msg = bot.send_message(call.chat.id, 'Введите название тикера')
        bot.register_next_step_handler(msg, show_ticker_info)
    elif call.text == 'Избранные тикеры':
        show_saved_ticker_info(call)
    else:
        send_start_keyboard(call, text="Я не понимаю :( Выберите один из пунктов меню:")


def find_tickers(msg):
    mask = msg.text.strip()
    if mask == '*':
        for message in message_form(sorted(all_tickers.keys())):
            bot.send_message(msg.chat.id, message)
    else:
        tickers = find_tickers_by_mask(msg.text)
        if len(tickers) == 0:
            bot.send_message(msg.chat.id, 'Ничего не найдено :(\nПопробуйте еще раз')
        else:
            for message in message_form(tickers):
                bot.send_message(msg.chat.id, message)
    send_start_keyboard(msg, "Чем еще могу помочь?")


def find_tickers_by_mask(mask):
    tickers_by_mask = []
    for ticker in sorted(all_tickers.keys()):
        if mask.upper() in ticker:
            tickers_by_mask.append(ticker)
    return tickers_by_mask


def message_form(message_list, sep=', '):
    messages = []
    message = ''
    for i, ticker in enumerate(message_list):
        message += ticker
        if len(message) > 3000:
            messages.append(message)
            message = ''
        else:
            message += sep
    messages.append(message[:-2])
    return messages


def show_ticker_info(msg):
    ticker = msg.text.upper()
    if ticker in sorted(all_tickers.keys()):
        figi = all_tickers[ticker]
        figi_info, level_info = get_ticker_info(figi)
        bot.send_message(msg.chat.id,
                         f'Название компании (фонда, валюты): {figi_info["name"]}\nТикер: {figi_info["ticker"]}\n'
                         f'Валюта: {figi_info["currency"]}\nСтатус торговли: {level_info["tradeStatus"]}\n'
                         f'Последняя цена: {level_info["lastPrice"]}')
        send_ticker_keyboard(msg, figi)
    else:
        bot.send_message(msg.chat.id, 'Компании (фонда, валюты) с таким тикером не найдено :(')
        send_start_keyboard(msg, "Чем еще могу помочь?")


def get_ticker_info(figi):
    figi_info = requests.request("GET", 'https://api-invest.tinkoff.ru/openapi/sandbox/market/search/by-figi',
                                 headers=headers,
                                 data={"figi": figi}).json()["payload"]
    level_info = requests.request("GET", 'https://api-invest.tinkoff.ru/openapi/sandbox/market/orderbook',
                                  headers=headers,
                                  data={"figi": figi, "depth": 0}).json()["payload"]
    return figi_info, level_info


def send_ticker_keyboard(message, figi, text="Выберите дальнейшее действие"):
    keyboard = types.ReplyKeyboardMarkup(row_width=3)
    itembtn1 = types.KeyboardButton('Посмотреть изменение цены')
    itembtn2 = types.KeyboardButton('Посмотреть стакан тикера')
    itembtn3 = types.KeyboardButton('Добавить в избранное')
    itembtn4 = types.KeyboardButton('Построить график изменения цены')
    itembtn5 = types.KeyboardButton('Удалить из избранного')
    itembtn6 = types.KeyboardButton('Назад')
    keyboard.add(itembtn1, itembtn2)
    keyboard.add(itembtn3, itembtn4)
    keyboard.add(itembtn5, itembtn6)
    msg = bot.send_message(message.from_user.id, text=text, reply_markup=keyboard)
    bot.register_next_step_handler(msg, callback_worker_ticker, figi)


def callback_worker_ticker(call, figi):
    if call.text == "Добавить в избранное":
        add_to_saved(call, figi)
    elif call.text == "Удалить из избранного":
        remove_from_saved(call, figi)
    elif call.text == "Посмотреть изменение цены":
        send_time_keyboard(call, figi)
    elif call.text == "Посмотреть стакан тикера":
        show_level(call, figi)
    elif call.text == "Построить график изменения цены":
        send_time_keyboard(call, figi, "Выберите временной промежуток для каждой свечи", '')
    elif call.text == "Назад":
        send_start_keyboard(call, "Чем еще могу помочь?")
    else:
        send_ticker_keyboard(call, figi, "Я не понимаю :-( Выберите один из пунктов меню:")


def add_to_saved(msg, figi):
    with sqlite3.connect('exchange_hse.db') as con:
        cursor = con.cursor()
        figi_info, level_info = get_ticker_info(figi)
        cursor.execute(f'SELECT figi FROM exchange WHERE user_id=={msg.from_user.id} AND figi==?', (figi,))
        if len(list(cursor.fetchall())) == 0:
            cursor.execute('INSERT INTO exchange (user_id, figi, ticker) VALUES (?, ?, ?)',
                           (msg.from_user.id, figi,
                            f'Название компании: {figi_info["name"]}\nТикер: {figi_info["ticker"]}\n'
                            f'Валюта: {figi_info["currency"]}\nСтатус торговли: {level_info["tradeStatus"]}\n'
                            f'Последняя цена: {level_info["lastPrice"]}'))
            con.commit()
            bot.send_message(msg.chat.id, 'Информация о тикере добавлена в избранное')
        else:
            bot.send_message(msg.chat.id, 'Информация о тикере уже есть в избранном')
    send_ticker_keyboard(msg, figi)


def remove_from_saved(msg, figi):
    with sqlite3.connect('exchange_hse.db') as con:
        cursor = con.cursor()
        cursor.execute(f'SELECT figi FROM exchange WHERE user_id=={msg.from_user.id} AND figi==?', (figi,))
        if len(list(cursor.fetchall())) == 0:
            bot.send_message(msg.chat.id, 'Информация о тикере отсутствует в избранном')
        else:
            cursor.execute(f'DELETE FROM exchange WHERE user_id=={msg.from_user.id} AND figi==?', (figi,))
            con.commit()
            bot.send_message(msg.chat.id, 'Информация о тикере удалена из избранного избранное')
        send_ticker_keyboard(msg, figi)


def show_level(msg, figi):
    level = requests.request("GET", 'https://api-invest.tinkoff.ru/openapi/sandbox/market/orderbook',
                             headers=headers,
                             data={"figi": figi, "depth": 10}).json()["payload"]
    bids = level['bids']
    asks = level['asks']
    if level['tradeStatus'] == 'NotAvailableForTrading':
        bot.send_message(msg.chat.id, 'В данный момент торги по тикеру не проводятся')
    else:
        res = []
        for ask in asks:
            res.append(f'Цена: {ask["price"]}, количество: {ask["quantity"]}\n')
        res.append('Заявки на продажу:\n')
        res.reverse()
        res.append('\nЗаявки на покупку:\n')
        for bid in bids:
            res.append(f'Цена: {bid["price"]}, количество: {bid["quantity"]}\n')
        bot.send_message(msg.chat.id, ''.join(res))
    send_ticker_keyboard(msg, figi)


def send_time_keyboard(message, figi, text="Выберите временной промежуток", func='price'):
    keyboard = types.ReplyKeyboardMarkup(row_width=3)
    itembtn1 = types.KeyboardButton('5 минут')
    itembtn2 = types.KeyboardButton('15 минут')
    itembtn3 = types.KeyboardButton('30 минут')
    itembtn4 = types.KeyboardButton('Час')
    itembtn5 = types.KeyboardButton('День')
    itembtn6 = types.KeyboardButton('Неделя')
    itembtn7 = types.KeyboardButton('Месяц')
    keyboard.add(itembtn1, itembtn2, itembtn3)
    keyboard.add(itembtn4, itembtn5)
    keyboard.add(itembtn6, itembtn7)
    msg = bot.send_message(message.from_user.id, text=text, reply_markup=keyboard)
    if func == 'price':
        bot.register_next_step_handler(msg, callback_show_price_change, figi)
    else:
        bot.register_next_step_handler(msg, callback_show_plot, figi)


def callback_show_price_change(call, figi):
    if call.text == '5 минут':
        time = '1min'
        delta = timedelta(minutes=5)
    elif call.text == '15 минут':
        time = '1min'
        delta = timedelta(minutes=15)
    elif call.text == '30 минут':
        time = '3min'
        delta = timedelta(minutes=30)
    elif call.text == 'Час':
        time = '5min'
        delta = timedelta(minutes=60)
    elif call.text == 'День':
        time = 'hour'
        delta = timedelta(days=1)
    elif call.text == 'Неделя':
        time = 'day'
        delta = timedelta(days=7)
    elif call.text == 'Месяц':
        time = 'day'
        delta = timedelta(days=30)
    else:
        bot.send_message(call.chat.id, "Такого ответа нет :(")
        send_time_keyboard(call, figi)
        return
    figi_info = requests.request("GET", 'https://api-invest.tinkoff.ru/openapi/sandbox/market/candles',
                                 headers=headers,
                                 data={"figi": figi,
                                       "from": (datetime.now() - delta).strftime('%Y-%m-%dT%H:%M:00.000000+03:00'),
                                       "to": datetime.now().strftime('%Y-%m-%dT%H:%M:00.000000+03:00'),
                                       "interval": time}).json()['payload']['candles']
    if len(figi_info) == 0:
        bot.send_message(call.chat.id, "Торги за текущее время не проводились или сейчас не проводятся")
        send_ticker_keyboard(call, figi)
    else:
        open_price = figi_info[0]["o"]
        close_price = figi_info[-1]["c"]
        change = round((close_price - open_price) * 100 / open_price, 2)
        if change == 0:
            change_message = f'Цена не изменилась'
        elif change > 0:
            change_message = f'Цена выросла на {change}%'
        else:
            change_message = f'Цена упала на {abs(change)}%'
        bot.send_message(call.chat.id, f'Цена открытия: {str(open_price)}\nЦена закрытия: {str(close_price)}\n'
                                       f'{change_message}')
        send_ticker_keyboard(call, figi)


def callback_show_plot(call, figi):
    if call.text == '5 минут':
        time = '5min'
        delta = timedelta(minutes=5 * 75)
    elif call.text == '15 минут':
        time = '15min'
        delta = timedelta(minutes=15 * 75)
    elif call.text == '30 минут':
        time = '30min'
        delta = timedelta(minutes=30 * 75)
    elif call.text == 'Час':
        time = 'hour'
        delta = timedelta(minutes=60 * 75)
    elif call.text == 'День':
        time = 'day'
        delta = timedelta(days=75)
    elif call.text == 'Неделя':
        time = 'week'
        delta = timedelta(days=7 * 75)
    elif call.text == 'Месяц':
        time = 'month'
        delta = timedelta(days=30 * 75)
    else:
        bot.send_message(call.chat.id, "Такого ответа нет :(")
        send_time_keyboard(call, figi)
        return
    candles = requests.request("GET", 'https://api-invest.tinkoff.ru/openapi/sandbox/market/candles',
                               headers=headers,
                               data={"figi": figi,
                                     "from": (datetime.now() - delta).strftime('%Y-%m-%dT%H:%M:00.000000+03:00'),
                                     "to": datetime.now().strftime('%Y-%m-%dT%H:%M:00.000000+03:00'),
                                     "interval": time}).json()['payload']['candles']
    figi_info, _ = get_ticker_info(figi)
    df = pd.DataFrame(candles)[['o', 'c', 'h', 'l', 'time']]
    df.columns = ['Open', 'Close', 'High', 'Low', 'time']
    df.index = pd.DatetimeIndex(df['time'])
    mpf.plot(df, type='candle', style='charles',
             title=figi_info['name'],
             ylabel=figi_info['currency'],
             savefig='plot.png')
    bot.send_photo(call.chat.id, photo=open('plot.png', 'rb'))
    send_ticker_keyboard(call, figi)


def show_saved_ticker_info(msg):
    with sqlite3.connect('exchange_hse.db') as con:
        cursor = con.cursor()
        cursor.execute(f'SELECT figi, ticker FROM exchange WHERE user_id=={msg.from_user.id}')
        tickers = get_saved_string(msg, cursor.fetchall())
    for message in message_form(tickers, ' \n'):
        bot.send_message(msg.chat.id, message)
    send_start_keyboard(msg, "Чем еще могу помочь?")


def get_saved_string(msg, tickers):
    with sqlite3.connect('exchange_hse.db') as con:
        cursor = con.cursor()
        cursor.execute(f'DELETE FROM exchange WHERE user_id=={msg.from_user.id}')
        if len(tickers) == 0:
            return "Избранное пусто"
        saved = ['Изменения цены показаны с последнего посещения избранного\n']
        for figi, ticker in list(tickers):
            figi_info, level_info = get_ticker_info(figi)
            new_ticker = f'Название компании: {figi_info["name"]}\nТикер: {figi_info["ticker"]}\n' \
                         f'Валюта: {figi_info["currency"]}\nСтатус торговли: {level_info["tradeStatus"]}\n' \
                         f'Последняя цена: {level_info["lastPrice"]}'
            cursor.execute('INSERT INTO exchange (user_id, figi, ticker) VALUES (?, ?, ?)',
                           (msg.from_user.id, figi, new_ticker))
            con.commit()
            previous_last_price = float(str(ticker).split()[-1].strip())
            change = round((level_info["lastPrice"] - previous_last_price) * 100 / previous_last_price, 2)

            if change == 0:
                saved.append(f'{str(new_ticker)}\n')
            elif change > 0:
                saved.append(f'{str(new_ticker)} (цена выросла на {change}%)\n')
            else:
                saved.append(f'{str(new_ticker)} (цена упала на {abs(change)}%)\n')
    return saved


bot.polling(none_stop=True)

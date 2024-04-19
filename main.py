import asyncio
import email
import json
import base64
import secrets
import string
from datetime import datetime, timedelta
import re
import time
import psycopg2
from PIL import Image

import random
from email.header import decode_header

from io import BytesIO
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver

from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os
from pyrogram import Client, filters
import imaplib
from bs4 import BeautifulSoup
import httpx
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

from keep_alive import keep_alive

load_dotenv('key.env')
domain = os.getenv('DOMAIN')
api_token = os.getenv('API_KEY_SIMPLE')
gmail_user = os.getenv('GMAIL_USER')
gmail_pass = os.getenv('GMAIL_PASS')
imap_url = "imap.gmail.com"

conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASS'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT')
)

messages = json.load(open("browser.i18n.json", encoding="utf8"))

key = os.getenv('ENCRYPTION_KEY')
cipher_suite = Fernet(key)

app = Client(name=os.getenv('BOT_NAME'), api_id=os.getenv('API_ID'), api_hash=os.getenv('API_HASH'),
             bot_token=os.getenv('BOT_TOKEN'))

options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

home_button = [InlineKeyboardButton("↩️ Home", callback_data="home")]


# Broadcast
@app.on_message(filters.command('broadcast') & filters.private & filters.user(int(os.getenv('ACCOUNT_ID'))))
async def broadcast(app, message):
    cur = conn.cursor()
    cur.execute("UPDATE users SET step = %s WHERE id = %s", ("broadcast", message.from_user.id))
    conn.commit()

    await message.reply_text(
        text="📣 Invia ora il messaggio da inviare a tutti gli utenti!",
        quote=True)


# Comando start
@app.on_message(filters.command('start') & filters.private)
async def start(app, message):
    try:
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE id = %s",
                    (message.from_user.id,))
        rowUser = cur.fetchone()

        if rowUser is None:

            home_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["channel_button"],
                                      url="t.me/FreeReadsChannel")],
                [InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["profile_button"],
                                      callback_data="profile"),
                 InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["category_button"],
                                      callback_data="categories")],
                [InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["populars_button"],
                                      callback_data="populars")],
                [InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["language_button"],
                                      callback_data="language"),
                 InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["support_button"],
                                      callback_data="assistence")],
                [InlineKeyboardButton(messages.get(message.from_user.language_code, "en")["search_button"],
                                      callback_data="search")]
            ])

            sentMessage = await message.reply_text(
                text=messages.get(message.from_user.language_code, "en")['welcome'].format(
                    username=message.from_user.mention()),
                quote=True,
                reply_markup=home_markup)

            idAccount = 0
            actUsers = 0

            cur.execute("SELECT * FROM accounts WHERE act_users < 2")
            rowAccount = cur.fetchone()
            if rowAccount is not None:
                idAccount = rowAccount[0]
                actUsers = rowAccount[1]

            cur.execute("UPDATE accounts SET act_users = %s WHERE id = %s", (actUsers + 1, idAccount))

            cur.execute(
                "INSERT INTO users (id, last_message, account_id, download_limit, downloaded, step, lang) VALUES (%s, %s, "
                "%s,"
                "%s, %s, %s, %s)",
                (message.from_user.id, sentMessage.id, idAccount, 5, 0, "home", message.from_user.language_code))
            conn.commit()

        if rowUser is not None:
            home_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[rowUser[6]]["channel_button"],
                                      url="t.me/FreeReadsChannel")],
                [InlineKeyboardButton(messages[rowUser[6]]["profile_button"],
                                      callback_data="profile"),
                 InlineKeyboardButton(messages[rowUser[6]]["category_button"],
                                      callback_data="categories")],
                [InlineKeyboardButton(messages[rowUser[6]]["populars_button"],
                                      callback_data="populars")],
                [InlineKeyboardButton(messages[rowUser[6]]["language_button"],
                                      callback_data="language"),
                 InlineKeyboardButton(messages[rowUser[6]]["support_button"], callback_data="assistence")],
                [InlineKeyboardButton(messages[rowUser[6]]["search_button"],
                                      callback_data="search")]
            ])

            now = datetime.now()
            hour = datetime.now().replace(day=now.day, hour=21, minute=0, second=0)
            difference = hour - now

            await message.reply_text(

                text=messages[rowUser[6]]["home"].format(username=message.from_user.mention(),
                                                         difference=str(difference).split('.')[0],
                                                         downloaded=rowUser[4]),
                reply_markup=home_markup
            )

    except Exception as e:
        app.send_message(
            text="<i><b>Eccezione messaggio, utente: " + message.from_user.id + "</b>, log: " + str(e) + "</i>",
            chat_id=os.getenv('ACCOUNT_ID'))


# Supporto
@app.on_message(filters.text & filters.private & filters.reply & filters.user(int(os.getenv('ACCOUNT_ID'))))
async def support_reply(app, message):
    await message.copy(message.reply_to_message.text.split(" ")[1])
    await app.send_message(
        text="<i>👌🏻 Messaggio <b>inviato</b> all'utente!</i>",
        chat_id=message.from_user.id, reply_markup=InlineKeyboardMarkup([
            home_button
        ]))


# Ricerca
@app.on_message(filters.text & filters.private)
async def request(app, message):
    try:

        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE id = %s",
                    (message.from_user.id,))
        rowUser = cur.fetchone()

        if rowUser is not None and rowUser[5] == 'assistence':
            await app.send_message(
                text="‼️<i><b> " + str(
                    message.from_user.id) + "</b> ha inviato un messaggio!\n\n📃 " + message.text + "</i>",
                chat_id=os.getenv('ACCOUNT_ID'))

            await app.send_message(text=messages[rowUser[6]]["assistence_received"],
                                   chat_id=message.from_user.id, reply_markup=InlineKeyboardMarkup([home_button]))

        if rowUser is not None and rowUser[5] == 'search':
            stateMessage = await app.send_message(text=messages[rowUser[6]]["search_loading"],
                                                  chat_id=message.from_user.id)

            async with httpx.AsyncClient() as http:
                response = await http.get(domain + '/s/' + message.text, timeout=30, cookies={"siteLanguage": "en"})

            content = response
            soup = BeautifulSoup(content, 'lxml')

            box = soup.find("div", {"id": "searchResultBox"})

            if box != None:
                divs = box.find_all("div", {"class": "resItemBox resItemBoxBooks exactMatch"})

                if len(divs) > 0:
                    result = []
                    for div in divs:
                        resultJson = {}
                        resultJson['name'] = div.find("h3", {"itemprop": "name"}).text.strip()
                        pub = div.find("a", {"title": "Publisher"})
                        if pub is not None:
                            resultJson['pub'] = pub.text
                        resultJson['url'] = (div.find("h3", {"itemprop": "name"}).find('a', href=True).get('href'))
                        label = div.find("div", {"class": "bookProperty property_year"})
                        if label is not None:
                            resultJson['year'] = label.find("div", {"class": "property_value"}).text
                        authors = div.find("div", {"class": "authors"}).find_all('a', href=True)
                        lang = div.find("div", {"class": "property_value text-capitalize"})
                        if lang is not None:
                            resultJson['lang'] = lang.text

                        authorsText = []
                        for author in authors:
                            authorsText.append(author.text)
                        resultJson['author'] = ', '.join(authorsText)
                        result.append(resultJson)

                    results = messages[rowUser[6]]["search_results"].format(query=message.text.strip().lower())

                    listButtonsRow = []
                    listButtonsTotal = []

                    await app.edit_message_text(text=messages[rowUser[6]]["search_found"],
                                                chat_id=message.from_user.id,
                                                message_id=stateMessage.id)

                    for res in result[:10]:
                        index = result.index(res)
                        complete = domain + res['url']

                        print(complete)

                        short_url = await url_shortener(complete)

                        if 'lang' in res.keys():
                            if len(res['author']) == 0 and 'pub' not in res.keys() and 'year' not in res.keys():
                                results = results + f"""{index + 1})<b> {res['name']}</b> - <i>{res['lang']}</i>\n\n"""
                            else:
                                results = results + f"""{index + 1})<b> {res['name']}</b> - <i>{res['lang']}</i>\n"""

                        else:
                            if len(res['author']) == 0 and 'pub' not in res.keys() and 'year' not in res.keys():
                                results = results + f"""{index + 1})<b> {res['name']}</b>\n\n"""
                            else:
                                results = results + f"""{index + 1})<b> {res['name']}</b>\n"""

                        if len(res['author']) > 0:

                            if 'year' not in res.keys() and 'pub' not in res.keys():
                                results = results + f"""     └ 🖊️ <i>{res['author']}</i> \n\n"""
                            else:
                                results = results + f"""     ├ 🖊️ <i>{res['author']}</i> \n"""

                        if 'year' in res.keys():
                            if 'pub' in res.keys():
                                results = results + f"""     ├ ⌛ <i>{res['year']}</i> \n"""
                            else:
                                results = results + f"""     └ ⌛ <i>{res['year']}</i> \n\n"""

                        if 'pub' in res.keys():
                            results = results + f"""     └ 📘 <i>{res['pub']}</i> \n\n"""

                        if index % 5 == 0:
                            listButtonsRow = []
                            listButtonsTotal.append(listButtonsRow)
                        listButtonsRow.append(InlineKeyboardButton(
                            str(index + 1),
                            callback_data="formats/" + short_url
                        ))

                    reply_markup = InlineKeyboardMarkup(listButtonsTotal)

                    await app.edit_message_text(
                        text=results + messages[rowUser[6]]["search_indications"],
                        disable_web_page_preview=True, reply_markup=reply_markup,
                        message_id=stateMessage.id, chat_id=message.from_user.id)
                else:
                    await app.edit_message_text(
                        text=messages[rowUser[6]]["search_not_found"].format(title=message.text.strip().lower()),
                        message_id=stateMessage.id, chat_id=message.from_user.id)
            else:
                await app.edit_message_text(
                    text=messages[rowUser[6]]["search_not_found"].format(title=message.text.strip().lower()),
                    message_id=stateMessage.id, chat_id=message.from_user.id)

        if rowUser is not None and rowUser[5] == 'broadcast':
            await send_message_followers(message)
            await app.send_message(
                text="<i>👌🏻 Messaggio inviato a <b>tutti</b> gli utenti!</i>",
                chat_id=message.from_user.id, reply_markup=InlineKeyboardMarkup([
                    home_button
                ]))

    except Exception as e:
        app.send_message(
            text="<i><b>Eccezione messaggio, utente: " + message.from_user.id + "</b>, log: " + str(e) + "</i>",
            chat_id=os.getenv('ACCOUNT_ID'))

    await message.delete()


@app.on_callback_query()
async def answer(app, callback_query):
    try:
        cur = conn.cursor()

        cur.execute("""
            SELECT users.*, accounts.*
            FROM users
            JOIN accounts ON users.account_id = accounts.id
            WHERE users.id = %s
        """, (callback_query.from_user.id,))

        rowUserAndAccount = cur.fetchone()

        reply_markup = InlineKeyboardMarkup([
            home_button
        ])

        # Categorie
        if callback_query.data == "categories":
            await callback_query.answer(messages[rowUserAndAccount[6]]["wip"], show_alert=True)

        # Popolari
        if callback_query.data == "populars":
            await callback_query.answer(messages[rowUserAndAccount[6]]["wip"], show_alert=True)

        # Assistenza
        if callback_query.data == "assistence":
            cur.execute("UPDATE users SET step = %s WHERE id = %s",
                        ("assistence", callback_query.from_user.id))
            conn.commit()

            await app.edit_message_text(text=messages[rowUserAndAccount[6]]["assistence"],
                                        chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                        reply_markup=reply_markup)

        # Ricerca
        if callback_query.data == "search":
            cur.execute("UPDATE users SET step = %s WHERE id = %s",
                        ("search", callback_query.from_user.id))
            conn.commit()

            await app.edit_message_text(text=messages[rowUserAndAccount[6]]["search"],
                                        chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                        reply_markup=reply_markup)

        # Modifica Lingua
        if len(callback_query.data.split("_")) == 3 and callback_query.data.split("_")[2] == "set":
            cur.execute("UPDATE users SET lang = %s WHERE id = %s",
                        (callback_query.data.split("_")[0], callback_query.from_user.id))
            conn.commit()

            reply_markup = InlineKeyboardMarkup([home_button])

            await app.edit_message_text(text=messages[callback_query.data.split("_")[0]]["lang_edit_succ"],
                                        chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                        reply_markup=reply_markup)

        # Lingua
        if callback_query.data == "language":

            horizList = []
            vertList = []
            lang_list = []
            for keys in messages:
                if rowUserAndAccount[6] not in keys:
                    lang_list.append(keys + "_button_set")

            for lang in lang_list:
                horizList.append(InlineKeyboardButton(messages[lang.split("_")[0]][lang], callback_data=lang))
                if len(horizList) == 2:
                    vertList.append(horizList)
                    horizList = []
                if len(horizList) < 2 and lang_list[-1] == lang:
                    vertList.append(horizList)

            vertList.append(home_button)
            reply_markup = InlineKeyboardMarkup(vertList)

            await app.edit_message_text(text=messages[rowUserAndAccount[6]]["language"],
                                        chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                        reply_markup=reply_markup)

        # Libri Scaricati
        if callback_query.data == "downloadedBooks":
            await callback_query.answer(messages[rowUserAndAccount[6]]["wip"], show_alert=True)

        # reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Indietro", callback_data="profile")]])
        # await app.edit_message_text(text=messages[rowUserAndAccount[6]]["library"],
        #                           chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
        #                          reply_markup=reply_markup)

        # Preferiti
        if callback_query.data == "favorites":
            await callback_query.answer(messages[rowUserAndAccount[6]]["wip"], show_alert=True)

        # WishList
        if callback_query.data == "wishlist":
            await callback_query.answer(messages[rowUserAndAccount[6]]["wip"], show_alert=True)

        # Profilo
        if callback_query.data == "profile":
            reply_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Libri scaricati", callback_data="downloadedBooks"),
                 InlineKeyboardButton("⭐ Preferiti", callback_data="favorites")],
                [InlineKeyboardButton("🔖 Lista desideri", callback_data="wishlist")],
                home_button
            ])

            await app.edit_message_text(text=messages[rowUserAndAccount[6]]['profile'],
                                        chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                        reply_markup=reply_markup)

        # Home
        if callback_query.data == "home":
            cur.execute("UPDATE users SET step = %s WHERE id = %s",
                        ("home", callback_query.from_user.id))
            conn.commit()

            home_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton(messages[rowUserAndAccount[6]]["channel_button"],
                                      url="t.me/FreeReadsChannel")],
                [InlineKeyboardButton(messages[rowUserAndAccount[6]]["profile_button"],
                                      callback_data="profile"),
                 InlineKeyboardButton(messages[rowUserAndAccount[6]]["category_button"],
                                      callback_data="categories")],
                [InlineKeyboardButton(messages[rowUserAndAccount[6]]["populars_button"],
                                      callback_data="populars")],
                [InlineKeyboardButton(messages[rowUserAndAccount[6]]["language_button"],
                                      callback_data="language"),
                 InlineKeyboardButton(messages[rowUserAndAccount[6]]["support_button"], callback_data="assistence")],
                [InlineKeyboardButton(messages[rowUserAndAccount[6]]["search_button"],
                                      callback_data="search")]
            ])

            now = datetime.now()
            hour = datetime.now().replace(day=now.day, hour=21, minute=0, second=0)
            difference = hour - now

            await app.edit_message_text(
                text=messages[rowUserAndAccount[6]]['home'].format(username=callback_query.from_user.mention(),
                                                                   difference=str(difference).split('.')[0],
                                                                   downloaded=rowUserAndAccount[4]),
                reply_markup=home_markup,
                chat_id=callback_query.from_user.id, message_id=callback_query.message.id
            )

        # Formati
        if callback_query.data.split("/", 1)[0] == "formats":

            formatState = await app.send_message(text=messages[rowUserAndAccount[6]]['formats_loading'],
                                                 chat_id=callback_query.from_user.id)

            url = callback_query.data.split("/", 1)[1]

            cipher_text = base64.b64decode(rowUserAndAccount[9])
            cookies = json.loads(cipher_suite.decrypt(cipher_text).decode())

            original_url = await get_original_url(url)

            driver = webdriver.Chrome(options=options)

            driver.execute_cdp_cmd('Network.enable', {})
            cookie_pass = {"name": "siteLanguage", "value": "en", "domain": "z-library.se"}
            driver.execute_cdp_cmd('Network.setCookie', cookie_pass)
            driver.execute_cdp_cmd('Network.disable', {})

            driver.get(original_url)

            for name, value in cookies.items():
                cookie = {"name": name, "value": value}
                driver.add_cookie(cookie)

            driver.refresh()

            try:
                element = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a.addDownloadedBook"))
                )
                await app.edit_message_text(text=messages[rowUserAndAccount[6]]['formats_found'],
                                            chat_id=callback_query.from_user.id, message_id=formatState.id)

                soup = BeautifulSoup(driver.page_source, 'html.parser')

                time.sleep(5)
                src = driver.execute_script("""
                    let cover = document.querySelector("z-cover");
                    if (cover) {
                        let shadowRoot = cover.shadowRoot;
                        if (shadowRoot) {
                            let img = shadowRoot.querySelector('img');
                            if (img) {
                                return img.getAttribute('src') || img.getAttribute('data-src');
                            }
                        }
                    }
                    return null;
                """)

                drop = soup.find('ul', {'class': 'dropdown-menu'})
                downloadListHoriz = []
                downloadListVert = []
                aButton = soup.find('a', {'class': 'btn btn-primary addDownloadedBook'}, href=True)
                urlButton = aButton.get('href')
                completeButton = "https://z-library.se" + urlButton
                shortButton = await url_shortener(completeButton)

                aS = drop.find_all('a', {'class': 'addDownloadedBook'}, href=True)
                aS.append(aButton)
                pdf = 0
                for a in aS:
                    if a is not None:

                        text = a.text.upper()

                        if "pdf" in text.lower():
                            pdf = 1

                        if a == aS[-1]:
                            text = re.search(r'\((.+?)\)', aButton.text).group(1).upper().replace(",", "")

                        url = a.get('href')

                        complete = "https://z-library.se" + url
                        short_url = await url_shortener(complete)

                        downloadListHoriz.append(InlineKeyboardButton(
                            text,
                            callback_data="download/" + short_url
                        ))
                        if len(downloadListHoriz) == 3:
                            downloadListVert.append(downloadListHoriz)
                            downloadListHoriz = []
                        if a == aS[-1] and len(downloadListHoriz) < 3:
                            downloadListVert.append(downloadListHoriz)
                if pdf == 0:
                    downloadListVert.append([InlineKeyboardButton(
                        "📄 PDF",
                        callback_data="download/" + shortButton + "-convert")])
                reply_markup = InlineKeyboardMarkup(
                    downloadListVert
                )
                book = soup.find("h1", {"itemprop": "name"})

                async with httpx.AsyncClient() as http:
                    coverFile = (await http.get(src))
                book_cover = Image.open(BytesIO(coverFile.content))

                altezza_massima = 400
                rapporto = altezza_massima / book_cover.height
                dimensione_nuova = (int(book_cover.width * rapporto), altezza_massima)
                book_cover_resized = book_cover.resize(dimensione_nuova, Image.LANCZOS)

                beige_back = Image.new('RGB', (1080, 580), (245, 245, 220))
                position = ((beige_back.width - book_cover_resized.width) // 2,
                            (beige_back.height - book_cover_resized.height) // 2)
                beige_back.paste(book_cover_resized, position)
                buffer = BytesIO()
                beige_back.save(buffer, format='JPEG')
                buffer.seek(0)
                await app.send_photo(photo=buffer,
                                     caption=messages[rowUserAndAccount[6]]['formats_results'].format(
                                         title=book.text.strip().lower()),
                                     reply_markup=reply_markup, chat_id=callback_query.from_user.id)

                await formatState.delete()

            except:

                await app.edit_message_text(
                    text=messages[rowUserAndAccount[6]]['formats_not_found'],
                    chat_id=callback_query.from_user.id,
                    message_id=formatState.id)
            driver.quit()

        # Download
        if callback_query.data.split("/", 1)[0] == "download":
            try:
                channel_member = await app.get_chat_member("freereadschannel", callback_query.from_user.id)
            except:
                channel_member = None

            if channel_member is None:
                await app.send_message(text=messages[rowUserAndAccount[6]]["channel_check"],
                                       chat_id=callback_query.from_user.id)

            if rowUserAndAccount[5] == "waiting":
                await app.send_message(text=messages[rowUserAndAccount[6]]["waiting_download"],
                                       chat_id=callback_query.from_user.id)

            if channel_member is not None and rowUserAndAccount[5] != "waiting":
                urlNotClean = callback_query.data.split("/", 1)[1]
                url = urlNotClean.split("-", 1)[0]

                file_url = await get_original_url(url)
                idBook = re.search(r'/dl/(\d+)/', file_url).group(1)

                cur.execute("SELECT * FROM books WHERE id = %s", (idBook,))
                rowBook = cur.fetchone()

                cur.execute("UPDATE users SET step = %s WHERE id = %s", ("waiting", callback_query.from_user.id))
                conn.commit()

                download_messaggio = await app.send_message(
                    text=messages[rowUserAndAccount[6]]["download_started"],
                    chat_id=callback_query.from_user.id)

                if rowBook is not None:

                    cur.execute("""   SELECT accounts.cookies
                                            FROM books
                                            INNER JOIN downloadedbooks ON books.id = downloadedbooks.book_id
                                            INNER JOIN users ON users.id = downloadedbooks.user_id
                                            INNER JOIN accounts ON accounts.id = users.account_id
                                            WHERE books.id = %s AND downloadedbooks.first = true
                                            """,
                                (rowBook[0],))
                    rowBookAndDownloaded = cur.fetchone()

                    cur.execute("SELECT * FROM downloadedBooks WHERE user_id = %s AND book_id = %s",
                                (callback_query.from_user.id, idBook))
                    rowBookAndUser = cur.fetchone()

                    cipher_text = base64.b64decode(rowBookAndDownloaded[0])
                    cookies = json.loads(cipher_suite.decrypt(cipher_text).decode())

                    async with httpx.AsyncClient() as http:
                        res = await http.get(rowBook[2], cookies=cookies)
                        last = await http.get(res.headers['Location'])
                    file = BytesIO(last.content)

                    name = re.search(r'filename="(.+?)"', last.headers['content-disposition']).group(1).replace(
                        ' (Z-Library)',
                        '')
                    file.name = name

                    if "convert" in callback_query.data:
                        file = await converter(cookies, rowBook[2], download_messaggio, callback_query, name,
                                               rowUserAndAccount)

                    await download_messaggio.delete()

                    progress_message = await app.send_message(text=messages[rowUserAndAccount[6]]["progress_message"],
                                                              chat_id=rowUserAndAccount[0])
                    if rowBookAndUser is not None:
                        await app.send_document(callback_query.from_user.id, file,
                                                caption=messages[rowUserAndAccount[6]][
                                                    "already_downloaded_yours"].format(
                                                    downloaded=rowUserAndAccount[4]),
                                                progress=progress_bar(rowUserAndAccount, progress_message, app))
                    if rowBookAndUser is None:
                        await app.send_document(chat_id=callback_query.from_user.id, document=file,
                                                caption=messages[rowUserAndAccount[6]][
                                                    "already_downloaded_them"].format(
                                                    downloaded=rowUserAndAccount[4]),
                                                progress=progress_bar(rowUserAndAccount, progress_message, app))

                        cur.execute("INSERT INTO downloadedbooks(user_id, book_id, first) VALUES(%s, %s , %s)",
                                    (rowUserAndAccount[0], rowBook[0], False))

                    cur.execute("UPDATE users SET step = %s WHERE id = %s",
                                ("search", callback_query.from_user.id))
                    conn.commit()

                if rowBook is None:
                    if rowUserAndAccount is not None and rowUserAndAccount[4] < rowUserAndAccount[3]:

                        cipher_text = base64.b64decode(rowUserAndAccount[9])
                        cookies = json.loads(cipher_suite.decrypt(cipher_text).decode())

                        async with httpx.AsyncClient() as http:
                            res = await http.get(await get_original_url(url), cookies=cookies)
                            print(res.headers['Location'])
                            last = await http.get(res.headers['Location'])

                        file = BytesIO(last.content)

                        name = re.search(r'filename="(.+?)"', last.headers['content-disposition']).group(1).replace(
                            ' (Z-Library)',
                            '')
                        file.name = name

                        if "convert" in callback_query.data:
                            file = await converter(cookies, file_url, download_messaggio, callback_query, name,
                                                   rowUserAndAccount)

                        await app.send_document(document=file,
                                                caption=messages[rowUserAndAccount[6]]["downloaded_book"].format(
                                                    new_count=rowUserAndAccount[4] + 1),
                                                chat_id=callback_query.from_user.id)
                        cur.execute(
                            "INSERT INTO books(id, title, url ) VALUES(%s, %s, %s)",
                            (idBook, name, file_url))
                        cur.execute("INSERT INTO downloadedbooks(user_id, book_id, first) VALUES(%s, %s, %s)",
                                    (rowUserAndAccount[0], idBook, True))
                        cur.execute("UPDATE users SET downloaded = %s, step = %s WHERE id = %s",
                                    (rowUserAndAccount[4] + 1, "search", callback_query.from_user.id))
                        conn.commit()
                        await download_messaggio.delete()

                    else:
                        await app.send_message(
                            text=messages[rowUserAndAccount[6]]['daily_limit_message'],
                            chat_id=callback_query.from_user.id)
    except Exception as e:
        app.send_message(
            text="<i><b>Eccezione callback, utente: " + callback_query.from_user.id + "</b>, log: " + str(e) + "</i>",
            chat_id=os.getenv('ACCOUNT_ID'))


async def create_account():
    cur = conn.cursor()

    async with httpx.AsyncClient() as http:
        response_creation = await http.post("https://api.simplelogin.io/api/alias/random/new", headers={
            "Authentication": api_token,
            "Content-Type": "application/json"
        },
                                            json={
                                                "mode": "uuid"
                                            })

    if response_creation.status_code == 201:
        random_string = ''.join(random.choice(string.ascii_lowercase) for i in range(10))
        random_number = random.randint(100, 999)
        username = random_string + str(random_number)

        alphabet = string.ascii_letters + string.digits + string.punctuation
        password = ''.join(secrets.choice(alphabet) for i in range(10))

        async with httpx.AsyncClient() as http:
            response_registrazione = await http.post("https://singlelogin.se/papi/user/verification/send-code",
                                                     data={'email': response_creation.json()['alias'],
                                                           'password': password,
                                                           'name': username,
                                                           'rx': 215,
                                                           'action': 'registration',
                                                           'site_mode': 'books',
                                                           'isSinglelogin': 1
                                                           })
        if response_registrazione.status_code == 200:
            await asyncio.sleep(30)
            mail = imaplib.IMAP4_SSL(imap_url)
            mail.login(str(gmail_user), str(gmail_pass))
            mail.select("inbox")
            result, data = mail.uid('search', None, '(UNSEEN SUBJECT "code")')
            email_ids = data[0].split()
            if email_ids:
                latest_email_id = email_ids[-1]

                mail.uid('store', latest_email_id, '+FLAGS', '(\\Seen)')

                result, email_data = mail.uid('fetch', latest_email_id, '(BODY.PEEK[])')

                raw_email = email_data[0][1]

                email_message = email.message_from_bytes(raw_email)

                code = (decode_header(email_message['Subject'])[0][0]).split()[0]

                verify_url = "https://singlelogin.se/rpc.php"

                async with httpx.AsyncClient() as http:
                    response_verifica = await http.post(verify_url,
                                                        data={
                                                            'isModal': True,
                                                            'email': response_creation.json()['alias'],
                                                            'password': password,
                                                            'name': username,
                                                            'rx': 215,
                                                            'action': 'registration',
                                                            'site_mode': 'books',
                                                            'isSinglelogin': 1,
                                                            'verifyCode': code,
                                                            'gg_json_mode': 1

                                                        })
                if response_verifica.status_code == 200:
                    info = json.dumps(dict(http.cookies)).encode()

                    cur.execute("SELECT COUNT(*) FROM accounts")
                    count = cur.fetchone()[0]

                    cur.execute(
                        "INSERT INTO accounts(id, act_users, cookies, email, password,username) VALUES (%s, %s, %s, "
                        "%s, %s, %s)",
                        (count + 1, 0,
                         base64.b64encode(cipher_suite.encrypt(info)).decode(),
                         base64.b64encode(cipher_suite.encrypt(response_creation.json()['alias'].encode())).decode(),
                         base64.b64encode(cipher_suite.encrypt(password.encode())).decode(),
                         base64.b64encode(cipher_suite.encrypt(username.encode())).decode()))
                    conn.commit()
                    async with httpx.AsyncClient() as http:
                        await http.delete(
                            f"https://api.simplelogin.io/api/aliases/{response_creation.json()['id']}", headers={
                                "Authentication": api_token,
                                "Content-Type": "application/json"
                            })

    else:
        print(f"Errore nella creazione dell'alias: {response_creation.content}")


async def reset_downloaded():
    cur = conn.cursor()

    cur.execute("UPDATE users SET downloaded = 0")
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    for user in users:

        try:
            await app.send_message(
                text=messages[user[6]]['download_reset'],
                chat_id=user[0])

        except:
            cur.execute("DELETE FROM users WHERE id = %s ", (user[0],))
            cur.execute("UPDATE accounts SET act_users = act_users - 1  WHERE id = %s", (user[2],))

    await app.send_message(
        text=" <i>🗓 Finita pulizia <b>download</b>!</i>",
        chat_id=os.getenv('ACCOUNT_ID'))

    conn.commit()


async def converter(cookies, file_url, last_message, callback_query, name, rowUserAndAccount):
    download_messaggio = await app.edit_message_text(
        text=messages[rowUserAndAccount[6]]['conversion_started'],
        message_id=last_message.id,
        chat_id=callback_query.from_user.id)
    async with httpx.AsyncClient() as http:
        moved = (await http.get(file_url + "?convertedTo=pdf", cookies=cookies, timeout=30)).headers['Location']
        lastMoved = await http.get(moved)

    await app.edit_message_text(
        text=messages[rowUserAndAccount[6]]['conversion_finished'],
        message_id=download_messaggio.id,
        chat_id=callback_query.from_user.id)

    file = BytesIO(lastMoved.content)
    file.name = name.split(".")[0] + ".pdf"

    return file


async def create_accounts():
    i = 0
    while i < 10:
        await create_account()
        await asyncio.sleep(30)
        i += 1
    await app.send_message(
        text=" <i>🗓 Creati <b>account</b>!</i>",
        chat_id=os.getenv('ACCOUNT_ID'))


async def url_shortener(complete):
    shorten_url = os.urandom(16).hex()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO urls (id, original_url, expiry) VALUES (%s, %s, %s)",
        (shorten_url, complete, datetime.now() + timedelta(days=7)))
    conn.commit()
    return shorten_url


async def get_original_url(shorten_url):
    cur = conn.cursor()
    cur.execute("SELECT * FROM urls WHERE id = %s",
                (shorten_url,))
    return cur.fetchone()[1]


async def send_message_followers(message):
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    users = cur.fetchall()
    for user in users:
        try:
            await message.forward(user[0])
            print("inviato " + str(user[0]))

        except:
            cur.execute("DELETE FROM users WHERE id = %s ", (user[0],))
            cur.execute("UPDATE accounts SET act_users = act_users - 1  WHERE id = %s", (user[2],))
            print("tolto utente " + str(user[0]))

    conn.commit()


async def clean_urls():
    cur = conn.cursor()
    cur.execute("DELETE FROM urls WHERE expiry < CURRENT_DATE")
    conn.commit()


def progress_bar(rowUserAndAccount, progress_message, app):
    async def progress(current, total):
        percent = float(current) / total

        rounded = round(percent * 100)
        if rounded % 5 == 0:
            filled_length = int(round(10 * percent))
            bar = ('📖' * filled_length) + ('📕' * (10 - filled_length))

            update_text = messages[rowUserAndAccount[6]]["progress_message"] + "\n\n" + f"[{bar}] {percent * 100:.1f}%"
            if (await app.get_messages(rowUserAndAccount[0], progress_message.id)).text == update_text:
                await progress_message.edit_text(update_text)
        if current == total:
            await progress_message.delete()

    return progress


scheduler = AsyncIOScheduler()
scheduler.add_job(reset_downloaded, 'cron', hour=21)
scheduler.add_job(create_accounts, 'cron', hour=22)
scheduler.add_job(clean_urls, 'cron', hour=23)

asyncio.run(create_accounts())

scheduler.start()

keep_alive()
app.run()

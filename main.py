import asyncio
import email
import json
import base64
import secrets
import string
import datetime
import re
import psycopg2
from PIL import Image

import random
from email.header import decode_header
import sys

import os
from io import BytesIO
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver

from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os
import pyshorteners
import lxml
from pyrogram import Client, filters
import tgcrypto
import imaplib
from bs4 import BeautifulSoup
import httpx
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto
from selenium.webdriver.common.by import By
from selenium.webdriver.support.wait import WebDriverWait

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

cur = conn.cursor()

key = os.getenv('ENCRYPTION_KEY')
cipher_suite = Fernet(key)

app = Client(name=os.getenv('BOT_NAME'), api_id=os.getenv('API_ID'), api_hash=os.getenv('API_HASH'),
             bot_token=os.getenv('BOT_TOKEN'))

options = webdriver.ChromeOptions()
options.add_argument("--headless")
options.add_argument("--disable-gpu")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")
driver = webdriver.Chrome(options=options)

shortener = pyshorteners.Shortener()

home_markup = InlineKeyboardMarkup([
    [InlineKeyboardButton("📣 Canale", url="t.me/FreeReadsChannel")],
    [InlineKeyboardButton("👤 Profilo", callback_data="profile"),
     InlineKeyboardButton("📄 Categorie", callback_data="categories")],
    [InlineKeyboardButton("🔥 Più popolari", callback_data="populars")],
    [InlineKeyboardButton("🇮🇹 Lingua", callback_data="language"),
     InlineKeyboardButton("🔧 Supporto", callback_data="assistence")]
])


# Comando start
@app.on_message(filters.command('start') & filters.private)
async def start(app, message):
    cur.execute("SELECT * FROM users WHERE id = %s",
                (message.from_user.id,))
    rowUser = cur.fetchone()

    if rowUser is None:
        sentMessage = await message.reply_text("""👋🏻 <i><b>Benvenuto!</b>

🔍 Per <b>cercare</b> un libro, invia il titolo qui. 

❗ Ricorda, hai a disposizione <b>5 download al giorno</b>. Fanne buon uso!</i>""", quote=True,
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
            "INSERT INTO users (id, last_message, account_id, download_limit, downloaded, step) VALUES (%s, %s, %s, "
            "%s, %s, %s)",
            (message.from_user.id, sentMessage.id, idAccount, 5, 0, "cerca"))
        conn.commit()

    if rowUser is not None:
        now = datetime.datetime.now()
        hour = datetime.datetime.now().replace(day=now.day, hour=22, minute=0, second=0)
        difference = hour - now

        await message.reply_text(
            text=f"""<i>👋🏻 <b>Bentornato!</b> 

📕 Oggi hai scaricato <b>{rowUser[4]}</b> libri.

🕛 Tra <b>{difference}</b> il counter verrà resettato!</i>""", reply_markup=home_markup
        )


# Ricerca
@app.on_message(filters.text & filters.private)
async def request(app, message):
    cur.execute("SELECT * FROM users WHERE id = %s",
                (message.from_user.id,))
    rowUser = cur.fetchone()

    if rowUser is not None and rowUser[5] == 'cerca':
        stateMessage = await app.send_message(text="🔍 <i>Sto cercando...</i>",
                                              chat_id=message.from_user.id)
        async with httpx.AsyncClient() as http:
            response = await http.get(domain + '/s/' + message.text, timeout=30)
        content = response.content
        soup = BeautifulSoup(content, 'lxml')
        box = soup.find("div", {"id": "searchResultBox"})
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
                resultJson['author'] = ' '.join(authorsText)
                result.append(resultJson)

            results = "✨ <i>Ecco i risultati per <b>" + message.text.strip().lower() + "</b>:</i> \n\n"

            listButtonsRow = []
            listButtonsTotal = []

            await app.edit_message_text(text="💡<i>Libro trovato! Sto elaborando i risultati...</i>",
                                        chat_id=message.from_user.id,
                                        message_id=stateMessage.id)

            for res in result[:10]:
                index = result.index(res)
                complete = domain + res['url']

                short_url = shortener.tinyurl.short(complete)
                if len(res['author']) == 0 and 'pub' not in res.keys() and 'year' not in res.keys():
                    results = results + f"""{index + 1})<b> {res['name']}</b> - <i>{res['lang']}</i>\n\n"""
                else:
                    results = results + f"""{index + 1})<b> {res['name']}</b> - <i>{res['lang']}</i>\n"""

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
                text=results + "👇🏻 <i>Per <b>visualizzare</b> i formati disponibili e <b>scaricare</b> il libro, "
                               "premi sul numero di riferimento tra quelli qui sotto.</i>",
                disable_web_page_preview=True, reply_markup=reply_markup,
                message_id=stateMessage.id, chat_id=message.from_user.id)
        else:
            await app.edit_message_text(
                text=f"❌ <i>Purtroppo, non ho trovato alcun libro con titolo <b>{message.text.strip().lower()}</b>.\n"
                     f"\n💡 Prova a scrivere il titolo in un altra <b>lingua</b>, o presta attenzione ad eventuali "
                     f"<b>errori</b>.</i>",
                message_id=stateMessage.id, chat_id=message.from_user.id)
        await message.delete()


@app.on_callback_query()
async def answer(app, callback_query):
    cur.execute("""
        SELECT users.*, accounts.*
        FROM users
        JOIN accounts ON users.account_id = accounts.id
        WHERE users.id = %s
    """, (callback_query.from_user.id,))

    rowUserAndAccount = cur.fetchone()

    if callback_query.data == "downloadedBooks":
        reply_markup = InlineKeyboardMarkup([[InlineKeyboardButton("↩️ Indietro", callback_data="profile")]])
        await app.edit_message_text(text="downloadedBooks",
                                    chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                    reply_markup=reply_markup)

    if callback_query.data == "profile":
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Libri scaricati", callback_data="downloadedBooks"),
             InlineKeyboardButton("⭐ Preferiti", callback_data="favorites")],
            [InlineKeyboardButton("🔖 Lista desideri", callback_data="wishList")],
            [InlineKeyboardButton("↩️ Indietro", callback_data="home")]
        ])

        await app.edit_message_text(text="💭 <i> Questo è la sezione dedicata al tuo profilo!</i>",
                                    chat_id=callback_query.from_user.id, message_id=callback_query.message.id,
                                    reply_markup=reply_markup)

    if callback_query.data == "home":
        now = datetime.datetime.now()
        hour = datetime.datetime.now().replace(day=now.day, hour=22, minute=0, second=0)
        difference = hour - now

        await app.edit_message_text(
            text=f"""<i>👋🏻 <b>Bentornato!</b> 

📕 Oggi hai scaricato <b>{rowUserAndAccount[4]}</b> libri.

🕛 Tra <b>{difference}</b> il counter verrà resettato!</i>""", reply_markup=home_markup,
            chat_id=callback_query.from_user.id, message_id=callback_query.message.id
        )

    if callback_query.data.split("/", 1)[0] == "formats":

        formatState = await app.send_message(text="📃<i> Sto verificando i formati disponibili...</i>",
                                             chat_id=callback_query.from_user.id)

        url = callback_query.data.split("/", 1)[1]
        cipher_text = base64.b64decode(rowUserAndAccount[8])
        cookies = json.loads(cipher_suite.decrypt(cipher_text).decode())
        async with httpx.AsyncClient() as http:
            responseTiny = await http.get(url)
        original_url = responseTiny.headers['Location']
        driver.get(original_url)

        for name, value in cookies.items():
            cookie = {"name": name, "value": value}
            driver.add_cookie(cookie)

        driver.refresh()

        await app.edit_message_text(text=f"⏳ <i>Carico le informazioni...</i>",
                                    chat_id=callback_query.from_user.id, message_id=formatState.id)
        # try:
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a.addDownloadedBook"))
        )

        html = driver.page_source
        soup = BeautifulSoup(html, 'html.parser')
        drop = soup.find('ul', {'class': 'dropdown-menu'})
        downloadListHoriz = []
        downloadListVert = []
        aButton = soup.find('a', {'class': 'btn btn-primary addDownloadedBook'}, href=True)
        urlButton = aButton.get('href')
        completeButton = "https://z-library.se" + urlButton
        shortButton = shortener.tinyurl.short(completeButton)

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
                short_url = shortener.tinyurl.short(complete)

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
        cover = soup.find("div", {"class": "z-book-cover covered"}).find("img").get("src")
        async with httpx.AsyncClient() as http:
            coverFile = (await http.get(cover))
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
        print(buffer.getvalue())
        await app.send_photo(photo=buffer,
                             caption=f"✨<i> Ecco i formati disponibili per <b>{book.text.strip().lower()}</b>.\n\n📕 Scegli "
                                     f"quello che preferisci, clicca il bottone, e partirà il <b>download</b>.</i>",
                             reply_markup=reply_markup, chat_id=callback_query.from_user.id)

        await formatState.delete()

    # except:
    #   await app.edit_message_text(
    #      text=f"🥺<i> Purtroppo, il libro potrebbe non essere più <b>disponibile</b>.\n\n📖 Prova a "
    #          f"scegliere un'<b>edizione</b> diversa.</i>",
    #    chat_id=callback_query.from_user.id,
    #   message_id=formatState.id)

    if callback_query.data.split("/", 1)[0] == "download":

        urlNotClean = callback_query.data.split("/", 1)[1]
        url = urlNotClean.split("-", 1)[0]

        async with httpx.AsyncClient() as http:
            responseTiny = await http.get(url)
            file_url = responseTiny.headers['Location']
        idBook = re.search(r'/dl/(\d+)/', file_url).group(1)
        print(file_url)
        print(idBook)

        cur.execute("SELECT * FROM books WHERE id = %s", (idBook,))
        rowBook = cur.fetchone()
        if rowBook is not None:

            download_messaggio = await app.send_message(
                text="✉️ <i>Ho iniziato il <b>download</b>. Attendi in linea!</i>",
                chat_id=callback_query.from_user.id)

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
                file = await converter(cookies, rowBook[2], download_messaggio, callback_query, name)

            if rowBookAndUser is not None:
                await app.send_document(callback_query.from_user.id, file,
                                        caption=f"🎁 <i>Avevi <b>già</b> scaricato questo libro, forse in un "
                                                f"formato diverso, quindi sei anco"
                                                f"ra a <b>{rowUserAndAccount[4]}</b> download!</i>")
            if rowBookAndUser is None:
                await app.send_document(document=file,
                                        caption=f"❕ <i>Questo libro è già stato scaricato da un altro <b>utente</b>!\n\nPer questo, sei ancora a <b>{rowUserAndAccount[4]}</b> download!</i>",
                                        chat_id=callback_query.from_user.id)

                cur.execute("INSERT INTO downloadedbooks(user_id, book_id, first) VALUES(%s, %s , %s)",
                            (rowUserAndAccount[0], rowBook[0], False))

                conn.commit()
            await download_messaggio.delete()

        if rowBook is None:
            if rowUserAndAccount is not None and rowUserAndAccount[4] < rowUserAndAccount[3]:
                download_messaggio = await app.send_message(
                    text="✉️ <i>Ho iniziato il <b>download</b>. Attendi in linea!</i>",
                    chat_id=callback_query.from_user.id)

                cipher_text = base64.b64decode(rowUserAndAccount[8])
                cookies = json.loads(cipher_suite.decrypt(cipher_text).decode())

                async with httpx.AsyncClient() as http:
                    responseTiny = await http.get(url)
                    file_url = responseTiny.headers['Location']
                    res = await http.get(file_url, cookies=cookies)
                    last = await http.get(res.headers['Location'])

                file = BytesIO(last.content)
                name = re.search(r'filename="(.+?)"', last.headers['content-disposition']).group(1).replace(
                    ' (Z-Library)',
                    '')
                file.name = name

                if "convert" in callback_query.data:
                    file = await converter(cookies, file_url, download_messaggio, callback_query, name)

                await app.send_document(document=file,
                                        caption=f"❕ <i>Download completato! Con questo, oggi hai scaricato <b>{rowUserAndAccount[4] + 1}</b> libro/i.</i>",
                                        chat_id=callback_query.from_user.id)
                cur.execute(
                    "INSERT INTO books(id, title, url ) VALUES(%s, %s, %s)",
                    (idBook, name, file_url))
                cur.execute("INSERT INTO downloadedbooks(user_id, book_id, first) VALUES(%s, %s, %s)",
                            (rowUserAndAccount[0], idBook, True))
                cur.execute("UPDATE users SET downloaded = %s WHERE id = %s",
                            (rowUserAndAccount[4] + 1, callback_query.from_user.id))
                conn.commit()
                await download_messaggio.delete()

            else:
                await app.send_message(
                    text="⚠️ <i>Purtroppo, hai raggiunto il tuo <b>limite</b> giornaliero. Non puoi più scaricare "
                         "libri per oggi.</i>",
                    chat_id=callback_query.from_user.id)


async def create_account():
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
    cur.execute("UPDATE users SET downloaded = 0")
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    for row in rows:
        await app.send_message(
            text="📌 <i>I <b>download</b> sono stati resettati!</i>",
            chat_id=row[0])

    await app.send_message(
        text=" <i>🗓 Finita pulizia <b>download</b>!</i>",
        chat_id=os.getenv('ACCOUNT_ID'))

    conn.commit()


async def converter(cookies, file_url, last_message, callback_query, name):
    download_messaggio = await app.edit_message_text(
        text="🔄 ️<i>Ho iniziato la <b>conversione</b>. Aspetta ancora qualche secondo...</i>",
        message_id=last_message.id,
        chat_id=callback_query.from_user.id)
    async with httpx.AsyncClient() as http:
        responseConversion = await http.get(file_url + "?convertedTo=pdf", cookies=cookies)
    moved = responseConversion.headers['Location']
    async with httpx.AsyncClient() as http:
        lastMoved = await http.get(moved)

    await app.edit_message_text(
        text="📁️ <i>Sto generando il <b>file</b>. Resta in linea...</i>",
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


scheduler = AsyncIOScheduler()
scheduler.add_job(reset_downloaded, 'cron', hour=22)
scheduler.add_job(create_accounts, 'cron', hour=23)
scheduler.start()

# scheduler.add_job(createAccount, 'interval', minutes=1)

app.run()

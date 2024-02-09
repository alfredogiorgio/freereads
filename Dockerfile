FROM python:3.12

WORKDIR /app

RUN apt-get update && apt-get install -y wget unzip

RUN wget https://dl.google.com/linux/deb/pool/main/g/google-chrome-stable/google-chrome-stable_114.0.5735.198-1_amd64.deb
RUN dpkg -i google-chrome-stable_114.0.5735.198-1_amd64.deb; apt-get -fy install

# Scarica, decomprimi e sposta ChromeDriver
RUN wget https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip
RUN unzip chromedriver_linux64.zip
RUN mv chromedriver /usr/bin/chromedriver
RUN chmod +x /usr/bin/chromedriver

COPY requirements.txt .

RUN pip install -r requirements.txt

COPY . .

CMD ["python3", "main.py"]
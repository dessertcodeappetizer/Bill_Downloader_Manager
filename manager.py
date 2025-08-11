"""!!Bill Manager!!"""

import configparser
import logging
import datetime
import os
import sys
import base64
import pandas
import json
import requests
import PyPDF2
import fitz
import time
import pytesseract
from pdf2image import convert_from_path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


class ConfigReader:
    """This class reads the confoguration file and make a dictionary."""
    def __init__(self, path):
        self.config_path = path
    
    def config_read(self):
        """It reads the config file and form config dictionary"""
        config = configparser.ConfigParser()
        config.read(self.config_path)
        con_dict = {}
        con_dict["bill_location"] = config["production"]["bill_location"]
        con_dict["excel_location"] = config["production"]["excel_location"]
        con_dict["log"] = config["production"]["log_location"]
        con_dict["prompt"] = config["production"]["prompt"]
        con_dict["api_key"] = config["production"]["api_key"]
        con_dict["ai_url"] = config["production"]["ai_url"]
        con_dict["model"] = config["production"]["model"]
        con_dict["query"] = config["production"]["query"]
        con_dict["save_folder"] = config["production"]["save_folder"]
        return con_dict
    
    def user_custom(self, con_dict):
        """This function is responsible for changing config data as per the user requirements."""
        days_ip = input("Enter the no. of days you want your bill processed: ")
        fol_loc = input("Enter the folder path: ")
        if days_ip != "":
            con_dict["query"] = con_dict["query"].replace(con_dict["query"][-2], days_ip)
        if fol_loc != "":
            con_dict["bill_location"] = fol_loc + '/'
        return con_dict


class Logger:
    """Log handler"""
    def __init__(self, config_dict):
        self.config_dict = config_dict
    def log(self):
        """It initiates logger."""
        dtime = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
        logger = logging.getLogger("BillLogger")
        logger.setLevel(logging.INFO)
        log_file = f"{self.config_dict['log']}manager_{dtime}.log"
        file_handler = logging.FileHandler(log_file)
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        print(f"Log_file: {log_file}")
        return logger


class Email_Manipulation:
    """This class is responsible for downloading the attachment into a proper folder in home
    environment."""
    def authenticate_gmail(self, logger):
        """Responsible for authenticating into the gmail with the help of client secret."""
        logger.info("Executing under authentication_gmail() of Email_Manipulation class.")
        # If modifying these SCOPES, delete the token.json file.
        SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
        creds = None
        # token.json stores user access and refresh tokens
        if os.path.exists('token.json'):
            logger.info("Token found!")
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        # If no valid credentials, initiate login flow
        if not creds or not creds.valid:
            logger.info("No valid credentials found, initiating login flow.")
            if creds and creds.expired and creds.refresh_token:
                logger.info("Credentials Expired! Refreshing!!!")
                creds.refresh(Request())
            else:
                logger.info("No credentials found. Using credentials.json for authentication.")
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for next run
            with open('token.json', 'w') as token:
                logger.info("Saving credentials for the next run")
                token.write(creds.to_json())
        return creds

    def search_emails(self, service, query, logger):
        logger.info("Executing under search_email() function of Email_Manipulation class.")
        try:
            results = service.users().messages().list(userId='me', q=query).execute()
            messages = results.get('messages', [])
            return messages
        except HttpError as error:
            logger.error(f'An error occurred: {error}')
            return []

    def get_attachments(self, service, msg_id, logger, bill_path):
        logger.info("Executing under get_attachments function of Email_Manipulation class.")
        try:
            logger.info("Trying to get the attachment and download.")
            message = service.users().messages().get(userId='me', id=msg_id).execute()
            payload = message.get('payload', {})
            parts = payload.get('parts', [])
            counter = 0
            for part in parts:
                filename = part.get("filename")
                body = part.get("body", {})
                data = body.get("data")
                attachment_id = body.get("attachmentId")
                if filename:
                    if not data:
                        attachment = service.users().messages().attachments().get(
                            userId='me', messageId=msg_id, id=attachment_id
                        ).execute()
                        data = attachment.get("data")
                    file_data = base64.urlsafe_b64decode(data.encode("UTF-8"))
                    path = os.path.join(bill_path, filename)
                    with open(path, "wb") as f:
                        f.write(file_data)
                    logger.info(f"Downloaded: {filename}")
                    print(f"Downloaded: {filename}")
                    # time_date = datetime.datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]
                    # rename_file_name = f"Bill_{time_date}.pdf"
                    # os.rename(bill_path + filename, bill_path + rename_file_name)
                    # logger.info(f"File renamed from {filename} to {rename_file_name}")
                    counter += 1
                    break
            logger.info(f"No. of files downloaded: {counter}")
        except HttpError as error:
            logger.error(f"An error occurred: {error}")

 
class Filter:
    """It filters based on pdf types."""
    def __init__(self, config_dict, log):
        self.config_dict = config_dict
        self.log = log
        
    def bill_path_generator(self):
        """It generates full path of the available pdf."""
        self.log.info("Executing under bill_path_generator() of Filter class.")
        file_paths = []
        for filename in os.listdir(self.config_dict["bill_location"]):
            full_path = os.path.join(self.config_dict["bill_location"], filename)
            if os.path.isfile(full_path):
                file_paths.append(full_path)
        self.log.info(f"Available bills are: {file_paths}")
        self.log.info(f"Available bill count: {len(file_paths)}")
        print(f"No. of bills found from the target folder: {len(file_paths)}")
        return file_paths
    
    def image_or_text(self, file_paths):
        """Bufurcating wrt image and text based pdf."""
        self.log.info("Executing under image_or_text() of Filter class.")
        print("Processing the downloaded pdf.")
        image, texts = [], []
        for pdf_path in file_paths:
            doc = fitz.open(pdf_path)
            for page in doc:
                text = page.get_text("text")
                if text.strip():
                    texts.append(pdf_path)
                else:
                    image.append(pdf_path)
                break
        self.log.info(f"Path of image based pdf are: {image}")
        self.log.info(f"Path of text based pdf are: {texts}")
        return image, texts


class Reader:
    """Responsible for reading pdf files."""
    def __init__(self, log, text, image):
        self.log = log
        self.texts = text
        self.image = image
    
    def reader_pypdf2(self):
        """Takes care of text based pdf."""
        self.log.info("Executing under reader_pypdf2() of Reader class.")
        all_text_file_data = []
        for files in self.texts:
            with open(files, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
            all_text_file_data.append([text])
            all_text_file_data.append(files)
        # self.log.info(f"Getting text based bill output as: {all_text_file_data}")
        return all_text_file_data

    def reader_pytesseract(self):
        """Takes care of image based pdf."""
        self.log.info("Executing under reader_pytesseract() of Reader class.")
        text = ""
        all_img_file_data = []
        for val in self.image:
            for img in convert_from_path(val):
                text += pytesseract.image_to_string(img) + "\n"
            all_img_file_data.append(text)
            all_img_file_data.append(val)
        # self.log.info(f"Getting image based bill output as: {all_img_file_data}")
        return all_img_file_data

  
class Ai_modulator:
    def __init__(self, text, image, api_key, prompt, log, ai_url, model):
        """Uses AI to filter useful informations."""
        self.text = text
        self.image = image
        self.api_key = api_key
        self.prompt = prompt
        self.ai_url = ai_url
        self.model = model
        self.log = log
        
    def ask_ai(self):
        self.log.info("Executing under ask_ai() of Ai_modulator class.")
        print("Initiating AI agent to fetch the details from the pdf. It may take a while...")
        url = self.ai_url
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "user", "content": self.prompt + f"PDF Content:\n{[self.text, self.image]}"}
            ],
            "temperature": 0.2
        }
        print("Thanks for your patience!!!")
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                ai_res = response.json()["choices"][0]["message"]["content"]
                self.log.info(f"Getting result from AI as: {ai_res}")
                return ai_res
            else:
                self.log.error(f"Error: {response.status_code}, {response.text}")
                print(f"Error: {response.status_code}, {response.text}")
                print("Terminating!")
                sys.exit()
        except Exception as error:
            self.log.error(f"Getting error as in ask_ai function: {error}")
            print("Terminating!")
        
    
class Writer:
    """It writes CSV from the json data it receives from Ai_modulator"""
    def __init__(self, ai_data, log, excel_path):
        self.ai_data = ai_data
        self.log = log
        self.excel = excel_path
    
    def csv_writer(self):
        """CSV writing"""
        self.log.info("Executing under csv_writer() of Writer class.")
        try:
            dtime = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            data = json.loads(self.ai_data)
            print(f"No. of bills getting written into CSV: {len(data)}")
            self.log.info(f"No. of bills getting written into CSV: {len(data)}")
            df = pandas.DataFrame(data)
            df["Expanse_Date"] = pandas.to_datetime(df["Expanse_Date"], format="%d/%m/%Y", errors='coerce')
            df.to_csv(f"{self.excel}Bill_{dtime}.csv", index=False)
            self.log.info("File writing successful!")
            print(f"CSV writing at {self.excel} Success!!!")
        except Exception as error:
            raise f"Getting error while writing file: {error} Unsuccessful!!!"
            # self.log.error(f"Getting error while writing file: {error}")
 
        
def main():
    object1 = ConfigReader("config.ini")
    res1 = object1.config_read()
    res1 = object1.user_custom(res1)
    object2 = Logger(res1)
    res2 = object2.log()
    object3 = Email_Manipulation()
    res3 = object3.authenticate_gmail(res2)
    res4 = build('gmail', 'v1', credentials=res3)
    res5 = object3.search_emails(res4, res1["query"], res2)
    for msg in res5:
        object3.get_attachments(res4, msg['id'], res2, res1["bill_location"])
        time.sleep(1)
    object4 = Filter(res1, res2)
    image, text = object4.image_or_text(object4.bill_path_generator())
    object5 = Reader(res2, text, image)
    txt = object5.reader_pypdf2()
    img = object5.reader_pytesseract()
    object6 = Ai_modulator(txt, img, res1["api_key"], res1["prompt"], res2, res1["ai_url"], res1["model"])
    res6 = object6.ask_ai()
    object7 = Writer(res6, res2, res1["excel_location"])
    object7.csv_writer()
    

if __name__ == "__main__":
    main()

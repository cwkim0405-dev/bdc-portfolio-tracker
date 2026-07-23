# config.py
from dotenv import load_dotenv
import os

load_dotenv()  # .env 파일의 내용을 환경 변수로 로드

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

SEC_USER_AGENT = "Chanwoo Kim cwkim0405@gmail.com"
SEC_BASE_URL = "https://data.sec.gov"
BXSL_CIK = "0001736035"
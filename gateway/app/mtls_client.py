"""
gateway - mtls_client.py 
"""

import ssl
import httpx
from pathlib import Path

CERT_DIR = Path("/certs")

def get_mtls_client() -> httpx.AsyncClient:
    # загрузка корневого сертификата CA, чтобы проверять сертификат сервера
    ssl_context = ssl.create_default_context(cafile=str(CERT_DIR / "ca.crt")) 

    # загрузка клиентского сертификата и приватного ключа
    # при mTLS сервер запрашивает клиентский сертификат, и если он подписан тем же CA и валиден, соединение устанавливается
    ssl_context.load_cert_chain(certfile=str(CERT_DIR / "client.crt"), keyfile=str(CERT_DIR / "client.key")) 

    # на всякий случай отключение проверки имени хоста в сертификате сервера
    # (сертификат выпущен на CN=nginx, а клиент обращается по этому же имени, но иногда в контейнерах могут быть расхождения)
    ssl_context.check_hostname = False 

    return httpx.AsyncClient(verify=ssl_context)
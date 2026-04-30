import requests
import json

ports = [5050, 54640, 63459, 58009]

def check():
    for port in ports:
        try:
            url = f"http://127.0.0.1:{port}/"
            resp = requests.get(url, timeout=2)
            print(f"Port {port}: UP (Status {resp.status_code})")
            print(f"Resp: {resp.json()}")
        except Exception as e:
            print(f"Port {port}: DOWN")

if __name__ == "__main__":
    check()

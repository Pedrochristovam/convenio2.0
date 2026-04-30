import os
import httpx
import asyncio
from dotenv import load_dotenv
import base64

async def test_ocr():
    load_dotenv()
    api_key = os.getenv("GOOGLE_VISION_API_KEY")
    print(f"Testando com chave: {api_key[:10]}...")
    
    url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
    
    # Imagem mínima (1x1 transparente)
    pixel = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0bIDAT\x08\x99c\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdcD\x1e\xe7\x00\x00\x00\x00IEND\xaeB`\x82'
    base64_image = base64.b64encode(pixel).decode("utf-8")
    
    payload = {
        "requests": [{
            "image": {"content": base64_image},
            "features": [{"type": "TEXT_DETECTION"}]
        }]
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, json=payload, timeout=30.0)
            print(f"Status: {response.status_code}")
            print(f"Resposta: {response.text[:500]}")
        except Exception as e:
            print(f"Erro na chamada: {e}")

if __name__ == "__main__":
    asyncio.run(test_ocr())

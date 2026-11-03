from dotenv import load_dotenv
load_dotenv()
from app import create_app


app = create_app()

if __name__ == '__main__':
    # host='0.0.0.0' diz ao Flask para escutar em TODAS as redes (127.0.0.1 e 192.168.0.20)
    app.run(host='0.0.0.0', port=5000, debug=True)
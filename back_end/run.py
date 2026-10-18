# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    # O host '0.0.0.0' permite que o telemóvel encontre o computador na rede local
    app.run(debug=True, host='0.0.0.0', port=5000)

from app import app
from flask import jsonify

@app.route('/')
def health_check():
    return jsonify({'status': 'ok'}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=3000)

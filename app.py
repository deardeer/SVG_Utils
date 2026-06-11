from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
import glob

app = Flask(__name__)

# 配置 CORS，允许所有来源访问
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# 或者更简单的配置
# CORS(app)  # 这也会允许所有来源

@app.route('/data/get_image_list')
def get_image_list():
    image_dir = './data/animals100_median/'
    images = []
    
    if os.path.exists(image_dir):
        for file in glob.glob(os.path.join(image_dir, '*.jpg')):
            images.append(os.path.basename(file))
        for file in glob.glob(os.path.join(image_dir, '*.jpeg')):
            images.append(os.path.basename(file))
        for file in glob.glob(os.path.join(image_dir, '*.png')):
            images.append(os.path.basename(file))
        images = sorted(list(set(images)))
    
    return jsonify({
        'success': True,
        'images': images,
        'count': len(images),
        'path': image_dir
    })

# 添加静态文件服务路由
@app.route('/data/animals100_median/<path:filename>')
def serve_image(filename):
    return send_from_directory('./data/animals100_median', filename)

@app.route('/data/LayerVec/<path:filename>')
def serve_layervec(filename):
    return send_from_directory('./data/LayerVec', filename)

@app.route('/data/VISTA/<path:filename>')
def serve_vista(filename):
    return send_from_directory('./data/VISTA', filename)

@app.after_request
def after_request(response):
    """添加额外的 CORS 头"""
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

if __name__ == '__main__':
    # 允许外部访问，方便调试
    app.run(host='0.0.0.0', port=5002, debug=True)
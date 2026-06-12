from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
import os
import glob

app = Flask(__name__)

# 1. 统一由 Flask-CORS 处理跨域，支持 credentials 和本地 file:// 打开的 null origin
CORS(app, resources={
    r"/*": {
        "origins": "*",  # 如果前端用 file:// 双击打开，可以改为 ["*"] 或允许所有
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

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

# ==================== 静态文件服务路由 ====================

@app.route('/data/animals100_median/<path:filename>')
def serve_image(filename):
    return send_from_directory('./data/animals100_median', filename)

@app.route('/data/LayerVec/<path:filename>')
def serve_layervec(filename):
    return send_from_directory('./data/LayerVec', filename)

@app.route('/data/VISTA/<path:filename>')
def serve_vista(filename):
    return send_from_directory('./data/VISTA', filename)

# ✨ 补上你漏掉的 VISTA_clean 路由！
@app.route('/data/VISTA_clean/<path:filename>')
def serve_vista_clean(filename):
    return send_from_directory('./data/VISTA_clean', filename)

# ========================================================

# 🚨 注意：这里删除了引发 CORS 冲突的 @app.after_request 钩子

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
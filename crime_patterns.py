# crime_patterns.py
import json
import os


def get_crime_patterns(path="resources/crime_patterns.json"):
    """加载罪名映射表"""
    try:
        # 确保路径存在
        if not os.path.exists(path):
            # 尝试相对路径
            alt_path = os.path.join(os.path.dirname(__file__), path)
            if os.path.exists(alt_path):
                path = alt_path
            else:
                print(f"警告: 映射表文件不存在: {path}")
                return {}

        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            print(f"成功加载 {len(data)} 个罪名的映射表")
            return data
    except Exception as e:
        print(f"加载映射表失败: {e}")
        return {}